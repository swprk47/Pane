"""
Builds the portable Windows release:

    python tools/build_release.py [--no-zip] [--installer]

    dist/Pane/                      the app folder (Pane.exe + _internal/)
    dist/Pane-<version>-win64.zip   the same folder zipped, with README and license notes
    dist/Pane-<version>-setup.exe   (--installer) Inno Setup installer built from installer/pane.iss

Needs PyInstaller (pip install pyinstaller) and, for --installer, Inno Setup 6
(winget install JRSoftware.InnoSetup). Version comes from core/version.py.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from core.version import APP_NAME, APP_VERSION  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"
LIBMPV = ROOT / "lib" / "mpv" / "libmpv-2.dll"       # mpv-2.dll is an identical copy; one is enough


def write_version_file() -> Path:
    major, minor, patch = (list(map(int, APP_VERSION.split("."))) + [0, 0, 0])[:3]
    tup = f"({major}, {minor}, {patch}, 0)"
    text = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable("040904B0", [
      StringStruct("CompanyName", "{APP_NAME}"),
      StringStruct("FileDescription", "{APP_NAME} video player"),
      StringStruct("FileVersion", "{APP_VERSION}"),
      StringStruct("InternalName", "{APP_NAME}"),
      StringStruct("OriginalFilename", "{APP_NAME}.exe"),
      StringStruct("ProductName", "{APP_NAME}"),
      StringStruct("ProductVersion", "{APP_VERSION}")])]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])])
  ])
'''
    BUILD.mkdir(exist_ok=True)
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def run_pyinstaller(version_file: Path):
    if not LIBMPV.exists():
        sys.exit(f"missing {LIBMPV} (run: python tools/setup_mpv.py)")
    cmd = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"),
        "--name", APP_NAME, "--noconfirm", "--clean", "--windowed",
        "--icon", str(ROOT / "assets" / "pane.ico"),
        "--version-file", str(version_file),
        "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'assets' / 'pane_logo.svg'};assets",
        "--add-data", f"{ROOT / 'assets' / 'pane.ico'};assets",
        "--add-binary", f"{LIBMPV};lib/mpv",
        "--hidden-import", "pywinstyles",
        "--exclude-module", "pytest", "--exclude-module", "tkinter", "--exclude-module", "unittest",
    ]
    print("[build]", " ".join(cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def add_docs(app_dir: Path):
    for name in ("README_RELEASE.txt", "THIRD_PARTY_NOTICES.txt", "LICENSE.txt"):
        src = ROOT / "release" / name
        if src.exists():
            shutil.copy(src, app_dir / name)
        else:
            print(f"[build] note: release/{name} not found, skipped")


def find_iscc() -> Path:
    import os
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    sys.exit("Inno Setup not found (winget install JRSoftware.InnoSetup)")


def build_installer() -> Path:
    import installer_registry
    installer_registry.write()
    iscc = find_iscc()
    script = ROOT / "installer" / "pane.iss"
    print(f"[build] compiling installer with {iscc.name} ...", flush=True)
    subprocess.run([str(iscc), f"/DAppVersion={APP_VERSION}", str(script)], check=True, cwd=ROOT)
    out = DIST / f"{APP_NAME}-{APP_VERSION}-setup.exe"
    print(f"[build] installer: {out}  ({out.stat().st_size / 1048576:.0f} MB)")
    return out


def folder_size_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true")
    ap.add_argument("--installer", action="store_true", help="also build the Inno Setup installer")
    ap.add_argument("--installer-only", action="store_true", help="only the installer, from the existing dist/Pane")
    args = ap.parse_args()

    if args.installer_only:
        build_installer()
        return
    run_pyinstaller(write_version_file())
    app_dir = DIST / APP_NAME
    add_docs(app_dir)
    print(f"[build] app folder: {app_dir}  ({folder_size_mb(app_dir):.0f} MB)")
    if args.installer:
        build_installer()
    if not args.no_zip:
        zip_base = DIST / f"{APP_NAME}-{APP_VERSION}-win64"
        archive = shutil.make_archive(str(zip_base), "zip", root_dir=DIST, base_dir=APP_NAME)
        print(f"[build] zip: {archive}  ({Path(archive).stat().st_size / 1048576:.0f} MB)")


if __name__ == "__main__":
    main()
