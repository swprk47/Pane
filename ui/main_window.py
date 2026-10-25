import os
import ctypes
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QFileDialog, QApplication
)
from PySide6.QtCore import Qt, QPoint, QEvent, QTimer
from PySide6.QtGui import QKeyEvent

from styles.glass_theme import GLASS_THEME_QSS
from ui.title_bar import GlassTitleBar
from ui.speed_popup import SpeedPopup
from ui.track_popup import TrackPopup
from ui.osd_widget import GlassOSDWidget
from ui.glass_controller import GlassController
from ui.next_up import NextUpCard, NEXT_UP_SECONDS
from core import playlist
from ui.media_info_panel import MediaInfoPanel
from core.version import APP_NAME, APP_VERSION
from core.media_types import open_dialog_filter
from core import app_log, diagnostics, exit_trace, file_errors
from ui.overlay import TopScrim, MiniProgress, CenterBadge, SeekIndicator
from core.tracks import pick_track, track_choice
from ui.icons import get_svg_icon
from core.player_engine import PlayerEngine
from core.tracks import format_delay
from ui import native_window
from core.settings import AppSettings


def apply_windows_11_rounded_corners(hwnd):
    """Apply native Windows 11 rounded window corners."""
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        val = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(val),
            ctypes.sizeof(val)
        )
    except Exception as e:
        print(f"[DWM] Corner preference notice: {e}")


from ui.viewport import VideoViewport  # noqa: F401  (the name stays importable from here)
from ui.context_menu import show_context_menu as _show_context_menu
from ui.key_bindings import KeyRouter
from ui.seek_tips import SeekTips
from ui.bookmark_flow import BookmarkFlow
from ui.help_flow import HelpFlow
from ui.update_flow import UpdateFlow


