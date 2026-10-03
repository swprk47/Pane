import os
import sys
import urllib.request
import json
import py7zr

def setup_libmpv():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lib_dir = os.path.join(base_dir, "lib", "mpv")
    os.makedirs(lib_dir, exist_ok=True)

    # Check if dll already exists
    dll_path = os.path.join(lib_dir, "mpv-2.dll")
    libmpv_path = os.path.join(lib_dir, "libmpv-2.dll")
    if os.path.exists(dll_path) or os.path.exists(libmpv_path):
        print("mpv library already exists in:", lib_dir)
        return lib_dir

    print("Fetching latest mpv-dev release info from GitHub...")
    api_url = "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Pane-Installer"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    download_url = None
    target_asset_name = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        # Choose standard x86_64 build (not v3 for wider compatibility)
        if name.startswith("mpv-dev-x86_64-") and not name.startswith("mpv-dev-x86_64-v3-") and name.endswith(".7z"):
            download_url = asset.get("browser_download_url")
            target_asset_name = name
            break

    if not download_url:
        # Fallback to any x86_64 dev
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if "mpv-dev-x86_64" in name and name.endswith(".7z"):
                download_url = asset.get("browser_download_url")
                target_asset_name = name
                break

    if not download_url:
        raise RuntimeError("Could not find mpv-dev-x86_64 archive in latest release assets.")

    archive_path = os.path.join(lib_dir, target_asset_name)
    print(f"Downloading {target_asset_name}...")
    urllib.request.urlretrieve(download_url, archive_path)
    print("Download completed. Extracting...")

    with py7zr.SevenZipFile(archive_path, mode='r') as z:
        z.extractall(path=lib_dir)

    # Cleanup archive
    if os.path.exists(archive_path):
        os.remove(archive_path)

    # python-mpv looks for mpv-2.dll or mpv-1.dll
    # If libmpv-2.dll was extracted, copy to mpv-2.dll if needed
    for f in os.listdir(lib_dir):
        if f.lower() in ("libmpv-2.dll", "mpv-2.dll", "libmpv-1.dll", "mpv-1.dll"):
            target_copy = os.path.join(lib_dir, "mpv-2.dll")
            src = os.path.join(lib_dir, f)
            if not os.path.exists(target_copy):
                import shutil
                shutil.copy2(src, target_copy)
            print(f"Found and configured: {f}")

    print("mpv setup successfully completed!")
    return lib_dir

if __name__ == "__main__":
    lib_path = setup_libmpv()
    print("Testing mpv initialization...")
    # Add lib_path to PATH and dll directory
    os.environ["PATH"] = lib_path + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(lib_path)

    import mpv
    player = mpv.MPV()
    print("SUCCESS! mpv initialized successfully. Version:", player.mpv_version)
    player.terminate()
