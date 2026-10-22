"""
Seek-bar thumbnails: the picture shown above the time when the pointer is over the seek bar.

Design: docs/superpowers/specs/2026-10-13-seekbar-thumbnails-design.md. This module has no widgets: the box maths, the
cache and the provider that makes pictures with a second, windowless mpv.
"""
import math
from collections import OrderedDict
from typing import Optional

from PySide6.QtGui import QImage

THUMB_H = 90                 # the picture's logical height
THUMB_MIN_W = 90             # and its logical width limits (the width follows the video's aspect ratio)
THUMB_MAX_W = 160
BUCKET_SECONDS = 2           # pictures are made and cached per 2 s of the video
CACHE_SIZE = 60              # per file, least recently used goes first


def thumbnail_box(aspect: float) -> tuple:
    """The logical (width, height) of the picture for a video of this aspect ratio: 90 px high, the width clamped to
    90..160 (a very wide or tall video is fitted inside with dark bars, never stretched). A bad aspect gives 160x90."""
    try:
        ok = math.isfinite(aspect) and aspect > 0
    except TypeError:
        ok = False
    if not ok:
        return THUMB_MAX_W, THUMB_H
    return max(THUMB_MIN_W, min(THUMB_MAX_W, round(THUMB_H * aspect))), THUMB_H


def bucket_of(seconds: float) -> int:
    """The 2 s step a time falls into (negative times count as 0)."""
    return int(max(0.0, seconds) // BUCKET_SECONDS)


class ThumbnailCache:
    """The most recently used pictures, keyed by (path, bucket)."""

    def __init__(self, limit: int = CACHE_SIZE):
        self._limit = limit
        self._items = OrderedDict()

    def get(self, key) -> Optional[QImage]:
        image = self._items.get(key)
        if image is not None:
            self._items.move_to_end(key)
        return image

    def put(self, key, image: QImage) -> None:
        self._items[key] = image
        self._items.move_to_end(key)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)
