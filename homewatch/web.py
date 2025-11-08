import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from selenium.webdriver import Firefox
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .settings import GECKODRIVER_PATH, FIREFOX_PATH, ADDONS_DIR

GITHUB_ADDONS = (
    ("uBlock", "gorhill"),
    ("SponsorBlock", "ajayyy"),
)

STATIC_ADDONS = (
    ("OriginalYouTubeAudio@1.2", "https://addons.mozilla.org/firefox/downloads/file/4411918/original_youtube_audio-1.2.xpi"),
)


def parse_tag(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split(".")))


def update_addons() -> list[Path]:
    ADDONS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, owner in GITHUB_ADDONS:
        response = requests.get(f"https://api.github.com/repos/{owner}/{name}/releases/latest")
        response.raise_for_status()
        data = response.json()
        online_tag = data["tag_name"]
        url = None
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith(".xpi"):
                url = asset["browser_download_url"]
                break
        if url is None:
            raise RuntimeError(f"Could not find a .xpi asset in the latest release of {owner}/{name}")
        path = None
        local_tag = None
        for cpath in ADDONS_DIR.glob("*.xpi"):
            cname, ctag = cpath.stem.strip(".xpi").split("@")
            if cname == name:
                path = cpath
                local_tag = ctag
        if local_tag is None or parse_tag(local_tag) < parse_tag(online_tag):
            print(f"Fetching {name}@{online_tag}")
            r = requests.get(url, stream=True)
            r.raise_for_status()
            if path is not None:
                os.remove(path)
            path = ADDONS_DIR / f"{name}@{online_tag}.xpi"
            with path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        paths.append(path)
    for name, url in STATIC_ADDONS:
        path = ADDONS_DIR / f"{name}.xpi"
        if not path.exists():
            print(f"Fetching {name}")
            r = requests.get(url, stream=True)
            r.raise_for_status()
            with path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        paths.append(path)
    return paths


def close_extension_welcome_tabs(driver: Firefox, original_handles=None, timeout=20, close_all_new=False):
    """
    Wait for new window handles to appear and close any that look like
    extension welcome pages.

    - driver: Selenium WebDriver (Firefox)
    - original_handles: set/list of handles present BEFORE install (if None, captured automatically)
    - timeout: seconds to wait for new tab(s) to appear and settle
    - close_all_new: if True, close ALL new handles (dangerous if you expect other windows)
    Returns: list of tuples (handle, url, title) that were closed
    """
    if original_handles is None:
        original_handles = set(driver.window_handles)
    else:
        original_handles = set(original_handles)
    end = time.time() + timeout
    closed = []
    while time.time() < end:
        current_handles = set(driver.window_handles)
        new_handles = list(current_handles - original_handles)
        if new_handles:
            for h in new_handles:
                try:
                    driver.switch_to.window(h)
                except WebDriverException:
                    continue
                try:
                    WebDriverWait(driver, 5).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except Exception:
                    pass
                url = ""
                title = ""
                try:
                    url = driver.current_url or ""
                except Exception:
                    url = ""
                try:
                    title = driver.title or ""
                except Exception:
                    title = ""
                probe = (url + " " + title).lower()
                is_welcome = (
                    "moz-extension://" in probe
                    or "sponsor" in probe
                    or "welcome" in probe
                    or "thank" in probe
                    or "get started" in probe
                    or "about:addons" in probe
                )
                if close_all_new or is_welcome:
                    try:
                        driver.close()
                        closed.append((h, url, title))
                    except WebDriverException:
                        pass
            break
        time.sleep(0.15)
    remaining = driver.window_handles
    if not remaining:
        return closed
    target = None
    for h in remaining:
        if h in original_handles:
            target = h
            break
    if target is None:
        target = remaining[0]
    try:
        driver.switch_to.window(target)
    except WebDriverException:
        pass
    return closed


def extract_youtube_id(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]
        match = re.match(r"^/(embed|shorts|live)/([^/?#&]+)", parsed.path)
        if match:
            return match.group(2)
    if parsed.hostname in ("youtu.be",):
        match = re.match(r"^/([^/?#&]+)", parsed.path)
        if match:
            return match.group(1)
    return None


