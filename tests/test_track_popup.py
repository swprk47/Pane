"""The audio / subtitle panel and the sync keys, in the real window."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.tracks import Track
from ui.track_popup import AUDIO_TAB, SUB_TAB, TrackPopup, _Row, _Switch

AUDIO = [Track(1, "audio", "한국어", "AAC · 2ch", True), Track(2, "audio", "영어", "AC3 · 5.1", False)]
SUBS = [Track(1, "sub", "한국어", "내장 · SRT", True), Track(2, "sub", "Movie.ko", "외부 · SMI", False, True)]


def _popup(qapp):
    p = TrackPopup()
    p.set_data(AUDIO, SUBS, True, 0.3, 0.0)
    p.show()
    qapp.processEvents()
    return p


def _rows(p):
    return p.findChildren(_Row)


def test_subtitle_tab_lists_tracks_and_a_load_row(qapp):
    p = _popup(qapp)
    assert p.tab == SUB_TAB
    rows = _rows(p)
    assert [r.name for r in rows] == ["한국어", "Movie.ko", "외부 자막 불러오기…"]
    assert [r.selected for r in rows[:2]] == [True, False]
    assert rows[2].plus
    p.close()


def test_audio_tab_lists_audio_tracks(qapp):
    p = _popup(qapp)
    p.set_tab(AUDIO_TAB)
    assert [r.name for r in _rows(p)] == ["한국어", "영어"]
    assert [r.detail for r in _rows(p)] == ["AAC · 2ch", "AC3 · 5.1"]
    p.close()


def test_clicking_a_row_chooses_that_track(qapp):
    p = _popup(qapp)
    picked = []
    p.subtitle_chosen.connect(picked.append)
    QTest.mouseClick(_rows(p)[1], Qt.LeftButton)
    assert picked == [2]
    p.set_tab(AUDIO_TAB)
    chosen = []
    p.audio_chosen.connect(chosen.append)
    QTest.mouseClick(_rows(p)[1], Qt.LeftButton)
    assert chosen == [2]
    p.close()


def test_load_row_and_switch_emit_their_signals(qapp):
    p = _popup(qapp)
    loads, toggles = [], []
    p.load_subtitle_requested.connect(lambda: loads.append(1))
    p.subtitles_toggled.connect(toggles.append)
    QTest.mouseClick(_rows(p)[-1], Qt.LeftButton)
    QTest.mouseClick(p.findChildren(_Switch)[0], Qt.LeftButton)
    assert loads == [1] and toggles == [False]
    p.close()


def test_no_subtitles_says_so_and_disables_the_switch(qapp):
    p = TrackPopup()
    p.set_data(AUDIO, [], True, 0.0, 0.0)
    p.show()
    qapp.processEvents()
    assert not p.findChildren(_Switch)[0].isEnabled()
    assert [r.name for r in _rows(p)] == ["외부 자막 불러오기…"]      # only the load row; the note is a label
    p.close()


def test_panel_grows_and_shrinks_with_the_tracks(qapp):
    p = _popup(qapp)
    tall = p.height()
    p.set_data(AUDIO, [], True, 0.0, 0.0)
    assert p.height() < tall
    p.close()


# --- in the window ---------------------------------------------------------

@pytest.fixture
def playing(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine.get_media_info().get("width"), timeout=5)
    return window


def test_z_and_x_move_the_subtitle_sync(playing):
    key = lambda k, mod=Qt.NoModifier: QTest.keyClick(playing, k, mod)
    key(Qt.Key_X)
    key(Qt.Key_X)
    assert playing.engine.get_sub_delay() == pytest.approx(0.2)
    key(Qt.Key_Z)
    assert playing.engine.get_sub_delay() == pytest.approx(0.1)
    assert "자막 싱크 +0.1초" in playing.osd.text_label.text()


def test_shift_z_and_x_move_the_audio_delay(playing):
    key = lambda k, mod=Qt.NoModifier: QTest.keyClick(playing, k, mod)
    key(Qt.Key_X, Qt.ShiftModifier)
    assert playing.engine.get_audio_delay() == pytest.approx(0.1)
    key(Qt.Key_Z, Qt.ShiftModifier)
    key(Qt.Key_Z, Qt.ShiftModifier)
    assert playing.engine.get_audio_delay() == pytest.approx(-0.1)
    assert playing.engine.get_sub_delay() == 0.0
    assert "오디오 지연 -0.1초" in playing.osd.text_label.text()


def test_ctrl_z_resets_both(playing):
    key = lambda k, mod=Qt.NoModifier: QTest.keyClick(playing, k, mod)
    key(Qt.Key_X)
    key(Qt.Key_X, Qt.ShiftModifier)
    key(Qt.Key_Z, Qt.ControlModifier)
    assert playing.engine.get_sub_delay() == 0.0
    assert playing.engine.get_audio_delay() == 0.0


def test_sync_keys_do_nothing_without_a_video(window):
    QTest.keyClick(window, Qt.Key_X)
    assert window.engine.get_sub_delay() == 0.0


def test_subtitle_button_opens_and_esc_closes_the_panel(playing, pump):
    playing.controller.subtitle_clicked.emit()
    assert playing.track_popup.isVisible()
    assert playing.controller.hold_visible()              # the controls stay while the panel is open
    QTest.keyClick(playing, Qt.Key_Escape)
    assert not playing.track_popup.isVisible()


def test_panel_shows_the_current_sync_after_a_key(playing, pump):
    playing.controller.subtitle_clicked.emit()
    QTest.keyClick(playing, Qt.Key_X)
    pump(timeout=0.4)
    labels = [l.text() for l in playing.track_popup.findChildren(type(playing.osd.text_label))]
    assert "+0.1초" in labels


def test_c_still_toggles_subtitles(playing):
    before = playing.engine.subtitles_visible()
    QTest.keyClick(playing, Qt.Key_C)
    assert playing.engine.subtitles_visible() is (not before)


def test_panel_sits_in_the_bottom_right_corner(playing, pump):
    from PySide6.QtCore import QPoint
    playing.controller.subtitle_clicked.emit()
    pump(timeout=0.2)
    popup, zone = playing.track_popup, playing.controller.right_zone
    parent = popup.parentWidget()
    assert popup.geometry().right() + 1 == zone.mapTo(parent, QPoint(zone.width(), 0)).x()     # right edge on the margin line
    assert popup.geometry().bottom() < playing.controller.btn_subtitle.mapTo(parent, QPoint(0, 0)).y()   # above the buttons


def test_track_and_speed_panels_sit_above_the_seek_bar(playing, pump):
    from PySide6.QtCore import QPoint
    c = playing.controller
    bar_top = c.timeline.mapTo(playing.track_popup.parentWidget(), QPoint(0, 0)).y()
    c.subtitle_clicked.emit()
    c.speed_button_clicked.emit()
    pump(timeout=0.2)
    assert playing.track_popup.geometry().bottom() < bar_top
    assert playing.speed_popup.geometry().bottom() < bar_top
