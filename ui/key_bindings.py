"""The keyboard of the main window. `KeyRouter.handle` answers one key press: True when it was a Pane key (and was dealt
with), False when it is none of Pane's (the window then lets Qt go on with it). The order of the checks is the behaviour
(the settings panel first, a name being typed next, the bookmark keys before the plain arrows, ...): do not reorder."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


class KeyRouter:
    def __init__(self, window):
        self.window = window

    def handle(self, event: QKeyEvent) -> bool:
        window = self.window
        key = event.key()
        modifiers = event.modifiers()

        # The control-layout panel is modal: it has the keyboard (normally it holds the focus itself).
        panel = window.controller.settings_panel
        if panel is not None:
            if key == Qt.Key_Escape:
                panel.reject()
            event.accept()
            return True

        # Bookmarks (before the plain Left / Right seek): B adds one, Shift+B opens the list, Alt+Left / Alt+Right jump
        # to the previous / next one. While a name is being typed, every key belongs to the field.
        if window.bookmark_panel is not None and window.bookmark_panel.is_editing:
            event.accept()
            return True
        if key == Qt.Key_B and not (modifiers & (Qt.ControlModifier | Qt.AltModifier)):
            if modifiers & Qt.ShiftModifier:
                window.toggle_bookmark_panel()
            else:
                window.add_bookmark()
            event.accept()
            return True
        if key in (Qt.Key_Left, Qt.Key_Right) and (modifiers & Qt.AltModifier):
            window.jump_bookmark(+1 if key == Qt.Key_Right else -1)
            event.accept()
            return True

        # Space: Play/Pause
        if key == Qt.Key_Space:
            window.engine.toggle_play()
            event.accept()
            return True

        # Speed: [ / ] (0.1x), Shift + [ / ] (0.05x)
        if key == Qt.Key_BracketRight:
            delta = 0.05 if (modifiers & Qt.ShiftModifier) else 0.1
            window.change_speed_relative(delta)
            event.accept()
            return True
        elif key == Qt.Key_BracketLeft:
            delta = -0.05 if (modifiers & Qt.ShiftModifier) else -0.1
            window.change_speed_relative(delta)
            event.accept()
            return True
        elif key in (Qt.Key_Backslash, Qt.Key_Backspace):
            window.reset_speed()
            event.accept()
            return True

        # Previous / next video: Shift+, / Shift+.  (also PageUp / PageDown)
        if key in (Qt.Key_Greater, Qt.Key_PageDown):
            window.play_adjacent(+1)
            event.accept()
            return True
        elif key in (Qt.Key_Less, Qt.Key_PageUp):
            window.play_adjacent(-1)
            event.accept()
            return True

        # Seeking: Left / Right
        if key == Qt.Key_Right:
            step = 1.0 if (modifiers & Qt.ShiftModifier) else 5.0
            window.seek_relative(step)
            event.accept()
            return True
        elif key == Qt.Key_Left:
            step = -1.0 if (modifiers & Qt.ShiftModifier) else -5.0
            window.seek_relative(step)
            event.accept()
            return True

        # Frame step: Comma / Period
        if key == Qt.Key_Period:
            window.engine.step_frame_forward()
            event.accept()
            return True
        elif key == Qt.Key_Comma:
            window.engine.step_frame_backward()
            event.accept()
            return True

        # Volume: Up / Down
        if key == Qt.Key_Up:
            cur = window.engine.get_volume()
            window.set_volume(cur + 5.0)
            event.accept()
            return True
        elif key == Qt.Key_Down:
            cur = window.engine.get_volume()
            window.set_volume(cur - 5.0)
            event.accept()
            return True
        elif key == Qt.Key_M:
            window.toggle_mute()
            event.accept()
            return True

        # Media info: I
        if key == Qt.Key_I and not (modifiers & Qt.ControlModifier):
            window.toggle_media_info()
            event.accept()
            return True

        # Subtitle: C
        if key == Qt.Key_C:
            window.toggle_subtitle()
            event.accept()
            return True

        # Subtitle sync Z / X (0.1 s), audio delay with Shift, reset with Ctrl+Z
        if key == Qt.Key_Z and (modifiers & Qt.ControlModifier):
            window.reset_sync()
            event.accept()
            return True
        if key in (Qt.Key_Z, Qt.Key_X) and not (modifiers & (Qt.ControlModifier | Qt.AltModifier)):
            window.change_sync(bool(modifiers & Qt.ShiftModifier), 0.1 if key == Qt.Key_X else -0.1)
            event.accept()
            return True

        # Open File: Ctrl + O
        if key == Qt.Key_O and (modifiers & Qt.ControlModifier):
            window._open_file_dialog()
            event.accept()
            return True

        # Screenshot: Ctrl + S
        if key == Qt.Key_S and (modifiers & Qt.ControlModifier):
            window.take_screenshot()
            event.accept()
            return True

        # Fullscreen / PIP / Esc
        if key in (Qt.Key_F, Qt.Key_Return):
            window.toggle_fullscreen()
            event.accept()
            return True
        elif key == Qt.Key_Escape:
            if window.next_up.is_counting():
                window.next_up.cancel()
            elif window.bookmark_panel is not None and window.bookmark_panel.isVisible():
                window.bookmark_panel.hide()
            elif window.track_popup.isVisible():
                window.track_popup.hide()
            elif window.info_panel.isVisible():
                window.info_panel.hide()
            elif window.isFullScreen():
                window.toggle_fullscreen()
            elif window._is_pip:
                window.toggle_pip_mode()
            event.accept()
            return True
        elif key == Qt.Key_P:
            window.toggle_pip_mode()
            event.accept()
            return True

        return False
