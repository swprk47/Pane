"""Where bundled files live: the project folder when run from source, the PyInstaller
bundle folder (sys._MEIPASS) when run as the packaged app."""
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


APP_ROOT = app_root()
LIB_MPV_DIR = APP_ROOT / "lib" / "mpv"
ASSETS_DIR = APP_ROOT / "assets"
