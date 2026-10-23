"""tools/install_test.py: the parts that can be checked without installing anything."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import install_test  # noqa: E402


def test_it_refuses_to_run_when_pane_is_running_or_installed(monkeypatch, capsys):
    monkeypatch.setattr(install_test, "pane_pids", lambda under=None: [1234])
    monkeypatch.setattr(install_test, "reg_export", lambda path: (_ for _ in ()).throw(AssertionError("touched the registry")))
    assert install_test.main(["--installer", "x.exe"]) == 2
    monkeypatch.setattr(install_test, "pane_pids", lambda under=None: [])
    monkeypatch.setattr(install_test, "uninstall_entry", lambda: ("HKCU", r"C:\x"))
    assert install_test.main(["--installer", "x.exe"]) == 2


def test_an_update_test_needs_the_signing_key():
    import pytest
    with pytest.raises(SystemExit):
        install_test.main(["--installer", "a.exe", "--update-installer", "b.exe"])


def test_wait_for_returns_as_soon_as_the_condition_holds():
    calls = []
    assert install_test.wait_for(lambda: calls.append(1) or len(calls) == 3, timeout=5, step=0.01) is True
    assert install_test.wait_for(lambda: False, timeout=0.05, step=0.01) is False


def test_the_update_state_is_cleared_between_the_install_and_the_update_phase():
    """The first run of the installed app checks the real GitHub (now "up to date") and writes the time of that check;
    left there, the daily limit would silence the check against the local test server."""
    import winreg
    sub = r"Software\PaneInstallTestTmp\AppSettings"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
            for name in ("last_update_check", "update_offer_version", "update_dismissed_version", "volume"):
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, "x")
        install_test.reset_update_state(sub)
        install_test.reset_update_state(sub)                      # (twice, and with nothing there: no error)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
            left = []
            try:
                i = 0
                while True:
                    left.append(winreg.EnumValue(k, i)[0])
                    i += 1
            except OSError:
                pass
        assert left == ["volume"]
        install_test.reset_update_state(r"Software\PaneInstallTestTmp\NoSuchKey")      # (no key at all: no error)
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\PaneInstallTestTmp")
        except OSError:
            pass
