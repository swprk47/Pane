"""
Shared pytest fixtures.

The GUI tests need a real desktop session (Qt widgets, an OpenGL surface and
libmpv); they are not meant for a headless CI box.
"""
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# libmpv lives in lib/mpv; core.player_engine adds it to PATH on import.
SAMPLE_VIDEO = ROOT / "tests" / "assets" / "sample.mp4"
SETTINGS_GROUPS = ("AppSettings", "ControllerLayout", "SpeedSettings")


def pytest_addoption(parser):
    parser.addoption("--run-e2e", action="store_true", default=False,
                     help="also run tests that send real mouse input (they move the cursor)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-e2e") or os.environ.get("PANE_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="sends real mouse input; run with --run-e2e or PANE_E2E=1")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Never touch the user's real saved settings (presets, layout, resume positions)."""
    from PySide6.QtCore import QSettings
    import core.settings as cs

    monkeypatch.setattr(cs, "APP_NAME", "PaneTest")
    monkeypatch.setattr(cs, "LEGACY_APP_NAME", "PaneTestLegacy")  # no migration from real data

    def wipe():
        for group in SETTINGS_GROUPS:
            s = QSettings("PaneTest", group)
            s.clear()
            s.sync()

    wipe()
    yield
    wipe()


@pytest.fixture
def pump(qapp):
    """pump(cond, timeout): run the Qt event loop until cond() is true (or timeout)."""
    def _pump(condition=None, timeout=3.0, step=0.02):
        end = time.time() + timeout
        while time.time() < end:
            qapp.processEvents()
            if condition is not None and condition():
                return True
            time.sleep(step)
        return bool(condition()) if condition is not None else True
    return _pump


@pytest.fixture(scope="session")
def sample_video():
    """A real 3 s, 640x360 mp4 (see tests/assets). Synthetic av://lavfi inputs are
    rejected by PlayerEngine.load_file() and prove nothing about real playback."""
    if not SAMPLE_VIDEO.exists():
        pytest.skip(f"missing {SAMPLE_VIDEO}")
    return str(SAMPLE_VIDEO)


@pytest.fixture
def engine(qapp):
    """Engine without any video/audio output, for logic tests."""
    from core.player_engine import PlayerEngine
    e = PlayerEngine(options_override={"vo": "null", "ao": "null"})
    yield e
    e.terminate()


@pytest.fixture
def window(qapp):
    """The real main window (render-API video surface), shown."""
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    qapp.processEvents()
