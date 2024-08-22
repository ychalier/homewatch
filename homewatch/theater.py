import logging
import pathlib
import threading
import time

from .player import Player, PlayerObserver
from .history import History
from .library import Library, LibraryFolder, Media
from .queue import Queue, StartOfQueueException, EndOfQueueException


logger = logging.getLogger(__name__)


class Theater(PlayerObserver):

    def __init__(self):
        PlayerObserver.__init__(self)
        self.library: Library = Library.from_settings()
        self.player: Player = Player()
        self.history: History = History()
        self.queue: Queue = Queue()
        self.player.setup()
        self.player.bind_observer(self)
        self.autoplay = True
    
    def load_current(self):
        media = self.queue.current_media
        logger.info("Loading media at %s", media.path)
        self.player.load(media, play=True)

    def on_time_changed(self, new_time: int):
        if new_time is not None and new_time >= 0:
            self.history.update(self.queue.current_media, new_time)

    def on_media_state_changed(self, new_state: int):
        if new_state == Player.STATE_ENDED and self.autoplay:
            def callback():
                time.sleep(.1)
                logger.info("Autoplay is on, loading next media")
                self.load_next()
            threading.Thread(target=callback).start()
    
    def load_and_play(self, path: str, seek: int = 0, target: str = "media"):
        logger.info("Loading \"%s\" with target %s", path, target)
        if target == "media":
            media = self.library.get_media(pathlib.Path(path))
            self.queue.add(
                media.folder.medias[:],
                first_index=media.folder_index,
                clear_first=True)
        elif target == "next":
            media = self.library.get_media(pathlib.Path(path))
            self.queue.append([media])
            return
        elif target == "folder":
            library_folder = self.library[pathlib.Path(path).as_posix()]
            self.queue.add(library_folder.medias, None, True)
        elif target == "playlist":
            playlist = self.library.get_playlist(pathlib.Path(path))
            medias = [
                self.library.get_media(playlist.folder.path / item)
                for item in playlist.elements
            ]
            self.queue.add(medias, None)
        self.load_current()
        if seek > 0:
            self.player.seek(seek)
    
    def jump_to(self, i):
        logger.debug("Jumping in queue to %d", i)
        self.queue.jump_to(i)
        self.load_current()

    def load_prev(self):
        logger.info("Loading previous element")
        try:
            self.queue.prev()
            self.load_current()
        except StartOfQueueException:
            pass

    def load_next(self):
        logger.info("Loading next element")
        try:
            self.queue.next()
            self.load_current()
        except EndOfQueueException:
            pass
    
    def get_folder_progress(self, library_folder: LibraryFolder) -> tuple[int, int]:
        progress, duration = 0, 0
        for media in library_folder.medias:
            progress += self.history[media]
            duration += int(media.duration * 1000)
        for subfolder in library_folder.subfolders:
            library_subfolder = self.library.get_subfolder(library_folder, subfolder)
            subprogress, subduration = self.get_folder_progress(library_subfolder)
            progress += subprogress
            duration += subduration
        return progress, duration
        
    def set_folder_progress(self, library_folder: LibraryFolder):
        for media in library_folder.medias:
            media.progress = self.history[media]
        for subfolder in library_folder.subfolders:
            progress, duration = self.get_folder_progress(self.library.get_subfolder(library_folder, subfolder))
            subfolder.progress = progress
            subfolder.duration = duration

    def set_viewed_media(self, media: Media, viewed: bool):
        if viewed:
            self.history.update(media, media.duration_ms)
        else:
            self.history.update(media, 0)

    def set_viewed_folder(self, folder: LibraryFolder, viewed: bool):
        for media in folder.medias:
            self.set_viewed_media(media, viewed)
        for subfolder in folder.subfolders:
            lf = self.library.get_subfolder(folder, subfolder)
            self.set_viewed_folder(lf, viewed)

    def set_viewed_path(self, path: pathlib.Path, viewed: bool):
        logger.info("Setting viewed status of %s to %s", path, viewed)
        if path.as_posix() in self.library:
            logger.debug("Path %s is a folder", path)
            self.set_viewed_folder(self.library[path.as_posix()], viewed)
            return
        media = self.library.get_media(path)
        if media is None:
            logger.error("Path %s is neither a folder or a media", path)
            raise KeyError(path)
        logger.debug("Path %s is a media", path)
        self.set_viewed_media(media, viewed)

    def get_status_dict(self) -> dict:
        return {
            "autoplay": self.autoplay,
            "queue": self.queue.get_status_dict(),
            "player": self.player.get_status_dict()
        }
        