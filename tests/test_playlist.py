"""The folder-as-playlist logic: natural order and the previous / next neighbours."""
import os

import pytest

from core import playlist


def touch(folder, *names):
    for n in names:
        (folder / n).write_bytes(b"x")


def names(paths):
    return [os.path.basename(p) for p in paths]


def test_numbers_compare_by_value_not_by_letter():
    ordered = sorted(["강의10.mp4", "강의2.mp4", "강의1.mp4", "강의20.mp4", "강의3.mp4"], key=playlist.natural_key)
    assert ordered == ["강의1.mp4", "강의2.mp4", "강의3.mp4", "강의10.mp4", "강의20.mp4"]


def test_letters_ignore_case_and_multiple_numbers_work():
    ordered = sorted(["S01E10.mkv", "s01e2.mkv", "S02E1.mkv", "S01E1.mkv"], key=playlist.natural_key)
    assert ordered == ["S01E1.mkv", "s01e2.mkv", "S01E10.mkv", "S02E1.mkv"]


def test_mixed_text_and_numbers_never_raise():
    # a name that starts with digits against one that starts with letters must still be comparable
    assert sorted(["a1.mp4", "1a.mp4", "b.mp4", "10.mp4", "2.mp4"], key=playlist.natural_key)
    assert sorted(["x2.mp4", "x10.mp4", "x1.mp4"], key=playlist.natural_key) == ["x1.mp4", "x2.mp4", "x10.mp4"]


def test_equal_looking_names_keep_a_stable_order():
    a, b = playlist.natural_key("ep01.mp4"), playlist.natural_key("EP01.mp4")
    assert a != b and sorted([a, b]) == sorted([b, a])


def test_folder_videos_lists_only_videos_in_natural_order(tmp_path):
    touch(tmp_path, "lec10.mp4", "lec2.mp4", "lec1.MKV", "notes.txt", "cover.jpg", "lec3.srt", ".hidden.mp4")
    (tmp_path / "sub.mp4").mkdir()                                  # a folder named like a video
    assert names(playlist.folder_videos(str(tmp_path / "lec1.MKV"))) == ["lec1.MKV", "lec2.mp4", "lec10.mp4"]


def test_neighbors_in_the_middle_and_at_both_ends(tmp_path):
    touch(tmp_path, "a1.mp4", "a2.mp4", "a3.mp4")
    prev_, next_ = playlist.neighbors(str(tmp_path / "a2.mp4"))
    assert (os.path.basename(prev_), os.path.basename(next_)) == ("a1.mp4", "a3.mp4")
    assert playlist.neighbors(str(tmp_path / "a1.mp4"))[0] is None
    assert playlist.neighbors(str(tmp_path / "a3.mp4"))[1] is None


def test_a_lone_file_has_no_neighbors(tmp_path):
    touch(tmp_path, "only.mp4")
    assert playlist.neighbors(str(tmp_path / "only.mp4")) == (None, None)


def test_the_open_file_counts_even_with_an_unlisted_extension(tmp_path):
    touch(tmp_path, "a1.mp4", "a3.mp4", "a2.m2ts")                  # .m2ts is opened through "All files"
    prev_, next_ = playlist.neighbors(str(tmp_path / "a2.m2ts"))
    assert (os.path.basename(prev_), os.path.basename(next_)) == ("a1.mp4", "a3.mp4")


def test_a_missing_folder_does_not_raise(tmp_path):
    ghost = tmp_path / "gone" / "x1.mp4"
    assert playlist.neighbors(str(ghost)) == (None, None)


def test_neighbors_follow_the_folder_as_it_changes(tmp_path):
    touch(tmp_path, "e1.mp4", "e2.mp4")
    assert os.path.basename(playlist.neighbors(str(tmp_path / "e2.mp4"))[1] or "") == ""
    touch(tmp_path, "e3.mp4")
    assert os.path.basename(playlist.neighbors(str(tmp_path / "e2.mp4"))[1]) == "e3.mp4"


def test_paths_compare_case_insensitively_on_windows(tmp_path):
    touch(tmp_path, "a1.mp4", "a2.mp4")
    upper = str(tmp_path / "A1.MP4")
    assert os.path.basename(playlist.neighbors(upper)[1]) == "a2.mp4"


def test_extension_list_matches_the_open_dialog():
    from core.media_types import VIDEO_EXTENSIONS
    assert all(playlist.is_video(f"x.{e}") and playlist.is_video(f"x.{e.upper()}") for e in VIDEO_EXTENSIONS)
    assert not playlist.is_video("x.txt") and not playlist.is_video("noext")
