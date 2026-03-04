"""Homewatch settings.
Most imporant settings are LIBRARY_MODE, LIBRARY_ROOT, SERVER_MODE, and
VLC_DLL_DIRECTORY on Windows.
"""

import enum
import os
import sys
import tomllib
from pathlib import Path


@enum.unique
class ChromecastGeneration(enum.Enum):
    GEN1 = 1
    GEN2 = 2
    GEN3 = 3
    ULTRA = 4
    GOOGLETV = 5
    NESTHUB = 6
    NESTHUBMAX = 7


def sget(data: dict, key: str, default: str | None = None, assert_in: list | None = None):
    value = data.get(key, default)
    if assert_in and not (value in assert_in):
        raise ValueError(f"Invalid value for key '{key}': got '{value}', expected one of '{", ".join(map(str, assert_in))}'")
    return value


# TODO: variable path
with open("default.toml", "rb") as file:
    data = tomllib.load(file)


data_library = data.get("library", {})
LIBRARY_MODE = sget(data_library, "mode", assert_in=["local", "remote"])
LIBRARY_ROOT = sget(data_library, "root")
VIDEO_EXTS = set(sget(data_library, "video_exts"))
SUBTITLE_EXTS = set(sget(data_library, "subtitle_exts"))
PLAYLIST_EXTS = set(sget(data_library, "playlist_exts"))
HIDDEN_DIRECTORY = sget(data_library, "hidden_directory")
THUMBNAIL_WIDTH = sget(data_library, "thumbnail_width")
THUMBNAIL_HEIGHT = sget(data_library, "thumbnail_height")
chromecast_generation_value = sget(data_library, "chromecast_generation")
CHROMECAST_GENERATION = ChromecastGeneration(chromecast_generation_value) if chromecast_generation_value else None
MARK_AS_VIEWED_THRESHOLD_SECONDS = sget(data_library, "mark_as_viewed_threshold_seconds")
MARK_AS_VIEWED_THRESHOLD_RATIO = sget(data_library, "mark_as_viewed_threshold_ratio")

data_server = data.get("server", {})
SERVER_MODE = sget(data_server, "mode", assert_in=["library", "player"])

data_server_urls = data_server.get("urls", {})
HOME_URL = sget(data_server_urls, "home")
STATIC_URL = sget(data_server_urls, "static")
MEDIA_URL = sget(data_server_urls, "media")

data_server_hooks = data_server.get("hooks", {})
PRE_HOOKS = sget(data_server_hooks, "pre")
POST_HOOKS = sget(data_server_hooks, "post")

data_player = data.get("player", {})
VLC_DLL_DIRECTORY = sget(data_player, "vlc_dll_directory")
HISTORY_PATH = sget(data_player, "history_path")
STATUS_PATH = sget(data_player, "status_path")
SHOW_WAITING_SCREEN_AT_STARTUP = sget(data_player, "show_waiting_screen_at_startup")
WAITING_SCREEN_VOLUME = sget(data_player, "waiting_screen_volume")

data_player_video = data_player.get("video", {})
DEFAULT_AUTOPLAY = sget(data_player_video, "autoplay")
DEFAULT_SHUFFLE = sget(data_player_video, "shuffle")
DEFAULT_LOOP = sget(data_player_video, "loop")
DEFAULT_CLOSE_ON_END = sget(data_player_video, "close_on_end")
DEFAULT_FASTFORWARD_SECONDS = sget(data_player_video, "fastforward_seconds")
DEFAULT_REWIND_SECONDS = sget(data_player_video, "rewind_seconds")
DEFAULT_SUBS_DELAY_STEP_MILLISECONDS = sget(data_player_video, "subs_delay_step_milliseconds")
DEFAULT_VOLUME = sget(data_player_video, "volume")
DEFAULT_ASPECT_RATIO = sget(data_player_video, "aspect_ratio")
# TODO: parse None?

PREFERRED_MEDIA_LANGUAGE = sget(data_player_video, "preferred_media_language")

LANGUAGE_CODES = {
    "fr": {"fr", "fre", "fra", "french"},
    "en": {"en", "eng", "english"},
}
LANGUAGE_FLAGS = {
    "fr": "🇫🇷",
    "en": "🇬🇧",
}
PREFERRED_MEDIA_LANGUAGE_CODES = LANGUAGE_CODES[PREFERRED_MEDIA_LANGUAGE]
PREFERRED_MEDIA_LANGUAGE_FLAG = LANGUAGE_FLAGS[PREFERRED_MEDIA_LANGUAGE]

BROADCAST_TIME_DELAY_MILLISECONDS = sget(data_player_video, "broadcast_time_delay_milliseconds")

data_player_web = data_player.get("web", {})
geckodriver_path_value = sget(data_player_web, "geckodriver_path")
GECKODRIVER_PATH = Path(geckodriver_path_value) if geckodriver_path_value else (Path("geckodriver.exe") if sys.platform == "win32" else Path("geckodriver"))
firefox_path_value = sget(data_player_web, "firefox_path")
FIREFOX_PATH = Path(firefox_path_value) if firefox_path_value else (Path("C:/Program Files/Mozilla Firefox/firefox.exe") if sys.platform == "win32" else Path("/usr/bin/firefox"))
ADDONS_DIR = Path(sget(data_player_web, "addons_dir"))
