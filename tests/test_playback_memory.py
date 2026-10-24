"""Per-video memory of the speed and of the chosen audio / subtitle track, with the folder's last values as the fallback."""
import json
import os
import shutil

import pytest

from core.settings import AppSettings
from core.tracks import AUDIO, SUB, Track, list_tracks, pick_track, track_choice


def folder_of(path):
    return os.path.normcase(os.path.dirname(os.path.abspath(path)))


# --- the store ------------------------------------------------------------------------------------------------

def test_what_is_saved_for_a_video_comes_back():
    s = AppSettings()
    s.save_playback_memory(r"D:\강의\1주차.mp4", speed=1.5, audio={"lang": "jpn", "title": ""}, sub="off")
    assert AppSettings().get_playback_memory(r"D:\강의\1주차.mp4") == {
        "speed": 1.5, "audio": {"lang": "jpn", "title": ""}, "sub": "off"}


def test_a_video_without_memory_inherits_the_last_values_of_its_own_folder_only():
    s = AppSettings()
    s.save_playback_memory(r"D:\강의\1주차.mp4", speed=1.25, sub={"lang": "kor", "title": ""})
    assert s.get_playback_memory(r"D:\강의\2주차.mp4") == {"speed": 1.25, "sub": {"lang": "kor", "title": ""}}
    assert s.get_playback_memory(r"D:\영화\a.mp4") == {}, "another folder: nothing"
    assert s.get_playback_memory(r"D:\강의\sub\3주차.mp4") == {}, "not a parent or a child folder either"


def test_each_field_of_the_video_wins_over_the_folder_and_the_missing_ones_fall_back_to_it():
    s = AppSettings()
    s.save_playback_memory(r"D:\강의\1주차.mp4", speed=1.5, audio={"lang": "jpn", "title": ""})
    s.save_playback_memory(r"D:\강의\2주차.mp4", speed=1.25)                # folder now: speed 1.25, audio jpn
    got = s.get_playback_memory(r"D:\강의\1주차.mp4")
    assert got["speed"] == 1.5 and got["audio"] == {"lang": "jpn", "title": ""}
    got = s.get_playback_memory(r"D:\강의\2주차.mp4")
    assert got["speed"] == 1.25 and got["audio"] == {"lang": "jpn", "title": ""}, "audio comes from the folder"


def test_update_folder_false_keeps_the_folders_values():
    s = AppSettings()
    s.save_playback_memory(r"D:\강의\1주차.mp4", speed=1.5)
    s.save_playback_memory(r"D:\강의\3주차.mp4", speed=1.0, update_folder=False)
    assert s.get_playback_memory(r"D:\강의\3주차.mp4")["speed"] == 1.0
    assert s.get_playback_memory(r"D:\강의\4주차.mp4")["speed"] == 1.5, "the exception did not change the folder"


def test_a_stream_has_no_folder_memory():
    s = AppSettings()
    s.save_playback_memory("http://example.com/live/a.mp4", speed=2.0)
    assert s.get_playback_memory("http://example.com/live/a.mp4")["speed"] == 2.0
    assert s.get_playback_memory("http://example.com/live/b.mp4") == {}


def test_the_store_keeps_the_latest_hundred_videos_and_thirty_folders():
    s = AppSettings()
    for i in range(110):
        s.save_playback_memory(rf"D:\f{i % 40}\v{i}.mp4", speed=1.1)
    files = json.loads(s.settings.value("playback_memory"))
    folders = json.loads(s.settings.value("folder_memory"))
    assert len(files) == 100 and len(folders) == 30
    assert r"D:\f29\v109.mp4" in files and r"D:\f0\v0.mp4" not in files


