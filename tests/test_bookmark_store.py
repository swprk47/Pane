"""Bookmarks per video in the settings store, and the chapter switch."""
import json

from core.settings import AppSettings


def test_bookmarks_round_trip_per_video():
    s = AppSettings()
    s.save_bookmarks(r"D:\강의\1주차.mp4", [{"t": 24.1, "name": "증명"}, {"t": 5, "name": ""}])
    s.save_bookmarks(r"D:\강의\2주차.mp4", [{"t": 9.0, "name": ""}])
    again = AppSettings()
    assert again.get_bookmarks(r"D:\강의\1주차.mp4") == [{"t": 5.0, "name": ""}, {"t": 24.1, "name": "증명"}]
    assert again.get_bookmarks(r"D:\강의\2주차.mp4") == [{"t": 9.0, "name": ""}]
    assert again.get_bookmarks(r"D:\강의\3주차.mp4") == []


def test_an_empty_list_forgets_the_video():
    s = AppSettings()
    s.save_bookmarks("a.mp4", [{"t": 1.0, "name": ""}])
    s.save_bookmarks("a.mp4", [])
    assert s.get_bookmarks("a.mp4") == [] and "a.mp4" not in json.loads(s.settings.value("bookmarks"))


def test_the_two_hundred_video_limit_drops_the_least_recently_changed():
    s = AppSettings()
    for i in range(205):
        s.save_bookmarks(f"v{i}.mp4", [{"t": 1.0, "name": ""}])
        if i == 100:
            s.save_bookmarks("v0.mp4", [{"t": 2.0, "name": ""}])               # touched again: it is recent now
    stored = json.loads(s.settings.value("bookmarks"))
    assert len(stored) == 200
    assert "v0.mp4" in stored and "v1.mp4" not in stored and "v204.mp4" in stored


def test_more_than_a_hundred_bookmarks_for_one_video_are_cut():
    s = AppSettings()
    s.save_bookmarks("a.mp4", [{"t": float(i), "name": ""} for i in range(150)])
    assert len(s.get_bookmarks("a.mp4")) == 100


def test_broken_stored_values_are_ignored_not_fatal():
    s = AppSettings()
    s.settings.setValue("bookmarks", "{not json")
    assert s.get_bookmarks("a.mp4") == []
    s.settings.setValue("bookmarks", json.dumps({"a.mp4": "x", "b.mp4": [{"t": "bad"}, {"t": 3, "name": "ok"}, 5]}))
    assert s.get_bookmarks("a.mp4") == [] and s.get_bookmarks("b.mp4") == [{"t": 3.0, "name": "ok"}]
    s.settings.setValue("bookmarks", json.dumps([1, 2]))
    assert s.get_bookmarks("a.mp4") == []
    s.save_bookmarks("a.mp4", [{"t": 1.0, "name": ""}])                          # saving over junk starts clean
    assert s.get_bookmarks("a.mp4") == [{"t": 1.0, "name": ""}]


def test_chapters_visible_defaults_to_on_and_is_remembered():
    s = AppSettings()
    assert s.get_chapters_visible() is True
    s.set_chapters_visible(False)
    assert AppSettings().get_chapters_visible() is False
    s.set_chapters_visible(True)
    assert AppSettings().get_chapters_visible() is True
