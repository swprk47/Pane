"""Bookmarks and chapters: the pure logic (core/bookmarks.py) and, further down, the engine's chapters."""
import pytest

from core import bookmarks as bm
from core.media_info import format_clock


# --- the list of bookmarks ----------------------------------------------------------------------------------------

def test_clean_keeps_valid_items_sorted_and_drops_the_rest():
    raw = [{"t": 5, "name": "b"}, {"t": "x"}, {"t": -1, "name": ""}, {"t": 2.123, "name": 3}, {"t": 1, "name": "a"}, 7]
    assert bm.clean(raw) == [{"t": 1.0, "name": "a"}, {"t": 5.0, "name": "b"}]
    assert bm.clean("nope") == [] and bm.clean(None) == []
    assert bm.clean([{"t": True, "name": ""}, {"t": float("nan"), "name": ""}, {"t": float("inf"), "name": ""}]) == []
    assert len(bm.clean([{"t": i, "name": ""} for i in range(150)])) == 100


def test_add_refuses_a_second_one_within_a_second():
    items = [{"t": 10.0, "name": ""}]
    got, added, existing = bm.add(items, 10.9)
    assert (got, added, existing) == (items, False, 10.0)
    got, added, existing = bm.add(items, 11.1)
    assert added and existing is None and [i["t"] for i in got] == [10.0, 11.1]
    assert got[1]["name"] == ""
    before = [{"t": 30.0, "name": "x"}]
    got, added, _ = bm.add(before, 5.0)
    assert [i["t"] for i in got] == [5.0, 30.0] and before == [{"t": 30.0, "name": "x"}], "sorted, the input untouched"


def test_the_hundred_and_first_is_refused():
    full = [{"t": float(i * 5), "name": ""} for i in range(100)]
    got, added, existing = bm.add(full, 777.0)
    assert not added and existing is None and len(got) == 100


def test_rename_and_remove_match_by_time():
    items = [{"t": 10.0, "name": ""}, {"t": 20.0, "name": "x"}]
    renamed = bm.rename(items, 10.0, "증명")
    assert renamed[0]["name"] == "증명" and items[0]["name"] == "", "the input is untouched"
    assert bm.rename(items, 99.0, "z") == items
    assert bm.remove(items, 20.0) == [items[0]] and bm.remove(items, 99.0) == items
    assert bm.remove(items, 20.004) == [items[0]], "within 0.005 s counts as the same time"


def test_previous_and_next_use_the_margins():
    items = [{"t": 10.0, "name": ""}, {"t": 20.0, "name": ""}, {"t": 30.0, "name": ""}]
    assert bm.previous(items, 21.5) == 20.0
    assert bm.previous(items, 20.5) == 10.0, "20.0 is the one we are standing on (within a second): t < now - 1.0"
    assert bm.previous(items, 20.0) == 10.0
    assert bm.previous(items, 10.5) is None
    assert bm.next_after(items, 20.0) == 30.0
    assert bm.next_after(items, 20.4) == 30.0
    assert bm.next_after(items, 29.6) is None
    assert bm.previous([], 5.0) is None and bm.next_after([], 5.0) is None


def test_nearest_picks_the_closest_pin_within_the_radius():
    marks = [(10.0, 100.0), (20.0, 105.0)]
    assert bm.nearest(marks, 103.0) == 20.0
    assert bm.nearest(marks, 120.0) is None
    assert bm.nearest(marks, 106.0, radius=0.5) is None
    assert bm.nearest([], 5.0) is None


def test_display_name_is_the_name_or_the_time():
    assert bm.display_name({"t": 125.3, "name": ""}) == format_clock(125.3)
    assert bm.display_name({"t": 125.3, "name": "증명 다시 보기"}) == "증명 다시 보기"


# --- chapters ----------------------------------------------------------------------------------------------------

