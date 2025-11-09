import dataclasses
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import time
import unicodedata
import urllib.parse
import warnings

import tqdm
import requests

from . import settings


logger = logging.getLogger(__name__)


SUBTITLE_TRACK = 0
SUBTITLE_FILE = 1
SUBTITLE_LANG_PATTERN = re.compile(r"\.([a-z]{2,3})$")


def probe_video(path: pathlib.Path) -> dict:
    logger.info("Probing video at %s", path)
    probe_path = path.parent / settings.HIDDEN_DIRECTORY / (path.stem + ".probe.json")
    probe_path.parent.mkdir(exist_ok=True)
    if probe_path.is_file():
        with probe_path.open("r", encoding="utf8") as file:
            data = json.load(file)
        return data
    data = json.loads(subprocess.check_output([
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path]).decode())
    with probe_path.open("w", encoding="utf8") as file:
        json.dump(data, file)
    return data


def ffmpeg_timestamp(total_seconds:float) -> str:
    hours = int(total_seconds) // 3600
    minutes = (int(total_seconds) - 3600 * hours) // 60
    seconds = int(total_seconds) - 3600 * hours - 60 * minutes
    milliseconds = int(1000 * (total_seconds - int(total_seconds)))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
   

def extract_thumbnail(path: pathlib.Path, duration: float) -> pathlib.Path:
    logger.info("Extracting thumbnail of %s (duration is %f)", path, duration)
    thumbnail_path = path.parent / settings.HIDDEN_DIRECTORY / (path.stem + ".thumbnail.jpg")
    thumbnail_path.parent.mkdir(exist_ok=True)
    if thumbnail_path.is_file():
        return thumbnail_path.relative_to(path.parent)
    w = str(settings.THUMBNAIL_WIDTH)
    h = str(settings.THUMBNAIL_HEIGHT)
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-skip_frame", "nokey",
            "-ss", ffmpeg_timestamp(duration),
            "-i", path,
            "-frames:v", "1",
            "-q:v", "2",
            "-vf",
            f"scale='max({w},{h}*iw/ih)':'max({h},{w}*ih/iw)',crop={w}:{h}",
            str(thumbnail_path),
            "-y"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    _, err = process.communicate()
    if process.returncode != 0:
        logger.warning(f"\r\nAn error occured while extracting thumbnail for '{path}':\n    " + re.sub("\r?\n", "\n    ", err.decode().strip()))
        if duration > 0:
            logger.debug("Retrying with first frame")
            return extract_thumbnail(path, 0)
    if not thumbnail_path.is_file() and duration > 0:
        return extract_thumbnail(path, 0)
    return thumbnail_path.relative_to(path.parent)


class AudioSource:

    def __init__(self,
            index: int,
            language: str | None = None,
            title: str | None = None):
        self.index = index
        self.language = language
        self.title = title
    
    def to_dict(self) -> dict:
        return {
            "id": self.index,
            "lang": self.language,
            "title": self.title
        }
    
    @classmethod
    def from_dict(cls, d:dict):
        return cls(d["id"], d["lang"], d["title"])


class SubtitleSource:

    def __init__(self,
            source_type: int,
            language: str | None = None,
            title: str | None = None):
        self.type = source_type
        self.language = language
        self.title = title

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "lang": self.language,
            "title": self.title
        }
    
    @classmethod
    def from_dict(cls, d:dict):
        if d["type"] == SUBTITLE_TRACK:
            return SubtitleTrack(d["id"], d["lang"], d["title"])
        elif d["type"] == SUBTITLE_FILE:
            return SubtitleFile(d["basename"], d["lang"])
        raise ValueError(f"Unknown subtitle type {d['type']}")


class SubtitleTrack(SubtitleSource):

    def __init__(self,
            index: int,
            language: str | None = None,
            title: str | None = None):
        SubtitleSource.__init__(self, SUBTITLE_TRACK, language, title)
        self.index = index

    def to_dict(self) -> dict:
        d = SubtitleSource.to_dict(self)
        d["id"] = self.index
        return d
    

class SubtitleFile(SubtitleSource):

    def __init__(self, basename: str, language: str | None = None):
        SubtitleSource.__init__(self, SUBTITLE_FILE, language)
        self.basename = basename

    def to_dict(self) -> dict:
        d = SubtitleSource.to_dict(self)
        d["basename"] = self.basename
        return d


