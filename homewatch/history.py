import hashlib
import json
import logging
import os

from .library import Media
from .settings import HISTORY_PATH


logger = logging.getLogger(__name__)


class History:

    def __init__(self, path: str = HISTORY_PATH):
        self._path = path
        os.makedirs(self._path, exist_ok=True)
        self._data = {}
        self._load()
    
    def _hashstr(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()

    def _hash(self, key: Media) -> str:
        return self._hashstr(key.path.as_posix())
    
    def _load(self):
        self._data = {}
        for path in next(os.walk(self._path))[2]:
            with open(os.path.join(self._path, path), "r", encoding="utf8") as file:
                data = json.load(file)
            if not data:
                continue
            hashed_key = self._hashstr(list(data)[0])
            self._data[hashed_key] = data

    def __getitem__(self, key: Media) -> int:
        hashed_key = self._hash(key)
        return self._data.get(hashed_key, {}).get(key.path.as_posix(), 0)

    def _save(self, hashed_key: str):
        path = os.path.join(self._path, f"{hashed_key}.json")
        with open(path, "w", encoding="utf8") as file:
            json.dump(self._data[hashed_key], file)

    def update(self, key: Media, value: int):
        logger.debug("Setting %s to %d", key, value)
        hashed_key = self._hash(key)
        self._data.setdefault(hashed_key, {})
        self._data[hashed_key][key.path.as_posix()] = value
        self._save(hashed_key)

    def to_dict(self) -> dict:
        d1 = {}
        for d2 in self._data.values():
            d1.update(d2)
        return d1