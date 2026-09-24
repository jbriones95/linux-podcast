import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, Pango


class NowPlayingPage(Adw.NavigationPage):
    """Full-screen playback controls opened from the mini-player."""

    def __init__(self, window):
        super().__init__(title="Now Playing")
        self.window = window
        self.app = window.app
        self.episode = self.app.playback.current_episode()
        self.podcast = self.app.playback.podcast
        self._seeking = False

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        self.art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=240)
        self.art.set_size_request(240, 240)
        if self.podcast:
            self.app.artwork.load(self.podcast.image_url, 480, self._set_artwork)
        content.append(self.art)

        self.title = Gtk.Label(label=self.episode.title if self.episode else "")
        self.title.set_wrap(True)
        self.title.set_xalign(0.5)
        self.title.set_justify(Gtk.Justification.CENTER)
        self.title.add_css_class("title-1")
        content.append(self.title)

        podcast_title = Gtk.Label(label=self.podcast.title if self.podcast else "")
        podcast_title.add_css_class("dim-label")
        content.append(podcast_title)

        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.seek.set_draw_value(False)
        self.seek.connect("value-changed", self._on_seek)
        gesture = Gtk.GestureClick.new()
        gesture.connect("pressed", lambda *_: setattr(self, "_seeking", True))
        gesture.connect("released", self._on_seek_released)
        self.seek.add_controller(gesture)
        content.append(self.seek)

        self.time = Gtk.Label(label="0:00 / 0:00")
        self.time.add_css_class("dim-label")
        content.append(self.time)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        controls.set_halign(Gtk.Align.CENTER)
        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.set_tooltip_text("Play next")
        next_btn.connect("clicked", lambda *_: self.window.play_next())
        controls.append(next_btn)
        self.play_btn = Gtk.Button(icon_name="media-playback-pause-symbolic")
        self.play_btn.add_css_class("suggested-action")
        self.play_btn.set_tooltip_text("Pause")
        self.play_btn.connect("clicked", lambda *_: self.app.playback.toggle())
        controls.append(self.play_btn)
        content.append(controls)

        description = Gtk.Label(label=self.episode.description if self.episode else "")
        description.set_wrap(True)
        description.set_selectable(True)
        description.set_xalign(0)
        description.set_ellipsize(Pango.EllipsizeMode.NONE)
        content.append(description)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

        self.app.connect("position", self._on_position)
        self.app.connect("playback-state", self._on_state)

    def _set_artwork(self, texture):
        if texture is not None:
            self.art.set_from_paintable(texture)

    def _on_position(self, app, position, duration):
        if not self._seeking and duration:
            self.seek.set_value(position / duration)
        self.time.set_text(f"{self._fmt(position)} / {self._fmt(duration)}")

    def _on_state(self, app, state):
        playing = state == "playing"
        self.play_btn.set_icon_name(
            "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic"
        )
        self.play_btn.set_tooltip_text("Pause" if playing else "Play")

    def _on_seek(self, scale):
        if self._seeking:
            return

    def _on_seek_released(self, gesture, n_press, x, y):
        self._seeking = False
        self.app.playback.seek_to_fraction(self.seek.get_value())

    @staticmethod
    def _fmt(seconds):
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
