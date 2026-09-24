import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib, Gio, GObject, Pango


class PodcastRow(GObject.Object):
    __gproperties__ = {
        "podcast_id": (int, "Podcast ID", "", 0, GObject.G_MAXINT, 0, GObject.ParamFlags.READWRITE),
        "title": (str, "Title", "", "", GObject.ParamFlags.READWRITE),
        "author": (str, "Author", "", "", GObject.ParamFlags.READWRITE),
        "episode_count": (int, "Episode count", "", 0, GObject.G_MAXINT, 0, GObject.ParamFlags.READWRITE),
        "image_url": (str, "Image URL", "", "", GObject.ParamFlags.READWRITE),
    }

    def __init__(self, podcast=None):
        super().__init__()
        if podcast:
            self.props.podcast_id = podcast.id
            self.props.title = podcast.title
            self.props.author = podcast.author or f"{podcast.episode_count} episodes"
            self.props.episode_count = podcast.episode_count
            self.props.image_url = podcast.image_url or ""


class LibraryPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title="Postcast")
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        search_btn = Gtk.Button(icon_name="system-search-symbolic")
        search_btn.set_tooltip_text("Search for podcasts")
        search_btn.connect("clicked", lambda *_: window.open_search())
        header.pack_end(search_btn)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh all feeds")
        refresh_btn.connect("clicked", lambda *_: self._refresh_all())
        header.pack_end(refresh_btn)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("Add podcast by URL")
        add_btn.connect("clicked", lambda *_: window.add_dialog())
        header.pack_end(add_btn)

        settings_btn = Gtk.Button(icon_name="open-menu-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", lambda *_: window.open_settings())
        header.pack_start(settings_btn)

        self._model = Gio.ListStore.new(PodcastRow)
        self._factory = Gtk.SignalListItemFactory()
        self._factory.connect("setup", self._on_factory_setup)
        self._factory.connect("bind", self._on_factory_bind)

        self._column_view = Gtk.ColumnView.new(self._model, self._factory)
        self._column_view.set_show_row_separators(True)
        self._column_view.set_hexpand(True)
        self._column_view.set_vexpand(True)
        self._column_view.set_single_click_activate(True)
        self._column_view.connect("activate", self._on_activate)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self._column_view)
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

        toolbar.set_content(stack)
        self.set_child(toolbar)
        GLib.idle_add(self.refresh)

    def _on_factory_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=48)
        art.set_size_request(48, 48)
        box.append(art)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_xalign(0)
        title.add_css_class("title-2")
        sub = Gtk.Label(label="")
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        sub.set_xalign(0)
        sub.add_css_class("dim-label")
        text.append(title)
        text.append(sub)
        text.set_hexpand(True)
        box.append(text)

        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        row = list_item.get_item()
        if row is None:
            return
        box = list_item.get_child()
        art = box.get_first_child()
        text_box = box.get_last_child()
        title = text_box.get_first_child()
        sub = text_box.get_last_child()

        title.set_label(row.props.title)
        sub.set_label(row.props.author)

        self.app.artwork.load(row.props.image_url, 96, self._art_cb(art))

    def _art_cb(self, image):
        def cb(texture):
            if texture is not None:
                image.set_from_paintable(texture)
        return cb

    def _on_activate(self, column_view, position):
        item = self._model.get_item(position)
        if item:
            self.window.open_podcast(item.props.podcast_id)

    def _on_row_activated(self, listbox, row):
        self.window.open_podcast(row.podcast.id)

    def refresh(self):
        podcasts = self.app.db.podcasts()
        self._model.splice(0, self._model.get_n_items())

        if not podcasts:
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")

        for pod in podcasts:
            row = PodcastRow(pod)
            self._model.append(row)

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