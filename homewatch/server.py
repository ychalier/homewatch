import asyncio
import json
import logging
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.parse

import jinja2
import qrcode
import websockets
import websockets.exceptions
import werkzeug
import werkzeug.middleware.shared_data
import werkzeug.serving

from .library import LibraryFolder, Hierarchy, Media
from .theater import Theater
from .player import Player, PlayerObserver
from .web import WebPlayer, WebPlayerObserver
from . import settings


logger = logging.getLogger(__name__)


BASEDIR = pathlib.Path(__file__).parent


def urljoin(base: str, *parts: str) -> str:
    if not parts:
        return base
    paths = [pathlib.Path(part) for part in parts]
    url = paths[0].joinpath(*paths[1:]).as_posix()
    return urllib.parse.urljoin(base, url)


def parse_qs(url: str) -> dict[str, None | str | list[str]]:
    query: dict[str, None | str | list[str]] = {}
    for key, value in urllib.parse.parse_qs(urllib.parse.urlparse(url)[4]).items():
        n = len(value)
        if n == 0:
            query[key] = None
        elif n == 1:
            query[key] = value[0]
        else:
            query[key] = value
    return query


def query_get(query: dict[str, None | str | list[str]], key: str, default: str) -> str:
    value = query.get(key)
    if value is None:
        return default
    if isinstance(value, list):
        return value[0]
    return value


class SleepWatcher(threading.Thread):

    PERIOD_SECONDS = 1

    def __init__(self, server: "WebsocketServer"):
        threading.Thread.__init__(self, daemon=True)
        self.server = server

    def run(self):
        while True:
            if self.server.sleep_at is not None and time.time() > self.server.sleep_at:
                logger.info("Server is going to sleep")
                self.server.close()
            time.sleep(self.PERIOD_SECONDS)