def test_broken_or_odd_values_are_ignored_not_fatal():
    s = AppSettings()
    s.settings.setValue("playback_memory", "{not json")
    s.settings.setValue("folder_memory", json.dumps({folder_of(r"D:\x\a.mp4"): {"speed": "fast", "audio": 5, "sub": 3}}))
    assert s.get_playback_memory(r"D:\x\a.mp4") == {}
    s.settings.setValue("playback_memory", json.dumps({r"D:\x\b.mp4": {"speed": "x", "audio": "jpn", "sub": {"lang": 1}}}))
    assert s.get_playback_memory(r"D:\x\b.mp4") == {}


# --- choosing a track again by what it is -----------------------------------------------------------------------

def tr(id, lang="", title="", kind=AUDIO):
    return Track(id=id, kind=kind, name="x", detail="", selected=False, lang=lang, title=title)


def test_list_tracks_carries_the_language_and_the_title():
    raw = [{"type": "audio", "id": 1, "lang": "jpn", "title": "Commentary"}, {"type": "sub", "id": 2}]
    a = list_tracks(raw, AUDIO)[0]
    s = list_tracks(raw, SUB)[0]
    assert (a.lang, a.title) == ("jpn", "Commentary") and (s.lang, s.title) == ("", "")


def test_track_choice_is_what_gets_remembered():
    assert track_choice(tr(1, "jpn", "Commentary")) == {"lang": "jpn", "title": "Commentary"}


def test_pick_track_prefers_language_and_title_then_the_language_alone():
    tracks = [tr(1, "jpn", "Main"), tr(2, "jpn", "Commentary"), tr(3, "eng", "Main")]
    assert pick_track(tracks, {"lang": "jpn", "title": "Commentary"}).id == 2
    assert pick_track(tracks, {"lang": "jpn", "title": "Director"}).id == 1, "same language, the lowest number"
    assert pick_track(tracks, {"lang": "eng", "title": ""}).id == 3
    assert pick_track(tracks, {"lang": "kor", "title": ""}) is None


def test_two_letter_and_three_letter_codes_mean_the_same_language():
    assert pick_track([tr(1, "kor")], {"lang": "ko", "title": ""}).id == 1
    assert pick_track([tr(1, "ja")], {"lang": "jpn", "title": ""}).id == 1


def test_a_track_without_a_language_is_found_by_its_title_only_and_never_guessed_by_number():
    tracks = [tr(1, "", "Main"), tr(2, "und", "Commentary")]
    assert pick_track(tracks, {"lang": "", "title": "Commentary"}).id == 2
    assert pick_track(tracks, {"lang": "und", "title": ""}) is None
    assert pick_track(tracks, {"lang": "", "title": ""}) is None
    assert pick_track(tracks, None) is None


# --- the window ------------------------------------------------------------------------------------------------

@pytest.fixture
def lecture_folder(tmp_path):
    """Two copies of the sample video in one folder, one more in another."""
    from conftest import SAMPLE_VIDEO
    a, b = tmp_path / "week" / "1.mp4", tmp_path / "week" / "2.mp4"
    other = tmp_path / "movies" / "x.mp4"
    for p in (a, b, other):
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SAMPLE_VIDEO, p)
    return str(a), str(b), str(other)


def settle(window, pump, speed=None):
    pump(None, timeout=0.5)


def test_opening_a_video_applies_its_remembered_speed(window, lecture_folder, pump):
    a, _, _ = lecture_folder
    window.app_settings.save_playback_memory(a, speed=1.5)
    window.load_media_file(a)
    assert pump(lambda: abs(window.engine.get_speed() - 1.5) < 0.01, timeout=10)
    assert "기억" not in window.osd.text_label.text(), "no message: remembering is the feature"


def test_a_video_without_memory_takes_the_speed_of_the_last_one_in_its_folder(window, lecture_folder, pump):
    a, b, other = lecture_folder
    window.app_settings.save_playback_memory(a, speed=1.25)
    window.load_media_file(b)
    assert pump(lambda: abs(window.engine.get_speed() - 1.25) < 0.01, timeout=10)
    window.engine.set_speed(1.0)
    pump(None, timeout=0.3)
    window.app_settings.save_playback_memory(a, speed=1.25)               # (put it back: the user change above saved 1.0)
    window.load_media_file(other)                                          # another folder: nothing is applied
    pump(None, timeout=0.8)
    assert abs(window.engine.get_speed() - 1.0) < 0.01


