"""Remote media player, built on top of VLC.

Description: https://wiki.videolan.org/Python_bindings
API Documentation: https://www.olivieraubert.net/vlc/python-ctypes/doc/
CLI Documentation: https://wiki.videolan.org/VLC_command-line_help/
Requires `libvlc.dll` on Windows
"""

import logging
import os
import pathlib
import sys
import urllib.parse

from .library import Library, Media, SUBTITLE_TRACK, SUBTITLE_FILE, SubtitleTrack, SubtitleFile
from . import settings

if settings.VLC_DLL_DIRECTORY is not None and os.path.isdir(settings.VLC_DLL_DIRECTORY) and sys.platform == "win32":
    os.add_dll_directory(settings.VLC_DLL_DIRECTORY)
import vlc


logger = logging.getLogger(__name__)


class PlayerObserver:

    def on_media_changed(self, media_path: str | None):
        """
        @param media_path: path (relative to library root) to the loaded media
        """
        pass

    def on_time_changed(self, new_time: int):
        """
        @param time: new player time in milliseconds
        """
        pass

    def on_media_state_changed(self, new_state: int | None):
        pass


class VlcEvent:
    """This is a type checking hack since event types are not declared as
    attributes of EventType in vlc.py.
    """

    MediaDiscovererEnded = vlc.EventType(1281)
    MediaDiscovererStarted = vlc.EventType(0x500)
    MediaDurationChanged = vlc.EventType(2)
    MediaFreed = vlc.EventType(4)
    MediaListEndReached = vlc.EventType(516)
    MediaListItemAdded = vlc.EventType(0x200)
    MediaListItemDeleted = vlc.EventType(514)
    MediaListPlayerNextItemSet = vlc.EventType(1025)
    MediaListPlayerPlayed = vlc.EventType(0x400)
    MediaListPlayerStopped = vlc.EventType(1026)
    MediaListViewItemAdded = vlc.EventType(0x300)
    MediaListViewItemDeleted = vlc.EventType(770)
    MediaListViewWillAddItem = vlc.EventType(769)
    MediaListViewWillDeleteItem = vlc.EventType(771)
    MediaListWillAddItem = vlc.EventType(513)
    MediaListWillDeleteItem = vlc.EventType(515)
    MediaMetaChanged = vlc.EventType(0)
    MediaParsedChanged = vlc.EventType(3)
    MediaPlayerAudioDevice = vlc.EventType(284)
    MediaPlayerAudioVolume = vlc.EventType(283)
    MediaPlayerBackward = vlc.EventType(264)
    MediaPlayerBuffering = vlc.EventType(259)
    MediaPlayerChapterChanged = vlc.EventType(285)
    MediaPlayerCorked = vlc.EventType(279)
    MediaPlayerESAdded = vlc.EventType(276)
    MediaPlayerESDeleted = vlc.EventType(277)
    MediaPlayerESSelected = vlc.EventType(278)
    MediaPlayerEncounteredError = vlc.EventType(266)
    MediaPlayerEndReached = vlc.EventType(265)
    MediaPlayerForward = vlc.EventType(263)
    MediaPlayerLengthChanged = vlc.EventType(273)
    MediaPlayerMediaChanged = vlc.EventType(0x100)
    MediaPlayerMuted = vlc.EventType(281)
    MediaPlayerNothingSpecial = vlc.EventType(257)
    MediaPlayerOpening = vlc.EventType(258)
    MediaPlayerPausableChanged = vlc.EventType(270)
    MediaPlayerPaused = vlc.EventType(261)
    MediaPlayerPlaying = vlc.EventType(260)
    MediaPlayerPositionChanged = vlc.EventType(268)
    MediaPlayerScrambledChanged = vlc.EventType(275)
    MediaPlayerSeekableChanged = vlc.EventType(269)
    MediaPlayerSnapshotTaken = vlc.EventType(272)
    MediaPlayerStopped = vlc.EventType(262)
    MediaPlayerTimeChanged = vlc.EventType(267)
    MediaPlayerTitleChanged = vlc.EventType(271)
    MediaPlayerUncorked = vlc.EventType(280)
    MediaPlayerUnmuted = vlc.EventType(282)
    MediaPlayerVout = vlc.EventType(274)
    MediaStateChanged = vlc.EventType(5)
    MediaSubItemAdded = vlc.EventType(1)
    MediaSubItemTreeAdded = vlc.EventType(6)
    RendererDiscovererItemAdded = vlc.EventType(1282)
    RendererDiscovererItemDeleted = vlc.EventType(1283)
    VlmMediaAdded = vlc.EventType(0x600)
    VlmMediaChanged = vlc.EventType(1538)
    VlmMediaInstanceStarted = vlc.EventType(1539)
    VlmMediaInstanceStatusEnd = vlc.EventType(1545)
    VlmMediaInstanceStatusError = vlc.EventType(1546)
    VlmMediaInstanceStatusInit = vlc.EventType(1541)
    VlmMediaInstanceStatusOpening = vlc.EventType(1542)
    VlmMediaInstanceStatusPause = vlc.EventType(1544)
    VlmMediaInstanceStatusPlaying = vlc.EventType(1543)
    VlmMediaInstanceStopped = vlc.EventType(1540)
    VlmMediaRemoved = vlc.EventType(1537)


