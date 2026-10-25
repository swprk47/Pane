"""The update notice of the main window: the card over the window, the checker behind it, and everything that happens between
the two (an offer, the download, the installer, a failure, the X, the home-screen button, the About box's check). The window
forwards the old names (`update_card`, `update_checker`, `_refresh_update_card`, `_on_about_check`, ...) and keeps the two
timings (`UPDATE_CHECK_TIMEOUT_MS`, `INSTALL_WAIT_MS`) as its own constants, which this reads through it (tests set them there)."""
import sys

from PySide6.QtCore import QObject, QTimer

from core import exit_trace, update_config
from core.update_checker import UpdateChecker
from core.version import APP_VERSION
from ui.start_screen import DOCK_BOTTOM, DOCK_H
from ui.update_card import UpdateCard


class UpdateFlow(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.card = UpdateCard(window.central_widget)
        self._install_wait = QTimer(self)                # the setup was started: Pane should be closed by it soon
        self._install_wait.setSingleShot(True)
        self._install_wait.timeout.connect(self.installer_stalled)
        self._installer_path = ""
        self.offer = None                                # the Manifest of the newer version the checker found
        self._home_check = False                         # the home screen's update check is running
        self.checker = UpdateChecker(window.app_settings, APP_VERSION, getattr(sys, "frozen", False),
                                     update_config.UPDATE_MANIFEST_URL,
                                     bytes.fromhex(update_config.UPDATE_PUBLIC_KEY_HEX), parent=window)

    # --- asking -------------------------------------------------------------------------------------------------

    def ask(self, done):
        """Ask for a version check now (whatever the daily time and the switch say) and call `done(kind, payload)` once
        with ("current", None), ("available", manifest) or ("failed", message). (A check that was already running, the
        automatic one, may end without a word: it does not wait for ever.)"""
        checker = self.checker
        state = {"done": False}
        handlers = {}

        def finish(kind, payload=None):
            if state["done"]:
                return
            state["done"] = True
            for signal, handler in handlers.items():
                try:
                    signal.disconnect(handler)
                except (RuntimeError, TypeError):
                    pass
            done(kind, payload)

        handlers[checker.up_to_date] = lambda: finish("current")
        handlers[checker.update_available] = lambda m: finish("available", m)
        handlers[checker.check_failed] = lambda message: finish("failed", message)
        for signal, handler in handlers.items():
            signal.connect(handler)
        QTimer.singleShot(self.window.UPDATE_CHECK_TIMEOUT_MS, lambda: finish("failed", "새 버전을 확인하지 못했어요"))
        checker.check(manual=True)

    def on_about_check(self, box, button):
        """"업데이트 확인": ask now and show the answer in the dialog; when there is an update the button becomes
        "지금 업데이트"."""
        if button.text() == "지금 업데이트":
            self.start()
            box.close()
            return
        button.setEnabled(False)
        box.setInformativeText("확인하는 중…")

        def done(kind, payload):
            button.setEnabled(True)
            if kind == "current":
                box.setInformativeText(f"최신 버전이에요 (v{APP_VERSION})")
            elif kind == "available":
                box.setInformativeText(f"새 버전이 있어요: {payload.version}")
                button.setText("지금 업데이트")
            else:
                box.setInformativeText(payload)

        self.ask(done)

    def check_from_home(self):
        """The button next to PIP: it turns while the check runs; the answer is a pill at the top (or the update card)."""
        window = self.window
        if self._home_check:
            return
        self._home_check = True
        button = window.title_bar.btn_update
        button.set_spinning(True)
        window.osd.show_message("확인하는 중…", "refresh")

        def done(kind, payload):
            self._home_check = False
            button.set_spinning(False)
            if kind == "current":
                window.osd.show_message(f"최신 버전이에요 (v{APP_VERSION})", "check")
            elif kind == "available":
                self.offer = payload                      # (asked for by hand: shown even if its X was pressed before)
                if self.card.mode not in ("progress", "installing"):
                    self.card.show_offer(payload.version, payload.notes)
                self.refresh_card()
            else:
                window.osd.show_message(payload, "warning")

        self.ask(done)

    # --- the card -------------------------------------------------------------------------------------------

    def on_available(self, manifest):
        self.offer = manifest
        if self.card.mode not in ("progress", "installing") \
                and manifest.version != self.window.app_settings.get_update_dismissed_version():
            self.card.show_offer(manifest.version, manifest.notes)
        self.refresh_card()

    def on_progress(self, done: int, total: int):
        if self.card.mode == "progress":
            self.card.show_progress(done, total)

    def on_installer_ready(self, path: str):
        self._installer_path = path
        self.card.show_installing()
        self._install_wait.start(self.window.INSTALL_WAIT_MS)
        self.refresh_card()

    def installer_stalled(self):
        """The setup was started but Pane is still running a minute later (administrator prompt cancelled, the file
        blocked after it started, the setup failed): say so and keep the file's place, with [다시 시도]."""
        if self.card.mode == "installing":
            self.card.show_failure(f"설치가 시작되지 않았어요. 설치 파일: {self._installer_path}")
            self.refresh_card()

    def on_failed(self, message: str):
        self._install_wait.stop()
        self.card.show_failure(message)
        self.refresh_card()

    def start(self):
        offer = self.offer
        if offer is None:
            return
        self._install_wait.stop()
        self.card.show_offer(offer.version, offer.notes)              # (sets the version the progress text names)
        if self.checker.download_and_install():                       # (False: a check is still running, stay as the offer)
            self.card.show_progress(0, offer.size)
        self.refresh_card()

    def dismiss(self):
        """The X: this version is not announced again (a newer one is); 정보 > 업데이트 확인 still offers it."""
        if self.offer is not None:
            self.window.app_settings.set_update_dismissed_version(self.offer.version)
        self.card.hide_card()

    def card_blocked(self) -> bool:
        """Never over a playing video; the next-video card, the settings panel and a file-error notice come first."""
        window = self.window
        playing = window._current_file is not None and window.engine.is_playing()
        return bool(playing or window.next_up.isVisible() or window.controller.settings_panel is not None
                    or window.viewport.start_screen.has_problem())

    def refresh_card(self):
        """Show or hide the card as the window's state allows (it keeps its content while hidden)."""
        if not hasattr(self.window, "controller"):
            return
        card = self.card
        if card.mode == "hidden" or self.card_blocked():
            card.setVisible(False)
            return
        card.setVisible(True)
        self.place_card()
        card.raise_()

    def place_card(self):
        """Bottom right, like the next-video card: above the controls of a loaded video, above the dock otherwise."""
        window = self.window
        vp = window.viewport.geometry()
        card = self.card
        x = max(vp.x() + 8, vp.right() - card.width() - 24)
        if window._current_file is not None:
            y = vp.bottom() - window.controller.CONTROLS_HEIGHT - card.height() - 6
        else:
            y = vp.bottom() - (DOCK_BOTTOM + DOCK_H) - card.height() - 12
        card.move(x, max(vp.y() + 8, y))

    # --- closing ------------------------------------------------------------------------------------------------

    def request_stop(self):
        self.checker.request_stop()                      # (a download in flight gives up at its next chunk)
        self.checker.wait_for_done(500)
        exit_trace.stage("update check stopped")
