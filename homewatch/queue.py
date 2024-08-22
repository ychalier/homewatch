"""Implementation of a media player queue. This offers features such as adding
elements for the future, shift elements from the future to the past, shuffling
and serialization.
"""

import logging
import random

from .library import Library, Media


logger = logging.getLogger(__name__)


class EmptyQueueException(Exception):
    pass


class StartOfQueueException(Exception):
    pass


class EndOfQueueException(Exception):
    pass


class Queue:
    """Generic Queue class. Elements can be added with the `.add` method. Call
    the `.next` method to load the next element. Elements can be accessed via
    their indices through brackets.
    """

    def __init__(self):
        self.elements: list[Media] = []
        self.ordering: list[int] = []
        self.current: int | None = None
        self.shuffle: bool = False
        self.loop: bool = True
    
    def to_dict(self) -> dict:
        return {
            "elements": [x.to_mindict() for x in self.elements],
            "ordering": self.ordering,
            "current": self.current,
            "shuffle": self.shuffle,
            "loop": self.loop,
        }
    
    def _ordered_elements(self) -> list[Media]:
        return [self.elements[i] for i in self.ordering]
    
    def __len__(self) -> int:
        return len(self.elements)

    def __str__(self):
        elements = list(map(str, self._ordered_elements()))
        if self.current is not None:
            elements[self.current] = f"*{elements[self.current]}"
        return "[" + ", ".join(elements) + "]"

    def __getitem__(self, key: int | slice) -> Media | list[Media]:
        self._ordered_elements()[key]

    def add(self, elements: list[Media], first_index: int | None = 0,
            clear_first: bool = True):
        logger.info("Adding %d elements, first_index is %s, clear_first is %s",
                    len(elements), first_index, clear_first)
        if clear_first:
            self.elements = []
            self.ordering = []
            self.current = None
        self.elements += elements
        i0 = len(self.ordering)
        new_ordering = list(range(i0, i0 + len(elements)))
        if self.shuffle:
            random.shuffle(new_ordering)
        if self.shuffle:
            if first_index is not None:
                new_ordering[new_ordering.index(i0 + first_index)] = new_ordering[0]
                new_ordering[0] = i0 + first_index
            self.current = i0
        elif first_index is not None:
            self.current = i0 + first_index
        else:
            self.current = i0
        self.ordering += new_ordering
    
    def append(self, elements: list[Media]):
        logger.info("Appending %d elements", len(elements))
        self.ordering += list(range(len(self.ordering), len(self.ordering) + len(elements)))
        self.elements += elements
            
    def set_shuffle(self, shuffle: bool):
        logger.info("Setting shuffle to %s", shuffle)
        self.shuffle = shuffle
        i = self.ordering[self.current]
        if self.shuffle:
            random.shuffle(self.ordering)
        else:
            self.ordering.sort()
        self.current = self.ordering.index(i)
    
    def doloop(self):
        logger.info("Looping the queue")
        self.current = 0
        if self.shuffle:
            random.shuffle(self.ordering)
        else:
            self.ordering.sort()

    def next(self):
        if self.current == len(self.elements) - 1 and self.loop:
            self.doloop()
        elif self.current < len(self.elements):
            self.current += 1
        else:
            raise EndOfQueueException()
        logger.info("Loading next element in queue, current is %s", self.current)

    def prev(self):
        if self.current > 0:
            self.current -= 1
        else:
            raise StartOfQueueException()
        logger.info("Loading previous element in queue, current is %s", self.current)
    
    @property
    def current_media(self) -> Media:
        return self.elements[self.ordering[self.current]]
    
    def jump_to(self, index: int):
        logger.info("Jumping to index %d", self.current)
        self.current = index

    def jump_to_media(self, media: Media):
        logger.info("Jumping to media at %s", media.path)
        j = None
        for i, target in enumerate(self.elements):
            if media.path == target.path:
                j = i
                break
        if j is not None:
            self.jump_to(self.ordering.index(j))

    @property
    def empty(self) -> bool:
        return not self.elements
    
    def get_status_dict(self) -> dict:
        return self.to_dict()
    
    def load_status_dict(self, status: dict, library: Library):
        self.elements = []
        for media_dict in status.get("elements", []):
            media = library.get_media2(media_dict["basename"], media_dict["folder"])
            if media is not None:
                self.elements.append(media)
        self.ordering = status.get("ordering", self.ordering)
        self.current = status.get("current", self.current)
        self.shuffle = status.get("shuffle", self.shuffle)
        self.loop = status.get("loop", self.loop)
