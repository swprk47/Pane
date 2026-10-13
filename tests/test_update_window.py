"""The update notice inside the player window: when the card shows, what its buttons do, the about dialog's button."""
import pytest
from PySide6.QtCore import QPoint

from core import update_config
from core.settings import AppSettings
from core.updater import Manifest
from core.version import APP_VERSION

URL = "https://example.com/Pane-1.3.0-setup.exe"


def offer(window, version="1.3.0"):
    m = Manifest(version=version, url=URL, sha256="a" * 64, size=70_000_000, notes="재생바에 시간이 보여요")
    window.update_checker.update_available.emit(m)
    return m


@pytest.fixture
def playing(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine.mpv._get_property("duration") is not None)
    return window


def test_the_window_has_a_checker_set_up_with_the_real_settings(window):
    c = window.update_checker
    assert c._url == update_config.UPDATE_MANIFEST_URL
    assert c._key == bytes.fromhex(update_config.UPDATE_PUBLIC_KEY_HEX)
    assert c._current == APP_VERSION and c._frozen is False, "from source: never offers an update"


def test_the_card_appears_on_the_start_screen_at_the_right_above_the_dock(window, qapp):
    offer(window)
    qapp.processEvents()
    card = window.update_card
    assert card.isVisible() and card.mode == "offer"
    vp = window.viewport.geometry()
    assert abs(card.geometry().right() - (vp.right() - 24)) <= 1
    dock = window.viewport.start_screen.dock_rect()
    dock_top = window.viewport.start_screen.mapTo(window.central_widget, QPoint(0, int(dock.top()))).y()
    assert card.geometry().bottom() < dock_top, "not over the dock"


def test_the_card_sits_above_the_controls_of_a_paused_video_and_hides_while_it_plays(playing, pump):
    w = playing
    offer(w)
    assert pump(lambda: not w.update_card.isVisible(), timeout=3), "never over a playing video"
    w.engine.pause()
    assert pump(lambda: w.update_card.isVisible(), timeout=3)
    controls_top = w.controller.y() + w.controller.height() - w.controller.CONTROLS_HEIGHT
    assert w.update_card.geometry().bottom() < controls_top
    w.engine.play()
    assert pump(lambda: not w.update_card.isVisible(), timeout=3)


def test_the_next_video_card_has_priority(window, qapp):
    offer(window)
    qapp.processEvents()
    window.next_up.start("next.mp4", 5)
    window._refresh_update_card()
    assert not window.update_card.isVisible()
    window.next_up.cancel()
    qapp.processEvents()
    assert window.update_card.isVisible(), "back when the next-video card is gone"


def test_a_file_problem_notice_has_priority_too(window, pump, tmp_path):
    bad = tmp_path / "notes.mp4"
    bad.write_text("not a video\n" * 20)
    offer(window)
    window.load_media_file(str(bad))
    assert pump(lambda: window.viewport.start_screen.has_problem(), timeout=5)
    assert not window.update_card.isVisible()


def test_the_settings_panel_hides_the_card_while_it_is_open(window, qapp):
    offer(window)
    window.controller._open_settings_dialog()
    qapp.processEvents()
    assert not window.update_card.isVisible()
    window.controller.settings_panel.reject()
    qapp.processEvents()
    assert window.update_card.isVisible()


def test_the_x_dismisses_this_version_for_good_and_a_newer_one_comes_back(window, qapp):
    offer(window, "1.3.0")
    window.update_card.btn_close.click()
    qapp.processEvents()
    assert not window.update_card.isVisible() and AppSettings().get_update_dismissed_version() == "1.3.0"
    offer(window, "1.3.0")
    qapp.processEvents()
    assert not window.update_card.isVisible(), "the same version stays dismissed"
    offer(window, "1.4.0")
    qapp.processEvents()
    assert window.update_card.isVisible() and "1.4.0" in window.update_card.title_text


def test_the_update_button_starts_one_download_and_shows_the_progress(window, qapp, monkeypatch):
    started = []
    monkeypatch.setattr(window.update_checker, "download_and_install", lambda: started.append(1) or True)
    offer(window)
    window.update_card.btn_update.click()
    qapp.processEvents()
    assert started == [1] and window.update_card.mode == "progress"
    window.update_checker.download_progress.emit(35_000_000, 70_000_000)
    assert "50%" in window.update_card.detail_text


