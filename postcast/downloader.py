import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from gi.repository import GLib

from .config import USER_AGENT


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
        self.worker = threading.Thread(target=self._run, daemon=True, name="postcast-download")
        self.worker.start()

    # ------- public API (thread-safe) -------
    def enqueue(self, episode_id, audio_url, title, podcast_title, destination_dir=None):
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

    # ------- internals -------
    def _run(self):
        while True:
            with self._lock:
                if self._queue:
                    current = self._queue.pop(0)
                else:
                    current = None
            if current is None:
                threading.Event().wait(0.2)
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
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                temppath = dest.with_suffix(".part")
                done = 0
                with open(temppath, "wb") as fh:
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
                            self._emit(
                                "download-progress",
                                episode_id,
                                done / total if total else 0.0,
                            )
                temppath.rename(dest)
            return dest
        except (urllib.error.URLError, OSError, Exception) as exc:
            dest.with_suffix(".part").unlink(missing_ok=True)
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