def get_state_name(state: int | None) -> str:
    if state is None:
        return "None"
    return [
        "NothingSpecial",
        "Opening",
        "Buffering",
        "Playing",
        "Paused",
        "Stopped",
        "Ended",
        "Error"
    ][state]


VlcMediaSlaveTypeAudio = vlc.MediaSlaveType(1)
VlcMediaSlaveTypeSubtitle = vlc.MediaSlaveType(0)


class Player:

    STATE_NOTHINGSPECIAL = 0
    STATE_OPENING = 1
    STATE_BUFFERING = 2
    STATE_PLAYING = 3
    STATE_PAUSED = 4
    STATE_STOPPED = 5
    STATE_ENDED = 6
    STATE_ERROR = 7

    def __init__(self):
        self.observers: set[PlayerObserver] = set()
        self.fastforward_seconds: int = settings.DEFAULT_FASTFORWARD_SECONDS
        self.rewind_seconds: int = settings.DEFAULT_REWIND_SECONDS
        self.subs_delay_step_ms: float = settings.DEFAULT_SUBS_DELAY_STEP_MILLISECONDS
        self.default_volume: int = settings.DEFAULT_VOLUME
        self.default_aspect_ratio: str | None = settings.DEFAULT_ASPECT_RATIO
        self.media: Media | None = None
        self.vlc_instance: vlc.Instance | None = None
        self.vlc_media_player: vlc.MediaPlayer | None = None
        self.vlc_media: vlc.Media | None = None
        self.vlc_event_manager: vlc.EventManager | None = None
        self.selected_audio_source: int | None = None
        self.selected_subtitle_source: int | None = None
        self.current_volume: int = self.default_volume
        self.current_aspect_ratio: str | None = self.default_aspect_ratio
        self.current_subs_delay: int = 0
        self._old_state = None
        self._playback_begins = False
        self._waiting_to_play = False
        self._waiting_to_pause = False
        self._waiting_to_stop = False
        self.waiting_screen_visible: bool = False
        self._previous_audio_and_subs_hash: str | None = None
        self._volume_before_waiting_screen: int = self.current_volume

    @property
    def media_path(self) -> str | None:
        if self.media is None:
            return None
        return self.media.path.as_posix()

    def mrl(self, basename: str) -> str:
        if self.media is None:
            raise ValueError("Media is None")
        if settings.LIBRARY_MODE == "local":
            return (pathlib.Path(settings.LIBRARY_ROOT) / self.media.folder.path / basename).as_uri()
        return urllib.parse.urljoin(settings.MEDIA_URL, urllib.parse.quote((self.media.folder.path / basename).as_posix()))

    @property
    def time(self) -> int | None:
        if self.vlc_media_player is None:
            return None
        return self.vlc_media_player.get_time()

    @property
    def state(self) -> int | None:
        if self.vlc_media_player is None:
            return None
        return self.vlc_media_player.get_state().value

    def setup(self):
        logger.info("Setting up the player")
        self.vlc_instance = vlc.Instance("--no-xlib --quiet")
        if not isinstance(self.vlc_instance, vlc.Instance):
            raise RuntimeError(f"Failed to initialized VLC instance")
        self.vlc_media_player = self.vlc_instance.media_player_new()
        if not isinstance(self.vlc_media_player, vlc.MediaPlayer):
            raise RuntimeError(f"Failed to initialized VLC media player")
        self.vlc_event_manager = self.vlc_media_player.event_manager()
        if not isinstance(self.vlc_event_manager, vlc.EventManager):
            raise RuntimeError(f"Failed to initialized VLC event manager")
        self.vlc_media_player.set_fullscreen(1)
        self.volume(self.default_volume)
        self.aspect_ratio(self.default_aspect_ratio)
        self.attach_events()

    def attach_events(self):
        def on_time_changed(event, player):
            logger.debug("Event fired: time changed to %d", event.u.new_time)
            for observer in self.observers:
                observer.on_time_changed(event.u.new_time)
            if self._playback_begins:
                self.on_playback_begins()
                self._playback_begins = False
        assert self.vlc_event_manager is not None
        self.vlc_event_manager.event_attach(
            VlcEvent.MediaPlayerTimeChanged,
            on_time_changed,
            self.vlc_media_player
        )
        state_event_types = (
            VlcEvent.MediaPlayerOpening,
            VlcEvent.MediaPlayerBuffering,
            VlcEvent.MediaPlayerPlaying,
            VlcEvent.MediaPlayerPaused,
            VlcEvent.MediaPlayerStopped,
            VlcEvent.MediaPlayerEndReached,
        )
        for event_type in state_event_types:
            def callback(event, player):
                logger.info("Event fired: state changed to %s (old state is %s)", get_state_name(self.state), get_state_name(self._old_state))
                new_state = self.state
                if self._old_state == new_state:
                    return
                self._old_state = new_state
                for observer in self.observers:
                    observer.on_media_state_changed(new_state)
            self.vlc_event_manager.event_attach(event_type, callback, self.vlc_media_player)
        def on_media_changed(event, player):
            logger.info("Event fired: media changed to %s", self.media_path)
            for observer in self.observers:
                observer.on_media_changed(self.media_path)
        self.vlc_event_manager.event_attach(
            VlcEvent.MediaPlayerMediaChanged,
            on_media_changed,
            self.vlc_media_player
        )
        def onbuffering(event, player):
            logger.debug("Event fired: media player is buffering, _waiting_to_play is %s", self._waiting_to_play)
            assert self.vlc_media_player is not None
            if self._waiting_to_play:
                self.vlc_media_player.play()
                self._playback_begins = True
                self._waiting_to_play = False
        self.vlc_event_manager.event_attach(
            VlcEvent.MediaPlayerBuffering,
            onbuffering,
            self.vlc_media_player
        )

    def on_playback_begins(self):
        logger.info("Playback begins")
        self.volume(self.current_volume)
        self.aspect_ratio(self.current_aspect_ratio)
        if not self.waiting_screen_visible:
            self.set_audio_source(self.selected_audio_source)
            self.set_subtitle_source(self.selected_subtitle_source)
        if self._waiting_to_pause:
            logger.info("Player is playing _waiting_to_pause is True, toggling pause now")
            self._waiting_to_pause = False
            self.toggle_play_pause()
        if self._waiting_to_stop:
            logger.info("Player is playing _waiting_to_stop is True, stopping now")
            self._waiting_to_stop = False
            self.stop()

    def auto_select_sources(self):
        previous_audio_source = self.selected_audio_source
        previous_subtitle_source = self.selected_subtitle_source

        self.selected_audio_source = None
        self.selected_subtitle_source = None

        if self.media is None:
            return

        current_audio_and_subs_hash = self.media.audio_and_subs_hash
        if current_audio_and_subs_hash == self._previous_audio_and_subs_hash:
            self.selected_audio_source = previous_audio_source
            self.selected_subtitle_source = previous_subtitle_source
            logger.info("Audio an subtitles sources match previous state. Re-selecting audio source %s and subtitle source %s",
                self.selected_audio_source, self.selected_subtitle_source)
            return

        foreign_audio_track = 0
        local_audio_track = None
        for i, source in enumerate(self.media.audio_sources):
            if source.language in settings.PREFERRED_MEDIA_LANGUAGE_CODES:
                local_audio_track = i
            if source.title is not None and "vo" in source.title.lower():
                foreign_audio_track = i

        local_subtitle_track = None
        for i, source in enumerate(self.media.subtitle_sources):
            if source.language in settings.PREFERRED_MEDIA_LANGUAGE_CODES:
                local_subtitle_track = i
                break

        if not self.media.audio_sources:
            if local_subtitle_track is not None:
                self.selected_subtitle_source = local_subtitle_track
            elif self.media.subtitle_sources:
                self.selected_subtitle_source = 0
        elif local_subtitle_track is not None:
            self.selected_audio_source = foreign_audio_track
            self.selected_subtitle_source = local_subtitle_track
        elif local_audio_track is not None:
            self.selected_audio_source = local_audio_track
        else:
            self.selected_audio_source = foreign_audio_track

        logger.info("Autoselected audio source %s and subtitle source %s",
            self.selected_audio_source, self.selected_subtitle_source)

    def load(self, media: Media, play: bool = False):
        logger.info("Loading media at %s", media.path)
        self.media = media
        self.auto_select_sources()
        self._previous_audio_and_subs_hash = self.media.audio_and_subs_hash
        self._waiting_to_play = play
        self.current_subs_delay = 0
        self.reload()
        if play:
            self.play()

    def reload(self):
        if self.vlc_media is not None:
            self.vlc_media.release()
        if self.media is None:
            logger.warning("Tried to reload player but media is None")
            return
        mrl = self.mrl(self.media.basename)
        logger.info("Loading media from MRL \"%s\"", mrl)
        assert self.vlc_instance is not None
        self.vlc_media = self.vlc_instance.media_new(mrl)
        assert self.vlc_media_player is not None
        self.vlc_media_player.set_media(self.vlc_media)

    def play(self):
        logger.info("Triggering play")
        if self.vlc_media_player is not None:
            self.vlc_media_player.play()
            self._playback_begins = True
        else:
            logger.error("Can not play, VLC media player is None")

    def toggle_play_pause(self):
        logger.info("Toggling pause")
        assert self.vlc_media_player is not None
        self.vlc_media_player.pause()

    def stop(self):
        logger.info("Stopping")
        assert self.vlc_media_player is not None
        self.vlc_media_player.stop()

    def seek(self, milliseconds: int):
        logger.info("Seeking to %d (ms)", milliseconds)
        assert self.vlc_media_player is not None
        self.vlc_media_player.set_time(milliseconds)

    def fastforward(self):
        logger.info("Fast forwarding %d seconds", self.fastforward_seconds)
        assert self.vlc_media_player is not None
        t = self.vlc_media_player.get_time()
        self.seek(t + 1000 * self.fastforward_seconds)

    def rewind(self):
        logger.info("Rewinding %d seconds", self.rewind_seconds)
        assert self.vlc_media_player is not None
        t = self.vlc_media_player.get_time()
        self.seek(t - 1000 * self.rewind_seconds)

    def subs_delay_set(self, delay: int):
        """
        @param delay: delay in milliseconds, positive: later, negative: earlier
        """
        self.current_subs_delay = delay
        assert self.vlc_media_player is not None
        self.vlc_media_player.video_set_spu_delay(self.current_subs_delay * 1000)

    def subs_delay_later(self):
        self.subs_delay_set(round(self.current_subs_delay + self.subs_delay_step_ms))

    def subs_delay_earlier(self):
        self.subs_delay_set(round(self.current_subs_delay - self.subs_delay_step_ms))

    def subs_delay_reset(self):
        self.subs_delay_set(0)

    def volume(self, value: int):
        """
        @param value: ranges from 0 (muted) to 100 (loudest)
        """
        logger.info("Setting volume to %d", value)
        assert self.vlc_media_player is not None
        self.current_volume = value
        self.vlc_media_player.audio_set_volume(value)

    def aspect_ratio(self, value: str | None):
        """
        @param value: string of the form "width:height", or `None` to reset
        """
        logger.info("Setting aspect ratio to %s", value)
        assert self.vlc_media_player is not None
        self.current_aspect_ratio = value
        self.vlc_media_player.video_set_aspect_ratio(value)

    def set_audio_source(self, i: int | None):
        """
        @param i: audio track index
        """
        logger.info("Setting audio source to %s", i)
        assert self.vlc_media_player is not None
        self.selected_audio_source = i
        if i is None:
            return
        assert self.media is not None
        self.vlc_media_player.audio_set_track(self.media.audio_sources[i].index)

    def set_subtitle_source(self, i: int | None):
        """
        @param i: subtitle track index, or `None` to disable subtitles
        """
        logger.info("Setting subtitle source to %s", i)
        assert self.vlc_media_player is not None
        if i == -1:
            i = None
        self.selected_subtitle_source = i
        if i is None:
            self.vlc_media_player.video_set_spu(-1)
            return
        assert self.media is not None
        subtitle_source = self.media.subtitle_sources[i]
        if subtitle_source.type == SUBTITLE_TRACK:
            assert isinstance(subtitle_source, SubtitleTrack)
            self.vlc_media_player.video_set_spu(subtitle_source.index)
        elif subtitle_source.type == SUBTITLE_FILE:
            assert isinstance(subtitle_source, SubtitleFile)
            uri = self.mrl(subtitle_source.basename)
            self.vlc_media_player.add_slave(VlcMediaSlaveTypeSubtitle, uri, 1)

    def close(self):
        logger.debug("Closing player")
        try:
            if self.vlc_media_player is not None:
                # NOTE: for some reason, realeasing the player here
                # makes the program silently crash, and I don't understand why.
                # self.vlc_media_player.release()
                pass
        except OSError as err:
            logger.warning(err)
        try:
            if self.vlc_instance is not None:
                self.vlc_instance.release()
        except OSError as err:
            logger.warning(err)
        logger.info("Closed player")

    def bind_observer(self, observer: PlayerObserver):
        logger.info("Binding observer %s", observer)
        self.observers.add(observer)

    def get_status_dict(self) -> dict:
        return {
            "media": None if self.media is None else self.media.to_mindict(),
            "current_volume": self.current_volume,
            "current_aspect_ratio": self.current_aspect_ratio,
            "time": self.time,
            "state": self.state,
            "selected_audio_source": self.selected_audio_source,
            "selected_subtitle_source": self.selected_subtitle_source,
            "delay": self.current_subs_delay,
        }

    def load_status_dict(self, status: dict, library: Library):
        media = None
        if status.get("media") is not None:
            media_dict = status["media"]
            media = library.get_media2(media_dict["basename"], media_dict["folder"])
        if media is not None:
            self.load(media)
            self.set_audio_source(status.get("selected_audio_source", self.selected_audio_source))
            self.set_subtitle_source(status.get("selected_subtitle_source", self.selected_subtitle_source))
            if status.get("state") in [Player.STATE_PLAYING, Player.STATE_PAUSED, Player.STATE_STOPPED]:
                self._waiting_to_pause = status["state"] == Player.STATE_PAUSED
                self._waiting_to_stop = status["state"] == Player.STATE_STOPPED
                self.play()
            self.seek(status.get("time", self.time))
        self.volume(status.get("current_volume", self.current_volume))
        self.subs_delay_set(status.get("delay", self.current_subs_delay))
        self.aspect_ratio(status.get("current_aspect_ratio", self.current_aspect_ratio))

    def show_waiting_screen(self):
        if self.vlc_media is not None:
            self.vlc_media.release()
        self.waiting_screen_visible = True
        path = pathlib.Path(__file__).parent.parent / "sample" / "waiting-screen.mp4"
        mrl = path.as_uri()
        logger.info("Loading waiting screen from MRL \"%s\"", mrl)
        assert self.vlc_instance is not None
        self.vlc_media = self.vlc_instance.media_new(mrl)
        assert self.vlc_media_player is not None
        self._volume_before_waiting_screen = self.current_volume
        self.volume(int(self.current_volume * settings.WAITING_SCREEN_VOLUME_FACTOR))
        self.vlc_media_player.set_media(self.vlc_media)
        self.vlc_media_player.play()
        self._playback_begins = True

    def hide_waiting_screen(self):
        self.waiting_screen_visible = False
        self.volume(self._volume_before_waiting_screen)
        if self.vlc_media_player is not None:
            self.vlc_media_player.stop()
