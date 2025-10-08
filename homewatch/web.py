import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from selenium.webdriver import Firefox
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.remote.webelement import WebElement

from .settings import GECKODRIVER_PATH, EXTENSIONS_DIR

UBLOCK_RELEASES = "https://api.github.com/repos/gorhill/uBlock/releases/latest"


def infer_tag_name(path: Path) -> str:
    base = path.stem
    parts = base.split("uBlock0_")
    if len(parts) > 1:
        rest = parts[1]
        ver = rest.split(".firefox")[0]
        return ver
    raise ValueError(f"Could not find version of {path}")


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split(".")))


def ensure_latest_ublock() -> Path:

    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch last release info
    res = requests.get(UBLOCK_RELEASES)
    res.raise_for_status()
    data = res.json()
    tag_name = data.get("tag_name")
    assets = data.get("assets", [])
    online_info = None
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".firefox.signed.xpi") or name.endswith(".xpi"):
            online_info = {
                "tag": tag_name,
                "name": name,
                "url": asset.get("browser_download_url")
            }
            break
    if online_info is None:
        raise RuntimeError("Could not find a .xpi asset in latest release")

    # Fetch local info
    local_info = None
    for path in EXTENSIONS_DIR.glob("*.xpi"):
        local_info = {
            "path": path,
            "tag": infer_tag_name(path)
        }
        break

    # If needed, download latest release
    if local_info is None or parse_version(local_info["tag"]) < parse_version(online_info["tag"]):
        print(f"Downloading new version {online_info['tag']} → {online_info['url']}")
        r = requests.get(online_info["url"], stream=True)
        r.raise_for_status()
        local_path = EXTENSIONS_DIR / online_info["name"]
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if local_info is not None:
            os.remove(local_info["path"])
        local_info = {
            "path": local_path,
            "tag": online_info["tag"]
        }

    return local_info["path"]


class WebPlayer:
    """
    @see https://support.google.com/youtube/answer/7631406?hl=en
    @see https://www.maketecheasier.com/cheatsheet/twitch-keyboard-shortcuts/
    """

    def __init__(self):
        self.element: WebElement | None = None
        self.driver = Firefox(service=Service(GECKODRIVER_PATH.as_posix()))
        self.setup()

    @property
    def url(self) -> str:
        return self.driver.current_url

    @property
    def title(self) -> str:
        return self.driver.title
    
    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc

    def setup(self):
        xpi_path = ensure_latest_ublock()
        self.driver.install_addon(xpi_path)
        self.driver.get("https://www.youtube.com/favicon.ico")
        self.driver.add_cookie({
            "name": "SOCS",
            "value": "CAESEwgDEgk4MTM3OTEyOTAaAmZyIAEaBgiAx4HHBg",
            "path": "/",
        })
        self.driver.get("about:blank")

    def load(self, url):
        self.driver.get(url)
        self.element = self.driver.find_element(By.TAG_NAME, "body")

    def toggle_play_pause(self):
        """Works on YouTube and Twitch
        """
        assert self.element is not None
        self.element.send_keys("k")

    def toggle_fullscreen(self):
        """Works on YouTube and Twitch
        """
        assert self.element is not None
        self.element.send_keys("f")

    def toggle_mute(self):
        """Works on YouTube and Twitch
        """
        assert self.element is not None
        self.element.send_keys("m")

    def seek_backward(self):
        """Works on YouTube and Twitch (not same keys)
        """
        assert self.element is not None
        if "youtube" in self.domain:
            self.element.send_keys("j")
        else:
            self.element.send_keys(Keys.ARROW_LEFT)

    def seek_forward(self):
        """Works on YouTube and Twitch (not same keys)
        """
        assert self.element is not None
        if "youtube" in self.domain:
            self.element.send_keys("l")
        else:
            self.element.send_keys(Keys.ARROW_RIGHT)

    def increase_volume(self):
        """Works on YouTube and Twitch (not same keys)
        """
        assert self.element is not None
        if "twitch" in self.domain:
            ActionChains(self.driver)\
                .key_down(Keys.SHIFT)\
                .send_keys_to_element(self.element, Keys.ARROW_UP)\
                .key_up(Keys.SHIFT)\
                .perform()
        else:
            self.element.send_keys(Keys.ARROW_UP)

    def decrease_volume(self):
        """Works on YouTube and Twitch (not same keys)
        """
        assert self.element is not None
        if "twitch" in self.domain:
            ActionChains(self.driver)\
                .key_down(Keys.SHIFT)\
                .send_keys_to_element(self.element, Keys.ARROW_DOWN)\
                .key_up(Keys.SHIFT)\
                .perform()
        else:
            self.element.send_keys(Keys.ARROW_DOWN)

    def seek_beginning(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("0")
    
    def seek_1(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("1")
    
    def seek_2(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("2")
    
    def seek_3(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("3")
    
    def seek_4(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("4")
    
    def seek_5(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("5")
    
    def seek_6(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("6")
    
    def seek_7(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("7")
    
    def seek_8(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("8")
    
    def seek_9(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("9")

    def toggle_captions(self):
        """YouTube only
        """
        assert self.element is not None
        self.element.send_keys("c")

    def load_next(self):
        """YouTube only
        """
        assert self.element is not None
        ActionChains(self.driver)\
            .key_down(Keys.SHIFT)\
            .send_keys_to_element(self.element, "n")\
            .key_up(Keys.SHIFT)\
            .perform()
    
    def load_prev(self):
        """YouTube only
        """
        assert self.element is not None
        ActionChains(self.driver)\
            .key_down(Keys.SHIFT)\
            .send_keys_to_element(self.element, "n")\
            .key_up(Keys.SHIFT)\
            .perform()

    def close(self):
        self.driver.quit()
