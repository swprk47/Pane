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
