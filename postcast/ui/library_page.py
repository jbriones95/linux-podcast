import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib, Pango

from ..feed import fetch_feed
from .episode_row import EpisodeRow


class LibraryPage(Adw.NavigationPage):
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
        self._search_entry.connect("search-changed", lambda *_: self.refresh())

        self._favorite_filter = Gtk.ToggleButton()
        self._favorite_filter.set_label("Favorites")
        self._favorite_filter.set_tooltip_text("Show favorites")
        self._favorite_filter.connect("toggled", lambda *_: self.refresh())

        self._unplayed_filter = Gtk.ToggleButton()
        self._unplayed_filter.set_label("Unplayed")
        self._unplayed_filter.set_tooltip_text("Show unplayed episodes")
        self._unplayed_filter.connect("toggled", lambda *_: self.refresh())

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tools.set_margin_start(12)
        tools.set_margin_end(12)
        tools.set_margin_top(8)
        tools.set_margin_bottom(4)
        tools.append(self._search_entry)

        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filters.set_margin_start(12)
        filters.set_margin_end(12)
        filters.set_margin_bottom(8)
        filters.append(self._favorite_filter)
        filters.append(self._unplayed_filter)
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh all feeds")
        refresh_btn.set_size_request(44, 44)
        refresh_btn.connect("clicked", lambda *_: self._refresh_all())
        filters.append(refresh_btn)
        queue_btn = Gtk.Button(icon_name="view-list-symbolic")
        queue_btn.set_tooltip_text("Playback queue")
        queue_btn.set_size_request(44, 44)
        queue_btn.connect("clicked", lambda *_: window.open_queue())
        filters.append(queue_btn)

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
        body.append(tools)
        body.append(filters)
        body.append(stack)
        toolbar.set_content(body)
        self.set_child(toolbar)
        GLib.idle_add(self.refresh)

    def refresh(self):
        while (row := self._listbox.get_first_child()) is not None:
            self._listbox.remove(row)

        query = self._search_entry.get_text().strip()
        favorites_only = self._favorite_filter.get_active()
        unplayed_only = self._unplayed_filter.get_active()
        if query or favorites_only or unplayed_only:
            results = self.app.db.search_episodes(
                query, favorites_only=favorites_only, unplayed_only=unplayed_only
            )
            if not results:
                self._status.set_title("No matching episodes")
                self._status.set_description("Try a different search or filter.")
                self._stack.set_visible_child_name("empty")
                return
            self._stack.set_visible_child_name("list")
            for episode, podcast in results:
                self._listbox.append(EpisodeRow(self.window, episode, podcast))
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
        podcasts = self.app.db.podcasts()
        if not podcasts:
            self.window.toast("No feeds to refresh yet.")
            return

        def work():
            for pod in podcasts:
                try:
                    data, episodes = fetch_feed(pod.feed_url)
                    self.app.db.upsert_podcast(data)
                    self.app.db.sync_episodes(pod.id, episodes)
                except Exception:
                    continue
            GLib.idle_add(self._all_done)

        threading.Thread(target=work, daemon=True).start()

    def _all_done(self):
        self.app.refresh_library()
        self.refresh()
        self.window.toast("All feeds refreshed.")
