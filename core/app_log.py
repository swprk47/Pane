r"""
Error log for the packaged app. A windowed exe has no console, so an unhandled error would
otherwise vanish. Everything printed or raised goes to %LOCALAPPDATA%\Pane\pane.log
(kept under ~1 MB). Not used when running from source (the console shows it).
"""
import os
import sys
import time
import traceback
from pathlib import Path

MAX_BYTES = 1_000_000


def log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Pane" / "pane.log"


def install(force: bool = False, path: Path = None):
    """Redirect stdout/stderr to the log file and log uncaught exceptions.
    Only in the frozen app unless force=True (tests)."""
    if not (force or getattr(sys, "frozen", False)):
        return None
    path = path or log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.write_bytes(path.read_bytes()[-MAX_BYTES // 2:])      # keep the newest half
        stream = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    stream.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} start ===\n")
    sys.stdout = sys.stderr = stream

    def hook(exc_type, exc, tb):
        stream.write("UNHANDLED ERROR:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))
        stream.flush()

    sys.excepthook = hook
    return path
