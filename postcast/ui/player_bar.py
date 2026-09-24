from gi.repository import Gtk


class PlayerBar(Gtk.Box):
    """Compact bottom bar showing currently playing episode + controls."""

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window = window
        self.app = window.app
        self.set_css_classes(["player-bar"])

        # seek bar
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        self.seek.set_size_request(-1, 2)
        self.seek.connect("value-changed", self._on_seek)
        self.seek_gesture = Gtk.GestureClick.new()
        self.seek.add_controller(self.seek_gesture)
        self.seek_gesture.connect("pressed", self._on_seek_pressed)
        self.seek_gesture.connect("released", self._on_seek_released)
        self._seeking = False

        # content row
        self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.row.set_margin_top(6)
        self.row.set_margin_bottom(6)

        self.art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=40)
        self.art.set_size_request(40, 40)
        self.art.add_css_class("player-art")

        self.title_label = Gtk.Label(label="")
        self.title_label.set_ellipsize(True)
        self.title_label.set_xalign(0)
        self.title_label.set_hexpand(True)
        self.title_label.add_css_class("title")

        self.time_label = Gtk.Label(label="0:00 / 0:00")
        self.time_label.add_css_class("dim-label")

        self._btn_play = Gtk.Button()
        self._btn_play.set_icon_name("media-playback-start-symbolic")
        self._btn_play.add_css_class("flat")
        self._btn_play.connect("clicked", self._on_play_clicked)

        self._btn_next = Gtk.Button()
        self._btn_next.set_icon_name("go-next-symbolic")
        self._btn_next.add_css_class("flat")
        self._btn_next.connect("clicked", lambda *_: self.window.play_next())

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title_box.set_hexpand(True)
        artist_label = self.title_label
        title_box.append(artist_label)

        self.row.append(self.art)
        self.row.append(title_box)
        self.row.append(self.time_label)
        self.row.append(self._btn_play)
        self.row.append(self._btn_next)

        self.append(self.seek)
        self.append(self.row)

        self._current_episode_id = None

        self.set_visible(False)

    # ---- wiring ----
    def set_episode(self, episode, podcast):
        self._current_episode_id = episode.id
        self.title_label.set_text(episode.title or "Unknown episode")
        self.set_visible(True)
        self._btn_play.set_icon_name("media-pause-symbolic")
        self.app.artwork.load(podcast.image_url, 80, self._set_artwork)
        self.app.playback.set_source(podcast, episode)

    def _set_artwork(self, texture):
        if texture is not None:
            self.art.set_from_paintable(texture)

    def clear(self):
        self._current_episode_id = None
        self.title_label.set_text("")
        self.time_label.set_text("0:00 / 0:00")
        self.seek.set_value(0)
        self.set_visible(False)

    # ---- remote/state updates ----
    def on_position(self, pos_sec, dur_sec):
        if self._seeking:
            return
        if dur_sec > 0:
            self.seek.set_value(pos_sec / dur_sec)
            self.seek.set_sensitive(True)
        else:
            self.seek.set_value(0)
            self.seek.set_sensitive(False)
        self.time_label.set_text(f"{self._fmt(pos_sec)} / {self._fmt(dur_sec)}")

    def on_state_changed(self, state):
        self._btn_play.set_icon_name(
            "media-pause-symbolic" if state == "playing" else "media-playback-start-symbolic"
        )

    def on_finished(self):
        self._btn_play.set_icon_name("media-playback-start-symbolic")

    # ---- interactions ----
    def _on_play_clicked(self, btn):
        self.app.playback.toggle()

    def _on_seek_pressed(self, *args):
        self._seeking = True

    def _on_seek_released(self, gesture, n_press, x, y):
        self._seeking = False
        if self._current_episode_id is not None:
            self.app.playback.seek_to_fraction(self.seek.get_value())

    def _on_seek(self, scale):
        pass

    @staticmethod
    def _fmt(seconds):
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"