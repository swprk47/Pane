"""
Builds the portable Windows release:

    python tools/build_release.py [--no-zip]

    dist/Pane/                      the app folder (Pane.exe + _internal/)
    dist/Pane-<version>-win64.zip   the same folder zipped, with README and license notes

Needs PyInstaller (pip install pyinstaller). Version comes from core/version.py.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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


def folder_size_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args()

    run_pyinstaller(write_version_file())
    app_dir = DIST / APP_NAME
    add_docs(app_dir)
    print(f"[build] app folder: {app_dir}  ({folder_size_mb(app_dir):.0f} MB)")
    if not args.no_zip:
        zip_base = DIST / f"{APP_NAME}-{APP_VERSION}-win64"
        archive = shutil.make_archive(str(zip_base), "zip", root_dir=DIST, base_dir=APP_NAME)
        print(f"[build] zip: {archive}  ({Path(archive).stat().st_size / 1048576:.0f} MB)")


if __name__ == "__main__":
    main()
