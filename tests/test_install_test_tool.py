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
