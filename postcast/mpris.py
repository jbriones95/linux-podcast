import gi
from datetime import datetime, timezone

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from .mpris_policy import seek_target


BUS_NAME = "org.mpris.MediaPlayer2.Postcast"
OBJECT_PATH = "/org/mpris/MediaPlayer2"

ROOT_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
</node>
"""

PLAYER_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek"><arg name="Offset" type="x" direction="in"/></method>
    <method name="SetPosition"><arg name="TrackId" type="o" direction="in"/><arg name="Position" type="x" direction="in"/></method>
    <method name="OpenUri"><arg name="Uri" type="s" direction="in"/></method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""


class MprisService:
    """Expose playback to Phosh, media keys, headsets, and desktop controls."""

    def __init__(self, app):
        self.app = app
        self.connection = None
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )
        app.connect("playback-state", self._on_state)
        app.connect("position", self._on_position)
        app.connect("seeked", self._on_seeked)
        app.connect("now-playing", self._on_now_playing)
        app.connect("volume-changed", self._on_volume_changed)
        app.connect("rate-changed", self._on_rate_changed)
        app.connect("queue-changed", self._on_queue_changed)

    def stop(self):
        if self.connection is not None:
            for registration in getattr(self, "_registrations", []):
                self.connection.unregister_object(registration)
            self.connection = None
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = None

    def _on_bus_acquired(self, connection, _name):
        self.connection = connection
        self._root_info = Gio.DBusNodeInfo.new_for_xml(ROOT_XML).interfaces[0]
        self._player_info = Gio.DBusNodeInfo.new_for_xml(PLAYER_XML).interfaces[0]
        self._registrations = [
            connection.register_object(
                OBJECT_PATH, self._root_info, self._method_call, self._get_property, self._set_property
            ),
            connection.register_object(
                OBJECT_PATH, self._player_info, self._method_call, self._get_property, self._set_property
            ),
        ]

    def _on_name_lost(self, _connection, _name):
        self.connection = None

    def _method_call(self, _connection, _sender, _path, interface, method, params, invocation):
        try:
            if interface == "org.mpris.MediaPlayer2":
                if method == "Raise":
                    self.app.activate()
                elif method == "Quit":
                    self.app.quit()
            elif interface == "org.mpris.MediaPlayer2.Player":
                playback = self.app.playback
                if method == "Next":
                    playback.play_next()
                elif method == "Previous":
                    playback.smart_rewind()
                elif method == "Pause":
                    playback.pause()
                elif method == "PlayPause":
                    playback.toggle()
                elif method == "Stop":
                    playback.stop()
                elif method == "Play":
                    playback.play()
                elif method == "Seek":
                    offset = params.unpack()[0]
                    position, duration = playback.player.position()
                    target = seek_target(position, duration, offset / 1_000_000)
                    playback.player.seek(target)
                elif method == "SetPosition":
                    track_id, position = params.unpack()
                    if track_id != self._track_id():
                        raise ValueError("TrackId does not match the current episode")
                    playback.player.seek(int(position / 1_000_000))
                elif method == "OpenUri":
                    uri = params.unpack()[0]
                    if not uri.startswith(("http://", "https://", "file://")):
                        raise ValueError("Unsupported URI scheme")
                    match = self.app.db.episode_by_playable_uri(uri)
                    if match is None:
                        raise ValueError("URI is not in the library")
                    self.app.playback.play_episode(match[1], match[0])
            invocation.return_value(GLib.Variant("()", ()))
        except Exception as exc:
            invocation.return_dbus_error("org.mpris.MediaPlayer2.Error", str(exc))

    def _get_property(self, _connection, _sender, _path, interface, name):
        if interface == "org.mpris.MediaPlayer2":
            root = {
                "CanQuit": GLib.Variant("b", True),
                "CanRaise": GLib.Variant("b", True),
                "HasTrackList": GLib.Variant("b", False),
                "Identity": GLib.Variant("s", "Postcast"),
                "DesktopEntry": GLib.Variant("s", "io.postcast.Postcast"),
                "SupportedUriSchemes": GLib.Variant("as", ["http", "https", "file"]),
                "SupportedMimeTypes": GLib.Variant("as", ["audio/mpeg", "audio/ogg", "audio/mp4"]),
            }
            return root.get(name)

        playback = self.app.playback
        player = self.app.player
        values = {
            "PlaybackStatus": GLib.Variant("s", self._status()),
            "LoopStatus": GLib.Variant("s", "None"),
            "Rate": GLib.Variant("d", playback.speed()),
            "Shuffle": GLib.Variant("b", False),
            "Metadata": GLib.Variant("a{sv}", self._metadata()),
            "Volume": GLib.Variant("d", playback.volume()),
            "MinimumRate": GLib.Variant("d", 0.5),
            "MaximumRate": GLib.Variant("d", 3.0),
            "CanGoNext": GLib.Variant("b", playback.can_go_next()),
            "CanGoPrevious": GLib.Variant("b", playback.can_go_previous()),
            "CanPlay": GLib.Variant("b", bool(playback.current_episode() and playback.current_episode().playable_uri())),
            "CanPause": GLib.Variant("b", bool(playback.current_episode() and playback.current_episode().playable_uri())),
            "CanSeek": GLib.Variant("b", playback.current_episode() is not None),
            "CanControl": GLib.Variant("b", True),
        }
        if name == "Position":
            return GLib.Variant("x", int(player.position()[0] * 1_000_000))
        return values.get(name)

    def _set_property(self, _connection, _sender, _path, interface, name, value):
        if interface != "org.mpris.MediaPlayer2.Player":
            return False
        if name == "Volume":
            self.app.playback.set_volume(value.unpack())
        elif name == "Rate":
            self.app.playback.set_speed(value.unpack())
        elif name == "LoopStatus":
            return value.unpack() == "None"
        elif name == "Shuffle":
            return value.unpack() is False
        else:
            return False
        self._emit_changed([name])
        return True

    def _status(self):
        state = self.app.player.state()
        return {"playing": "Playing", "paused": "Paused"}.get(state, "Stopped")

    def _metadata(self):
        episode = self.app.playback.current_episode()
        podcast = self.app.playback.podcast
        if episode is None:
            return {}
        track_id = f"/org/mpris/MediaPlayer2/Track/{episode.id}"
        values = {
            "mpris:trackid": GLib.Variant("o", track_id),
            "xesam:title": GLib.Variant("s", episode.title or "Untitled episode"),
            "xesam:album": GLib.Variant("s", podcast.title if podcast else ""),
            "xesam:artist": GLib.Variant("as", [podcast.author] if podcast and podcast.author else []),
            "xesam:url": GLib.Variant("s", episode.playable_uri() or ""),
            "mpris:length": GLib.Variant("x", int((episode.duration_seconds or 0) * 1_000_000)),
        }
        if episode.description:
            values["xesam:comment"] = GLib.Variant("as", [episode.description])
        if episode.published:
            values["xesam:contentCreated"] = GLib.Variant(
                "s", datetime.fromtimestamp(episode.published, timezone.utc).isoformat()
            )
        if podcast and podcast.image_url:
            values["mpris:artUrl"] = GLib.Variant(
                "s", self.app.artwork.cached_uri(podcast.image_url) or podcast.image_url
            )
        return values

    def _track_id(self):
        episode = self.app.playback.current_episode()
        return f"/org/mpris/MediaPlayer2/Track/{episode.id}" if episode else "/"

    def _emit_changed(self, names):
        if self.connection is None:
            return
        changed = {}
        for name in names:
            value = self._get_property(
                self.connection, None, OBJECT_PATH, "org.mpris.MediaPlayer2.Player", name
            )
            if value is not None:
                changed[name] = value
        self.connection.emit_signal(
            None,
            OBJECT_PATH,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", ("org.mpris.MediaPlayer2.Player", changed, [])),
        )

    def _on_state(self, _app, _state):
        self._emit_changed(
            ["PlaybackStatus", "CanPlay", "CanPause", "CanSeek", "CanGoNext", "CanGoPrevious"]
        )

    def _on_position(self, _app, _position, _duration):
        self._emit_changed(["Position"])

    def _on_seeked(self, _app, position):
        self._emit_seeked(position)
        self._emit_changed(["Position"])

    def _on_now_playing(self, _app, _podcast, _episode):
        self._emit_changed(
            [
                "Metadata", "Position", "PlaybackStatus", "CanPlay", "CanPause",
                "CanSeek", "CanGoNext", "CanGoPrevious",
            ]
        )

    def _on_volume_changed(self, _app, _value):
        self._emit_changed(["Volume"])

    def _on_rate_changed(self, _app, _value):
        self._emit_changed(["Rate"])

    def _on_queue_changed(self, _app):
        self._emit_changed(["CanGoNext", "CanGoPrevious"])

    def _emit_seeked(self, position):
        if self.connection is not None:
            self.connection.emit_signal(
                None,
                OBJECT_PATH,
                "org.mpris.MediaPlayer2.Player",
                "Seeked",
                GLib.Variant("(x)", (int(position * 1_000_000),)),
            )
