r"""
Error log for the packaged app. A windowed exe has no console, so an unhandled error would
otherwise vanish. Everything printed or raised goes to %LOCALAPPDATA%\Pane\pane.log
(kept under ~1 MB). Not used when running from source (the console shows it).

A crash Python cannot catch (a native one: an access violation in libmpv, say) skips the hook below; faulthandler writes
the Python stack of every thread to the same file at that moment, so the log says what the app was doing.
"""
import contextlib
import faulthandler
import os
import sys
import time
import traceback
from pathlib import Path

MAX_BYTES = 1_000_000
_fault_stream = None               # where faulthandler writes, once install() switched it on


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
    global _fault_stream
    try:
        faulthandler.enable(file=stream, all_threads=True)
        _fault_stream = stream
    except (OSError, RuntimeError, ValueError):
        _fault_stream = None
    return path


@contextlib.contextmanager
def quiet_native_errors():
    """Around mpv.terminate(): libmpv raises and handles an internal exception (0xe24c4a02) there, and faulthandler would
    log it as a crash at every close. A real crash anywhere else is still recorded."""
    paused = _fault_stream is not None and faulthandler.is_enabled()
    if paused:
        faulthandler.disable()
    try:
        yield
    finally:
        if paused:
            try:
                faulthandler.enable(file=_fault_stream, all_threads=True)
            except (OSError, RuntimeError, ValueError):
                pass
