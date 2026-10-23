"""
Install test: runs a built installer for real on this PC, then puts everything back.

    python tools/install_test.py --installer dist/Pane-1.3.0-setup.exe
    python tools/install_test.py --installer dist/Pane-1.3.0-setup.exe --update-installer dist/Pane-1.3.1-setup.exe \
        --sign-key <private.key>

What it does (per-user install into the default folder, the way a friend installs it):
  1. refuses to run when Pane is running or an install of Pane already exists (it must not touch a real one),
  2. backs up HKCU\\Software\\Pane (the settings),
  3. installs silently and checks: files, the uninstall entry and its InstallLocation, `installed_scope` == "user",
  4. starts the installed app and checks it is still alive after a few seconds with nothing new in pane.log's errors,
  5. with --update-installer: serves a signed manifest for that newer installer from 127.0.0.1, starts the app pointed
     at it (PANE_UPDATE_MANIFEST_URL), presses [업데이트] through UI Automation (no mouse is moved) and waits until the
     installed exe is the newer version and running again,
  6. always: stops the app it started, uninstalls, checks the folder and the uninstall entry are gone, restores the
     settings registry from the backup and checks it is identical.

It touches the screen (the app's window appears for a moment) but never the mouse or the keyboard. Exit code 0 = all
checks passed.
"""
import argparse
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from core.updater import UNINSTALL_SUBKEY, installed_scope  # noqa: E402

SETTINGS_KEY = r"HKCU\Software\Pane"
SETUP_FLAGS = ["/CURRENTUSER", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""), flush=True)
    return ok


def powershell(script: str, timeout=60) -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return out.stdout.strip()


def uninstall_entry():
    """(hive name, InstallLocation) of Pane's uninstall entry, or None."""
    for name, hive in (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)):
        try:
            with winreg.OpenKey(hive, UNINSTALL_SUBKEY) as key:
                return name, winreg.QueryValueEx(key, "InstallLocation")[0]
        except OSError:
            continue
    return None


def pane_pids(under: Path = None) -> list:
    where = f"| Where-Object {{ $_.Path -like '{under}\\*' }}" if under else ""
    out = powershell(f"Get-Process Pane -ErrorAction SilentlyContinue {where} | ForEach-Object {{ $_.Id }}")
    return [int(x) for x in out.split()] if out else []


def file_version(exe: Path) -> str:
    return powershell(f"(Get-Item '{exe}').VersionInfo.ProductVersion")


def press_button(pid: int, name: str) -> bool:
    """Press a button of the window of process `pid` by its name through UI Automation (the mouse is not used)."""
    script = f"""
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$w = $A::RootElement.FindFirst('Children', (New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, {pid})))
if ($w) {{
  $b = $w.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, '{name}')))
  if ($b) {{ $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); 'pressed' }}
}}"""
    return powershell(script) == "pressed"


UPDATE_VALUES = ("last_update_check", "update_offer_version", "update_dismissed_version")


