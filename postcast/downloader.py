import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import logging
from pathlib import Path

from gi.repository import GLib

from .config import USER_AGENT
from .download_errors import DownloadError, classify_download_error

logger = logging.getLogger(__name__)


class DownloadManager:
    """Sequential background downloader with per-file progress callbacks."""

    def __init__(self, directory: Path, db=None):
        self.directory = directory
        self.db = db
        self.directory.mkdir(parents=True, exist_ok=True)
        self._queue = []
        self._lock = threading.Lock()
        self._current = None  # episode_id currently downloading
        self._cancel_flags = set()
        self._progress_pending = {}
        self._progress_timers = set()
        self._callbacks = {}
        self._stop_event = threading.Event()
        if self.db is not None:
            self.db.reconcile_download_jobs()
        self.worker = threading.Thread(target=self._run, daemon=True, name="postcast-download")
        self.worker.start()
        if self.db is not None:
            with self._lock:
                for job in self.db.download_jobs(statuses=("queued",)):
                    self._queue.append(self._job_item(job))

    # ------- public API (thread-safe) -------
    def enqueue(self, episode_id, audio_url, title, podcast_title, destination_dir=None):
        if self._stop_event.is_set():
            return False
        with self._lock:
            if self._stop_event.is_set():
                return False
            if self._current == episode_id or any(
                item["episode_id"] == episode_id for item in self._queue
            ):
                return False
            directory = Path(destination_dir or (self.directory / self._slug(podcast_title)))
            destination = directory / self._filename(audio_url, title)
            partial = destination.with_suffix(".part")
            if self.db is not None and not self.db.enqueue_download(
                episode_id, audio_url, destination, partial
            ):
                return False
            self._cancel_flags.discard(episode_id)
            self._queue.append({
                "episode_id": episode_id,
                "url": audio_url,
                "title": title,
                "podcast": podcast_title,
                "dir": directory,
                "destination": destination,
                "partial": partial,
            })
        return True

    def is_queued_or_active(self, episode_id):
        with self._lock:
            if self._current == episode_id:
                return True
            return any(item["episode_id"] == episode_id for item in self._queue)

    def state(self, episode_id):
        with self._lock:
            if self._current == episode_id:
                return "downloading"
            if any(item["episode_id"] == episode_id for item in self._queue):
                return "queued"
        if self.db is not None:
            job = self.db.download_job(episode_id)
            return job["status"] if job is not None else None
        return None

    def cancel(self, episode_id):
        job = self.db.download_job(episode_id) if self.db is not None else None
        with self._lock:
            self._cancel_flags.add(episode_id)
            self._queue = [i for i in self._queue if i["episode_id"] != episode_id]
        if self.db is not None:
            self.db.remove_download_job(episode_id)
        if job:
            Path(job["partial_path"]).unlink(missing_ok=True)

    def active_id(self):
        with self._lock:
            return self._current

    def shutdown(self, timeout=5):
        """Stop accepting work while preserving jobs for restart recovery."""
        with self._lock:
            self._queue.clear()
        self._stop_event.set()
        self.worker.join(timeout=timeout)

    # ------- internals -------
    def _run(self):
        while not self._stop_event.is_set():
            with self._lock:
                if self._queue:
                    current = self._queue.pop(0)
                else:
                    current = None
            if current is None:
                self._stop_event.wait(0.2)
                continue

            episode_id = current["episode_id"]
            with self._lock:
                self._current = episode_id
            if self.db is not None:
                self.db.update_download_job(episode_id, status="downloading", attempts=1)

            self._emit("download-started", episode_id)

            dest = current["dir"] / self._filename(current["url"], current["title"])
            current["dir"].mkdir(parents=True, exist_ok=True)
            completed, error = self._download(episode_id, current["url"], dest)

            with self._lock:
                self._current = None
                self._cancel_flags.discard(episode_id)

            if completed is not None:
                if self.db is not None:
                    self.db.remove_download_job(episode_id)
                self._emit("download-finished", episode_id, dest)
            else:
                if self.db is not None and error.kind != "cancelled":
                    self.db.update_download_job(
                        episode_id,
                        status="failed",
                        error_kind=error.kind,
                        error_message=error.message,
                    )
                self._emit("download-failed", episode_id, error)

    def _download(self, episode_id, url, dest):
        temppath = dest.with_suffix(".part")
        last_error = None
        for attempt in range(3):
            try:
                start = temppath.stat().st_size if temppath.exists() else 0
                headers = {"User-Agent": USER_AGENT}
                if start:
                    headers["Range"] = f"bytes={start}-"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resumed = start > 0 and resp.getcode() == 206
                    if not resumed:
                        start = 0
                    total = int(resp.headers.get("Content-Length") or 0) + start
                    if total and shutil.disk_usage(dest.parent).free < total - start:
                        raise OSError("Not enough free space for download")
                    mode = "ab" if resumed else "wb"
                    done = start
                    with open(temppath, mode) as fh:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            if self._stop_event.is_set():
                                return None, DownloadError(
                                    "shutdown", "Download paused for application shutdown."
                                )
                            if self._is_cancelled(episode_id):
                                fh.close()
                                temppath.unlink(missing_ok=True)
                                return None, DownloadError("cancelled", "Download cancelled.")
                            fh.write(chunk)
                            done += len(chunk)
                            if self.db is not None:
                                self.db.update_download_job(
                                    episode_id,
                                    bytes_downloaded=done,
                                    total_bytes=total or None,
                                )
                            if total:
                                self._emit("download-progress", episode_id, done / total)
                    if self._is_cancelled(episode_id):
                        temppath.unlink(missing_ok=True)
                        return None, DownloadError("cancelled", "Download cancelled.")
                    temppath.replace(dest)
                return dest, None
            except Exception as exc:
                last_error = self._classify_error(exc)
                logger.exception(
                    "Download attempt %d failed for episode %s", attempt + 1, episode_id
                )
                if attempt < 2 and not self._stop_event.wait(1 << attempt):
                    continue
                return None, last_error
        return None, last_error or DownloadError("unknown", "Download failed.")

    @staticmethod
    def _classify_error(exc):
        return classify_download_error(exc)

    def _is_cancelled(self, episode_id):
        with self._lock:
            return episode_id in self._cancel_flags

    @staticmethod
    def _job_item(job):
        destination = Path(job["destination_path"])
        return {
            "episode_id": job["episode_id"],
            "url": job["url"],
            "title": job["title"],
            "podcast": job["podcast_title"],
            "dir": destination.parent,
            "destination": destination,
            "partial": Path(job["partial_path"]),
        }

    def _filename(self, url, title):
        ext = Path(urllib.parse.urlparse(url).path).suffix or ".mp3"
        ext = ext[:5] if len(ext) <= 5 and ext.startswith(".") else ".mp3"
        safe = self._slug(title)[:80] or "episode"
        return f"{safe}{ext}"

    @staticmethod
    def _slug(text):
        text = re.sub(r"[^\w\s-]", "", text or "")
        text = re.sub(r"\s+", "-", text.strip())
        return text[:100].lower() or "podcast"

    def _emit(self, signal, *args):
        if signal == "download-progress":
            episode_id, progress = args
            with self._lock:
                self._progress_pending[episode_id] = progress
                if episode_id in self._progress_timers:
                    return
                self._progress_timers.add(episode_id)
            GLib.timeout_add(100, self._deliver_progress, episode_id)
            return
        GLib.idle_add(self._deliver, signal, args)

    def _deliver_progress(self, episode_id):
        with self._lock:
            progress = self._progress_pending.pop(episode_id, None)
        if progress is not None:
            for cb in self._callbacks.get("download-progress", []):
                try:
                    cb(episode_id, progress)
                except Exception:
                    pass
        with self._lock:
            if episode_id in self._progress_pending:
                return True
            self._progress_timers.discard(episode_id)
        return GLib.SOURCE_REMOVE

    def _deliver(self, signal, args):
        for cb in self._callbacks.get(signal, []):
            try:
                cb(*args)
            except Exception:
                pass

    def connect(self, signal, cb):
        self._callbacks.setdefault(signal, []).append(cb)
