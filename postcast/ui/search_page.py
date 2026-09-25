import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, Pango


class SearchPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title="Search")
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
        header.set_title_widget(self.entry)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.set_vexpand(True)

        self._status = Adw.StatusPage.new()
        self._status.set_icon_name("system-search-symbolic")
        self._status.set_title("Search")
        self._status.set_description("Find new podcasts to subscribe to.")

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self._listbox)

        stack = Gtk.Stack(vexpand=True)
        stack.add_named(self._status, "empty")
        stack.add_named(scroll, "results")
        self._stack = stack

        toolbar.set_content(stack)
        self.set_child(toolbar)

    # ---------- actions ----------
    def _on_search(self, *args):
        term = self.entry.get_text().strip()
        self._search_generation += 1
        generation = self._search_generation
        if not term:
            self._stack.set_visible_child_name("empty")
            return

        def on_results(results):
            if generation != self._search_generation:
                return
            if isinstance(results, Exception):
                self.window.toast(f"Search failed: {results}")
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
                lambda *_, row=row, url=item["feed_url"], button=sub_btn: self._subscribe(
                    row, url, button
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

    def _subscribe(self, row, feed_url, button):
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

        self.window._subscribe(feed_url, done)
