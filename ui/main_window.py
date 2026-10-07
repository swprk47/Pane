import os
import ctypes
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel,
    QFileDialog, QMenu, QApplication
)
from PySide6.QtCore import Qt, QPoint, Signal, QEvent, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent

import pywinstyles
from styles.glass_theme import GLASS_THEME_QSS
from ui.title_bar import GlassTitleBar, native_start_window_drag
from ui.speed_popup import SpeedPopup
from ui.osd_widget import GlassOSDWidget
from ui.glass_controller import GlassController
from ui.next_up import NextUpCard, NEXT_UP_SECONDS
from core import playlist
from ui.media_info_panel import MediaInfoPanel
from core.version import APP_NAME, APP_VERSION
from core.media_types import open_dialog_filter
from core import app_log
from ui.mpv_gl import MpvGLWidget
from ui.overlay import TopScrim, MiniProgress, CenterBadge
from ui.icons import get_svg_icon, get_svg_pixmap
from styles.palette import MUTED_ICON
from core.player_engine import PlayerEngine
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

        # Empty state notice overlay
        self.notice_layout = QVBoxLayout(self)
        self.notice_layout.setAlignment(Qt.AlignCenter)
        self.notice_widget = QWidget(self)
        nw_layout = QVBoxLayout(self.notice_widget)
        nw_layout.setAlignment(Qt.AlignCenter)

        self.lbl_icon = QLabel(self)
        self.lbl_icon.setPixmap(get_svg_pixmap("film", 56, MUTED_ICON, stroke_width=1.5))
        self.lbl_icon.setStyleSheet("margin-bottom: 10px;")
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        nw_layout.addWidget(self.lbl_icon)

        self.lbl_main = QLabel("재생할 영상을 이곳으로 끌어다 놓으세요", self)
        self.lbl_main.setObjectName("EmptyNoticeLabel")
        self.lbl_main.setAlignment(Qt.AlignCenter)
        nw_layout.addWidget(self.lbl_main)

        self.lbl_sub = QLabel("화면 클릭하여 파일 열기 / 화면 아무 곳이나 드래그하여 창 이동", self)
        self.lbl_sub.setObjectName("EmptyNoticeSubLabel")
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        nw_layout.addWidget(self.lbl_sub)

        self.notice_layout.addWidget(self.notice_widget)

    def show_empty_notice(self, show: bool):
        self.notice_widget.setVisible(show)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
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

        self._margin = 8
        self._resizing = False
        self._resize_edge = None
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
        self.title_bar.close_requested.connect(self._on_close)

        # 2. Video Viewport
        self.viewport = VideoViewport(self)
        self.viewport.file_dropped.connect(self.load_media_file)
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

    def _init_floating_widgets(self):
        self._duration = 0.0

        # Stacking order, bottom to top: viewport < scrims/badge < controller < OSD
        self.top_scrim = TopScrim(self.central_widget)
        self.center_badge = CenterBadge(self.central_widget)
        self.center_badge.hide()
        self.mini_progress = MiniProgress(self.central_widget)
        self.mini_progress.hide()

        self.speed_popup = SpeedPopup(self.central_widget)

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
        self.controller.hold_visible = lambda: self.speed_popup.isVisible() or self.title_bar.underMouse()
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
        self.controller.play_pause_clicked.connect(self.engine.toggle_play)
        self.controller.prev_frame_clicked.connect(self.engine.step_frame_backward)
        self.controller.prev_file_clicked.connect(lambda: self.play_adjacent(-1))
        self.controller.next_file_clicked.connect(lambda: self.play_adjacent(+1))
        self.controller.next_frame_clicked.connect(self.engine.step_frame_forward)
        self.controller.seek_backward_clicked.connect(lambda s: self.seek_relative(-s))
        self.controller.seek_forward_clicked.connect(lambda s: self.seek_relative(s))
        self.controller.seek_requested.connect(lambda pos: self.engine.seek(pos, "absolute"))
        self.controller.speed_button_clicked.connect(self._show_speed_popup)
        self.controller.volume_changed.connect(self.set_volume)
        self.controller.mute_clicked.connect(self.toggle_mute)
        self.controller.subtitle_clicked.connect(self.toggle_subtitle)
        self.controller.screenshot_clicked.connect(self.take_screenshot)
        self.controller.fullscreen_clicked.connect(self.toggle_fullscreen)

        # Speed popup -> Engine
        self.speed_popup.speed_selected.connect(self.engine.set_speed)

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        apply_windows_11_rounded_corners(hwnd)
        try:
            pywinstyles.apply_style(self, "acrylic")
        except Exception as e:
            print(f"[pywinstyles] acrylic not applied: {e}")
        # pywinstyles replaces the window stylesheet with "background-color:
        # transparent;", which wipes the whole theme. Re-apply it afterwards.
        self.setStyleSheet(GLASS_THEME_QSS)
        self._reposition_floating_widgets()

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
        act_sub_toggle.triggered.connect(self.toggle_subtitle)
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
        act_layout = menu.addAction("컨트롤러 버튼 배열 설정")
        act_layout.triggered.connect(self.controller._open_settings_dialog)

        act_about = menu.addAction(f"{APP_NAME} 정보 (v{APP_VERSION})")
        act_about.triggered.connect(self.show_about)

        # 9. Exit
        act_exit = menu.addAction("Pane 종료 (Alt+F4)")
        act_exit.triggered.connect(self.close)

        menu.exec(global_pos)

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

    def show_about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, f"{APP_NAME} 정보", self.about_text())

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())

    # --- Media Playback Lifecycle ---

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

    def load_media_file(self, file_path: str):
        if not os.path.exists(file_path):
            return

        self._current_file = file_path
        self.next_up.cancel()
        self._next_target = None
        self._update_playlist_state()
        self.center_badge.reset()
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
        self.osd.show_message(f"{speed:.2f}x", "speed")

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
        self.osd.show_message(os.path.basename(target), "skip_next" if step > 0 else "skip_prev")

    def _update_playlist_state(self):
        prev_, next_ = playlist.neighbors(self._current_file) if self._current_file else (None, None)
        self.controller.set_playlist_state(prev_ is not None, next_ is not None)

    # --- Actions ---

    def seek_relative(self, seconds: float):
        self.next_up.cancel()
        self.engine.seek(seconds, reference="relative")
        direction = f"+{int(seconds)}s" if seconds > 0 else f"{int(seconds)}s"
        self.osd.show_message(direction, "forward_5" if seconds > 0 else "backward_5")

    def change_speed_relative(self, delta: float):
        self.engine.change_speed_relative(delta)

    def reset_speed(self):
        self.engine.reset_speed()

    def set_volume(self, volume: float):
        self.engine.set_volume(volume)
        self.osd.show_message(f"볼륨 {int(volume)}%", "volume_high")

    def toggle_mute(self):
        is_muted = self.engine.toggle_mute()
        self.controller.set_volume_display(self.engine.get_volume(), is_muted=is_muted)
        self.osd.show_message("음소거" if is_muted else "음소거 해제", "volume_mute" if is_muted else "volume_high")

    def toggle_subtitle(self):
        visible = self.engine.toggle_subtitle_visibility()
        self.osd.show_message("자막 켬" if visible else "자막 끔", "subtitle")

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
            self.speed_popup.toggle_above_widget(self.controller.btn_speed)

    def _on_viewport_clicked(self):
        if self.viewport.notice_widget.isVisible():
            self._open_file_dialog()
            return
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
            self.osd.show_message("전체화면 종료", "exit_fullscreen")
        else:
            self.showFullScreen()
            self.title_bar.hide()
            self.osd.show_message("전체화면 (F/ESC)", "fullscreen")
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
            self.osd.show_message("PIP 항상 위 모드 (P)", "pip")
        else:
            self._is_pip = False
            self._set_always_on_top(False)
            if self._saved_geometry:
                self.setGeometry(self._saved_geometry)
            self.title_bar.set_pip_active(False)
            self.osd.show_message("일반 모드 복원", "pip")
        self._reposition_floating_widgets()

    # --- Keybindings Map ---

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

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
            self.osd.show_message("1프레임 앞", "next_frame")
            event.accept()
            return
        elif key == Qt.Key_Comma:
            self.engine.step_frame_backward()
            self.osd.show_message("1프레임 뒤", "prev_frame")
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

        if hasattr(self, "osd"):
            self.osd.move(vp.x() + (vp.width() - self.osd.width()) // 2, vp.y() + inset + 12)

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
        self.mini_progress.raise_()
        c.raise_()
        if self.speed_popup.isVisible():
            self.speed_popup.raise_()
        if self.next_up.isVisible():
            self.next_up.raise_()
        if self.info_panel.isVisible():
            self.info_panel.raise_()
        if hasattr(self, "osd"):
            self.osd.raise_()

    # --- Frameless Window Drag & Resize ---

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self.isMaximized() and not self.isFullScreen():
            edge = self._get_edge(event.pos())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.isMaximized() and not self.isFullScreen():
            if self._resizing:
                self._do_resize(event.globalPosition().toPoint())
                event.accept()
                return
            else:
                self._update_cursor(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._resizing = False
        self._resize_edge = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def _get_edge(self, pos: QPoint):
        rect = self.rect()
        m = self._margin
        left = pos.x() <= m
        right = pos.x() >= rect.width() - m
        top = pos.y() <= m
        bottom = pos.y() >= rect.height() - m

        if top and left: return "top-left"
        if top and right: return "top-right"
        if bottom and left: return "bottom-left"
        if bottom and right: return "bottom-right"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _update_cursor(self, pos: QPoint):
        edge = self._get_edge(pos)
        if edge in ("top-left", "bottom-right"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge in ("top-right", "bottom-left"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edge in ("left", "right"):
            self.setCursor(Qt.SizeHorCursor)
        elif edge in ("top", "bottom"):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _do_resize(self, global_pos: QPoint):
        geo = self.geometry()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()

        if "right" in self._resize_edge:
            new_w = max(min_w, global_pos.x() - geo.left())
            geo.setWidth(new_w)
        if "bottom" in self._resize_edge:
            new_h = max(min_h, global_pos.y() - geo.top())
            geo.setHeight(new_h)
        if "left" in self._resize_edge:
            new_w = max(min_w, geo.right() - global_pos.x())
            geo.setLeft(geo.right() - new_w)
        if "top" in self._resize_edge:
            new_h = max(min_h, geo.bottom() - global_pos.y())
            geo.setTop(geo.bottom() - new_h)

        self.setGeometry(geo)

    @staticmethod
    def _format_seconds(secs: float) -> str:
        s = int(max(0, secs))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _on_close(self):
        # Render context first, then the mpv core (the other order aborts).
        if hasattr(self, "viewport"):
            self.viewport.release()
        if hasattr(self, "engine"):
            self.engine.terminate()

    def closeEvent(self, event):
        self._on_close()
        super().closeEvent(event)