def test_chapters_from_mpv_keeps_the_usable_and_needs_two():
    raw = [{"time": 0, "title": "Intro"}, {"time": 760, "title": "Graphs"}, {"time": 760.4, "title": "dup"},
           {"time": 5000, "title": "late"}, {"time": -1, "title": "bad"}]
    assert bm.chapters_from_mpv(raw, 3860) == [(0.0, "Intro"), (760.0, "Graphs")]
    assert bm.chapters_from_mpv([{"time": 0, "title": "Intro"}], 3860) == []
    assert bm.chapters_from_mpv("nope", 3860) == [] and bm.chapters_from_mpv(None, 3860) == []
    assert bm.chapters_from_mpv([{"time": 0}, {"time": 50}], 3860) == [(0.0, ""), (50.0, "")]
    assert bm.chapters_from_mpv([{"time": 0, "title": "a"}, {"time": "x"}, 4, {"time": 60, "title": 5}], 3860) == [
        (0.0, "a"), (60.0, "")], "junk items are skipped, a non-string title becomes empty"


def test_chapter_at_names_the_chapter_under_a_time():
    chapters = [(0.0, "Intro"), (760.0, ""), (1800.0, "Proofs")]
    assert bm.chapter_at(chapters, 100.0) == (1, "Intro")
    assert bm.chapter_at(chapters, 760.0) == (2, "챕터 2"), "no title: the number"
    assert bm.chapter_at(chapters, 2000.0) == (3, "Proofs")
    assert bm.chapter_at([(5.0, "A"), (100.0, "B")], 2.0) is None, "before the first chapter"
    assert bm.chapter_at([], 10.0) is None


def test_gap_ratios_skip_close_gaps_and_give_up_above_sixty():
    ratios = bm.gap_ratios([0.0, 760.0, 1800.0, 3000.0], 3860.0, 880.0)
    assert ratios == pytest.approx([760 / 3860, 1800 / 3860, 3000 / 3860]), "none for the chapter at 0"
    close = bm.gap_ratios([0.0, 760.0, 761.0], 3860.0, 880.0)                     # 1 s = 0.23 px apart
    assert close == pytest.approx([760 / 3860])
    many = bm.gap_ratios([i * 50.0 for i in range(70)], 3860.0, 880.0)             # 11 px apart, 69 gaps
    assert many == []
    assert bm.gap_ratios([], 3860.0, 880.0) == [] and bm.gap_ratios([0.0, 10.0], 0.0, 880.0) == []


# --- the engine's chapters ---------------------------------------------------------------------------------------

def test_a_file_without_chapters_has_none(engine, sample_video, pump):
    engine.load_file(sample_video)
    assert pump(lambda: engine.get_media_info().get("width"), timeout=10)
    assert engine.chapters() == []


def test_chapters_reads_mpvs_chapter_list(engine, monkeypatch):
    engine._duration = 3860.0
    original = engine.mpv._get_property
    raw = [{"time": 0, "title": "Intro"}, {"time": 760, "title": "Graphs"}, {"time": 1800, "title": "Proofs"}]
    monkeypatch.setattr(engine.mpv, "_get_property", lambda name, *a, **k: raw if name == "chapter-list" else original(name, *a, **k))
    assert engine.chapters() == [(0.0, "Intro"), (760.0, "Graphs"), (1800.0, "Proofs")]


def test_a_failing_property_read_gives_no_chapters(engine, monkeypatch):
    def boom(name, *a, **k):
        raise RuntimeError("mpv is gone")

    monkeypatch.setattr(engine.mpv, "_get_property", boom)
    assert engine.chapters() == []


def test_chapters_are_not_cut_by_the_previous_videos_length(engine, monkeypatch):
    """Final review: mpv reports file-loaded before the new duration, so the engine's cached length is still the old one's."""
    engine._duration = 600.0                              # the 10-minute video watched before
    original = engine.mpv._get_property
    raw = [{"time": 0, "title": "Intro"}, {"time": 1800, "title": "Graphs"}, {"time": 3000, "title": "Proofs"}]

    def prop(name, *a, **k):
        return {"chapter-list": raw, "duration": 5400.0}.get(name) if name in ("chapter-list", "duration") else original(name, *a, **k)

    monkeypatch.setattr(engine.mpv, "_get_property", prop)
    assert engine.chapters() == [(0.0, "Intro"), (1800.0, "Graphs"), (3000.0, "Proofs")]
