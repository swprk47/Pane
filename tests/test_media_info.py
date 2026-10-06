"""Codec / decoder / stream info: reading from mpv, formatting, the panel, the I shortcut."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from core import media_info as mi
from ui.media_info_panel import MediaInfoPanel, WARN, GPU_OK


def info(**over):
    base = {k: None for k in mi._PROPERTIES}
    base.update(over)
    return base


def rows(sections, title):
    return dict(next(r for t, r in sections if t == title))


# --- formatting ------------------------------------------------------------

@pytest.mark.parametrize("bps,expected", [
    (None, "—"), (0, "—"), (96_000, "96 kbps"), (999_000, "999 kbps"),
    (1_000_000, "1.0 Mbps"), (8_400_000, "8.4 Mbps"),
])
def test_format_bitrate(bps, expected):
    assert mi.format_bitrate(bps) == expected


@pytest.mark.parametrize("n,expected", [
    (None, "—"), (512, "512 B"), (2048, "2.0 KB"), (300347, "293.3 KB"),
    (5 * 1024 ** 2, "5.0 MB"), (3 * 1024 ** 3, "3.0 GB"),
])
def test_format_bytes(n, expected):
    assert mi.format_bytes(n) == expected


@pytest.mark.parametrize("sec,expected", [(None, "—"), (59, "0:59"), (125, "2:05"), (7707, "2:08:27")])
def test_format_duration(sec, expected):
    assert mi.format_duration(sec) == expected


def test_format_fps():
    assert mi.format_fps(29.97002997) == "29.97 fps"
    assert mi.format_fps(None) == "—"


def test_decoder_description():
    assert mi.describe_decoder("d3d11va-copy") == "GPU · d3d11va-copy (프레임 복사)"
    assert mi.describe_decoder("d3d11va") == "GPU · d3d11va"
    assert mi.describe_decoder("no") == "CPU (소프트웨어)"
    assert mi.describe_decoder(None) == "CPU (소프트웨어)"


# --- describe() ------------------------------------------------------------

def test_describe_a_typical_h264_aac_file():
    sections = mi.describe(info(
        video_format="h264", video_codec="H.264 / AVC", video_profile="High", width=1920, height=1080,
        container_fps=29.97, video_bitrate=4_200_000, pixel_format="yuv420p", hwdec="d3d11va-copy",
        audio_format="aac", audio_codec="AAC (Advanced Audio Coding)", audio_samplerate=48000,
        audio_channels="stereo", audio_bitrate=128_000,
        container="mov,mp4", file_size=734_003_200, duration=7707, speed=1.25, actual_fps=29.9,
        dropped_vo=2, dropped_decoder=3, vo="libmpv"))
    v, a, f, p = (rows(sections, t) for t in ("비디오", "오디오", "파일", "재생"))
    assert v["코덱"] == "H264 · High"
    assert v["해상도"] == "1920 × 1080"
    assert v["디코더"].startswith("GPU")
    assert v["비트레이트"] == "4.2 Mbps"
    assert a["코덱"] == "AAC" and a["샘플레이트"] == "48 kHz" and a["채널"] == "stereo"
    assert f["크기"] == "700.0 MB" and f["길이"] == "2:08:27"
    assert p["배속"] == "1.25x" and p["버려진 프레임"].startswith("5 ")


def test_describe_without_audio_or_info_yet():
    sections = mi.describe(info())                       # nothing loaded: every value unknown
    assert rows(sections, "오디오") == {"코덱": "오디오 없음"}
    assert rows(sections, "비디오")["코덱"] == "—"
    assert rows(sections, "비디오")["디코더"] == "—"     # no video => no decoder claim


def test_describe_software_decoding():
    sections = mi.describe(info(video_format="hevc", hwdec="no"))
    assert rows(sections, "비디오")["디코더"] == "CPU (소프트웨어)"


def test_plain_text_lists_every_section():
    text = mi.to_plain_text(mi.describe(info(video_format="vp9", width=640, height=360)))
    for header in ("[비디오]", "[오디오]", "[파일]", "[재생]"):
        assert header in text
    assert "코덱: VP9" in text and "해상도: 640 × 360" in text


def test_read_media_info_tolerates_unavailable_properties():
    class Flaky:
        def _get_property(self, name):
            if name == "video-format":
                return "av1"
            raise AttributeError("mpv property does not exist")

    got = mi.read_media_info(Flaky())
    assert got["video_format"] == "av1"
    assert got["audio_format"] is None and got["width"] is None


# --- real media ------------------------------------------------------------

def test_engine_reports_real_file_details(engine, sample_video, pump):
    engine.load_file(sample_video)
    assert pump(lambda: engine.get_media_info()["width"] is not None), "no video info after load"
    got = engine.get_media_info()
    assert got["video_format"] == "h264"
    assert (got["width"], got["height"]) == (640, 360)
    assert got["duration"] == pytest.approx(3.0, abs=0.2)
    assert got["container"] and "mp4" in got["container"]
    assert got["audio_format"] is None                  # the sample has no audio track
    sections = mi.describe(got)
    assert rows(sections, "비디오")["코덱"].startswith("H264")
    assert rows(sections, "비디오")["디코더"].startswith(("GPU", "CPU"))


def test_engine_info_before_loading_does_not_crash(engine):
    sections = mi.describe(engine.get_media_info())
    assert rows(sections, "비디오")["코덱"] == "—"


# --- panel -----------------------------------------------------------------

@pytest.fixture
def panel(qapp):
    host = QWidget()
    host.resize(900, 500)
    p = MediaInfoPanel(host)
    state = {"info": info(video_format="h264", width=1280, height=720, hwdec="d3d11va-copy", container_fps=30.0)}
    p.set_provider(lambda: state["info"])
    p._state = state
    host.show()
    yield p
    host.close()


def test_panel_shows_values_when_opened(panel):
    assert not panel.isVisible()
    panel.show()
    html = panel.body.text()
    assert "H264" in html and "1280 × 720" in html


def test_panel_refreshes_with_the_timer(panel, pump):
    panel.show()
    assert panel._timer.isActive()
    panel._state["info"] = info(video_format="vp9", width=3840, height=2160)
    assert pump(lambda: "3840 × 2160" in panel.body.text(), timeout=2.5)
    assert "VP9" in panel.body.text()


def test_panel_stops_refreshing_when_hidden(panel):
    panel.show()
    panel.hide()
    assert not panel._timer.isActive()


def test_copy_button_puts_the_info_on_the_clipboard(panel):
    panel.show()
    panel.btn_copy.click()
    text = QApplication.clipboard().text()
    assert "코덱: H264" in text and "[비디오]" in text
    assert panel.btn_copy.text() == "복사됨"


def test_close_button_hides_the_panel(panel):
    panel.show()
    panel.btn_close.click()
    assert not panel.isVisible()


def test_hardware_is_accented_and_software_is_flagged():
    gpu = MediaInfoPanel._value_html("디코더", "GPU · d3d11va-copy (프레임 복사)")
    cpu = MediaInfoPanel._value_html("디코더", "CPU (소프트웨어)")
    assert GPU_OK in gpu and WARN not in gpu
    assert WARN in cpu


def test_dropped_frames_are_flagged_only_when_nonzero():
    assert WARN not in MediaInfoPanel._value_html("버려진 프레임", "0 (출력 0 · 디코더 0)")
    assert WARN in MediaInfoPanel._value_html("버려진 프레임", "7 (출력 4 · 디코더 3)")


def test_html_escapes_untrusted_values(panel):
    panel._state["info"] = info(video_format="<b>x</b>", container="a&b")
    panel.show()
    html = panel.body.text()
    assert "<b>x</b>" not in html.lower()                    # no raw tag from the file's metadata
    assert "&lt;B&gt;X&lt;/B&gt;" in html                    # shown as text (codec names are upper-cased)
    assert "a&amp;b" in html


# --- main window -----------------------------------------------------------

def test_i_key_toggles_the_panel_for_loaded_media(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine.get_media_info()["width"] is not None)
    QTest.keyClick(window, Qt.Key_I)
    assert window.info_panel.isVisible()
    assert "H264" in window.info_panel.body.text()
    QTest.keyClick(window, Qt.Key_I)
    assert not window.info_panel.isVisible()


def test_info_without_media_shows_a_hint_instead(window):
    window.toggle_media_info()
    assert not window.info_panel.isVisible()
    assert "먼저" in window.osd.text_label.text()


def test_escape_closes_the_panel_before_anything_else(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(timeout=0.5)
    window.toggle_fullscreen()
    pump(timeout=0.5)
    window.toggle_media_info()
    QTest.keyClick(window, Qt.Key_Escape)
    assert not window.info_panel.isVisible()
    assert window.isFullScreen(), "the first Esc must only close the panel"
    window.toggle_fullscreen()


def test_panel_sits_in_the_top_right_inside_the_window(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(timeout=0.5)
    window.toggle_media_info()
    pump(timeout=0.2)
    p, vp = window.info_panel, window.viewport.geometry()
    assert p.x() >= vp.x() and p.x() + p.width() <= vp.right() + 1
    assert p.y() >= vp.y()
    assert p.x() > vp.x() + vp.width() // 3, "panel should hug the right edge"


def test_panel_follows_a_window_resize(window, sample_video, pump):
    window.load_media_file(sample_video)
    window.toggle_media_info()
    window.resize(900, 560)
    pump(timeout=0.4)
    p, vp = window.info_panel, window.viewport.geometry()
    assert p.x() + p.width() <= vp.right() + 1
