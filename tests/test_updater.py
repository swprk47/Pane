"""The update logic: versions, the signed manifest, the verified download, the installer launch."""
import base64
from pathlib import Path
import json

import pytest

from core.updater import Manifest, ManifestError, is_newer, parse_manifest, parse_version, verify_signature

import nacl.signing
from update_helpers import GOOD, INSTALLER, manifest_for, server, signed      # noqa: F401  (server is a fixture)


# --- versions ---------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [("1.3.0", (1, 3, 0)), ("v1.3", (1, 3, 0)), ("1.2.10", (1, 2, 10)), (" 2.0.1 ", (2, 0, 1))])
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize("text", ["abc", "", "1.2.3.4", "1..2", "-1.0.0", "1.x.0"])
def test_parse_version_rejects_what_is_not_a_version(text):
    with pytest.raises(ValueError):
        parse_version(text)


@pytest.mark.parametrize("candidate,current,expected", [
    ("1.3.0", "1.2.0", True), ("1.2.10", "1.2.9", True), ("1.2.0", "1.2.0", False),
    ("1.1.9", "1.2.0", False), ("v2.0", "1.9.9", True),
])
def test_is_newer(candidate, current, expected):
    assert is_newer(candidate, current) is expected


# --- the signed manifest --------------------------------------------------------

def test_a_correctly_signed_manifest_parses():
    raw, public = signed(GOOD)
    m = parse_manifest(raw, public)
    assert m == Manifest(version="1.3.0", url=GOOD["url"], sha256="a" * 64, size=123456, notes="새 기능")


def test_the_notes_are_optional():
    payload = {k: v for k, v in GOOD.items() if k != "notes"}
    raw, public = signed(payload)
    assert parse_manifest(raw, public).notes == ""


def test_a_manifest_signed_by_another_key_is_rejected():
    raw, _ = signed(GOOD)
    other_public = bytes(nacl.signing.SigningKey.generate().verify_key)
    with pytest.raises(ManifestError):
        parse_manifest(raw, other_public)


def test_a_manifest_whose_payload_was_edited_is_rejected():
    raw, public = signed(GOOD)
    envelope = json.loads(raw)
    envelope["payload"] = envelope["payload"].replace("123456", "123457")           # a different size, the old signature
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(envelope).encode("utf-8"), public)


def test_verify_signature_tells_good_from_bad():
    key = nacl.signing.SigningKey.generate()
    sig = key.sign(b"payload").signature
    assert verify_signature(b"payload", sig, bytes(key.verify_key)) is True
    assert verify_signature(b"payload!", sig, bytes(key.verify_key)) is False
    assert verify_signature(b"payload", b"short", bytes(key.verify_key)) is False


@pytest.mark.parametrize("change", [
    {"sha256": None}, {"url": None}, {"size": None}, {"version": None},          # a field missing
    {"size": "123456"}, {"size": 0}, {"size": -5}, {"size": True},               # a wrong size
    {"sha256": "abc"}, {"sha256": "z" * 64}, {"sha256": "a" * 64 + chr(10)},                                  # not 64 hex characters
    {"url": "http://evil.example/Pane.exe"}, {"url": "ftp://example.com/p.exe"}, {"url": "file:///c:/x.exe"},
    {"version": "latest"},
])
def test_missing_or_mistyped_fields_are_rejected_even_when_signed(change):
    payload = dict(GOOD)
    for k, v in change.items():
        if v is None:
            payload.pop(k)
        else:
            payload[k] = v
    raw, public = signed(payload)
    with pytest.raises(ManifestError):
        parse_manifest(raw, public)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/Pane.exe", "http://localhost/Pane.exe", "https://github.com/swprk47/Pane/x.exe"])
def test_https_or_a_local_address_is_accepted(url):
    raw, public = signed({**GOOD, "url": url})
    assert parse_manifest(raw, public).url == url


@pytest.mark.parametrize("raw", [b"<html>login</html>", b"", b"{}", b'{"payload": 5, "signature": "x"}', b'{"payload": "{}"}', b"[1, 2]", b"\xff\xfe"])
def test_garbage_and_html_are_rejected(raw):
    with pytest.raises(ManifestError):
        parse_manifest(raw, bytes(nacl.signing.SigningKey.generate().verify_key))


# --- fetching the manifest and downloading the installer (a real HTTP server on 127.0.0.1) ----------

from core.updater import UpdateError, download_installer, fetch_manifest


def test_fetch_manifest_from_a_server(server):
    raw, public = signed(GOOD)
    server.routes["/latest.json"] = (raw, None)
    assert fetch_manifest(server.base + "/latest.json", public).version == "1.3.0"


def test_fetch_manifest_with_an_html_login_page_raises_manifest_error(server):
    server.routes["/latest.json"] = (b"<html><body>Sign in to the hotel wifi</body></html>", None)
    with pytest.raises(ManifestError):
        fetch_manifest(server.base + "/latest.json", bytes(nacl.signing.SigningKey.generate().verify_key))


