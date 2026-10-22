# Seek-bar Thumbnails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hovering the seek bar shows a small picture of that moment above the existing time pill, made by a hidden second mpv, with two switches in Settings > 성능, costing nothing when unused.

**Architecture:** `core/thumbnails.py` (Qt-light, no widgets) owns the cache, the box maths and `ThumbnailProvider`: one lazily created windowless mpv, one worker thread with "latest request wins", closed after 10 s idle. `ui/overlay.py` gets `ThumbnailTip` (draws one picture). `MainWindow` joins them to the existing `timeline.hover_moved` and to two new settings.

**Tech Stack:** Python 3.14, PySide6, python-mpv (libmpv), pytest. No new dependency (no Pillow: `screenshot-raw` returns bytes).

**Spec:** `docs/superpowers/specs/2026-10-13-seekbar-thumbnails-design.md` (read it first; it holds the owner's choices).

## Global Constraints

- Branch `feature/seekbar-thumbnails`. Commits only as the steps say, English messages ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Never `git stash`. Settings tests are isolated by `tests/conftest.py` (APP_NAME `PaneTest`); never touch the real `HKCU\Software\Pane`.
- Picture box: logical height **90 px**, width = 90 × aspect clamped to **90..160**; the image is made at twice that (**320×180 max**) for 200 % displays; never stretched (fit inside, dark bars when clamped).
- Gap between picture and time pill: **6 px**; border 1 px white at 40 % alpha; corner radius 10 px.
- Cache: key `(path, bucket)`, `bucket = int(seconds // 2)`, **60** pictures, least recently used out.
- Second mpv: created on the first request after a file is set, `vo=null ao=null aid=no sid=no pause=yes hwdec=no idle=yes keep-open=yes hr-seek=no`, seeks with `absolute+keyframes`; closed after **10 s** without a request; **no instance at all** while switch 1 is off.
- Stop mode delay: **300 ms**. Defaults: `thumbnails_enabled` True, `thumbnails_on_stop` False.
- Failures never show a dialog: one `print("[thumbnails] ...")` line (it reaches `pane.log`), pill only.
- Lightness rule (PROGRESS.md §8-0): cost when unused is zero; the measured cost is written to PROGRESS.md (Task 6).
- Known facts from probing (2026-10-13): `m.command("screenshot-raw", "video")` returns `{"w","h","stride","format":"bgr0","data": bytes}`; wait for `m.wait_for_event("playback-restart", timeout=...)` after `seek` or the picture is the old one; `tests/assets/sample.mp4` has ONE keyframe, so keyframe seeks return the same picture for every time (tests that need different pictures use the provider's `exact=True`).

## Review Focus

- Opening a video and hovering with switch 1 off must create no second mpv (lightness rule). Pinned in Task 3 and Task 5.
- Hover before a video is loaded, with duration 0 (stream), or after the video is closed: nothing requested, nothing shown. Task 5.
- A picture that arrives after the pointer moved on or after another video was opened must be dropped, not shown. Tasks 3 and 5.
- A file with no video track (audio), or one mpv cannot open, must not hang the worker or the window: no picture, one log line. Task 3.
- Closing the window while a request runs must neither hang nor leave a `mpv` process thread behind. Task 3 (`shutdown`) and Task 5.

---

## File Structure

- Create `core/thumbnails.py`: `thumbnail_box`, `bucket_of`, `ThumbnailCache`, `ThumbnailProvider`.
- Modify `ui/overlay.py`: add `ThumbnailTip` next to `SeekTimeTip`.
- Modify `core/settings.py`, `ui/settings_panel.py`, `ui/glass_controller.py`, `ui/main_window.py`: settings, switches, wiring.
- Modify `tools/perf_probe.py`: `--sweep` option for the measurement.
- Tests: `tests/test_thumbnails.py` (Tasks 2–3), `tests/test_thumbnail_tip.py` (Task 4), `tests/test_thumbnail_window.py` (Tasks 1 and 5), additions to `tests/test_settings_panel.py`.

### Task 1: The two settings and their switches

**Files:**
- Modify: `core/settings.py` (next to `get_hwdec_enabled`), `ui/settings_panel.py` (rows + signals + page), `ui/glass_controller.py`, `ui/main_window.py` (persist only)
- Test: `tests/test_thumbnail_window.py`, `tests/test_settings_panel.py`

**Interfaces:**
- Produces: `AppSettings.get_thumbnails_enabled() -> bool`, `set_thumbnails_enabled(bool)`, `get_thumbnails_on_stop() -> bool`, `set_thumbnails_on_stop(bool)`; `SettingsPanel(..., thumbnails_on: bool = True, thumbnails_on_stop: bool = False)` with signals `thumbnails_changed(bool)`, `thumbnails_on_stop_changed(bool)`, rows `row_thumbnails`, `row_thumbnails_stop`, switches `switch_thumbnails`, `switch_thumbnails_stop`; `GlassController` signals of the same names and attributes `thumbnails_on`, `thumbnails_on_stop`; `MainWindow.thumbnails_on` / `thumbnails_on_stop` read from settings and kept current.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_thumbnail_window.py (settings part)
def test_the_thumbnail_settings_default_to_following_on_and_stop_mode_off():
    s = AppSettings()
    assert s.get_thumbnails_enabled() is True and s.get_thumbnails_on_stop() is False
    s.set_thumbnails_enabled(False); s.set_thumbnails_on_stop(True)
    assert AppSettings().get_thumbnails_enabled() is False and AppSettings().get_thumbnails_on_stop() is True

def test_the_performance_tab_has_the_two_thumbnail_switches_and_they_save_at_once(window, qapp):
    window.controller._open_settings_dialog()
    panel = window.controller.settings_panel
    panel.set_tab(PERFORMANCE_TAB)
    assert panel.switch_thumbnails.checked is True and panel.switch_thumbnails_stop.checked is False
    panel.switch_thumbnails_stop.toggled.emit(True)
    assert AppSettings().get_thumbnails_on_stop() is True and window.thumbnails_on_stop is True
    panel.switch_thumbnails.toggled.emit(False)
    assert AppSettings().get_thumbnails_enabled() is False and window.thumbnails_on is False

def test_the_stop_switch_is_dimmed_and_inert_while_thumbnails_are_off(window, qapp):
    window.app_settings.set_thumbnails_enabled(False)
    window.controller.thumbnails_on = False
    window.controller._open_settings_dialog()
    panel = window.controller.settings_panel
    assert panel.row_thumbnails_stop.isEnabled() is False
    panel.switch_thumbnails.toggled.emit(True)
    assert panel.row_thumbnails_stop.isEnabled() is True
```

Add to `tests/test_settings_panel.py` one assertion that the panel's fixed size is the same with the performance tab shown as with the layout tab (the panel "keeps one size whatever the tab").

- [ ] **Step 2: Run them; expect FAIL** — `pytest tests/test_thumbnail_window.py -k "settings or switches or dimmed" -q` fails with `AttributeError: ... get_thumbnails_enabled`.
- [ ] **Step 3: Implement** the four `AppSettings` methods (keys `thumbnails_enabled`, `thumbnails_on_stop`, same string handling as `get_hwdec_enabled`); in `settings_panel.py` two row constants `THUMBNAILS_ROW = ("재생바 썸네일", "재생바에 마우스를 올리면 그 위치의 장면을 보여 줍니다.")` and `THUMBNAILS_STOP_ROW = ("마우스를 멈췄을 때만 표시", "훑는 동안은 시간만 보이고 잠깐 멈추면 장면이 나타나요. 4K 60fps처럼 영상이 끊길 때 켜 보세요.")` added to the performance page (`_build_options_page` already takes lists), the second row indented 18 px, and disabled with a 0.45 opacity effect while `switch_thumbnails` is off (update on its `toggled`); controller plumbing mirrors `hwdec_changed` (`_on_thumbnails_switched`, `_on_thumbnails_stop_switched`); `MainWindow` connects the controller signals to `app_settings.set_thumbnails_*`, sets `controller.thumbnails_on/_on_stop` from settings at start and keeps `self.thumbnails_on` / `self.thumbnails_on_stop` current.
- [ ] **Step 4: Run** `pytest tests/test_thumbnail_window.py tests/test_settings_panel.py -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: settings and switches for seek-bar thumbnails`.

### Task 2: Box maths, bucket and cache (pure code)

**Files:**
- Create: `core/thumbnails.py` (the three pieces below only)
- Test: `tests/test_thumbnails.py`

**Interfaces:**
- Produces: `THUMB_H = 90`, `THUMB_MIN_W = 90`, `THUMB_MAX_W = 160`, `BUCKET_SECONDS = 2`, `CACHE_SIZE = 60`; `thumbnail_box(aspect: float) -> tuple[int, int]` (logical width, height); `bucket_of(seconds: float) -> int`; `class ThumbnailCache` with `__init__(limit: int = CACHE_SIZE)`, `get(key) -> QImage | None` (a hit becomes most recent), `put(key, image)`, `clear()`, `__len__`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("aspect,expected", [(16/9, (160, 90)), (1.0, (90, 90)), (9/16, (90, 90)),
                                              (21/9, (160, 90)), (4/3, (120, 90)), (0, (160, 90)), (-1, (160, 90)), (float("nan"), (160, 90))])
def test_thumbnail_box_clamps_the_width(aspect, expected):
    assert thumbnail_box(aspect) == expected

@pytest.mark.parametrize("sec,b", [(0, 0), (1.99, 0), (2.0, 1), (3.5, 1), (125.3, 62), (-4, 0)])
def test_bucket_of_is_two_second_steps(sec, b):
    assert bucket_of(sec) == b

def test_the_cache_keeps_the_most_recently_used_sixty():
    c = ThumbnailCache(limit=3)
    for i in range(3): c.put(("f", i), QImage(2, 2, QImage.Format_RGB32))
    assert c.get(("f", 0)) is not None            # 0 is now the newest
    c.put(("f", 3), QImage(2, 2, QImage.Format_RGB32))
    assert c.get(("f", 1)) is None and c.get(("f", 0)) is not None and len(c) == 3
    c.clear(); assert len(c) == 0
```

- [ ] **Step 2: Run; expect FAIL** (`ModuleNotFoundError: core.thumbnails`).
- [ ] **Step 3: Implement** the functions and `ThumbnailCache` (an `OrderedDict` with `move_to_end`).
- [ ] **Step 4: Run `pytest tests/test_thumbnails.py -q`; expect pass.**
- [ ] **Step 5: Commit** `feat: thumbnail box, bucket and cache`.

### Task 3: `ThumbnailProvider` (second mpv, worker, idle close)

**Files:**
- Modify: `core/thumbnails.py`
- Test: `tests/test_thumbnails.py`

**Interfaces:**
- Consumes: Task 2's pieces. Import mpv as `core/player_engine.py` does (`from core import player_engine` first, which puts `lib/mpv` on PATH; then `import mpv`).
- Produces: `class ThumbnailProvider(QObject)`:
  `__init__(self, parent=None, *, exact: bool = False, clock=time.monotonic)` (`exact=True` seeks `absolute+exact`, for tests);
  `thumbnail_ready = Signal(str, int, QImage)` (path, bucket, picture);
  `set_enabled(enabled: bool)`; `set_file(path: str | None)` (drops queued work, clears the cache, terminates the instance; `None` = no video);
  `request(path: str, seconds: float) -> None` (cache hit: emits `thumbnail_ready` at once; miss: queued, latest wins; ignored while disabled, for a `path` that is not the current file, or after `shutdown`);
  `has_instance -> bool`; `_tick_idle()` (what the 1 s timer calls: terminates the instance when `clock() - last_request >= 10`); `shutdown()` (stop timer, drop work, terminate, wait at most 1 s for the worker). Names the tests rely on: `_grab(seconds: float) -> QImage | None` (makes one picture on the worker thread), `_cache` (a `ThumbnailCache`), `_exact`.

- [ ] **Step 1: Write the failing tests** (real mpv, `tests/assets/sample.mp4` via `sample_video`, `pump`):

```python
def test_a_request_returns_a_picture_of_the_right_size(sample_video, pump):
    p = ThumbnailProvider(exact=True); got = []; p.thumbnail_ready.connect(lambda path, b, img: got.append((b, img)))
    p.set_file(sample_video); p.request(sample_video, 1.5)
    assert pump(lambda: got, timeout=10)
    b, img = got[0]
    assert b == 0 and (img.width(), img.height()) == (320, 180) and not img.isNull()
    p.shutdown()

def test_different_times_give_different_pictures(sample_video, pump):              # exact=True: sample.mp4 has one keyframe
    p = ThumbnailProvider(exact=True); got = {}
    p.thumbnail_ready.connect(lambda path, b, img: got.__setitem__(b, img))
    p.set_file(sample_video); p.request(sample_video, 0.2); p.request(sample_video, 2.8)
    assert pump(lambda: 1 in got, timeout=10)
    p.request(sample_video, 0.2)                                       # bucket 0 again (it may have been dropped as stale)
    assert pump(lambda: 0 in got, timeout=10) and got[0] != got[1]
    p.shutdown()

def test_the_same_two_second_bucket_is_made_once_and_then_served_from_the_cache(sample_video, pump, monkeypatch):
    p = ThumbnailProvider(exact=True); made = []; got = []
    real = p._grab; monkeypatch.setattr(p, "_grab", lambda sec: made.append(sec) or real(sec))
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video); p.request(sample_video, 1.1)
    assert pump(lambda: got, timeout=10)
    p.request(sample_video, 1.9)                                       # same bucket: answered synchronously from the cache
    assert got == [0, 0] and len(made) == 1
    p.shutdown()

def test_only_the_newest_of_several_quick_requests_is_made(sample_video, pump, monkeypatch):
    p = ThumbnailProvider(exact=True); made = []; got = []
    real = p._grab; monkeypatch.setattr(p, "_grab", lambda sec: made.append(sec) or real(sec))
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    for sec in (0.1, 0.9, 2.1, 2.9):                                   # buckets 0, 0, 1, 1: the pointer sweeps on
        p.request(sample_video, sec)
    assert pump(lambda: 1 in got, timeout=10)
    assert len(made) <= 2 and 2.9 in made, "the newest request is made; at most the first one was already running"
    p.shutdown()

def test_nothing_is_created_while_thumbnails_are_off(sample_video, monkeypatch):
    created = []
    monkeypatch.setattr(thumbnails.mpv, "MPV", lambda **kw: created.append(kw))
    p = ThumbnailProvider(); p.set_enabled(False); p.set_file(sample_video); p.request(sample_video, 1.0)
    assert created == [] and p.has_instance is False

def test_the_instance_closes_after_ten_idle_seconds_and_returns_on_demand(sample_video, pump):
    now = [100.0]; p = ThumbnailProvider(exact=True, clock=lambda: now[0]); got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video); p.request(sample_video, 0.2)
    assert pump(lambda: got, timeout=10) and p.has_instance
    now[0] += 9.9; p._tick_idle(); assert p.has_instance
    now[0] += 0.2; p._tick_idle(); assert not p.has_instance
    p.request(sample_video, 2.5)
    assert pump(lambda: 1 in got, timeout=10) and p.has_instance
    p.shutdown()

def test_a_new_file_clears_the_cache_and_drops_a_picture_still_being_made(sample_video, pump):
    p = ThumbnailProvider(exact=True); got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append((path, b)))
    p.set_file(sample_video); p.request(sample_video, 1.0)
    p.set_file(None)                                                   # the video was closed before the picture arrived
    pump(None, timeout=1.5)
    assert got == [] and len(p._cache) == 0
    p.shutdown()

def test_a_file_that_mpv_cannot_open_gives_no_picture_no_hang_and_one_log_line(tmp_path, sample_video, pump, capsys):
    bad = tmp_path / "broken.mp4"; bad.write_bytes(b"not a video")
    p = ThumbnailProvider(exact=True); got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(path))
    p.set_file(str(bad)); p.request(str(bad), 1.0); p.request(str(bad), 5.0)
    pump(None, timeout=5)
    assert got == [] and capsys.readouterr().out.count("[thumbnails]") == 1
    p.set_file(sample_video); p.request(sample_video, 1.0)             # still alive for a good file afterwards
    assert pump(lambda: got, timeout=10) and got == [sample_video]
    p.shutdown()

def test_shutdown_while_a_request_runs_returns_quickly(sample_video):
    import time
    p = ThumbnailProvider(exact=True); p.set_file(sample_video); p.request(sample_video, 1.0)
    t0 = time.time(); p.shutdown()
    assert time.time() - t0 < 3 and p.has_instance is False
```

- [ ] **Step 2: Run; expect FAIL** (`ImportError: cannot import name 'ThumbnailProvider'`).
- [ ] **Step 3: Implement `ThumbnailProvider`.** One `QThreadPool` thread (as `core/update_checker.py` does) running a job that takes the newest pending `(path, bucket, seconds)`; the picture is made in `_grab(seconds) -> QImage | None`: create the instance if needed with the options in Global Constraints plus `vf=scale=320:180:force_original_aspect_ratio=decrease`, `loadfile(path)`, wait up to 3 s for a duration and a video track (no video track = give up for this file and remember it), `seek <seconds> absolute+keyframes` (or `absolute+exact` with `exact=True`), `wait_for_event("playback-restart", timeout=3)`, `command("screenshot-raw", "video")`, `QImage(data, w, h, stride, QImage.Format_RGB32).copy()`. A result is delivered only if its path is still the current file and its bucket is still the newest request's. Cache every picture made. A 1 s `QTimer` drives `_tick_idle`. Any exception: `print(f"[thumbnails] {type(e).__name__}: {e}")` once per file, return `None`.
- [ ] **Step 4: Run `pytest tests/test_thumbnails.py -q`; expect pass.** Then mutation check: remove the "path is still current" guard, the idle test and the stale-file test must fail; restore.
- [ ] **Step 5: Commit** `feat: ThumbnailProvider with a hidden second mpv`.

### Task 4: `ThumbnailTip` widget

**Files:**
- Modify: `ui/overlay.py` (after `SeekTimeTip`)
- Test: `tests/test_thumbnail_tip.py`

**Interfaces:**
- Consumes: `_OverlayBase` as `SeekTimeTip` uses it; `thumbnail_box` from `core.thumbnails`.
- Produces: `class ThumbnailTip(_OverlayBase)`: `GAP = 6`, `EDGE = 8`; `show_at(image: QImage, x_center: float, y_bottom: float, bounds: QRect)` (size from `thumbnail_box(image.width()/image.height())`, bottom edge at `y_bottom`, centred on `x_center`, kept `EDGE` px inside `bounds`); `hide_tip()`; `isVisible()` false until `show_at`.

- [ ] **Step 1: Write the failing tests** (real render with `widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))`, never `grab()`):

```python
def test_the_picture_is_drawn_inside_a_rounded_border(qapp):          # a solid red 320x180 image; render; the middle pixel is red, the corner pixel (0,0) is NOT red (rounded), and a border pixel is light
def test_a_wide_and_a_tall_picture_get_the_clamped_box(qapp):         # 21:9 -> 160x90 box with dark bars; 9:16 -> 90x90 with dark bars left/right
def test_it_sits_centred_on_the_pointer_and_stays_inside_the_bounds(qapp):   # x_center near both edges stays within bounds with EDGE margin; y_bottom is the widget's bottom edge
def test_hide_tip_hides_it(qapp):
```

- [ ] **Step 2: Run; expect FAIL** (`ImportError: ThumbnailTip`).
- [ ] **Step 3: Implement** the widget: paint the image fitted and centred on `QColor(14, 14, 18)` inside a 10 px rounded clip, then a 1 px `QColor(255,255,255,102)` border (40 %); size = `thumbnail_box` result; `show_at` moves/resizes, shows and raises (as `SeekTimeTip.show_at` does).
- [ ] **Step 4: Run `pytest tests/test_thumbnail_tip.py -q`; expect pass.**
- [ ] **Step 5: Commit** `feat: ThumbnailTip overlay`.

### Task 5: Wiring in `MainWindow` (follow mode, stop mode, lifecycle)

**Files:**
- Modify: `ui/main_window.py` (`__init__` near `self.seek_tip = SeekTimeTip(...)` and the `hover_moved` connections at ~line 299; `_show_seek_tip` ~line 492; `load_media_file` ~line 632; `_on_close` ~line 1267; the place that raises floating widgets ~line 1236)
- Test: `tests/test_thumbnail_window.py`

**Interfaces:**
- Consumes: `ThumbnailProvider`, `bucket_of`, `ThumbnailTip`, Task 1's `self.thumbnails_on` / `self.thumbnails_on_stop`.
- Produces: `MainWindow.thumbnail_provider`, `MainWindow.thumbnail_tip`, `MainWindow.STOP_DELAY_MS = 300`.

- [ ] **Step 1: Write the failing tests** (`window`, `sample_video`, `pump`; hover is driven by emitting `window.controller.timeline.hover_moved.emit(seconds, x)`; the provider is made exact with `window.thumbnail_provider._exact = True` where pictures must differ):

```python
def test_hovering_shows_the_pill_and_then_the_picture_six_pixels_above_it(window, sample_video, pump)
def test_leaving_the_bar_hides_both(window, sample_video, pump)
def test_with_thumbnails_off_only_the_pill_is_shown_and_no_second_mpv_exists(window, sample_video, pump)   # also asserts window.thumbnail_provider.has_instance is False
def test_stop_mode_shows_the_picture_only_after_the_pointer_rests(window, sample_video, pump)               # STOP_DELAY_MS shortened to 50 in the test; a move hides only the picture
def test_a_picture_for_a_place_the_pointer_left_is_not_shown(window, sample_video, pump)                    # emit thumbnail_ready for bucket 0 after the pointer is at bucket 1
def test_nothing_is_requested_before_a_video_is_loaded_or_when_the_duration_is_unknown(window, monkeypatch)  # request spy: not called
def test_opening_another_video_clears_the_picture_and_the_cache(window, sample_video, pump)
def test_closing_the_window_with_a_request_running_does_not_hang(qapp, sample_video)                        # builds its own MainWindow, requests, closes; returns < 3 s
def test_the_switches_take_effect_at_once(window, sample_video, pump)                                       # switch off while a picture is shown: it hides; stop mode on: next move shows none
```

- [ ] **Step 2: Run; expect FAIL** (`AttributeError: ... thumbnail_provider`).
- [ ] **Step 3: Implement.** Create `ThumbnailProvider(self)` and `ThumbnailTip(self.central_widget)` beside `seek_tip`; `provider.set_enabled(self.thumbnails_on)` at start and on the switch signal (switching off also hides the tip). In `_show_seek_tip`, after placing the pill: remember `(seconds, x)`; if thumbnails are off, no file or duration ≤ 0: hide the tip and return; follow mode: `provider.request(self._current_file, seconds)`; stop mode: hide the tip and restart a single-shot `QTimer(STOP_DELAY_MS)` whose timeout requests for the remembered position. A `thumbnail_ready(path, bucket, image)` slot shows the tip (`show_at(image, spot.x(), pill_top - ThumbnailTip.GAP, viewport.geometry())`) only if `path == self._current_file` and `bucket == bucket_of(remembered seconds)` and the pill is visible; `hover_left`, the controls hiding (`visibility_changed(False)`) and every place that calls `seek_tip.hide_tip()` also call `thumbnail_tip.hide_tip()`; raise the tip together with the pill in the raise-floating-widgets code. `load_media_file` calls `provider.set_file(file_path)`; `_on_close` calls `provider.shutdown()`.
- [ ] **Step 4: Run `pytest tests/test_thumbnail_window.py tests/test_seekbar_hover.py tests/test_window.py -q`; expect pass.** Mutation check: drop the `bucket ==` guard and the stale-picture test must fail; restore.
- [ ] **Step 5: Run the whole suite** (`python -m pytest -q`). Expected: every test passes except the two known monitor-dependent ones in `tests/test_native_window.py` when no external monitor is attached.
- [ ] **Step 6: Commit** `feat: seek-bar thumbnails in the main window`.

### Task 6: Measure it, record it, verify with the real window

**Files:**
- Modify: `tools/perf_probe.py` (option `--sweep thumbs-off|follow|stop`), `PROGRESS.md`, `CHANGELOG.md`
- Test: `tests/test_release.py` is unchanged; add `tests/test_perf_probe_sweep.py` only for the pure helper (the sweep positions), the measurement itself is manual.

**Interfaces:**
- Consumes: the window from Task 5. The sweep drives `window.controller.timeline.hover_moved.emit(seconds, x)` along the bar (about one bar width per second, back and forth) while the clip plays; the mouse is not used.
- Produces: `sweep_positions(duration: float, span: float, margin: float, t: float) -> tuple[float, float]` (seconds and x at sweep time `t`) in `tools/perf_probe.py`.

- [ ] **Step 1: Write the failing test** `test_sweep_positions_go_back_and_forth_inside_the_bar` (at `t=0` the left end, at one bar-width of time the right end, back again; x stays within `[margin, margin + span]`).
- [ ] **Step 2: Run; expect FAIL.** Step 3: implement `sweep_positions` and the `--sweep` option (thumbs setting applied through the window's own settings so the same code path runs). Step 4: run the test; expect pass. Commit `tools: sweep option for the performance probe`.
- [ ] **Step 5: Measure** (no mouse; ask the owner first because the window appears and the probe plays 4K video): `python tools/perf_probe.py <4K60 clip> <1080p clip> --seconds 10 --modes windowed --sweep thumbs-off`, then `--sweep follow`, then `--sweep stop`; note dropped frames (`drop_vo`+`drop_dec`), memory, and (from a short script printing `time.time()` between `request` and `thumbnail_ready`) the picture latency median and worst.
- [ ] **Step 6: Record** the numbers in PROGRESS.md (§1 bullet and the lightness-rule table the other features use); if the 4K60 `follow` run drops clearly more frames than `thumbs-off`, write it down and ask the owner whether stop mode should become the default (do not change the default yourself). Add the CHANGELOG line under a new `## Unreleased` heading. Commit `docs: thumbnail measurements and changelog`.
- [ ] **Step 7: Install check:** build is not needed for this feature, but before the release that carries it run `python tools/install_test.py ...` as docs/RELEASING.md says.
