"""
Pane: Modern Apple Glass-styled Media Player for Windows 11.
Features 0.05x precision speed control, modular customizable controls,
pitch correction, subtitles, PIP mode, and smooth frameless glass UI.
"""
import sys
import os
from pathlib import Path

# Add project root to sys.path
# Source checkout: the folder of this file. Packaged app: the PyInstaller bundle folder.
PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT))

# Setup libmpv path before importing Qt / mpv
from core.paths import LIB_MPV_DIR as LIB_MPV
if LIB_MPV.exists():
    os.environ["PATH"] = str(LIB_MPV) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(LIB_MPV))
        except Exception:
            pass

from core import app_log, exit_trace
app_log.install()          # packaged app only: errors go to %LOCALAPPDATA%\Pane\pane.log

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from ui.main_window import MainWindow
from ui.icons import LOGO_ICO


def startup_file(argv):
    """The file Windows (or the command line) asked to open: the first argument that is not a flag. It is passed on
    even when the file is gone, so the player can say so instead of silently opening empty."""
    if len(argv) > 1 and argv[1] and not argv[1].startswith("-"):
        return argv[1]
    return None


def main():
    # High DPI & Modern Font Settings
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    from core.version import APP_VERSION
    app.setApplicationName("Pane")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Pane")

    # Give the process its own identity so the taskbar shows Pane's icon instead
    # of grouping it under python.exe, and use the logo for window / taskbar.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Pane.Player")
        except Exception:
            pass
    if LOGO_ICO.exists():
        app.setWindowIcon(QIcon(str(LOGO_ICO)))

    # Set default modern font
    font = QFont("Segoe UI Variable Text", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    # If a video file was passed as argument, play it immediately (a bad or missing one shows its reason)
    target_file = startup_file(sys.argv)
    if target_file:
        window.load_media_file(target_file)

    exit_trace.install_exit_marker()
    code = app.exec()
    exit_trace.mark("event loop ended")
    sys.exit(code)


if __name__ == "__main__":
    main()