class LibraryEntry:

    def __init__(self, folder: "LibraryFolder", basename: str):
        self.folder = folder
        self.basename: str = basename


class Media(LibraryEntry):

    PATTERN_DIRECTOR = re.compile(r'\(([^\(]+)\) *$')
    PATTERN_EPISODE = re.compile(r'^((\d+)\. |S(\d+)E(\d+) (?:- )?)')

    def __init__(self,
            folder: "LibraryFolder",
            basename: str,
            duration: float,
            video_codec: str | None = None,
            video_profile: int | None = None,
            video_level: str | None = None,
            audio_codec: str | None = None,
            audio_profile: str | None = None,
            resolution: int | None = None,
            framerate: int | None = None,
            thumbnail: str | None = None,
            audio_sources: list[AudioSource] = [],
            subtitle_sources: list[SubtitleSource] = []):
        LibraryEntry.__init__(self, folder, basename)
        self.duration = duration
        self.video_codec = video_codec
        self.video_profile = video_profile
        self.video_level = video_level
        self.audio_codec = audio_codec
        self.audio_profile = audio_profile
        self.resolution = resolution
        self.framerate = framerate
        self.thumbnail = thumbnail
        self.audio_sources = audio_sources
        self.subtitle_sources = subtitle_sources
        self.name = "Unnamed"
        self.ext = None
        self.title = None
        self.counter = None
        self.season = None
        self.episode = None
        self.director = None
        self.year = None
        self._extract_fields()
    
    def _extract_fields(self):
        split = os.path.splitext(self.basename)
        self.name = split[0]
        self.ext = split[1].lower()
        remainder = self.name
        rematch = self.PATTERN_DIRECTOR.search(remainder)
        if rematch is not None:
            remainder = remainder.replace(rematch.group(0), "").strip()
            elements = rematch.group(1).split(", ")
            for i, element in enumerate(elements):
                if re.match(r"^\d{4}$", element):
                    self.year = int(element)
                    elements.pop(i)
                    break
            elements = [s for s in elements if s]
            if elements:
                self.director = ", ".join(elements)
        rematch = self.PATTERN_EPISODE.search(remainder)
        if rematch is not None and rematch.group(1) is not None:
            remainder = remainder.replace(rematch.group(1), "").strip()
            if rematch.group(2) is not None:
                self.counter = int(rematch.group(2))
            else:
                self.season = int(rematch.group(3))
                self.episode = int(rematch.group(4))
        self.title = remainder

    def __str__(self) -> str:
        return f"<Media '{self.basename}'>"

    @property
    def path(self) -> pathlib.Path:
        return self.folder.path / self.basename
    
    @property
    def folder_index(self) -> int:
        index = self.folder.index(self)
        if index is None:
            raise ValueError(f"Could not find folder index of media {self.path}")
        return index

    @property
    def duration_display(self) -> str:
        hours = int(self.duration / 3600)
        minutes = int((self.duration - 3600 * hours) / 60)
        if hours == 0 and minutes == 0:
            return f"{round(self.duration)} s"
        elif hours == 0:
            return f"{minutes} min"
        else:
            return f"{hours}h{minutes:02d}"
        
    @property
    def has_preferred_language(self) -> bool:
        for source in self.audio_sources + self.subtitle_sources:
            if source.language in settings.PREFERRED_MEDIA_LANGUAGE_CODES:
                return True
        return False
    
    @property
    def duration_ms(self) -> int:
        return int(self.duration * 1000)

    @property
    def is_visible_in_browser(self) -> bool:
        return self.ext in [".mp4", ".webm", ".ogg"]
    
    @property
    def is_castable(self) -> bool:
        """
        @see https://developers.google.com/cast/docs/media
        """
        if settings.CHROMECAST_GENERATION is None:
            return False
        if self.audio_codec is not None and not (
            self.audio_codec in {"flac", "aac", "mp3", "opus", "vorbis", "wav", "webm"}):
            return False
        match settings.CHROMECAST_GENERATION:
            case settings.ChromecastGeneration.GEN1 | settings.ChromecastGeneration.GEN2:
                return (self.video_codec == "h264" and self.video_level <= 41)\
                    or (self.video_codec == "vp8" and (
                        (self.resolution <= 720 and self.framerate <= 60)
                        or
                        (self.resolution <= 1080 and self.framerate <= 30)
                    ))
            case settings.ChromecastGeneration.GEN3:
                return (self.video_codec == "h264" and self.video_level <= 42)\
                    or (self.video_codec == "vp8" and (
                        (self.resolution <= 720 and self.framerate <= 60)
                        or
                        (self.resolution <= 1080 and self.framerate <= 30)
                    ))
            case settings.ChromecastGeneration.ULTRA:
                return (self.video_codec == "h264" and self.video_level <= 42)\
                    or (self.video_codec == "vp8" and self.resolution <= 2160 and self.framerate <= 30)\
                    or (self.video_codec == "hevc" and self.video_level <= 51)\
                    or (self.video_codec == "vp9" and self.resolution <= 2160 and self.framerate <= 60)
            case settings.ChromecastGeneration.GOOGLETV:
                return (self.video_codec == "h264" and self.video_level <= 51)\
                    or (self.video_codec == "hevc" and self.video_level <= 51)\
                    or (self.video_codec == "vp9" and self.resolution <= 2160 and self.framerate <= 60)
            case settings.ChromecastGeneration.NESTHUB:
                return (self.video_codec == "h264" and self.video_level <= 41)\
                    or (self.video_codec == "vp9" and self.resolution <= 720 and self.framerate <= 60)
            case settings.ChromecastGeneration.NESTHUBMAX:
                return (self.video_codec == "h264" and self.video_level <= 41)\
                    or (self.video_codec == "vp9" and self.resolution <= 720 and self.framerate <= 30)
        return False

    @property
    def media_type_string(self) -> str:
        """
        @see https://developers.google.com/cast/docs/media
        """
        container = None
        match self.ext:
            case ".mp4":
                container = "video/mp4"
            case ".webm":
                container = "video/webm"
            case ".mkv":
                container = "video/x-matroska"
            case _:
                container = "video/mp4"
        video_codec = None
        match self.video_codec:
            case "h264":
                if self.video_level == 30 and self.video_profile == "Baseline":
                    video_codec = "avc1.42E01E"
                elif self.video_level == 31 and self.video_profile == "Baseline":
                    video_codec = "avc1.42E01F"
                elif self.video_level == 31 and self.video_profile == "Main":
                    video_codec = "avc1.4D401F"
                elif self.video_level == 40 and self.video_profile == "Main":
                    video_codec = "avc1.4D4028"
                elif self.video_level == 40 and self.video_profile == "High":
                    video_codec = "avc1.640028"
                elif self.video_level == 41 and self.video_profile == "High":
                    video_codec = "avc1.640029"
                elif self.video_level == 42 and self.video_profile == "High":
                    video_codec = "avc1.64002A"
            case "vp8" | "vp9":
                video_codec = self.video_codec
        if video_codec is None:
            video_codec = self.video_codec
        audio_codec = None
        match self.audio_codec:
            case "aac":
                if self.audio_profile == "HE":
                    audio_codec = "mp4a.40.5"
                elif self.audio_profile == "LC":
                    audio_codec = "mp4a.40.2"
            case "mp3":
                audio_codec = "mp4a.69"
        if audio_codec is None:
            audio_codec = self.audio_codec
        if video_codec is None and audio_codec is None:
            return container
        if audio_codec is None:
            return container + f'; codecs="{video_codec}"'
        if video_codec is None:
            return container + f'; codecs="{audio_codec}"'
        return container + f'; codecs="{video_codec}, {audio_codec}"'

    def to_dict(self) -> dict:
        return {
            "basename": self.basename,
            "duration": self.duration,
            "video_codec": self.video_codec,
            "video_profile": self.video_profile,
            "video_level": self.video_level,
            "audio_codec": self.audio_codec,
            "audio_profile": self.audio_profile,
            "resolution": self.resolution,
            "framerate": self.framerate,
            "thumbnail": str(self.thumbnail),
            "audio_sources": [s.to_dict() for s in self.audio_sources],
            "subtitle_sources": [s.to_dict() for s in self.subtitle_sources],
            "folder": self.folder.path.as_posix(),
        }
    
    def subtitle(self) -> str:
        elements = []
        if self.counter is not None:
            elements.append(f"#{self.counter}")
        if self.season is not None:
            elements.append(f"Saison {self.season}")
        if self.episode is not None:
            elements.append(f"Épisode {self.episode}")
        if self.director is not None:
            elements.append(self.director)
        if self.year is not None:
            elements.append(str(self.year))
        elements.append(self.duration_display)
        return " · ".join(elements)
    
    def to_fulldict(self) -> dict:
        base_dict = self.to_dict()
        if self.thumbnail is None:
            logger.warning("Media has no thumbnail: %s", self.path)
        base_dict.update(
            name=self.name,
            ext=self.ext,
            title=self.title,
            counter=self.counter,
            season=self.season,
            director=self.director,
            year=self.year,
            mediapath=self.path.as_posix(),
            thumbnail=None if self.thumbnail is None else pathlib.Path(self.thumbnail).as_posix(),
        )
        return base_dict

    def to_mindict(self) -> dict:
        if self.thumbnail is None:
            logger.warning("Media has no thumbnail: %s", self.path)
        return {
            "basename": self.basename,
            "title": self.title,
            "subtitle": self.subtitle(),
            "folder": self.folder.path.as_posix(),
            "thumbnail": None if self.thumbnail is None else pathlib.Path(self.thumbnail).as_posix(),
        }

    @classmethod
    def from_dict(cls, folder: "LibraryFolder", d:dict):
        return cls(
            folder,
            d["basename"],
            d["duration"],
            d["video_codec"],
            d["video_profile"],
            d["video_level"],
            d["audio_codec"],
            d["audio_profile"],
            d["resolution"],
            d["framerate"],
            d["thumbnail"],
            [AudioSource.from_dict(s) for s in d["audio_sources"]],
            [SubtitleSource.from_dict(s) for s in d["subtitle_sources"]]
        )

    @classmethod
    def from_path(cls, folder: "LibraryFolder", path: pathlib.Path):
        logger.debug("Analyzing media at %s", path)
        probe = probe_video(path)
        media = cls(folder, path.name, float(probe["format"]["duration"]))
        for stream in probe["streams"]:
            match stream["codec_type"]:
                case "video":
                    media.video_codec = stream.get("codec_name")
                    media.video_profile = stream.get("profile")
                    media.video_level = int(stream.get("level", 0))
                    # consider vertical videos rotated
                    media.resolution = min(stream.get("width", 0), stream.get("height", 0))
                    fps = tuple(map(float, stream.get("avg_frame_rate", "0/1").split("/")))
                    if fps[1] == 0:
                        media.framerate = round(fps[0])
                    else:
                        media.framerate = round(fps[0] / fps[1])
                case "audio":
                    media.audio_codec = stream.get("codec_name")
                    media.audio_profile = stream.get("profile")
                    tags = stream.get("tags", {})
                    media.audio_sources.append(AudioSource(
                        stream["index"],
                        tags.get("language"),
                        tags.get("title")
                    ))
                case "subtitle":
                    tags = stream.get("tags", {})
                    media.subtitle_sources.append(SubtitleTrack(
                        stream["index"],
                        tags.get("language"),
                        tags.get("title")
                    ))
        media.thumbnail = extract_thumbnail(path, media.duration / 2)
        return media


