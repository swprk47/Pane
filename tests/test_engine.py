"""PlayerEngine: speed precision, volume, loading and real playback."""
import os

import pytest

SPEEDS = [1.0, 1.2, 1.25, 1.4, 1.45, 1.75, 2.0]


@pytest.mark.parametrize("speed", SPEEDS)
def test_set_speed_is_exact(engine, speed):
    assert engine.set_speed(speed) == speed
    assert engine.get_speed() == speed


def test_relative_speed_steps_of_005(engine):
    engine.set_speed(1.20)
    assert engine.change_speed_relative(+0.05) == 1.25
    assert engine.change_speed_relative(+0.15) == 1.40
    assert engine.change_speed_relative(-0.05) == 1.35
    assert engine.reset_speed() == 1.0


def test_speed_is_clamped(engine):
    assert engine.set_speed(0.01) == 0.25
    assert engine.set_speed(9.0) == 4.0


def test_volume_set_and_clamp(engine):
    engine.set_volume(75.0)
    assert engine.get_volume() == 75.0
    engine.set_volume(250.0)
    assert engine.get_volume() == 100.0
    engine.set_volume(-5.0)
    assert engine.get_volume() == 0.0


def test_mute_toggle(engine):
    assert engine.toggle_mute() is True
    assert engine.toggle_mute() is False


# --- loading ---------------------------------------------------------------

def test_load_missing_file_fails_and_reports(engine, tmp_path):
    errors = []
    engine.error_occurred.connect(errors.append)
    assert engine.load_file(str(tmp_path / "does_not_exist.mp4")) is False
    assert errors and "not found" in errors[0].lower()


def test_synthetic_lavfi_input_is_rejected(engine):
    """load_file() only accepts existing files, so av://lavfi sources cannot be
    used to exercise playback. (The old tests ignored this False return value
    and therefore verified nothing.)"""
    assert engine.load_file("av://lavfi:testsrc=duration=2:size=640x360:rate=30") is False


def test_load_real_file_plays(engine, sample_video, pump):
    loaded = []
    engine.file_loaded.connect(loaded.append)
    assert engine.load_file(sample_video) is True
    assert loaded == [os.path.basename(sample_video)]

    assert pump(lambda: engine._duration > 0), "duration never reported"
    assert engine._duration == pytest.approx(3.0, abs=0.2)
    assert pump(lambda: engine._time_pos > 0.3), "playback position did not advance"
    assert engine.is_playing()


def test_pause_and_resume_signal_state(engine, sample_video, pump):
    states = []
    engine.playback_state_changed.connect(states.append)
    engine.load_file(sample_video)
    pump(lambda: engine._time_pos > 0.1)

    engine.pause()
    assert pump(lambda: states and states[-1] is False)
    assert not engine.is_playing()
    frozen = engine._time_pos
    pump(timeout=0.4)
    assert engine._time_pos == pytest.approx(frozen, abs=0.05), "time advanced while paused"

    engine.play()
    assert pump(lambda: states[-1] is True)
    assert engine.is_playing()


def test_absolute_seek_while_playing(engine, sample_video, pump):
    engine.load_file(sample_video)
    engine.set_speed(0.5)                      # slow, so we can observe the jump
    pump(lambda: engine._time_pos > 0.2)
    engine.seek(2.0, "absolute")
    assert pump(lambda: engine._time_pos >= 1.9), f"time_pos={engine._time_pos}"


def test_relative_seek_moves_forward(engine, sample_video, pump):
    engine.load_file(sample_video)
    engine.set_speed(0.5)
    pump(lambda: engine._time_pos > 0.2)
    start = engine._time_pos
    engine.seek(1.0, "relative")
    assert pump(lambda: engine._time_pos > start + 0.8), f"{start} -> {engine._time_pos}"


def test_frame_step_advances_one_frame(engine, sample_video, pump):
    engine.load_file(sample_video)
    pump(lambda: engine._time_pos > 0.2)
    engine.pause()
    pump(timeout=0.3)
    before = engine._time_pos
    engine.step_frame_forward()
    assert pump(lambda: engine._time_pos > before + 0.01), "frame step did not move time"
    assert engine._time_pos - before == pytest.approx(1 / 30, abs=0.03)


