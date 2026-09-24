import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, Pango

from .episode_row import EpisodeRow


class PodcastPage(Adw.NavigationPage):
    """Detail view of one subscribed podcast: artwork, info, episode list."""

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
        self._listbox.set_vexpand(True)
        self._listbox.connect("row-activated", self._on_row_activated)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self._listbox)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.append(self._header_widget())
        content.append(scroll)

        toolbar.set_content(content)
        self.set_child(toolbar)
        self._rows = {}
        self.rebuild()

    # ---------- header ----------
    def _header_widget(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(8)

        self._art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=96)
        self._art.set_size_request(96, 96)
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
        desc.set_lines(4)
        desc.set_ellipsize(Pango.EllipsizeMode.END)

        unsub_btn = Gtk.Button(label="Unsubscribe")
        unsub_btn.add_css_class("destructive-action")
        unsub_btn.connect("clicked", self._on_unsubscribe)

        text.append(title)
        text.append(author)
        text.append(desc)
        text.append(unsub_btn)
        text.set_hexpand(True)
        box.append(text)
        return box

    def _art_cb(self, texture):
        if texture is not None:
            self._art.set_from_paintable(texture)

    # ---------- rows ----------
    def rebuild(self):
        while (child := self._listbox.get_first_child()) is not None:
            self._listbox.remove(child)
        self._rows.clear()

        episodes = self.app.db.episodes(self.podcast_id)
        if not episodes:
            status = Adw.StatusPage.new()
            status.set_icon_name("media-playback-start-symbolic")
            status.set_title("No episodes yet")
            status.set_description(
                "This feed has no episodes, or they may not be loaded yet. "
                "Pull to refresh."
            )
            self._listbox.append(status)
            return

        for ep in episodes:
            row = EpisodeRow(self.window, ep, self.podcast)
            self._rows[ep.id] = row
            self._listbox.append(row)

    def refresh_rows(self):
        for ep in self.app.db.episodes(self.podcast_id):
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
