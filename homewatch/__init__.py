import argparse
import json
import logging
import pathlib
import re

from .library import Library
from .server import runserver


def setup_logging(verbose: bool = False):
    BASE_DIR = pathlib.Path(__file__).parent.parent
    logger = logging.getLogger("homewatch")
    syslog = logging.FileHandler(filename=BASE_DIR / "homewatch.log", mode="w", encoding="utf8")
    syslog.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)-18s %(message)s"))
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(syslog)
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addHandler(syslog)


def parse_host_string(string: str, default_hostname: str = "127.0.0.1",
                      default_port: int = 8000) -> tuple[str, int]:
    if string is None:
        return default_hostname, default_port
    m = re.match(r"^(?:https?://)?([A-Za-z0-9\.]+)(?::(\d+))?$", string)
    hostname, port = default_hostname, default_port
    if m is not None:
        hostname = m.group(1)
        if m.group(2) is not None:
            port = int(m.group(2))
    return hostname, port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="action")
    parser_scan = subparsers.add_parser("scan")
    parser_scan.add_argument("root", type=str)
    parser_scan.add_argument("-c", "--clear", action="store_true")
    parser_scan.add_argument("-o", "--output_path", type=str, default=None)
    parser_runserver = subparsers.add_parser("runserver")
    parser_runserver.add_argument("host", type=str, default="127.0.0.1:8000", nargs="?")
    parser_runserver.add_argument("-d", "--debug", action="store_true")
    parser_runserver.add_argument("-q", "--qrcode", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    match args.action:
        case "scan":
            root = pathlib.Path(args.root)
            if args.clear:
                Library.clear(root)
                return
            library = Library.from_scan(root)
            if args.output_path is not None:
                with open(args.output_path, "w", encoding="utf8") as file:
                    json.dump(library.to_dict(), file, indent=4)
            else:
                print(json.dumps(library.to_dict()))
        case "runserver":
            hostname, port = parse_host_string(args.host)
            runserver(hostname, port, args.debug, args.qrcode)
