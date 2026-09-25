import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from ..player import Player


class Playback:
    """Orchestrates the Player: what is playing, persist positions, auto-advance."""

    def __init__(self, app, player: Player):
        self.app = app
        self.db = app.db
        self.player = player
        self.podcast = None
        self.episode = None
        self._queue = []      # Episode objects
        self._queue_index = -1

        player.connect("position", self._on_position)
        player.connect("progress", self._on_progress)
        player.connect("state-changed", self._on_state)
        player.connect("finished", self._on_finished)
        player.connect("error", self._on_error)

    # ---------- public ----------
    def set_source(self, podcast, episode, queue=None):
        self.podcast = podcast
        self.episode = episode
        if queue is not None:
            self._queue = queue
            self._queue_index = self._index_of(episode.id)

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

    def shutdown(self):
        """Persist the current position before the application exits."""
        if self.episode:
            position, _duration = self.player.position()
            if position > 0:
                self.db.set_position(self.episode.id, position)
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
        self.player.play()

    def play_next(self):
        if not self.episode or not self._queue:
            return False
        nxt = self._next_item()
        if nxt is None:
            self.app.toast("End of list (nothing unplayed left).")
            return False
        self.play_episode(self.podcast, nxt, self._queue)
        return True

    def current_episode(self):
        return self.episode

    # ---------- internals ----------
    def _index_of(self, episode_id):
        for i, e in enumerate(self._queue):
            if e.id == episode_id:
                return i
        return -1

    def _next_item(self):
        if not self._queue:
            return None
        n = len(self._queue)
        start = self._queue_index + 1
        # first unplayed episode after the current one, wrapping around
        for i in range(start, start + n):
            e = self._queue[i % n]
            if e.id != self.episode.id and not e.played:
                self._queue_index = i % n
                return e
        # nothing unplayed left: just advance in queue order
        nxt = self._queue[(self._queue_index + 1) % n]
        if nxt.id == self.episode.id:
            return None
        self._queue_index = (self._queue_index + 1) % n
        return nxt

    # ---------- callbacks ----------
    def _on_position(self, pos, dur):
        self.app.emit("position", pos, dur)

    def _on_progress(self, pos, dur):
        if self.episode and pos > 0:
            self.db.set_position(self.episode.id, pos)

    def _on_state(self, state):
        self.app.emit("playback-state", state)

    def _on_finished(self):
        if self.episode:
            self.db.mark_played(self.episode.id, True, 0)
            self.app.emit("episode-finished", self.episode.id)
        self.app.emit("playback-state", "stopped")
        # auto-advance
        self.play_next()

    def _on_error(self, err):
        self.app.emit("playback-error", err)
