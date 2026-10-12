"""The two switches of the settings panel at the engine level: hardware decoding and the lecture-voice preset."""
import pytest

from core import audio_presets
from core.settings import AppSettings


# --- saved preferences -----------------------------------------------------

def test_hardware_decoding_defaults_to_on_and_is_remembered():
    s = AppSettings()
    assert s.get_hwdec_enabled() is True
    s.set_hwdec_enabled(False)
    assert AppSettings().get_hwdec_enabled() is False


def test_lecture_audio_defaults_to_off_and_is_remembered():
    s = AppSettings()
    assert s.get_lecture_audio() is False
    s.set_lecture_audio(True)
    assert AppSettings().get_lecture_audio() is True


# --- hardware decoding (changes take effect at once, without reloading the video) -----

def test_hardware_decoding_can_be_turned_off_and_on_while_a_video_plays(engine, pump, sample_video):
    engine.load_file(sample_video)
    assert pump(lambda: engine.mpv._get_property("video-format") is not None)
    engine.set_hardware_decoding(False)
    assert engine.hardware_decoding is False
    assert pump(lambda: engine.mpv._get_property("hwdec-current") in ("no", None, ""))
    engine.set_hardware_decoding(True)
    assert engine.hardware_decoding is True


def test_turning_hardware_decoding_on_keeps_the_copy_mode_of_the_render_api(engine):
    """In the player window GL interop is unavailable: it must come back as auto-copy, not plain auto."""
    engine.set_hardware_decoding(False)
    engine.set_hardware_decoding(True)
    expected = "auto-copy" if engine.render_api else "auto"
    assert engine.mpv._get_property("hwdec") == [expected]


# --- the lecture-voice preset ----------------------------------------------

def test_lecture_graph_is_the_one_the_user_picked():
    g = audio_presets.LECTURE_VOICE
    assert g.startswith("[aid1]highpass=f=90")
    assert "acompressor=threshold=-34dB:ratio=4" in g
    assert "alimiter=limit=0.8:attack=1:release=100:level=0" in g, "level=0 keeps the limiter from re-boosting to 0 dBFS"
    assert g.rstrip().endswith("[ao]")


@pytest.fixture
def wav(tmp_path):
    """A 2 s mono wav: a file that has an audio track (the sample video has none)."""
    import struct, wave
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", 800 if (i // 40) % 2 else -800) for i in range(32000)))
    return str(path)


def graph(engine):
    return engine.mpv._get_property("lavfi-complex") or ""


def test_the_filter_is_set_once_the_loaded_file_is_known_to_have_audio(engine, pump, wav):
    engine.set_lecture_audio(True)
    engine.load_file(wav)
    assert pump(lambda: graph(engine) == audio_presets.LECTURE_VOICE)
    engine.set_lecture_audio(False)
    assert engine.lecture_audio is False and graph(engine) == ""


def test_turning_it_on_during_playback_applies_at_once(engine, pump, wav):
    engine.load_file(wav)
    assert pump(lambda: engine.mpv._get_property("audio-codec-name") is not None)
    engine.set_lecture_audio(True)
    assert graph(engine) == audio_presets.LECTURE_VOICE


def test_nothing_loaded_means_no_graph_but_the_choice_is_kept(engine):
    engine.set_lecture_audio(True)
    assert engine.lecture_audio is True and graph(engine) == ""


def test_a_video_without_audio_still_plays_with_the_preset_on(engine, pump, sample_video):
    """With the graph set, mpv refuses a file that has no audio track ("Pad aid1 is not connected"),
    so the graph must not be there for such a file. (Signals, not polling: the 3 s sample reports 0.0 once it ends.)"""
    times = []
    engine.time_pos_changed.connect(times.append)
    engine.set_lecture_audio(True)
    engine.load_file(sample_video)
    engine.play()
    assert pump(lambda: any(t > 0.3 for t in times), timeout=5)
    assert graph(engine) == ""


def test_moving_from_a_video_with_audio_to_one_without_does_not_break_playback(engine, pump, wav, sample_video):
    times = []
    engine.time_pos_changed.connect(times.append)
    engine.set_lecture_audio(True)
    engine.load_file(wav)
    assert pump(lambda: graph(engine) == audio_presets.LECTURE_VOICE)
    times.clear()
    engine.load_file(sample_video)
    engine.play()
    assert pump(lambda: any(t > 0.3 for t in times), timeout=5)
    assert graph(engine) == ""


# --- turning it off again must give the sound back -------------------------------------

def selected_audio(engine):
    return [t["id"] for t in (engine.mpv._get_property("track-list") or []) if t["type"] == "audio" and t["selected"]]


def test_the_audio_track_is_selected_again_after_switching_the_preset_off(engine, pump, wav):
    """mpv leaves the track deselected (aid=False) when the complex graph is removed: silence."""
    engine.load_file(wav)
    assert pump(lambda: selected_audio(engine) == [1])
    for _ in range(3):                                          # (a second round used to fail differently from the first)
        engine.set_lecture_audio(True)
        assert pump(lambda: graph(engine) == audio_presets.LECTURE_VOICE)
        engine.set_lecture_audio(False)
        assert pump(lambda: selected_audio(engine) == [1]), "no audio track selected: the sound is gone"
        assert engine.mpv._get_property("aid") == 1


def test_switching_off_before_the_graph_ever_applied_leaves_the_track_alone(engine, pump, wav):
    engine.load_file(wav)
    assert pump(lambda: selected_audio(engine) == [1])
    engine.set_lecture_audio(False)
    assert selected_audio(engine) == [1]
