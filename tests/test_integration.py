"""End-to-end flows through MainWindow with a real media file (tests/assets/sample.mp4)."""
import shutil

import pytest


@pytest.fixture
def playing(window, sample_video, pump):
    """MainWindow with the sample loaded and actually playing."""
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.2), "sample never started playing"
    return window


def test_load_returns_true_and_reaches_the_engine(window, sample_video):
    """Guards the old synthetic-input tests, which ignored load_file()'s return value."""
    assert window.engine.load_file(sample_video) is True
    assert window.engine.load_file("av://lavfi:testsrc=duration=2:size=640x360:rate=30") is False


def test_speed_change_reaches_every_part_of_the_ui(playing, pump):
    w = playing
    w.change_speed_relative(+0.25)                       # 1.00 -> 1.25
    assert pump(lambda: w.controller.btn_speed.text() == "1.25x")
    assert w.engine.get_speed() == 1.25
    assert w.osd.full_text() == "배속 1.25x"
    assert w.speed_popup.slider.value() == 125

    w.change_speed_relative(+0.15)                       # 1.25 -> 1.40
    assert pump(lambda: w.controller.btn_speed.text() == "1.40x")
    assert w.engine.get_speed() == 1.40


def test_speed_popup_chip_changes_playback_speed(playing, pump):
    w = playing
    chip = next(c for c in (w.speed_popup.preset_layout.itemAt(i).widget()
                            for i in range(w.speed_popup.preset_layout.count()))
                if c is not None and c.speed == 1.5)
    chip.click()
    assert pump(lambda: w.controller.btn_speed.text() == "1.50x")   # signal reached the UI
    assert w.engine.get_speed() == 1.5


def test_volume_reaches_engine_slider_and_settings(playing, pump):
    w = playing
    w.set_volume(40.0)
    assert pump(lambda: w.controller.vol_slider.value() == 40)
    assert w.engine.get_volume() == 40.0
    assert pump(lambda: w.app_settings.get_volume() == 40.0)


def test_time_display_follows_playback(playing, pump):
    w = playing
    assert pump(lambda: w.controller.lbl_time.text().startswith("00:01"), timeout=3.0), w.controller.lbl_time.text()
    assert w.controller.lbl_time.text().endswith("/ 00:02")        # 2.97 s file


def test_resume_position_is_offered_on_reopen(window, sample_video, pump):
    window.app_settings.save_resume_position(sample_video, 12.0)
    assert window.app_settings.get_resume_position(sample_video) == 12.0
    window.load_media_file(sample_video)
    assert window.osd.text_label.text().startswith("이어서 재생")


def test_recent_files_are_recorded(window, sample_video):
    window.load_media_file(sample_video)
    assert window.app_settings.get_recent_files()[0] == sample_video


def test_sidecar_subtitle_is_auto_loaded(window, sample_video, tmp_path, pump):
    clip = tmp_path / "lecture.mp4"
    shutil.copy(sample_video, clip)
    (tmp_path / "lecture.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nhello\n", encoding="utf-8")
    window.load_media_file(str(clip))
    assert window.osd.text_label.text().startswith("자막 로드됨")
    assert "lecture.srt" in window.osd.text_label.text()


def test_seek_button_moves_playback(playing, pump):
    w = playing
    w.engine.set_speed(0.5)
    start = w.engine._time_pos
    w.seek_relative(1.0)
    assert pump(lambda: w.engine._time_pos > start + 0.8), f"{start} -> {w.engine._time_pos}"
    assert not w.osd.isVisible()              # a seek is visible on the timeline: no notice


def test_finish_then_open_another_file(window, sample_video, pump):
    window.load_media_file(sample_video)
    window.engine.set_speed(4.0)
    assert pump(lambda: window.osd.text_label.text() == "재생 완료", timeout=6.0)
    window.engine.set_speed(1.0)
    window.load_media_file(sample_video)                   # replay after EOF
    assert pump(lambda: window.engine.is_playing() and window.engine._time_pos > 0.3, timeout=3.0)


def test_speed_panel_opens_in_the_bottom_left_corner_above_the_controls(playing, pump):
    w = playing
    assert pump(lambda: w.controller.left_zone.isVisible())
    w._show_speed_popup()
    left = w.controller.left_zone.mapTo(w.central_widget, w.controller.left_zone.rect().topLeft()).x()
    assert w.speed_popup.isVisible() and w.speed_popup.x() == left
    assert w.speed_popup.y() + w.speed_popup.height() <= w.controller.btn_speed.mapTo(
        w.central_widget, w.controller.btn_speed.rect().topLeft()).y()
