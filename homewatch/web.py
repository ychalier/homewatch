import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

import bs4
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


ADDON_URL_TEMPLATE = "https://addons.mozilla.org/firefox/addon/{name}/"
ADDONS = (
    "ublock-origin",
    "sponsorblock",
    "youtube-no-translation",
    "1-click-quality-for-twitch"
)

logger = logging.getLogger(__name__)


def parse_tag(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split(".")))


def update_addons() -> list[Path]:
    ADDONS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in ADDONS:
        response = requests.get(ADDON_URL_TEMPLATE.format(name=name))
        response.raise_for_status()
        soup = bs4.BeautifulSoup(response.text, features="html.parser")
        metadata_script = soup.find("script", {"type": "application/ld+json"})
        if metadata_script is None:
            raise RuntimeError(f"Could not find metadata tag for addon {name}")
        metadata = json.loads(metadata_script.text)
        online_tag = metadata["version"]
        install_button = soup.find("a", {"class": "InstallButtonWrapper-download-link"})
        if install_button is None:
            raise RuntimeError(f"Could not find install button for addon {name}")
        url = install_button["href"]
        if isinstance(url, list):
            url = url[0]
        path = None
        local_tag = None
        for cpath in ADDONS_DIR.glob("*.xpi"):
            cname, ctag = cpath.stem.strip(".xpi").split("@")
            if cname == name:
                path = cpath
                local_tag = ctag
        if local_tag is None or parse_tag(local_tag) < parse_tag(online_tag):
            logger.debug(f"Fetching {name}@{online_tag}")
            r = requests.get(url, stream=True)
            r.raise_for_status()
            if path is not None:
                os.remove(path)
            path = ADDONS_DIR / f"{name}@{online_tag}.xpi"
            with path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        paths.append(path)
    return paths


def close_extension_welcome_tabs(driver: Firefox, tabs_to_close: int, timeout: float = 10):
    """
    Wait for new window handles to appear and close any that look like
    extension welcome pages.

    - driver: Selenium WebDriver (Firefox)
    - original_handles: set/list of handles present BEFORE install (if None, captured automatically)
    - timeout: seconds to wait for new tab(s) to appear and settle
    - close_all_new: if True, close ALL new handles (dangerous if you expect other windows)
    Returns: list of tuples (handle, url, title) that were closed
    """
    original_handles = list(driver.window_handles)[:1]
    end = time.time() + timeout
    count = 0
    while time.time() < end and count < tabs_to_close:
        for handle in set(driver.window_handles):
            if handle in original_handles:
                continue
            try:
                driver.switch_to.window(handle)
            except WebDriverException as err:
                print(err)
                continue
            try:
                WebDriverWait(driver, 5).until(lambda d: d.execute_script("return document.readyState") == "complete")
            except Exception as err:
                print(err)
            try:
                driver.close()
                count += 1
            except WebDriverException as err:
                print(err)
        time.sleep(0.15)
    target = None
    for handle in set(driver.window_handles):
        if handle in original_handles:
            target = handle
            break
    if target is None:
        for handle in set(driver.window_handles):
            target = handle
            break
    try:
        if target is not None:
            driver.switch_to.window(target)
    except WebDriverException:
        pass


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


class WebPlayerObserver:
    
    def on_page_loaded(self, url: str, title: str, state: str):
        pass
    
    def on_webplayer_closed(self):
        pass


