"""The OSD pill: its content and animation, and which actions are allowed to show it."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ui.osd_widget import GlassOSDWidget, SPEED_COLOR


@pytest.fixture
def osd(qapp):
    host = QWidget()
    host.resize(800, 400)
    o = GlassOSDWidget(host)
    host.show()
    qapp.processEvents()
    yield o
    host.close()


# --- the pill itself -----------------------------------------------------------

def test_text_value_and_accent(osd):
    osd.show_message("배속", "speed", "1.25x", accent=True)
    assert osd.full_text() == "배속 1.25x"
    assert osd.value_label.isVisibleTo(osd)
    assert SPEED_COLOR.lower() in osd.value_label.styleSheet().lower()
    osd.show_message("볼륨", "volume_high", "70%")
    assert SPEED_COLOR.lower() not in osd.value_label.styleSheet().lower()


def test_no_value_hides_the_value_label(osd):
    osd.show_message("캡처 저장됨", "screenshot")
    assert osd.full_text() == "캡처 저장됨"
    assert not osd.value_label.isVisibleTo(osd)


def test_grows_open_then_folds_up_and_hides(osd, pump):
    osd.show_message("볼륨", "volume_high", "70%")
    assert osd.isVisible()
    assert pump(lambda: osd._t == 1.0, timeout=1.5)               # grew out of the top edge
    assert pump(lambda: osd._t < 1.0, timeout=3.0)                # folding up
    assert pump(lambda: not osd.isVisible(), timeout=2.0)


def test_a_new_message_while_open_swaps_the_content_and_stays(osd, pump):
    osd.show_message("볼륨", "volume_high", "70%")
    assert pump(lambda: osd._t == 1.0, timeout=1.5)
    pump(timeout=0.6)
    osd.show_message("볼륨", "volume_high", "75%")                # (the timer starts over)
    assert osd.full_text() == "볼륨 75%"
    pump(timeout=0.6)
    assert osd.isVisible() and osd._t == 1.0                       # the first message's second would be up by now


def test_a_message_while_folding_opens_it_again(osd, pump):
    osd.show_message("볼륨", "volume_high", "70%")
    assert pump(lambda: osd._t < 1.0 and osd._closing, timeout=4.0)
    osd.show_message("볼륨", "volume_high", "80%")
    assert pump(lambda: osd._t == 1.0, timeout=1.5)
    assert osd.isVisible()


def test_it_sits_centred_at_the_top_edge(osd):
    osd.place(400, 0)
    osd.show_message("배속", "speed", "1.25x")
    assert abs(osd.geometry().center().x() - 400) <= 1
    assert osd.geometry().top() == 0


# --- who may show it -----------------------------------------------------------

@pytest.fixture
def ready(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine.get_media_info().get("width"), timeout=5)
    window.engine.pause()                      # (the 3 s sample would end - and say "재생 완료" - during a test)
    window.engine.seek(0.5, "absolute")
    pump(timeout=0.3)
    window.osd.hide()
    window.osd.hold_timer.stop()
    return window


def _shows_osd(window, pump, action) -> bool:
    window.osd.hide()
    window.osd._t = 0.0
    action()
    pump(timeout=0.15)
    return window.osd.isVisible()


def test_keyboard_volume_shows_the_value_but_the_mouse_does_not(ready, pump):
    ready.engine.set_volume(50)
    assert not _shows_osd(ready, pump, lambda: ready.controller.volume_changed.emit(60.0))      # the volume popup
    assert _shows_osd(ready, pump, lambda: QTest.keyClick(ready, Qt.Key_Up))
    assert ready.osd.full_text() == "볼륨 65%"


def test_volume_notice_never_goes_past_the_ends(ready, pump):
    ready.engine.set_volume(100)
    QTest.keyClick(ready, Qt.Key_Up)
    assert ready.osd.full_text() == "볼륨 100%"
    ready.engine.set_volume(0)
    QTest.keyClick(ready, Qt.Key_Down)
    assert ready.osd.full_text() == "볼륨 0%"


def test_keyboard_mute_shows_but_the_button_does_not(ready, pump):
    assert not _shows_osd(ready, pump, lambda: ready.controller.mute_clicked.emit())
    assert _shows_osd(ready, pump, lambda: QTest.keyClick(ready, Qt.Key_M))
    assert ready.osd.full_text() == "음소거 해제"


def test_keyboard_speed_shows_but_the_speed_panel_does_not(ready, pump):
    assert not _shows_osd(ready, pump, lambda: ready.speed_popup.speed_selected.emit(1.5))
    ready.engine.set_speed(1.0)
    pump(timeout=0.2)
    assert _shows_osd(ready, pump, lambda: QTest.keyClick(ready, Qt.Key_BracketRight))
    assert ready.osd.full_text() == "배속 1.10x"
    assert _shows_osd(ready, pump, lambda: QTest.keyClick(ready, Qt.Key_Backslash))
    assert ready.osd.full_text() == "배속 1.00x"


def test_subtitle_key_shows_but_the_panel_switch_does_not(ready, pump):
    assert not _shows_osd(ready, pump, lambda: ready._set_subtitles_visible(False))
    assert _shows_osd(ready, pump, lambda: QTest.keyClick(ready, Qt.Key_C))
    assert ready.osd.full_text() == "자막 켬"


@pytest.mark.parametrize("name, action", [
    ("seek", lambda w: w.seek_relative(-0.2)),
    ("seek key", lambda w: QTest.keyClick(w, Qt.Key_Left)),   # (backwards: forwards would reach the end of the 3 s sample)
    ("frame step", lambda w: QTest.keyClick(w, Qt.Key_Period)),
    ("fullscreen", lambda w: w.toggle_fullscreen()),
    ("pip", lambda w: w.toggle_pip_mode()),
])
def test_things_you_can_see_happen_show_no_notice(ready, pump, name, action):
    assert not _shows_osd(ready, pump, lambda: action(ready)), name
    if name == "fullscreen":
        ready.toggle_fullscreen()
    if name == "pip":
        ready.toggle_pip_mode()


def test_notices_and_warnings_still_show(ready, pump, tmp_path, monkeypatch):
    monkeypatch.setattr(type(ready.engine), "default_capture_dir", staticmethod(lambda: tmp_path))    # not the desktop
    assert _shows_osd(ready, pump, lambda: ready.take_screenshot())
    assert ready.osd.full_text().startswith("캡처 저장됨")
    ready._current_file = None
    assert _shows_osd(ready, pump, ready.toggle_media_info)
    assert "먼저" in ready.osd.full_text()
