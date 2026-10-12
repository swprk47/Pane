"""The update checker: when it runs, what it reports, how it downloads and starts the installer."""
import hashlib
from pathlib import Path

import nacl.signing
import pytest

from core import update_checker as uc
from core.settings import AppSettings
from core.update_checker import UpdateChecker
from core.updater import should_check
from update_helpers import GOOD, INSTALLER, server, signed      # noqa: F401  (server is a fixture)

NOW = 1_000_000.0


# --- the settings and the throttle ------------------------------------------------------------

def test_update_checks_default_to_on_and_the_choice_is_remembered():
    s = AppSettings()
    assert s.get_update_check_enabled() is True
    s.set_update_check_enabled(False)
    assert AppSettings().get_update_check_enabled() is False


def test_the_time_of_the_last_check_is_remembered():
    s = AppSettings()
    assert s.get_last_update_check() == 0.0
    s.set_last_update_check(NOW)
    assert AppSettings().get_last_update_check() == NOW


@pytest.mark.parametrize("last,expected", [
    (0.0, True), (NOW - 86400, True), (NOW - 86399, False), (NOW - 10, False), (NOW + 5000, True),      # (a clock set back)
])
def test_should_check(last, expected):
    assert should_check(NOW, last) is expected


# --- the checker ---------------------------------------------------------------------------------