class Folder(LibraryEntry):

    NAME_PATTERN = re.compile(r'^([^\(]+)( \((.+)\))?$')

    def __init__(self,
            folder: "LibraryFolder",
            basename: str):
        LibraryEntry.__init__(self, folder, basename)
        self.title: str = "Untitled"
        self.subtitle: list[str] = []
        self._extract_fields()

    def _extract_fields(self):
        rematch = self.NAME_PATTERN.match(self.basename)
        if rematch is None:
            self.title = self.basename
        else:
            self.title = rematch.group(1)
            self.subtitle = []
            if rematch.group(3) is not None:
                for part in rematch.group(3).split(","):
                    if part.strip() != "":
                        self.subtitle.append(part.strip())
    
    def to_dict(self) -> dict:
        return {
            "basename": self.basename,
        }
    
    @classmethod
    def from_dict(cls, folder: "LibraryFolder", d: dict):
        return cls(folder, d["basename"])
    
    @classmethod
    def from_path(cls, folder: "LibraryFolder", path: str | pathlib.Path):
        logger.debug("Analyzing subfolder at %s", path)
        return cls(folder, os.path.basename(path))


class Playlist(LibraryEntry):

    def __init__(self,
            folder: "LibraryFolder",
            basename: str,
            elements: list[str] = []):
        LibraryEntry.__init__(self, folder, basename)
        self.elements: list[str] = elements
    
    @property
    def title(self) -> str:
        return os.path.splitext(self.basename)[0]
    
    @property
    def size(self) -> int:
        return len(self.elements)
    
    def to_dict(self) -> dict:
        return {
            "basename": self.basename,
            "elements": self.elements
        }
    
    @classmethod
    def from_dict(cls, folder: "LibraryFolder", d: dict):
        return cls(folder, d["basename"], d["elements"])

    @classmethod
    def from_path(cls, folder: "LibraryFolder", path: str | pathlib.Path):
        logger.debug("Analyzing playlist at %s", path)
        with open(path, "r", encoding="utf8") as file:
            elements = []
            for line in file.read().strip().split("\n"):
                if line.strip() != "":
                    elements.append(line.strip())
        return cls(folder, os.path.basename(path), elements)


