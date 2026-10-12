import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal

# Configure mpv-2.dll lookup path before importing mpv
def _setup_mpv_path():
    from core.paths import LIB_MPV_DIR
    lib_mpv_dir = LIB_MPV_DIR
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
from core import audio_presets

# The one speed range: the keys, the speed panel's slider and its typed input all stay inside it.
MIN_SPEED, MAX_SPEED = 0.25, 4.0


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
    _tracks_changed = Signal()             # mpv's track list changed (emitted from its thread, handled in ours)

    def __init__(self, wid=None, parent=None, render_api=False, options_override=None):
        """render_api=True: no window of mpv's own; the caller draws frames via
        MpvRenderContext (see ui/mpv_gl.py). Otherwise mpv opens its own window
        or embeds into `wid`. `options_override` overrides individual mpv options
        (tests use {"vo": "null", "ao": "null"} to run without any window)."""
        super().__init__(parent)
        self.wid = wid
        self.render_api = render_api
        self.hardware_decoding = True
        self.lecture_audio = False
        self._aid_before = None
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

        self._tracks_changed.connect(self._sync_lecture_audio)
        self._bind_mpv_observers()

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

        @self.mpv.property_observer("track-list")
        def _on_track_list(_name, _value):
            self._tracks_changed.emit()

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
            elif value is False:
                self._eof_emitted = False        # left the end (seek / replay): the next end counts again

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
        self.reset_sync()                    # sync is per video: the previous one's offsets must not carry over
        self._set_audio_graph("", restore_track=False)  # (mpv refuses a file without audio while the graph is set; it comes back
                                             # through _sync_lecture_audio once the new file's tracks are known)
        try:
            # Start position goes in as a load option. Seeking right after loadfile fails
            # (the file isn't loaded yet), which silently broke "resume where you left off".
            if start_time > 0:
                self.mpv.loadfile(file_path, start=f"{start_time:.3f}")
            else:
                self.mpv.loadfile(file_path)
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

    def at_end(self) -> bool:
        """True while the file sits at its last frame (keep_open)."""
        try:
            return bool(self.mpv._get_property("eof-reached"))
        except Exception:
            return False

    def replay(self):
        """Start the file again from the beginning."""
        self._eof_emitted = False
        self.mpv.seek(0, reference="absolute")
        self.mpv.pause = False

    def toggle_play(self):
        """Toggle between play and pause. At the end of the file, play starts it again (mpv would just stay
        paused on the last frame)."""
        if self.at_end():
            self.replay()
            return
        self.mpv.pause = not self.mpv.pause

    def is_playing(self) -> bool:
        """Return True if media is currently playing."""
        return not bool(self.mpv.pause)

    # --- Precise Speed Controls (Core requirement) ---

    def set_speed(self, speed: float):
        """
        Set playback speed with 0.01 precision.
        Maintains pitch correction (scaletempo2).
        Range: MIN_SPEED to MAX_SPEED (0.25x to 4.0x)
        """
        clamped_speed = max(MIN_SPEED, min(MAX_SPEED, round(speed, 2)))
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
            self._set_prop("sub-visibility", True)

    # --- Audio / subtitle tracks and sync ---

    def _track_list(self) -> list:
        try:
            return self.mpv._get_property("track-list") or []
        except Exception:
            return []

    def audio_tracks(self) -> list:
        from core.tracks import AUDIO, list_tracks
        return list_tracks(self._track_list(), AUDIO)

    def subtitle_tracks(self) -> list:
        from core.tracks import SUB, list_tracks
        return list_tracks(self._track_list(), SUB)

    def _set_prop(self, name: str, value) -> bool:
        try:
            self.mpv._set_property(name, value)
            return True
        except Exception as e:
            print(f"[PlayerEngine] Could not set {name}: {e}")
            return False

    def _get_float(self, name: str) -> float:
        try:
            return float(self.mpv._get_property(name) or 0.0)
        except Exception:
            return 0.0

    def select_audio_track(self, track_id: int) -> bool:
        return self._set_prop("aid", int(track_id))

    def select_subtitle_track(self, track_id: int) -> bool:
        """Show the given subtitle track (also turns subtitles on)."""
        return self._set_prop("sid", int(track_id)) and self._set_prop("sub-visibility", True)

    def subtitles_visible(self) -> bool:
        try:
            return bool(self.mpv._get_property("sub-visibility"))
        except Exception:
            return True

    def get_sub_delay(self) -> float:
        return round(self._get_float("sub-delay"), 2)

    def get_audio_delay(self) -> float:
        return round(self._get_float("audio-delay"), 2)

    def change_sub_delay(self, delta: float) -> float:
        """Subtitle sync, in seconds (+ = later). Returns the new value."""
        value = round(self.get_sub_delay() + delta, 2)
        self._set_prop("sub-delay", value)
        return value

    def change_audio_delay(self, delta: float) -> float:
        """Audio delay, in seconds (+ = audio later). Returns the new value."""
        value = round(self.get_audio_delay() + delta, 2)
        self._set_prop("audio-delay", value)
        return value

    def reset_sync(self):
        self._set_prop("sub-delay", 0.0)
        self._set_prop("audio-delay", 0.0)

    def toggle_subtitle_visibility(self) -> bool:
        """Toggle subtitle visibility."""
        try:
            current = self.mpv.sub_visibility
            self.mpv.sub_visibility = not current
            return bool(self.mpv.sub_visibility)
        except Exception:
            return False

    @staticmethod
    def default_capture_dir() -> Path:
        """The user's real desktop folder. It is not always <home>/Desktop: on localized or
        OneDrive-redirected systems it has another name (here: 바탕화면), and mpv fails
        silently when the target folder does not exist."""
        from PySide6.QtCore import QStandardPaths
        for loc in (QStandardPaths.DesktopLocation, QStandardPaths.PicturesLocation):
            path = QStandardPaths.writableLocation(loc)
            if path and Path(path).is_dir():
                return Path(path)
        return Path.home()

    def take_screenshot(self, output_path: str = None) -> str:
        """
        Capture high-resolution screenshot of current video frame.
        If output_path is None, saves to the real desktop folder (see default_capture_dir).
        """
        if output_path is None:
            desktop = self.default_capture_dir()
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

    # --- Settings that take effect at once (the settings panel's switches) ---

    def set_hardware_decoding(self, enabled: bool):
        """GPU decoding on/off while playing: mpv switches decoders without reloading the video. Turning it on
        in the player window keeps the copy-back mode (GL interop for hardware surfaces isn't available there)."""
        self.hardware_decoding = bool(enabled)
        try:
            self.mpv.hwdec = ("auto-copy" if self.render_api else "auto") if enabled else "no"
        except Exception as e:
            print(f"[PlayerEngine] hwdec error: {e}")

    def set_lecture_audio(self, enabled: bool):
        """The "lecture voice" filter chain (core.audio_presets) on/off, live."""
        self.lecture_audio = bool(enabled)
        self._sync_lecture_audio()

    def _has_audio_track(self) -> bool:
        try:
            return any(t.get("type") == "audio" for t in (self.mpv._get_property("track-list") or []))
        except Exception:
            return False

    def _set_audio_graph(self, graph: str, restore_track: bool = True):
        """Set (or, with "", remove) the complex audio graph. While the graph runs mpv holds no audio track
        selection (aid=False) and does not give it back when the graph goes away: that was silence after
        switching the preset off. So the selected track is remembered going in and re-selected going out."""
        try:
            current = self.mpv._get_property("lavfi-complex") or ""
            if current == graph:
                return
            if graph:
                self._aid_before = self.mpv._get_property("aid")
            self.mpv._set_property("lavfi-complex", graph)
            if current and not graph and restore_track:
                self._reselect_audio_track()
        except Exception as e:
            print(f"[PlayerEngine] audio filter error: {e}")

    def _reselect_audio_track(self):
        ids = [t.get("id") for t in self._track_list() if t.get("type") == "audio"]
        if not ids:
            return
        want = self._aid_before if self._aid_before in ids else "auto"
        # ("no" first: setting the same value again is ignored by mpv, and a second round trip failed without it)
        self.mpv.command("set", "aid", "no")
        self.mpv.command("set", "aid", str(want))

    def _sync_lecture_audio(self):
        """The lecture graph ties the audio to track 1 and mpv won't play a file that has none: so it is set only
        while the loaded file has an audio track."""
        want = self.lecture_audio and self._has_audio_track()
        self._set_audio_graph(audio_presets.LECTURE_VOICE if want else "")

    # --- Lifecycle ---

    def terminate(self):
        """Cleanly terminate the mpv core engine."""
        try:
            self.mpv.terminate()
        except Exception:
            pass
