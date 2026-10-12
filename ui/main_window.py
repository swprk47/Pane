import os
import ctypes
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QFileDialog, QMenu, QApplication
)
from PySide6.QtCore import Qt, QPoint, Signal, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent

import pywinstyles
from styles.glass_theme import GLASS_THEME_QSS
from ui.title_bar import GlassTitleBar, native_start_window_drag
from ui.speed_popup import SpeedPopup
from ui.track_popup import TrackPopup
from ui.osd_widget import GlassOSDWidget
from ui.glass_controller import GlassController
from ui.next_up import NextUpCard, NEXT_UP_SECONDS
from ui.start_screen import StartScreen
from core import playlist
from ui.media_info_panel import MediaInfoPanel
from core.version import APP_NAME, APP_VERSION
from core.media_types import open_dialog_filter
from core.media_info import format_clock
from core import app_log, diagnostics
from ui.mpv_gl import MpvGLWidget
from ui.overlay import TopScrim, MiniProgress, CenterBadge, SeekIndicator, SeekTimeTip
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


class VideoViewport(MpvGLWidget):
    """
    Dedicated video rendering viewport.
    Supports dragging anywhere on the screen to move the window,
    right-click context menu, and file drag-and-drop.
    """
    file_dropped = Signal(str)
    double_clicked = Signal()
    clicked = Signal()
    context_menu_requested = Signal(QPoint)

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self._press_pos = None
        self._drag_started = False
        self._after_double_click = False

        # Empty state: the start screen covers the viewport until a video is loaded
        self.start_screen = StartScreen(self)
        self.notice_widget = self.start_screen          # (what "is the empty state showing" asks)
        self.start_screen.setGeometry(self.rect())
        self.start_screen.show()

    def show_empty_notice(self, show: bool):
        self.start_screen.setVisible(show)
        if show:
            self.start_screen.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.start_screen.setGeometry(self.rect())

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.start_screen.set_dragging(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.start_screen.set_dragging(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.start_screen.set_dragging(False)
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.exists(file_path):
                self.file_dropped.emit(file_path)
        event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._after_double_click = True
            self.double_clicked.emit()
            event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        # Right button is deliberately not handled here: it falls through to
        # contextMenuEvent so the menu opens through exactly one code path.
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_started = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Start the native window move only once the cursor really drags.
        # Starting it on press would swallow the button-up and break
        # click / double-click detection.
        if (event.buttons() & Qt.LeftButton and self._press_pos is not None
                and not self._drag_started
                and not self.parent_window.isFullScreen()
                and not self.parent_window.isMaximized()):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved >= QApplication.startDragDistance():
                self._drag_started = True
                native_start_window_drag(int(self.parent_window.winId()))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            if not self._drag_started and not self._after_double_click:
                self.clicked.emit()
            self._after_double_click = False
            self._press_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(event.globalPos())
        event.accept()


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

        self.app_settings = AppSettings()

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
        self.seek_tip = SeekTimeTip(self.central_widget)
        self.mini_progress = MiniProgress(self.central_widget)
        self.mini_progress.hide()

        self.speed_popup = SpeedPopup(self.central_widget)
        self.track_popup = TrackPopup(self.central_widget)

        self.next_up = NextUpCard(self.central_widget)
        self._next_target = None
        self.next_up.finished.connect(self._play_next_target)
        self.next_up.play_now.connect(self._play_next_target)

        self.info_panel = MediaInfoPanel(self.central_widget)
        self.info_panel.set_provider(self.engine.get_media_info)

        self.controller = GlassController(self.central_widget)
        self.controller.forward_target = self.viewport
        self.controller.set_media_loaded(False)
        # keep the controls on screen while the speed panel is open
        # (and while the mouse is on the title bar, which fades with them)
        self.controller.hold_visible = (lambda: self.speed_popup.isVisible() or self.track_popup.isVisible()
                                        or self.title_bar.underMouse())
        self.controller.visibility_changed.connect(self._on_controls_visibility)
        self.controller.opacity_changed.connect(self._on_controls_opacity)
        self.title_bar.activity.connect(self.controller.trigger_activity)
        self.title_bar.installEventFilter(self)
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
        self.engine.volume_changed.connect(self._on_volume_changed)
        self.engine.file_ended.connect(self._on_file_ended)
        self.engine.error_occurred.connect(lambda err: self.osd.show_message(err, "warning"))

        # Controller -> Engine
        self.controller.timeline.hover_moved.connect(self._show_seek_tip)
        self.controller.timeline.hover_left.connect(self.seek_tip.hide_tip)
        self.controller.visibility_changed.connect(lambda shown: None if shown else self.seek_tip.hide_tip())
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
        try:
            pywinstyles.apply_style(self, "acrylic")
        except Exception as e:
            print(f"[pywinstyles] acrylic not applied: {e}")
        # pywinstyles replaces the window stylesheet with "background-color:
        # transparent;", which wipes the whole theme. Re-apply it afterwards.
        self.setStyleSheet(GLASS_THEME_QSS)
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
        """Display comprehensive Apple Glass context menu on right click."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(26, 26, 36, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 12px;
                padding: 6px;
                font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
            }
            QMenu::item {
                color: #FFFFFF;
                font-size: 13px;
                padding: 6px 20px 6px 12px;
                border-radius: 6px;
                margin: 1px 0;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.16);
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 0.12);
                margin: 4px 6px;
            }
        """)

        # 1. Open File
        act_open = menu.addAction("파일 열기... (Ctrl+O)")
        act_open.triggered.connect(self._open_file_dialog)

        menu.addSeparator()

        # 2. Play / Pause
        is_playing = self.engine.is_playing()
        act_play = menu.addAction("일시정지 (Space)" if is_playing else "재생 (Space)")
        act_play.triggered.connect(self.engine.toggle_play)
        prev_, next_ = playlist.neighbors(self._current_file) if self._current_file else (None, None)
        act_prev = menu.addAction("이전 영상 (Shift+,)")
        act_prev.setEnabled(prev_ is not None)
        act_prev.triggered.connect(lambda: self.play_adjacent(-1))
        act_next = menu.addAction("다음 영상 (Shift+.)")
        act_next.setEnabled(next_ is not None)
        act_next.triggered.connect(lambda: self.play_adjacent(+1))
        act_auto = menu.addAction("영상이 끝나면 다음 영상 자동 재생")
        act_auto.setCheckable(True)
        act_auto.setChecked(self.app_settings.get_auto_next())
        act_auto.triggered.connect(self.app_settings.set_auto_next)

        # 3. Speed Submenu
        speed_menu = menu.addMenu("재생 속도 (배속)")
        speed_menu.setStyleSheet(menu.styleSheet())
        cur_spd = self.engine.get_speed()

        for spd in [0.8, 1.0, 1.2, 1.25, 1.4, 1.5, 1.75, 2.0]:
            label = f"{spd:g}x" + ("  ✓" if abs(cur_spd - spd) < 0.01 else "")
            act_s = speed_menu.addAction(label)
            act_s.triggered.connect(lambda _, s=spd: self.engine.set_speed(s))

        speed_menu.addSeparator()
        act_speed_popup = speed_menu.addAction("정밀 배속 슬라이더 & 프리셋 설정...")
        act_speed_popup.triggered.connect(self._show_speed_popup)

        # 4. Subtitles
        sub_menu = menu.addMenu("자막 (Subtitles)")
        sub_menu.setStyleSheet(menu.styleSheet())
        act_sub_toggle = sub_menu.addAction("자막 켜기 / 끄기 (C)")
        act_sub_toggle.triggered.connect(lambda: self.toggle_subtitle(osd=False))
        act_sub_load = sub_menu.addAction("외부 자막 파일 선택...")
        act_sub_load.triggered.connect(self._select_subtitle_file)

        menu.addSeparator()

        # 5. Screenshot
        act_shot = menu.addAction("현재 화면 고화질 캡처 (Ctrl+S)")
        act_shot.triggered.connect(self.take_screenshot)

        # Media info (codec / decoder / stats)
        act_info = menu.addAction("재생 정보 - 코덱, 디코더 (I)")
        act_info.setCheckable(True)
        act_info.setChecked(self.info_panel.isVisible())
        act_info.triggered.connect(self.toggle_media_info)

        # 6. PIP Mode
        act_pip = menu.addAction("PIP 항상 위 모드 (P)")
        act_pip.setCheckable(True)
        act_pip.setChecked(self._is_pip)
        act_pip.triggered.connect(self.toggle_pip_mode)

        # 7. Fullscreen
        act_full = menu.addAction("전체화면 (F)")
        act_full.setCheckable(True)
        act_full.setChecked(self.isFullScreen())
        act_full.triggered.connect(self.toggle_fullscreen)

        menu.addSeparator()

        # 8. Customize Buttons
        act_layout = menu.addAction("설정...")
        act_layout.triggered.connect(self.controller._open_settings_dialog)

        act_about = menu.addAction(f"{APP_NAME} 정보 (v{APP_VERSION})")
        act_about.triggered.connect(self.show_about)

        # 9. Exit
        act_exit = menu.addAction("Pane 종료 (Alt+F4)")
        act_exit.triggered.connect(self.close)

        menu.exec(global_pos)

    def _show_seek_tip(self, seconds: float, x: float):
        """The time under the pointer, as a pill just above the seek bar."""
        tl = self.controller.timeline
        spot = tl.mapTo(self.central_widget, QPoint(round(x), tl.height() // 2))
        self.seek_tip.show_at(format_clock(seconds), spot.x(), spot.y() - 15, self.viewport.geometry())

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
            self.engine.mpv, screens=diagnostics.describe_screens(QApplication.screens()))

    def copy_diagnostics(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.diagnostics_text())

    def show_about(self):
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Information, f"{APP_NAME} 정보", self.about_text(), QMessageBox.Ok, self)
        copy_btn = box.addButton("진단 정보 복사", QMessageBox.ActionRole)
        copy_btn.clicked.disconnect()           # keep the dialog open so "복사됨" can be shown
        copy_btn.clicked.connect(lambda: self._on_copy_diagnostics(copy_btn))
        box.exec()

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
            return

        self._current_file = file_path
        self.track_popup.hide()
        self.next_up.cancel()
        self._next_target = None
        self._update_playlist_state()
        self.center_badge.reset()
        self.seek_indicator.reset()
        self.seek_tip.hide_tip()
        file_name = os.path.basename(file_path)
        self.viewport.show_empty_notice(False)
        self.viewport.set_has_frame(True)
        self.top_scrim.set_title(file_name)
        self.top_scrim.show()
        self.controller.set_media_loaded(True)

        resume_pos = self.app_settings.get_resume_position(file_path)
        start_time = 0.0
        if resume_pos > 5.0:
            start_time = resume_pos
            self.osd.show_message(f"이어서 재생 ({self._format_seconds(resume_pos)})", "clock")

        self.engine.load_file(file_path, start_time=start_time)
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
        self.controller.set_time_pos(time_pos)
        if self._duration > 0:
            self.mini_progress.set_ratio(time_pos / self._duration)
        if self._current_file:
            self.app_settings.save_resume_position(self._current_file, time_pos)

    def _on_speed_changed(self, speed: float):
        self.controller.set_speed_display(speed)
        self.speed_popup.set_current_speed(speed)

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
        self._show_speed_osd(self.engine.reset_speed())

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
        self._refresh_track_popup_soon()

    def _choose_subtitle_track(self, track_id: int):
        self.engine.select_subtitle_track(track_id)
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
        user32.SetWindowPos(ctypes.c_void_p(int(self.winId())),
                            ctypes.c_void_p(HWND_TOPMOST if on else HWND_NOTOPMOST),
                            0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

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
        key = event.key()
        modifiers = event.modifiers()

        # The control-layout panel is modal: it has the keyboard (normally it holds the focus itself).
        panel = self.controller.settings_panel
        if panel is not None:
            if key == Qt.Key_Escape:
                panel.reject()
            event.accept()
            return

        # Space: Play/Pause
        if key == Qt.Key_Space:
            self.engine.toggle_play()
            event.accept()
            return

        # Speed: [ / ] (0.1x), Shift + [ / ] (0.05x)
        if key == Qt.Key_BracketRight:
            delta = 0.05 if (modifiers & Qt.ShiftModifier) else 0.1
            self.change_speed_relative(delta)
            event.accept()
            return
        elif key == Qt.Key_BracketLeft:
            delta = -0.05 if (modifiers & Qt.ShiftModifier) else -0.1
            self.change_speed_relative(delta)
            event.accept()
            return
        elif key in (Qt.Key_Backslash, Qt.Key_Backspace):
            self.reset_speed()
            event.accept()
            return

        # Previous / next video: Shift+, / Shift+.  (also PageUp / PageDown)
        if key in (Qt.Key_Greater, Qt.Key_PageDown):
            self.play_adjacent(+1)
            event.accept()
            return
        elif key in (Qt.Key_Less, Qt.Key_PageUp):
            self.play_adjacent(-1)
            event.accept()
            return

        # Seeking: Left / Right
        if key == Qt.Key_Right:
            step = 1.0 if (modifiers & Qt.ShiftModifier) else 5.0
            self.seek_relative(step)
            event.accept()
            return
        elif key == Qt.Key_Left:
            step = -1.0 if (modifiers & Qt.ShiftModifier) else -5.0
            self.seek_relative(step)
            event.accept()
            return

        # Frame step: Comma / Period
        if key == Qt.Key_Period:
            self.engine.step_frame_forward()
            event.accept()
            return
        elif key == Qt.Key_Comma:
            self.engine.step_frame_backward()
            event.accept()
            return

        # Volume: Up / Down
        if key == Qt.Key_Up:
            cur = self.engine.get_volume()
            self.set_volume(cur + 5.0)
            event.accept()
            return
        elif key == Qt.Key_Down:
            cur = self.engine.get_volume()
            self.set_volume(cur - 5.0)
            event.accept()
            return
        elif key == Qt.Key_M:
            self.toggle_mute()
            event.accept()
            return

        # Media info: I
        if key == Qt.Key_I and not (modifiers & Qt.ControlModifier):
            self.toggle_media_info()
            event.accept()
            return

        # Subtitle: C
        if key == Qt.Key_C:
            self.toggle_subtitle()
            event.accept()
            return

        # Subtitle sync Z / X (0.1 s), audio delay with Shift, reset with Ctrl+Z
        if key == Qt.Key_Z and (modifiers & Qt.ControlModifier):
            self.reset_sync()
            event.accept()
            return
        if key in (Qt.Key_Z, Qt.Key_X) and not (modifiers & (Qt.ControlModifier | Qt.AltModifier)):
            self.change_sync(bool(modifiers & Qt.ShiftModifier), 0.1 if key == Qt.Key_X else -0.1)
            event.accept()
            return

        # Open File: Ctrl + O
        if key == Qt.Key_O and (modifiers & Qt.ControlModifier):
            self._open_file_dialog()
            event.accept()
            return

        # Screenshot: Ctrl + S
        if key == Qt.Key_S and (modifiers & Qt.ControlModifier):
            self.take_screenshot()
            event.accept()
            return

        # Fullscreen / PIP / Esc
        if key in (Qt.Key_F, Qt.Key_Return):
            self.toggle_fullscreen()
            event.accept()
            return
        elif key == Qt.Key_Escape:
            if self.next_up.is_counting():
                self.next_up.cancel()
            elif self.track_popup.isVisible():
                self.track_popup.hide()
            elif self.info_panel.isVisible():
                self.info_panel.hide()
            elif self.isFullScreen():
                self.toggle_fullscreen()
            elif self._is_pip:
                self.toggle_pip_mode()
            event.accept()
            return
        elif key == Qt.Key_P:
            self.toggle_pip_mode()
            event.accept()
            return

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
        if self.speed_popup.isVisible():
            self.speed_popup.raise_()
        if self.track_popup.isVisible():
            self.track_popup.raise_()
        if self.next_up.isVisible():
            self.next_up.raise_()
        if self.info_panel.isVisible():
            self.info_panel.raise_()
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
        # Render context first, then the mpv core (the other order aborts).
        if hasattr(self, "viewport"):
            self.viewport.release()
        if hasattr(self, "engine"):
            self.engine.terminate()

    def closeEvent(self, event):
        # Freeing the render context and stopping mpv takes ~0.4 s while a video plays. The window must not stay on
        # screen, frozen, for that long after the X was pressed: hide it first. (Pausing mpv here as well, to cut the sound,
        # crashed the process now and then, so the sound simply ends with the shutdown.)
        self.hide()
        if not self._shut_down:                       # (a window can be closed twice, e.g. by a test's cleanup:
            self._shut_down = True                    # the shutdown runs once)
            self._on_close()
        super().closeEvent(event)
