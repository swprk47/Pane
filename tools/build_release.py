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

GITHUB_REPO = "swprk47/Pane"          # where the releases (and the update manifest) live
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


def default_installer_url(version: str) -> str:
    """Where the release asset of `version` will be (the tag is v<version>): the URL put into the update manifest."""
    return f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/{APP_NAME}-{version}-setup.exe"


def write_update_manifest(installer: Path, version: str, url: str, notes: str, key_path, out: Path) -> Path:
    """Sign `latest.json` for `installer` (see tools/update_manifest.py, docs/RELEASING.md)."""
    import update_manifest
    out = Path(out)
    out.write_bytes(update_manifest.make_manifest(installer, version, url, notes, update_manifest.load_private_key(key_path)))
    print(f"[build] update manifest: {out}")
    return out


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
    ap.add_argument("--sign-key", help="private key file: also write dist/latest.json, the signed update manifest")
    ap.add_argument("--installer-url", help="where the installer will be downloaded from (default: this version's GitHub release)")
    ap.add_argument("--notes", default="", help="one line of release notes for the update manifest")
    args = ap.parse_args()
    if args.sign_key and not (args.installer or args.installer_only):
        sys.exit("--sign-key needs --installer (the manifest describes the installer)")

    def sign(installer: Path):
        if args.sign_key:
            write_update_manifest(installer, APP_VERSION, args.installer_url or default_installer_url(APP_VERSION),
                                  args.notes, args.sign_key, DIST / "latest.json")

    if args.installer_only:
        sign(build_installer())
        return
    run_pyinstaller(write_version_file())
    app_dir = DIST / APP_NAME
    add_docs(app_dir)
    print(f"[build] app folder: {app_dir}  ({folder_size_mb(app_dir):.0f} MB)")
    if args.installer:
        sign(build_installer())
    if not args.no_zip:
        zip_base = DIST / f"{APP_NAME}-{APP_VERSION}-win64"
        archive = shutil.make_archive(str(zip_base), "zip", root_dir=DIST, base_dir=APP_NAME)
        print(f"[build] zip: {archive}  ({Path(archive).stat().st_size / 1048576:.0f} MB)")


if __name__ == "__main__":
    main()
