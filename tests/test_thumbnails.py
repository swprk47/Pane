"""Seek-bar thumbnails: the box maths, the cache (Task 2) and the provider with its hidden mpv (Task 3)."""
import pytest
from PySide6.QtGui import QImage

from core.thumbnails import ThumbnailCache, bucket_of, thumbnail_box


# --- box, bucket, cache (Task 2) ----------------------------------------------------------------

@pytest.mark.parametrize("aspect,expected", [
    (16 / 9, (160, 90)), (1.0, (90, 90)), (9 / 16, (90, 90)), (21 / 9, (160, 90)), (4 / 3, (120, 90)),
    (0, (160, 90)), (-1, (160, 90)), (float("nan"), (160, 90)),
])
def test_thumbnail_box_clamps_the_width(aspect, expected):
    assert thumbnail_box(aspect) == expected


@pytest.mark.parametrize("sec,b", [(0, 0), (1.99, 0), (2.0, 1), (3.5, 1), (125.3, 62), (-4, 0)])
def test_bucket_of_is_two_second_steps(sec, b):
    assert bucket_of(sec) == b


def _img():
    return QImage(2, 2, QImage.Format_RGB32)


def test_the_cache_keeps_the_most_recently_used_sixty():
    c = ThumbnailCache(limit=3)
    for i in range(3):
        c.put(("f", i), _img())
    assert c.get(("f", 0)) is not None                      # 0 is now the newest
    c.put(("f", 3), _img())
    assert c.get(("f", 1)) is None and c.get(("f", 0)) is not None and len(c) == 3
    c.clear()
    assert len(c) == 0
