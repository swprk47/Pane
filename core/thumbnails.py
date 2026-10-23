"""
Seek-bar thumbnails: the picture shown above the time when the pointer is over the seek bar.

Design: docs/superpowers/specs/2026-10-13-seekbar-thumbnails-design.md. This module has no widgets: the box maths, the
cache and the provider that makes pictures with a second, windowless mpv.
"""
import math
import threading
import time
from collections import OrderedDict
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

from core import player_engine          # noqa: F401  (puts lib/mpv on PATH before mpv is imported)
import mpv

THUMB_H = 90                 # the picture's logical height
THUMB_MIN_W = 90             # and its logical width limits (the width follows the video's aspect ratio)
THUMB_MAX_W = 160
BUCKET_SECONDS = 2           # pictures are made and cached per 2 s of the video
CACHE_SIZE = 60              # per file, least recently used goes first
IDLE_SECONDS = 10.0          # the second mpv is closed after this long without a request
LOAD_SECONDS = 3.0           # how long a file may take to open / a seek to finish before the picture is given up


def thumbnail_box(aspect: float) -> tuple:
    """The logical (width, height) of the picture for a video of this aspect ratio: 90 px high, the width clamped to
    90..160 (a very wide or tall video is fitted inside with dark bars, never stretched). A bad aspect gives 160x90."""
    try:
        ok = math.isfinite(aspect) and aspect > 0
    except TypeError:
        ok = False
    if not ok:
        return THUMB_MAX_W, THUMB_H
    return max(THUMB_MIN_W, min(THUMB_MAX_W, round(THUMB_H * aspect))), THUMB_H


def bucket_of(seconds: float) -> int:
    """The 2 s step a time falls into (negative times count as 0)."""
    return int(max(0.0, seconds) // BUCKET_SECONDS)


class ThumbnailCache:
    """The most recently used pictures, keyed by (path, bucket)."""

    def __init__(self, limit: int = CACHE_SIZE):
        self._limit = limit
        self._items = OrderedDict()

    def get(self, key) -> Optional[QImage]:
        image = self._items.get(key)
        if image is not None:
            self._items.move_to_end(key)
        return image

    def put(self, key, image: QImage) -> None:
        self._items[key] = image
        self._items.move_to_end(key)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def image_from_shot(shot: dict) -> QImage:
    """The picture in mpv's `screenshot-raw` reply (a dict with w, h, stride, format, data). Only `bgr0` (what mpv gives
    on little-endian Windows) is understood; anything else is refused rather than shown with wrong colours."""
    w, h, stride, data = shot.get("w"), shot.get("h"), shot.get("stride"), shot.get("data")
    if shot.get("format") != "bgr0":
        raise ValueError(f"unexpected screenshot format {shot.get('format')!r}")
    if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0 and isinstance(stride, int) and stride >= 4 * w):
        raise ValueError(f"unexpected screenshot size {w}x{h}, stride {stride}")
    if data is None or len(data) < stride * h:
        raise ValueError("the screenshot data is shorter than its size says")
    return QImage(data, w, h, stride, QImage.Format_RGB32).copy()      # (the bytes belong to mpv's reply)


class _Bridge(QObject):
    ready = Signal(str, int, QImage)         # emitted from the worker thread, delivered in ours