def test_the_speed_the_app_applied_is_not_saved_as_if_the_user_had_set_it(window, lecture_folder, pump):
    a, _, _ = lecture_folder
    window.app_settings.save_playback_memory(a, speed=1.5, update_folder=False)    # the video's own memory only
    window.load_media_file(a)
    assert pump(lambda: abs(window.engine.get_speed() - 1.5) < 0.01, timeout=10)
    pump(None, timeout=0.6)
    assert window.app_settings.get_playback_memory(os.path.join(os.path.dirname(a), "2.mp4")) == {}, \
        "opening a video must not make its speed the folder's"


def test_a_speed_the_user_sets_is_saved_for_the_video_and_for_its_folder(window, lecture_folder, pump):
    a, b, _ = lecture_folder
    window.load_media_file(a)
    pump(None, timeout=0.5)
    window.engine.set_speed(1.25)
    assert pump(lambda: window.app_settings.get_playback_memory(a).get("speed") == 1.25, timeout=5)
    assert window.app_settings.get_playback_memory(b)["speed"] == 1.25, "the folder follows"


def test_resetting_the_speed_is_remembered_for_this_video_only(window, lecture_folder, pump):
    a, b, _ = lecture_folder
    window.app_settings.save_playback_memory(a, speed=1.5)
    window.load_media_file(a)
    assert pump(lambda: abs(window.engine.get_speed() - 1.5) < 0.01, timeout=10)
    window.reset_speed()
    pump(None, timeout=0.6)
    assert window.app_settings.get_playback_memory(a)["speed"] == 1.0
    assert window.app_settings.get_playback_memory(b)["speed"] == 1.5, "the folder's speed is kept for the next video"


def test_an_out_of_range_remembered_speed_is_brought_into_range(window, lecture_folder, pump):
    a, _, _ = lecture_folder
    window.app_settings.save_playback_memory(a, speed=9.0, update_folder=False)
    window.load_media_file(a)
    assert pump(lambda: abs(window.engine.get_speed() - 4.0) < 0.01, timeout=10)


def test_the_tracks_ready_signal_comes_once_for_each_opened_video(window, lecture_folder, pump):
    a, b, _ = lecture_folder
    got = []
    window.engine.tracks_ready.connect(lambda: got.append(1))
    window.load_media_file(a)
    assert pump(lambda: len(got) == 1, timeout=10)
    pump(None, timeout=0.6)
    assert len(got) == 1
    window.load_media_file(b)
    assert pump(lambda: len(got) == 2, timeout=10)


class FakeTracks:
    """Stands in for the track list of a loaded file, and records what the window chooses."""

    def __init__(self, window, monkeypatch, audio, sub, visible=True):
        self.chosen, self.visible = [], visible
        e = window.engine
        monkeypatch.setattr(e, "audio_tracks", lambda: audio)
        monkeypatch.setattr(e, "subtitle_tracks", lambda: sub)
        monkeypatch.setattr(e, "select_audio_track", lambda i: self.chosen.append(("audio", i)) or True)
        monkeypatch.setattr(e, "select_subtitle_track", lambda i: self.chosen.append(("sub", i)) or True)
        monkeypatch.setattr(e, "subtitles_visible", lambda: self.visible)
        monkeypatch.setattr(e, "set_subtitles_visible", lambda v: setattr(self, "visible", v) or self.chosen.append(("visible", v)))
        monkeypatch.setattr(e, "toggle_subtitle_visibility", lambda: setattr(self, "visible", not self.visible) or self.visible)


