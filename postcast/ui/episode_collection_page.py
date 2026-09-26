import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib, Gio, GObject

from .episode_row import EpisodeRow, format_date


class EpisodeListItem(GObject.Object):
    def __init__(self, episode=None, podcast=None, date_label=None):
        super().__init__()
        self.episode = episode
        self.podcast = podcast
        self.date_label = date_label


class EpisodeCollectionPage(Adw.NavigationPage):
    """Mobile-friendly aggregate episode list for New and Favorites."""

    _PAGE_SIZE = 40

    def __init__(self, window, mode):
        self.mode = mode
        title = {
            "new": "New episodes",
            "favorites": "Favorites",
            "downloaded": "Downloads",
        }[mode]
        super().__init__(title=title)
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)
        heading = Gtk.Label(label=title)
        heading.add_css_class("title")
        header.set_title_widget(heading)

        self._listbox = None
        self._model = None
        self._row_bindings = {}
        if mode == "new":
            self._model = Gio.ListStore.new(EpisodeListItem)
            selection = Gtk.NoSelection.new(self._model)
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._setup_list_item)
            factory.connect("bind", self._bind_list_item)
            factory.connect("unbind", self._unbind_list_item)
            self._listview = Gtk.ListView.new(selection, factory)
            self._listview.connect("activate", self._on_list_activate)
            list_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            list_content.append(self._listview)
            self._model_footer = Gtk.Button(label="Load more episodes")
            self._model_footer.set_margin_top(8)
            self._model_footer.set_margin_bottom(16)
            self._model_footer.set_visible(False)
            list_content.append(self._model_footer)
        else:
            self._listview = None
            self._listbox = Gtk.ListBox()
            self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            self._listbox.set_vexpand(True)
            self._listbox.connect("row-activated", self._on_row_activated)
            list_content = self._listbox

        self._status = Adw.StatusPage.new()
        self._status.set_icon_name(
            "mail-unread-symbolic"
            if mode == "new"
            else "folder-download-symbolic"
            if mode == "downloaded"
            else "starred-symbolic"
        )
        self._status.set_title(
            "No new episodes"
            if mode == "new"
            else "No downloads yet"
            if mode == "downloaded"
            else "No favorites yet"
        )
        self._status.set_description(
            "Refresh your shows to find new episodes."
            if mode == "new"
            else "Downloaded episodes are available offline."
            if mode == "downloaded"
            else "Favorite episodes will appear here."
        )
        self._stack = Gtk.Stack(vexpand=True)
        self._stack.add_named(self._status, "empty")
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(list_content)
        self._stack.add_named(scroll, "list")
        toolbar.set_content(self._stack)
        self.set_child(toolbar)
        self._offset = 0
        self._generation = 0
        self._current_date = None
        self._load_more_button = None
        if self._model is not None:
            self._load_more_button = self._model_footer
            self._model_footer.set_visible(False)
        self.refresh()

    def refresh(self):
        self._generation += 1
        generation = self._generation
        if self._model is not None:
            self._model.remove_all()
            self._row_bindings.clear()
        else:
            while (row := self._listbox.get_first_child()) is not None:
                self._listbox.remove(row)
        self._offset = 0
        self._current_date = None
        self._load_more_button = None
        self._load_page(generation)

    def _load_page(self, generation):
        offset = self._offset

        def work():
            if self.mode == "new":
                return self.app.db.recent_episodes(limit=self._PAGE_SIZE, offset=offset)
            if self.mode == "downloaded":
                return self.app.db.search_episodes(
                    downloaded_only=True, limit=self._PAGE_SIZE, offset=offset
                )
            return self.app.db.search_episodes(
                favorites_only=True, limit=self._PAGE_SIZE, offset=offset
            )

        def done(results):
            if generation != self._generation:
                return
            if isinstance(results, Exception):
                self._stack.set_visible_child_name("empty")
                self._status.set_title("Could not load episodes")
                self._status.set_description("Try refreshing again.")
                return
            self._render_page(results, generation)

        self.app.async_tasks.submit(
            ("collection", self.mode),
            work,
            done,
            lambda callback: GLib.idle_add(callback),
        )

    def _render_page(self, results, generation):
        if not results:
            if self._offset == 0:
                self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")
        self._offset += len(results)
        self._append_batch(results, 0, generation)

    def _append_batch(self, results, index, generation):
        if generation != self._generation:
            return GLib.SOURCE_REMOVE
        for episode, podcast in results[index : index + 10]:
            date = format_date(episode.published)
            if date != self._current_date:
                self._current_date = date
                if self._model is not None:
                    self._model.append(EpisodeListItem(date_label=date))
                else:
                    heading = Gtk.Label(label=date)
                    heading.set_xalign(0)
                    heading.set_margin_start(16)
                    heading.set_margin_end(16)
                    heading.set_margin_top(14)
                    heading.set_margin_bottom(4)
                    heading.add_css_class("heading")
                    self._listbox.append(heading)
            if self._model is not None:
                self._model.append(EpisodeListItem(episode, podcast))
            else:
                self._listbox.append(EpisodeRow(self.window, episode, podcast, show_podcast=True))
        index += 10
        if index < len(results):
            GLib.idle_add(self._append_batch, results, index, generation)
            return GLib.SOURCE_REMOVE
        if len(results) == self._PAGE_SIZE:
            if self._model is None:
                self._load_more_button = Gtk.Button(label="Load more episodes")
                self._load_more_button.set_margin_top(8)
                self._load_more_button.set_margin_bottom(16)
                self._load_more_button.connect("clicked", lambda *_: self._load_next_page(generation))
                self._listbox.append(self._load_more_button)
            else:
                self._load_more_button.set_visible(True)
                self._load_more_button.connect("clicked", lambda *_: self._load_next_page(generation))
        return GLib.SOURCE_REMOVE

    def _load_next_page(self, generation):
        if self._load_more_button is not None:
            if self._listbox is not None:
                self._listbox.remove(self._load_more_button)
                self._load_more_button = None
            else:
                self._load_more_button.set_visible(False)
        self._load_page(generation)

    def _on_row_activated(self, _listbox, row):
        if isinstance(row, EpisodeRow):
            self.window.open_episode(row.episode.id, row.podcast.id)

    def _setup_list_item(self, _factory, list_item):
        list_item.set_child(Gtk.Box(orientation=Gtk.Orientation.VERTICAL))

    def _bind_list_item(self, _factory, list_item):
        container = list_item.get_child()
        item = list_item.get_item()
        while (child := container.get_first_child()) is not None:
            container.remove(child)
        if item.date_label is not None:
            label = Gtk.Label(label=item.date_label)
            label.set_xalign(0)
            label.set_margin_start(16)
            label.set_margin_top(14)
            label.set_margin_bottom(4)
            label.add_css_class("heading")
            container.append(label)
            return
        row = EpisodeRow(self.window, item.episode, item.podcast, show_podcast=True)
        self._row_bindings[item.episode.id] = row
        container.append(row)

    def _unbind_list_item(self, _factory, list_item):
        container = list_item.get_child()
        item = list_item.get_item()
        if item is not None and item.episode is not None:
            self._row_bindings.pop(item.episode.id, None)
        while (child := container.get_first_child()) is not None:
            container.remove(child)

    def _on_list_activate(self, _listview, position):
        item = self._model.get_item(position)
        if item is not None and item.episode is not None:
            self.window.open_episode(item.episode.id, item.podcast.id)

    def update_row_download(self, episode_id, downloading, progress=None):
        if self._model is not None:
            row = self._row_bindings.get(episode_id)
            if row is not None:
                row.update_download_state(downloading, progress)
            return
        child = self._listbox.get_first_child()
        while child is not None:
            if isinstance(child, EpisodeRow) and child.episode.id == episode_id:
                child.update_download_state(downloading, progress)
                return
            child = child.get_next_sibling()
