import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango


def _accessible_label(widget, label):
    try:
        widget.update_property([Gtk.AccessibleProperty.LABEL], [label])
    except (AttributeError, TypeError):
        pass


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
        _accessible_label(self.seek, "Playback position")
        self.seek.connect("value-changed", self._on_seek)
        self.seek_gesture = Gtk.GestureDrag.new()
        self.seek.add_controller(self.seek_gesture)
        self.seek_gesture.connect("drag-begin", self._on_seek_begin)
        self.seek_gesture.connect("drag-update", self._on_seek_update)
        self.seek_gesture.connect("drag-end", self._on_seek_end)
        self.seek_gesture.connect("cancel", lambda *_: setattr(self, "_seeking", False))
        seek_click = Gtk.GestureClick.new()
        seek_click.connect("released", self._on_seek_click)
        self.seek.add_controller(seek_click)
        self._seeking = False

        # content row
        self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.row.set_margin_top(6)
        self.row.set_margin_bottom(6)

        self.art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=40)
        self.art.set_size_request(40, 40)
        self.art.add_css_class("player-art")

        self.title_label = Gtk.Label(label="")
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_xalign(0)
        self.title_label.set_hexpand(True)
        self.title_label.add_css_class("title")

        self.podcast_label = Gtk.Label(label="")
        self.podcast_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.podcast_label.set_xalign(0)
        self.podcast_label.add_css_class("dim-label")

        self.time_label = Gtk.Label(label="0:00 / 0:00")
        self.time_label.add_css_class("dim-label")

        self._btn_play = Gtk.Button()
        self._btn_play.set_icon_name("media-playback-start-symbolic")
        self._btn_play.set_tooltip_text("Play")
        self._btn_play.add_css_class("flat")
        self._btn_play.set_size_request(44, 44)
        _accessible_label(self._btn_play, "Play")
        self._btn_play.connect("clicked", self._on_play_clicked)

        self._btn_previous = Gtk.Button()
        self._btn_previous.set_icon_name("media-skip-backward-symbolic")
        self._btn_previous.set_tooltip_text("Play previous")
        self._btn_previous.add_css_class("flat")
        self._btn_previous.set_size_request(44, 44)
        self._btn_previous.connect("clicked", lambda *_: self.app.playback.smart_rewind())
        _accessible_label(self._btn_previous, "Rewind or play previous episode")

        self._btn_next = Gtk.Button()
        self._btn_next.set_icon_name("go-next-symbolic")
        self._btn_next.set_tooltip_text("Play next")
        self._btn_next.add_css_class("flat")
        self._btn_next.set_size_request(44, 44)
        self._btn_next.connect("clicked", lambda *_: self.window.play_next())
        _accessible_label(self._btn_next, "Play next episode")

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title_box.set_hexpand(True)
        title_box.append(self.title_label)
        title_box.append(self.podcast_label)
        _accessible_label(title_box, "Open expanded player")
        _accessible_label(self.art, "Podcast artwork; open expanded player")

        for widget in (self.art, title_box, self.time_label):
            gesture = Gtk.GestureClick.new()
            gesture.connect("released", self._on_open_full_player)
            widget.add_controller(gesture)

        self.row.append(self.art)
        self.row.append(title_box)
        self.row.append(self.time_label)
        self.row.append(self._btn_previous)
        self.row.append(self._btn_play)
        self.row.append(self._btn_next)

        self.append(self.seek)
        self.append(self.row)

        self._current_episode_id = None
        self._artwork_token = object()
        self._compact_width = None

        self.set_visible(False)

    # ---- wiring ----
    def set_episode(self, episode, podcast):
        self._current_episode_id = episode.id
        token = self._artwork_token = object()
        self.title_label.set_text(episode.title or "Unknown episode")
        self.podcast_label.set_text(podcast.title if podcast else "")
        self.set_visible(True)
        self.on_state_changed(self.app.player.state())
        if podcast:
            self.app.artwork.load(
                podcast.image_url,
                80,
                lambda texture, token=token: self._set_artwork(texture, token),
            )
        if self.window.player_sheet is not None:
            self.window.player_sheet.set_episode(episode, podcast)

    def _set_artwork(self, texture, token):
        if texture is not None and token is self._artwork_token:
            self.art.set_from_paintable(texture)

    def clear(self):
        self._current_episode_id = None
        self.title_label.set_text("")
        self.podcast_label.set_text("")
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
        playing = state == "playing"
        self._btn_play.set_icon_name(
            "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic"
        )
        self._btn_play.set_tooltip_text("Pause" if playing else "Play")
        _accessible_label(self._btn_play, "Pause" if playing else "Play")

    def on_finished(self):
        self._btn_play.set_icon_name("media-playback-start-symbolic")
        self._btn_play.set_tooltip_text("Play")

    # ---- interactions ----
    def _on_play_clicked(self, btn):
        self.app.playback.toggle()

    def _on_open_full_player(self, gesture, n_press, x, y):
        if n_press == 1:
            self.window.open_now_playing()

    def update_layout(self, width):
        """Reduce compact controls when portrait width cannot fit them well."""
        mode = "narrow" if width > 0 and width < 400 else "regular"
        if mode == self._compact_width:
            return
        self._compact_width = mode
        narrow = mode == "narrow"
        self._btn_previous.set_visible(not narrow)
        self._btn_next.set_visible(not narrow)
        self.time_label.set_visible(not narrow)

    def _set_seek_from_x(self, x):
        width = self.seek.get_width()
        if width > 0:
            self.seek.set_value(max(0.0, min(1.0, x / width)))

    def _on_seek_begin(self, _gesture, start_x, _start_y):
        self._seeking = True
        self.seek_gesture_start_x = start_x
        self._set_seek_from_x(start_x)

    def _on_seek_update(self, _gesture, offset_x, _offset_y):
        self._set_seek_from_x(self.seek_gesture_start_x + offset_x)

    def _on_seek_end(self, _gesture, offset_x, _offset_y):
        self._set_seek_from_x(self.seek_gesture_start_x + offset_x)
        self._seeking = False
        if self._current_episode_id is not None:
            self.app.playback.seek_to_fraction(self.seek.get_value())

    def _on_seek_click(self, _gesture, n_press, x, _y):
        if n_press == 1 and not self._seeking:
            self._set_seek_from_x(x)
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


