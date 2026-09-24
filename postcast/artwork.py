import hashlib
import threading
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib

from .config import USER_AGENT, artwork_cache_dir


class ArtworkCache:
    """Download podcast artwork and expose as Gdk.Texture on the main thread."""

    def __init__(self):
        self._mem = {}
        self._pending = {}
        self.dir = artwork_cache_dir()

    def load(self, url, size, on_ready):
        """on_ready(texture|None) called on the main thread; size in px."""
        if not url:
            GLib.idle_add(on_ready, None)
            return
        key = (url, size)
        if key in self._mem:
            GLib.idle_add(on_ready, self._mem[key])
            return

        # disk cache
        fp = self._disk_path(url, size)
        if fp.exists():
            try:
                tex = self._decode(fp, size)
                self._mem[key] = tex
                GLib.idle_add(on_ready, tex)
                return
            except Exception:
                pass

        if key in self._pending:
            self._pending[key].append(on_ready)
            return
        self._pending[key] = [on_ready]
        threading.Thread(
            target=self._fetch_worker, args=(url, size, fp, key), daemon=True
        ).start()

    def _disk_path(self, url, size):
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.dir / f"{h}-{size}.png"

    def _fetch_worker(self, url, size, fp, key):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            fp.write_bytes(data)
        except Exception:
            data = None

        def finish():
            callbacks = self._pending.pop(key, [])
            if data is None:
                for cb in callbacks:
                    try:
                        cb(None)
                    except Exception:
                        pass
                return
            try:
                tex = self._decode(fp, size)
                self._mem[key] = tex
            except Exception:
                tex = None
            for cb in callbacks:
                try:
                    cb(tex)
                except Exception:
                    pass

        GLib.idle_add(finish)

    @staticmethod
    def _decode(path, size):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(path), size, size, True
        )
        pixbuf = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        text = Gdk.Texture.new_for_pixbuf(pixbuf)
        return text

    def clear(self):
        self._mem.clear()
        try:
            for p in self.dir.glob("*"):
                p.unlink()
        except OSError:
            pass