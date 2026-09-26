import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib

from .episode_row import EpisodeRow


class QueuePage(Adw.NavigationPage):
    """Persistent cross-podcast playback queue."""

    def __init__(self, window):
        super().__init__(title="Queue")
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)
        clear = Gtk.Button(label="Clear")
        clear.add_css_class("destructive-action")
        clear.connect("clicked", self._clear)
        header.pack_end(clear)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)
        self._status = Adw.StatusPage.new()
        self._status.set_icon_name("view-list-symbolic")
        self._status.set_title("Queue is empty")
        self._status.set_description("Add episodes from a podcast or episode page.")

        stack = Gtk.Stack(vexpand=True)
        stack.add_named(self._status, "empty")
        self._scroll = Gtk.ScrolledWindow(vexpand=True)
        self._scroll.set_child(self._listbox)
        stack.add_named(self._scroll, "list")
        self._stack = stack
        toolbar.set_content(stack)
        self.set_child(toolbar)
        self.refresh()

    def refresh(self):
        focused_id = self._focused_episode_id()
        adjustment = self._scroll.get_vadjustment()
        scroll_value = adjustment.get_value()
        while (row := self._listbox.get_first_child()) is not None:
            self._listbox.remove(row)
        items = self.app.db.queue_items()
        if not items:
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")
        for position, (episode, podcast) in enumerate(items):
            self._listbox.append(EpisodeRow(
                self.window,
                episode,
                podcast,
                queue_position=position,
                queue_count=len(items),
            ))
        adjustment.set_value(scroll_value)
        if focused_id is not None:
            GLib.idle_add(self._restore_focus, focused_id)

    def _focused_episode_id(self):
        focus = self.window.get_focus()
        while focus is not None:
            if isinstance(focus, EpisodeRow):
                return focus.episode.id
            focus = focus.get_parent()
        return None

    def _restore_focus(self, episode_id):
        child = self._listbox.get_first_child()
        while child is not None:
            if isinstance(child, EpisodeRow) and child.episode.id == episode_id:
                child.play_btn.grab_focus()
                return GLib.SOURCE_REMOVE
            child = child.get_next_sibling()
        return GLib.SOURCE_REMOVE

    def _on_row_activated(self, _listbox, row):
        if isinstance(row, EpisodeRow):
            self.window.open_episode(row.episode.id, row.podcast.id)

    def _clear(self, *_args):
        self.app.db.clear_queue()
        self.app.playback.reload_queue()
        self.app.queue_changed()
        self.window.toast("Queue cleared.")

    def update_row_download(self, episode_id, downloading, progress=None):
        child = self._listbox.get_first_child()
        while child is not None:
            if isinstance(child, EpisodeRow) and child.episode.id == episode_id:
                child.update_download_state(downloading, progress)
                return
            child = child.get_next_sibling()
