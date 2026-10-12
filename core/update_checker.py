"""
The Qt side of the in-app update: checks for a newer version on a worker thread (at most once a day, only in the
installed app, only when switched on) and downloads, verifies and starts the installer when the user asks.

Nothing here touches the network or starts a thread unless a check is really due: an automatic check that is off,
not due or running from source returns at once. The logic itself lives in core/updater.py.

Signals (emitted on the GUI thread):
    update_available(Manifest)   a newer version exists
    up_to_date()                 the check worked, nothing newer
    check_failed(str)            only for a manual check (an automatic one fails silently, with one log line)
    download_progress(int, int)  bytes done, bytes total
    installer_ready(str)         the installer was verified and started; the app should close
    install_failed(str)          nothing was started; the message says where a downloaded file is, if any
"""
import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from core.updater import (ManifestError, UpdateError, download_installer, fetch_manifest, install_scope, is_newer,
                          launch_installer, should_check)


class _Bridge(QObject):
    """Carries a worker thread's results back to the GUI thread (queued signals)."""
    check_done = Signal(object)
    check_error = Signal(str)
    progress = Signal(int, int)
    install_done = Signal(str)
    install_error = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        self._fn()


class UpdateChecker(QObject):
    update_available = Signal(object)
    up_to_date = Signal()
    check_failed = Signal(str)
    download_progress = Signal(int, int)
    installer_ready = Signal(str)
    install_failed = Signal(str)

    def __init__(self, settings, current_version: str, frozen: bool, manifest_url: str, public_key: bytes, parent=None, *,
                 now=time.time, download_dir=None, scope: str = None):
        super().__init__(parent)
        self._settings = settings
        self._current = current_version
        self._frozen = frozen
        self._url = manifest_url
        self._key = public_key
        self._now = now
        self._download_dir = Path(download_dir) if download_dir else Path(tempfile.gettempdir()) / "PaneUpdate"
        self._scope = scope
        self._busy = False
        self.latest = None                         # the Manifest of the newer version, once one was offered
        self._manual = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._bridge = _Bridge()
        self._bridge.check_done.connect(self._on_check_done)
        self._bridge.check_error.connect(self._on_check_error)
        self._bridge.progress.connect(self.download_progress)
        self._bridge.install_done.connect(self._on_install_done)
        self._bridge.install_error.connect(self._on_install_error)

    @property
    def busy(self) -> bool:
        return self._busy

    def wait_for_done(self, msecs: int = 5000) -> bool:
        return self._pool.waitForDone(msecs)

    # --- checking --------------------------------------------------------------------------------
    def check(self, manual: bool = False):
        """An automatic check (manual=False) only runs when it is on, due and in the installed app; a manual one
        (the "check now" button) always runs, except from source where there is nothing to update."""
        if self._busy:
            return
        if not self._frozen:
            if manual:
                self.check_failed.emit("업데이트는 설치해서 쓰는 Pane에서만 확인해요")
            return
        if not manual and (not self._settings.get_update_check_enabled()
                           or not should_check(self._now(), self._settings.get_last_update_check())):
            return
        self._busy = True
        self._manual = manual
        self._pool.start(_Job(self._fetch))

    def _fetch(self):                                   # (worker thread)
        try:
            self._bridge.check_done.emit(fetch_manifest(self._url, self._key))
        except (UpdateError, ManifestError) as e:
            self._bridge.check_error.emit(str(e))
        except Exception as e:                          # a surprise must not kill the thread silently
            self._bridge.check_error.emit(f"{type(e).__name__}: {e}")

    def _on_check_done(self, manifest):
        self._busy = False
        self._settings.set_last_update_check(self._now())
        if is_newer(manifest.version, self._current):
            self.latest = manifest
            self.update_available.emit(manifest)
        else:
            self.up_to_date.emit()

    def _on_check_error(self, message: str):
        self._busy = False
        if self._manual:
            self.check_failed.emit("새 버전을 확인하지 못했어요")
        else:
            print(f"[updates] check failed: {message}")

    # --- installing ------------------------------------------------------------------------------
    def _install_scope(self) -> str:
        if self._scope:
            return self._scope
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return install_scope(Path(sys.executable).parent, Path(local))

    def download_and_install(self):
        """Download the offered installer, verify it and start it (one at a time; nothing without an offer)."""
        if self._busy or self.latest is None:
            return
        self._busy = True
        manifest = self.latest
        self._pool.start(_Job(lambda: self._download(manifest)))

    def _download(self, manifest):                      # (worker thread)
        path = None
        try:
            path = download_installer(manifest, self._download_dir, progress=self._bridge.progress.emit)
            launch_installer(path, self._install_scope())
        except Exception as e:
            self._bridge.install_error.emit(f"{e}" if isinstance(e, UpdateError) else f"{type(e).__name__}: {e} ({path})")
            return
        self._bridge.install_done.emit(str(path))

    def _on_install_done(self, path: str):
        self._busy = False
        self.installer_ready.emit(path)

    def _on_install_error(self, message: str):
        self._busy = False
        self.install_failed.emit(f"업데이트를 설치하지 못했어요: {message}")
