"""Closing the app while the update works: nothing new starts, a running download is abandoned."""
from pathlib import Path

from core import update_checker as uc
from core.updater import Manifest
from test_update_checker import make, names      # noqa: F401  (make is a fixture)
from update_helpers import server                # noqa: F401  (a fixture the make fixture uses)


def test_a_stopped_checker_starts_nothing(make, pump, monkeypatch, server):
    started = []
    monkeypatch.setattr(uc, "launch_installer", lambda path, scope: started.append(path))
    checker, _, events = make()
    checker.check()
    assert pump(lambda: "update_available" in names(events), timeout=5)
    checker.request_stop()
    assert checker.stopping is True
    server.requests.clear()
    checker.check(manual=True)
    checker.download_and_install()
    pump(None, timeout=0.4)
    assert server.requests == [] and started == [], "nothing new after the app is closing"


def test_a_download_that_sees_the_stop_flag_is_abandoned(make, monkeypatch):
    started = []
    monkeypatch.setattr(uc, "launch_installer", lambda path, scope: started.append(path))

    def fake_download(manifest, dest, progress=None, timeout=30.0):
        progress(1, 2)                                   # (the worker reports progress: the stop flag is checked here)
        return Path(dest) / "never.exe"

    monkeypatch.setattr(uc, "download_installer", fake_download)
    checker, _, events = make()
    manifest = Manifest(version="1.3.0", url="http://127.0.0.1/x", sha256="a" * 64, size=2, notes="")
    checker.request_stop()
    errors = []
    checker._bridge.install_error.connect(errors.append)
    checker._download(manifest)
    assert errors and started == []


def test_a_close_during_the_last_step_starts_no_installer(make, monkeypatch):
    """The window closed after the last chunk was reported: the verified file must not be launched (it would relaunch Pane)."""
    started = []
    monkeypatch.setattr(uc, "launch_installer", lambda path, scope: started.append(path))
    checker, _, events = make()

    def fake_download(manifest, dest, progress=None, timeout=30.0):
        checker.request_stop()                           # (closed while the file was being verified and renamed)
        return Path(dest) / "done.exe"

    monkeypatch.setattr(uc, "download_installer", fake_download)
    manifest = Manifest(version="1.3.0", url="http://127.0.0.1/x", sha256="a" * 64, size=2, notes="")
    errors = []
    checker._bridge.install_error.connect(errors.append)
    checker._download(manifest)
    assert errors and started == []


# --- the process must end when the window is closed, whatever the network is doing -----------------------

import subprocess

import pytest
import sys
import textwrap

ROOT = Path(__file__).resolve().parent.parent


def test_the_worker_thread_is_a_daemon_so_a_hanging_request_cannot_hold_the_process(make, monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(uc, "fetch_manifest", lambda *a, **k: gate.wait(30))
    checker, _, events = make()
    checker.check(manual=True)
    assert checker._worker.daemon is True
    assert checker.wait_for_done(300) is False, "still running: wait_for_done gives up after the time it was given"
    checker.request_stop()
    gate.set()
    assert checker.wait_for_done(3000) is True


def test_a_process_with_an_update_check_hanging_on_the_network_still_exits_at_once():
    """The installed app hung on a silent network for up to 10 s (30 s while downloading) after its window was gone."""
    script = textwrap.dedent(f"""
        import sys, threading, time
        sys.path.insert(0, {str(ROOT)!r})
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication([])
        import core.update_checker as uc
        uc.fetch_manifest = lambda *a, **k: threading.Event().wait(60)      # a network that never answers

        class Settings:
            def get_update_check_enabled(self): return True
            def get_last_update_check(self): return 0.0
            def get_update_offer_version(self): return ""
            def get_update_dismissed_version(self): return ""
            def set_last_update_check(self, v): pass
            def set_update_offer_version(self, v): pass

        checker = uc.UpdateChecker(Settings(), "1.0.0", True, "http://127.0.0.1:9/x", bytes(32), scope="user")
        checker.check(manual=True)
        time.sleep(0.4)                       # the request is in flight ... and the program ends now
    """)
    started = __import__("time").time()
    try:
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=12)
    except subprocess.TimeoutExpired:
        pytest.fail("the process was still alive 12 s after its main work ended (a hanging request held it)")
    assert done.returncode == 0, done.stderr.decode(errors="replace")[-400:]
    assert __import__("time").time() - started < 8
