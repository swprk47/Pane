"""Audio / subtitle tracks: naming (pure) and selection / sync on a real engine."""
import pytest

from core.tracks import AUDIO, SUB, format_delay, language_name, list_tracks

RAW = [
    {"id": 1, "type": "video", "codec": "h264"},
    {"id": 1, "type": "audio", "lang": "kor", "codec": "aac", "demux-channel-count": 2, "selected": True},
    {"id": 2, "type": "audio", "lang": "eng", "codec": "ac3", "demux-channel-count": 6},
    {"id": 3, "type": "audio", "codec": "eac3", "demux-channel-count": 8, "title": "Commentary"},
    {"id": 1, "type": "sub", "lang": "kor", "codec": "subrip", "selected": True},
    {"id": 2, "type": "sub", "codec": "ass"},
    {"id": 3, "type": "sub", "lang": "kor", "codec": "subrip", "external": True,
     "external-filename": r"C:\Videos\Movie.ko.srt"},
]


def test_language_names():
    assert language_name("kor") == "한국어"
    assert language_name("en") == "영어"
    assert language_name("pt-BR") == "포르투갈어"
    assert language_name("xyz") == "xyz"
    assert language_name("und") == ""
    assert language_name(None) == ""


def test_audio_rows_show_language_codec_and_channels():
    rows = list_tracks(RAW, AUDIO)
    assert [(r.id, r.name, r.detail, r.selected) for r in rows] == [
        (1, "한국어", "AAC · 2ch", True),
        (2, "영어", "AC3 · 5.1", False),
        (3, "Commentary", "E-AC3 · 7.1", False),
    ]


def test_subtitle_rows_say_embedded_or_external():
    rows = list_tracks(RAW, SUB)
    assert [(r.id, r.name, r.detail, r.external) for r in rows] == [
        (1, "한국어", "내장 · SRT", False),
        (2, "트랙 2", "내장 · ASS", False),                 # no language, no title: numbered
        (3, "Movie.ko", "외부 · SRT", True),                # an external file is named by the file
    ]


def test_no_tracks():
    assert list_tracks([], AUDIO) == []
    assert list_tracks(None, SUB) == []
    assert list_tracks([{"id": 1, "type": "video"}], AUDIO) == []


@pytest.mark.parametrize("value, text", [
    (0, "0.0초"), (0.3, "+0.3초"), (-0.1, "-0.1초"), (1.0, "+1.0초"), (0.25, "+0.25초"), (0.001, "0.0초"),
])
def test_format_delay(value, text):
    assert format_delay(value) == text


# --- on a real engine ------------------------------------------------------

@pytest.fixture
def loaded(engine, sample_video, pump):
    engine.load_file(sample_video)
    assert pump(lambda: engine.get_media_info().get("width"), timeout=5)
    return engine


@pytest.fixture
def silence(tmp_path):
    """A 1 s silent wav: the sample video has no audio of its own."""
    import wave
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes(4 * 8000))
    return str(path)


def test_sub_and_audio_delay_steps(loaded):
    assert loaded.change_sub_delay(+0.1) == 0.1
    assert loaded.change_sub_delay(+0.2) == 0.3
    assert loaded.change_sub_delay(-0.4) == -0.1
    assert loaded.get_sub_delay() == -0.1
    assert loaded.change_audio_delay(+0.1) == 0.1
    assert loaded.get_audio_delay() == 0.1
    loaded.reset_sync()
    assert loaded.get_sub_delay() == 0.0
    assert loaded.get_audio_delay() == 0.0


def test_sync_does_not_carry_over_to_the_next_video(loaded, sample_video):
    loaded.change_sub_delay(+0.5)
    loaded.change_audio_delay(-0.2)
    loaded.load_file(sample_video)
    assert loaded.get_sub_delay() == 0.0
    assert loaded.get_audio_delay() == 0.0


def test_external_subtitle_becomes_a_selected_track(loaded, tmp_path, pump):
    srt = tmp_path / "Hello.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    assert loaded.subtitle_tracks() == []
    loaded.set_subtitle(str(srt))
    assert pump(lambda: len(loaded.subtitle_tracks()) == 1)
    track = loaded.subtitle_tracks()[0]
    assert track.name == "Hello" and track.external and track.selected


def test_selecting_a_subtitle_turns_subtitles_on(loaded, tmp_path, pump):
    srt = tmp_path / "A.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
    loaded.set_subtitle(str(srt))
    assert pump(lambda: len(loaded.subtitle_tracks()) == 1)
    loaded.toggle_subtitle_visibility()
    assert loaded.subtitles_visible() is False
    assert loaded.select_subtitle_track(loaded.subtitle_tracks()[0].id) is True
    assert loaded.subtitles_visible() is True


def test_select_audio_track(loaded, silence, pump):
    loaded.mpv.audio_add(silence)
    loaded.mpv.audio_add(silence)                  # two audio tracks to switch between
    assert pump(lambda: len(loaded.audio_tracks()) == 2)
    first, second = loaded.audio_tracks()
    assert loaded.select_audio_track(first.id) is True
    assert pump(lambda: [t.selected for t in loaded.audio_tracks()] == [True, False])
    assert loaded.select_audio_track(second.id) is True
    assert pump(lambda: [t.selected for t in loaded.audio_tracks()] == [False, True])
