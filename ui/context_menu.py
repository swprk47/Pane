"""The right-click menu of the main window: built each time it is asked for, from the window's current state."""
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu

from core import playlist
from core.version import APP_NAME, APP_VERSION


def show_context_menu(window, global_pos: QPoint) -> None:
    """Display comprehensive Apple Glass context menu on right click."""
    menu = QMenu(window)
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
    act_open.triggered.connect(window._open_file_dialog)

    menu.addSeparator()

    # 2. Play / Pause
    is_playing = window.engine.is_playing()
    act_play = menu.addAction("일시정지 (Space)" if is_playing else "재생 (Space)")
    act_play.triggered.connect(window.engine.toggle_play)
    prev_, next_ = playlist.neighbors(window._current_file) if window._current_file else (None, None)
    act_prev = menu.addAction("이전 영상 (Shift+,)")
    act_prev.setEnabled(prev_ is not None)
    act_prev.triggered.connect(lambda: window.play_adjacent(-1))
    act_next = menu.addAction("다음 영상 (Shift+.)")
    act_next.setEnabled(next_ is not None)
    act_next.triggered.connect(lambda: window.play_adjacent(+1))
    act_auto = menu.addAction("영상이 끝나면 다음 영상 자동 재생")
    act_auto.setCheckable(True)
    act_auto.setChecked(window.app_settings.get_auto_next())
    act_auto.triggered.connect(window.app_settings.set_auto_next)

    # 3. Speed Submenu
    speed_menu = menu.addMenu("재생 속도 (배속)")
    speed_menu.setStyleSheet(menu.styleSheet())
    cur_spd = window.engine.get_speed()

    for spd in [0.8, 1.0, 1.2, 1.25, 1.4, 1.5, 1.75, 2.0]:
        label = f"{spd:g}x" + ("  ✓" if abs(cur_spd - spd) < 0.01 else "")
        act_s = speed_menu.addAction(label)
        act_s.triggered.connect(lambda _, s=spd: window.engine.set_speed(s))

    speed_menu.addSeparator()
    act_speed_popup = speed_menu.addAction("정밀 배속 슬라이더 & 프리셋 설정...")
    act_speed_popup.triggered.connect(window._show_speed_popup)

    # 4. Subtitles
    sub_menu = menu.addMenu("자막 (Subtitles)")
    sub_menu.setStyleSheet(menu.styleSheet())
    act_sub_toggle = sub_menu.addAction("자막 켜기 / 끄기 (C)")
    act_sub_toggle.triggered.connect(lambda: window.toggle_subtitle(osd=False))
    act_sub_load = sub_menu.addAction("외부 자막 파일 선택...")
    act_sub_load.triggered.connect(window._select_subtitle_file)

    menu.addSeparator()

    # 5. Screenshot
    act_shot = menu.addAction("현재 화면 고화질 캡처 (Ctrl+S)")
    act_shot.triggered.connect(window.take_screenshot)

    # Media info (codec / decoder / stats)
    act_info = menu.addAction("재생 정보 - 코덱, 디코더 (I)")
    act_info.setCheckable(True)
    act_info.setChecked(window.info_panel.isVisible())
    act_info.triggered.connect(window.toggle_media_info)

    # 6. PIP Mode
    act_pip = menu.addAction("PIP 항상 위 모드 (P)")
    act_pip.setCheckable(True)
    act_pip.setChecked(window._is_pip)
    act_pip.triggered.connect(window.toggle_pip_mode)

    # 7. Fullscreen
    act_full = menu.addAction("전체화면 (F)")
    act_full.setCheckable(True)
    act_full.setChecked(window.isFullScreen())
    act_full.triggered.connect(window.toggle_fullscreen)

    menu.addSeparator()

    # 8. The shortcut help, then the settings
    act_help = menu.addAction("단축키 (?)")
    act_help.triggered.connect(window.help.toggle)

    act_layout = menu.addAction("설정...")
    act_layout.triggered.connect(window.controller._open_settings_dialog)

    act_about = menu.addAction(f"{APP_NAME} 정보 (v{APP_VERSION})")
    act_about.triggered.connect(window.show_about)

    # 9. Exit
    act_exit = menu.addAction("Pane 종료 (Alt+F4)")
    act_exit.triggered.connect(window.close)

    menu.exec(global_pos)
