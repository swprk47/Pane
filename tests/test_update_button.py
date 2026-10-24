"""The 업데이트 확인 button on the title bar (next to PIP, home screen only): where it sits, how it spins, what it says."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import QWidget

from core.updater import Manifest
from ui.title_bar import GlassTitleBar

MANIFEST = Manifest(version="1.4.1", url="https://example.com/p.exe", sha256="a" * 64, size=1000, notes="notes")


@pytest.fixture
def pills(window, monkeypatch):
    shown = []
    original = window.osd.show_message

    def record(text, icon="", value="", accent=False):
        shown.append((text, icon))
        original(text, icon, value, accent)

    monkeypatch.setattr(window.osd, "show_message", record)
    return shown


def fake_check(window, monkeypatch, outcome, *payload):
    """Replace the network check: `outcome` is the name of the checker signal to emit once it is asked."""
    calls = []

    def check(manual=False):
        calls.append(manual)
        if outcome:
            getattr(window.update_checker, outcome).emit(*payload)

    monkeypatch.setattr(window.update_checker, "check", check)
    return calls


# --- where it sits -------------------------------------------------------------------------------------------------

def test_the_button_sits_between_pip_and_the_window_buttons_with_a_divider(window):
    bar = window.title_bar
    lay = bar.layout()
    order = [lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget()]
    assert order.index(bar.btn_pip) + 1 == order.index(bar.btn_update), "right after PIP"
    assert order.index(bar.btn_update) + 1 == order.index(bar.sep_update) and order.index(bar.sep_update) + 1 == order.index(bar.btn_min)
    assert bar.btn_update.toolTip() == "업데이트 확인"
    assert (bar.btn_update.width(), bar.btn_update.height()) == (28, 28)
    assert bar.btn_update in bar._buttons(), "it fades and goes inert with the other buttons"


def test_it_shows_on_the_home_screen_and_hides_while_a_video_is_open(window, sample_video, pump):
    bar = window.title_bar
    assert bar.btn_update.isVisible() and bar.sep_update.isVisible()
    window.load_media_file(sample_video)
    assert not bar.btn_update.isVisible() and not bar.sep_update.isVisible()
    window._show_file_problem(sample_video, "gone")
    assert bar.btn_update.isVisible() and bar.sep_update.isVisible(), "back on the home screen"


# --- the spinning --------------------------------------------------------------------------------------------------

def render(widget) -> QImage:
    img = QImage(widget.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return img


def test_while_spinning_the_icon_turns_and_it_finishes_the_turn_when_asked_to_stop(window, pump):
    b = window.title_bar.btn_update
    still = render(b)
    b.set_spinning(True)
    assert b.spinning
    seen = set()
    for _ in range(12):
        pump(None, timeout=0.05)
        seen.add(b.angle())
    assert len(seen) > 3 and max(seen) > 0, "the angle changes while it spins"
    assert render(b) != still or b.angle() == 0
    assert pump(lambda: 40 < b.angle() < 300, timeout=3)               # (in the middle of a turn)
    b.set_spinning(False)
    assert b.spinning and b.angle() > 0, "asked to stop in the middle of a turn: it does not snap back"
    before = b.angle()
    assert pump(lambda: b.angle() != before, timeout=2), "it goes on turning"
    assert pump(lambda: not b.spinning, timeout=3), "it ends by itself after the turn it was in"
    assert b.angle() == 0
    assert render(b) == still, "at rest the icon is back where it was"


# --- what pressing does ------------------------------------------------------------------------------------------

def test_pressing_asks_for_a_manual_check_and_says_when_it_is_current(window, monkeypatch, pills, pump):
    calls = fake_check(window, monkeypatch, "up_to_date")
    window.title_bar.btn_update.click()
    assert calls == [True]
    assert pills[0][0] == "확인하는 중…" and pills[-1][0].startswith("최신 버전이에요")
    assert not window.title_bar.btn_update.spinning or pump(lambda: not window.title_bar.btn_update.spinning, timeout=3)


def test_a_failed_check_says_so_with_the_message(window, monkeypatch, pills):
    fake_check(window, monkeypatch, "check_failed", "새 버전을 확인하지 못했어요")
    window.title_bar.btn_update.click()
    assert pills[-1] == ("새 버전을 확인하지 못했어요", "warning")


def test_a_new_version_shows_the_update_card_even_when_that_version_was_dismissed(window, monkeypatch):
    window.app_settings.set_update_dismissed_version("1.4.1")
    fake_check(window, monkeypatch, "update_available", MANIFEST)
    window.title_bar.btn_update.click()
    assert window.update_card.mode == "offer" and window.update_card.isVisible()
    assert "1.4.1" in window.update_card._title


def test_it_does_not_ask_again_while_a_check_is_running(window, monkeypatch, pills):
    calls = fake_check(window, monkeypatch, None)                  # (never answers)
    window.title_bar.btn_update.click()
    window.title_bar.btn_update.click()
    assert calls == [True] and window.title_bar.btn_update.spinning
    window.update_checker.up_to_date.emit()
    window.title_bar.btn_update.click()
    assert calls == [True, True], "free again once it has answered"
    window.update_checker.up_to_date.emit()


def test_a_check_that_never_answers_ends_after_the_timeout(window, monkeypatch, pills, pump):
    monkeypatch.setattr(window, "UPDATE_CHECK_TIMEOUT_MS", 200)
    fake_check(window, monkeypatch, None)
    window.title_bar.btn_update.click()
    assert pump(lambda: pills and pills[-1][0] == "새 버전을 확인하지 못했어요", timeout=3)
    assert pump(lambda: not window.title_bar.btn_update.spinning, timeout=3)


def test_the_about_dialog_check_still_answers(window, monkeypatch):
    """(It shares the asking code with the button.)"""
    fake_check(window, monkeypatch, "up_to_date")
    box = window._build_about_box()
    button = next(b for b in box.buttons() if b.text() == "업데이트 확인")
    window._on_about_check(box, button)
    assert "최신 버전" in box.informativeText()
    box.close()