class LibraryFolder:

    def __init__(
            self,
            path: pathlib.Path,
            medias: list[Media] = [],
            folders: list[Folder] = [],
            playlists: list[Playlist] = []):
        self.path = path
        self.medias = medias[:]
        self._media_index = { x.basename: x for x in self.medias }
        self.subfolders = folders[:]
        self._subfolders_index = { x.basename: x for x in self.subfolders }
        self.playlists = playlists[:]
        self._playlists_index = { x.basename: x for x in self.playlists }
    
    def index(self, media: Media) -> int | None:
        """Return index of media in media list.
        Returns None if media does not exist.
        """
        for i, target in enumerate(self.medias):
            if target.basename == media.basename:
                return i
        return None
    
    @property
    def name(self) -> str:
        return self.path.name

    @property
    def parent(self) -> pathlib.Path:
        return self.path.parent
    
    def add_media(self, media: Media):
        self.medias.append(media)
        self._media_index[media.basename] = media
    
    def get_media(self, basename: str) -> Media | None:
        return self._media_index.get(basename)
    
    def add_subfolder(self, folder: Folder):
        self.subfolders.append(folder)
        self._subfolders_index[folder.basename] = folder
    
    def get_subfolder(self, basename: str) -> Folder | None:
        return self._subfolders_index.get(basename)

    def add_playlist(self, playlist: Playlist):
        self.playlists.append(playlist)
        self._playlists_index[playlist.basename] = playlist
    
    def get_playlist(self, basename: str) -> Playlist | None:
        return self._playlists_index.get(basename)
    
    def sort(self):
        key = lambda x: "".join(
            c for c in unicodedata.normalize("NFD", x.basename)
            if unicodedata.category(c) != "Mn")
        self.medias.sort(key=key)
        self.subfolders.sort(key=key)
        self.playlists.sort(key=key)

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "medias": [x.to_dict() for x in self.medias],
            "subfolders": [x.to_dict() for x in self.subfolders],
            "playlists": [x.to_dict() for x in self.playlists],
        }

    @classmethod
    def from_scan(cls, root: str | pathlib.Path, path: pathlib.Path, quiet: bool = True):
        """
        @param document_root: library document root, 
        """
        folder = cls(path)
        if isinstance(root, str):
            root = pathlib.Path(root)
        fullpath = root / path
        if not fullpath.is_relative_to(root) or not fullpath.is_dir():
            logger.error("Could not scan library folder at %s", fullpath)
            return folder
        logger.info("Scanning library folder at %s", fullpath)
        try:
            _, dirs, files = next(os.walk(str(fullpath)))
        except StopIteration:
            return folder
        pbar = tqdm.tqdm(total=len(dirs) + len(files), disable=quiet)
        subtitle_paths: list[pathlib.Path] = []
        medias_names: dict[str, Media] = {}
        for dirname in dirs:
            pbar.set_description(dirname)
            pbar.update(1)
            if dirname == settings.HIDDEN_DIRECTORY:
                continue
            folder.add_subfolder(Folder.from_path(folder, dirname))
        for filename in files:
            pbar.set_description(filename)
            pbar.update(1)
            path = fullpath / filename
            ext = path.suffix.lower()
            if ext in settings.VIDEO_EXTS:
                media = Media.from_path(folder, path)
                medias_names[media.name] = media
                folder.add_media(media)
            elif ext in settings.SUBTITLE_EXTS:
                subtitle_paths.append(path)
            elif ext in settings.PLAYLIST_EXTS:
                folder.add_playlist(Playlist.from_path(folder, path))
        pbar.close()
        for path in subtitle_paths:
            name = path.stem
            lang_match = SUBTITLE_LANG_PATTERN.search(name)
            lang = None
            if lang_match is not None:
                name = SUBTITLE_LANG_PATTERN.sub("", name)
                lang = lang_match.group(1)
            if name not in medias_names:
                warnings.warn("Could not find media associated to subtitle file '%s'" % path)
                continue
            medias_names[name].subtitle_sources.append(SubtitleFile(path.name, lang))
        folder.sort()
        return folder
    
    @classmethod
    def from_url(cls, url: str):
        logger.info("Fetching library folder at %s", url)
        d = requests.get(url).json()
        return cls.from_dict(d)
    
    @classmethod
    def from_dict(cls, d: dict):
        folder = cls(pathlib.Path(d["path"]))
        for dd in d["medias"]:
            folder.add_media(Media.from_dict(folder, dd))
        for dd in d["subfolders"]:
            folder.add_subfolder(Folder.from_dict(folder, dd))
        for dd in d["playlists"]:
            folder.add_playlist(Playlist.from_dict(folder, dd))
        return folder
    
    @classmethod
    def from_file(cls, path: str):
        logger.info("Loading library folder at %s", path)
        with open(path, "r", encoding="utf8") as file:
            d = json.load(file)
        return cls.from_dict(d)
    
    @classmethod
    def from_settings(cls, path: pathlib.Path):
        if settings.LIBRARY_MODE == "local":
            return cls.from_scan(pathlib.Path(settings.LIBRARY_ROOT), path)
        elif settings.LIBRARY_MODE == "remote":
            url = urllib.parse.urljoin(settings.LIBRARY_ROOT, (path / "index.json").as_posix())
            return cls.from_url(url)
        raise ValueError(f"LIBRARY_MODE: {settings.LIBRARY_MODE}")


