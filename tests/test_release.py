"""Release plumbing: version, bundled-file paths, error log, About text, release docs, build script."""
import re
import sys
from pathlib import Path

import pytest

from core import app_log, paths, version

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"


# --- version ---------------------------------------------------------------

def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.APP_VERSION)
    assert version.APP_VERSION == version.__version__
    assert version.APP_NAME == "Pane"


# --- paths (source vs packaged app) ---------------------------------------

def test_app_root_is_the_project_when_run_from_source():
    assert not getattr(sys, "frozen", False)
    assert paths.app_root() == ROOT
    assert (paths.ASSETS_DIR / "pane_logo.svg").exists()
    assert (paths.LIB_MPV_DIR / "libmpv-2.dll").exists()


def test_app_root_is_the_bundle_folder_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.app_root() == tmp_path


# --- error log -------------------------------------------------------------

@pytest.fixture
def restore_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)


def test_log_is_not_installed_when_running_from_source(restore_streams, tmp_path):
    before = sys.stdout
    assert app_log.install(path=tmp_path / "x.log") is None
    assert sys.stdout is before and not (tmp_path / "x.log").exists()


def test_log_captures_prints_and_unhandled_errors(restore_streams, tmp_path):
    log = tmp_path / "Pane" / "pane.log"
    assert app_log.install(force=True, path=log) == log
    print("hello from the app")
    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    sys.stdout.flush()
    text = log.read_text(encoding="utf-8")
    assert "start ===" in text
    assert "hello from the app" in text
    assert "UNHANDLED ERROR" in text and "ValueError: boom" in text


def test_log_keeps_its_size_bounded(restore_streams, tmp_path):
    log = tmp_path / "pane.log"
    log.write_bytes(b"x" * (app_log.MAX_BYTES + 5000))
    app_log.install(force=True, path=log)
    sys.stdout.flush()
    assert log.stat().st_size < app_log.MAX_BYTES


def test_log_location_is_under_localappdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\someone\AppData\Local")
    assert str(app_log.log_path()).endswith(r"Pane\pane.log")


# --- About -----------------------------------------------------------------

def test_about_text_has_version_and_support_info(window):
    text = window.about_text()
    assert f"v{version.APP_VERSION}" in text
    assert "mpv:" in text and "Qt for Python:" in text
    assert str(app_log.log_path()) in text
    assert "THIRD_PARTY_NOTICES" in text


# --- release documents -----------------------------------------------------

def test_release_documents_exist_and_are_consistent():
    for name in ("README_RELEASE.txt", "THIRD_PARTY_NOTICES.txt", "LICENSE.txt"):
        assert (RELEASE / name).exists(), name
    readme = (RELEASE / "README_RELEASE.txt").read_text(encoding="utf-8")
    assert version.APP_VERSION in readme.splitlines()[0], "README header must carry the current version"
    for shortcut in ("Space", "Ctrl+O", "Ctrl+S", "Esc", "I "):
        assert shortcut in readme, f"shortcut {shortcut!r} missing from the README"
    for topic in ("SmartScreen", "PC 보호", "업데이트", "pane.log", "알려진 한계"):
        assert topic in readme or topic == "SmartScreen", topic


def test_third_party_notices_cover_the_bundled_components():
    text = (RELEASE / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8").lower()
    for component in ("mpv", "ffmpeg", "pyside6", "qt", "python-mpv", "pywinstyles", "pyinstaller", "lgpl", "gpl"):
        assert component in text, component


def test_readme_documents_every_key_binding_in_the_code():
    """Keys handled in MainWindow.keyPressEvent that a user should know about."""
    code = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
    for key_const in ("Key_Space", "Key_M", "Key_C", "Key_P", "Key_I", "Key_F"):
        assert key_const in code
    readme = (RELEASE / "README_RELEASE.txt").read_text(encoding="utf-8")
    for line in ("Space", "음소거", "자막", "PIP", "재생 정보", "전체화면"):
        assert line in readme


# --- build script ----------------------------------------------------------

def test_build_script_writes_version_info_from_the_single_source():
    from tools import build_release
    path = build_release.write_version_file()
    text = path.read_text(encoding="utf-8")
    major, minor, patch = version.APP_VERSION.split(".")
    assert f"({major}, {minor}, {patch}, 0)" in text
    assert f'StringStruct("ProductVersion", "{version.APP_VERSION}")' in text
    assert f'StringStruct("OriginalFilename", "{version.APP_NAME}.exe")' in text


def test_build_inputs_exist():
    from tools import build_release
    assert build_release.LIBMPV.exists()
    for asset in ("pane.ico", "pane_logo.svg"):
        assert (ROOT / "assets" / asset).exists()


# --- the update release steps ------------------------------------------------------------

def test_third_party_notices_name_pynacl_and_libsodium():
    text = (RELEASE / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8").lower()
    assert "pynacl" in text and "libsodium" in text and "apache" in text


def test_build_release_writes_a_signed_manifest_for_the_installer(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import build_release
    import update_manifest
    from core.updater import parse_manifest

    key = tmp_path / "update.key"
    public = bytes.fromhex(update_manifest.generate_keypair(key))
    installer = tmp_path / "Pane-1.3.0-setup.exe"
    installer.write_bytes(b"MZ installer bytes" * 100)
    out = build_release.write_update_manifest(installer, "1.3.0", build_release.default_installer_url("1.3.0"),
                                              "notes", key, tmp_path / "latest.json")
    manifest = parse_manifest(out.read_bytes(), public)
    assert manifest.version == "1.3.0" and manifest.size == installer.stat().st_size


def test_the_default_installer_url_is_the_release_of_the_same_version_in_the_same_repository():
    sys.path.insert(0, str(ROOT / "tools"))
    import build_release
    from core import update_config
    assert build_release.default_installer_url("1.3.0") == \
        "https://github.com/swprk47/Pane/releases/download/v1.3.0/Pane-1.3.0-setup.exe"
    repo = "https://github.com/swprk47/Pane/releases/"
    assert update_config.UPDATE_MANIFEST_URL.startswith(repo) and build_release.default_installer_url("1.3.0").startswith(repo)


def test_the_release_notes_explain_the_manifest_upload_and_the_key():
    text = (ROOT / "docs" / "RELEASING.md").read_text(encoding="utf-8")
    for needle in ("latest.json", "--sign-key", "back", "Publish", "pre-release"):
        assert needle in text, needle


def test_the_readme_tells_users_about_the_updates():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "업데이트" in text and "1.3.0" in text
