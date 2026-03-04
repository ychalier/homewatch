import argparse
import json
import logging
import os
import pathlib

from .library import Library
from .server import runserver
from .settings import Settings


def setup_logging(verbose: bool = False):
    BASE_DIR = pathlib.Path(__file__).parent.parent
    logger = logging.getLogger("homewatch")
    syslog = logging.FileHandler(filename=BASE_DIR / "homewatch.log", mode="a", encoding="utf8")
    syslog.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)-18s %(message)s"))
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(syslog)
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addHandler(syslog)


def build_sample_directory(full: bool):
    import requests, tqdm
    root = os.path.realpath("sample")
    target_files = [("waiting-screen.mp4", "https://drive.chalier.fr/protected/waiting-screen.mp4")]
    if full:
        target_files += [
            ("Big Buck Bunny (Blender Foundation, 2014).avi", "https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_480p_stereo.avi"),
            ("Sintel (Blender Foundation, 2010).mkv", "https://download.blender.org/durian/movies/Sintel.2010.720p.mkv"),
            ("Sintel (Blender Foundation, 2010).en.srt", "https://durian.blender.org/wp-content/content/subtitles/sintel_en.srt"),
            ("Sintel (Blender Foundation, 2010).fr.srt", "https://durian.blender.org/wp-content/content/subtitles/sintel_fr.srt"),
        ]
    for filename, url in target_files:
        path = os.path.join(root, filename)
        if os.path.isfile(path):
            continue
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, stream=True)
        response.raise_for_status()
        length = response.headers.get("content-length")
        pbar = tqdm.tqdm(total=int(length) if length is not None else None, unit="B", unit_divisor=1024, unit_scale=True)
        pbar.set_description(filename)
        with open(path, "wb") as file:
            for data in response.iter_content(chunk_size=4096):
                file.write(data)
                pbar.update(len(data))
        pbar.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--config", type=pathlib.Path, default=pathlib.Path("default.toml"))
    subparsers = parser.add_subparsers(dest="action")
    parser_scan = subparsers.add_parser("scan")
    parser_scan.add_argument("root", type=str)
    parser_scan.add_argument("--clear", action="store_true")
    parser_scan.add_argument("--output", type=str, default=None)
    parser_runserver = subparsers.add_parser("runserver")
    parser_runserver.add_argument("-d", "--debug", action="store_true")
    parser_runserver.add_argument("-q", "--qrcode", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    settings = Settings.from_file(args.config)
    build_sample_directory(settings.library_mode == "local" and settings.library_root == os.path.realpath("sample"))
    match args.action:
        case "scan":
            root = pathlib.Path(args.root)
            if args.clear:
                Library.clear_hidden_directories(root, settings.hidden_directory)
                return
            settings.library_root = root.as_posix()
            library = Library.from_scan(settings)
            if args.output is not None:
                with open(args.output, "w", encoding="utf8") as file:
                    json.dump(library.to_dict(), file, indent=4)
            else:
                print(json.dumps(library.to_dict()))
        case "runserver":
            runserver(settings, args.debug, args.qrcode)
