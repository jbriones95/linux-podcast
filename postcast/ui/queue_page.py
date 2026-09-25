import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

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
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self._listbox)
        stack.add_named(scroll, "list")
        self._stack = stack
        toolbar.set_content(stack)
        self.set_child(toolbar)
        self.refresh()

    def refresh(self):
        while (row := self._listbox.get_first_child()) is not None:
            self._listbox.remove(row)
        items = self.app.db.queue_items()
        if not items:
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")
        for episode, podcast in items:
            self._listbox.append(EpisodeRow(self.window, episode, podcast))

    def _on_row_activated(self, _listbox, row):
        if isinstance(row, EpisodeRow):
            self.window.open_episode(row.episode.id, row.podcast.id)

    def _clear(self, *_args):
        self.app.db.clear_queue()
        self.app.playback._load_queue()
        self.refresh()
        self.window.toast("Queue cleared.")