class WebPlayer:
    """
    @see https://support.google.com/youtube/answer/7631406?hl=en
    @see https://www.maketecheasier.com/cheatsheet/twitch-keyboard-shortcuts/
    """

    def __init__(self):
        self.element: WebElement | None = None
        options = Options()
        options.binary_location = FIREFOX_PATH.as_posix()
        options.set_preference("media.autoplay.default", 0)
        options.set_preference("media.autoplay.blocking_policy", 0)
        service = Service(GECKODRIVER_PATH.as_posix())
        self.driver = Firefox(options, service)
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
        orig = set(self.driver.window_handles)
        for xpi_path in update_addons():
            self.driver.install_addon(xpi_path, temporary=True)
        close_extension_welcome_tabs(self.driver, original_handles=orig, timeout=10, close_all_new=False)
        self.driver.switch_to.window(self.driver.window_handles[0])
        self.driver.get("https://www.youtube.com/favicon.ico")
        self.driver.add_cookie({
            "name": "SOCS",
            "value": "CAESEwgDEgk4MTM3OTEyOTAaAmZyIAEaBgiAx4HHBg",
            "path": "/",
        })
        self.driver.get("about:blank")

    def load(self, url):
        yt_video_id = extract_youtube_id(url)
        if yt_video_id is not None:
            url = f"https://www.youtube.com/embed/{yt_video_id}"
        self.driver.get(url)
        try:
            WebDriverWait(self.driver, 5).until(lambda d: d.execute_script("return document.readyState") == "complete")
        except TimeoutException:
            pass
        self.element = self.driver.find_element(By.TAG_NAME, "body")
        if yt_video_id is not None:
            size = self.driver.get_window_size()
            width = size["width"]
            height = size["height"]
            ActionChains(self.driver).move_by_offset(width/2, height/2).click().perform()
            ActionChains(self.driver).move_by_offset(-width/2, -height/2).perform()
    
    def execute_action(self, action: str, retry: bool = True):
        assert self.element is not None
        try:
            if action == "play":
                self.element.send_keys("k")
            elif action == "fullscreen":
                self.element.send_keys("f")
            elif action == "mute":
                self.element.send_keys("m")
            elif action == "prev":
                ActionChains(self.driver)\
                    .key_down(Keys.SHIFT)\
                    .send_keys_to_element(self.element, "n")\
                    .key_up(Keys.SHIFT)\
                    .perform()
            elif action == "next":
                ActionChains(self.driver)\
                    .key_down(Keys.SHIFT)\
                    .send_keys_to_element(self.element, "n")\
                    .key_up(Keys.SHIFT)\
                    .perform()
            elif action == "rewind":
                self.element.send_keys(Keys.ARROW_LEFT)
            elif action == "fastforward":
                self.element.send_keys(Keys.ARROW_RIGHT)
            elif action == "volume-up":
                if "twitch" in self.domain:
                    ActionChains(self.driver)\
                        .key_down(Keys.SHIFT)\
                        .send_keys_to_element(self.element, Keys.ARROW_UP)\
                        .key_up(Keys.SHIFT)\
                        .perform()
                else:
                    self.element.send_keys(Keys.ARROW_UP)
            elif action == "volume-down":
                if "twitch" in self.domain:
                    ActionChains(self.driver)\
                        .key_down(Keys.SHIFT)\
                        .send_keys_to_element(self.element, Keys.ARROW_DOWN)\
                        .key_up(Keys.SHIFT)\
                        .perform()
                else:
                    self.element.send_keys(Keys.ARROW_DOWN)
            elif action == "home":
                self.element.send_keys("0")
            elif action == "seek-1":
                self.element.send_keys("1")
            elif action == "seek-2":
                self.element.send_keys("2")
            elif action == "seek-3":
                self.element.send_keys("3")
            elif action == "seek-4":
                self.element.send_keys("4")
            elif action == "seek-5":
                self.element.send_keys("5")
            elif action == "seek-6":
                self.element.send_keys("6")
            elif action == "seek-7":
                self.element.send_keys("7")
            elif action == "seek-8":
                self.element.send_keys("8")
            elif action == "seek-9":
                self.element.send_keys("9")
            elif action == "captions":
                self.element.send_keys("c")
            elif action == "refresh":
                self.driver.refresh()
                try:
                    WebDriverWait(self.driver, 5).until(lambda d: d.execute_script("return document.readyState") == "complete")
                except TimeoutException:
                    pass
                self.element = self.driver.find_element(By.TAG_NAME, "body")
        except StaleElementReferenceException as err:
            if retry:
                self.element = self.driver.find_element(By.TAG_NAME, "body")
                self.execute_action(action, retry=False)

    def close(self):
        self.driver.quit()
