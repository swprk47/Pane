"""
Timed "[exit]" lines for pane.log while the app closes: when something keeps the process alive after its window is gone
(a ghost taskbar button), the last line shows where it stopped. Costs nothing while the app runs.

    [exit] closing
    [exit] update check stopped (0.00 s)         seconds since the line before
    ...
    [exit] interpreter exiting                    the very last thing Python does
"""
import atexit
import time

_last = None


def begin() -> None:
    """The window was asked to close."""
    global _last
    _last = time.perf_counter()
    print("[exit] closing", flush=True)


def stage(name: str) -> None:
    """A step of the shutdown is done; the time since the previous step is shown."""
    global _last
    now = time.perf_counter()
    since = now - (_last if _last is not None else now)
    _last = now
    print(f"[exit] {name} ({since:.2f} s)", flush=True)


def mark(name: str) -> None:
    print(f"[exit] {name}", flush=True)


def install_exit_marker() -> None:
    """Print a last line when the interpreter really ends (a hang after this line's absence is in the teardown)."""
    atexit.register(mark, "interpreter exiting")
