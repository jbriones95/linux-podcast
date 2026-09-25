import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

from ..player import Player


class Playback:
    """Orchestrates the Player: what is playing, persist positions, auto-advance."""

    def __init__(self, app, player: Player):
        self.app = app
        self.db = app.db
        self.player = player
        self.podcast = None
        self.episode = None
        self._queue = []      # (Podcast, Episode) pairs persisted in the database
        self._queue_index = -1
        self._fallback_queue = []
        self._fallback_index = -1
        self._last_listen_position = 0
        self._sleep_source = None
        self._rate = float(self.db.get_setting("playback_rate", 1.0))
        self._volume = float(self.db.get_setting("playback_volume", 1.0))
        self.player.set_volume(self._volume)
        self._load_queue()

        player.connect("position", self._on_position)
        player.connect("progress", self._on_progress)
        player.connect("state-changed", self._on_state)
        player.connect("finished", self._on_finished)
        player.connect("error", self._on_error)

    # ---------- public ----------
    def set_source(self, podcast, episode, queue=None):
        self.podcast = podcast
        self.episode = episode
        self._last_listen_position = episode.position_seconds
        if queue is not None:
            self._fallback_queue = [(podcast, item) for item in queue]
            self._fallback_index = self._index_of(episode.id, self._fallback_queue)
        else:
            self._load_queue()
            self._fallback_queue = [
                (podcast, item) for item in self.db.episodes(podcast.id)
            ]
            self._fallback_index = self._index_of(episode.id, self._fallback_queue)
            self._queue_index = self._index_of(episode.id, self._queue)

    def toggle(self):
        self.player.toggle()

    def seek_to_fraction(self, fraction):
        pos, dur = self.player.position()
        if dur:
            self.player.seek(int(fraction * dur))

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()
        self._save_position()

    def stop(self):
        self._save_position()
        self.player.stop()

    def add_to_queue(self, podcast, episode):
        if self.db.add_to_queue(episode.id):
            self._load_queue()
            self.app.toast("Added to queue.")
        else:
            self.app.toast("Already in queue.")

    def remove_from_queue(self, episode):
        self.db.remove_from_queue(episode.id)
        self._load_queue()

    def is_queued(self, episode):
        return self.db.is_queued(episode.id)

    def _load_queue(self):
        self._queue = self.db.queue_items()
        if self.episode:
            self._queue_index = self._index_of(self.episode.id, self._queue)

    def _save_position(self):
        if self.episode:
            position, _duration = self.player.position()
            if position > 0:
                self.db.set_position(self.episode.id, position)
                self._record_listening(position)

    def _record_listening(self, position):
        delta = int(position) - int(self._last_listen_position)
        if 0 < delta <= 60 and self.episode:
            self.db.record_listening(self.episode.id, delta)
        self._last_listen_position = int(position)

    def skip(self, seconds):
        position, duration = self.player.position()
        target = max(0, position + int(seconds))
        if duration:
            target = min(target, duration)
        self.player.seek(target)

    def set_speed(self, rate):
        self._rate = max(0.5, min(3.0, float(rate)))
        self.db.set_setting("playback_rate", self._rate)
        self.player.set_rate(self._rate)

    def speed(self):
        return self._rate

    def set_volume(self, value):
        self._volume = max(0.0, min(1.0, float(value)))
        self.db.set_setting("playback_volume", self._volume)
        self.player.set_volume(self._volume)

    def volume(self):
        return self._volume

    def set_sleep_timer(self, minutes):
        self.cancel_sleep_timer()
        if minutes:
            self._sleep_source = GLib.timeout_add_seconds(
                int(minutes) * 60, self._sleep_expired
            )

    def cancel_sleep_timer(self):
        if self._sleep_source is not None:
            GLib.source_remove(self._sleep_source)
            self._sleep_source = None

    def _sleep_expired(self):
        self._sleep_source = None
        self.pause()
        self.app.toast("Sleep timer ended.")
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        """Persist the current position before the application exits."""
        self._save_position()
        self.cancel_sleep_timer()
        self.player.close()

    # ---------- queue ----------
    def play_episode(self, podcast, episode, queue=None):
        self.set_source(podcast, episode, queue)
        self.app.emit("now-playing", podcast, episode)
        uri = episode.playable_uri()
        if not uri:
            self.app.toast("This episode has no playable audio URL.")
            return
        self.player.load(uri, episode.position_seconds)
        self.player.set_rate(self._rate)
        self.player.play()

    def play_next(self):
        if not self.episode:
            return False
        nxt = self._next_item()
        if nxt is None:
            self.app.toast("End of list (nothing unplayed left).")
            return False
        self.play_episode(nxt[0], nxt[1])
        return True

    def current_episode(self):
        return self.episode

    # ---------- internals ----------
    def _index_of(self, episode_id, queue):
        for i, item in enumerate(queue):
            if item[1].id == episode_id:
                return i
        return -1

    def _next_item(self):
        queue = self._queue
        index = self._queue_index
        if queue:
            if index < 0:
                return queue[0]
            if index + 1 < len(queue):
                self._queue_index = index + 1
                return queue[self._queue_index]
            return None

        queue = self._fallback_queue
        if not queue:
            return None
        n = len(queue)
        start = self._fallback_index + 1
        # first unplayed episode after the current one, wrapping around
        for i in range(start, start + n):
            e = queue[i % n][1]
            if e.id != self.episode.id and not e.played:
                self._fallback_index = i % n
                return queue[self._fallback_index]
        # nothing unplayed left: just advance in queue order
        next_index = (self._fallback_index + 1) % n
        nxt = queue[next_index][1]
        if nxt.id == self.episode.id:
            return None
        self._fallback_index = next_index
        return queue[next_index]

    # ---------- callbacks ----------
    def _on_position(self, pos, dur):
        self.app.emit("position", pos, dur)

    def _on_progress(self, pos, dur):
        if self.episode and pos > 0:
            self.db.set_position(self.episode.id, pos)
            self._record_listening(pos)

    def _on_state(self, state):
        self.app.emit("playback-state", state)

    def _on_finished(self):
        if self.episode:
            self.db.mark_played(self.episode.id, True, 0)
            self.db.record_listening(self.episode.id, 0, completed=True)
            self.app.emit("episode-finished", self.episode.id)
        self.app.emit("playback-state", "stopped")
        # auto-advance
        self.play_next()

    def _on_error(self, err):
        self.app.emit("playback-error", err)