@dataclasses.dataclass
class HierarchyElement:
    path: str
    medias: int


class Hierarchy:

    def __init__(self, root: pathlib.Path, folders: list[HierarchyElement]):
        self.root = root
        self.folders: list[HierarchyElement] = folders

    def to_dict(self):
        return {
            "root": self.root.as_posix(),
            "folders": [
                {"path": f.path, "medias": f.medias}
                for f in self.folders
            ]
        }

    @classmethod
    def from_dict(cls, d: dict):
        folders = [
            HierarchyElement(dd["path"], dd["medias"])
            for dd in d["folders"]
        ]
        return cls(pathlib.Path(d["root"]), folders)
    
    @classmethod
    def from_scan(cls, root: pathlib.Path):
        logger.info("Exploring hierarchy at %s", root)
        folders = []
        f = lambda filename: os.path.splitext(filename)[1] in settings.VIDEO_EXTS
        for dirpath, _, files in os.walk(root):
            if os.path.basename(dirpath) == settings.HIDDEN_DIRECTORY:
                continue
            folders.append(HierarchyElement(
                pathlib.Path(dirpath).relative_to(root).as_posix(),
                len(list(filter(f, files)))))
        return cls(root, folders)
    
    @classmethod
    def from_url(cls, url: str):
        logger.info("Fetching hierarchy at %s", url)
        d = requests.get(url + "hierarchy.json").json()
        return cls.from_dict(d)

    @classmethod
    def from_settings(cls):
        if settings.LIBRARY_MODE == "local":
            return cls.from_scan(pathlib.Path(settings.LIBRARY_ROOT))
        elif settings.LIBRARY_MODE == "remote":
            return cls.from_url(settings.LIBRARY_ROOT)
        raise ValueError(f"LIBRARY_MODE: {settings.LIBRARY_MODE}")


