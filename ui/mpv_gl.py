"""
Video surface that renders libmpv through its OpenGL render API into a
QOpenGLWidget.

Unlike embedding mpv in a native child window (``wid``), the video becomes an
ordinary Qt-composited widget, so translucent Qt widgets (scrims, floating
controls) blend with it properly.

Note: do not call QSurfaceFormat.setDefaultFormat() with a custom
version/profile; on this setup it made the window present black.
"""
import mpv
from PySide6.QtCore import Qt, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget

# Shown when nothing is loaded (matches the viewport background #0E0E12).
IDLE_RGB = (14 / 255, 14 / 255, 18 / 255)


class MpvGLWidget(QOpenGLWidget):
    _frame_ready = Signal()  # emitted from mpv's thread, handled on the GUI thread

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mpv = None
        self._ctx = None
        self._get_proc = None  # keep the ctypes callback alive
        self._has_frame = False
        self._frame_ready.connect(self.update, Qt.QueuedConnection)

    # --- wiring -----------------------------------------------------------

    def attach_mpv(self, mpv_instance):
        """Give the widget the mpv core to draw. Safe before or after the GL
        context exists."""
        self._mpv = mpv_instance
        if self.isValid():
            self.makeCurrent()
            self._create_render_context()
            self.doneCurrent()

    def release(self):
        """Free the render context while the GL context is still alive. Must
        run before mpv is terminated, or mpv aborts the process."""
        if self._ctx is not None and self.isValid():
            self.makeCurrent()
            self._free_render_context()
            self.doneCurrent()
        self._ctx = None
        self._mpv = None

    def set_has_frame(self, has_frame: bool):
        """False draws the idle background instead of mpv's (black) output."""
        self._has_frame = has_frame
        self.update()

    # --- GL lifecycle -----------------------------------------------------

    def initializeGL(self):
        self.context().aboutToBeDestroyed.connect(self._free_render_context, Qt.DirectConnection)
        if self._mpv is not None:
            self._create_render_context()

    def _create_render_context(self):
        if self._ctx is not None or self._mpv is None:
            return
        gl = self.context()

        def get_proc_address(_ctx, name):
            addr = gl.getProcAddress(name)
            return int(addr) if addr else None

        self._get_proc = mpv.MpvGlGetProcAddressFn(get_proc_address)
        self._ctx = mpv.MpvRenderContext(
            self._mpv, "opengl",
            opengl_init_params={"get_proc_address": self._get_proc},
        )
        self._ctx.update_cb = self._frame_ready.emit

    def _free_render_context(self):
        # Runs with the GL context current (also when the window is recreated
        # for PIP/fullscreen); initializeGL builds a new one afterwards.
        if self._ctx is not None:
            try:
                self._ctx.update_cb = None
                self._ctx.free()
            except Exception as e:
                print(f"[MpvGLWidget] render context free: {e}")
            self._ctx = None

    def paintGL(self):
        f = self.context().functions()
        if self._ctx is None or not self._has_frame:
            f.glClearColor(*IDLE_RGB, 1.0)
            f.glClear(0x4000)  # GL_COLOR_BUFFER_BIT
            return

        self._ctx.update()
        dpr = self.devicePixelRatioF()
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        self._ctx.render(
            opengl_fbo={"w": w, "h": h, "fbo": self.defaultFramebufferObject()},
            flip_y=True,
        )
        # mpv leaves GL state dirty; restore what Qt's compositor relies on.
        f.glUseProgram(0)
        f.glBindBuffer(0x8892, 0)   # GL_ARRAY_BUFFER
        f.glBindBuffer(0x8893, 0)   # GL_ELEMENT_ARRAY_BUFFER
        f.glActiveTexture(0x84C0)   # GL_TEXTURE0
        f.glBindTexture(0x0DE1, 0)  # GL_TEXTURE_2D
        f.glDisable(0x0BE2)         # GL_BLEND
        f.glDisable(0x0B71)         # GL_DEPTH_TEST
        f.glDisable(0x0C11)         # GL_SCISSOR_TEST
        f.glPixelStorei(0x0CF5, 4)  # GL_UNPACK_ALIGNMENT
        f.glViewport(0, 0, w, h)