class WebsocketServer(threading.Thread, PlayerObserver, WebPlayerObserver):

    def __init__(self, server: "PlayerServer", hostname: str):
        threading.Thread.__init__(self, daemon=True)
        PlayerObserver.__init__(self)
        WebPlayerObserver.__init__(self)
        self.server = server
        self.host = hostname
        self.port = None
        self.connections = set()
        self.theater = self.server.theater
        self.player = self.server.theater.player
        self.close_on_end = settings.DEFAULT_CLOSE_ON_END
        self.sleep_at = None
        self.player.bind_observer(self)
        self.sleep_watcher = SleepWatcher(self)
        self.sleep_watcher.start()

    def on_time_changed(self, new_time: int):
        self._broadcast(f"TIME {new_time}")

    def on_media_changed(self, media_path: str | None):
        self._broadcast(f"MPTH {media_path}")

    def on_media_state_changed(self, new_state: int | None):
        self._broadcast(f"MSTT {new_state}")
        if new_state == Player.STATE_ENDED and self.close_on_end:
            self.close()

    def close(self):
        logger.info("Closing websocket server")
        self.server.close(hooks=True)

    def _broadcast(self, message: str):
        logger.debug("Broadcasting %s", message)
        websockets.broadcast(self.connections, message)

    def _on_client_message(self, websocket, message: str):
        logger.debug("Websocket %s \"%s\"", websocket.id.hex, message)
        if message == "PONG":
            return
        cmd, *args = message.split(" ")
        match cmd:
            case "PAUS":
                self.player.toggle_play_pause()
            case "PLAY":
                self.player.play()
            case "RPLY":
                self.player.reload()
                self.player.play()
            case "RWND":
                self.player.rewind()
            case "FFWD":
                self.player.fastforward()
            case "SLAT":
                self.player.subs_delay_later()
                self._broadcast(f"SDEL {self.player.current_subs_delay}")
            case "SEAR":
                self.player.subs_delay_earlier()
                self._broadcast(f"SDEL {self.player.current_subs_delay}")
            case "SRST":
                self.player.subs_delay_reset()
                self._broadcast(f"SDEL {self.player.current_subs_delay}")
            case "STOP":
                self.player.stop()
            case "VOLU":
                self.player.volume(int(args[0]))
            case "ASPR":
                self.player.aspect_ratio(args[0] if args[0] != "" else None)
            case "ASRC":
                self.player.set_audio_source(int(args[0]) if args[0] != "" else None)
            case "SSRC":
                self.player.set_subtitle_source(int(args[0]) if args[0] != "" else None)
            case "SEEK":
                self.player.seek(int(args[0]))
            case "PREV":
                self.theater.load_prev()
            case "NEXT":
                self.theater.load_next()
            case "AUTO":
                self.theater.autoplay = bool(int(args[0]))
            case "SHUF":
                self.theater.queue.set_shuffle(bool(int(args[0])))
            case "CLOS":
                self.close_on_end = bool(int(args[0]))
            case "SLEE":
                if int(args[0]) == 0:
                    self.sleep_at = None
                else:
                    self.sleep_at = int(args[0])
            case "JUMP":
                self.theater.jump_to(int(args[0]))
            case "MEDI":
                self._broadcast(f"MPTH {self.player.media_path}")
            case "WEB":
                self._on_client_message_web(websocket, args[0], args[1:])
        
    def _on_client_message_web(self, websocket, action: str, args: list[str]):
        if self.server.web_player is None:
            return
        if action == "close":
            self.server.web_player.close()
            self.server.web_player = None
        else:
            self.server.web_player.execute_action(action)
    
    def on_page_loaded(self, url: str, title: str, state: str):
        body = json.dumps({"url": url, "title": title, "state": state})
        self._broadcast(f"WEBLOAD {body}")
    
    def on_webplayer_closed(self):
        self._broadcast(f"WEBCLOS")

    def run(self):
        async def register(websocket):
            logger.debug("WebSocket client connected: %s", websocket.id.hex)
            self.connections.add(websocket)
            try:
                async for message in websocket:
                    try:
                        self._on_client_message(websocket, message)
                    except Exception as err:
                        logger.error(
                            "Error on client %s message \"%s\": %s",
                            websocket.id.hex,
                            message,
                            err)
            except websockets.exceptions.ConnectionClosedError:
                pass
            except ConnectionResetError:
                pass
            logger.debug("WebSocket client disconnected: %s", websocket.id.hex)
            self.connections.remove(websocket)
        async def start_server():
            async with websockets.serve(register, self.host, None) as wserver:
                for socket in wserver.sockets:
                    self.port = socket.getsockname()[1]
                    break
                logger.info("Starting websocket server at ws://%s:%d", self.host, self.port)
                await asyncio.Future()
        asyncio.run(start_server())


