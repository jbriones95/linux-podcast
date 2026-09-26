import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib, Pango

from .episode_row import EpisodeRow


class LibraryPage(Adw.NavigationPage):
    _PAGE_SIZE = 40

    def __init__(self, window):
        super().__init__(title="Postcast")
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        title = Gtk.Label(label="Library")
        title.add_css_class("title")
        header.set_title_widget(title)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add podcast by URL")
        add_btn.connect("clicked", lambda *_: window.add_dialog())
        header.pack_end(add_btn)

        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", lambda *_: window.open_settings())
        header.pack_end(settings_btn)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search library")
        self._search_entry.set_hexpand(True)
        self._search_refresh_source = None
        self._search_generation = 0
        self._search_offset = 0
        self._load_more_button = None
        self._search_entry.connect("search-changed", self._on_search_changed)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tools.set_margin_start(12)
        tools.set_margin_end(12)
        tools.set_margin_top(8)
        tools.set_margin_bottom(4)
        tools.append(self._search_entry)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_margin_start(12)
        actions.set_margin_end(12)
        actions.set_margin_bottom(8)
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh all feeds")
        refresh_btn.set_size_request(44, 44)
        refresh_btn.connect("clicked", lambda *_: self._refresh_all())
        actions.append(refresh_btn)
        queue_btn = Gtk.Button(icon_name="view-list-symbolic")
        queue_btn.set_tooltip_text("Playback queue")
        queue_btn.set_size_request(44, 44)
        queue_btn.connect("clicked", lambda *_: window.open_queue())
        actions.append(queue_btn)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)
        self._listbox.set_vexpand(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self._listbox)
        scroll.set_vexpand(True)

        self._status = Adw.StatusPage.new()
        self._status.set_icon_name("audio-x-generic-symbolic")
        self._status.set_title("No podcasts yet")
        self._status.set_description(
            "Search for podcasts or add one by its RSS feed URL."
        )
        find_btn = Gtk.Button(label="Find podcasts")
        find_btn.add_css_class("suggested-action")
        find_btn.connect("clicked", lambda *_: window.open_search())
        self._status.set_child(find_btn)

        stack = Gtk.Stack(vexpand=True)
        stack.add_named(self._status, "empty")
        stack.add_named(scroll, "list")
        self._stack = stack

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.set_focusable(True)
        self.initial_focus_target = body
        body.append(tools)
        body.append(actions)
        body.append(stack)
        toolbar.set_content(body)
        self.set_child(toolbar)
        GLib.idle_add(self.refresh)

    def _on_search_pressed(self, _gesture, _n_press, _x, _y):
        self._search_entry.set_focusable(True)
        self._search_entry.grab_focus()

    def reset_search_focus(self):
        self.initial_focus_target.grab_focus()


    def refresh(self):
        self._search_generation += 1
        generation = self._search_generation
        while (row := self._listbox.get_first_child()) is not None:
            self._listbox.remove(row)
        self._load_more_button = None

        query = self._search_entry.get_text().strip()
        if query:
            self._search_offset = 0
            self._load_search_page(query, generation, "all")
            return

        podcasts = self.app.db.podcasts()

        if not podcasts:
            self._status.set_title("No podcasts yet")
            self._status.set_description(
                "Search for podcasts or add one by its RSS feed URL."
            )
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")

        for pod in podcasts:
            row = Gtk.ListBoxRow()
            row.podcast = pod
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(8)
            box.set_margin_end(8)

            art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=48)
            art.set_size_request(48, 48)
            self.app.artwork.load(pod.image_url, 96, self._art_cb(art))
            box.append(art)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = Gtk.Label(label=pod.title)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.set_xalign(0)
            title.add_css_class("title-2")
            sub = Gtk.Label(label=pod.author or f"{pod.episode_count} episodes")
            sub.set_ellipsize(Pango.EllipsizeMode.END)
            sub.set_xalign(0)
            sub.add_css_class("dim-label")
            text.append(title)
            text.append(sub)
            text.set_hexpand(True)
            box.append(text)

            row.set_child(box)
            self._listbox.append(row)

    def _load_search_page(self, query, generation, filter_mode):
        favorites = filter_mode == "favorites"
        unplayed = filter_mode == "unplayed"
        downloaded = filter_mode == "downloaded"
        offset = self._search_offset

        def work():
            return self.app.db.search_episodes(
                query,
                favorites_only=favorites,
                unplayed_only=unplayed,
                downloaded_only=downloaded,
                limit=self._PAGE_SIZE,
                offset=offset,
            )

        def done(results):
            if generation != self._search_generation:
                return
            if isinstance(results, Exception):
                self._status.set_title("Search failed")
                self._status.set_description("Try again or check your connection.")
                self._stack.set_visible_child_name("empty")
                return
            self._render_search_results(results, query, generation, filter_mode)

        self.app.async_tasks.submit(
            "library-search", work, done, lambda callback: GLib.idle_add(callback)
        )

    def _render_search_results(self, results, query, generation, filter_mode):
        if not results and self._search_offset == 0:
            self._status.set_title("No episodes found")
            self._status.set_description("Try a different search or filter.")
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")
        self._search_offset += len(results)
        self._append_search_batch(results, 0, query, generation, filter_mode)

    def _append_search_batch(self, results, index, query, generation, filter_mode):
        if generation != self._search_generation:
            return GLib.SOURCE_REMOVE
        for episode, podcast in results[index : index + 10]:
            self._listbox.append(EpisodeRow(self.window, episode, podcast))
        index += 10
        if index < len(results):
            GLib.idle_add(
                self._append_search_batch, results, index, query, generation, filter_mode
            )
            return GLib.SOURCE_REMOVE
        if len(results) == self._PAGE_SIZE:
            self._load_more_button = Gtk.Button(label="Load more episodes")
            self._load_more_button.set_margin_top(8)
            self._load_more_button.set_margin_bottom(16)
            self._load_more_button.connect(
                "clicked", lambda *_: self._load_next_search_page(query, generation, filter_mode)
            )
            self._listbox.append(self._load_more_button)
        return GLib.SOURCE_REMOVE

    def _load_next_search_page(self, query, generation, filter_mode):
        if self._load_more_button is not None:
            self._listbox.remove(self._load_more_button)
            self._load_more_button = None
        self._load_search_page(query, generation, filter_mode)

    def _on_search_changed(self, _entry):
        if self._search_refresh_source is not None:
            GLib.source_remove(self._search_refresh_source)
        self._search_refresh_source = GLib.timeout_add(250, self._refresh_search)

    def _refresh_search(self):
        self._search_refresh_source = None
        self.refresh()
        return GLib.SOURCE_REMOVE

    def _art_cb(self, image):
        def cb(texture):
            if texture is not None:
                image.set_from_paintable(texture)
        return cb

    def _on_row_activated(self, listbox, row):
        if isinstance(row, EpisodeRow):
            self.window.open_episode(row.episode.id, row.podcast.id)
        else:
            self.window.open_podcast(row.podcast.id)

    def _refresh_all(self):
        if not self.app.db.podcasts():
            self.window.toast("No feeds to refresh yet.")
            return
        if self.app.start_refresh_feeds():
            self.window.toast("Refreshing feeds…")
        else:
            self.window.toast("A refresh is already in progress.")
