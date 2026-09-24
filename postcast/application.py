from gi.repository import Gio, GLib, Adw, GObject

from .config import APP_ID, APP_NAME
from .database import Database
from .downloader import DownloadManager
from .artwork import ArtworkCache
from .player import Player
from .ui.playback import Playback
from .ui.window import MainWindow


class PostcastApplication(Adw.Application, GObject.Object):
    __gsignals__ = {
        "now-playing": (
            GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_PYOBJECT)),
        "position": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
        "playback-state": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "episode-finished": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "playback-error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "library-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        GLib.set_application_name(APP_NAME)
        self.db = Database()
        self.artwork = ArtworkCache()
        self.downloads = DownloadManager(self._download_dir())
        self.player = Player()
        self.playback = Playback(self, self.player)
        self.window = None

        self.downloads.connect("download-started", self._on_dl_started)
        self.downloads.connect("download-progress", self._on_dl_progress)
        self.downloads.connect("download-finished", self._on_dl_finished)
        self.downloads.connect("download-failed", self._on_dl_failed)

    # ---------- paths/settings ----------
    def _download_dir(self):
        from .config import default_download_dir
        saved = self.db.get_setting("download_dir")
        import pathlib
        return pathlib.Path(saved) if saved else default_download_dir()

    def set_download_dir(self, path):
        import pathlib
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
        self.db.set_setting("download_dir", str(path))
        self.downloads.directory = pathlib.Path(path)

    # ---------- lifecycle ----------
    def do_activate(self):
        if self.window is None:
            self.window = MainWindow(application=self)
            self.window.present()
        else:
            self.window.present()

    # ---------- download toggle ----------
    def download_toggle(self, episode):
        if self.downloads.is_queued_or_active(episode.id):
            self.downloads.cancel(episode.id)
            self.toast("Cancelled download.")
            return
        if episode.is_downloaded:
            from pathlib import Path
            self.toast("Already downloaded.")
            return
        podcast = self.db.podcast(episode.podcast_id)
        self.downloads.enqueue(
            episode.id,
            episode.audio_url,
            episode.title,
            podcast.title if podcast else "Podcast",
        )
        self.toast("Downloading…")

    def _on_dl_started(self, episode_id):
        self._refresh_dl_rows(episode_id, downloading=True)

    def _on_dl_progress(self, episode_id, progress):
        if self.window:
            self.window.update_download_progress(episode_id, progress)

    def _on_dl_finished(self, episode_id, path):
        self.db.set_downloaded(episode_id, str(path))
        self._refresh_dl_rows(episode_id, downloading=False)
        self.toast("Download done.")
        if self.window:
            self.window.refresh_current_page()

    def _on_dl_failed(self, episode_id):
        self._refresh_dl_rows(episode_id, downloading=False)
        self.toast("Download failed.")

    def _refresh_dl_rows(self, episode_id, downloading):
        if self.window:
            self.window.update_episode_row_download(episode_id, downloading)

    # ---------- library ----------
    def refresh_library(self):
        self.emit("library-changed")

    def toast(self, message):
        if self.window:
            self.window.toast(message)