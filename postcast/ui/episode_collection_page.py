import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from .episode_row import EpisodeRow, format_date


class EpisodeCollectionPage(Adw.NavigationPage):
    """Mobile-friendly aggregate episode list for New and Favorites."""

    def __init__(self, window, mode):
        self.mode = mode
        title = "New episodes" if mode == "new" else "Favorites"
        super().__init__(title=title)
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)
        heading = Gtk.Label(label=title)
        heading.add_css_class("title")
        header.set_title_widget(heading)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.set_vexpand(True)
        self._listbox.connect("row-activated", self._on_row_activated)

        self._status = Adw.StatusPage.new()
        self._status.set_icon_name(
            "mail-unread-symbolic" if mode == "new" else "starred-symbolic"
        )
        self._status.set_title("No new episodes" if mode == "new" else "No favorites yet")
        self._status.set_description(
            "Refresh your shows to find new episodes."
            if mode == "new"
            else "Favorite episodes will appear here."
        )
        self._stack = Gtk.Stack(vexpand=True)
        self._stack.add_named(self._status, "empty")
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self._listbox)
        self._stack.add_named(scroll, "list")
        toolbar.set_content(self._stack)
        self.set_child(toolbar)
        self.refresh()

    def refresh(self):
        while (row := self._listbox.get_first_child()) is not None:
            self._listbox.remove(row)
        if self.mode == "new":
            results = self.app.db.recent_episodes()
        else:
            results = self.app.db.search_episodes(favorites_only=True)
        if not results:
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")
        current_date = None
        for episode, podcast in results:
            date = format_date(episode.published)
            if date != current_date:
                current_date = date
                heading = Gtk.Label(label=date)
                heading.set_xalign(0)
                heading.set_margin_start(16)
                heading.set_margin_end(16)
                heading.set_margin_top(14)
                heading.set_margin_bottom(4)
                heading.add_css_class("heading")
                # Let Gtk.ListBox wrap the heading itself. Mixing manually
                # nested ListBoxRow instances with episode rows can cause
                # touch-device list rendering to collapse sibling rows.
                self._listbox.append(heading)
            self._listbox.append(
                EpisodeRow(self.window, episode, podcast, show_podcast=True)
            )

    def _on_row_activated(self, _listbox, row):
        if isinstance(row, EpisodeRow):
            self.window.open_episode(row.episode.id, row.podcast.id)
