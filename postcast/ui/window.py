import threading
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gtk, GLib, Gio

from ..feed import FeedError, fetch_feed, normalize_feed_url
from ..interop import import_opml
from ..sync import export_library, import_library
from ..search import search_podcasts
from ..ui.library_page import LibraryPage
from ..ui.podcast_page import PodcastPage
from ..ui.search_page import SearchPage
from ..ui.settings_page import SettingsPage
from ..ui.episode_page import EpisodePage
from ..ui.queue_page import QueuePage
from ..ui.statistics_page import StatisticsPage
from ..ui.about_page import AboutPage
from ..ui.episode_collection_page import EpisodeCollectionPage


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="Postcast")
        self.app = application
        self._toast_overlay = Adw.ToastOverlay.new()
        self.set_content(self._toast_overlay)

        shell = Gtk.Overlay()
        self._toast_overlay.set_child(shell)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        shell.set_child(root)

        self.library = LibraryPage(self)
        self.new_page = EpisodeCollectionPage(self, "new")
        self.favorites_page = EpisodeCollectionPage(self, "favorites")
        self.downloaded_page = EpisodeCollectionPage(self, "downloaded")

        self._sections = {}
        self._section_stack = Gtk.Stack(vexpand=True)
        for name, page in (
            ("shows", self.library),
            ("new", self.new_page),
            ("favorites", self.favorites_page),
            ("downloaded", self.downloaded_page),
        ):
            nav = Adw.NavigationView()
            nav.add(page)
            self._sections[name] = (nav, page)
            self._section_stack.add_named(nav, name)
        self.nav = self._sections["shows"][0]
        root.append(self._section_stack)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        root.append(separator)
        self._section_buttons = {}
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bottom.set_margin_start(6)
        bottom.set_margin_end(6)
        bottom.set_margin_top(4)
        bottom.set_margin_bottom(4)
        previous = None
        for name, label, icon in (
            ("shows", "Shows", "view-list-symbolic"),
            ("new", "New", "mail-unread-symbolic"),
            ("favorites", "Favorites", "starred-symbolic"),
            ("downloaded", "Downloads", "folder-download-symbolic"),
        ):
            button = Gtk.ToggleButton()
            button.set_size_request(-1, 60)
            button.set_hexpand(True)
            button.set_tooltip_text(label)
            button.add_css_class("flat")
            button.set_child(self._section_button_content(icon, label))
            if previous is not None:
                button.set_group(previous)
            button.connect("toggled", self._on_section_toggled, name)
            self._section_buttons[name] = button
            bottom.append(button)
            previous = button
        self._section_buttons["shows"].set_active(True)
        root.append(bottom)

        from .player_bar import PlayerBar, PlayerSheet
        self.player_bar = PlayerBar(self)
        root.append(self.player_bar)
        self.player_sheet = PlayerSheet(self)
        shell.add_overlay(self.player_sheet)

        self.app.connect("position", self._on_position)
        self.app.connect("playback-state", self._on_playback_state)
        self.app.connect("episode-finished", self._on_episode_finished)
        self.app.connect("playback-error", self._on_playback_error)
        self.app.connect("library-changed", self._on_library_changed)
        self.app.connect("queue-changed", self._on_queue_changed)
        self.app.connect("now-playing", self._on_now_playing)
        current_episode = self.app.playback.current_episode()
        if current_episode is not None:
            self.player_bar.set_episode(current_episode, self.app.playback.podcast)

        # OnePlus 6T portrait is 1080x2340 (2.17:1); phosh presents it at
        # roughly 412x915 logical pixels. Keep the desktop preview portrait
        # sized while allowing the compositor to maximize it on-device.
        self.set_default_size(412, 915)
        self.set_size_request(360, 640)
        self.set_resizable(True)
        self.connect("notify::width", self._on_width_changed)
        self._on_width_changed()

        self._install_shortcuts()

    # ---------- public helpers ----------
    def toast(self, message):
        self._toast_overlay.add_toast(Adw.Toast.new(message))

    def finish_initial_focus_setup(self):
        """Set a non-editable initial focus after GTK has mapped the window."""
        self.library.reset_search_focus()
        target = self.library.initial_focus_target
        self.set_focus(target)
        target.grab_focus()
        return GLib.SOURCE_REMOVE

    def _on_now_playing(self, app, podcast, episode):
        self.player_bar.set_episode(episode, podcast)
        self._refresh_rows()

    def play_episode(self, episode, podcast):
        self.app.playback.play_episode(podcast, episode)
        self._refresh_rows()

    def is_current(self, episode_id):
        return (
            self.app.playback.current_episode()
            and self.app.playback.current_episode().id == episode_id
        )

    def play_next(self):
        self.app.playback.play_next()

    def play_previous(self):
        self.app.playback.play_previous()

    def move_queue_item(self, episode_id, target_position):
        self.app.move_queue_item(episode_id, target_position)

    def current_page(self):
        return self.nav.get_visible_page()

    @staticmethod
    def _section_button_content(icon_name, label):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.set_halign(Gtk.Align.CENTER)
        image = Gtk.Image(icon_name=icon_name)
        text = Gtk.Label(label=label)
        text.add_css_class("caption")
        content.append(image)
        content.append(text)
        return content

    def _on_section_toggled(self, button, name):
        if button.get_active() and not getattr(self, "_switching_section", False):
            self.switch_section(name)

    def switch_section(self, name):
        nav, page = self._sections[name]
        self._switching_section = True
        for section, button in self._section_buttons.items():
            button.set_active(section == name)
        self._switching_section = False
        nav.pop_to_page(page)
        self.nav = nav
        self._section_stack.set_visible_child_name(name)
        if name == "shows":
            self.library.reset_search_focus()
        page.refresh()

    # ---------- navigation ----------
    def open_podcast(self, podcast_id):
        page = PodcastPage(self, podcast_id)
        self.nav.push(page)

    def open_episode(self, episode_id, podcast_id=None):
        page = EpisodePage(self, episode_id, podcast_id)
        self.nav.push(page)

    def open_now_playing(self):
        if self.app.playback.current_episode() is None:
            self.toast("Nothing is playing.")
            return
        self._player_focus = self.get_focus()
        self.player_sheet.open()
        self.player_sheet.close_button.grab_focus()

    def restore_player_focus(self):
        focus = getattr(self, "_player_focus", None)
        self._player_focus = None
        if focus is not None and focus.get_root() is self:
            focus.grab_focus()
        else:
            self.player_bar._btn_play.grab_focus()

    def _on_width_changed(self, *_args):
        self.player_bar.update_layout(self.get_width())

    def _install_shortcuts(self):
        group = Gio.SimpleActionGroup()
        actions = {
            "player-play-pause": (self._shortcut_play_pause, []),
            "player-skip-backward": (self._shortcut_skip_backward, []),
            "player-skip-forward": (self._shortcut_skip_forward, []),
            "close-player": (self._shortcut_close_player, []),
            "show-shortcuts": (lambda *_: self.open_shortcuts(), ["F1"]),
        }
        for name, (callback, accelerators) in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            group.add_action(action)
            self.app.set_accels_for_action(f"win.{name}", accelerators)
        self.insert_action_group("win", group)
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    def _on_key_pressed(self, _controller, keyval, _keycode, _state):
        if not self._shortcut_allowed():
            return False
        if keyval == Gdk.KEY_space:
            self._shortcut_play_pause()
            return True
        if keyval == Gdk.KEY_Left:
            self._shortcut_skip_backward()
            return True
        if keyval == Gdk.KEY_Right:
            self._shortcut_skip_forward()
            return True
        if keyval == Gdk.KEY_BackSpace and self.player_sheet.get_visible():
            self._shortcut_close_player()
            return True
        return False

    def _shortcut_allowed(self):
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Entry, Gtk.TextView, Gtk.DropDown)):
            return False
        return True

    def _shortcut_play_pause(self, *_args):
        if self._shortcut_allowed():
            self.app.playback.toggle()

    def _shortcut_skip_backward(self, *_args):
        if self._shortcut_allowed():
            self.app.playback.skip(-15)

    def _shortcut_skip_forward(self, *_args):
        if self._shortcut_allowed():
            self.app.playback.skip(30)

    def _shortcut_close_player(self, *_args):
        if self._shortcut_allowed() and self.player_sheet.get_visible():
            self.player_sheet.close()

    def open_shortcuts(self):
        shortcuts = Gtk.ShortcutsWindow(transient_for=self, modal=True)
        section = Gtk.ShortcutsSection(title="Playback")
        group = Gtk.ShortcutsGroup(title="Controls")
        for title, accelerator in (
            ("Play or pause", "Space"),
            ("Rewind 15 seconds", "Left"),
            ("Skip forward 30 seconds", "Right"),
            ("Close player", "BackSpace"),
        ):
            group.append(Gtk.ShortcutsShortcut(title=title, accelerator=accelerator))
        section.append(group)
        shortcuts.append(section)
        shortcuts.present()

    def open_queue(self):
        self.nav.push(QueuePage(self))

    def open_statistics(self):
        self.nav.push(StatisticsPage(self))

    def open_about(self):
        self.nav.push(AboutPage(self))

    def add_dialog(self):
        self.open_add_podcast()

    def open_search(self):
        self.open_add_podcast()

    def open_add_podcast(self):
        page = SearchPage(self)
        self.nav.push(page)

    def open_settings(self):
        page = SettingsPage(self)
        self.nav.push(page)

    # ---------- feed subscribe helper (main-thread safe) ----------
    def _subscribe(self, feed_url, on_done=None, fallback_image_url=""):
        try:
            feed_url = normalize_feed_url(feed_url)
        except ValueError as exc:
            self._subscribe_done(
                None, {"feed_url": feed_url, "error": str(exc)}, on_done
            )
            return

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
            except Exception as exc:
                GLib.idle_add(
                    self._subscribe_done,
                    None,
                    {"feed_url": feed_url, "error": f"Could not read feed: {exc}"},
                    on_done,
                )
                return
            if not podcast.get("image_url") and fallback_image_url:
                podcast["image_url"] = fallback_image_url
            podcast_id = self.app.db.upsert_podcast(podcast)
            self.app.db.sync_episodes(podcast_id, episodes)
            GLib.idle_add(self._subscribe_done, podcast_id, None, on_done)

        threading.Thread(target=work, daemon=True).start()

    def _subscribe_done(self, podcast_id, err, on_done=None):
        if on_done:
            on_done(podcast_id, err)
        self.app.refresh_library()
        if podcast_id and err is None:
            self.toast("Subscribed!")
            self.open_podcast(podcast_id)
        elif err is not None:
            self.toast(f"Could not add feed: {err.get('error','')}")

    # ---------- feed refresh ----------
    def refresh_feed(self, podcast_id):
        if self.app.refresh_podcast(podcast_id):
            self.toast("Refreshing feed…")
        else:
            self.toast("A refresh is already in progress.")

    def _feed_refreshed(self, podcast_id):
        self.app.refresh_library()
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

    def import_opml(self, path):
        try:
            urls = import_opml(path)
        except Exception as exc:
            self.toast(f"Could not import OPML: {exc}")
            return

        def work():
            imported = 0
            for url in urls:
                try:
                    url = normalize_feed_url(url)
                    podcast, episodes = fetch_feed(url)
                    podcast_id = self.app.db.upsert_podcast(podcast)
                    self.app.db.sync_episodes(podcast_id, episodes)
                    imported += 1
                except Exception:
                    continue
            GLib.idle_add(self._opml_imported, imported)

        threading.Thread(target=work, daemon=True, name="postcast-opml-import").start()

    def export_library(self, path):
        try:
            export_library(self.app.db, path)
            self.toast(f"Library exported to {path}.")
        except Exception as exc:
            self.toast(f"Could not export library: {exc}")

    def import_library(self, path):
        try:
            count = import_library(self.app.db, path)
        except Exception as exc:
            self.toast(f"Could not import library: {exc}")
            return
        self.app.playback._load_queue()
        self.app.refresh_library()
        self.toast(f"Merged {count} episode{'s' if count != 1 else ''}.")

    def _opml_imported(self, count):
        self.app.refresh_library()
        self.toast(f"Imported {count} podcast{'s' if count != 1 else ''}.")

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
        self.refresh_current_page()

    def _on_queue_changed(self, app):
        if isinstance(self.current_page(), QueuePage):
            self.current_page().refresh()

    def _refresh_rows(self):
        page = self.current_page()
        if isinstance(page, PodcastPage):
            page.refresh_rows()

    # ---------- player bar state sync ----------
    def update_episode_row_download(self, episode_id, downloading):
        page = self.current_page()
        if isinstance(page, (PodcastPage, EpisodeCollectionPage, QueuePage)):
            page.update_row_download(episode_id, downloading)

    def update_download_progress(self, episode_id, progress):
        page = self.current_page()
        if isinstance(page, PodcastPage):
            page.update_row_progress(episode_id, progress)
        elif isinstance(page, (EpisodeCollectionPage, QueuePage)):
            page.update_row_download(episode_id, True, progress)

    def refresh_current_page(self):
        page = self.current_page()
        if isinstance(page, LibraryPage):
            page.refresh()
        elif isinstance(page, PodcastPage):
            page.rebuild()
        elif isinstance(page, EpisodePage):
            page.refresh()
        elif isinstance(page, QueuePage):
            page.refresh()
        elif isinstance(page, EpisodeCollectionPage):
            page.refresh()

    def delete_episode_audio(self, episode_id):
        ep = self.app.db.episode(episode_id)
        if ep and ep.downloaded_path:
            try:
                Path(ep.downloaded_path).unlink(missing_ok=True)
            except OSError:
                pass
            self.app.db.clear_download(episode_id)
            self.toast("Download deleted.")
            self.refresh_current_page()