def test_speed_signal_reports_new_value(engine, pump):
    seen = []
    engine.speed_changed.connect(seen.append)
    engine.set_speed(1.35)
    assert pump(lambda: 1.35 in seen)


def test_screenshot_writes_a_png(engine, sample_video, pump, tmp_path):
    engine.load_file(sample_video)
    pump(lambda: engine._time_pos > 0.3)
    out = tmp_path / "shot.png"
    assert engine.take_screenshot(str(out)) == str(out)
    assert out.exists() and out.stat().st_size > 1000


def test_end_of_file_signal_fires_once(engine, sample_video, pump):
    """Regression: with keep_open=yes mpv sends no end-file event at EOF, so
    file_ended (and the 'playback finished' OSD) never fired."""
    ended = []
    engine.file_ended.connect(lambda: ended.append(True))
    engine.load_file(sample_video)
    engine.set_speed(4.0)
    assert pump(lambda: ended, timeout=6.0), "file_ended was not emitted"
    pump(timeout=0.5)
    assert ended == [True], "file_ended must fire exactly once"


def test_start_time_is_applied_when_loading(engine, sample_video, pump):
    """Regression: seeking right after loadfile failed (file not loaded yet), so 'resume where
    you left off' showed its OSD but always started at 0."""
    engine.set_speed(0.5)
    assert engine.load_file(sample_video, start_time=1.8) is True
    assert pump(lambda: engine._time_pos > 1.8), f"time_pos={engine._time_pos}: start position ignored"
    assert engine._time_pos < 2.8


def test_no_start_time_begins_at_the_start(engine, sample_video, pump):
    engine.set_speed(0.5)
    engine.load_file(sample_video)
    assert pump(lambda: engine._time_pos > 0.1)
    assert engine._time_pos < 1.0


def test_default_capture_dir_is_an_existing_folder(engine):
    """Regression: the default was <home>/Desktop, which does not exist on localized
    Windows (the desktop is called 바탕화면 here), so Ctrl+S failed."""
    d = engine.default_capture_dir()
    assert d.is_dir()


def test_default_screenshot_lands_in_the_capture_dir(engine, sample_video, pump, tmp_path, monkeypatch):
    from PySide6.QtCore import QStandardPaths
    monkeypatch.setattr(QStandardPaths, "writableLocation", staticmethod(lambda loc: str(tmp_path)))
    engine.load_file(sample_video)
    pump(lambda: engine._time_pos > 0.3)
    out = engine.take_screenshot()                       # no explicit path: the default location
    assert out and out.startswith(str(tmp_path))
    assert (tmp_path / out.split("\\")[-1].split("/")[-1]).exists()


# --- the end of a file -------------------------------------------------------

def _run_to_the_end(engine, sample_video, pump):
    engine.load_file(sample_video)
    engine.play()
    engine.set_speed(4.0)
    assert pump(lambda: engine.at_end(), timeout=8.0), "the sample never reached its end"


def test_play_at_the_end_starts_the_file_again(engine, sample_video, pump):
    ended = []
    engine.file_ended.connect(lambda: ended.append(1))
    _run_to_the_end(engine, sample_video, pump)
    assert not engine.is_playing(), "keep_open leaves it paused on the last frame"
    engine.toggle_play()
    assert pump(lambda: not engine.at_end() and engine.is_playing(), timeout=2.0)
    assert engine._time_pos < 2.0, "it started again from the beginning"
    assert len(ended) == 1


def test_the_end_is_reported_again_after_a_replay(engine, sample_video, pump):
    ended = []
    engine.file_ended.connect(lambda: ended.append(1))
    _run_to_the_end(engine, sample_video, pump)
    engine.toggle_play()
    assert pump(lambda: len(ended) >= 2, timeout=8.0), "the second end of the same file was not reported"


def test_toggle_in_the_middle_still_just_pauses(engine, sample_video, pump):
    engine.load_file(sample_video)
    engine.play()
    assert pump(lambda: engine._time_pos > 0.2, timeout=3.0)
    engine.toggle_play()
    assert not engine.is_playing() and not engine.at_end()
