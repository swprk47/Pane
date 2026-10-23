"""The settings panel: the tabs (컨트롤 배치 | 성능 | 오디오) and the switches that apply at once."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ui.glass_controller import BUTTON_METADATA, DEFAULT_LAYOUT
from ui.glass_switch import GlassSwitch
from ui.settings_panel import SettingsPanel, LAYOUT_TAB, PERFORMANCE_TAB, AUDIO_TAB


@pytest.fixture
def panel(qapp):
    host = QWidget()
    host.resize(1000, 650)
    host.show()
    p = SettingsPanel(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host)
    p.open()
    qapp.processEvents()
    yield p
    p.reject()
    host.close()


def click_switch(sw):
    QTest.mouseClick(sw, Qt.LeftButton, Qt.NoModifier, sw.rect().center())


# --- tabs ------------------------------------------------------------------

def test_it_opens_on_the_control_layout_tab(panel):
    assert panel.tab == LAYOUT_TAB
    assert panel.editor.isVisible()
    assert not panel.switch_hwdec.isVisible() and not panel.switch_lecture.isVisible()


def test_the_tabs_switch_pages(panel):
    panel.btn_tab_perf.click()
    assert panel.tab == PERFORMANCE_TAB
    assert panel.switch_hwdec.isVisible() and not panel.editor.isVisible()
    panel.btn_tab_audio.click()
    assert panel.tab == AUDIO_TAB
    assert panel.switch_lecture.isVisible() and not panel.switch_hwdec.isVisible()
    panel.btn_tab_layout.click()
    assert panel.tab == LAYOUT_TAB and panel.editor.isVisible()


def test_only_the_selected_tab_looks_selected(panel):
    panel.btn_tab_perf.click()
    assert [b.isActive() for b in (panel.btn_tab_layout, panel.btn_tab_perf, panel.btn_tab_audio)] == [False, True, False]


def test_the_panel_does_not_change_size_between_tabs(panel):
    size = panel.size()
    panel.btn_tab_perf.click()
    assert panel.size() == size
    panel.btn_tab_audio.click()
    assert panel.size() == size


def test_apply_cancel_and_reset_belong_to_the_layout_tab_only(panel):
    assert panel.btn_apply.isVisible() and panel.btn_cancel.isVisible() and panel.btn_reset.isVisible()
    panel.btn_tab_perf.click()
    assert not panel.btn_apply.isVisible() and not panel.btn_reset.isVisible()
    assert panel.btn_close_perf.isVisible()
    panel.btn_tab_audio.click()
    assert panel.btn_close_audio.isVisible()


def test_the_layout_edit_survives_a_visit_to_another_tab(panel):
    panel.editor.move_key("prev_frame", "center", 0)
    panel.btn_tab_perf.click()
    panel.btn_tab_layout.click()
    assert panel.editor.layout()["center"][0] == "prev_frame"


def test_the_close_buttons_close_the_panel(panel):
    finished = []
    panel.finished.connect(finished.append)
    panel.btn_tab_audio.click()
    panel.btn_close_audio.click()
    assert finished == [False] and not panel.isVisible()


# --- the switches: one signal per click, nothing else needed -----------------

def test_switches_start_from_the_values_given(qapp):
    host = QWidget()
    host.resize(900, 600)
    host.show()
    p = SettingsPanel(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host, hwdec_on=False, lecture_audio_on=True)
    p.open()
    assert p.switch_hwdec.checked is False and p.switch_lecture.checked is True
    p.reject()
    host.close()


def test_hardware_decoding_switch_applies_at_once(panel):
    got = []
    panel.hwdec_changed.connect(got.append)
    panel.btn_tab_perf.click()
    assert isinstance(panel.switch_hwdec, GlassSwitch) and panel.switch_hwdec.checked is True
    click_switch(panel.switch_hwdec)
    click_switch(panel.switch_hwdec)
    assert got == [False, True]


def test_lecture_audio_switch_applies_at_once(panel):
    got = []
    panel.lecture_audio_changed.connect(got.append)
    panel.btn_tab_audio.click()
    assert panel.switch_lecture.checked is False
    click_switch(panel.switch_lecture)
    assert got == [True]


def test_clicking_a_row_label_toggles_its_switch_too(panel):
    got = []
    panel.hwdec_changed.connect(got.append)
    panel.btn_tab_perf.click()
    QTest.mouseClick(panel.row_hwdec, Qt.LeftButton, Qt.NoModifier, panel.row_hwdec.rect().center())
    assert got == [False] and panel.switch_hwdec.checked is False


# --- wired to the player ---------------------------------------------------

def test_the_switches_drive_the_engine_and_are_remembered(window, pump):
    c = window.controller
    c._open_settings_dialog()
    p = c.settings_panel
    p.btn_tab_perf.click()
    click_switch(p.switch_hwdec)
    assert window.engine.hardware_decoding is False
    assert window.app_settings.get_hwdec_enabled() is False
    p.btn_tab_audio.click()
    click_switch(p.switch_lecture)
    assert window.engine.lecture_audio is True
    assert window.app_settings.get_lecture_audio() is True
    p.reject()
    # opened again: the panel shows what was chosen
    c._open_settings_dialog()
    q = c.settings_panel
    assert q.switch_hwdec.checked is False and q.switch_lecture.checked is True
    q.reject()


def test_saved_choices_are_applied_when_the_window_starts(qapp, pump):
    from core.settings import AppSettings
    from ui.main_window import MainWindow
    s = AppSettings()
    s.set_hwdec_enabled(False)
    s.set_lecture_audio(True)
    w = MainWindow()
    w.show()
    qapp.processEvents()
    try:
        assert w.engine.hardware_decoding is False
        assert w.engine.lecture_audio is True
    finally:
        w.close()
        qapp.processEvents()


# --- the 일반 tab: the switch for the automatic update check --------------------------------

def test_a_general_tab_has_the_update_switch(panel):
    from ui.settings_panel import GENERAL_TAB
    panel.btn_tab_general.click()
    assert panel.tab == GENERAL_TAB
    assert panel.switch_updates.isVisible() and not panel.editor.isVisible()
    assert panel.switch_updates.checked is True, "on by default"
    assert panel.btn_close_general.isVisible()
    assert panel.btn_tab_general.isActive() and not panel.btn_tab_perf.isActive()


def test_the_update_switch_applies_at_once(panel):
    got = []
    panel.updates_changed.connect(got.append)
    panel.btn_tab_general.click()
    click_switch(panel.switch_updates)
    click_switch(panel.switch_updates)
    assert got == [False, True]


def test_the_panel_keeps_its_size_with_four_tabs(panel):
    size = panel.size()
    for button in (panel.btn_tab_perf, panel.btn_tab_audio, panel.btn_tab_general, panel.btn_tab_layout):
        button.click()
        assert panel.size() == size


def test_the_update_switch_starts_from_the_value_given(qapp):
    host = QWidget()
    host.resize(900, 600)
    host.show()
    p = SettingsPanel(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host, updates_on=False)
    p.open()
    assert p.switch_updates.checked is False
    p.reject()
    host.close()


def test_the_switch_turns_the_automatic_check_off_and_is_remembered(window):
    from core.settings import AppSettings
    c = window.controller
    c._open_settings_dialog()
    p = c.settings_panel
    p.btn_tab_general.click()
    click_switch(p.switch_updates)
    assert AppSettings().get_update_check_enabled() is False
    p.reject()
    c._open_settings_dialog()
    q = c.settings_panel
    assert q.switch_updates.checked is False, "the panel shows what was chosen"
    q.reject()


def test_the_thumbnail_rows_sit_on_the_performance_tab_without_changing_the_panel_size(panel):
    size = panel.size()
    assert not panel.switch_thumbnails.isVisible()
    panel.btn_tab_perf.click()
    assert panel.switch_thumbnails.isVisible() and panel.switch_thumbnails_stop.isVisible()
    assert panel.size() == size


def _panel_with_thumbnails(qapp, on):
    host = QWidget()
    host.resize(900, 600)
    host.show()
    p = SettingsPanel(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host, thumbnails_on=on)
    p.open()
    return host, p


def test_the_stop_row_is_dimmed_once_and_shows_no_pointing_hand_while_it_is_inert(qapp):
    """The row's text is dimmed to 0.45 and the switch dims itself to 0.45 when disabled: the whole row must not be dimmed
    a second time (the switch ended up at about 0.2)."""
    host, p = _panel_with_thumbnails(qapp, False)
    row = p.row_thumbnails_stop
    assert row.graphicsEffect() is None, "no second dimming over the whole row"
    assert not row.isEnabled() and row.cursor().shape() == Qt.ArrowCursor
    for label in (row.title_label, row.desc_label):
        assert label.graphicsEffect() is not None and abs(label.graphicsEffect().opacity() - 0.45) < 1e-6
    p.switch_thumbnails.toggled.emit(True)                                   # thumbnails on: the row comes alive
    assert row.isEnabled() and row.cursor().shape() == Qt.PointingHandCursor
    for label in (row.title_label, row.desc_label):
        assert abs(label.graphicsEffect().opacity() - 1.0) < 1e-6
    p.reject()
    host.close()