class LibraryServer:

    def __init__(self):
        self.jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader(BASEDIR / "templates"))
        self.jinja.globals.update(
            url=lambda *x: urljoin(settings.HOME_URL, *x),
            static=lambda *x: urljoin(settings.STATIC_URL, *x),
            media=lambda *x: urljoin(settings.MEDIA_URL, *x),
            media_url=settings.MEDIA_URL,
            playermode=settings.SERVER_MODE == "player",
            enable_chromecast=settings.CHROMECAST_GENERATION is not None,
            preferred_media_language_flag=settings.PREFERRED_MEDIA_LANGUAGE_FLAG,
            first_library_load=True,
        )

    def _get_landing_redirection_target(self) -> str:
        return "library"

    def _get_library_folder(self, relpath: pathlib.Path) -> LibraryFolder | None:
        return LibraryFolder.from_settings(relpath.parent if relpath.name in {"index.html", "index.json"} else relpath)

    def view_landing(self, request: werkzeug.Request) -> werkzeug.Response:
        return werkzeug.Response("Found", status=302, mimetype="text/plain", headers={
            "Location": urljoin(
            request.host_url + settings.HOME_URL,
            self._get_landing_redirection_target())
        })

    def view_player(self, request: werkzeug.Request) -> werkzeug.Response:
        return werkzeug.Response("Found", status=302, mimetype="text/plain", headers={
            "Location": urljoin( request.host_url + settings.HOME_URL, "library")
        })

    def view_basic(self, template_name, **kwargs) -> werkzeug.Response:
        template = self.jinja.get_template(template_name)
        text = template.render(**kwargs)
        return werkzeug.Response(text, status=200, mimetype="text/html")

    def view_about(self, request: werkzeug.Request) -> werkzeug.Response:
        return self.view_basic("about.html")

    def view_library(self, request: werkzeug.Request) -> werkzeug.Response | None:
        relpath = pathlib.Path(request.path[1:]).relative_to("library/")
        query = parse_qs(request.url)
        embedded = query.get("embedded") == "1"
        library_folder = self._get_library_folder(relpath)
        if library_folder is None:
            return None
        if relpath.name.endswith(".json"):
            text = json.dumps(library_folder.to_dict())
            return werkzeug.Response(text, status=200, mimetype="application/json")
        template = self.jinja.get_template("library.html")
        text = template.render(library=library_folder, embedded=embedded, subfolder_prefix="library")
        self.jinja.globals.update(first_library_load=False)
        return werkzeug.Response(text, status=200, mimetype="text/html")

    def dispatch_request(self, request: werkzeug.Request) -> werkzeug.Response | None:
        # TODO: enhance path resolution?
        path = pathlib.Path(request.path[1:])
        if str(path) == ".":
            return self.view_landing(request)
        elif str(path) == "alive":
            return werkzeug.Response("YES", status=200, mimetype="text/plain")
        elif str(path) == "about":
            return self.view_about(request)
        elif path.is_relative_to("library/"):
            if str(path.relative_to("library/")) == "hierarchy.json":
                hierarchy = Hierarchy.from_settings()
                text = json.dumps(hierarchy.to_dict())
                return werkzeug.Response(text, status=200, mimetype="application/json")
            return self.view_library(request)
        elif str(path) == "player":
            return self.view_player(request)
        return None

    def wsgi_app(self, environ, start_response):
        request = werkzeug.Request(environ)
        response = self.dispatch_request(request)
        if response is None:
            response = werkzeug.Response("404 Not Found", status=404, mimetype="text/plain")
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)


