import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, Pango

from ..feed import normalize_feed_url


class SearchPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title="Add podcast")
        self.window = window
        self.app = window.app
        self._search_generation = 0

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        self.entry = Gtk.SearchEntry(placeholder_text="Search podcasts…")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self._on_search)
        self.entry.set_search_delay(600)
        self.entry.connect("search-changed", self._on_search)

        search_title = Gtk.Label(label="Find a podcast")
        search_title.set_xalign(0)
        search_title.add_css_class("heading")

        rss_title = Gtk.Label(label="Add by RSS feed")
        rss_title.set_xalign(0)
        rss_title.add_css_class("heading")
        self.rss_entry = Gtk.Entry(placeholder_text="https://example.com/feed.xml")
        self.rss_entry.set_hexpand(True)
        self.rss_button = Gtk.Button(label="Add")
        self.rss_button.add_css_class("suggested-action")
        self.rss_button.set_size_request(72, 48)
        self.rss_button.connect("clicked", self._on_rss_add)
        self.rss_entry.connect("activate", self._on_rss_add)
        rss_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rss_row.append(self.rss_entry)
        rss_row.append(self.rss_button)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        controls.set_margin_start(16)
        controls.set_margin_end(16)
        controls.set_margin_top(16)
        controls.set_margin_bottom(8)
        controls.append(search_title)
        controls.append(self.entry)
        controls.append(rss_title)
        controls.append(rss_row)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.set_vexpand(True)

        self._status = Adw.StatusPage.new()
        self._status.set_icon_name("system-search-symbolic")
        self._status.set_title("Search")
        self._status.set_description("Find new podcasts to subscribe to.")

        stack = Gtk.Stack(vexpand=True)
        stack.add_named(self._status, "empty")
        stack.add_named(self._listbox, "results")
        self._stack = stack

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(controls)
        body.append(stack)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(body)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    def _on_search_pressed(self, _gesture, _n_press, _x, _y):
        self.entry.set_focusable(True)
        self.entry.grab_focus()

    def _on_rss_pressed(self, _gesture, _n_press, _x, _y):
        self.rss_entry.set_focusable(True)
        self.rss_entry.grab_focus()

    def _on_rss_add(self, *_args):
        try:
            url = normalize_feed_url(self.rss_entry.get_text())
        except ValueError as exc:
            self.window.toast(str(exc))
            return
        self.rss_button.set_sensitive(False)
        self.rss_button.set_label("Adding…")

        def done(_podcast_id, err):
            if err:
                self.rss_button.set_sensitive(True)
                self.rss_button.set_label("Add")
                self.window.toast(f"Could not add feed: {err.get('error', '')}")
                return
            self.rss_entry.set_text("")
            self.rss_button.set_label("Added")
            self.window.toast("Podcast added.")

        self.window._subscribe(url, done)

    # ---------- actions ----------
    def _on_search(self, *args):
        term = self.entry.get_text().strip()
        self._search_generation += 1
        generation = self._search_generation
        if not term:
            self._stack.set_visible_child_name("empty")
            return

        self._status.set_icon_name("system-search-symbolic")
        self._status.set_title("Searching…")
        self._status.set_description("Looking for podcasts.")
        self._stack.set_visible_child_name("empty")

        def on_results(results):
            if generation != self._search_generation:
                return
            if isinstance(results, Exception):
                self._status.set_title("Search failed")
                self._status.set_description("Check your connection and try again.")
                self._stack.set_visible_child_name("empty")
                return
            self._render(results)

        self.window.search(term, on_results)

    def _render(self, results):
        while (child := self._listbox.get_first_child()) is not None:
            self._listbox.remove(child)

        if not results:
            self._status.set_title("No results")
            self._status.set_description("Try a different search term.")
            self._stack.set_visible_child_name("empty")
            return

        self._stack.set_visible_child_name("results")
        for item in results:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(8)
            box.set_margin_end(8)

            art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=48)
            art.set_size_request(48, 48)
            self.app.artwork.load(item["image_url"], 96, self._art_cb(art))
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            top.append(art)

            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = Gtk.Label(label=item["title"])
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.set_xalign(0)
            title.add_css_class("title-2")

            sub = Gtk.Label(
                label=f"{item['author']} · {item['track_count']} episodes"
            )
            sub.set_ellipsize(Pango.EllipsizeMode.END)
            sub.set_xalign(0)
            sub.add_css_class("dim-label")

            text.append(title)
            text.append(sub)
            text.set_hexpand(True)
            top.append(text)
            box.append(top)

            sub_btn = Gtk.Button(label="Subscribe")
            sub_btn.set_tooltip_text("Subscribe to this podcast")
            sub_btn.add_css_class("suggested-action")
            sub_btn.connect(
                "clicked",
                 lambda *_, row=row, url=item["feed_url"], button=sub_btn, image=item.get("image_url", ""): self._subscribe(
                     row, url, button, image
                ),
            )
            sub_btn.set_size_request(-1, 44)
            sub_btn.set_halign(Gtk.Align.END)
            box.append(sub_btn)

            row.set_child(box)
            self._listbox.append(row)

    def _art_cb(self, image):
        def cb(texture):
            if texture is not None:
                image.set_from_paintable(texture)
        return cb

    def _subscribe(self, row, feed_url, button, fallback_image_url=""):
        button.set_sensitive(False)
        button.set_label("Subscribing…")

        def done(podcast_id, err):
            if err:
                button.set_sensitive(True)
                button.set_label("Try again")
                self.window.toast(f"Could not subscribe: {err.get('error','')}")
                return
            button.set_label("Subscribed")
            button.remove_css_class("suggested-action")
            button.add_css_class("success")

        self.window._subscribe(feed_url, done, fallback_image_url)
