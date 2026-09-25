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

logger = logging.getLogger(__name__)


class DownloadManager:
    """Sequential background downloader with per-file progress callbacks."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._queue = []
        self._lock = threading.Lock()
        self._current = None  # episode_id currently downloading
        self._cancel_flags = set()
        self._callbacks = {}
        self._stop_event = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True, name="postcast-download")
        self.worker.start()

    # ------- public API (thread-safe) -------
    def enqueue(self, episode_id, audio_url, title, podcast_title, destination_dir=None):
        if self._stop_event.is_set():
            return False
        with self._lock:
            self._queue.append({
                "episode_id": episode_id,
                "url": audio_url,
                "title": title,
                "podcast": podcast_title,
                "dir": destination_dir or (self.directory / self._slug(podcast_title)),
            })
        return True

    def is_queued_or_active(self, episode_id):
        with self._lock:
            if self._current == episode_id:
                return True
            return any(item["episode_id"] == episode_id for item in self._queue)

    def cancel(self, episode_id):
        with self._lock:
            self._cancel_flags.add(episode_id)
            self._queue = [i for i in self._queue if i["episode_id"] != episode_id]

    def active_id(self):
        with self._lock:
            return self._current

    def shutdown(self, timeout=5):
        """Stop accepting work and let the worker exit cleanly."""
        with self._lock:
            self._cancel_flags.update(item["episode_id"] for item in self._queue)
            if self._current is not None:
                self._cancel_flags.add(self._current)
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

            self._emit("download-started", episode_id)

            dest = current["dir"] / self._filename(current["url"], current["title"])
            current["dir"].mkdir(parents=True, exist_ok=True)
            completed = self._download(episode_id, current["url"], dest)

            with self._lock:
                self._current = None
                self._cancel_flags.discard(episode_id)

            if completed is not None:
                self._emit("download-finished", episode_id, dest)
            else:
                self._emit("download-failed", episode_id)

    def _download(self, episode_id, url, dest):
        temppath = dest.with_suffix(".part")
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
                            if episode_id in self._cancel_flags:
                                fh.close()
                                temppath.unlink(missing_ok=True)
                                return None
                            fh.write(chunk)
                            done += len(chunk)
                            if total:
                                self._emit("download-progress", episode_id, done / total)
                    temppath.rename(dest)
                return dest
            except Exception:
                logger.exception(
                    "Download attempt %d failed for episode %s", attempt + 1, episode_id
                )
                if attempt < 2 and not self._stop_event.wait(1 << attempt):
                    continue
                return None

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
        GLib.idle_add(self._deliver, signal, args)

    def _deliver(self, signal, args):
        for cb in self._callbacks.get(signal, []):
            try:
                cb(*args)
            except Exception:
                pass

    def connect(self, signal, cb):
        self._callbacks.setdefault(signal, []).append(cb)
