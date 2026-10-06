"""
"Play the next video in this folder": the folder is the playlist.

Videos in the same folder as the open file are ordered by file name with a *natural* sort, so numbers
compare by value (``lecture2`` before ``lecture10``). Nothing is stored: the neighbours are looked up
from the folder each time, so files added or removed in between are picked up.
"""
import os
import re
from typing import List, Optional, Tuple

from core.media_types import VIDEO_EXTENSIONS

_DIGITS = re.compile(r"(\d+)")
_EXTENSIONS = frozenset(f".{e}" for e in VIDEO_EXTENSIONS)


def natural_key(name: str):
    """Sort key where digit runs compare as numbers and letters ignore case: lecture2 < lecture10."""
    parts = _DIGITS.split(name.casefold())
    # even positions are text, odd positions are digit runs; the ints go in a tuple so that a text/number
    # mismatch between two names never compares str with int
    return [(0, int(p), "") if i % 2 else (1, 0, p) for i, p in enumerate(parts)] + [(2, 0, name)]


def is_video(name: str) -> bool:
    return os.path.splitext(name)[1].casefold() in _EXTENSIONS


def folder_videos(path: str) -> List[str]:
    """Full paths of the videos next to ``path`` (including ``path`` itself), in playing order."""
    folder = os.path.dirname(os.path.abspath(path))
    here = os.path.basename(path)
    names = set()
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_file() and not entry.name.startswith(".") and is_video(entry.name):
                    names.add(entry.name)
    except OSError:
        pass
    if here.casefold() not in {n.casefold() for n in names}:   # (Windows file names ignore case)
        names.add(here)              # the open file counts even if its extension is not in the list
    return [os.path.join(folder, n) for n in sorted(names, key=natural_key)]


def neighbors(path: str) -> Tuple[Optional[str], Optional[str]]:
    """(previous, next) video of ``path`` in its folder; None at either end."""
    videos = folder_videos(path)
    here = os.path.normcase(os.path.abspath(path))
    for i, v in enumerate(videos):
        if os.path.normcase(v) == here:
            prev_ = videos[i - 1] if i > 0 else None
            next_ = videos[i + 1] if i + 1 < len(videos) else None
            return prev_, next_
    return None, None