class PlayerServer(LibraryServer):

    def __init__(self, address: str):
        LibraryServer.__init__(self)
        self.theater = Theater()
        self.wss = WebsocketServer(self, address)
        self.wss.start()
        self.web_player: WebPlayer | None = None
        for hook_path in settings.PRE_HOOKS:
            execute_hook(hook_path)
        if settings.SHOW_WAITING_SCREEN_AT_STARTUP:
            self.theater.show_waiting_screen()

    def export_status(self) -> dict:
        data = self.theater.get_status_dict()
        if settings.STATUS_PATH:
            with open(settings.STATUS_PATH, "w") as file:
                json.dump(data, file)
        return data

    def read_status(self) -> dict | None:
        if settings.STATUS_PATH and os.path.isfile(settings.STATUS_PATH):
            logger.info("Loading status from %s", settings.STATUS_PATH)
            with open(settings.STATUS_PATH, "r") as file:
                status = json.load(file)
            return status
        return None

    def close(self, hooks: bool = True, restart: bool = False):
        logger.info("Closing server")
        self.export_status()
        self.theater.close()
        if hooks:
            for hook_path in settings.POST_HOOKS:
                execute_hook(hook_path)
        if restart:
            os._exit(42)
        else:
            os._exit(0)

    def _get_landing_redirection_target(self) -> str:
        return "player"

    def _get_library_folder(self, relpath: pathlib.Path) -> LibraryFolder | None:
        folder_path = relpath.parent if relpath.name in {"index.html", "index.json"} else relpath
        try:
            library_folder = self.theater.library[folder_path.as_posix()]
        except KeyError:
            return None
        self.theater.set_folder_progress(library_folder)
        return library_folder

    def view_player(self, request: werkzeug.Request):
        relpath = pathlib.Path(request.path[1:]).relative_to("player/")
        query = parse_qs(request.url)
        embedded = query.get("embedded") == "1"
        library_folder = self._get_library_folder(relpath)
        if library_folder is None:
            return werkzeug.Response("404 Not Found", status=404, mimetype="application/json")
        if relpath.name.endswith(".json"):
            text = json.dumps(library_folder.to_dict())
            return werkzeug.Response(text, status=200, mimetype="application/json")
        template = self.jinja.get_template("player.html")
        text = template.render(
            library=library_folder,
            embedded=embedded,
            wss_url=f"ws://{self.wss.host}:{self.wss.port}",
            subfolder_prefix="player")
        self.jinja.globals.update(first_library_load=False)
        return werkzeug.Response(text, status=200, mimetype="text/html")

    def view_web(self, request: werkzeug.Request) -> werkzeug.Response:
        if request.method == "POST":
            url = request.form.get("url")
            if url is None:
                return werkzeug.Response("400 Bad Request", status=400, mimetype="text/plain")
            self.theater.hide_waiting_screen()
            if self.web_player is None:
                self.web_player = WebPlayer()
                self.web_player.bind_observer(self.wss)
            self.web_player.load(url)
        template = self.jinja.get_template("web.html")
        text = template.render(
            player=self.web_player,
            wss_url=f"ws://{self.wss.host}:{self.wss.port}",)
        return werkzeug.Response(text, status=200, mimetype="text/html")

    def view_api_load(self, request: werkzeug.Request) -> werkzeug.Response:
        query = parse_qs(request.url)
        path = query_get(query, "path", "")
        target = query_get(query, "target", "media")
        queue_arg = query_get(query, "queue", "")
        queue_index = [int(x) for x in queue_arg.split(",") if x]
        seek = int(query_get(query, "seek", "0"))
        self.theater.load_and_play(path, seek, target, queue_index)
        if target == "next":
            self.wss._broadcast("QUEU")
        return werkzeug.Response("OK", status=204, mimetype="text/plain")
    
    def _media_from_query_path(self, query: dict[str, None | str | list[str]]) -> Media | None:
        path = query.get("path")
        if path is None:
            return None
        if isinstance(path, list):
            path = path[0]
        return self.theater.library.get_media(pathlib.Path(path))

    def view_api_history(self, request: werkzeug.Request) -> werkzeug.Response:
        if request.method == "GET":
            query = parse_qs(request.url)
            media = self._media_from_query_path(query)
            if media is None:
                return werkzeug.Response("404 Not Found", status=404, mimetype="text/plain")
            text = str(self.theater.history[media])
            return werkzeug.Response(text, status=200, mimetype="text/plain")
        elif request.method == "POST":
            query = parse_qs(request.url)
            path = query["path"]
            if path is None:
                return werkzeug.Response("400 Bad Request", status=400, mimetype="text/plain")
            if isinstance(path, list):
                path = path[0]
            viewed = query["viewed"] == "1"
            self.theater.set_viewed_path(pathlib.Path(path), viewed)
            return werkzeug.Response("OK", status=204, mimetype="text/plain")
        return werkzeug.Response("405 Method Not Allowed", status=405, mimetype="text/plain")

    def view_api_media(self, request: werkzeug.Request) -> werkzeug.Response:
        query = parse_qs(request.url)
        media = self._media_from_query_path(query)
        if media is None:
            return werkzeug.Response("404 Not Found", status=404, mimetype="text/plain")
        media_details = media.to_fulldict()
        text = json.dumps(media_details)
        return werkzeug.Response(text, status=200, mimetype="application/json")

    def view_api_player(self, request: werkzeug.Request) -> werkzeug.Response:
        data = {
            "mediaPath": self.theater.player.media_path,
            "state": self.theater.player.state,
            "time": self.theater.player.time,
            "audio": self.theater.player.selected_audio_source,
            "subs": self.theater.player.selected_subtitle_source,
            "volume": self.theater.player.current_volume,
            "subtitlesDelay": self.theater.player.current_subs_delay,
            "autoplay": self.theater.autoplay,
            "shuffle": self.theater.queue.shuffle,
            "closeOnEnd": self.wss.close_on_end,
            "sleepAt": self.wss.sleep_at,
            "aspectRatio": self.theater.player.current_aspect_ratio,
        }
        text = json.dumps(data)
        return werkzeug.Response(text, status=200, mimetype="application/json")

    def view_api_queue(self, request: werkzeug.Request) -> werkzeug.Response:
        data = self.theater.queue.to_dict()
        text = json.dumps(data)
        return werkzeug.Response(text, status=200, mimetype="application/json")

    def view_api_close(self, request: werkzeug.Request) -> werkzeug.Response:
        hooks = bool(int(query_get(parse_qs(request.url), "hooks", "0")))
        def callback():
            time.sleep(.1)
            self.close(hooks)
        threading.Thread(target=callback).start()
        return werkzeug.Response("OK", status=204, mimetype="text/plain")
    
    def view_api_restart(self, request: werkzeug.Request) -> werkzeug.Response:
        def callback():
            time.sleep(.1)
            self.close(False, True)
        threading.Thread(target=callback).start()
        return werkzeug.Response("OK", status=204, mimetype="text/plain")

    def view_api_read_status(self, request: werkzeug.Request) -> werkzeug.Response:
        status = self.read_status()
        text = json.dumps(status)
        return werkzeug.Response(text, status=200, mimetype="application/json")

    def view_api_load_status(self, request: werkzeug.Request) -> werkzeug.Response:
        status = self.read_status()
        if status is not None:
            self.theater.load_status_dict(status)
        return werkzeug.Response("OK", status=204, mimetype="text/plain")

    def view_api_export_status(self, request: werkzeug.Request) -> werkzeug.Response:
        data = self.export_status()
        text = json.dumps(data)
        return werkzeug.Response(text, status=200, mimetype="application/json")

    def view_api_wait(self, request: werkzeug.Request) -> werkzeug.Response:
        query = parse_qs(request.url)
        show = query.get("show", "0")
        if show == "0":
            self.theater.player.hide_waiting_screen()
        else:
            self.theater.player.show_waiting_screen()
        return werkzeug.Response("200 OK", status=200, mimetype="text/plain")

    def dispatch_request(self, request: werkzeug.Request) -> werkzeug.Response:
        response = super().dispatch_request(request)
        if response is not None:
            return response
        path = pathlib.Path(request.path[1:])
        path_posix = path.as_posix()
        if path.is_relative_to("player/"):
            return self.view_player(request)
        elif path_posix == "web":
            return self.view_web(request)
        elif path_posix == "api/load":
            return self.view_api_load(request)
        elif path_posix == "api/media":
            return self.view_api_media(request)
        elif path_posix == "api/player":
            return self.view_api_player(request)
        elif path_posix == "api/history":
            return self.view_api_history(request)
        elif path_posix == "api/queue":
            return self.view_api_queue(request)
        elif path_posix == "api/close":
            return self.view_api_close(request)
        elif path_posix == "api/restart":
            return self.view_api_restart(request)
        elif path_posix == "api/status/read":
            return self.view_api_read_status(request)
        elif path_posix == "api/status/load":
            return self.view_api_load_status(request)
        elif path_posix == "api/status/export":
            return self.view_api_export_status(request)
        elif path_posix == "api/wait":
            return self.view_api_wait(request)
        return werkzeug.Response("404 Not Found", status=404, mimetype="text/plain")


