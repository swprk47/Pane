import os
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal

# Configure mpv-2.dll lookup path before importing mpv
def _setup_mpv_path():
    project_root = Path(__file__).resolve().parent.parent
    lib_mpv_dir = project_root / "lib" / "mpv"
    if lib_mpv_dir.exists():
        path_str = str(lib_mpv_dir)
        os.environ["PATH"] = path_str + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(path_str)
            except Exception:
                pass

_setup_mpv_path()
import mpv


class PlayerEngine(QObject):
    """
    High-performance media playback engine based on libmpv.
    Dispatches Qt Signals for UI reactivity and thread-safe event handling.
    """
    # Signals for UI integration
    time_pos_changed = Signal(float)       # Current playback time in seconds
    duration_changed = Signal(float)       # Media duration in seconds
    playback_state_changed = Signal(bool)  # True: playing, False: paused
    speed_changed = Signal(float)          # Current playback speed (e.g. 1.25)
    volume_changed = Signal(float)         # Volume (0 - 100)
    file_loaded = Signal(str)              # Loaded media title or filename
    file_ended = Signal()                  # Playback reached end
    error_occurred = Signal(str)           # Error message

    def __init__(self, wid=None, parent=None, render_api=False, options_override=None):
        """render_api=True: no window of mpv's own; the caller draws frames via
        MpvRenderContext (see ui/mpv_gl.py). Otherwise mpv opens its own window
        or embeds into `wid`. `options_override` overrides individual mpv options
        (tests use {"vo": "null", "ao": "null"} to run without any window)."""
        super().__init__(parent)
        self.wid = wid
        self._current_file = None
        self._duration = 0.0
        self._time_pos = 0.0
        self._is_paused = False
        self._speed = 1.0
        self._volume = 100.0
        self._eof_emitted = False

        # mpv initialization options
        mpv_options = {
            "hwdec": "auto",                    # Hardware acceleration (GPU)
            "audio_pitch_correction": "yes",     # scaletempo2 pitch correction on speed change
            "keep_open": "yes",                  # Keep last frame open at end
            "cursor_autohide": "no",             # Controlled by our UI layer
            "sub_auto": "fuzzy",                 # Automatically load matching subtitles
            "vo": "gpu",                         # Modern GPU video output
            # Let the Qt viewport own mouse interaction and window gestures.
            "input_default_bindings": "no",
            "input_vo_keyboard": "no",
            "input_cursor": "no",
            "osc": "no",
        }

        if render_api:
            mpv_options["vo"] = "libmpv"
            # GL interop for hardware surfaces isn't available here; decode on
            # the GPU but copy frames back.
            mpv_options["hwdec"] = "auto-copy"
        elif wid is not None:
            mpv_options["wid"] = wid

        mpv_options.update(options_override or {})

        try:
            self.mpv = mpv.MPV(**mpv_options)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MPV engine: {e}")

        self._bind_mpv_observers()

    def set_wid(self, wid: int):
        """Set or update the native window handle for video rendering."""
        self.wid = wid
        try:
            self.mpv.wid = wid
        except Exception as e:
            print(f"[PlayerEngine] Warning setting wid: {e}")

    def _bind_mpv_observers(self):
        """Bind property observers to emit Qt signals asynchronously."""
        @self.mpv.property_observer("time-pos")
        def _on_time_pos(_name, value):
            if value is not None:
                self._time_pos = float(value)
                self.time_pos_changed.emit(self._time_pos)

        @self.mpv.property_observer("duration")
        def _on_duration(_name, value):
            if value is not None:
                self._duration = float(value)
                self.duration_changed.emit(self._duration)

        @self.mpv.property_observer("pause")
        def _on_pause(_name, value):
            if value is not None:
                self._is_paused = bool(value)
                # Emit is_playing (inverted pause)
                self.playback_state_changed.emit(not self._is_paused)

        @self.mpv.property_observer("speed")
        def _on_speed(_name, value):
            if value is not None:
                self._speed = round(float(value), 3)
                self.speed_changed.emit(self._speed)

        @self.mpv.property_observer("volume")
        def _on_volume(_name, value):
            if value is not None:
                self._volume = float(value)
                self.volume_changed.emit(self._volume)

        # With keep_open=yes mpv never sends end-file at EOF; it just flips
        # eof-reached. Listen to both so file_ended fires exactly once.
        @self.mpv.property_observer("eof-reached")
        def _on_eof_reached(_name, value):
            if value is True:
                self._emit_file_ended()

        @self.mpv.event_callback("end-file")
        def _on_end_file(event):
            reason = getattr(event, "reason", None)
            if reason == mpv.MpvEventEndFile.EOF:
                self._emit_file_ended()

    def _emit_file_ended(self):
        if not self._eof_emitted:
            self._eof_emitted = True
            self.file_ended.emit()

    # --- Core Controls ---

    def load_file(self, file_path: str, start_time: float = 0.0):
        """Load and play a video or audio file."""
        if not os.path.exists(file_path):
            self.error_occurred.emit(f"File not found: {file_path}")
            return False

        self._current_file = file_path
        self._eof_emitted = False
        try:
            # mpv loadfile command
            self.mpv.loadfile(file_path)
            if start_time > 0:
                self.seek(start_time, reference="absolute")
            self.file_loaded.emit(os.path.basename(file_path))
            return True
        except Exception as e:
            self.error_occurred.emit(f"Error loading media: {e}")
            return False

    def play(self):
        """Resume playback."""
        self.mpv.pause = False

    def pause(self):
        """Pause playback."""
        self.mpv.pause = True

    def toggle_play(self):
        """Toggle between play and pause."""
        self.mpv.pause = not self.mpv.pause

    def is_playing(self) -> bool:
        """Return True if media is currently playing."""
        return not bool(self.mpv.pause)

    # --- Precise Speed Controls (Core requirement) ---

    def set_speed(self, speed: float):
        """
        Set playback speed with 0.01 precision.
        Maintains pitch correction (scaletempo2).
        Range: 0.1x to 4.0x
        """
        clamped_speed = max(0.1, min(4.0, round(speed, 2)))
        self.mpv.speed = clamped_speed
        return clamped_speed

    def change_speed_relative(self, delta: float) -> float:
        """
        Adjust speed by delta (e.g. +0.05, -0.05, +0.1, -0.1).
        """
        current = self.get_speed()
        new_speed = round(current + delta, 2)
        return self.set_speed(new_speed)

    def reset_speed(self) -> float:
        """Reset speed to 1.0x."""
        return self.set_speed(1.0)

    def get_speed(self) -> float:
        """Get current playback speed."""
        try:
            return round(float(self.mpv.speed), 2)
        except Exception:
            return 1.0

    # --- Seeking & Frame Stepping ---

    def seek(self, seconds: float, reference: str = "relative"):
        """
        Seek in media.
        reference: 'relative' (default), 'absolute', 'relative-percent'
        """
        try:
            if reference == "relative":
                self.mpv.seek(seconds, reference="relative")
            elif reference == "absolute":
                self.mpv.seek(seconds, reference="absolute")
            elif reference == "percent":
                self.mpv.seek(seconds, reference="absolute-percent")
        except Exception as e:
            print(f"[PlayerEngine] Seek error: {e}")

    def step_frame_forward(self):
        """Step one frame forward (useful when paused)."""
        try:
            self.mpv.frame_step()
        except Exception as e:
            print(f"[PlayerEngine] Frame step error: {e}")

    def step_frame_backward(self):
        """Step one frame backward (useful when paused)."""
        try:
            self.mpv.frame_back_step()
        except Exception as e:
            print(f"[PlayerEngine] Frame back-step error: {e}")

    # --- Volume & Audio ---

    def set_volume(self, volume: float):
        """Set volume (0 - 100)."""
        clamped = max(0.0, min(100.0, float(volume)))
        self.mpv.volume = clamped

    def get_volume(self) -> float:
        """Get current volume."""
        try:
            return float(self.mpv.volume)
        except Exception:
            return 100.0

    def toggle_mute(self) -> bool:
        """Toggle audio mute state."""
        try:
            self.mpv.mute = not self.mpv.mute
            return bool(self.mpv.mute)
        except Exception:
            return False

    # --- Subtitles & Screenshot ---

    def set_subtitle(self, sub_path: str):
        """Add and select a subtitle file."""
        if os.path.exists(sub_path):
            self.mpv.sub_add(sub_path)

    def toggle_subtitle_visibility(self) -> bool:
        """Toggle subtitle visibility."""
        try:
            current = self.mpv.sub_visibility
            self.mpv.sub_visibility = not current
            return bool(self.mpv.sub_visibility)
        except Exception:
            return False

    def take_screenshot(self, output_path: str = None) -> str:
        """
        Capture high-resolution screenshot of current video frame.
        If output_path is None, saves to Desktop or current directory.
        """
        if output_path is None:
            desktop = Path.home() / "Desktop"
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = str(desktop / f"Pane_capture_{timestamp}.png")

        try:
            # video-high: with subtitles/full render
            self.mpv.screenshot_to_file(output_path, "video")
            return output_path
        except Exception as e:
            self.error_occurred.emit(f"Screenshot failed: {e}")
            return ""

    # --- Media info ---

    def get_media_info(self) -> dict:
        """Codec / decoder / stream details (see core.media_info)."""
        from core.media_info import read_media_info
        return read_media_info(self.mpv)

    # --- Lifecycle ---

    def terminate(self):
        """Cleanly terminate the mpv core engine."""
        try:
            self.mpv.terminate()
        except Exception:
            pass