@pytest.fixture
def make(server, qapp, tmp_path):
    made = []

    def build(current="1.2.0", frozen=True, enabled=True, last=0.0, version="1.3.0", body=INSTALLER, serve_manifest=True,
              serve_installer=True, installer_body=None):
        key = nacl.signing.SigningKey.generate()
        settings = AppSettings()
        settings.set_update_check_enabled(enabled)
        settings.set_last_update_check(last)
        payload = {**GOOD, "version": version, "url": server.base + f"/Pane-{version}-setup.exe",
                   "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}
        if serve_manifest:
            server.routes["/latest.json"] = (signed(payload, key)[0], None)
        if serve_installer:
            server.routes[f"/Pane-{version}-setup.exe"] = (body if installer_body is None else installer_body, None)
        checker = UpdateChecker(settings, current, frozen, server.base + "/latest.json", bytes(key.verify_key),
                                now=lambda: NOW, download_dir=tmp_path / "dl", scope="user")
        events = []
        checker.update_available.connect(lambda m: events.append(("update_available", m)))
        checker.up_to_date.connect(lambda: events.append(("up_to_date", None)))
        checker.check_failed.connect(lambda msg: events.append(("check_failed", msg)))
        checker.download_progress.connect(lambda d, t: events.append(("progress", (d, t))))
        checker.installer_ready.connect(lambda p: events.append(("installer_ready", p)))
        checker.install_failed.connect(lambda msg: events.append(("install_failed", msg)))
        made.append(checker)
        return checker, settings, events

    yield build
    for checker in made:
        checker.wait_for_done(5000)


def names(events):
    return [n for n, _ in events if n != "progress"]


@pytest.mark.parametrize("kwargs", [dict(enabled=False), dict(last=NOW - 100), dict(frozen=False)], ids=["off", "not due", "from source"])
def test_an_automatic_check_is_skipped_when_off_or_not_due_or_from_source(make, pump, server, kwargs):
    checker, settings, events = make(**kwargs)
    checker.check()
    pump(None, timeout=0.4)
    assert server.requests == [], "no request at all: no thread, no network"
    assert events == [] and checker.busy is False


def test_a_manual_check_ignores_the_throttle_and_the_off_switch(make, pump, server):
    checker, settings, events = make(enabled=False, last=NOW - 10)
    checker.check(manual=True)
    assert pump(lambda: names(events), timeout=5)
    assert names(events) == ["update_available"] and server.requests == ["/latest.json"]


def test_a_manual_check_from_a_source_run_says_updates_need_the_installed_app(make, pump, server):
    checker, _, events = make(frozen=False)
    checker.check(manual=True)
    assert pump(lambda: events, timeout=2)
    assert names(events) == ["check_failed"] and server.requests == []


def test_a_newer_version_emits_update_available_and_records_the_time(make, pump):
    checker, settings, events = make()
    checker.check()
    assert pump(lambda: names(events), timeout=5)
    kind, manifest = events[0]
    assert kind == "update_available" and manifest.version == "1.3.0"
    assert settings.get_last_update_check() == NOW
    assert names(events) == ["update_available"]


@pytest.mark.parametrize("current,offered", [("1.3.0", "1.3.0"), ("1.4.0", "1.3.0")], ids=["equal", "lower"])
def test_an_equal_or_lower_version_is_up_to_date_and_never_offered(make, pump, current, offered):
    checker, settings, events = make(current=current, version=offered)
    checker.check()
    assert pump(lambda: names(events), timeout=5)
    assert names(events) == ["up_to_date"]
    assert settings.get_last_update_check() == NOW


def test_a_failed_automatic_check_is_silent_and_is_tried_again_next_time(make, pump, server):
    checker, settings, events = make(serve_manifest=False)
    checker.check()
    assert pump(lambda: server.requests, timeout=5)
    pump(None, timeout=0.5)
    assert events == [], "nothing for the user"
    assert settings.get_last_update_check() == 0.0, "a failure does not count as a check"


def test_a_failed_manual_check_is_reported(make, pump, server):
    checker, _, events = make(serve_manifest=False)
    checker.check(manual=True)
    assert pump(lambda: events, timeout=5)
    assert names(events) == ["check_failed"] and events[0][1]


def test_a_login_page_instead_of_the_manifest_is_a_failure_not_a_crash(make, pump, server):
    checker, settings, events = make()
    server.routes["/latest.json"] = (b"<html>Sign in to continue</html>", None)
    checker.check(manual=True)
    assert pump(lambda: events, timeout=5)
    assert names(events) == ["check_failed"]


def test_download_and_install_verifies_then_starts_the_installer_once(make, pump, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(uc, "launch_installer", lambda path, scope: started.append((Path(path), scope)))
    checker, _, events = make()
    checker.check()
    assert pump(lambda: "update_available" in names(events), timeout=5)
    checker.download_and_install()
    checker.download_and_install()                       # (a second click while it runs: nothing)
    assert pump(lambda: "installer_ready" in names(events), timeout=8)
    checker.wait_for_done(8000)                          # (let every queued job finish before counting what happened)
    pump(None, timeout=0.3)
    assert started == [(tmp_path / "dl" / "Pane-1.3.0-setup.exe", "user")], "one download, one installer"
    assert names(events).count("installer_ready") == 1
    assert (tmp_path / "dl" / "Pane-1.3.0-setup.exe").read_bytes() == INSTALLER
    progress = [v for n, v in events if n == "progress"]
    assert progress and progress[-1] == (len(INSTALLER), len(INSTALLER))
    assert checker.busy is False


def test_a_bad_download_does_not_start_anything_and_a_retry_is_possible(make, pump, monkeypatch, server):
    started = []
    monkeypatch.setattr(uc, "launch_installer", lambda path, scope: started.append(path))
    checker, _, events = make(installer_body=b"X" * len(INSTALLER))           # right size, wrong bytes
    checker.check()
    assert pump(lambda: "update_available" in names(events), timeout=5)
    checker.download_and_install()
    assert pump(lambda: "install_failed" in names(events), timeout=8)
    assert started == [] and checker.busy is False
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    checker.download_and_install()
    assert pump(lambda: "installer_ready" in names(events), timeout=8)
    assert len(started) == 1


def test_the_installer_failing_to_start_is_reported_with_where_the_file_is(make, pump, monkeypatch, tmp_path):
    def refuse(path, scope):
        raise uc.UpdateError(f"could not start the installer (blocked); it is saved at {path}")

    monkeypatch.setattr(uc, "launch_installer", refuse)
    checker, _, events = make()
    checker.check()
    assert pump(lambda: "update_available" in names(events), timeout=5)
    checker.download_and_install()
    assert pump(lambda: "install_failed" in names(events), timeout=8)
    message = next(v for n, v in events if n == "install_failed")
    assert str(tmp_path / "dl") in message
    assert "installer_ready" not in names(events)


def test_download_and_install_without_an_offer_does_nothing(make, pump, server):
    checker, _, events = make()
    checker.download_and_install()
    pump(None, timeout=0.3)
    assert events == [] and server.requests == []
