"""Remote media player, built on top of VLC.

Description: https://wiki.videolan.org/Python_bindings
API Documentation: https://www.olivieraubert.net/vlc/python-ctypes/doc/
CLI Documentation: https://wiki.videolan.org/VLC_command-line_help/
Requires `libvlc.dll` on Windows
"""

import logging
import os
import pathlib
import urllib.parse

from .library import Library, Media, SUBTITLE_TRACK, SUBTITLE_FILE
from . import settings

if settings.VLC_DLL_DIRECTORY is not None and os.path.isdir(settings.VLC_DLL_DIRECTORY):
    os.add_dll_directory(settings.VLC_DLL_DIRECTORY)
import vlc


logger = logging.getLogger(__name__)


class PlayerObserver:

    def on_media_changed(self, media_path: str):
        """
        @param media_path: path (relative to library root) to the loaded media
        """
        pass

    def on_time_changed(self, new_time: int):
        """
        @param time: new player time in milliseconds
        """
        pass
        
    def on_media_state_changed(self, new_state: int):
        pass


class Player:

    STATE_NOTHINGSPECIAL = 0
    STATE_OPENING = 1
    STATE_BUFFERING = 2
    STATE_PLAYING = 3
    STATE_PAUSED = 4
    STATE_STOPPED = 5
    STATE_ENDED = 6
    STATE_ERROR = 7

    def __init__(self,
                 fastforward_seconds: int = settings.PLAYER_FASTFORWARD_SECONDS,
                 rewind_seconds: int = settings.PLAYER_REWIND_SECONDS,
                 default_volume: int = settings.PLAYER_DEFAULT_VOLUME,
                 default_aspect_ratio: str | None = settings.PLAYER_DEFAULT_ASPECT_RATIO):
        self.observers: set[PlayerObserver] = set()
        self.fastforward_seconds: int = fastforward_seconds
        self.rewind_seconds: int = rewind_seconds
        self.default_volume: int = default_volume
        self.default_aspect_ratio: str | None = default_aspect_ratio
        self.media: Media | None = None
        self.vlc_instance: vlc.Instance | None = None
        self.vlc_media_player: vlc.MediaPlayer | None = None
        self.vlc_media: vlc.Media | None = None
        self.vlc_event_manager: vlc.EventManager | None = None
        self.selected_audio_source: int = 0
        self.selected_subtitle_source: int | None = None
        self.current_volume: int = self.default_volume
        self.current_aspect_ratio: str | None = self.default_aspect_ratio
        self._old_state = None
        self._waiting_to_play = False
        self._waiting_to_pause = False
        self._waiting_to_stop = False

    @property
    def media_path(self) -> str | None:
        if self.media is None:
            return None
        return self.media.path.as_posix()

    def mrl(self, basename: str) -> str:
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
        self.vlc_instance = vlc.Instance("--quiet")
        self.vlc_media_player = self.vlc_instance.media_player_new()
        self.vlc_event_manager = self.vlc_media_player.event_manager()
        self.vlc_media_player.set_fullscreen(1)
        self.volume(self.default_volume)
        self.aspect_ratio(self.default_aspect_ratio)
        self.attach_events()
    
    def attach_events(self):
        def on_time_changed(event, player):
            logger.debug("Event fired: time changed to %d", event.u.new_time)
            for observer in self.observers:
                observer.on_time_changed(event.u.new_time)
            if self._waiting_to_pause:
                logger.info("Player is playing _waiting_to_pause is True, toggling pause now")
                self._waiting_to_pause = False
                self.toggle_play_pause()
            if self._waiting_to_stop:
                logger.info("Player is playing _waiting_to_stop is True, stopping now")
                self._waiting_to_stop = False
                self.stop()
        self.vlc_event_manager.event_attach(
            vlc.EventType.MediaPlayerTimeChanged,
            on_time_changed,
            self.vlc_media_player
        )
        state_event_types = (
            vlc.EventType.MediaPlayerOpening,
            vlc.EventType.MediaPlayerBuffering,
            vlc.EventType.MediaPlayerPlaying,
            vlc.EventType.MediaPlayerPaused,
            vlc.EventType.MediaPlayerStopped,
            vlc.EventType.MediaPlayerEndReached,
        )
        for event_type in state_event_types:
            def callback(event, player):
                logger.info("Event fired: state changed to %s (old state is %s)", self.state, self._old_state)
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
            vlc.EventType.MediaPlayerMediaChanged,
            on_media_changed,
            self.vlc_media_player
        )
        def onbuffering(event, player):
            logger.debug("Event fired: media player is buffering, _waiting_to_play is %s", self._waiting_to_play)
            if self._waiting_to_play:
                self.vlc_media_player.play()
                self._waiting_to_play = False
        self.vlc_event_manager.event_attach(
            vlc.EventType.MediaPlayerBuffering,
            onbuffering,
            self.vlc_media_player
        )
    
    def auto_select_sources(self):
        found = False
        self.selected_audio_source = 0 if self.media.audio_sources else None
        self.selected_subtitle_source = None
        for i, source in enumerate(self.media.subtitle_sources):
            if source.language in settings.PREFERRED_MEDIA_LANGUAGE_CODES:
                self.selected_subtitle_source = i
                found = True
                break
        if not found:
            for i, source in enumerate(self.media.audio_sources):
                 if source.language in settings.PREFERRED_MEDIA_LANGUAGE_CODES:
                    self.selected_audio_source = i
                    break

    def load(self, media: Media, play: bool = False):
        logger.info("Loading media at %s", media.path)
        self.media = media
        self.auto_select_sources()
        self._waiting_to_play = play
        self.reload()
        if play:
            self.play()
        
    def reload(self):
        if self.vlc_media is not None:
            self.vlc_media.release()
        mrl = self.mrl(self.media.basename)
        logger.info("Loading media from MRL \"%s\"", mrl)
        self.vlc_media = self.vlc_instance.media_new(mrl)
        self.vlc_media_player.set_media(self.vlc_media)
        self.set_audio_source(self.selected_audio_source)
        self.set_subtitle_source(self.selected_subtitle_source)
        
    def play(self):
        logger.info("Triggering play")
        if self.vlc_media_player is not None:
            self.vlc_media_player.play()
        else:
            logger.error("Can not play, VLC media player is None")

    def toggle_play_pause(self):
        logger.info("Toggling pause")
        self.vlc_media_player.pause()
    
    def stop(self):
        logger.info("Stopping")
        self.vlc_media_player.stop()

    def seek(self, milliseconds: int):
        logger.info("Seeking to %d (ms)", milliseconds)
        self.vlc_media_player.set_time(milliseconds)

    def fastforward(self):
        logger.info("Fast forwarding %d seconds", self.fastforward_seconds)
        t = self.vlc_media_player.get_time()
        self.seek(t + 1000 * self.fastforward_seconds)
    
    def rewind(self):
        logger.info("Rewinding %d seconds", self.rewind_seconds)
        t = self.vlc_media_player.get_time()
        self.seek(t - 1000 * self.rewind_seconds)

    def volume(self, value: int):
        """
        @param value: ranges from 0 (muted) to 100 (loudest)
        """
        logger.info("Setting volume to %d", value)
        self.current_volume = value
        self.vlc_media_player.audio_set_volume(value)

    def aspect_ratio(self, value: str | None):
        """
        @param value: string of the form "width:height", or `None` to reset
        """
        logger.info("Setting aspect ratio to %s", value)
        self.current_aspect_ratio = value
        self.vlc_media_player.video_set_aspect_ratio(value)
    
    def set_audio_source(self, i: int | None):
        """
        @param i: audio track index
        """
        logger.info("Setting audio source to %s", i)
        self.selected_audio_source = i
        if i is None:
            return
        self.vlc_media_player.audio_set_track(self.media.audio_sources[i].index)

    def set_subtitle_source(self, i: int | None):
        """
        @param i: subtitle track index, or `None` to disable subtitles
        """
        logger.info("Setting subtitle source to %s", i)
        if i == -1:
            i = None
        self.selected_subtitle_source = i
        if i is None:
            self.vlc_media_player.video_set_spu(-1)
            return
        subtitle_source = self.media.subtitle_sources[i]
        if subtitle_source.type == SUBTITLE_TRACK:
            self.vlc_media_player.video_set_spu(subtitle_source.index)
        elif subtitle_source.type == SUBTITLE_FILE:
            uri = self.mrl(subtitle_source.basename)
            self.vlc_media_player.add_slave(vlc.MediaSlaveType.subtitle, uri, 1)

    def close(self):
        logger.info("Closing player")
        try:
            if self.vlc_media_player is not None:
                self.vlc_media_player.release()
        except OSError:
            pass
        try:
            if self.vlc_instance is not None:
                self.vlc_instance.release()
        except OSError:
            pass
    
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
            "selected_subtitle_source": self.selected_subtitle_source
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
        self.aspect_ratio(status.get("current_aspect_ratio", self.current_aspect_ratio))
