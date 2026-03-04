"""Homewatch settings.
"""

import enum
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@enum.unique
class ChromecastGeneration(enum.Enum):
    NONE = 0
    GEN1 = 1
    GEN2 = 2
    GEN3 = 3
    ULTRA = 4
    GOOGLETV = 5
    NESTHUB = 6
    NESTHUBMAX = 7

LANGUAGE_CODES = {
    "fr": {"fr", "fre", "fra", "french"},
    "en": {"en", "eng", "english"},
}

LANGUAGE_FLAGS = {
    "fr": "🇫🇷",
    "en": "🇬🇧",
}


def sget(
        data: dict,
        key: str,
        default: str | None = None,
        assert_in: list | None = None,
        empty_is_none: bool = False,
        none_is_default: bool = False):
    value = data.get(key, default)
    if assert_in and not (value in assert_in):
        raise ValueError(f"Invalid value for key '{key}': got '{value}', expected one of '{", ".join(map(str, assert_in))}'")
    if empty_is_none and value == "":
        value = None
    if none_is_default and value is None:
        value = default
    return value


def sget_str(*args, **kwargs) -> str:
    value = sget(*args, **kwargs)
    assert isinstance(value, str)
    return value


def sget_liststr(*args, **kwargs) -> list[str]:
    value = sget(*args, **kwargs)
    assert isinstance(value, list)
    for x in value:
        assert isinstance(x, str)
    return value


def sget_setstr(*args, **kwargs) -> set[str]:
    value = sget(*args, **kwargs)
    assert isinstance(value, list)
    for x in value:
        assert isinstance(x, str)
    return set(value)


def sget_bool(*args, **kwargs) -> bool:
    value = sget(*args, **kwargs)
    assert isinstance(value, bool)
    return value


def sget_int(*args, **kwargs) -> int:
    value = sget(*args, **kwargs)
    assert isinstance(value, int)
    return value


def sget_float(*args, **kwargs) -> float:
    value = sget(*args, **kwargs)
    assert isinstance(value, float)
    return value



@dataclass
class Settings:

    library_mode: Literal["local"] | Literal["remote"]
    library_root: str
    video_exts: set[str]
    subtitle_exts: set[str]
    playlist_exts: set[str]
    hidden_directory: str
    thumbnail_width: int
    thumbnail_height: int
    chromecast_generation: ChromecastGeneration
    mark_as_viewed_threshold_seconds: float
    mark_as_viewed_threshold_ratio: float

    server_mode: Literal["library"] | Literal["player"]

    home_url: str
    static_url: str
    media_url: str

    pre_hooks: list[str]
    post_hooks: list[str]

    vlc_dll_directory: str | None
    history_path: str
    status_path: str

    show_waiting_screen_at_startup: bool
    waiting_screen_volume: int

    default_autoplay: bool
    default_shuffle: bool
    default_loop: bool
    default_close_on_end: bool
    default_fastforward_seconds: int
    default_rewind_seconds: int
    default_subs_delay_step_milliseconds: int
    default_volume: int
    default_aspect_ratio: str | None
    preferred_media_language: str
    broadcast_time_delay_milliseconds: int

    geckodriver_path: Path
    firefox_path: Path
    addons_dir: Path

    @classmethod
    def from_file(cls, path: str | Path):
        with open(Path(__file__).parent.parent / "default.toml", "rb") as file:
            data = tomllib.load(file)
        with open(path, "rb") as file:
            data.update(tomllib.load(file))
        return cls(
            library_mode=sget(data, "library_mode", assert_in=["local", "remote"]), # type: ignore
            library_root=sget_str(data, "library_root"),
            video_exts=sget_setstr(data, "video_exts"),
            subtitle_exts=sget_setstr(data, "subtitle_exts"),
            playlist_exts=sget_setstr(data, "playlist_exts"),
            hidden_directory=sget_str(data, "hidden_directory"),
            thumbnail_width=sget_int(data, "thumbnail_width"),
            thumbnail_height=sget_int(data, "thumbnail_height"),
            chromecast_generation=ChromecastGeneration(sget_int(data, "chromecast_generation")),
            mark_as_viewed_threshold_seconds=sget_int(data, "mark_as_viewed_threshold_seconds"),
            mark_as_viewed_threshold_ratio=sget_float(data, "mark_as_viewed_threshold_ratio"),
            server_mode=sget(data, "server_mode", assert_in=["library", "player"]), # type: ignore
            home_url=sget_str(data, "home_url"),
            static_url=sget_str(data, "static_url"),
            media_url=sget_str(data, "media_url"),
            pre_hooks=sget_liststr(data, "pre_hooks"),
            post_hooks=sget_liststr(data, "post_hooks"),
            vlc_dll_directory=sget(data, "vlc_dll_directory", empty_is_none=True),
            history_path=sget_str(data, "history_path"),
            status_path=sget_str(data, "status_path"),
            show_waiting_screen_at_startup=sget_bool(data, "show_waiting_screen_at_startup"),
            waiting_screen_volume=sget_int(data, "waiting_screen_volume"),
            default_autoplay=sget_bool(data, "default_autoplay"),
            default_shuffle=sget_bool(data, "default_shuffle"),
            default_loop=sget_bool(data, "default_loop"),
            default_close_on_end=sget_bool(data, "default_close_on_end"),
            default_fastforward_seconds=sget_int(data, "default_fastforward_seconds"),
            default_rewind_seconds=sget_int(data, "default_rewind_seconds"),
            default_subs_delay_step_milliseconds=sget_int(data, "default_subs_delay_step_milliseconds"),
            default_volume=sget_int(data, "default_volume"),
            default_aspect_ratio=sget(data, "default_aspect_ratio", empty_is_none=True),
            preferred_media_language=sget(data, "preferred_media_language", assert_in=["fr", "en"]), # type: ignore
            broadcast_time_delay_milliseconds=sget_int(data, "broadcast_time_delay_milliseconds"),
            geckodriver_path=Path(sget_str(data, "geckodriver_path", default="geckodriver.exe" if sys.platform == "win32" else "geckodriver", empty_is_none=True, none_is_default=True)),
            firefox_path=Path(sget_str(data, "firefox_path", default="C:\\Program Files\\Mozilla Firefox\\firefox.exe" if sys.platform == "win32" else "/usr/bin/firefox", empty_is_none=True, none_is_default=True)),
            addons_dir=Path(sget_str(data, "addons_dir")),
        )

    @property
    def preferred_media_language_codes(self) -> set[str]:
        return LANGUAGE_CODES[self.preferred_media_language]

    @property
    def preferred_media_language_flag(self) -> str:
        return LANGUAGE_FLAGS[self.preferred_media_language]