def test_library_connection(max_retries: int = 3):
    if settings.LIBRARY_MODE == "local":
        return
    for attempt in range(max_retries):
        try:
            response = requests.get(settings.LIBRARY_ROOT + "alive")
            if response.status_code == 200:
                logger.info("Successfully connected to remote library")
                return
        except requests.exceptions.ConnectionError:
            pass
        logger.error("Could not connect to remote library, retrying in 1s (attempt %d)", attempt + 1)
        print("Remote library unreachable, retrying in 1s")
        time.sleep(1)
    logger.error("Could not connect to remote library. Maximum retries reached (%d). Exiting.", max_retries)
    print("Remote library unreachable, exiting")
    os._exit(1)


class Library(dict[str, LibraryFolder]):

    def __init__(self, root: str | pathlib.Path, folders: list[LibraryFolder] = []):
        self.root = root
        for folder in folders:
            self[folder.path.as_posix()] = folder

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "folders": [folder.to_dict() for folder in self.values()]
        }

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            pathlib.Path(d["root"]),
            [LibraryFolder.from_dict(dd) for dd in d["folders"]])
    
    @classmethod
    def from_scan(cls, root: pathlib.Path):
        logger.info("Scanning library at %s", root)
        if not root.is_dir():
            logger.error("Library root does not exist: %s", root)
            raise FileNotFoundError(str(root))
        library = cls(root)
        hierarchy = Hierarchy.from_settings()
        total = sum([folder.medias for folder in hierarchy.folders])
        pbar = tqdm.tqdm(total=total, desc="Scanning library", unit="media")
        for folder in hierarchy.folders:
            folder_path = pathlib.Path(folder.path)
            logger.debug("Adding folder to library: %s", folder_path)
            library_folder = LibraryFolder.from_scan(library.root, folder_path, True)
            library[folder_path.as_posix()] = library_folder
            pbar.update(folder.medias)
        pbar.close()
        return library

    @classmethod
    def from_url(cls, url: str):
        logger.info("Fetching library at %s", url)
        test_library_connection()
        library = cls(url)
        hierarchy = Hierarchy.from_settings()
        total = sum([folder.medias for folder in hierarchy.folders])
        pbar = tqdm.tqdm(total=total, desc="Fetching library", unit="media")
        for folder in hierarchy.folders:
            folder_path = pathlib.Path(folder.path)
            folder_url = urllib.parse.urljoin(url, (folder_path / "index.json").as_posix())
            library_folder = LibraryFolder.from_url(folder_url)
            library[folder_path.as_posix()] = library_folder
            pbar.update(folder.medias)
        pbar.close()
        return library
    
    @classmethod
    def from_settings(cls):
        if settings.LIBRARY_MODE == "local":
            return cls.from_scan(pathlib.Path(settings.LIBRARY_ROOT))
        elif settings.LIBRARY_MODE == "remote":
            return cls.from_url(settings.LIBRARY_ROOT)
        raise ValueError(f"LIBRARY_MODE: {settings.LIBRARY_MODE}")

    @staticmethod
    def clear_hidden_directories(top: pathlib.Path):
        logger.info("Clearing library at %s", top)
        for path in list(top.glob("**")):
            if path.is_dir() and path.name == settings.HIDDEN_DIRECTORY:
                logger.info("Deleting %s", path)
                shutil.rmtree(str(path))
    
    def get_media(self, path: pathlib.Path) -> Media | None:
        folder = self.get(path.parent.as_posix(), None)
        if folder is None:
            return None
        return folder.get_media(path.name)
    
    def get_media2(self, basename: str, folder: str) -> Media | None:
        return self.get_media(pathlib.Path(folder) / basename)
    
    def get_playlist(self, path: pathlib.Path) -> Playlist | None:
        folder = self.get(path.parent.as_posix(), None)
        if folder is None:
            return None
        return folder.get_playlist(path.name)

    def get_subfolder(self, parent: LibraryFolder, subfolder: Folder) -> LibraryFolder:
        return self[(parent.path / subfolder.basename).as_posix()]