"""
Bookmarks (places of a video marked to look at again) and chapters (the file's own table of contents): the pure logic,
no widgets. Design: docs/superpowers/specs/2026-10-24-bookmarks-chapters-design.md.

A bookmark is a dict {"t": seconds, "name": str}; an empty name is shown as the time.
"""
import math

from core.media_info import format_clock

MAX_PER_VIDEO = 100          # bookmarks kept for one video
MIN_ADD_GAP = 1.0            # a new bookmark must be at least this far from every existing one
PREVIOUS_MARGIN = 1.0        # "previous" skips the bookmark we are standing on (within this many seconds)
NEXT_MARGIN = 0.5
SAME_TIME = 0.005            # two times this close are the same bookmark (rename / remove)
CHAPTER_MIN_GAP = 1.0        # a chapter closer than this to the one before is dropped
GAP_MIN_TIME = 0.5           # no gap is drawn for a chapter that starts at the very beginning
GAP_MIN_PIXELS = 10.0        # a gap closer than this to the last drawn one is skipped
GAP_MAX_COUNT = 60           # with more gaps than this none are drawn


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def clean(items) -> list:
    """The valid bookmarks of whatever was stored, sorted by time and capped: junk is dropped, never raised on."""
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        t, name = item.get("t"), item.get("name")
        if _is_number(t) and t >= 0 and isinstance(name, str):
            out.append({"t": round(float(t), 2), "name": name})
    out.sort(key=lambda i: i["t"])
    return out[:MAX_PER_VIDEO]


def add(items: list, t: float):
    """(new list, added, existing_t): not added when another bookmark is within a second (existing_t says which) or when
    the video already has the maximum (existing_t None)."""
    for item in items:
        if abs(item["t"] - t) < MIN_ADD_GAP:
            return items, False, item["t"]
    if len(items) >= MAX_PER_VIDEO:
        return items, False, None
    return sorted(items + [{"t": round(float(t), 2), "name": ""}], key=lambda i: i["t"]), True, None


def rename(items: list, t: float, name: str) -> list:
    return [{**i, "name": name} if abs(i["t"] - t) <= SAME_TIME else dict(i) for i in items]


def remove(items: list, t: float) -> list:
    return [i for i in items if abs(i["t"] - t) > SAME_TIME]


def previous(items: list, now: float):
    """The last bookmark before the one we stand on, or None."""
    before = [i["t"] for i in items if i["t"] < now - PREVIOUS_MARGIN]
    return before[-1] if before else None


def next_after(items: list, now: float):
    after = [i["t"] for i in items if i["t"] > now + NEXT_MARGIN]
    return after[0] if after else None


def nearest(marks: list, x: float, radius: float = 6.0):
    """The time of the pin closest to pixel `x` within `radius` pixels; `marks` is [(time, pixel x)]."""
    best, best_d = None, radius
    for t, px in marks:
        d = abs(px - x)
        if d <= best_d:
            best, best_d = t, d
    return best


def display_name(item: dict) -> str:
    return item["name"] or format_clock(item["t"])


# --- chapters ----------------------------------------------------------------------------------------------------

def chapters_from_mpv(raw, duration: float) -> list:
    """[(start seconds, title)] from mpv's `chapter-list`: starts inside the video, at least a second apart; the one at 0
    is kept (its name is shown) but gets no gap. Fewer than two usable chapters is no chapters at all."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict) or not _is_number(item.get("time")):
            continue
        t = float(item["time"])
        if t < 0 or (duration > 0 and t >= duration):
            continue
        if out and t - out[-1][0] < CHAPTER_MIN_GAP:
            continue
        title = item.get("title")
        out.append((t, title if isinstance(title, str) else ""))
    return out if len(out) >= 2 else []


def chapter_at(chapters: list, t: float):
    """(1-based number, title or `챕터 N`) of the chapter that contains time `t`; None before the first one."""
    found = None
    for number, (start, title) in enumerate(chapters, 1):
        if start <= t:
            found = (number, title or f"챕터 {number}")
        else:
            break
    return found


def gap_ratios(chapter_times: list, duration: float, span: float,
               min_px: float = GAP_MIN_PIXELS, max_gaps: int = GAP_MAX_COUNT) -> list:
    """Where (0..1 along the bar) the bar is cut: every chapter start after the beginning, skipping one that would be
    closer than `min_px` to the last cut; none at all when there would be more than `max_gaps`."""
    if duration <= 0 or span <= 0:
        return []
    ratios, last_px = [], None
    for t in chapter_times:
        if t <= GAP_MIN_TIME or t >= duration:
            continue
        px = t / duration * span
        if last_px is not None and px - last_px < min_px:
            continue
        ratios.append(t / duration)
        last_px = px
    return ratios if len(ratios) <= max_gaps else []