def create_app(hostname: str = "127.0.0.1", with_static: bool = True):
    if settings.SERVER_MODE == "library":
        app = LibraryServer()
    else:
        app = PlayerServer(hostname)
    logger.info("Created WSGI app %s", app.__class__.__name__)
    if with_static:
        app.wsgi_app = werkzeug.middleware.shared_data.SharedDataMiddleware(
            app.wsgi_app,
            {
                '/static': str(BASEDIR / "static"),
                '/media': str(pathlib.Path(settings.LIBRARY_ROOT)) if settings.LIBRARY_MODE == "local" else "",
            })
    return app


def execute_hook(path: str):
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = pathlib.Path(__file__).parent / "hooks" / p
    logger.info("Executing hook at %s", p)
    subprocess.run(str(p), shell=True, start_new_session=True)


def runserver(hostname: str = "127.0.0.1", port: int = 8000,
              debug: bool = False, show_qrcode: bool = False):
    app = create_app(hostname)
    logger.info("Starting Werkzeug development server at %s:%d", hostname, port)
    if show_qrcode:
        qr = qrcode.QRCode()
        qr.add_data(f"http://{hostname}:{port}")
        qr.print_ascii()
    print(f"Server is up at http://{hostname}:{port}, press ^C to quit")
    werkzeug.serving.run_simple(
        hostname, port,
        app,
        use_debugger=debug,
        use_reloader=debug)
