import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, Pango

from .episode_row import format_date, format_duration


class EpisodePage(Adw.NavigationPage):
    """Readable episode details; playback is an explicit action."""

    def __init__(self, window, episode_id, podcast_id=None):
        super().__init__(title="Episode")
        self.window = window
        self.app = window.app
        self.episode = self.app.db.episode(episode_id)
        self.podcast = self.app.db.podcast(podcast_id or self.episode.podcast_id)
        if self.episode:
            self.set_title(self.episode.title or "Episode")

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(20)
        content.set_margin_bottom(24)
        content.set_margin_start(20)
        content.set_margin_end(20)

        art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=160)
        art.set_size_request(160, 160)
        if self.podcast:
            self.app.artwork.load(self.podcast.image_url, 320, self._set_artwork(art))
        content.append(art)

        title = Gtk.Label(label=self.episode.title if self.episode else "")
        title.set_wrap(True)
        title.set_xalign(0)
        title.set_justify(Gtk.Justification.CENTER)
        title.add_css_class("title-1")
        content.append(title)

        meta_parts = [
            format_date(self.episode.published),
            format_duration(self.episode.duration_seconds),
        ]
        if self.episode.season_number is not None or self.episode.episode_number is not None:
            season = f"S{self.episode.season_number}" if self.episode.season_number is not None else ""
            number = f"E{self.episode.episode_number}" if self.episode.episode_number is not None else ""
            meta_parts.insert(0, f"{season}{number}")
        if self.episode.explicit:
            meta_parts.append("Explicit")
        meta = Gtk.Label(label=" · ".join(meta_parts))
        meta.add_css_class("dim-label")
        content.append(meta)

        actions = Gtk.Grid()
        actions.set_row_spacing(8)
        actions.set_column_spacing(8)
        actions.set_column_homogeneous(True)
        actions.set_hexpand(True)
        play = Gtk.Button(label="Play")
        play.add_css_class("suggested-action")
        play.set_size_request(-1, 48)
        play.connect("clicked", lambda *_: self.window.play_episode(self.episode, self.podcast))
        actions.attach(play, 0, 0, 2, 1)
        self.download = Gtk.Button()
        self.download.set_size_request(-1, 48)
        self.download.connect("clicked", self._on_download)
        self.favorite = Gtk.Button()
        self.favorite.set_size_request(-1, 48)
        self.favorite.connect("clicked", self._on_favorite)
        self.played = Gtk.Button()
        self.played.set_size_request(-1, 48)
        self.played.connect("clicked", self._on_played)
        self.queue = Gtk.Button()
        self.queue.set_size_request(-1, 48)
        self.queue.connect("clicked", self._on_queue)
        actions.attach(self.download, 0, 1, 1, 1)
        actions.attach(self.favorite, 1, 1, 1, 1)
        actions.attach(self.played, 0, 2, 1, 1)
        actions.attach(self.queue, 1, 2, 1, 1)
        self._update_action_labels()
        content.append(actions)

        description = Gtk.Label(label=self.episode.description or "No description available.")
        description.set_wrap(True)
        description.set_selectable(False)
        description.set_xalign(0)
        description.set_ellipsize(Pango.EllipsizeMode.NONE)
        content.append(description)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    def _update_action_labels(self):
        self.download.set_label("Delete download" if self.episode.is_downloaded else "Download")
        self.favorite.set_label("Unfavorite" if self.episode.favorite else "Favorite")
        self.played.set_label("Mark unplayed" if self.episode.played else "Mark played")
        self.queue.set_label(
            "Remove from queue"
            if self.app.playback.is_queued(self.episode)
            else "Add to queue"
        )

    def _on_download(self, *args):
        if self.episode.is_downloaded:
            self.window.delete_episode_audio(self.episode.id)
        else:
            self.app.download_toggle(self.episode)
        self.episode = self.app.db.episode(self.episode.id)
        self._update_action_labels()

    def _on_favorite(self, *args):
        self.app.toggle_favorite(self.episode)
        self.episode = self.app.db.episode(self.episode.id)
        self._update_action_labels()

    def _on_played(self, *args):
        self.app.toggle_played(self.episode)
        self.episode = self.app.db.episode(self.episode.id)
        self._update_action_labels()

    def _on_queue(self, *args):
        if self.app.playback.is_queued(self.episode):
            self.app.playback.remove_from_queue(self.episode)
        else:
            self.app.playback.add_to_queue(self.podcast, self.episode)
        self._update_action_labels()

    def refresh(self):
        self.episode = self.app.db.episode(self.episode.id)
        self._update_action_labels()

    @staticmethod
    def _set_artwork(image):
        def callback(texture):
            if texture is not None:
                image.set_from_paintable(texture)
        return callback
