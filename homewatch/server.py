import asyncio
import json
import logging
import os
import pathlib
import subprocess
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

from .library import LibraryFolder, Hierarchy
from .theater import Theater
from .player import Player, PlayerObserver
from . import settings


logger = logging.getLogger(__name__)


BASEDIR = pathlib.Path(__file__).parent


def urljoin(base: str, *parts: str) -> str:
    if not parts:
        return base
    paths = [pathlib.Path(part) for part in parts]
    url = paths[0].joinpath(*paths[1:]).as_posix()
    return urllib.parse.urljoin(base, url)


def parse_qs(url: str) -> dict:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url)[4])
    for key in query:
        n = len(query[key])
        if n == 0:
            query[key] = None
        elif n == 1:
            query[key] = query[key][0]
    return query


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


class WebsocketServer(threading.Thread, PlayerObserver):

    def __init__(self, server: "PlayerServer", hostname: str):
        threading.Thread.__init__(self, daemon=True)
        PlayerObserver.__init__(self)
        self.server = server
        self.host = hostname
        self.port = None
        self.connections = set()
        self.theater = self.server.theater
        self.player = self.server.theater.player
        self.close_on_end = False
        self.sleep_at = None
        self.player.bind_observer(self)
        self.sleep_watcher = SleepWatcher(self)
        self.sleep_watcher.start()
    
    def on_time_changed(self, new_time: int):
        self._broadcast(f"TIME {new_time}")
    
    def on_media_changed(self, media_path: str):
        self._broadcast(f"MPTH {media_path}")
    
    def on_media_state_changed(self, new_state: int):
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
                self.port = wserver.sockets[0].getsockname()[1]
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
        )
    
    def _get_landing_redirection_target(self) -> str:
        return "library"
    
    def _get_library_folder(self, relpath: pathlib.Path) -> LibraryFolder:
        return LibraryFolder.from_settings(relpath.parent if relpath.name in {"index.html", "index.json"} else relpath)
    
    def view_landing(self, request: werkzeug.Request):
        return werkzeug.Response("Found", status=302, mimetype="text/plain", headers={
            "Location": urljoin(
            request.host_url + settings.HOME_URL,
            self._get_landing_redirection_target())
        })
    
    def view_player(self, request: werkzeug.Request) -> werkzeug.Response:
        return werkzeug.Response("Found", status=302, mimetype="text/plain", headers={
            "Location": urljoin( request.host_url + settings.HOME_URL, "library")
        })
    
    def view_basic(self, template_name, **kwargs):
        template = self.jinja.get_template(template_name)
        text = template.render(**kwargs)
        return werkzeug.Response(text, status=200, mimetype="text/html")
    
    def view_about(self, request: werkzeug.Request):
        return self.view_basic("about.html")
    
    def view_library(self, request: werkzeug.Request):
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
        text = template.render(library=library_folder, embedded=embedded)
        return werkzeug.Response(text, status=200, mimetype="text/html")

    def dispatch_request(self, request: werkzeug.Request) -> werkzeug.Response:
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
        for hook_path in settings.PRE_HOOKS:
            execute_hook(hook_path)
        if settings.STATUS_PATH and os.path.isfile(settings.STATUS_PATH):
            logger.info("Loading status from %s", settings.STATUS_PATH)
            with open(settings.STATUS_PATH, "r") as file:
                status = json.load(file)
            self.theater.load_status_dict(status)

    def export_status(self) -> dict:
        data = self.theater.get_status_dict()
        if settings.STATUS_PATH:
            with open(settings.STATUS_PATH, "w") as file:
                json.dump(data, file)
        return data

    def close(self, hooks=True):
        logger.info("Closing server")
        self.export_status()
        if hooks:
            for hook_path in settings.POST_HOOKS:
                execute_hook(hook_path)
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
        return self.view_basic("player.html", wss_url=f"ws://{self.wss.host}:{self.wss.port}")

    def view_api_load(self, request: werkzeug.Request) -> werkzeug.Response:
        query = parse_qs(request.url)
        path = query.get("path", "")
        target = query.get("target", "media")
        seek = int(query.get("seek", 0))
        self.theater.load_and_play(path, seek, target)
        if target == "next":
            self.wss._broadcast("QUEU")
        return werkzeug.Response("OK", status=204, mimetype="text/plain")
    
    def view_api_history(self, request: werkzeug.Request) -> werkzeug.Response:
        if request.method == "GET":
            query = parse_qs(request.url)
            path = query["path"]
            text = str(self.theater.history[path])
            return werkzeug.Response(text, status=200, mimetype="text/plain")
        elif request.method == "POST":
            query = parse_qs(request.url)
            path = pathlib.Path(query["path"])
            viewed = query["viewed"] == "1"
            self.theater.set_viewed_path(path, viewed)
            return werkzeug.Response("OK", status=204, mimetype="text/plain")
        return  werkzeug.Response("405 Method Not Allowed", status=405, mimetype="text/plain")

    def view_api_media(self, request: werkzeug.Request) -> werkzeug.Response:
        path = parse_qs(request.url)["path"]
        media_details = self.theater.library.get_media(pathlib.Path(path)).to_fulldict()
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
        hooks = bool(int(parse_qs(request.url).get("hooks", 0)))
        def callback():
            time.sleep(.1)
            self.close(hooks)
        threading.Thread(target=callback).start()
        return werkzeug.Response("OK", status=204, mimetype="text/plain")
    
    def view_status(self, request: werkzeug.Request) -> werkzeug.Response:
        data = self.export_status()
        text = json.dumps(data)
        return werkzeug.Response(text, status=200, mimetype="application/json")
    
    def dispatch_request(self, request: werkzeug.Request) -> werkzeug.Response:
        response = super().dispatch_request(request)
        if response is not None:
            return response
        path = pathlib.Path(request.path[1:]).as_posix()
        if path == "player":
            return self.view_player(request)
        elif path == "api/load":
            return self.view_api_load(request)
        elif path == "api/media":
            return self.view_api_media(request)
        elif path == "api/player":
            return self.view_api_player(request)
        elif path == "api/history":
            return self.view_api_history(request)
        elif path == "api/queue":
            return self.view_api_queue(request)
        elif path == "api/close":
            return self.view_api_close(request)
        elif path == "status":
            return self.view_status(request)
        return None


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