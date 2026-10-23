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
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.updater import (ManifestError, UpdateError, download_installer, fetch_manifest, installed_scope, is_newer,
                          launch_installer, remove_old_installers, should_check)


class _Bridge(QObject):
    """Carries a worker thread's results back to the GUI thread (queued signals)."""
    check_done = Signal(object)
    check_error = Signal(str)
    progress = Signal(int, int)
    install_done = Signal(str)
    install_error = Signal(str)


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
        self._stopping = False
        self.latest = None                         # the Manifest of the newer version, once one was offered
        self._manual = False
        self._worker = None                        # a daemon thread: a request hanging on the network must never keep the
                                                   # process alive after the window is gone (it did, for up to 10-30 s)
        self._bridge = _Bridge()
        self._bridge.check_done.connect(self._on_check_done)
        self._bridge.check_error.connect(self._on_check_error)
        self._bridge.progress.connect(self.download_progress)
        self._bridge.install_done.connect(self._on_install_done)
        self._bridge.install_error.connect(self._on_install_error)

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def stopping(self) -> bool:
        return self._stopping

    def request_stop(self):
        """The app is closing: nothing new starts and a running download gives up at its next chunk (its partial file
        is removed). A request that is stuck on the network is simply left behind: the thread is a daemon."""
        self._stopping = True

    def wait_for_done(self, msecs: int = 5000) -> bool:
        """Wait up to `msecs` for the running job; False when it is still running."""
        worker = self._worker
        if worker is None:
            return True
        worker.join(msecs / 1000.0)
        return not worker.is_alive()

    def _start_worker(self, fn) -> None:
        self._worker = threading.Thread(target=fn, name="update-worker", daemon=True)
        self._worker.start()

    # --- checking --------------------------------------------------------------------------------
    def check(self, manual: bool = False):
        """An automatic check (manual=False) only runs when it is on, due and in the installed app; a manual one
        (the "check now" button) always runs, except from source where there is nothing to update."""
        if self._busy or self._stopping:
            return
        if not self._frozen or self._install_scope() is None:      # (from source, or a copy the setup did not install)
            if manual:
                self.check_failed.emit("업데이트는 설치해서 쓰는 Pane에서만 확인해요")
            return
        if not manual and (not self._settings.get_update_check_enabled()
                           or not (self._has_pending_offer()
                                   or should_check(self._now(), self._settings.get_last_update_check()))):
            return
        self._busy = True
        self._manual = manual
        self._start_worker(self._fetch)

    def _has_pending_offer(self) -> bool:
        """An offer that was found earlier and is still newer than this build: the next start checks at once instead of
        waiting for the daily time, so a notice that was ignored comes back."""
        offered = self._settings.get_update_offer_version()
        try:
            return bool(offered) and is_newer(offered, self._current)
        except ValueError:
            return False

    def _fetch(self):                                   # (worker thread)
        remove_old_installers(self._download_dir)       # (what the last update left: about 70 MB each)
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
            self._settings.set_update_offer_version(manifest.version)
            self.update_available.emit(manifest)
        else:
            self._settings.set_update_offer_version("")
            self.up_to_date.emit()

    def _on_check_error(self, message: str):
        self._busy = False
        if self._manual:
            self.check_failed.emit("새 버전을 확인하지 못했어요")
        else:
            print(f"[updates] check failed: {message}")

    # --- installing ------------------------------------------------------------------------------
    def _install_scope(self):
        """"user", "machine", or None for an exe the setup did not install (see core.updater.installed_scope)."""
        return self._scope or installed_scope(Path(sys.executable).parent)

    def download_and_install(self) -> bool:
        """Download the offered installer, verify it and start it (one at a time; nothing without an offer).
        False when nothing was started (a check or another download is running, the app is closing, no offer)."""
        if self._busy or self._stopping or self.latest is None:
            return False
        self._busy = True
        manifest = self.latest
        self._start_worker(lambda: self._download(manifest))
        return True

    def _download(self, manifest):                      # (worker thread)
        path = None
        try:
            def report(done, total):
                if self._stopping:
                    raise UpdateError("the app is closing")
                self._bridge.progress.emit(done, total)

            path = download_installer(manifest, self._download_dir, progress=report)
            if self._stopping:                           # (closed during the last step: do not start what would relaunch us)
                raise UpdateError("the app is closing")
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