def test_the_installer_starting_and_a_failure_change_the_card(window, qapp, monkeypatch):
    started = []
    monkeypatch.setattr(window.update_checker, "download_and_install", lambda: started.append(1) or True)
    offer(window)
    window.update_card.btn_update.click()
    window.update_checker.installer_ready.emit("C:/x/Pane-1.3.0-setup.exe")
    assert window.update_card.mode == "installing"
    window.update_checker.install_failed.emit("업데이트를 설치하지 못했어요: blocked")
    assert window.update_card.mode == "failed" and "blocked" in window.update_card.detail_text
    window.update_card.btn_update.click()                       # 다시 시도
    assert started == [1, 1] and window.update_card.mode == "progress"


def test_the_card_follows_the_window_size(window, qapp):
    offer(window)
    window.resize(1300, 800)
    qapp.processEvents()
    assert abs(window.update_card.geometry().right() - (window.viewport.geometry().right() - 24)) <= 1


def test_closing_the_window_stops_the_update_work(qapp):
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    qapp.processEvents()
    w.close()
    qapp.processEvents()
    assert w.update_checker.stopping is True


# --- the about dialog's button ---------------------------------------------------------------

def about_button(box):
    return next(b for b in box.buttons() if b.text() in ("업데이트 확인", "지금 업데이트"))


def test_the_about_box_has_a_check_now_button_next_to_the_diagnostics_one(window):
    box = window._build_about_box()
    texts = [b.text() for b in box.buttons()]
    assert "업데이트 확인" in texts and "진단 정보 복사" in texts


def test_check_now_reports_up_to_date(window, monkeypatch):
    box = window._build_about_box()
    monkeypatch.setattr(window.update_checker, "check", lambda manual=False: window.update_checker.up_to_date.emit())
    about_button(box).click()
    assert "최신 버전" in box.informativeText() and APP_VERSION in box.informativeText()


def test_check_now_reports_a_failure_and_can_be_tried_again(window, monkeypatch):
    box = window._build_about_box()
    monkeypatch.setattr(window.update_checker, "check",
                        lambda manual=False: window.update_checker.check_failed.emit("새 버전을 확인하지 못했어요"))
    about_button(box).click()
    assert "확인하지 못했어요" in box.informativeText()
    assert about_button(box).isEnabled()


def test_check_now_from_a_source_run_says_updates_need_the_installed_app(window):
    box = window._build_about_box()
    about_button(box).click()
    assert "설치해서" in box.informativeText()


def test_check_now_finds_an_update_and_the_button_then_starts_it(window, monkeypatch):
    started = []
    monkeypatch.setattr(window.update_checker, "download_and_install", lambda: started.append(1) or True)
    box = window._build_about_box()
    monkeypatch.setattr(window.update_checker, "check", lambda manual=False: offer(window, "1.3.0"))
    about_button(box).click()
    assert "1.3.0" in box.informativeText() and about_button(box).text() == "지금 업데이트"
    about_button(box).click()
    assert started == [1] and window.update_card.mode == "progress"


def test_an_installer_that_never_takes_over_turns_the_card_into_a_failure_that_names_the_file(window, qapp, pump):
    """UAC cancelled or the setup blocked after it started: Pane is still here, so the card must say so, with the file."""
    offer(window)
    window.INSTALL_WAIT_MS = 50
    window.update_checker.installer_ready.emit("C:/Temp/PaneUpdate/Pane-1.3.0-setup.exe")
    assert window.update_card.mode == "installing"
    assert pump(lambda: window.update_card.mode == "failed", timeout=3)
    assert "Pane-1.3.0-setup.exe" in window.update_card.toolTip()
    assert window.update_card.btn_update.text() == "다시 시도"


def test_a_failure_card_has_the_whole_message_as_its_tooltip(window, qapp):
    offer(window)
    window.update_checker.install_failed.emit("업데이트를 설치하지 못했어요: " + "긴 이유 " * 30)
    assert "긴 이유" in window.update_card.toolTip() and len(window.update_card.toolTip()) > 100


def test_the_update_button_does_not_freeze_the_card_when_the_download_could_not_start(window, qapp, monkeypatch):
    monkeypatch.setattr(window.update_checker, "download_and_install", lambda: False)
    offer(window)
    window.update_card.btn_update.click()
    qapp.processEvents()
    assert window.update_card.mode == "offer"