class MainWindow(QMainWindow):
    """
    Apple Glass Frameless Main Window for Windows 11 with fully integrated player engine.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWindowContainer")
        self.resize(1060, 640)
        self.setMinimumSize(640, 380)

        # Frameless Window Hint & Translucent Container
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(GLASS_THEME_QSS)

        self._is_pip = False
        self._saved_geometry = None
        self._current_file = None
        self._time_pos = 0.0                             # the playback position as the window last knew it
        self._last_problem = None          # what mpv said about the last file that would not open (for the diagnostics)

        self.app_settings = AppSettings()
        self.keys = KeyRouter(self)                      # the keyboard (ui/key_bindings.py)
        self.marks = BookmarkFlow(self)                  # bookmarks and chapters (ui/bookmark_flow.py)

        # A click toggles play/pause AT ONCE (no waiting to see whether a second click follows). If the
        # second click does come (double-click = fullscreen), the toggle is undone. The timer is the window
        # in which a double-click can still arrive.
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(QApplication.doubleClickInterval())
        self._click_timer.timeout.connect(self._disarm_click_undo)
        self._click_undo_armed = False

        self._init_layout()
        self._init_engine()
        self._init_floating_widgets()
        self._connect_signals()
        self._refresh_start_screen()

        # Install global event filters for mouse tracking
        self.installEventFilter(self)
        self.viewport.installEventFilter(self)

    def _init_layout(self):
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("MainWindowContainer")
        self.central_widget.setMouseTracking(True)
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Custom Glass Title Bar: floats over the top of the video (placed in
        #    _reposition_floating_widgets), so the video uses the whole window.
        self.title_bar = GlassTitleBar(self, self.central_widget)
        self.title_bar.pip_toggled.connect(self.toggle_pip_mode)

        # 2. Video Viewport
        self.viewport = VideoViewport(self)
        self.viewport.file_dropped.connect(self.load_media_file)
        self.viewport.start_screen.open_requested.connect(self._open_file_dialog)
        self.viewport.start_screen.resume_requested.connect(self.load_media_file)
        self.viewport.clicked.connect(self._on_viewport_clicked)
        self.viewport.double_clicked.connect(self._on_viewport_double_clicked)
        self.viewport.context_menu_requested.connect(self.show_context_menu)
        self.main_layout.addWidget(self.viewport, stretch=1)

    def _init_engine(self):
        # mpv draws into the viewport through the render API (no native child
        # window), so the overlay widgets above can blend with the video.
        self.engine = PlayerEngine(parent=self, render_api=True)
        self.viewport.attach_mpv(self.engine.mpv)
        last_vol = self.app_settings.get_volume()
        self.engine.set_volume(last_vol)
        # the settings-panel choices (hardware decoding defaults to on, the lecture voice to off)
        if not self.app_settings.get_hwdec_enabled():
            self.engine.set_hardware_decoding(False)
        if self.app_settings.get_lecture_audio():
            self.engine.set_lecture_audio(True)

    def _init_floating_widgets(self):
        self._duration = 0.0

        # Stacking order, bottom to top: viewport < scrims/badge < controller < OSD
        self.top_scrim = TopScrim(self.central_widget)
        self.center_badge = CenterBadge(self.central_widget)
        self.center_badge.hide()
        self.seek_indicator = SeekIndicator(self.central_widget)
        self.tips = SeekTips(self)                       # the pill and the picture above the seek bar (ui/seek_tips.py)
        self._applying_speed = None                      # a speed set from memory: its change notice is not a user choice
        self.mini_progress = MiniProgress(self.central_widget)
        self.mini_progress.hide()

        self.speed_popup = SpeedPopup(self.central_widget)
        self.track_popup = TrackPopup(self.central_widget)

        self.next_up = NextUpCard(self.central_widget)
        self._next_target = None
        self.next_up.finished.connect(self._play_next_target)
        self.next_up.play_now.connect(self._play_next_target)

        # the update notice: a card over the window and the checker behind it (ui/update_flow.py)
        self.updates = UpdateFlow(self)

        self.help = HelpFlow(self)                       # the shortcut help (ui/help_flow.py)

        self.info_panel = MediaInfoPanel(self.central_widget)
        self.info_panel.set_provider(self.engine.get_media_info)

        self.controller = GlassController(self.central_widget)
        self.controller.forward_target = self.viewport
        self.controller.set_media_loaded(False)
        # keep the controls on screen while the speed panel is open
        # (and while the mouse is on the title bar, which fades with them)
        self.controller.hold_visible = (lambda: self.speed_popup.isVisible() or self.track_popup.isVisible()
                                        or self.marks.panel_visible()
                                        or self.title_bar.underMouse())
        self.controller.visibility_changed.connect(self._on_controls_visibility)
        self.controller.opacity_changed.connect(self._on_controls_opacity)
        self.title_bar.activity.connect(self.controller.trigger_activity)
        self.title_bar.installEventFilter(self)
        self.title_bar.update_clicked.connect(self.updates.check_from_home)
        self.title_bar.help_clicked.connect(self.help.toggle)
        self.top_scrim.hide()

        self.osd = GlassOSDWidget(self.central_widget)
        self.osd.raise_()

        self._reposition_floating_widgets()

    def _connect_signals(self):
        # Engine -> UI
        self.engine.time_pos_changed.connect(self._on_time_pos_changed)
        self.engine.duration_changed.connect(self.controller.set_duration)
        self.engine.duration_changed.connect(self._on_duration_changed)
        self.engine.playback_state_changed.connect(self.controller.set_playback_state)
        self.engine.playback_state_changed.connect(self._on_playback_state)
        self.engine.speed_changed.connect(self._on_speed_changed)
        self.engine.tracks_ready.connect(self._apply_remembered_tracks)
        self.engine.tracks_ready.connect(self.marks.load_chapters)
        self.engine.volume_changed.connect(self._on_volume_changed)
        self.engine.file_ended.connect(self._on_file_ended)
        self.engine.error_occurred.connect(lambda err: self.osd.show_message(err, "warning"))
        self.engine.load_failed.connect(self._on_load_failed)
        self.viewport.start_screen.copy_requested.connect(self.copy_diagnostics)

        # Controller -> Engine
        self.controller.timeline.hover_moved.connect(self.tips.show)
        self.controller.timeline.hover_left.connect(self.tips.hide)
        self.controller.timeline.pin_pressed.connect(lambda t: self.marks.seek_to(t, say=False))
        self.controller.bookmarks_clicked.connect(self.marks.toggle_panel)
        self.controller.visibility_changed.connect(lambda shown: None if shown else self.tips.hide())
        self.updates.card.update_clicked.connect(self.updates.start)
        self.updates.card.dismissed.connect(self.updates.dismiss)
        self.updates.checker.update_available.connect(self.updates.on_available)
        self.updates.checker.download_progress.connect(self.updates.on_progress)
        self.updates.checker.installer_ready.connect(self.updates.on_installer_ready)
        self.updates.checker.install_failed.connect(self.updates.on_failed)
        self.engine.playback_state_changed.connect(lambda _playing: self.updates.refresh_card())
        for signal in (self.next_up.finished, self.next_up.cancelled, self.next_up.play_now,
                       self.controller.settings_panel_toggled):
            signal.connect(self.updates.refresh_card)
        QTimer.singleShot(5000, self.updates.checker.check)       # the automatic check, a moment after the window is up
        self.controller.thumbnails_on = self.tips.thumbnails_on
        self.controller.thumbnails_on_stop = self.tips.thumbnails_on_stop
        self.controller.thumbnails_changed.connect(self.tips.on_thumbnails_changed)
        self.controller.thumbnails_on_stop_changed.connect(self.tips.on_thumbnails_on_stop_changed)
        self.controller.chapters_on = self.marks.chapters_on
        self.controller.chapters_changed.connect(self.marks.on_chapters_changed)
        self.controller.updates_on = self.app_settings.get_update_check_enabled()
        self.controller.updates_changed.connect(self.app_settings.set_update_check_enabled)
        self.controller.hwdec_on = self.engine.hardware_decoding
        self.controller.lecture_audio_on = self.engine.lecture_audio
        self.controller.hwdec_changed.connect(self._on_hwdec_changed)
        self.controller.lecture_audio_changed.connect(self._on_lecture_audio_changed)
        self.controller.play_pause_clicked.connect(self.engine.toggle_play)
        self.controller.prev_frame_clicked.connect(self.engine.step_frame_backward)
        self.controller.prev_file_clicked.connect(lambda: self.play_adjacent(-1))
        self.controller.next_file_clicked.connect(lambda: self.play_adjacent(+1))
        self.controller.next_frame_clicked.connect(self.engine.step_frame_forward)
        self.controller.seek_backward_clicked.connect(lambda s: self.seek_relative(-s))
        self.controller.seek_forward_clicked.connect(lambda s: self.seek_relative(s))
        self.controller.seek_requested.connect(lambda pos: self.engine.seek(pos, "absolute"))
        self.controller.speed_button_clicked.connect(self._show_speed_popup)
        self.controller.volume_changed.connect(lambda v: self.set_volume(v, osd=False))
        self.controller.mute_clicked.connect(lambda: self.toggle_mute(osd=False))
        self.controller.subtitle_clicked.connect(self._show_track_popup)
        self.controller.screenshot_clicked.connect(self.take_screenshot)
        self.controller.fullscreen_clicked.connect(self.toggle_fullscreen)

        # Speed popup -> Engine
        self.speed_popup.speed_selected.connect(self.engine.set_speed)

        # Track popup <-> Engine
        self.track_popup.opened.connect(self._refresh_track_popup)
        self.track_popup.audio_chosen.connect(self._choose_audio_track)
        self.track_popup.subtitle_chosen.connect(self._choose_subtitle_track)
        self.track_popup.subtitles_toggled.connect(self._set_subtitles_visible)
        self.track_popup.load_subtitle_requested.connect(self._select_subtitle_file)

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        apply_windows_11_rounded_corners(hwnd)
        native_window.enable_native_frame(hwnd)              # Win+arrow snapping, resizable, taskbar menu
        # (No acrylic backdrop: opaque video / start screen cover the whole window, so it was never seen, except as a
        # grey strip along the edge while the window is dragged larger, before Qt has painted the new area.)
        self._reposition_floating_widgets()

    def nativeEvent(self, event_type, message):
        """Windows messages that are ours (no visible frame, see ui/native_window.py)."""
        if native_window.IS_WINDOWS and bytes(event_type) == b"windows_generic_MSG":
            # (sizing borders only while the window can be resized: not maximized, not fullscreen)
            result = native_window.handle_message(int(message), not (self.isMaximized() or self.isFullScreen()))
            if result is not None:
                return True, result
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "title_bar"):
            # (Qt rewrites the window style when the state changes, e.g. in and out of fullscreen)
            native_window.enable_native_frame(int(self.winId()))
            # maximized by Win+Up / a snap as well as by the title bar's button: keep its icon right
            self.title_bar.sync_maximized(self.isMaximized())

    # --- Mouse Tracking Event Filter ---

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseMove, QEvent.HoverMove, QEvent.MouseButtonPress):
            if hasattr(self, "controller"):
                self.controller.trigger_activity()
        return super().eventFilter(watched, event)

    # --- Video Context Menu (Right Click) ---

    def show_context_menu(self, global_pos: QPoint):
        _show_context_menu(self, global_pos)

    STOP_DELAY_MS = 300                                  # ("only when the pointer rests": SeekTips reads it through the window)

    # The tips live in ui/seek_tips.py; the old names stay here as forwarders.
    @property
    def seek_tip(self):
        return self.tips.seek_tip

    @property
    def thumbnail_tip(self):
        return self.tips.thumbnail_tip

    @property
    def thumbnail_provider(self):
        return self.tips.thumbnail_provider

    @property
    def thumbnails_on(self) -> bool:
        return self.tips.thumbnails_on

    @thumbnails_on.setter
    def thumbnails_on(self, value: bool):
        self.tips.thumbnails_on = value

    @property
    def thumbnails_on_stop(self) -> bool:
        return self.tips.thumbnails_on_stop

    @thumbnails_on_stop.setter
    def thumbnails_on_stop(self, value: bool):
        self.tips.thumbnails_on_stop = value

    def _hide_seek_tips(self):
        self.tips.hide()

    @property
    def _stop_timer(self):
        return self.tips._stop_timer

    def _thumb_seconds(self) -> float:
        return self.tips._seconds()

    def _on_thumbnails_changed(self, enabled: bool):
        self.tips.on_thumbnails_changed(enabled)

    def _on_thumbnails_on_stop_changed(self, enabled: bool):
        self.tips.on_thumbnails_on_stop_changed(enabled)

    # Bookmarks and chapters live in ui/bookmark_flow.py; the old names stay here as forwarders.
    @property
    def bookmarks(self) -> list:
        return self.marks.bookmarks

    @property
    def chapters(self) -> list:
        return self.marks.chapters

    @property
    def chapters_on(self) -> bool:
        return self.marks.chapters_on

    @property
    def bookmark_panel(self):
        return self.marks.panel

    def add_bookmark(self):
        self.marks.add()

    def rename_bookmark(self, t: float, name: str):
        self.marks.rename(t, name)

    def delete_bookmark(self, t: float):
        self.marks.delete(t)

    def jump_bookmark(self, direction: int):
        self.marks.jump(direction)

    def toggle_bookmark_panel(self):
        self.marks.toggle_panel()

    def _seek_to_mark(self, t: float, say: bool):
        self.marks.seek_to(t, say)

    def _load_chapters(self):
        self.marks.load_chapters()

    def _refresh_marks(self):
        self.marks.refresh()

    def _on_chapters_changed(self, enabled: bool):
        self.marks.on_chapters_changed(enabled)

    def _on_hwdec_changed(self, enabled: bool):
        self.engine.set_hardware_decoding(enabled)
        self.app_settings.set_hwdec_enabled(enabled)

    def _on_lecture_audio_changed(self, enabled: bool):
        self.engine.set_lecture_audio(enabled)
        self.app_settings.set_lecture_audio(enabled)

    def about_text(self) -> str:
        import platform
        import PySide6
        try:
            mpv_ver = self.engine.mpv._get_property("mpv-version")
        except Exception:
            mpv_ver = "?"
        lines = [
            f"{APP_NAME} v{APP_VERSION}",
            "",
            f"mpv: {mpv_ver}",
            f"Qt for Python: {PySide6.__version__}",
            f"Python: {platform.python_version()}  ·  {platform.platform()}",
            "",
            f"오류 기록: {app_log.log_path()}",
            "",
            "제3자 구성 요소와 라이선스는 THIRD_PARTY_NOTICES.txt를 확인하세요.",
        ]
        return "\n".join(lines)

    def diagnostics_text(self) -> str:
        from PySide6.QtWidgets import QApplication
        return diagnostics.build_report(
            self.engine.mpv, screens=diagnostics.describe_screens(QApplication.screens()), problem=self._problem_text())

    def _problem_text(self):
        """The last file error, with the mpv lines logged after it was reported (a bad file's "Failed to recognize file
        format" comes a few ms after the failure itself)."""
        if not self._last_problem:
            return None
        late = [line for line in self.engine._mpv_errors if line not in self._last_problem]
        return self._last_problem + (f" (+ {' | '.join(late)})" if late else "")

    def copy_diagnostics(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.diagnostics_text())

    def _build_about_box(self):
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Information, f"{APP_NAME} 정보", self.about_text(), QMessageBox.Ok, self)
        copy_btn = box.addButton("진단 정보 복사", QMessageBox.ActionRole)
        copy_btn.clicked.disconnect()           # keep the dialog open so "복사됨" can be shown
        copy_btn.clicked.connect(lambda: self._on_copy_diagnostics(copy_btn))
        check_btn = box.addButton("업데이트 확인", QMessageBox.ActionRole)
        check_btn.clicked.disconnect()
        check_btn.clicked.connect(lambda: self._on_about_check(box, check_btn))
        return box

    def show_about(self):
        self._build_about_box().exec()

    UPDATE_CHECK_TIMEOUT_MS = 20000                      # (the update notice reads these two through the window)
    INSTALL_WAIT_MS = 60000

    # The update notice lives in ui/update_flow.py; the old names stay here as forwarders.
    @property
    def update_card(self):
        return self.updates.card

    @property
    def update_checker(self):
        return self.updates.checker

    def _ask_for_update(self, done):
        self.updates.ask(done)

    def _on_about_check(self, box, button):
        self.updates.on_about_check(box, button)

    def _check_update_from_home(self):
        self.updates.check_from_home()

    def _refresh_update_card(self):
        updates = getattr(self, "updates", None)
        if updates is not None:
            updates.refresh_card()

    def _on_copy_diagnostics(self, button):
        self.copy_diagnostics()
        button.setText("복사됨")
        QTimer.singleShot(1500, lambda: button.setText("진단 정보 복사"))

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())

    # --- Media Playback Lifecycle ---

    def _refresh_start_screen(self):
        """The start screen offers the most recent video that is still on disk."""
        start = self.viewport.start_screen
        for path in self.app_settings.get_recent_files():
            if os.path.exists(path):
                start.set_resume(path, self.app_settings.get_resume_position(path), self.app_settings.get_duration(path))
                return
        start.clear_resume()

    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "비디오 파일 선택",
            "",
            open_dialog_filter()
        )
        if file_path:
            self.load_media_file(file_path)

    def _select_subtitle_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "자막 파일 선택",
            "",
            "Subtitle Files (*.srt *.vtt *.ass *.smi);;All Files (*.*)"
        )
        if file_path:
            self.engine.set_subtitle(file_path)
            self.osd.show_message(f"자막 로드됨: {os.path.basename(file_path)}", "subtitle")
            self._refresh_track_popup_soon()

    def load_media_file(self, file_path: str):
        if not os.path.exists(file_path):
            self._show_file_problem(file_path)               # (opened from Windows after the file was moved, say)
            return
        self.viewport.start_screen.clear_problem()
        self._last_problem = None
        self.help.close()                                 # (its layout was chosen for the home screen)

        self._current_file = file_path
        self._duration = 0.0                              # (the new video says how long it is in a moment)
        self.controller.set_duration(0.0)                 # (the seek bar too: pins must not use the old video's length)
        self._time_pos = 0.0
        self.marks.open_video(file_path)
        self.track_popup.hide()
        self.next_up.cancel()
        self._next_target = None
        self._update_playlist_state()
        self.center_badge.reset()
        self.seek_indicator.reset()
        self._hide_seek_tips()
        self.thumbnail_provider.set_file(file_path)
        file_name = os.path.basename(file_path)
        self.viewport.show_empty_notice(False)
        self.viewport.set_has_frame(True)
        self.top_scrim.set_title(file_name)
        self.top_scrim.show()
        self.controller.set_media_loaded(True)
        self.title_bar.set_update_visible(False)

        resume_pos = self.app_settings.get_resume_position(file_path)
        start_time = 0.0
        if resume_pos > 5.0:
            start_time = resume_pos
            self.osd.show_message(f"이어서 재생 ({self._format_seconds(resume_pos)})", "clock")

        self.engine.load_file(file_path, start_time=start_time)
        self._apply_remembered_speed(file_path)
        self._refresh_update_card()
        self.engine.play()
        # mpv reports no change when it was already un-paused, so tell the controller it is playing: without
        # this the controls (and the title bar) never auto-hide until the first pause / resume.
        self.controller.set_playback_state(True)

        self._auto_load_subtitle(file_path)
        self.app_settings.add_recent_file(file_path)
        self.controller.trigger_activity()
        self.controller.raise_()

    def _auto_load_subtitle(self, video_path: str):
        base, _ = os.path.splitext(video_path)
        for ext in [".srt", ".vtt", ".ass", ".smi"]:
            sub_file = base + ext
            if os.path.exists(sub_file):
                self.engine.set_subtitle(sub_file)
                self.osd.show_message(f"자막 로드됨: {os.path.basename(sub_file)}", "subtitle")
                break

    def _on_duration_changed(self, duration: float):
        self._duration = duration
        if self._current_file and duration > 0:
            self.app_settings.save_duration(self._current_file, duration)     # (the start screen's progress line)
        self.marks.refresh()

    def _on_playback_state(self, is_playing: bool):
        if is_playing:
            self.next_up.cancel()            # playing again (the user restarted it): stay on this video
        # Big symbol over the picture: PAUSE while paused, PLAY for a moment after resuming.
        self.center_badge.set_playing(is_playing, self._current_file is not None)
        self._reposition_floating_widgets()

    def _on_controls_opacity(self, value: float):
        # The shade behind the top and the title bar fade together with the controls.
        self.top_scrim.set_opacity(value)
        self.title_bar.set_opacity(value)

    def _on_controls_visibility(self, visible: bool):
        # While controls are hidden a thin progress line stays at the bottom edge.
        has_media = self._current_file is not None
        self.mini_progress.setVisible(has_media and not visible)
        if not visible:
            self.top_scrim.set_opacity(0.0)
            # without media the bar stays (nothing to hide the controls for); with media it goes with them
            self.title_bar.set_opacity(0.0 if has_media else 1.0)
        self.mini_progress.raise_()

    def _on_time_pos_changed(self, time_pos: float):
        if time_pos > 0.0 and not self.center_badge.armed:
            self.center_badge.arm()
        self._time_pos = time_pos
        self.controller.set_time_pos(time_pos)
        if self._duration > 0:
            self.mini_progress.set_ratio(time_pos / self._duration)
        if self._current_file:
            self.app_settings.save_resume_position(self._current_file, time_pos)

    def _on_speed_changed(self, speed: float):
        self.controller.set_speed_display(speed)
        self.speed_popup.set_current_speed(speed)
        applied, self._applying_speed = self._applying_speed, None
        if applied is not None and abs(speed - applied) < 0.005:
            return                                       # (the change the app made from memory, not the user's)
        if self._current_file:
            self.app_settings.save_playback_memory(self._current_file, speed=speed)

    # --- what is remembered per video (speed, audio / subtitle choice): see AppSettings.get_playback_memory ---------

    def _apply_remembered_speed(self, file_path: str):
        speed = self.app_settings.get_playback_memory(file_path).get("speed")
        if speed is not None:
            self._applying_speed = self.engine.set_speed(speed)          # (set_speed brings it into 0.25..4.0)

    def _apply_remembered_tracks(self):
        """The new video's tracks are known: choose again what was chosen for this video or its folder, by language."""
        path = self._current_file
        if not path:
            return
        memory, e = self.app_settings.get_playback_memory(path), self.engine
        if "audio" in memory and not e.lecture_audio:                  # (the lecture preset keeps track 1 for itself)
            track = pick_track(e.audio_tracks(), memory["audio"])
            if track and not track.selected:
                e.select_audio_track(track.id)
        sub = memory.get("sub")
        if sub == "off":
            e.set_subtitles_visible(False)
        elif isinstance(sub, dict):
            track = pick_track(e.subtitle_tracks(), sub)
            if track and not (track.selected and e.subtitles_visible()):
                e.select_subtitle_track(track.id)

    def _remember_track(self, kind: str, track_id: int):
        if not self._current_file:
            return
        tracks = self.engine.audio_tracks() if kind == "audio" else self.engine.subtitle_tracks()
        track = next((t for t in tracks if t.id == track_id), None)
        choice = track_choice(track) if track else None
        if choice:
            self.app_settings.save_playback_memory(self._current_file, **{"audio" if kind == "audio" else "sub": choice})

    def _on_volume_changed(self, volume: float):
        self.controller.set_volume_display(volume)
        self.app_settings.save_volume(volume)

    def _on_file_ended(self):
        self.controller.set_playback_state(False)
        _, nxt = playlist.neighbors(self._current_file) if self._current_file else (None, None)
        if nxt and self.app_settings.get_auto_next():
            self._next_target = nxt
            self.next_up.start(os.path.basename(nxt), NEXT_UP_SECONDS)
            self._reposition_floating_widgets()
            self._refresh_update_card()
        else:
            self.osd.show_message("재생 완료", "check")

    # --- Previous / next video in the folder ---

    def _play_next_target(self):
        target, self._next_target = self._next_target, None
        if target and os.path.exists(target):
            self.load_media_file(target)

    def play_adjacent(self, step: int):
        """Open the previous (-1) or next (+1) video of the current file's folder."""
        if not self._current_file:
            return
        prev_, next_ = playlist.neighbors(self._current_file)
        target = next_ if step > 0 else prev_
        if not target:
            self.osd.show_message("마지막 영상입니다" if step > 0 else "첫 영상입니다", "warning")
            return
        self.load_media_file(target)

    def _on_load_failed(self, path: str, why: str, log_lines: list):
        """mpv could not open the file (it reports this a moment after loadfile)."""
        if path and self._current_file and path != self._current_file:
            return                                           # (an old file's failure, we have moved on)
        self._show_file_problem(path, why, log_lines)

    def _show_file_problem(self, path: str, why: str = "", log_lines=()):
        """Back to the empty start screen, with the reason in plain words under the logo."""
        problem = file_errors.classify(path, why, log_lines)
        self._last_problem = problem.detail
        self._current_file = None
        self.help.close()
        self.marks.forget()
        self.next_up.cancel()
        self._next_target = None
        self._update_playlist_state()
        self.center_badge.reset()
        self.seek_indicator.reset()
        self._hide_seek_tips()
        self.thumbnail_provider.set_file(None)
        self.top_scrim.hide()
        self.controller.set_media_loaded(False)
        self.title_bar.set_update_visible(True)
        self.viewport.set_has_frame(False)
        self.app_settings.remove_recent_file(path)          # (a file that does not open is not one to resume)
        self._refresh_start_screen()
        self.viewport.start_screen.set_problem(problem.title, problem.hint)
        self.viewport.show_empty_notice(True)
        self._refresh_update_card()

    def _update_playlist_state(self):
        prev_, next_ = playlist.neighbors(self._current_file) if self._current_file else (None, None)
        self.controller.set_playlist_state(prev_ is not None, next_ is not None)

    # --- Actions ---

    def seek_relative(self, seconds: float):
        self.next_up.cancel()
        self.engine.seek(seconds, reference="relative")
        if self._current_file is not None:
            self.seek_indicator.show_seek(seconds)

    # (The OSD pill only confirms keyboard shortcuts: a value changed with the mouse is already on screen in
    # its panel / popup, so those callers pass osd=False.)

    def change_speed_relative(self, delta: float):
        self._show_speed_osd(self.engine.change_speed_relative(delta))

    def reset_speed(self):
        speed = self.engine.reset_speed()
        if self._current_file:
            # remembered for this video only: the folder keeps its speed for the next video (an exception, not a new habit)
            self.app_settings.save_playback_memory(self._current_file, speed=speed, update_folder=False)
            self._applying_speed = speed                                   # (its change notice is not a second choice)
        self._show_speed_osd(speed)

    def _show_speed_osd(self, speed: float):
        self.osd.show_message("배속", "speed", f"{speed:.2f}x", accent=True)

    def set_volume(self, volume: float, osd: bool = True):
        self.engine.set_volume(volume)
        if osd:
            # (what the engine settled on: the key handler asks for current + 5, which may be past 100)
            self.osd.show_message("볼륨", "volume_high", f"{int(round(self.engine.get_volume()))}%")

    def toggle_mute(self, osd: bool = True):
        is_muted = self.engine.toggle_mute()
        self.controller.set_volume_display(self.engine.get_volume(), is_muted=is_muted)
        if osd:
            self.osd.show_message("음소거" if is_muted else "음소거 해제", "volume_mute" if is_muted else "volume_high")

    def toggle_subtitle(self, osd: bool = True):
        visible = self.engine.toggle_subtitle_visibility()
        if self._current_file:
            if not visible:
                self.app_settings.save_playback_memory(self._current_file, sub="off")
            else:
                selected = next((t for t in self.engine.subtitle_tracks() if t.selected), None)
                choice = track_choice(selected) if selected else None
                if choice:
                    self.app_settings.save_playback_memory(self._current_file, sub=choice)
        if osd:
            self.osd.show_message("자막 켬" if visible else "자막 끔", "subtitle")
        self._refresh_track_popup_soon()

    # --- audio / subtitle tracks and sync ---

    def _show_track_popup(self):
        if self._current_file is None:
            self.osd.show_message("영상을 먼저 열어 주세요", "warning")
            return
        button = self.controller.btn_subtitle
        if button is not None:             # (the layout may have hidden the button)
            self.track_popup.toggle_above_widget(button, align_to=self.controller.right_zone, above=self.controller.timeline)

    def _refresh_track_popup(self):
        e = self.engine
        self.track_popup.set_data(e.audio_tracks(), e.subtitle_tracks(), e.subtitles_visible(),
                                  e.get_sub_delay(), e.get_audio_delay())

    def _refresh_track_popup_soon(self):
        """mpv reports a changed track list a moment after the change."""
        if self.track_popup.isVisible():
            QTimer.singleShot(120, lambda: self.track_popup.isVisible() and self._refresh_track_popup())

    def _choose_audio_track(self, track_id: int):
        self.engine.select_audio_track(track_id)
        self._remember_track("audio", track_id)
        self._refresh_track_popup_soon()

    def _choose_subtitle_track(self, track_id: int):
        self.engine.select_subtitle_track(track_id)
        self._remember_track("sub", track_id)
        self._refresh_track_popup_soon()

    def _set_subtitles_visible(self, visible: bool):
        if self.engine.subtitles_visible() != visible:
            self.toggle_subtitle(osd=False)

    def change_sync(self, audio: bool, delta: float):
        if self._current_file is None:
            return
        if audio:
            value = self.engine.change_audio_delay(delta)
            self.osd.show_message("오디오 지연", "volume_high", format_delay(value))
        else:
            value = self.engine.change_sub_delay(delta)
            self.osd.show_message("자막 싱크", "subtitle", format_delay(value))
        self._refresh_track_popup_soon()

    def reset_sync(self):
        if self._current_file is None:
            return
        self.engine.reset_sync()
        self.osd.show_message("싱크 초기화", "subtitle")
        self._refresh_track_popup_soon()

    def take_screenshot(self):
        path = self.engine.take_screenshot()
        if path:
            self.osd.show_message(f"캡처 저장됨: {os.path.basename(path)}", "screenshot")

    def toggle_media_info(self):
        if self.info_panel.isVisible():
            self.info_panel.hide()
            return
        if self._current_file is None:
            self.osd.show_message("영상을 먼저 열어 주세요", "warning")
            return
        self.info_panel.show()
        self._reposition_floating_widgets()

    def _show_speed_popup(self):
        if hasattr(self.controller, "btn_speed"):
            self.speed_popup.toggle_above_widget(self.controller.btn_speed, align_to=self.controller.left_zone,
                                                 above=self.controller.timeline)

    def _on_viewport_clicked(self):
        if self.viewport.notice_widget.isVisible():
            return                        # the start screen: opening a file is the "영상 열기" button's job (and Ctrl+O)
        if self._current_file:
            self.engine.toggle_play()
            self._click_undo_armed = True
            self._click_timer.start()

    def _on_viewport_double_clicked(self):
        self._click_timer.stop()
        if self._click_undo_armed and self._current_file:
            self.engine.toggle_play()           # the first click of this pair already toggled: undo it
        self._click_undo_armed = False
        self.toggle_fullscreen()

    def _disarm_click_undo(self):
        self._click_undo_armed = False

    # --- Fullscreen & PIP Modes ---

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.title_bar.show()
            self.title_bar.btn_max.setIcon(get_svg_icon("maximize", size=12))
        else:
            self.showFullScreen()
            self.title_bar.hide()
        self._reposition_floating_widgets()

    def _set_always_on_top(self, on: bool):
        """Topmost via the Win32 API. Changing Qt's WindowStaysOnTopHint recreates the
        native window, which blanked the video (and re-created the GL context) on every
        PIP toggle."""
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.SetWindowPos.restype = ctypes.c_int
        done = user32.SetWindowPos(ctypes.c_void_p(int(self.winId())),
                                   ctypes.c_void_p(HWND_TOPMOST if on else HWND_NOTOPMOST),
                                   0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        if not done:
            print(f"[PIP] SetWindowPos(topmost={on}) failed, Windows error {ctypes.windll.kernel32.GetLastError()}")
        return bool(done)

    def is_always_on_top(self) -> bool:
        GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x00000008
        return bool(ctypes.windll.user32.GetWindowLongW(int(self.winId()), GWL_EXSTYLE) & WS_EX_TOPMOST)

    def toggle_pip_mode(self):
        if not self._is_pip:
            self._saved_geometry = self.geometry()
            self._is_pip = True
            self._set_always_on_top(True)
            self.resize(480, 270)
            self.title_bar.set_pip_active(True)
        else:
            self._is_pip = False
            self._set_always_on_top(False)
            if self._saved_geometry:
                self.setGeometry(self._saved_geometry)
            self.title_bar.set_pip_active(False)
        self._reposition_floating_widgets()

    # --- Keybindings Map ---

    def keyPressEvent(self, event: QKeyEvent):
        if not self.keys.handle(event):
            super().keyPressEvent(event)

    # --- Layout & Resizing ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_floating_widgets()

    def _reposition_floating_widgets(self):
        """Lay the overlay out over the video area (the viewport's rectangle)."""
        if not hasattr(self, "controller"):
            return
        vp = self.viewport.geometry()
        if vp.width() <= 0 or vp.height() <= 0:
            return
        if self.tips.area_changed(vp):            # (the tips were placed for the bar as it was: only a change of the video
            self.marks.hide_panel()               #  area moves them, and the list; a layout pass alone does not)

        # Controls: compact (transport only) when the full set doesn't fit.
        c = self.controller
        c.set_compact(False)
        needed = c.layout().minimumSize().width()
        if vp.width() < needed:
            c.set_compact(True)

        strip_h = min(c.STRIP_HEIGHT, vp.height())
        c.setGeometry(vp.x(), vp.bottom() + 1 - strip_h, vp.width(), strip_h)
        bar_shown = not self.title_bar.isHidden()
        inset = self.title_bar.height() if bar_shown else 0
        self.title_bar.setGeometry(vp.x(), vp.y(), vp.width(), self.title_bar.height())
        self.top_scrim.set_bar_inset(inset)
        self.top_scrim.setGeometry(vp.x(), vp.y(), vp.width(), self.top_scrim.height())
        self.mini_progress.setGeometry(vp.x(), vp.bottom() + 1 - self.mini_progress.height(),
                                       vp.width(), self.mini_progress.height())
        self.center_badge.move(vp.x() + (vp.width() - self.center_badge.width()) // 2,
                               vp.y() + (vp.height() - self.center_badge.height()) // 2)

        self.seek_indicator.place(vp)
        if self.updates.card.isVisible():
            self.updates.place_card()
        if hasattr(self, "osd"):
            self.osd.place(vp.x() + vp.width() // 2, vp.y())      # (the same spot with or without the title bar)

        # the next-video card: bottom right, just above the controls
        nu = self.next_up
        nu.move(max(vp.x() + 8, vp.right() - nu.width() - 24),
                max(vp.y() + 8, vp.bottom() - c.CONTROLS_HEIGHT - nu.height() - 6))

        # media info: top-right corner of the video area
        if self.info_panel.isVisible():
            self.info_panel.adjustSize()
            self.info_panel.move(max(vp.x() + 8, vp.right() - self.info_panel.width() - 14), vp.y() + inset + 10)

        self.help.relayout()

        # stacking order, bottom to top
        self.top_scrim.raise_()
        if bar_shown:
            self.title_bar.raise_()
        self.center_badge.raise_()
        self.seek_indicator.raise_()
        self.mini_progress.raise_()
        c.raise_()
        if self.seek_tip.isVisible():
            self.seek_tip.raise_()
        if self.thumbnail_tip.isVisible():
            self.thumbnail_tip.raise_()
        if self.update_card.isVisible():
            self.update_card.raise_()
        if self.speed_popup.isVisible():
            self.speed_popup.raise_()
        if self.track_popup.isVisible():
            self.track_popup.raise_()
        if self.marks.panel_visible():
            self.marks.raise_panel()
        if self.next_up.isVisible():
            self.next_up.raise_()
        if self.info_panel.isVisible():
            self.info_panel.raise_()
        self.help.raise_panel()
        if hasattr(self, "controller") and self.controller.settings_panel is not None:
            self.controller.settings_panel.raise_overlay()
        if hasattr(self, "osd"):
            self.osd.raise_()

    # (Moving the window: the title bar and the video view start Windows' own move; resizing by the edges is answered
    # to Windows in nativeEvent, see ui/native_window.py.)

    @staticmethod
    def _format_seconds(secs: float) -> str:
        s = int(max(0, secs))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    _shut_down = False

    def _on_close(self):
        exit_trace.begin()                              # (timed "[exit]" lines in pane.log: where a slow or stuck exit stopped)
        self.updates.request_stop()                     # (a download in flight gives up at its next chunk; traced)
        self.tips.shutdown()                            # (a picture in the making gets a second at most)
        exit_trace.stage("thumbnails closed")
        # Render context first, then the mpv core (the other order aborts).
        if hasattr(self, "viewport"):
            self.viewport.release()
        exit_trace.stage("video surface released")
        if hasattr(self, "engine"):
            self.engine.terminate()
        exit_trace.stage("mpv terminated")

    def closeEvent(self, event):
        # Freeing the render context and stopping mpv takes ~0.4 s while a video plays. The window must not stay on
        # screen, frozen, for that long after the X was pressed: hide it first. (Pausing mpv here as well, to cut the sound,
        # crashed the process now and then, so the sound simply ends with the shutdown.)
        self.hide()
        if not self._shut_down:                       # (a window can be closed twice, e.g. by a test's cleanup:
            self._shut_down = True                    # the shutdown runs once)
            self._on_close()
        super().closeEvent(event)
