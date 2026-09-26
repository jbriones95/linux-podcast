import hashlib
import os
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib

from .config import USER_AGENT, artwork_cache_dir


MAX_ARTWORK_BYTES = 8 * 1024 * 1024


class ArtworkCache:
    """Download and decode artwork away from the GTK main loop."""

    def __init__(self):
        self._mem = {}
        self._pending = {}
        self._failed = set()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="postcast-art")
        self.dir = artwork_cache_dir()

    def load(self, url, size, on_ready):
        """Call on_ready(texture|None) on the GTK main thread."""
        if not url:
            GLib.idle_add(on_ready, None)
            return
        key = (url, int(size))
        if key in self._mem:
            GLib.idle_add(on_ready, self._mem[key])
            return
        if key in self._failed:
            GLib.idle_add(on_ready, None)
            return

        with self._lock:
            if key in self._pending:
                self._pending[key].append(on_ready)
                return
            self._pending[key] = [on_ready]

        source = self._source_path(url)
        if source.exists():
            self._executor.submit(self._decode_worker, source, size, key)
        elif self._legacy_path(url, size).exists():
            self._executor.submit(self._decode_worker, self._legacy_path(url, size), size, key)
        else:
            self._executor.submit(self._fetch_worker, url, source, size, key)

    def _source_path(self, url):
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.dir / f"{digest}.source"

    def cached_uri(self, url):
        if not url:
            return ""
        source = self._source_path(url)
        if source.exists():
            return Gio.File.new_for_path(str(source)).get_uri()
        return ""

    def _legacy_path(self, url, size):
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.dir / f"{digest}-{size}.png"

    def _fetch_worker(self, url, source, size, key):
        data = bytearray()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_ARTWORK_BYTES:
                    raise ValueError("artwork is too large")
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_ARTWORK_BYTES:
                        raise ValueError("artwork is too large")
            source.parent.mkdir(parents=True, exist_ok=True)
            temporary = source.with_suffix(f".{threading.get_ident()}.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, source)
            self._decode_worker(source, size, key)
        except Exception:
            self._finish(key, None, failed=True)

    def _decode_worker(self, source, size, key):
        try:
            pixbuf = self._decode_pixbuf(source, size)
        except Exception:
            pixbuf = None
        self._finish(key, pixbuf)

    def _finish(self, key, pixbuf, failed=False):
        def deliver():
            with self._lock:
                callbacks = self._pending.pop(key, [])
            texture = None
            if pixbuf is not None:
                try:
                    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                    self._mem[key] = texture
                except Exception:
                    failed_result = True
                else:
                    failed_result = False
            else:
                failed_result = True
            if failed or failed_result:
                self._failed.add(key)
            for callback in callbacks:
                try:
                    callback(texture)
                except Exception:
                    pass
            return GLib.SOURCE_REMOVE

        GLib.idle_add(deliver)

    @staticmethod
    def _decode_pixbuf(path, size):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
        side = min(pixbuf.get_width(), pixbuf.get_height())
        x = (pixbuf.get_width() - side) // 2
        y = (pixbuf.get_height() - side) // 2
        pixbuf = pixbuf.new_subpixbuf(x, y, side, side)
        return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)

    def clear(self):
        self._mem.clear()
        self._failed.clear()
        try:
            for path in self.dir.glob("*"):
                path.unlink()
        except OSError:
            pass

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