def test_the_remembered_tracks_are_chosen_by_language_when_a_video_is_ready(window, lecture_folder, monkeypatch):
    a, _, _ = lecture_folder
    window._current_file = a
    window.app_settings.save_playback_memory(a, audio={"lang": "jpn", "title": ""}, sub={"lang": "kor", "title": ""})
    fake = FakeTracks(window, monkeypatch, [tr(1, "eng"), tr(2, "jpn")], [tr(3, "eng", kind=SUB), tr(4, "kor", kind=SUB)])
    window._apply_remembered_tracks()
    assert ("audio", 2) in fake.chosen and ("sub", 4) in fake.chosen


def test_a_remembered_off_turns_the_subtitles_off(window, lecture_folder, monkeypatch):
    a, _, _ = lecture_folder
    window._current_file = a
    window.app_settings.save_playback_memory(a, sub="off")
    fake = FakeTracks(window, monkeypatch, [], [tr(3, "eng", kind=SUB)])
    window._apply_remembered_tracks()
    assert fake.chosen == [("visible", False)]


def test_nothing_is_changed_when_no_remembered_track_exists_in_the_new_video(window, lecture_folder, monkeypatch):
    a, _, _ = lecture_folder
    window._current_file = a
    window.app_settings.save_playback_memory(a, audio={"lang": "fra", "title": ""}, sub={"lang": "deu", "title": ""})
    fake = FakeTracks(window, monkeypatch, [tr(1, "eng")], [tr(3, "eng", kind=SUB)])
    window._apply_remembered_tracks()
    assert fake.chosen == []


def test_the_lecture_voice_preset_keeps_its_own_audio_track(window, lecture_folder, monkeypatch):
    a, _, _ = lecture_folder
    window._current_file = a
    window.engine.lecture_audio = True
    window.app_settings.save_playback_memory(a, audio={"lang": "jpn", "title": ""}, sub={"lang": "kor", "title": ""})
    fake = FakeTracks(window, monkeypatch, [tr(1, "eng"), tr(2, "jpn")], [tr(4, "kor", kind=SUB)])
    window._apply_remembered_tracks()
    assert fake.chosen == [("sub", 4)], "the subtitle is applied, the audio track is not"
    window.engine.lecture_audio = False


def test_choosing_a_track_remembers_it_by_language_and_title(window, lecture_folder, monkeypatch):
    a, b, _ = lecture_folder
    window._current_file = a
    FakeTracks(window, monkeypatch, [tr(1, "eng"), tr(2, "jpn", "Commentary")], [tr(4, "kor", kind=SUB)])
    window._choose_audio_track(2)
    window._choose_subtitle_track(4)
    got = window.app_settings.get_playback_memory(a)
    assert got["audio"] == {"lang": "jpn", "title": "Commentary"} and got["sub"] == {"lang": "kor", "title": ""}
    assert window.app_settings.get_playback_memory(b)["audio"]["lang"] == "jpn", "the folder follows"


def test_a_track_that_cannot_be_recognised_again_is_not_remembered(window, lecture_folder, monkeypatch):
    a, _, _ = lecture_folder
    window._current_file = a
    FakeTracks(window, monkeypatch, [tr(1, "", "")], [tr(4, "und", "", kind=SUB)])
    window._choose_audio_track(1)
    window._choose_subtitle_track(4)
    assert window.app_settings.get_playback_memory(a) == {}


def test_switching_the_subtitles_off_and_on_is_remembered(window, lecture_folder, monkeypatch):
    a, _, _ = lecture_folder
    window._current_file = a
    sub = Track(id=4, kind=SUB, name="x", detail="", selected=True, lang="kor", title="")
    FakeTracks(window, monkeypatch, [], [sub], visible=True)
    window.toggle_subtitle(osd=False)                                      # on -> off
    assert window.app_settings.get_playback_memory(a)["sub"] == "off"
    window.toggle_subtitle(osd=False)                                      # off -> on: the selected track is remembered
    assert window.app_settings.get_playback_memory(a)["sub"] == {"lang": "kor", "title": ""}
