import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango

from ..models import Episode


def format_duration(seconds):
    if not seconds:
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_date(published):
    if not published:
        return "Unknown date"
    import datetime

    return datetime.datetime.fromtimestamp(published).strftime("%b %d, %Y")


class EpisodeRow(Gtk.ListBoxRow):
    """A single episode row with play + download actions."""

    def __init__(self, window, episode: Episode, podcast=None):
        super().__init__()
        self.window = window
        self.app = window.app
        self.episode = episode
        self.podcast = podcast

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        # text side
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text_box.set_hexpand(True)

        self.title = Gtk.Label(label=episode.title or "Untitled")
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.title.set_xalign(0)
        self.title.add_css_class("title-2")

        self.meta = Gtk.Label(
            label=f"{format_date(episode.published)} · {format_duration(episode.duration_seconds)}"
        )
        self.meta.set_xalign(0)
        self.meta.add_css_class("dim-label")

        self.state = Gtk.Label(label="")
        self.state.set_xalign(0)
        self.state.add_css_class("dim-label")

        text_box.append(self.title)
        text_box.append(self.meta)
        text_box.append(self.state)
        box.append(text_box)

        self.favorite_btn = Gtk.Button()
        self.favorite_btn.add_css_class("flat")
        self.favorite_btn.set_valign(Gtk.Align.CENTER)
        self.favorite_btn.connect("clicked", self._on_favorite)
        box.append(self.favorite_btn)

        self.played_btn = Gtk.Button()
        self.played_btn.add_css_class("flat")
        self.played_btn.set_valign(Gtk.Align.CENTER)
        self.played_btn.connect("clicked", self._on_played)
        box.append(self.played_btn)

        # download button
        self.download_btn = Gtk.Button()
        self.download_btn.set_icon_name("folder-download-symbolic")
        self.download_btn.set_tooltip_text("Download")
        self.download_btn.add_css_class("flat")
        self.download_btn.set_valign(Gtk.Align.CENTER)
        self.download_btn.connect("clicked", self._on_download)
        box.append(self.download_btn)

        # play button
        self.play_btn = Gtk.Button()
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.play_btn.set_tooltip_text("Play")
        self.play_btn.add_css_class("flat")
        self.play_btn.set_valign(Gtk.Align.CENTER)
        self.play_btn.connect("clicked", self._on_play)
        box.append(self.play_btn)

        self.set_child(box)
        self._downloading = False
        self._progress = None
        self._update_download_icon()
        self._update_play_icon()
        self._update_state_icons()

    def rerender(self, episode):
        if episode is None:
            return
        self.episode.played = episode.played
        self.episode.favorite = episode.favorite
        self.episode.position_seconds = episode.position_seconds
        self.episode.downloaded_path = episode.downloaded_path
        self._update_download_icon()
        self._update_play_icon()
        self._update_state_icons()

    # ---- actions ----
    def _on_play(self, *args):
        self.window.play_episode(self.episode, self.podcast)

    def _on_download(self, *args):
        if self.episode.is_downloaded:
            self.window.delete_episode_audio(self.episode.id)
        else:
            self.app.download_toggle(self.episode)

    def _on_favorite(self, *args):
        self.app.toggle_favorite(self.episode)

    def _on_played(self, *args):
        self.app.toggle_played(self.episode)

    # ---- state ----
    def update_download_state(self, downloading=False, progress=None):
        self._downloading = downloading
        self._progress = progress
        self._update_download_icon()

    def set_playing(self, playing):
        self._update_play_icon()

    def _update_play_icon(self):
        playing = self.window.is_current(self.episode.id)
        if playing and self.app.player.is_playing():
            self.play_btn.set_icon_name("media-playback-pause-symbolic")
        else:
            self.play_btn.set_icon_name("media-playback-start-symbolic")

    def _update_state_icons(self):
        if self.episode.favorite:
            self.favorite_btn.set_icon_name("starred-symbolic")
            self.favorite_btn.set_tooltip_text("Remove favorite")
        else:
            self.favorite_btn.set_icon_name("non-starred-symbolic")
            self.favorite_btn.set_tooltip_text("Add favorite")
        if self.episode.played:
            self.played_btn.set_icon_name("mail-read-symbolic")
            self.played_btn.set_tooltip_text("Mark unplayed")
        else:
            self.played_btn.set_icon_name("mail-unread-symbolic")
            self.played_btn.set_tooltip_text("Mark played")

    def _update_download_icon(self):
        if getattr(self, "_downloading", False):
            self.download_btn.set_icon_name("folder-sync-symbolic")
            self.download_btn.set_tooltip_text("Downloading…")
            return
        if self.episode.is_downloaded:
            self.download_btn.set_icon_name("emblem-ok-symbolic")
            self.download_btn.set_tooltip_text("Downloaded")
            self.state.set_text("Downloaded · " + self._progress_text())
        else:
            self.download_btn.set_icon_name("folder-download-symbolic")
            self.download_btn.set_tooltip_text("Download")
            self.state.set_text(self._progress_text())

    def _progress_text(self):
        if self.episode.played:
            return "Played"
        if self.episode.position_seconds:
            return f"{format_duration(self.episode.position_seconds)} played"
        return ""
