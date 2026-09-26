import gi
import logging

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

from .config import USER_AGENT
from .playback_policy import rate_requires_seek


logger = logging.getLogger(__name__)


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
        self.playbin.connect("source-setup", self._on_source_setup)
        self._state = self.STATE_STOPPED
        self._desired_state = self.STATE_STOPPED
        self._buffering = False
        self._generation = 0
        self._uri = None
        self._last_saved = None
        self._position_timer = None
        self._last_emitted_position = None
        self._callbacks = {}
        self._seek_target = None
        self._rate = 1.0
        self._pending_rate = None
        self._rate_position = None
        self._rate_retry_source = None
        self._rate_retry_count = 0
        self._rate_retry_generation = 0
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
        self._generation += 1
        self._uri = uri
        self._last_emitted_position = None
        self._last_saved = None
        self.playbin.set_property("uri", uri)
        self._seek_target = position_seconds
        self._desired_state = self.STATE_PAUSED
        self._set_state(self.STATE_PAUSED)
        self.playbin.set_state(Gst.State.PAUSED)

    def play(self):
        if not self._uri:
            return False
        self._desired_state = self.STATE_PLAYING
        self._buffering = False
        result = self.playbin.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            self._set_state(self.STATE_STOPPED)
            self._emit("error", "GStreamer could not start playback")
            return False
        return True

    def pause(self):
        self._desired_state = self.STATE_PAUSED
        self._buffering = False
        self.playbin.set_state(Gst.State.PAUSED)
        self._stop_position_timer()
        self._set_state(self.STATE_PAUSED)

    def toggle(self):
        if self._state in (self.STATE_PLAYING,):
            self.pause()
        elif self._uri:
            self.play()

    def stop(self):
        self._generation += 1
        self._desired_state = self.STATE_STOPPED
        self._buffering = False
        self.playbin.set_state(Gst.State.NULL)
        self._set_state(self.STATE_STOPPED)
        self._stop_position_timer()
        if self._rate_retry_source is not None:
            GLib.source_remove(self._rate_retry_source)
            self._rate_retry_source = None
        self._seek_target = None
        self._rate_position = None
        self._rate_retry_count = 0

    def close(self):
        """Release GStreamer resources during application shutdown."""
        self.stop()
        self._bus.remove_signal_watch()

    def is_playing(self):
        return self._state == self.STATE_PLAYING

    def state(self):
        return self._state

    def desired_state(self):
        return self._desired_state

    def set_volume(self, value):
        value = max(0.0, min(1.0, float(value)))
        try:
            self.playbin.set_property("volume", value)
        except Exception:
            pass

    def set_rate(self, rate):
        rate = max(0.5, min(3.0, float(rate)))
        self._rate = rate
        if not rate_requires_seek(rate):
            # Normal speed is GStreamer's native mode. Do not issue a FLUSH
            # seek merely to reapply 1x: remote sources may not be seekable
            # during preroll, and the flush can restart network buffering.
            self._pending_rate = None
            self._rate_position = None
            self._cancel_rate_retry()
            return
        self._pending_rate = rate
        self._rate_retry_count = 0
        self._rate_retry_generation = self._generation
        if not self._uri:
            return
        position, duration = self.position()
        if duration <= 0 or not self._is_seekable():
            logger.debug("Deferring rate %.2f for non-seekable/unready URI %s", rate, self._uri)
            return
        if not self._apply_rate(position) and self._state == self.STATE_PLAYING:
            self._start_rate_retry()

    def _apply_rate(self, position=None):
        if not self._uri:
            return False
        if position is None:
            position, duration = self.position()
        else:
            _current, duration = self.position()
        if duration <= 0 or not self._is_seekable():
            return False
        if position is None:
            position = 0
        success = self.playbin.seek(
            self._pending_rate or self._rate,
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
            Gst.SeekType.SET,
            position * Gst.SECOND,
            Gst.SeekType.END,
            0,
        )
        if success:
            self._pending_rate = None
            self._rate_position = None
        return bool(success)

    def _retry_rate(self):
        if (
            self._pending_rate is None
            or not self._uri
            or self._desired_state != self.STATE_PLAYING
            or self._rate_retry_generation != self._generation
        ):
            self._rate_retry_source = None
            return GLib.SOURCE_REMOVE
        self._rate_retry_count += 1
        if self._rate_retry_count > 10:
            logger.warning("Giving up rate restoration for %s", self._uri)
            self._pending_rate = None
            self._rate_retry_source = None
            return GLib.SOURCE_REMOVE
        position = self._rate_position
        if self._apply_rate(position):
            self._rate_retry_source = None
            return GLib.SOURCE_REMOVE
        return True

    def _start_rate_retry(self):
        if self._rate_retry_source is None:
            self._rate_retry_source = GLib.timeout_add(250, self._retry_rate)

    def _cancel_rate_retry(self):
        if self._rate_retry_source is not None:
            GLib.source_remove(self._rate_retry_source)
            self._rate_retry_source = None

    def _is_seekable(self):
        try:
            success, seekable, _start, _end = self.playbin.query_seeking(Gst.Format.TIME)
            return bool(success and seekable)
        except (AttributeError, TypeError, RuntimeError):
            return False

    def rate(self):
        return self._rate

    def seek(self, seconds):
        seconds = max(0, int(seconds))
        _position, duration = self.position()
        if duration:
            seconds = min(seconds, duration)
        # Do not gate explicit seeks on query_seeking(). For HTTP sources the
        # query can report false while prerolling/buffering even though the
        # server supports byte-range seeks. Let GStreamer attempt the seek.
        if not self._uri:
            return False
        success = self.playbin.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
            seconds * Gst.SECOND,
        )
        if success:
            self._emit("position", seconds, duration)
            self._emit("seeked", seconds)
        return bool(success)

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
        elif t == Gst.MessageType.BUFFERING:
            percent = message.parse_buffering()[0]
            was_buffering = self._buffering
            self._buffering = percent < 100
            if self._buffering and self._desired_state == self.STATE_PLAYING:
                self.playbin.set_state(Gst.State.PAUSED)
            elif was_buffering and not self._buffering and self._desired_state == self.STATE_PLAYING:
                self.playbin.set_state(Gst.State.PLAYING)
        elif t == Gst.MessageType.ERROR:
            err, dbg = message.parse_error()
            self._stop_position_timer()
            self._set_state(self.STATE_STOPPED)
            logger.error("GStreamer playback error for %s: %s (%s)", self._uri, err.message, dbg)
            self._emit("error", f"{err.message}")
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.playbin:
                old, new, pending = message.parse_state_changed()
                if new == Gst.State.PLAYING and self._desired_state == self.STATE_PLAYING:
                    self._set_state(self.STATE_PLAYING)
                    self._start_position_timer()
                elif new == Gst.State.PAUSED and self._desired_state == self.STATE_PAUSED:
                    self._set_state(self.STATE_PAUSED)
                    self._stop_position_timer()
                if new == Gst.State.PLAYING and self._desired_state == self.STATE_PLAYING and self._seek_target is not None:
                    self._rate_position = self._seek_target
                    if self._seek_target > 0:
                        self.seek(self._seek_target)
                    self._seek_target = None
                if (
                    new == Gst.State.PLAYING
                    and self._desired_state == self.STATE_PLAYING
                    and self._pending_rate is not None
                    and self._is_seekable()
                ):
                    self._start_rate_retry()

    def _on_source_setup(self, _playbin, source):
        try:
            source.set_property("user-agent", USER_AGENT)
            logger.debug("Configured streaming source %s with Postcast User-Agent", source.get_name())
        except Exception:
            pass

    def _start_position_timer(self):
        if self._position_timer is None:
            self._position_timer = GLib.timeout_add(1000, self._emit_position)

    def _stop_position_timer(self):
        if self._position_timer is not None:
            GLib.source_remove(self._position_timer)
            self._position_timer = None

    def _emit_position(self):
        if self._state != self.STATE_PLAYING:
            return True
        pos, dur = self.position()
        current = (pos, dur)
        if current != self._last_emitted_position:
            self._last_emitted_position = current
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
