"""Characterization tests for the split of main_window.py: what the window does today, written against window-level names so
that they keep passing while the code moves into its own modules (docs/superpowers/plans/2026-10-25-...-split.md).

They pin three kinds of things: the right-click menu's entries, that a signal reaches its handler exactly once (a handler
connected twice would act twice, one connected nowhere would go silent), and the order in which closing is traced."""
import importlib

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu

from core import exit_trace
from core.updater import Manifest
from core.version import APP_VERSION

MANIFEST = Manifest(version="9.9.9", url="https://example.com/p.exe", sha256="a" * 64, size=1000, notes="notes")


def load(window, path, pump):
    window.load_media_file(path)
    assert pump(lambda: window._duration > 0 and window.controller.timeline._duration > 0, timeout=10)
    window.engine.pause()


class Counter:
    """Wraps a callable: counts the calls and still makes them."""

    def __init__(self, original=None, result=None):
        self.calls = []
        self._original = original
        self._result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self._original(*args, **kwargs) if self._original else self._result


# --- the right-click menu ----------------------------------------------------------------------------------------

def _menu_modules():
    modules = [importlib.import_module("ui.main_window")]
    try:
        modules.append(importlib.import_module("ui.context_menu"))
    except ImportError:
        pass
    return [m for m in modules if hasattr(m, "QMenu")]


def test_the_right_click_menu_has_these_entries(window, monkeypatch):
    seen = []

    class FakeMenu(QMenu):
        """Never shown: exec() only writes down what the menu holds."""

        def exec(self, *args, **kwargs):
            def walk(menu, depth=0):
                for a in menu.actions():
                    seen.append(("  " * depth) + ("---" if a.isSeparator() else a.text()
                                                  + (" [checked]" if a.isCheckable() and a.isChecked() else "")
                                                  + (" [disabled]" if not a.isEnabled() else "")))
                    if a.menu():
                        walk(a.menu(), depth + 1)
            walk(self)
            return None

    for module in _menu_modules():
        monkeypatch.setattr(module, "QMenu", FakeMenu)
    window.show_context_menu(QPoint(10, 10))
    assert seen == [
        "파일 열기... (Ctrl+O)", "---", "일시정지 (Space)", "이전 영상 (Shift+,) [disabled]", "다음 영상 (Shift+.) [disabled]",
        "영상이 끝나면 다음 영상 자동 재생 [checked]",
        "재생 속도 (배속)", "  0.8x", "  1x  ✓", "  1.2x", "  1.25x", "  1.4x", "  1.5x", "  1.75x", "  2x", "  ---",
        "  정밀 배속 슬라이더 & 프리셋 설정...",
        "자막 (Subtitles)", "  자막 켜기 / 끄기 (C)", "  외부 자막 파일 선택...", "---",
        "현재 화면 고화질 캡처 (Ctrl+S)", "재생 정보 - 코덱, 디코더 (I)", "PIP 항상 위 모드 (P)", "전체화면 (F)", "---",
        "설정...", f"Pane 정보 (v{APP_VERSION})", "Pane 종료 (Alt+F4)",
    ]


# --- a signal reaches its handler exactly once ------------------------------------------------------------------

def test_hovering_the_bar_shows_the_pill_once(window, sample_video, pump, monkeypatch):
    load(window, sample_video, pump)
    counter = Counter(window.seek_tip.show_at)
    monkeypatch.setattr(window.seek_tip, "show_at", counter)
    tl = window.controller.timeline
    tl.hover_moved.emit(1.0, tl._margin() + tl._span() / 3)
    assert len(counter.calls) == 1
    tl.hover_left.emit()


def test_tracks_ready_loads_the_chapters_once(window, sample_video, pump, monkeypatch):
    load(window, sample_video, pump)
    counter = Counter(result=[])
    monkeypatch.setattr(window.engine, "chapters", counter)
    window.engine.tracks_ready.emit()
    assert len(counter.calls) == 1


def test_a_new_version_offer_reaches_the_card_once(window, monkeypatch):
    counter = Counter(result=None)
    monkeypatch.setattr(window.update_card, "show_offer", counter)
    window.update_checker.update_available.emit(MANIFEST)
    assert len(counter.calls) == 1 and counter.calls[0][0][0] == "9.9.9"


def test_the_thumbnail_and_chapter_switches_reach_the_settings_once(window, monkeypatch):
    thumbs, chapters = Counter(result=None), Counter(result=None)
    monkeypatch.setattr(window.app_settings, "set_thumbnails_enabled", thumbs)
    monkeypatch.setattr(window.app_settings, "set_chapters_visible", chapters)
    window.controller.thumbnails_changed.emit(False)
    window.controller.chapters_changed.emit(False)
    assert len(thumbs.calls) == 1 and len(chapters.calls) == 1


def test_a_key_is_handled_once(window, monkeypatch):
    counter = Counter(result=None)
    monkeypatch.setattr(window, "toggle_mute", counter)
    QTest.keyClick(window, Qt.Key_M)
    assert len(counter.calls) == 1


# --- closing -----------------------------------------------------------------------------------------------------

def test_closing_keeps_the_traced_order(window, monkeypatch):
    stages = []
    monkeypatch.setattr(exit_trace, "stage", lambda name, *a, **k: stages.append(name))
    window.close()
    assert stages == ["update check stopped", "thumbnails closed", "video surface released", "mpv terminated"]
