"""Homewatch settings.
Most imporant settings are LIBRARY_MODE, LIBRARY_ROOT, SERVER_MODE, and
VLC_DLL_DIRECTORY on Windows.
"""

import os

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
LIBRARY_ROOT = os.path.expanduser("~/Videos")

# Set of media file extensions (anything else will be ignored)
VIDEO_EXTS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm", ".wmv"}

# Set of subtitle file extensions (anything else will be ignored)
SUBTITLE_EXTS = {".srt", ".sub"}

# Set of playlist file extensions (anything else will be ignored)
PLAYLIST_EXTS = {".playlist"}

# Name of the folder containing video details and generated thumbnails
HIDDEN_DIRECTORY = ".homewatch"

# Generated thumbnail dimensions
THUMBNAIL_WIDTH = 200
THUMBNAIL_HEIGHT = 300

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

# Player default settings
PLAYER_FASTFORWARD_SECONDS = 30
PLAYER_REWIND_SECONDS = 30
PLAYER_DEFAULT_VOLUME = 50
PLAYER_DEFAULT_ASPECT_RATIO = None

# If a media file is available in one of those languages, the player will try
# to automatically select it. It first tries to set the subtitle track, to keep
# the original audio, but then tries setting the audio track if subtitles are
# not available in any preferred language. Note that this relies on audio and
# subtitle track metadata, which is often incomplete. 
PREFERRED_LANGUAGES = ["fr", "fre", "fra"]
