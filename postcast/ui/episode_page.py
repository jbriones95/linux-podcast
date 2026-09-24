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

        meta = Gtk.Label(
            label=(
                f"{format_date(self.episode.published)} · "
                f"{format_duration(self.episode.duration_seconds)}"
            )
        )
        meta.add_css_class("dim-label")
        content.append(meta)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.CENTER)
        play = Gtk.Button(label="Play")
        play.add_css_class("suggested-action")
        play.connect("clicked", lambda *_: self.window.play_episode(self.episode, self.podcast))
        actions.append(play)
        download = Gtk.Button(label="Download")
        download.connect("clicked", lambda *_: self.app.download_toggle(self.episode))
        actions.append(download)
        content.append(actions)

        description = Gtk.Label(label=self.episode.description or "No description available.")
        description.set_wrap(True)
        description.set_selectable(True)
        description.set_xalign(0)
        description.set_ellipsize(Pango.EllipsizeMode.NONE)
        content.append(description)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    @staticmethod
    def _set_artwork(image):
        def callback(texture):
            if texture is not None:
                image.set_from_paintable(texture)
        return callback