def test_fetch_manifest_refuses_a_huge_answer(server):
    server.routes["/latest.json"] = (b"x" * 200_000, None)
    with pytest.raises(ManifestError):
        fetch_manifest(server.base + "/latest.json", bytes(nacl.signing.SigningKey.generate().verify_key))


def test_fetch_manifest_404_raises_update_error(server):
    with pytest.raises(UpdateError):
        fetch_manifest(server.base + "/missing.json", b"\0" * 32)


def test_fetch_manifest_connection_refused_raises_update_error():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                    # (nobody listens here once the socket is closed)
    with pytest.raises(UpdateError):
        fetch_manifest(f"http://127.0.0.1:{port}/latest.json", b"\0" * 32, timeout=2.0)


def test_download_writes_the_file_and_reports_progress(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    seen = []
    path = download_installer(manifest_for(server), tmp_path / "dl", progress=lambda done, total: seen.append((done, total)))
    assert path == tmp_path / "dl" / "Pane-1.3.0-setup.exe"
    assert path.read_bytes() == INSTALLER
    assert seen and seen[-1] == (len(INSTALLER), len(INSTALLER))
    assert [d for d, _ in seen] == sorted(d for d, _ in seen), "progress only grows"


def test_a_file_with_the_wrong_hash_is_deleted_and_raises(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    wrong = manifest_for(server, sha256="0" * 64)
    with pytest.raises(UpdateError):
        download_installer(wrong, tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == [], "no partial or rejected file is left"


def test_a_truncated_download_is_deleted_and_raises(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER[:1000], len(INSTALLER))
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_file_bigger_than_the_manifest_size_is_stopped(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER + b"extra" * 10_000, None)
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_404_for_the_installer_leaves_nothing_behind(server, tmp_path):
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_an_earlier_good_download_survives_a_failed_retry(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    good = download_installer(manifest_for(server), tmp_path / "dl")
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER[:10], len(INSTALLER))
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert good.read_bytes() == INSTALLER


# --- starting the installer ----------------------------------------------------------------------

from core import updater as updater_module
from core.updater import installed_scope, installer_command, launch_installer


@pytest.fixture
def uninstall_keys():
    """Two throw-away registry keys that stand in for the setup's per-user and all-users uninstall entries."""
    import winreg
    base = r"Software\PaneInstalledScopeTmp"
    yield winreg, base
    for name in ("user", "machine"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{base}\\{name}")
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
    except OSError:
        pass


def _register(uninstall_keys, name, location):
    winreg, base = uninstall_keys
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{base}\\{name}") as k:
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, location)


def _hives(uninstall_keys):
    winreg, base = uninstall_keys
    return (("user", winreg.HKEY_CURRENT_USER, f"{base}\\user"), ("machine", winreg.HKEY_CURRENT_USER, f"{base}\\machine"))


def test_the_scope_is_where_the_setup_registered_this_folder(uninstall_keys):
    _register(uninstall_keys, "user", r"C:\Apps\Pane" + chr(92))                 # (Inno writes a trailing backslash)
    _register(uninstall_keys, "machine", r"C:\Program Files\Pane" + chr(92))
    hives = _hives(uninstall_keys)
    assert installed_scope(Path("C:/Apps/Pane"), hives=hives) == "user"
    assert installed_scope(Path("c:/program files/pane"), hives=hives) == "machine", "Windows paths ignore case"


def test_a_folder_the_setup_did_not_register_has_no_scope(uninstall_keys):
    _register(uninstall_keys, "user", r"C:\Apps\Pane" + chr(92))
    hives = _hives(uninstall_keys)
    assert installed_scope(Path("C:/Users/x/Downloads/Pane"), hives=hives) is None
    assert installed_scope(Path("C:/Apps/Pane"), hives=(("user", uninstall_keys[0].HKEY_CURRENT_USER, r"Software\PaneNoSuchKeyTmp"),)) is None


@pytest.mark.parametrize("scope,flag", [("user", "/CURRENTUSER"), ("machine", "/ALLUSERS")])
def test_installer_command_for_each_scope(scope, flag):
    exe = Path(r"C:\Temp\Pane-1.3.0-setup.exe")
    assert installer_command(exe, scope) == [str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                                              "/CLOSEAPPLICATIONS", "/RELAUNCH", flag]


def test_an_unknown_scope_is_refused():
    with pytest.raises(ValueError):
        installer_command(Path("x.exe"), "everyone")


def test_launch_installer_starts_it_detached_and_does_not_wait(monkeypatch):
    calls = []

    class FakeProcess:
        def wait(self, *a, **k):
            raise AssertionError("the app must not wait for the installer: the installer closes the app")

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(updater_module.subprocess, "Popen", fake_popen)
    exe = Path(r"C:\Temp\Pane-1.3.0-setup.exe")
    launch_installer(exe, "user")
    command, kwargs = calls[0]
    assert command == installer_command(exe, "user")
    DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP = 0x00000008, 0x00000200
    assert kwargs["creationflags"] & DETACHED_PROCESS and kwargs["creationflags"] & CREATE_NEW_PROCESS_GROUP
    assert kwargs["close_fds"] is True


def test_launch_installer_failure_is_an_update_error_naming_the_file(monkeypatch):
    def refuse(*a, **k):
        raise OSError(1260, "blocked by policy")

    monkeypatch.setattr(updater_module.subprocess, "Popen", refuse)
    exe = Path(r"C:\Temp\Pane-1.3.0-setup.exe")
    with pytest.raises(UpdateError) as info:
        launch_installer(exe, "user")
    assert str(exe) in str(info.value), "the message tells where the file is so it can be run by hand"


def test_old_installers_and_partial_files_are_removed_from_the_download_folder(tmp_path):
    from core.updater import remove_old_installers
    (tmp_path / "Pane-1.3.0-setup.exe").write_bytes(b"x")
    (tmp_path / "Pane-1.3.1-setup.exe.part").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"keep")
    remove_old_installers(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notes.txt"]
    remove_old_installers(tmp_path / "does-not-exist")          # (no folder yet: nothing to do, no error)


def test_a_download_without_a_length_that_ends_early_is_deleted_and_raises(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER[:1000], "none")      # no Content-Length at all, the connection just ends
    with pytest.raises(UpdateError, match="incomplete"):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_full_disk_is_an_update_error_that_says_so_and_leaves_nothing(server, tmp_path, monkeypatch):
    import errno
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    real_open = open

    class FullDisk:
        def __init__(self, file):
            self._file = file

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._file.close()

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(updater_module, "open", lambda path, mode="r": FullDisk(real_open(path, mode)), raising=False)
    with pytest.raises(UpdateError, match="disk"):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == [], "the half-written file is removed"


def test_a_download_folder_that_cannot_be_written_is_an_update_error(server, tmp_path, monkeypatch):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)

    def refuse(path, mode="r"):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(updater_module, "open", refuse, raising=False)
    with pytest.raises(UpdateError, match="disk"):
        download_installer(manifest_for(server), tmp_path / "dl")


# --- the installer cannot be swapped between the check and the start --------------------------------------

def _sha(data) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def test_the_installer_is_locked_against_writes_and_replacement_from_the_check_on(tmp_path, monkeypatch):
    exe = tmp_path / "Pane-1.3.0-setup.exe"
    exe.write_bytes(INSTALLER)
    other = tmp_path / "evil.exe"
    other.write_bytes(b"MZ-evil")
    attempts = []

    def fake_popen(command, **kwargs):
        for label, attempt in (("write", lambda: open(exe, "r+b")),
                               ("replace", lambda: __import__("os").replace(other, exe)),
                               ("delete", lambda: exe.unlink())):
            try:
                attempt()
                attempts.append((label, "worked"))
            except PermissionError:
                attempts.append((label, "refused"))
        return object()

    monkeypatch.setattr(updater_module.subprocess, "Popen", fake_popen)
    try:
        launch_installer(exe, "user", sha256=_sha(INSTALLER))
        assert attempts == [("write", "refused"), ("replace", "refused"), ("delete", "refused")], attempts
        with pytest.raises(PermissionError):                        # (still held: the app is about to close, the installer runs)
            open(exe, "r+b")
    finally:
        updater_module.release_installer_locks()
    assert exe.read_bytes() == INSTALLER
    with open(exe, "r+b"):                                          # released: the file is free again
        pass


def test_an_installer_that_no_longer_matches_its_hash_is_not_started(tmp_path, monkeypatch):
    exe = tmp_path / "Pane-1.3.0-setup.exe"
    exe.write_bytes(INSTALLER + b"tampered")
    started = []
    monkeypatch.setattr(updater_module.subprocess, "Popen", lambda *a, **k: started.append(a))
    with pytest.raises(UpdateError, match="changed"):
        launch_installer(exe, "user", sha256=_sha(INSTALLER))
    assert started == []
    exe.write_bytes(b"free")                                        # and nothing stays locked


def test_a_missing_installer_is_an_update_error_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(updater_module.subprocess, "Popen", lambda *a, **k: pytest.fail("started a missing file"))
    with pytest.raises(UpdateError):
        launch_installer(tmp_path / "gone.exe", "user", sha256=_sha(INSTALLER))


def test_a_new_download_can_replace_a_file_that_is_still_locked_from_a_try_that_did_not_finish(server, tmp_path, monkeypatch):
    """The administrator prompt was cancelled and the user presses [다시 시도]: the file this app locked must not block it."""
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    dl = tmp_path / "dl"
    first = download_installer(manifest_for(server), dl)
    monkeypatch.setattr(updater_module.subprocess, "Popen", lambda *a, **k: object())
    try:
        launch_installer(first, "user", sha256=_sha(INSTALLER))
        again = download_installer(manifest_for(server), dl)
        assert again.read_bytes() == INSTALLER
    finally:
        updater_module.release_installer_locks()
