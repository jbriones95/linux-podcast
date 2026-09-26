import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib, Pango

from .episode_row import EpisodeRow


class PodcastPage(Adw.NavigationPage):
    """Detail view of one subscribed podcast: artwork, info, episode list."""

    _PAGE_SIZE = 40

    def __init__(self, window, podcast_id):
        super().__init__(title="Podcast")
        self.window = window
        self.app = window.app
        self.podcast_id = podcast_id
        self.podcast = self.app.db.podcast(podcast_id)
        if self.podcast:
            self.set_title(self.podcast.title or "Podcast")

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh feed")
        refresh_btn.connect("clicked", lambda *_: window.refresh_feed(self.podcast_id))
        header.pack_end(refresh_btn)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.append(self._header_widget())
        content.append(self._listbox)

        # Use one touch scroller for artwork, description, and episodes. A
        # nested scroller made the description feel sticky and caused gesture
        # handoff/highlight artifacts on the phone.
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)

        toolbar.set_content(scroll)
        self.set_child(toolbar)
        self._rows = {}
        self._offset = 0
        self._generation = 0
        self._load_more_button = None
        self.rebuild()

    # ---------- header ----------
    def _header_widget(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(12)
        box.set_margin_bottom(8)

        self._art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=128)
        self._art.set_size_request(128, 128)
        self._art.set_halign(Gtk.Align.CENTER)
        if self.podcast:
            self.app.artwork.load(self.podcast.image_url, 192, self._art_cb)
        box.append(self._art)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(label=self.podcast.title if self.podcast else "")
        title.set_wrap(True)
        title.set_xalign(0)
        title.add_css_class("title-1")

        author = Gtk.Label(label=self.podcast.author if self.podcast else "")
        author.set_xalign(0)
        author.set_wrap(True)
        author.add_css_class("dim-label")

        desc = Gtk.Label(label=self.podcast.description if self.podcast else "")
        desc.set_wrap(True)
        desc.set_xalign(0)
        desc.set_selectable(False)

        unsub_btn = Gtk.Button(label="Unsubscribe")
        unsub_btn.add_css_class("destructive-action")
        unsub_btn.connect("clicked", self._on_unsubscribe)

        text.append(title)
        text.append(author)
        text.append(desc)
        unsub_btn.set_hexpand(True)
        text.append(unsub_btn)
        text.set_hexpand(True)
        box.append(text)
        return box

    def _art_cb(self, texture):
        if texture is not None:
            self._art.set_from_paintable(texture)

    # ---------- rows ----------
    def rebuild(self):
        self._generation += 1
        generation = self._generation
        while (child := self._listbox.get_first_child()) is not None:
            self._listbox.remove(child)
        self._rows.clear()
        self._offset = 0
        self._load_more_button = None
        self._load_page(generation)

    def _load_page(self, generation):
        offset = self._offset

        def work():
            return self.app.db.episodes(
                self.podcast_id, limit=self._PAGE_SIZE, offset=offset
            )

        def done(episodes):
            if generation != self._generation:
                return
            if isinstance(episodes, Exception):
                status = Adw.StatusPage.new()
                status.set_icon_name("dialog-error-symbolic")
                status.set_title("Could not load episodes")
                status.set_description("Try refreshing this podcast again.")
                self._listbox.append(status)
                return
            self._render_page(episodes, generation)

        self.app.async_tasks.submit(
            ("podcast", self.podcast_id),
            work,
            done,
            lambda callback: GLib.idle_add(callback),
        )

    def _render_page(self, episodes, generation):
        if not episodes:
            if self._offset:
                return
            status = Adw.StatusPage.new()
            status.set_icon_name("media-playback-start-symbolic")
            status.set_title("No episodes yet")
            status.set_description(
                "This feed has no episodes, or they may not be loaded yet. "
                "Pull to refresh."
            )
            self._listbox.append(status)
            return

        self._offset += len(episodes)
        self._append_batch(episodes, 0, generation)

    def _append_batch(self, episodes, index, generation):
        if generation != self._generation:
            return GLib.SOURCE_REMOVE
        for ep in episodes[index : index + 10]:
            row = EpisodeRow(self.window, ep, self.podcast)
            self._rows[ep.id] = row
            self._listbox.append(row)
        index += 10
        if index < len(episodes):
            GLib.idle_add(self._append_batch, episodes, index, generation)
            return GLib.SOURCE_REMOVE
        if len(episodes) == self._PAGE_SIZE:
            self._load_more_button = Gtk.Button(label="Load more episodes")
            self._load_more_button.set_margin_top(8)
            self._load_more_button.set_margin_bottom(16)
            self._load_more_button.connect("clicked", lambda *_: self._load_next_page(generation))
            self._listbox.append(self._load_more_button)
        return GLib.SOURCE_REMOVE

    def _load_next_page(self, generation):
        if self._load_more_button is not None:
            self._listbox.remove(self._load_more_button)
            self._load_more_button = None
        self._load_page(generation)

    def refresh_rows(self):
        for ep in self.app.db.episodes(self.podcast_id, limit=self._offset):
            row = self._rows.get(ep.id)
            if row is not None:
                row.rerender(ep)

    # ---------- download status ----------
    def _on_row_activated(self, listbox, row):
        if isinstance(row, EpisodeRow):
            self.window.open_episode(row.episode.id, self.podcast_id)

    def update_row_download(self, episode_id, downloading):
        for ep_id, row in self._rows.items():
            if ep_id == episode_id:
                row.update_download_state(downloading=downloading)

    def update_row_progress(self, episode_id, progress):
        for ep_id, row in self._rows.items():
            if ep_id == episode_id:
                row.update_download_state(downloading=True)
                row._progress = progress
                row._update_download_icon()

    # ---------- actions ----------
    def _on_unsubscribe(self, *args):
        dialog = Adw.AlertDialog.new(
            "Unsubscribe?",
            "This will remove the podcast and its episode history "
            "from your library.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Unsubscribe")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(dlg, resp):
            if resp == "remove":
                self.app.db.delete_podcast(self.podcast_id)
                self.app.refresh_library()
                self.window.toast("Unsubscribed.")
                self.window.nav.pop()

        dialog.connect("response", on_response)
        dialog.present(self.window)