def reset_update_state(subkey: str = r"Software\Pane\AppSettings") -> None:
    """Forget what the update check stored. The first run of the installed app checks the real GitHub and writes the
    time of that check; left there, the daily limit would silence the check against the local test server."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
            for name in UPDATE_VALUES:
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
    except OSError:
        pass


def wait_for(condition, timeout, step=1.0):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(step)
    return False


def reg_export(path: Path):
    subprocess.run(["reg", "export", SETTINGS_KEY, str(path), "/y"], capture_output=True)
    return path.exists()


def reg_restore(backup: Path, had_key: bool):
    subprocess.run(["reg", "delete", SETTINGS_KEY, "/f"], capture_output=True)
    if had_key:
        subprocess.run(["reg", "import", str(backup)], capture_output=True)


def serve(directory: Path):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **kw)   # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    handler_cls = http.server.SimpleHTTPRequestHandler
    handler_cls.log_message = lambda *a, **k: None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--installer", required=True, help="the installer under test (it will be installed)")
    ap.add_argument("--update-installer", help="a NEWER installer: also test the update from the first to this one")
    ap.add_argument("--sign-key", help="private key file (needed with --update-installer)")
    args = ap.parse_args(argv)
    installer = Path(args.installer).resolve()
    newer = Path(args.update_installer).resolve() if args.update_installer else None
    if newer and not args.sign_key:
        ap.error("--update-installer needs --sign-key")

    print("Checking the PC is clean ...")
    if pane_pids() or uninstall_entry():
        print("Pane is running or already installed here: not touching it.")
        return 2

    work = Path(tempfile.mkdtemp(prefix="pane-install-test-"))
    backup = work / "settings.reg"
    had_key = reg_export(backup)
    log = Path(os.environ["LOCALAPPDATA"]) / "Pane" / "pane.log"
    log_size = log.stat().st_size if log.exists() else 0
    httpd = None
    exe = None
    try:
        print("Installing ...")
        code = subprocess.run([str(installer), *SETUP_FLAGS], timeout=600).returncode
        check("the setup exits with 0", code == 0, f"exit {code}")
        entry = uninstall_entry()
        if not check("the uninstall entry exists in HKCU (a per-user install)", bool(entry and entry[0] == "HKCU")):
            return 1
        folder = Path(entry[1])
        exe = folder / "Pane.exe"
        check("Pane.exe and the uninstaller are in the install folder", exe.exists() and (folder / "unins000.exe").exists())
        check("it went to the per-user folder",
              str(folder).lower().startswith(os.environ["LOCALAPPDATA"].lower()), str(folder))
        check("installed_scope(folder) reads 'user' from the registry", installed_scope(folder) == "user", str(folder))
        check("installed_scope of another folder is None", installed_scope(Path(r"C:\Users\nobody\Downloads\Pane")) is None)

        print("Starting the installed app ...")
        env = dict(os.environ)
        env.pop("PANE_UPDATE_MANIFEST_URL", None)
        proc = subprocess.Popen([str(exe)], env=env)
        time.sleep(10)
        check("the app is still running after 10 s", proc.poll() is None, f"exit {proc.poll()}")
        new_log = ""
        if log.exists():
            with open(log, "rb") as f:
                f.seek(log_size)
                new_log = f.read().decode("utf-8", "replace")
        check("pane.log has no unhandled error", "UNHANDLED" not in new_log, new_log[-300:])
        subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
        time.sleep(1)

        if newer:
            print("Testing the update ...")
            import update_manifest
            version = file_version(newer) or "9.9.9"
            serve_dir = work / "serve"
            serve_dir.mkdir()
            shutil.copy2(newer, serve_dir / newer.name)
            httpd = serve(serve_dir)
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            (serve_dir / "latest.json").write_bytes(update_manifest.make_manifest(
                newer, version, f"{base}/{newer.name}", "install test", update_manifest.load_private_key(args.sign_key)))
            before = file_version(exe)
            reset_update_state()
            env["PANE_UPDATE_MANIFEST_URL"] = f"{base}/latest.json"
            proc = subprocess.Popen([str(exe)], env=env)
            card = wait_for(lambda: press_button(proc.pid, "업데이트"), 40, step=2)
            check("the update card appeared and [업데이트] was pressed", card)
            if card:
                done = wait_for(lambda: file_version(exe) == version, 150, step=3)
                check(f"the installed exe became {version} (was {before})", done, file_version(exe))
                check("the new version is running from the same folder", wait_for(lambda: bool(pane_pids(folder)), 30))
                check("the entry still points at the same folder", (uninstall_entry() or (0, ""))[1] == entry[1])
            for pid in pane_pids(folder):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            if proc.poll() is None:
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
    finally:
        print("Cleaning up ...")
        if httpd:
            httpd.shutdown()
        if exe is not None:
            for pid in pane_pids(exe.parent):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            time.sleep(1)
            unins = exe.parent / "unins000.exe"
            if unins.exists():
                subprocess.run([str(unins), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=300)
                time.sleep(3)
            check("the uninstaller removed the folder", not exe.parent.exists(), str(exe.parent))
            check("the uninstall entry is gone", uninstall_entry() is None)
        reg_restore(backup, had_key)
        after = work / "settings_after.reg"
        same = (reg_export(after) and after.read_bytes() == backup.read_bytes()) if had_key else not reg_export(after)
        check("the settings registry is back exactly as it was", same)
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(Path(tempfile.gettempdir()) / "PaneUpdate", ignore_errors=True)
    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed" + ("" if not failed else f", {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
