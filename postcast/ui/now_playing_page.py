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

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(16)
        content.set_margin_bottom(20)
        content.set_margin_start(16)
        content.set_margin_end(16)

        self.art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=200)
        self.art.set_size_request(200, 200)
        self.art.set_halign(Gtk.Align.CENTER)
        if self.podcast:
            self.app.artwork.load(self.podcast.image_url, 480, self._set_artwork)
        content.append(self.art)

        self.title = Gtk.Label(label=self.episode.title if self.episode else "")
        self.title.set_wrap(True)
        self.title.set_lines(3)
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

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.set_halign(Gtk.Align.CENTER)
        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.set_size_request(52, 52)
        next_btn.set_tooltip_text("Play next")
        next_btn.connect("clicked", lambda *_: self.window.play_next())
        controls.append(next_btn)
        self.play_btn = Gtk.Button(icon_name="media-playback-pause-symbolic")
        self.play_btn.set_size_request(60, 60)
        self.play_btn.add_css_class("suggested-action")
        self.play_btn.set_tooltip_text("Pause")
        self.play_btn.connect("clicked", lambda *_: self.app.playback.toggle())
        controls.append(self.play_btn)
        content.append(controls)

        seek_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        seek_controls.set_hexpand(True)
        seek_controls.set_halign(Gtk.Align.CENTER)
        back_btn = Gtk.Button(label="-15s")
        back_btn.set_size_request(100, 48)
        back_btn.set_tooltip_text("Skip back 15 seconds")
        back_btn.connect("clicked", lambda *_: self.app.playback.skip(-15))
        seek_controls.append(back_btn)
        forward_btn = Gtk.Button(label="+30s")
        forward_btn.set_size_request(100, 48)
        forward_btn.set_tooltip_text("Skip forward 30 seconds")
        forward_btn.connect("clicked", lambda *_: self.app.playback.skip(30))
        seek_controls.append(forward_btn)
        content.append(seek_controls)

        playback_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        speed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        speed_row.append(Gtk.Label(label="Speed"))
        self.speed_dropdown = Gtk.DropDown.new(
            Gtk.StringList.new(["0.75x", "1.0x", "1.25x", "1.5x", "2.0x"]), None
        )
        speed_values = [0.75, 1.0, 1.25, 1.5, 2.0]
        speed_index = min(range(len(speed_values)), key=lambda i: abs(speed_values[i] - self.app.playback.speed()))
        self.speed_dropdown.set_selected(speed_index)
        self.speed_dropdown.connect("notify::selected", self._on_speed_changed, speed_values)
        speed_row.append(self.speed_dropdown)
        speed_row.set_margin_start(8)
        speed_row.set_margin_end(8)
        playback_controls.append(speed_row)

        volume_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        volume_row.append(Gtk.Label(label="Volume"))
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.volume.set_value(self.app.playback.volume())
        self.volume.set_hexpand(True)
        self.volume.connect("value-changed", self._on_volume_changed)
        volume_row.append(self.volume)
        volume_row.set_margin_start(8)
        volume_row.set_margin_end(8)
        playback_controls.append(volume_row)

        sleep_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sleep_row.append(Gtk.Label(label="Sleep timer"))
        self.sleep_dropdown = Gtk.DropDown.new(
            Gtk.StringList.new(["Off", "15 minutes", "30 minutes", "60 minutes"]), None
        )
        self.sleep_minutes = [0, 15, 30, 60]
        self.sleep_dropdown.connect("notify::selected", self._on_sleep_changed)
        sleep_row.append(self.sleep_dropdown)
        sleep_row.set_margin_start(8)
        sleep_row.set_margin_end(8)
        playback_controls.append(sleep_row)
        content.append(playback_controls)

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

    def _on_speed_changed(self, dropdown, _param, values):
        self.app.playback.set_speed(values[dropdown.get_selected()])

    def _on_volume_changed(self, scale):
        self.app.playback.set_volume(scale.get_value())

    def _on_sleep_changed(self, dropdown, _param):
        minutes = self.sleep_minutes[dropdown.get_selected()]
        self.app.playback.set_sleep_timer(minutes)
        if minutes:
            self.window.toast(f"Sleep timer set for {minutes} minutes.")
        else:
            self.window.toast("Sleep timer off.")

    @staticmethod
    def _fmt(seconds):
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
