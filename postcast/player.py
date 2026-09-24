import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib


class Player:
    """Thin GStreamer playback wrapper running on the GLib main loop."""

    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_STOPPED = "stopped"

    def __init__(self):
        Gst.init(None)
        self.playbin = Gst.ElementFactory.make("playbin", "player")
        self._bus = self.playbin.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message", self._on_message)
        self._state = self.STATE_STOPPED
        self._uri = None
        self._last_saved = None
        self._position_timer = None
        self._callbacks = {}
        self._seek_target = None
        self._setup_volume()

    def _setup_volume(self):
        try:
            self.playbin.set_property("volume", 1.0)
        except Exception:
            pass

    # ------- public API -------
    def connect(self, signal, cb):
        self._callbacks.setdefault(signal, []).append(cb)

    def load(self, uri, position_seconds=0):
        self.stop()
        self._uri = uri
        self.playbin.set_property("uri", uri)
        self._seek_target = position_seconds
        self._set_state(self.STATE_PAUSED)
        self.playbin.set_state(Gst.State.PLAYING)
        self._start_position_timer()

    def play(self):
        self.playbin.set_state(Gst.State.PLAYING)
        self._set_state(self.STATE_PLAYING)
        self._start_position_timer()

    def pause(self):
        self.playbin.set_state(Gst.State.PAUSED)
        self._set_state(self.STATE_PAUSED)

    def toggle(self):
        if self._state in (self.STATE_PLAYING,):
            self.pause()
        elif self._uri:
            self.play()

    def stop(self):
        self.playbin.set_state(Gst.State.NULL)
        self._set_state(self.STATE_STOPPED)
        self._stop_position_timer()
        self._uri = None

    def is_playing(self):
        return self._state == self.STATE_PLAYING

    def state(self):
        return self._state

    def set_volume(self, value):
        value = max(0.0, min(1.0, float(value)))
        try:
            self.playbin.set_property("volume", value)
        except Exception:
            pass

    def seek(self, seconds):
        seconds = max(0, int(seconds))
        self.playbin.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            seconds * Gst.SECOND,
        )

    def position(self):
        """Return (position_seconds, duration_seconds)."""
        ok, pos = self.playbin.query_position(Gst.Format.TIME)
        ok2, dur = self.playbin.query_duration(Gst.Format.TIME)
        pos_s = int(pos / Gst.SECOND) if ok else 0
        dur_s = int(dur / Gst.SECOND) if ok2 else 0
        return pos_s, dur_s

    # ------- internals -------
    def _on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            self._stop_position_timer()
            self._set_state(self.STATE_STOPPED)
            self._emit("finished")
        elif t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            self._stop_position_timer()
            self._set_state(self.STATE_STOPPED)
            self._emit("error", f"{err.message}")
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.playbin:
                old, new, pending = message.parse_state_changed()
                if new == Gst.State.PLAYING and self._seek_target is not None:
                    self.seek(self._seek_target)
                    self._seek_target = None

    def _start_position_timer(self):
        if self._position_timer is None:
            self._position_timer = GLib.timeout_add(500, self._emit_position)

    def _stop_position_timer(self):
        if self._position_timer is not None:
            GLib.source_remove(self._position_timer)
            self._position_timer = None

    def _emit_position(self):
        if self._state != self.STATE_PLAYING:
            return True
        pos, dur = self.position()
        self._emit("position", pos, dur)
        # save progress at most every ~5 s
        if (self._last_saved is None or pos - self._last_saved >= 5) and pos > 0 and (dur == 0 or pos < dur - 1):
            self._last_saved = pos
            self._emit("progress", pos, dur)
        return True

    def _set_state(self, state):
        if self._state != state:
            self._state = state
            self._emit("state-changed", state)

    def _emit(self, signal, *args):
        for cb in self._callbacks.get(signal, []):
            try:
                cb(*args)
            except Exception:
                pass