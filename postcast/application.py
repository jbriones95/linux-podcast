import threading
import time

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject

from .config import APP_ID, APP_NAME, data_dir
from .database import Database
from .async_tasks import AsyncCoordinator
from .downloader import DownloadManager
from .artwork import ArtworkCache
from .feed import fetch_feed
from .player import Player
from .ui.playback import Playback
from .ui.window import MainWindow


class PostcastApplication(Adw.Application, GObject.Object):
    __gsignals__ = {
        "now-playing": (
            GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_PYOBJECT)),
        "position": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
        "seeked": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "playback-state": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "episode-finished": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "playback-error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "library-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "queue-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "refresh-finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "volume-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "rate-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "chapters-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "chapter-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        GLib.set_application_name(APP_NAME)
        self._db = None
        self._artwork = None
        self._downloads = None
        self._player = None
        self._playback = None
        self.window = None
        self._refresh_source = None
        self._refresh_thread = None
        self._mpris = None
        self._suspend_cookie = None
        self._playback_hold = False
        self._async_tasks = AsyncCoordinator()

    @property
    def db(self):
        if self._db is None:
            self._db = Database()
        return self._db

    @property
    def async_tasks(self):
        return self._async_tasks

    @property
    def artwork(self):
        if self._artwork is None:
            self._artwork = ArtworkCache()
        return self._artwork

    @property
    def downloads(self):
        if self._downloads is None:
            self._downloads = DownloadManager(self._download_dir(), self.db)
            self._downloads.connect("download-started", self._on_dl_started)
            self._downloads.connect("download-progress", self._on_dl_progress)
            self._downloads.connect("download-finished", self._on_dl_finished)
            self._downloads.connect("download-failed", self._on_dl_failed)
        return self._downloads

    @property
    def player(self):
        if self._player is None:
            self._player = Player()
        return self._player

    @property
    def playback(self):
        if self._playback is None:
            self._playback = Playback(self, self.player)
        return self._playback

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
        if self._downloads is not None:
            self._downloads.directory = pathlib.Path(path)

    # ---------- lifecycle ----------
    def do_startup(self):
        # Explicit dispatch is required by the PyGObject bindings shipped on
        # postmarketOS; bound super() dispatch loses the application argument.
        Adw.Application.do_startup(self)
        from .mpris import MprisService

        self._mpris = MprisService(self)
        for name, callback in (
            ("player-play-pause", lambda *_: self.playback.toggle()),
            ("player-previous", lambda *_: self.playback.smart_rewind()),
            ("player-next", lambda *_: self.playback.play_next()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        self.connect("playback-state", self._update_suspend_inhibition)

    def do_activate(self):
        if self.window is None:
            self.window = MainWindow(application=self)
            self.window.present()
            GLib.idle_add(self.window.finish_initial_focus_setup)
        else:
            self.window.present()
            GLib.idle_add(self.window.finish_initial_focus_setup)
        self._update_suspend_inhibition()
        if self._refresh_source is None:
            self._refresh_source = GLib.timeout_add_seconds(1800, self._scheduled_refresh)
            GLib.idle_add(self.refresh_feeds, True)

    def _scheduled_refresh(self):
        self.refresh_feeds(True)
        return True

    def start_refresh_feeds(self, notify_new=False):
        """Start a refresh and report whether work was accepted."""
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return False
        self.refresh_feeds(notify_new)
        return True

    def refresh_feeds(self, notify_new=False):
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return False
        previous_refresh = self.db.get_setting("last_refresh_at")

        def work():
            notifications = []
            for podcast in self.db.podcasts():
                try:
                    data, episodes = fetch_feed(podcast.feed_url)
                    self.db.upsert_podcast(data)
                    new_count = self.db.sync_episodes(podcast.id, episodes)
                    if notify_new and previous_refresh and new_count:
                        notifications.append((podcast.title, new_count))
                except Exception:
                    continue
            self.db.set_setting("last_refresh_at", str(int(time.time())))
            GLib.idle_add(self.refresh_library)
            GLib.idle_add(self._refresh_finished)
            for title, count in notifications:
                GLib.idle_add(self._notify_new_episodes, title, count)

        self._refresh_thread = threading.Thread(target=work, daemon=True, name="postcast-refresh")
        self._refresh_thread.start()
        return False

    def _refresh_finished(self):
        self.emit("refresh-finished")
        return GLib.SOURCE_REMOVE

    def refresh_podcast(self, podcast_id):
        """Refresh one feed through the same coordinator as refresh-all."""
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return False

        def work():
            try:
                podcast = self.db.podcast(podcast_id)
                if podcast is not None:
                    data, episodes = fetch_feed(podcast.feed_url)
                    self.db.upsert_podcast(data)
                    self.db.sync_episodes(podcast_id, episodes)
            except Exception:
                pass
            GLib.idle_add(self.refresh_library)
            GLib.idle_add(self._refresh_finished)

        self._refresh_thread = threading.Thread(
            target=work, daemon=True, name="postcast-refresh-feed"
        )
        self._refresh_thread.start()
        return True

    def _notify_new_episodes(self, podcast_title, count):
        if self.db.get_setting("notify_new_episodes", "1") != "1":
            return False
        notification = Gio.Notification.new("New podcast episodes")
        notification.set_body(f"{count} new episode{'s' if count != 1 else ''} from {podcast_title}")
        notification.set_icon(Gio.ThemedIcon.new("audio-x-generic-symbolic"))
        self.send_notification("new-episodes", notification)
        return False

    def do_shutdown(self):
        self._release_suspend_inhibition()
        if self._playback_hold:
            self.release()
            self._playback_hold = False
        if self._mpris is not None:
            self._mpris.stop()
            self._mpris = None
        if self._refresh_source is not None:
            GLib.source_remove(self._refresh_source)
            self._refresh_source = None
        if self._playback is not None:
            self._playback.shutdown()
        elif self._player is not None:
            self._player.close()
        if self._downloads is not None:
            self._downloads.shutdown()
        if self._artwork is not None:
            self._artwork.close()
        self._async_tasks.close()
        if self._db is not None:
            self._db.close()
        Adw.Application.do_shutdown(self)

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
        queued = self.downloads.enqueue(
            episode.id,
            episode.audio_url,
            episode.title,
            podcast.title if podcast else "Podcast",
        )
        self.toast("Downloading…" if queued else "Download already queued.")

    def toggle_favorite(self, episode):
        self.db.set_favorite(episode.id, not episode.favorite)
        self.refresh_library()

    def toggle_played(self, episode):
        self.db.mark_played(episode.id, not episode.played, 0)
        self.refresh_library()

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

    def _on_dl_failed(self, episode_id, error=None):
        self._refresh_dl_rows(episode_id, downloading=False)
        if error is not None and error.kind == "cancelled":
            return
        self.toast(error.message if error is not None else "Download failed.")

    def _update_suspend_inhibition(self, *_args):
        if self.player.state() == self.player.STATE_PLAYING:
            if not self._playback_hold:
                self.hold()
                self._playback_hold = True
            if self._suspend_cookie is None and self.window is not None:
                self._suspend_cookie = self.inhibit(
                    self.window,
                    Gio.ApplicationInhibitFlags.SUSPEND,
                    "Audio playback",
                )
        else:
            self._release_suspend_inhibition()
            if self._playback_hold:
                self.release()
                self._playback_hold = False

    def _release_suspend_inhibition(self):
        if self._suspend_cookie is not None:
            self.uninhibit(self._suspend_cookie)
            self._suspend_cookie = None

    def move_queue_item(self, episode_id, target_position):
        if self.db.move_queue_item(episode_id, target_position):
            self.playback.reload_queue()
            self.emit("queue-changed")

    def queue_changed(self):
        self.emit("queue-changed")

    def _refresh_dl_rows(self, episode_id, downloading):
        if self.window:
            self.window.update_episode_row_download(episode_id, downloading)

    # ---------- library ----------
    def refresh_library(self):
        self.emit("library-changed")

    def toast(self, message):
        if self.window:
            self.window.toast(message)
