import threading
from pathlib import Path

from gi.repository import Adw, Gtk, GLib

from ..feed import FeedError, fetch_feed
from ..search import search_podcasts
from ..ui.library_page import LibraryPage
from ..ui.podcast_page import PodcastPage
from ..ui.search_page import SearchPage
from ..ui.settings_page import SettingsPage


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="Postcast")
        self.app = application
        self._toast_overlay = Adw.ToastOverlay.new()
        self.set_content(self._toast_overlay)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(root)

        self.nav = Adw.NavigationView()
        self.library = LibraryPage(self)
        self.nav.add(self.library)
        root.append(self.nav)

        from .player_bar import PlayerBar
        self.player_bar = PlayerBar(self)
        root.append(self.player_bar)

        self.app.connect("position", self._on_position)
        self.app.connect("playback-state", self._on_playback_state)
        self.app.connect("episode-finished", self._on_episode_finished)
        self.app.connect("playback-error", self._on_playback_error)
        self.app.connect("library-changed", self._on_library_changed)
        self.app.connect("now-playing", self._on_now_playing)

        self.set_default_size(420, 760)

    # ---------- public helpers ----------
    def toast(self, message):
        self._toast_overlay.add_toast(Adw.Toast.new(message))

    def _on_now_playing(self, app, podcast, episode):
        self.player_bar.set_episode(episode, podcast)
        self._refresh_rows()

    def play_episode(self, episode, podcast):
        queue = self.app.db.episodes(podcast.id)
        self.app.playback.play_episode(podcast, episode, queue)
        self._refresh_rows()

    def is_current(self, episode_id):
        return (
            self.app.playback.current_episode()
            and self.app.playback.current_episode().id == episode_id
        )

    def play_next(self):
        self.app.playback.play_next()

    def current_page(self):
        return self.nav.get_visible_page()

    # ---------- navigation ----------
    def open_podcast(self, podcast_id):
        page = PodcastPage(self, podcast_id)
        self.nav.push(page)

    def add_dialog(self):
        entry = Gtk.Entry(placeholder_text="https://…/feed.xml")
        entry.set_hexpand(True)
        dialog = Adw.AlertDialog.new(
            "Add podcast",
            "Enter the RSS/Atom feed URL of the podcast to subscribe to.",
        )
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")

        def on_response(dlg, resp):
            if resp != "add":
                return
            url = entry.get_text().strip()
            if url:
                self._subscribe(url)

        dialog.connect("response", on_response)
        dialog.present(self)

    def open_search(self):
        page = SearchPage(self)
        self.nav.push(page)

    def open_settings(self):
        page = SettingsPage(self)
        self.nav.push(page)

    # ---------- feed subscribe helper (main-thread safe) ----------
    def _subscribe(self, feed_url, on_done=None):
        def work():
            try:
                podcast, episodes = fetch_feed(feed_url)
            except FeedError as exc:
                GLib.idle_add(
                    self._subscribe_done,
                    None,
                    {"feed_url": feed_url, "error": str(exc)},
                    on_done,
                )
                return
            podcast_id = self.app.db.upsert_podcast(podcast)
            self.app.db.sync_episodes(podcast_id, episodes)
            GLib.idle_add(self._subscribe_done, podcast_id, None, on_done)

        threading.Thread(target=work, daemon=True).start()

    def _subscribe_done(self, podcast_id, err, on_done=None):
        if on_done:
            on_done(podcast_id, err)
        self.app.refresh_library()
        self.library.refresh()
        if podcast_id and err is None:
            self.toast("Subscribed!")
            self.open_podcast(podcast_id)
        elif err is not None:
            self.toast(f"Could not add feed: {err.get('error','')}")

    # ---------- feed refresh ----------
    def refresh_feed(self, podcast_id):
        def work():
            podcast = self.app.db.podcast(podcast_id)
            if podcast is None:
                return
            try:
                data, episodes = fetch_feed(podcast.feed_url)
            except FeedError as exc:
                GLib.idle_add(self.toast, f"Refresh failed: {exc}")
                return
            self.app.db.upsert_podcast(data)
            self.app.db.sync_episodes(podcast_id, episodes)
            GLib.idle_add(self._feed_refreshed, podcast_id)

        threading.Thread(target=work, daemon=True).start()

    def _feed_refreshed(self, podcast_id):
        self.app.refresh_library()
        self.library.refresh()
        if isinstance(self.current_page(), PodcastPage):
            self.current_page().rebuild()
        self.toast("Feed updated.")

    # ---------- search ----------
    def search(self, term, on_results):
        def work():
            try:
                results = search_podcasts(term)
                results = [r for r in results]
            except Exception as exc:
                results = exc
            GLib.idle_add(on_results, results)

        threading.Thread(target=work, daemon=True).start()

    # ---------- app signal handlers ----------
    def _on_position(self, app, pos, dur):
        self.player_bar.on_position(pos, dur)

    def _on_playback_state(self, app, state):
        self.player_bar.on_state_changed(state)

    def _on_episode_finished(self, app, episode_id):
        self.player_bar.on_finished()
        self._refresh_rows()

    def _on_playback_error(self, app, message):
        self.toast(f"Playback error: {message}")
        self.player_bar.on_finished()

    def _on_library_changed(self, app):
        self.library.refresh()

    def _refresh_rows(self):
        page = self.current_page()
        if isinstance(page, PodcastPage):
            page.refresh_rows()

    # ---------- player bar state sync ----------
    def update_episode_row_download(self, episode_id, downloading):
        page = self.current_page()
        if isinstance(page, PodcastPage):
            page.update_row_download(episode_id, downloading)

    def update_download_progress(self, episode_id, progress):
        page = self.current_page()
        if isinstance(page, PodcastPage):
            page.update_row_progress(episode_id, progress)

    def refresh_current_page(self):
        page = self.current_page()
        if isinstance(page, PodcastPage):
            page.rebuild()

    def delete_episode_audio(self, episode_id):
        ep = self.app.db.episode(episode_id)
        if ep and ep.downloaded_path:
            try:
                Path(ep.downloaded_path).unlink(missing_ok=True)
            except OSError:
                pass
            self.app.db.clear_download(episode_id)
            self.toast("Download deleted.")