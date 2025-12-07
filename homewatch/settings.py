"""Homewatch settings.
Most imporant settings are LIBRARY_MODE, LIBRARY_ROOT, SERVER_MODE, and
VLC_DLL_DIRECTORY on Windows.
"""

import enum
import os
import sys
from pathlib import Path

# ====================== #
# Media library settings #
# ====================== #

# Library can either be 'local', ie. a local folder containing media files and
# subfolders, or 'remote', ie. it can fetched from another Homewatch server.
LIBRARY_MODE = "local"

# If the library mode is 'local', then this should be an absolute path to the
# root folder containing media files. If the library mode is 'remote', this
# should be the URL to the remote Homewatch server, ending with '/library/'
# (the trailing slash is important).
LIBRARY_ROOT = os.path.realpath("sample")

# Set of media file extensions (anything else will be ignored)
VIDEO_EXTS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm", ".wmv"}

# Set of subtitle file extensions (anything else will be ignored)
SUBTITLE_EXTS = {".srt", ".sub", ".ass"}

# Set of playlist file extensions (anything else will be ignored)
PLAYLIST_EXTS = {".playlist"}

# Name of the folder containing video details and generated thumbnails
HIDDEN_DIRECTORY = ".homewatch"

# Generated thumbnail dimensions
THUMBNAIL_WIDTH = 200
THUMBNAIL_HEIGHT = 300

# Chromecast settings, use to determine if a media can be casted or not.
# You must either specify None to disable Chromecast support, or one of the
# generation enumerated below:

@enum.unique
class ChromecastGeneration(enum.Enum):
    GEN1 = 1
    GEN2 = 2
    GEN3 = 3
    ULTRA = 4
    GOOGLETV = 5
    NESTHUB = 6
    NESTHUBMAX = 7

CHROMECAST_GENERATION = None

# Threshold for automatic detection of when a media or a folder is 'done',
# ie. it has been completely seen.
MARK_AS_VIEWED_THRESHOLD_SECONDS = 30
MARK_AS_VIEWED_THRESHOLD_RATIO = 0.98

# =============== #
# Server settings #
# =============== #

# Server can either be a 'library' and only serve the raw content and the
# library indexes, or a 'player', in which case it will link to VLC to control
# media playback.
SERVER_MODE = "player"

# URL settings
HOME_URL = "/"
STATIC_URL = "/static/"
MEDIA_URL = "/media/"

# Path to scripts (Bash, Powershell, …) that will be executed either just before
# the server starts (pre-hooks) or when the server closes (post-hooks). Paths
# can either be absolute or relative to the `hooks` folder.
PRE_HOOKS = []
POST_HOOKS = []

# =============== #
# Player settings #
# =============== #

# On Windows, one must specify the path to the VLC installation directory,
# eg. C:\Program Files\VideoLAN\VLC. This is not required on Linux, in which
# case the value can be None.
VLC_DLL_DIRECTORY = None

# Folder containing watch history
HISTORY_PATH = "history"

# File path to export theater status
STATUS_PATH = "status.json"

# Enable waiting screen at startup
SHOW_WAITING_SCREEN_AT_STARTUP = True

# Default settings
DEFAULT_AUTOPLAY = True
DEFAULT_SHUFFLE = False
DEFAULT_LOOP = True
DEFAULT_CLOSE_ON_END = False
DEFAULT_FASTFORWARD_SECONDS = 30
DEFAULT_REWIND_SECONDS = 30
DEFAULT_SUBS_DELAY_STEP_MILLISECONDS = 500
DEFAULT_VOLUME = 50
DEFAULT_ASPECT_RATIO = None

# Preferred media language, as a 2 letters ISO 639 code. Supported languages are
# reported below. This is used to provide library filtering and automatic
# subtitle and audio track selection.
PREFERRED_MEDIA_LANGUAGE = "fr"

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

# Delay between two time update message the websocket server has to wait for.
# Prevents self-DDOS when messages are fired too quickly, which may occur for
# some media files.
BROADCAST_TIME_DELAY_MILLISECONDS = 900

# =================== #
# Web Player settings #
# =================== #

# Path to geckodriver executable
# Download from https://github.com/mozilla/geckodriver/releases
GECKODRIVER_PATH = Path("geckodriver.exe") if sys.platform == "win32" else Path("geckodriver")

# Path to Firefox executable
FIREFOX_PATH = Path("C:/Program Files/Mozilla Firefox/firefox.exe") if sys.platform == "win32" else Path("/usr/bin/firefox")

# Web player will download and install Firefox extensions,
# and store them in this directory as .xpi file.
ADDONS_DIR = Path(".extensions")