class PlayerSheet(Gtk.Overlay):
    """Expanded player presented in-place as a swipe-dismissable sheet."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.app = window.app
        self._seeking = False
        self._episode_id = None
        self._artwork_token = object()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_visible(False)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.set_margin_top(36)
        panel.add_css_class("background")
        panel.add_css_class("player-sheet")
        self.panel = panel
        self.set_child(panel)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-end", self._on_drag_end)
        panel.add_controller(drag)

        handle = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        handle.set_size_request(48, 4)
        handle.set_halign(Gtk.Align.CENTER)
        handle.set_margin_top(8)
        handle.add_css_class("pill")
        panel.append(handle)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(8)
        header.set_margin_bottom(4)
        close = Gtk.Button(icon_name="go-down-symbolic")
        self.close_button = close
        close.set_tooltip_text("Close player")
        _accessible_label(close, "Close expanded player")
        close.add_css_class("flat")
        close.set_size_request(48, 48)
        close.connect("clicked", lambda *_: self.close())
        header.append(close)
        handle = Gtk.Label(label="Now playing")
        handle.add_css_class("title")
        handle.set_hexpand(True)
        handle.set_xalign(0.5)
        header.append(handle)
        header.append(Gtk.Box())
        panel.append(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(8)
        content.set_margin_bottom(24)
        scroll.set_child(content)
        panel.append(scroll)

        self.art = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=220)
        self.art.set_size_request(220, 220)
        self.art.set_halign(Gtk.Align.CENTER)
        self.art.add_css_class("player-art-large")
        content.append(self.art)

        self.title = Gtk.Label(label="")
        self.title.set_wrap(True)
        self.title.set_lines(3)
        self.title.set_xalign(0.5)
        self.title.set_justify(Gtk.Justification.CENTER)
        self.title.add_css_class("title-1")
        content.append(self.title)

        self.podcast = Gtk.Label(label="")
        self.podcast.add_css_class("dim-label")
        self.podcast.set_ellipsize(Pango.EllipsizeMode.END)
        self.podcast.set_xalign(0.5)
        content.append(self.podcast)

        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        _accessible_label(self.seek, "Playback position")
        self.seek.connect("value-changed", lambda *_: None)
        seek_gesture = Gtk.GestureDrag.new()
        self.seek_gesture = seek_gesture
        seek_gesture.connect("drag-begin", self._on_seek_begin)
        seek_gesture.connect("drag-update", self._on_seek_update)
        seek_gesture.connect("drag-end", self._on_seek_end)
        seek_gesture.connect("cancel", lambda *_: setattr(self, "_seeking", False))
        seek_click = Gtk.GestureClick.new()
        seek_click.connect("released", self._on_seek_click)
        self.seek.add_controller(seek_click)
        self.seek.add_controller(seek_gesture)
        content.append(self.seek)

        self.time = Gtk.Label(label="0:00 / 0:00")
        self.time.add_css_class("dim-label")
        content.append(self.time)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.set_halign(Gtk.Align.CENTER)
        self._add_icon_button(controls, "media-skip-backward-symbolic", "Rewind or play previous", self.app.playback.smart_rewind)
        self._add_text_button(controls, "-15s", "Rewind 15 seconds", lambda: self.app.playback.skip(-15))
        self.play_btn = self._add_icon_button(
            controls, "media-playback-start-symbolic", "Play", self.app.playback.toggle, suggested=True
        )
        self._add_text_button(controls, "+30s", "Skip forward 30 seconds", lambda: self.app.playback.skip(30))
        self._add_icon_button(controls, "media-skip-forward-symbolic", "Play next episode", self.app.playback.play_next)
        content.append(controls)

        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        settings.add_css_class("card")
        settings.set_margin_top(8)
        settings.set_margin_start(4)
        settings.set_margin_end(4)
        speed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        speed_row.append(Gtk.Label(label="Speed"))
        self.speed_values = [0.75, 1.0, 1.25, 1.5, 2.0]
        self.speed = Gtk.DropDown.new(Gtk.StringList.new(["0.75x", "1.0x", "1.25x", "1.5x", "2.0x"]), None)
        _accessible_label(self.speed, "Playback speed")
        self.speed.set_selected(min(range(len(self.speed_values)), key=lambda i: abs(self.speed_values[i] - self.app.playback.speed())))
        self.speed.connect("notify::selected", self._on_speed_changed)
        speed_row.append(self.speed)
        settings.append(speed_row)

        volume_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        volume_row.append(Gtk.Label(label="Volume"))
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        _accessible_label(self.volume, "Volume")
        self.volume.set_value(self.app.playback.volume())
        self.volume.set_hexpand(True)
        self.volume.connect("value-changed", lambda scale: self.app.playback.set_volume(scale.get_value()))
        volume_row.append(self.volume)
        settings.append(volume_row)

        sleep_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sleep_row.append(Gtk.Label(label="Sleep timer"))
        self.sleep_values = [0, 15, 30, 60]
        self.sleep = Gtk.DropDown.new(
            Gtk.StringList.new(["Off", "15 minutes", "30 minutes", "60 minutes"]), None
        )
        _accessible_label(self.sleep, "Sleep timer")
        self.sleep.connect("notify::selected", self._on_sleep_changed)
        sleep_row.append(self.sleep)
        settings.append(sleep_row)
        content.append(settings)

        self.description = Gtk.Label(label="")
        self.description.set_wrap(True)
        self.description.set_xalign(0)
        self.description.set_selectable(False)
        self.description.set_ellipsize(Pango.EllipsizeMode.NONE)
        content.append(self.description)

        self.chapter_list = Gtk.ListBox()
        self.chapter_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.chapter_list.add_css_class("boxed-list")
        self.chapter_list.set_visible(False)
        content.append(self.chapter_list)
        self._chapter_rows = []

        self.app.connect("position", self._on_position)
        self.app.connect("playback-state", self._on_state)
        self.app.connect("volume-changed", self._on_volume_changed)
        self.app.connect("rate-changed", self._on_rate_changed)
        self.app.connect("chapters-changed", self._on_chapters_changed)
        self.app.connect("chapter-changed", self._on_chapters_changed)

    def _add_icon_button(self, box, icon, tooltip, callback, suggested=False):
        button = Gtk.Button(icon_name=icon)
        button.set_tooltip_text(tooltip)
        button.set_size_request(48 if not suggested else 60, 48 if not suggested else 60)
        button.add_css_class("suggested-action" if suggested else "flat")
        _accessible_label(button, tooltip)
        button.connect("clicked", lambda *_: callback())
        box.append(button)
        return button

    def _add_text_button(self, box, label, tooltip, callback):
        button = Gtk.Button(label=label)
        button.set_tooltip_text(tooltip)
        button.set_size_request(58, 48)
        button.add_css_class("flat")
        _accessible_label(button, tooltip)
        button.connect("clicked", lambda *_: callback())
        box.append(button)

    def set_episode(self, episode, podcast):
        self._episode_id = episode.id
        token = self._artwork_token = object()
        self.title.set_text(episode.title or "Unknown episode")
        self.podcast.set_text(podcast.title if podcast else "")
        self.description.set_text(episode.description or "")
        self._render_chapters()
        if podcast:
            self.app.artwork.load(
                podcast.image_url,
                480,
                lambda texture, token=token: self._set_artwork(texture, token),
            )
        self.on_state_changed(self.app.player.state())

    def open(self):
        episode = self.app.playback.current_episode()
        podcast = self.app.playback.podcast
        if episode is None:
            self.window.toast("Nothing is playing.")
            return
        self.set_episode(episode, podcast)
        self.set_visible(True)

    def close(self):
        self.set_visible(False)
        self.window.restore_player_focus()

    def _set_artwork(self, texture, token):
        if texture is not None and token is self._artwork_token:
            self.art.set_from_paintable(texture)

    def on_position(self, _app, position, duration):
        if not self._seeking and duration:
            self.seek.set_value(position / duration)
        elif not duration:
            self.seek.set_value(0)
            self.seek.set_sensitive(False)
        else:
            self.seek.set_sensitive(True)
        self.time.set_text(f"{PlayerBar._fmt(position)} / {PlayerBar._fmt(duration)}")

    def on_state_changed(self, state):
        playing = state == "playing"
        self.play_btn.set_icon_name(
            "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic"
        )
        self.play_btn.set_tooltip_text("Pause" if playing else "Play")
        _accessible_label(self.play_btn, "Pause" if playing else "Play")

    def _on_position(self, app, position, duration):
        if self.get_visible():
            self.on_position(app, position, duration)

    def _on_state(self, _app, state):
        self.on_state_changed(state)

    def _on_chapters_changed(self, *_args):
        if self.get_visible():
            self._render_chapters()

    def _render_chapters(self):
        while (child := self.chapter_list.get_first_child()) is not None:
            self.chapter_list.remove(child)
        self._chapter_rows = []
        chapters = self.app.playback.chapters()
        self.chapter_list.set_visible(bool(chapters))
        for chapter in chapters:
            button = Gtk.Button(label=f"{self._fmt(chapter.start_seconds)}  {chapter.title}")
            button.set_halign(Gtk.Align.FILL)
            button.add_css_class("flat")
            _accessible_label(button, f"Jump to chapter {chapter.title}")
            button.connect(
                "clicked", lambda _button, chapter=chapter:
                self.app.playback.jump_to_chapter(chapter)
            )
            self.chapter_list.append(button)
            self._chapter_rows.append((chapter, button))

    def _set_seek_from_x(self, x):
        width = self.seek.get_width()
        if width > 0:
            self.seek.set_value(max(0.0, min(1.0, x / width)))

    def _on_seek_begin(self, _gesture, start_x, _start_y):
        self._seeking = True
        self.seek_gesture_start_x = start_x
        self._set_seek_from_x(start_x)

    def _on_seek_update(self, _gesture, offset_x, _offset_y):
        self._set_seek_from_x(self.seek_gesture_start_x + offset_x)

    def _on_seek_end(self, _gesture, offset_x, _offset_y):
        self._set_seek_from_x(self.seek_gesture_start_x + offset_x)
        self._seeking = False
        if self._episode_id is not None:
            self.app.playback.seek_to_fraction(self.seek.get_value())

    def _on_seek_click(self, _gesture, n_press, x, _y):
        if n_press == 1 and not self._seeking:
            self._set_seek_from_x(x)
            if self._episode_id is not None:
                self.app.playback.seek_to_fraction(self.seek.get_value())

    def _on_speed_changed(self, dropdown, _param=None):
        self.app.playback.set_speed(self.speed_values[dropdown.get_selected()])

    def _on_volume_changed(self, _app, value):
        if abs(self.volume.get_value() - value) > 0.001:
            self.volume.set_value(value)

    def _on_rate_changed(self, _app, value):
        index = min(range(len(self.speed_values)), key=lambda i: abs(self.speed_values[i] - value))
        if self.speed.get_selected() != index:
            self.speed.set_selected(index)

    def _on_sleep_changed(self, dropdown, _param):
        minutes = self.sleep_values[dropdown.get_selected()]
        self.app.playback.set_sleep_timer(minutes)

    def _on_drag_end(self, _gesture, offset_x, offset_y):
        if offset_y > 70 and abs(offset_y) > abs(offset_x):
            self.close()
