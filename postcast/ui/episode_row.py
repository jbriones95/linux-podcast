import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango

from ..models import Episode


def _accessible_label(widget, label):
    try:
        widget.update_property([Gtk.AccessibleProperty.LABEL], [label])
    except (AttributeError, TypeError):
        pass


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

    def __init__(
        self, window, episode: Episode, podcast=None, show_podcast=False,
        queue_position=None, queue_count=None,
    ):
        super().__init__()
        self.window = window
        self.app = window.app
        self.episode = episode
        self.podcast = podcast
        self._show_podcast = show_podcast
        self._artwork_token = object()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.set_hexpand(True)

        if show_podcast and podcast:
            artwork = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=64)
            artwork.set_size_request(64, 64)
            artwork.set_valign(Gtk.Align.START)
            top.append(artwork)
            self._artwork_url = podcast.image_url
            token = self._artwork_token
            if self._artwork_url:
                self.app.artwork.load(
                    self._artwork_url,
                    128,
                    self._artwork_callback(artwork, token, self._artwork_url),
                )

        # text side
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text_box.set_hexpand(True)

        self.title = Gtk.Label(label=episode.title or "Untitled")
        self.title.set_wrap(True)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.title.set_lines(2)
        self.title.set_xalign(0)
        self.title.add_css_class("title-2")

        meta_parts = [format_date(episode.published), format_duration(episode.duration_seconds)]
        if episode.season_number is not None or episode.episode_number is not None:
            season = f"S{episode.season_number}" if episode.season_number is not None else ""
            number = f"E{episode.episode_number}" if episode.episode_number is not None else ""
            meta_parts.insert(0, f"{season}{number}")
        if episode.explicit:
            meta_parts.append("Explicit")
        if show_podcast and podcast:
            meta_parts.insert(0, podcast.title or "Unknown show")
        self.meta = Gtk.Label(label=" · ".join(meta_parts))
        self.meta.set_xalign(0)
        self.meta.set_ellipsize(Pango.EllipsizeMode.END)
        self.meta.set_max_width_chars(42)
        self.meta.add_css_class("dim-label")

        self.state = Gtk.Label(label="")
        self.state.set_xalign(0)
        self.state.add_css_class("dim-label")

        text_box.append(self.title)
        text_box.append(self.meta)
        text_box.append(self.state)
        top.append(text_box)

        self.favorite_btn = Gtk.Button()
        self.favorite_btn.add_css_class("flat")
        self.favorite_btn.set_valign(Gtk.Align.CENTER)
        self.favorite_btn.connect("clicked", self._on_favorite)
        self.favorite_btn.set_size_request(44, 44)

        self.played_btn = Gtk.Button()
        self.played_btn.add_css_class("flat")
        self.played_btn.set_valign(Gtk.Align.CENTER)
        self.played_btn.connect("clicked", self._on_played)
        self.played_btn.set_size_request(44, 44)

        self.queue_btn = Gtk.Button()
        self.queue_btn.add_css_class("flat")
        self.queue_btn.set_valign(Gtk.Align.CENTER)
        self.queue_btn.connect("clicked", self._on_queue)
        self.queue_btn.set_size_request(44, 44)

        # download button
        self.download_btn = Gtk.Button()
        self.download_btn.set_icon_name("folder-download-symbolic")
        self.download_btn.set_tooltip_text("Download")
        self.download_btn.add_css_class("flat")
        self.download_btn.set_valign(Gtk.Align.CENTER)
        self.download_btn.connect("clicked", self._on_download)
        self.download_btn.set_size_request(44, 44)

        # play button
        self.play_btn = Gtk.Button()
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.play_btn.set_tooltip_text("Play")
        self.play_btn.add_css_class("flat")
        self.play_btn.set_valign(Gtk.Align.CENTER)
        self.play_btn.connect("clicked", self._on_play)
        self.play_btn.set_size_request(44, 44)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        actions.set_halign(Gtk.Align.END)
        for button in (
            self.favorite_btn,
            self.played_btn,
            self.queue_btn,
            self.download_btn,
            self.play_btn,
        ):
            actions.append(button)
        if queue_position is not None:
            if queue_position > 0:
                self._add_queue_move_button(
                    actions, "go-up-symbolic", "Move earlier", queue_position - 1
                )
            if queue_position < (queue_count or 0) - 1:
                self._add_queue_move_button(
                    actions, "go-down-symbolic", "Move later", queue_position + 1
                )
        box.append(top)
        box.append(actions)

        self.set_child(box)
        self._downloading = False
        self._download_state = None
        self._progress = None
        self.download_progress = Gtk.ProgressBar()
        self.download_progress.set_hexpand(True)
        self.download_progress.set_visible(False)
        box.append(self.download_progress)
        self._update_download_icon()
        self._update_play_icon()
        self._update_state_icons()
        self._update_queue_icon()
        self.update_download_state(state=self.app.downloads.state(self.episode.id))

    def _add_queue_move_button(self, box, icon, tooltip, target_position):
        button = Gtk.Button(icon_name=icon)
        button.set_tooltip_text(tooltip)
        button.add_css_class("flat")
        button.set_size_request(44, 44)
        button.connect(
            "clicked",
            lambda *_: self.window.move_queue_item(self.episode.id, target_position),
        )
        box.append(button)

    def _artwork_callback(self, image, token, url):
        def callback(texture):
            if (
                texture is not None
                and token is self._artwork_token
                and url == getattr(self, "_artwork_url", "")
                and self.get_parent() is not None
            ):
                image.set_from_paintable(texture)

        return callback

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

    def _on_queue(self, *args):
        if self.app.playback.is_queued(self.episode):
            self.app.playback.remove_from_queue(self.episode)
        elif self.podcast:
            self.app.playback.add_to_queue(self.podcast, self.episode)
        self._update_queue_icon()

    def _update_queue_icon(self):
        if self.app.playback.is_queued(self.episode):
            self.queue_btn.set_icon_name("list-remove-symbolic")
            self.queue_btn.set_tooltip_text("Remove from queue")
            _accessible_label(self.queue_btn, "Remove episode from queue")
        else:
            self.queue_btn.set_icon_name("list-add-symbolic")
            self.queue_btn.set_tooltip_text("Add to queue")
            _accessible_label(self.queue_btn, "Add episode to queue")

    # ---- state ----
    def update_download_state(self, downloading=False, progress=None, state=None):
        self._download_state = state or ("downloading" if downloading else None)
        self._downloading = self._download_state in ("queued", "downloading")
        self._progress = progress
        self._update_download_icon()

    def set_playing(self, playing):
        self._update_play_icon()

    def _update_play_icon(self):
        playing = self.window.is_current(self.episode.id)
        if playing and self.app.player.is_playing():
            self.play_btn.set_icon_name("media-playback-pause-symbolic")
            _accessible_label(self.play_btn, "Pause episode")
        else:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
            _accessible_label(self.play_btn, "Play episode")

    def _update_state_icons(self):
        if self.episode.favorite:
            self.favorite_btn.set_icon_name("starred-symbolic")
            self.favorite_btn.set_tooltip_text("Remove favorite")
            _accessible_label(self.favorite_btn, "Remove episode from favorites")
        else:
            self.favorite_btn.set_icon_name("non-starred-symbolic")
            self.favorite_btn.set_tooltip_text("Add favorite")
            _accessible_label(self.favorite_btn, "Add episode to favorites")
        if self.episode.played:
            self.played_btn.set_icon_name("mail-read-symbolic")
            self.played_btn.set_tooltip_text("Mark unplayed")
            _accessible_label(self.played_btn, "Mark episode unplayed")
        else:
            self.played_btn.set_icon_name("mail-unread-symbolic")
            self.played_btn.set_tooltip_text("Mark played")
            _accessible_label(self.played_btn, "Mark episode played")

    def _update_download_icon(self):
        if getattr(self, "_download_state", None) == "queued":
            self.download_btn.set_icon_name("folder-download-symbolic")
            self.download_btn.set_tooltip_text("Download queued")
            _accessible_label(self.download_btn, "Download queued")
            self.download_progress.set_visible(False)
            self.state.set_text("Queued for download")
            return
        if getattr(self, "_downloading", False):
            self.download_btn.set_icon_name("media-playback-stop-symbolic")
            self.download_btn.set_tooltip_text("Cancel download")
            _accessible_label(self.download_btn, "Cancel episode download")
            self.download_progress.set_visible(True)
            if self._progress is not None:
                self.download_progress.set_fraction(self._progress)
                self.state.set_text(f"Downloading {int(self._progress * 100)}%")
            else:
                self.download_progress.pulse()
                self.state.set_text("Downloading…")
            return
        self.download_progress.set_visible(False)
        if self.episode.is_downloaded:
            self.download_btn.set_icon_name("folder-download-symbolic")
            self.download_btn.set_tooltip_text("Delete downloaded episode")
            _accessible_label(self.download_btn, "Delete downloaded episode")
            self.state.set_text("Downloaded · " + self._progress_text())
        else:
            self.download_btn.set_icon_name("folder-download-symbolic")
            self.download_btn.set_tooltip_text("Download")
            _accessible_label(self.download_btn, "Download episode")
            self.state.set_text(self._progress_text())

    def _progress_text(self):
        if self.episode.played:
            return "Played"
        if self.episode.position_seconds:
            return f"{format_duration(self.episode.position_seconds)} played"
        return ""
