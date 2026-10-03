"""
GlassPlayer: Modern Apple Glass-styled Media Player for Windows 11.
Features 0.05x precision speed control, modular customizable controls,
pitch correction, subtitles, PIP mode, and smooth frameless glass UI.
"""
import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup libmpv path before importing Qt / mpv
LIB_MPV = PROJECT_ROOT / "lib" / "mpv"
if LIB_MPV.exists():
    os.environ["PATH"] = str(LIB_MPV) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(LIB_MPV))
        except Exception:
            pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.main_window import MainWindow


def main():
    # High DPI & Modern Font Settings
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("GlassPlayer")
    app.setOrganizationName("GlassPlayer")

    # Set default modern font
    font = QFont("Segoe UI Variable Text", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    # If video file passed as argument, play immediately
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
        if os.path.exists(target_file):
            window.load_media_file(target_file)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