class WebPlayer:
    """
    @see https://support.google.com/youtube/answer/7631406?hl=en
    @see https://www.maketecheasier.com/cheatsheet/twitch-keyboard-shortcuts/
    """

    def __init__(self, server_hostname: str, server_port: int):
        self.server_hostname = server_hostname
        self.server_port = server_port
        self.observers: set[WebPlayerObserver] = set()
        self.element: WebElement | None = None
        options = Options()
        options.binary_location = FIREFOX_PATH.as_posix()
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        options.set_preference("media.autoplay.default", 0)
        options.set_preference("media.autoplay.blocking_policy", 0)
        service = Service(GECKODRIVER_PATH.as_posix())
        self.driver = Firefox(options, service)
        self.state: str = "off"
        self.setup()

    @property
    def url(self) -> str:
        return self.driver.current_url

    @property
    def title(self) -> str:
        return self.driver.title

    def setup(self):
        for xpi_path in update_addons():
            self.driver.install_addon(xpi_path, temporary=True)
        close_extension_welcome_tabs(self.driver, 2)
        self.driver.switch_to.window(self.driver.window_handles[0])
        self.driver.get("https://www.youtube.com/favicon.ico")
        self.driver.add_cookie({
            "name": "SOCS",
            "value": "CAESEwgDEgk4MTM3OTEyOTAaAmZyIAEaBgiAx4HHBg",
            "path": "/",
        })
        self.driver.get("about:blank")

    def load(self, url):
        logger.info("Loading %s", url)
        yt_video_id = extract_youtube_id(url)
        if yt_video_id is not None:
            url = f"https://www.youtube.com/embed/{yt_video_id}?autoplay=1"
            self.driver.get(f"http://{self.server_hostname}:{self.server_port}/youtube?" + urlencode({"url": url}))
        else:
            self.driver.get(url)
        try:
            WebDriverWait(self.driver, 5).until(lambda d: d.execute_script("return document.readyState") == "complete")
        except TimeoutException:
            pass
        domain = urlparse(self.url).netloc
        if "youtu" in domain or self.server_hostname in domain:
            self.state = "youtube"
            iframe = self.driver.find_element(By.TAG_NAME, "iframe")
            self.driver.switch_to.frame(iframe)
            self.element = self.driver.find_element(By.TAG_NAME, "body")
            self.click_at_center()
            self.click_at_center()
        elif "twitch" in domain:
            self.state = "twitch"
            self.element = self.driver.find_element(By.TAG_NAME, "body")
        else:
            raise NotImplementedError(f"Domain not supported {domain}")
        for observer in self.observers:
            observer.on_page_loaded(self.url, self.title, self.state)

    def click_at_center(self):
        size = self.driver.get_window_size()
        width = size["width"]
        height = size["height"]
        ActionChains(self.driver).move_by_offset(width/2, height/2).click().perform()
        ActionChains(self.driver).move_by_offset(-width/2, -height/2).perform()

    def execute_action(self, action: str, retry: bool = True):
        assert self.element is not None
        logger.debug("Executing action %s", action)
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
                if self.state == "twitch":
                    ActionChains(self.driver)\
                        .key_down(Keys.SHIFT)\
                        .send_keys_to_element(self.element, Keys.ARROW_UP)\
                        .key_up(Keys.SHIFT)\
                        .perform()
                else:
                    self.element.send_keys(Keys.ARROW_UP)
            elif action == "volume-down":
                if self.state == "twitch":
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
            elif action == "quality-480":
                for button in self.driver.find_elements(By.CSS_SELECTOR, "button.quality-button"):
                    if "480" in button.text:
                        button.click()
            elif action == "quality-720":
                for button in self.driver.find_elements(By.CSS_SELECTOR, "button.quality-button"):
                    if "720" in button.text:
                        button.click()
            elif action == "quality-1080":
                for button in self.driver.find_elements(By.CSS_SELECTOR, "button.quality-button"):
                    if "1080" in button.text:
                        button.click()
            elif action == "quality-auto":
                for button in self.driver.find_elements(By.CSS_SELECTOR, "button.quality-button"):
                    if "Auto" in button.text:
                        button.click()
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
        logger.info("Closing web player")
        self.driver.quit()
        for observer in self.observers:
            observer.on_webplayer_closed()
    
    def bind_observer(self, observer: WebPlayerObserver):
        logger.info("Binding observer %s", observer)
        self.observers.add(observer)