class ThumbnailProvider(QObject):
    """Makes the pictures: one hidden mpv (no window, no sound, paused) that is created on the first request after a
    file is set, one worker thread where only the newest request is made, a cache, and a 10 s idle close. With the
    feature switched off (`set_enabled(False)`) no mpv is ever created."""

    thumbnail_ready = Signal(str, int, QImage)       # path, bucket, picture (never for a stale request)

    EXTRA_OPTIONS = {}                               # options added to the second mpv (the performance probe tries some)

    def __init__(self, parent=None, *, exact: bool = False, clock=time.monotonic):
        super().__init__(parent)
        self._exact = exact                          # exact seeks instead of nearest-keyframe (tests: sample.mp4 has one keyframe)
        self._clock = clock
        self._enabled = True
        self._shutdown = False
        self._path = None                            # the file whose pictures are asked for
        self._generation = 0                         # raised when the file changes: older results are dropped
        self._cache = ThumbnailCache()
        self._lock = threading.Lock()                # guards _pending, _latest, _running and the cache
        self._pending = None                         # (path, seconds, generation): the newest request not yet taken
        self._latest = None                          # (path, bucket) of the newest request: what a delivered picture must match
        self._making = None                          # (path, bucket) the worker is making right now
        self._running = False
        self._no_picture = set()                     # files that cannot give pictures (no video track, cannot be opened)
        self._logged = set()
        self._last_request = 0.0
        self._mpv = None
        self._mpv_path = None
        self._mpv_lock = threading.Lock()            # held by whoever uses or closes the mpv
        self._close_pending = False                  # a close was asked while the worker was inside the mpv
        self._worker = None                          # a daemon thread: it can never keep the process alive at exit
        self._bridge = _Bridge()
        self._bridge.ready.connect(self.thumbnail_ready)
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(1000)
        self._idle_timer.timeout.connect(self._tick_idle)

    # --- state ------------------------------------------------------------------------------------
    @property
    def has_instance(self) -> bool:
        return self._mpv is not None and not self._close_pending

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self._drop_work()
            self._close_instance()

    def set_file(self, path) -> None:
        """The video that pictures are asked for changed (None: no video). Queued work is dropped, the cache cleared and
        the hidden mpv closed."""
        self._path = path
        self._no_picture.discard(path)
        self._logged.discard(path)
        self._drop_work()
        self._close_instance()

    def shutdown(self) -> None:
        """The window is closing: nothing new is made, a running request gets at most a second to finish."""
        self._shutdown = True
        self._idle_timer.stop()
        self._drop_work()
        self._close_instance(wait=1.0)

    def _drop_work(self) -> None:
        with self._lock:
            self._generation += 1
            self._pending = None
            self._latest = None
            self._cache.clear()

    # --- requests (GUI thread) ---------------------------------------------------------------------
    def request(self, path: str, seconds: float) -> None:
        """Ask for the picture at `seconds`; it arrives through `thumbnail_ready` (at once when it is cached)."""
        if not self._enabled or self._shutdown or path != self._path or path in self._no_picture:
            return
        bucket = bucket_of(seconds)
        key = (path, bucket)
        self._last_request = self._clock()
        start = False
        with self._lock:
            self._latest = key
            hit = self._cache.get(key)
            if hit is None and key == self._making:
                return                                   # (being made right now: it is delivered when it is ready)
            if hit is None:
                self._pending = (path, seconds, self._generation)
                start = not self._running
                self._running = True
        if hit is not None:
            self.thumbnail_ready.emit(path, bucket, hit)
            return
        if not self._idle_timer.isActive():
            self._idle_timer.start()
        if start:
            self._worker = threading.Thread(target=self._work, name="thumbnail-worker", daemon=True)
            self._worker.start()

    def _tick_idle(self) -> None:
        if self._mpv is not None and self._clock() - self._last_request >= IDLE_SECONDS:
            self._close_instance()
        if self._mpv is None:
            self._idle_timer.stop()

    # --- the worker thread --------------------------------------------------------------------------
    def _work(self) -> None:
        try:
            while True:
                with self._lock:
                    request, self._pending = self._pending, None
                    if request is None:
                        self._running = False
                        return
                path, seconds, generation = request
                if self._shutdown or generation != self._generation or path != self._path:
                    continue
                key = (path, bucket_of(seconds))
                with self._lock:
                    hit = self._cache.get(key)
                    self._making = None if hit is not None else key
                if hit is not None:                      # (made meanwhile by the request before it)
                    self._deliver(path, key[1], hit, generation)
                    continue
                try:
                    self._make_one(path, seconds, generation)
                except Exception as e:                   # a surprise costs this one picture, not the feature
                    self._log_once(path, f"worker error: {type(e).__name__}: {e}")
                finally:
                    with self._lock:
                        self._making = None
        finally:
            with self._lock:                             # (however the loop ended, a later request can start a new worker)
                self._running = False

    def _make_one(self, path: str, seconds: float, generation: int) -> None:
        image = self._grab(seconds)
        if image is None:
            return
        bucket = bucket_of(seconds)
        with self._lock:
            if generation == self._generation:
                self._cache.put((path, bucket), image)
        self._deliver(path, bucket, image, generation)

    def _deliver(self, path: str, bucket: int, image: QImage, generation: int) -> None:
        """Hand the picture over, but only while it is still the one the pointer is waiting for."""
        with self._lock:
            current = generation == self._generation and self._latest == (path, bucket)
        if current and not self._shutdown:
            self._bridge.ready.emit(path, bucket, image)

    def _grab(self, seconds: float) -> Optional[QImage]:
        """One picture of the current file at `seconds`, or None (logged once per file)."""
        path = self._path
        try:
            with self._mpv_lock:
                try:
                    if self._shutdown:
                        return None
                    if self._close_pending:
                        self._terminate_locked()         # (a close was asked for; this request wants a fresh instance)
                    if self._mpv is None or self._mpv_path != path:
                        self._open(path)
                        if self._close_pending or self._shutdown:
                            return None
                    return self._shoot(seconds)
                except TimeoutError as e:
                    # a slow disk or a busy PC is not "this file has no pictures": start afresh on the next hover
                    self._terminate_locked()
                    self._log_once(path, f"timed out: {e}")
                    return None
                finally:
                    if self._close_pending:
                        self._terminate_locked()
        except Exception as e:
            self._give_up(path, f"{type(e).__name__}: {e}")
            return None

    def _open(self, path: str) -> None:
        close_asked = self._close_pending
        self._terminate_locked()
        self._close_pending = close_asked                # (the old instance is gone, but a close asked meanwhile still stands)
        options = dict(vo="null", ao="null", aid="no", sid="no", pause="yes", hwdec="no", idle="yes", keep_open="yes",
                       hr_seek="yes" if self._exact else "no", input_default_bindings="no", loglevel="fatal",
                       vd_lavc_threads=2,                # (measured: the hidden mpv must not compete for every core; PROGRESS.md)
                       vf=f"scale={2 * THUMB_MAX_W}:{2 * THUMB_H}:force_original_aspect_ratio=decrease")
        options.update(self.EXTRA_OPTIONS)
        self._mpv = mpv.MPV(**options)
        self._mpv_path = path
        with self._mpv.prepare_and_wait_for_event("file-loaded", "end-file", timeout=LOAD_SECONDS):
            self._mpv.loadfile(path)                 # (the handler exists before the event can come)
        has_video = any(t.get("type") == "video" and not t.get("albumart") for t in (self._mpv.track_list or []))
        if not self._mpv.duration or not has_video:
            self._terminate_locked()
            raise RuntimeError("no video track or the file cannot be opened")

    def _shoot(self, seconds: float) -> QImage:
        m = self._mpv
        with m.prepare_and_wait_for_event("playback-restart", timeout=LOAD_SECONDS):
            m.command("seek", float(seconds), "absolute+exact" if self._exact else "absolute+keyframes")
        return image_from_shot(m.command("screenshot-raw", "video"))

    def _give_up(self, path, reason: str) -> None:
        """This file cannot give pictures (no video track, cannot be opened): not asked for again until it is reopened."""
        self._no_picture.add(path)
        self._log_once(path, reason)

    def _log_once(self, path, reason: str) -> None:
        if path not in self._logged:
            self._logged.add(path)
            print(f"[thumbnails] {reason}")

    # --- closing -------------------------------------------------------------------------------------
    def _terminate_locked(self) -> None:
        m, self._mpv, self._mpv_path, self._close_pending = self._mpv, None, None, False
        if m is not None:
            try:
                m.terminate()
            except Exception as e:
                print(f"[thumbnails] closing the second mpv failed: {e}")

    def _close_instance(self, wait: float = 0.0) -> None:
        """Close the hidden mpv now, or (the worker is inside it and `wait` ran out) as soon as the worker is out."""
        if not wait:
            self._close_pending = True                   # (has_instance is False from now on)
            threading.Thread(target=self._close_in_background, name="thumbnail-closer", daemon=True).start()
            return
        if self._mpv_lock.acquire(timeout=wait):         # (shutdown: the window is closing anyway, wait for it)
            try:
                self._terminate_locked()
            finally:
                self._mpv_lock.release()
        else:
            self._close_pending = True

    def _close_in_background(self) -> None:
        with self._mpv_lock:
            if self._close_pending:
                self._terminate_locked()
