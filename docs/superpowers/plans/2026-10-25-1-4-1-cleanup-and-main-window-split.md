# 1.4.1 cleanup and the `main_window.py` split — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ship Pane 1.4.1 (a handful of small fixes plus the update-check button already on `main`), then split
`ui/main_window.py` into six units without changing any behaviour.

**Architecture:** Part 1 is five independent bounded fixes, each test-first, then docs, then a release. Part 2 moves six
clusters out of `MainWindow` one at a time (cut and paste, forwarding names left behind), guarded by characterization
tests written first and by `pyflakes` and the full suite after every move.

**Tech Stack:** Python 3.14 (`./.venv/Scripts/python.exe`), PySide6, pytest, pyflakes (in the venv), Inno Setup / PyInstaller
for the release.

**Spec:** `docs/superpowers/specs/2026-10-25-main-window-split-design.md` (Part 2). Part 1 was agreed in chat on
2026-10-25 (the table is reproduced in each task).

## Global Constraints

- Run Python as `./.venv/Scripts/python.exe`; never `python -` / `python3 -` (it waits for stdin and hangs); write patch
  scripts to `scratch/` with the Write tool instead of heredocs with Korean or quotes.
- Commit messages in English, ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Features and fixes
  on their own branch; merge `--no-ff` and push **only when the person says so**. Never `git stash`.
- Tests use the isolated `PaneTest` settings (conftest). Anything that touches the real registry, opens a real window,
  removes the installed Pane, or publishes needs the person's go-ahead first (see Tasks 7 and 8).
- The full suite (`./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`) may die once with exit code 139 (the known
  native crash, PROGRESS §5 #33): run it again once before suspecting the change.
- Mutation checks use `scratch/mutate.py <file> <old> <new> <pytest args>` (it restores the file itself).
- Part 2 changes no behaviour: a test may be edited only when a name truly disappears, and the edit and its reason go in
  the commit message. A step that cannot be made to pass is reverted, not forced.

## Review Focus

1. Renaming a bookmark: switching to another window (Alt-Tab) must not throw the typed name away, but clicking elsewhere
   in Pane still cancels it (Task 1).
2. A very long name (Korean, double-width characters) in the hover pill must stay inside the video area, cut with `…`
   (Task 2).
3. The bookmark list in a small window (PIP is 480×270) must fit between the top edge and the seek bar, never run under
   the bar or off the top (Task 3).
4. After a move in Part 2 a signal must still reach its handler **exactly once** (a forwarder plus a direct connection would
   double it; a missed connection would silence it) (Task 9, guarded again in every move).
5. Closing the window must keep the traced order: update check stopped → thumbnails closed → video surface released → mpv
   terminated (Tasks 9, 13, 15).

---

# Part 1 — Pane 1.4.1 (branch `fix/1.4.1-cleanup`, from `main`)

Start: `git checkout main && git checkout -b fix/1.4.1-cleanup` (the docs branch `docs/1.4.1-and-split` is merged first,
with the person's go-ahead, so the spec and this plan are on `main`).

### Task 1: A rename survives switching windows

**Files:** Modify `ui/bookmark_panel.py` (`_NameEdit.focusOutEvent`); Test `tests/test_bookmark_panel.py`.

**Interfaces:** Consumes `_NameEdit`, `rows`, `hover`, `edit_field` (test helpers already in the file). Produces nothing new.

- [ ] **Step 1: failing test** in `tests/test_bookmark_panel.py` (add `QFocusEvent` to the `PySide6.QtGui` import):

```python
@pytest.mark.parametrize("reason", [Qt.ActiveWindowFocusReason, Qt.PopupFocusReason])
def test_losing_the_window_focus_does_not_cancel_a_rename_but_clicking_elsewhere_does(qapp, panel, reason):
    row = rows(panel)[0]
    hover(row)
    row.edit_button.click()
    field = edit_field(panel)
    field.setText("keep me")
    QApplication.sendEvent(field, QFocusEvent(QEvent.FocusOut, reason))
    assert panel.is_editing and edit_field(panel) is field and field.text() == "keep me"
    QApplication.sendEvent(field, QFocusEvent(QEvent.FocusOut, Qt.MouseFocusReason))
    qapp.processEvents()
    assert not panel.is_editing
```
- [ ] **Step 2:** run `tests/test_bookmark_panel.py -k window_focus`. Expected: the two parametrized cases FAIL (the first assert).
- [ ] **Step 3:** in `_NameEdit.focusOutEvent`, after `super().focusOutEvent(event)`, return without `self._cancel()` when
  `event.reason()` is `Qt.ActiveWindowFocusReason` or `Qt.PopupFocusReason`.
- [ ] **Step 4:** run the file. Expected: all pass. Mutation: delete the new `return` (use `scratch/mutate.py`) → the test fails.
- [ ] **Step 5:** commit `fix: a bookmark rename survives switching to another window`.

### Task 2: A long name is cut to fit the hover pill

**Files:** Modify `ui/overlay.py` (`SeekTimeTip.show_at`, `paintEvent`); Test `tests/test_seekbar_hover.py`.

**Interfaces:** Produces `SeekTimeTip.shown_text: str` (what is painted; `text` stays the full text the caller gave).

- [ ] **Step 1: failing test** in `tests/test_seekbar_hover.py` (add `QRect` to the `PySide6.QtCore` import and `QColor` to the `PySide6.QtGui` one; `QWidget` is already imported):

```python
def test_a_text_wider_than_the_video_area_is_cut_with_an_ellipsis_and_the_pill_stays_inside(qapp):
    host = QWidget()
    host.resize(400, 200)
    tip = SeekTimeTip(host)
    bounds = QRect(0, 0, 400, 200)
    long_name = "아주 긴 북마크 이름 " * 12
    tip.show_at(long_name, 200, 100, bounds, dot=QColor(255, 200, 87), detail="0:34")
    assert tip.width() <= bounds.width() - 2 * SeekTimeTip.EDGE
    assert tip.text == long_name and tip.shown_text.endswith("…") and len(tip.shown_text) < len(long_name)
    assert tip.x() >= bounds.left() + SeekTimeTip.EDGE and tip.x() + tip.width() <= bounds.right() - SeekTimeTip.EDGE + 1
    tip.show_at("0:34", 200, 100, bounds)
    assert tip.shown_text == "0:34"
```
- [ ] **Step 2:** run it. Expected: FAIL (`shown_text` missing).
- [ ] **Step 3:** in `show_at`, compute the room for the text (`bounds.width() - 2 * EDGE - 2 * PAD` minus the dot and the
  detail widths), elide with `QFontMetrics.elidedText(text, Qt.ElideRight, max(room, 40))`, store it in `self.shown_text`,
  size the pill from `shown_text`, and paint `shown_text` (both painting branches). With no dot or detail and a short text the
  pill is exactly as before (the existing tests in the file prove it).
- [ ] **Step 4:** run `tests/test_seekbar_hover.py tests/test_timeline_marks.py`. Expected: all pass. Mutation: skip the
  elision → the new test fails.
- [ ] **Step 5:** commit `fix: a very long bookmark or chapter name is cut to fit the hover pill`.

### Task 3: The bookmark list fits a small window

**Files:** Modify `ui/bookmark_panel.py` (`set_items`, `show_above_widget`, new `_apply_scroll_height`); Test
`tests/test_bookmark_panel.py`.

**Interfaces:** Produces `BookmarkPanel._apply_scroll_height()` (sets the list's height from the row count, `VISIBLE_ROWS`
and the room above the `above` widget, never fewer than 2 rows; with `above` unknown, the room above `parent.height() - 100`).

- [ ] **Step 1: failing test** (import `QPushButton`, `ROW_HEIGHT`, `VISIBLE_ROWS` from the panel module):

```python
def test_in_a_short_window_the_list_gets_shorter_so_the_panel_fits_above_the_bar(qapp):
    host = QWidget()
    host.resize(480, 270)
    host.show()
    bar = QWidget(host)
    bar.setGeometry(0, 200, 480, 30)
    bar.show()
    anchor = QPushButton("b", host)
    anchor.setGeometry(430, 230, 30, 30)
    anchor.show()
    p = BookmarkPanel(host)
    p.set_items([{"t": float(i * 10), "name": ""} for i in range(20)], 600.0)
    p.show_above_widget(anchor, above=bar)
    qapp.processEvents()
    assert p.geometry().top() >= 8 and p.geometry().bottom() < bar.geometry().top()
    assert p._scroll.height() >= 2 * ROW_HEIGHT
    tall = QWidget()
    tall.resize(900, 700)
    tall.show()
    bar2 = QWidget(tall)
    bar2.setGeometry(0, 600, 900, 30)
    bar2.show()
    q = BookmarkPanel(tall)
    q.set_items([{"t": float(i * 10), "name": ""} for i in range(20)], 600.0)
    q.show_above_widget(bar2, above=bar2)
    assert q._scroll.height() == VISIBLE_ROWS * ROW_HEIGHT, "a tall window still shows the usual seven rows"
```
- [ ] **Step 2:** run it. Expected: FAIL (first assertion: the panel's bottom is under the bar).
- [ ] **Step 3:** implement `_apply_scroll_height`; call it at the end of `set_items` (replacing the fixed-height line) and in
  `show_above_widget` before `adjustSize()`; empty list keeps `EMPTY_HEIGHT`.
- [ ] **Step 4:** run `tests/test_bookmark_panel.py tests/test_bookmark_window.py`. Expected: all pass. Mutation: return
  `VISIBLE_ROWS` rows always → the new test fails.
- [ ] **Step 5:** commit `fix: the bookmark list is shorter in a small window so the panel fits above the seek bar`.

### Task 4: The list is not rebuilt while a name is being typed

**Files:** Modify `ui/main_window.py` (`_refresh_marks`); Test `tests/test_bookmark_window.py`.

- [ ] **Step 1: failing test** (the file's `window`, `video`, `add_at`, `_BookmarkRow`, `QLineEdit` are already there):

```python
def test_the_list_is_not_rebuilt_while_a_name_is_being_typed(window, video, pills, qapp):
    add_at(window, 0.3)
    window.toggle_bookmark_panel()
    row = window.bookmark_panel.findChildren(_BookmarkRow)[0]
    row.edit_button.click()
    field = window.bookmark_panel.findChildren(QLineEdit)[0]
    field.setText("half a na")
    window._on_duration_changed(window._duration)            # what a length refinement from mpv does
    window._refresh_marks()
    assert window.bookmark_panel.is_editing
    assert window.bookmark_panel.findChildren(QLineEdit)[0] is field and field.text() == "half a na"
```
- [ ] **Step 2:** run it. Expected: FAIL (`is_editing` is False after the rebuild).
- [ ] **Step 3:** in `_refresh_marks`, call `bookmark_panel.set_items(...)` only when the panel is visible **and not
  `is_editing`**.
- [ ] **Step 4:** run `tests/test_bookmark_window.py`. Expected: pass. Mutation: drop the `is_editing` condition → fails.
- [ ] **Step 5:** commit `fix: the bookmark list is left alone while a name is being typed`.

### Task 5: No pins at the old length for a moment after opening a video

**Files:** Modify `ui/main_window.py` (`load_media_file`); Test `tests/test_bookmark_window.py`.

- [ ] **Step 1: failing test** (`shutil`, `AppSettings`, `load` helper exist in the file):

```python
def test_a_newly_opened_video_has_no_pins_until_its_length_is_known(window, sample_video, pump, tmp_path):
    other = str(tmp_path / "other.mp4")
    shutil.copy(sample_video, other)
    AppSettings().save_bookmarks(other, [{"t": 1.0, "name": ""}])
    load(window, sample_video, pump)                          # a length is known (about 3 s)
    window.load_media_file(other)
    tl = window.controller.timeline
    assert tl._duration == 0 and tl._pin_marks() == [], "the old video's length must not place the new video's pins"
    assert pump(lambda: len(tl._pin_marks()) == 1, timeout=10)
```
- [ ] **Step 2:** run it. Expected: FAIL (`tl._duration` is still the old length).
- [ ] **Step 3:** in `load_media_file`, right where `self._duration = 0.0` is reset, also call `self.controller.set_duration(0.0)`.
  Check by eye in the test run that the controller's time label shows its usual empty state for a video without a length.
- [ ] **Step 4:** run `tests/test_bookmark_window.py tests/test_window.py tests/test_playback_memory.py`. Expected: pass. Mutation:
  remove the call → fails.
- [ ] **Step 5:** commit `fix: pins wait for the new video's length instead of using the old one`.

### Task 6: Docs

**Files:** Modify `PROGRESS.md`, `CHANGELOG.md`.

- [ ] **Step 1:** in PROGRESS §1 change the status words of the five 2026-10 bullets: auto-update → "v1.3.0에 포함";
  playback memory, bookmarks + chapters, update/crash stability → "`main`에 병합, v1.4.0에 포함"; the home update button →
  "`main`에 병합, 1.4.1 예정". In §8-1 mark 1.3 and 1.4 rows with what shipped and what remains (`Ctrl+G`, `?` help, the split);
  add one bullet for this cleanup and the split with a pointer to the spec and this plan.
- [ ] **Step 2:** CHANGELOG `## Unreleased`: one bullet each for Tasks 1–5 (user-visible wording, English).
- [ ] **Step 3:** run `tests/test_release.py`. Expected: pass. Commit `docs: status after 1.4.0 and the 1.4.1 fixes`.

### Task 7: Old probe keys in the registry (ask first)

- [ ] **Step 1:** ask the person; only after a yes, run in PowerShell:
  `foreach ($k in 'PanePerf','PanePerfLegacy','PaneProbe','PaneProbeLegacy','PaneScratchShotLegacy') { $p = "HKCU:\Software\$k"; if (Test-Path $p) { Remove-Item $p -Recurse -Force } }`
- [ ] **Step 2:** verify `Test-Path 'HKCU:\Software\Pane'` is still `True` and that `PaneTest` / `PaneTestLegacy` were not touched.
  Nothing to commit.

### Task 8: Release 1.4.1 (each outward step needs the person's go-ahead)

**Files:** Modify `core/version.py` (`__version__`), `installer/pane.iss` (the doc line and `#define AppVersion`),
`release/README_RELEASE.txt` (lines 1 and 4), `CHANGELOG.md` (`## Unreleased` → `## 1.4.1 - <date>`). Procedure: `docs/RELEASING.md`.

- [ ] **Step 1:** bump the version in those places; full suite. Expected: all pass (rerun once on exit 139). Commit `release: 1.4.1`.
- [ ] **Step 2:** build: `./.venv/Scripts/python.exe tools/build_release.py --installer --sign-key "C:\Users\47sha\Documents\pane_update_private.key" --notes "<one English line>"`
  (run it in the background; it takes minutes). Copy `dist/Pane-1.4.1-setup.exe`, `-win64.zip`, `latest.json` to `dist/release-1.4.1/`.
- [ ] **Step 3 (ask first, it removes the installed Pane for a while):** back up `HKCU\Software\Pane` with
  `reg export`, uninstall the all-users Pane (elevated `unins000.exe /SILENT`), run
  `tools/install_test.py --installer dist/release-1.4.0/Pane-1.4.0-setup.exe --update-installer dist/Pane-1.4.1-setup.exe --sign-key <key>`
  (Expected: every check passes), then reinstall the official 1.4.0 with `/ALLUSERS /SILENT` and compare the settings export.
- [ ] **Step 4 (ask first):** merge the branch into `main` (`--no-ff`), `git tag -a v1.4.1 -m "Pane 1.4.1"`, push `main` and the tag.
- [ ] **Step 5:** the person publishes the GitHub release (installer + `latest.json`); then run `scratch/verify_release.py`
  (update its local path to `dist\release-1.4.1\...`). Expected: manifest verified, newer than 1.4.0, installer hash and size equal to the local build.
- [ ] **Step 6:** record the release in PROGRESS (like the 1.4.0 bullet) and commit `docs: 1.4.1 released`.

---

# Part 2 — the split (branch `refactor/main-window-split`, from `main` after Part 1)

Each of Tasks 10–15 follows the same recipe (the spec's "How each step is done"):

1. `grep -rn "<each moving name>" tests ui` — every hit outside the moving code needs a forwarder or a changed call.
2. Create the new module; cut the code out of `main_window.py` and paste it in; change only `self.` → `self.window.` for the
   window's things (or `window.` in a function), imports, and the lines named in the task. No other edit.
3. Leave the forwarding names the task lists; connect signals once, to one place.
4. `./.venv/Scripts/python.exe -m pyflakes ui/<new module>.py ui/main_window.py` — Expected: nothing that is not in
   `scratch/pyflakes_before.txt`.
5. Run the focused tests named in the task, then the full suite. Expected: the same count as the baseline, all pass.
6. `wc -l ui/main_window.py` goes into the commit message body. One commit per task.

### Task 9: Baseline and characterization tests

**Files:** Create `tests/test_split_wiring.py`; record numbers in `scratch/` (not committed).

- [ ] **Step 1:** `git checkout main && git checkout -b refactor/main-window-split`. Run the full suite and write down the
  pass count `N`; `wc -l ui/main_window.py` → `L`; `./.venv/Scripts/python.exe -m pyflakes ui > scratch/pyflakes_before.txt`.
- [ ] **Step 2:** write `tests/test_split_wiring.py` with these tests (all use the `window` fixture; they patch **window-level**
  names so they survive the moves):
  - `test_the_right_click_menu_has_these_entries`: a `FakeMenu(QMenu)` whose `exec` returns `None` after recording every action
    (recursively; separators as `"---"`; `[checked]` for a checked checkable action; `[disabled]` when disabled), patched in as
    `QMenu` on every module that has that name among `ui.main_window` and (once it exists) `ui.context_menu` — never call a real
    `QMenu.exec`. Call `window.show_context_menu(QPoint(10, 10))`. Expected list, exactly (the same with or without a video):

    ```
    파일 열기... (Ctrl+O) | --- | 일시정지 (Space) | 이전 영상 (Shift+,) [disabled] | 다음 영상 (Shift+.) [disabled]
    | 영상이 끝나면 다음 영상 자동 재생 [checked] | 재생 속도 (배속) → [0.8x, "1x  ✓", 1.2x, 1.25x, 1.4x, 1.5x, 1.75x, 2x,
    ---, 정밀 배속 슬라이더 & 프리셋 설정...] | 자막 (Subtitles) → [자막 켜기 / 끄기 (C), 외부 자막 파일 선택...] | ---
    | 현재 화면 고화질 캡처 (Ctrl+S) | 재생 정보 - 코덱, 디코더 (I) | PIP 항상 위 모드 (P) | 전체화면 (F) | ---
    | 설정... | Pane 정보 (v1.4.0) | Pane 종료 (Alt+F4)
    ```
    (compare against `f"Pane 정보 (v{APP_VERSION})"` so a version bump does not break it).
  - `test_hovering_the_bar_shows_the_pill_once`: with the `video` flow of `test_bookmark_window.py` (copy its `load` helper),
    wrap `window.seek_tip.show_at` in a counter, emit `window.controller.timeline.hover_moved.emit(1.0, x)`; expect 1 call.
  - `test_tracks_ready_loads_the_chapters_once`: set `window._current_file`, replace `window.engine.chapters` with a counter
    returning `[]`, emit `window.engine.tracks_ready`; expect 1 call.
  - `test_a_new_version_offer_reaches_the_card_once`: counter around `window.update_card.show_offer`, emit
    `window.update_checker.update_available.emit(MANIFEST)` (a `Manifest` like the one in `tests/test_update_button.py`); expect 1.
  - `test_the_thumbnail_and_chapter_switches_reach_the_settings_once`: counters around
    `window.app_settings.set_thumbnails_enabled` and `set_chapters_visible`; emit `window.controller.thumbnails_changed.emit(False)`
    and `chapters_changed.emit(False)`; expect 1 call each.
  - `test_a_key_is_handled_once`: counter around `window.toggle_mute`, `QTest.keyClick(window, Qt.Key_M)`; expect 1.
  - `test_closing_keeps_the_traced_order`: record `core.exit_trace.stage` names while `window.close()` runs; expect
    `["update check stopped", "thumbnails closed", "video surface released", "mpv terminated"]`.
- [ ] **Step 3:** run the file. Expected: all PASS now (they describe today's behaviour). Prove they bite: temporarily add a
  second `connect` of `_load_chapters` to `engine.tracks_ready` (with `scratch/mutate.py`) → `test_tracks_ready_loads_the_chapters_once` fails; restore.
- [ ] **Step 4:** full suite → `N + 7` (or the number you added). Commit `test: characterization tests before splitting main_window`.

### Task 10: `ui/viewport.py` — `VideoViewport`

**Files:** Create `ui/viewport.py`; Modify `ui/main_window.py`.

**Interfaces:** Produces `ui.viewport.VideoViewport` (the class, unchanged: its signals `file_dropped`, `clicked`,
`double_clicked`, `context_menu_requested`, the `start_screen`, `attach_mpv`, `release`, `show_empty_notice`).
`main_window.py` keeps `from ui.viewport import VideoViewport  # noqa: F401` so the old import path still works.

- [ ] Follow the recipe. Focused tests: `tests/test_window.py tests/test_start_screen.py tests/test_native_window.py tests/test_split_wiring.py`.
- [ ] Commit `refactor: move VideoViewport out of main_window`.

### Task 11: `ui/context_menu.py` — the right-click menu

**Files:** Create `ui/context_menu.py`; Modify `ui/main_window.py`.

**Interfaces:** Produces `def show_context_menu(window, global_pos: QPoint) -> None` (the body of today's
`MainWindow.show_context_menu`, with `self` → `window`). `MainWindow.show_context_menu(self, global_pos)` stays and only calls it.

- [ ] Follow the recipe. The menu characterization test must pass **unchanged** (its patch already covers `ui.context_menu`).
  Focused: `tests/test_split_wiring.py tests/test_window.py`.
- [ ] Commit `refactor: move the right-click menu out of main_window`.

### Task 12: `ui/key_bindings.py` — `KeyRouter`

**Files:** Create `ui/key_bindings.py`; Modify `ui/main_window.py`.

**Interfaces:** Produces `class KeyRouter: __init__(self, window)`, `handle(self, event: QKeyEvent) -> bool` (True when the key
was consumed: every branch that today ends `event.accept(); return`). `MainWindow.keys = KeyRouter(self)` is created in
`_init_floating_widgets`; `keyPressEvent(self, event)` becomes `if not self.keys.handle(event): super().keyPressEvent(event)`.

- [ ] Follow the recipe. **The order of the checks must not change** (settings panel, rename-field guard, bookmark keys, then the
  rest) — compare the new function to the old one top to bottom before running tests. Calls go to the window's public
  names (`toggle_mute`, `add_bookmark`, …), which are patchable in the tests.
- [ ] Focused: `tests/test_window.py tests/test_bookmark_window.py tests/test_split_wiring.py tests/test_seek_indicator.py tests/test_speed_osd.py`.
- [ ] Commit `refactor: move key handling out of main_window`.

### Task 13: `ui/seek_tips.py` — `SeekTips`

**Files:** Create `ui/seek_tips.py`; Modify `ui/main_window.py`.

**Interfaces:** Produces `class SeekTips(QObject)` created in `_init_floating_widgets` where the pill and the picture are
created today (`self.tips = SeekTips(self)`), owning `seek_tip`, `thumbnail_tip`, `thumbnail_provider`, `thumbnails_on`,
`thumbnails_on_stop`, the pointer spot, the viewport the tips were placed for, the rest timer, and `STOP_DELAY_MS = 300`. Methods:
`show(seconds: float, x: float)`, `hide()`, `request()`, `on_ready(path, bucket, image)`,
`on_thumbnails_changed(enabled)`, `on_thumbnails_on_stop_changed(enabled)`, `area_changed(viewport_rect: QRect)` (what
`_reposition_floating_widgets` does with `_tips_viewport`: hide the tips when the area changed — the panel hiding that sits in
the same `if` stays in `MainWindow` until Task 14), `shutdown()`.
**Forwarders on `MainWindow`:** properties `seek_tip`, `thumbnail_tip`, `thumbnail_provider`, `thumbnails_on` and
`thumbnails_on_stop` (read-write), method `_hide_seek_tips()`. Signal connections in `_connect_signals` point at `self.tips.*`;
`_on_close` calls `self.tips.shutdown()` in the place of `self.thumbnail_provider.shutdown()`, same trace line.
For now the pill's text, dot and detail are still decided inside `SeekTips.show` using `window.bookmarks`, `window.chapters`,
`window.chapters_on`.

- [ ] Follow the recipe. Focused: `tests/test_seekbar_hover.py tests/test_thumbnail_window.py tests/test_thumbnail_tip.py tests/test_thumbnails.py tests/test_split_wiring.py tests/test_exit_trace.py tests/test_bookmark_window.py`.
- [ ] Commit `refactor: move the seek-bar pill and thumbnails out of main_window`.

### Task 14: `ui/bookmark_flow.py` — `BookmarkFlow`

**Files:** Create `ui/bookmark_flow.py`; Modify `ui/main_window.py`, `ui/seek_tips.py`.

**Interfaces:** Produces `class BookmarkFlow(QObject)` (`self.marks = BookmarkFlow(self)`, created before `SeekTips`) owning
`bookmarks: list`, `chapters: list`, `chapters_on: bool`, `panel` (None until first use). Methods (the bodies of today's):
`usable() -> bool`, `forget()`, `open_video(path)` (= `forget()`, then load the stored bookmarks and `refresh()`),
`load_chapters()`, `refresh()`, `set_bookmarks(items)`, `add()`, `rename(t, name)`, `delete(t)`, `seek_to(t, say: bool)`,
`jump(direction: int)`, `toggle_panel()`, `on_chapters_changed(enabled)`, `hide_panel()`, `raise_panel()`,
`panel_visible() -> bool`, and **new** `pill_for(seconds: float, x: float) -> tuple[str, QColor | None, str]` returning the
`(text, dot, detail)` that `SeekTips.show` computes inline today (bookmark under the pointer first, then the chapter, then the
time) — `SeekTips.show` now calls `window.marks.pill_for(...)`.
**Forwarders on `MainWindow`:** properties `bookmarks`, `chapters`, `chapters_on`, `bookmark_panel` (read-only except
`chapters_on`, which tests read), methods `add_bookmark`, `jump_bookmark`, `toggle_bookmark_panel`, `rename_bookmark`,
`delete_bookmark`, `_load_chapters`, `_on_chapters_changed`, `_refresh_marks`, `_seek_to_mark`, `_forget_marks`, `_marks_usable`.
The `controller.hold_visible` lambda, `_reposition_floating_widgets` (panel hide and raise), `load_media_file`,
`_show_file_problem`, `_on_duration_changed` call the unit. `_time_pos` stays on the window.

- [ ] Follow the recipe. Focused: `tests/test_bookmark_window.py tests/test_bookmarks.py tests/test_bookmark_panel.py tests/test_bookmark_button.py tests/test_timeline_marks.py tests/test_split_wiring.py tests/test_seekbar_hover.py`.
- [ ] Commit `refactor: move bookmarks and chapters out of main_window`.

### Task 15: `ui/update_flow.py` — `UpdateFlow`

**Files:** Create `ui/update_flow.py`; Modify `ui/main_window.py`.

**Interfaces:** Produces `class UpdateFlow(QObject)` (`self.updates = UpdateFlow(self)`), owning `update_card`,
`update_checker`, the install-wait timer, `_installer_path`, `_update_offer`, `_home_check`. Methods (today's bodies):
`ask(done)`, `on_about_check(box, button)`, `check_from_home()`, `on_available(manifest)`, `on_progress(done, total)`,
`on_installer_ready(path)`, `installer_stalled()`, `on_failed(message)`, `start()`, `dismiss()`, `card_blocked() -> bool`,
`refresh_card()`, `place_card()`, `request_stop()` (= `update_checker.request_stop()` + `wait_for_done(500)` + the
`exit_trace.stage("update check stopped")` line, called by `_on_close` at the same point).
**Constants stay on `MainWindow`** (`UPDATE_CHECK_TIMEOUT_MS`, `INSTALL_WAIT_MS`) and the unit reads them through the window at
call time, because tests patch them on the window.
**Forwarders on `MainWindow`:** properties `update_card`, `update_checker`; methods `_ask_for_update`, `_on_about_check`,
`_check_update_from_home`, `_refresh_update_card`, `_start_update`, `_dismiss_update`, `_update_card_blocked`,
`_on_update_available`. The `title_bar.update_clicked`, `update_card.*` and `update_checker.*` connections point at the unit;
the `QTimer.singleShot(5000, self.update_checker.check)` stays as it is.

- [ ] Follow the recipe. Focused: `tests/test_update_button.py tests/test_update_window.py tests/test_update_ui.py tests/test_update_checker.py tests/test_update_checker_stop.py tests/test_split_wiring.py tests/test_exit_trace.py`.
- [ ] Commit `refactor: move the update notice out of main_window`.

### Task 16: Wrap-up and review

- [ ] **Step 1:** `wc -l ui/main_window.py` (Expected: about 900 or fewer; each new module under 300), `./.venv/Scripts/python.exe -m pyflakes ui`
  compared with `scratch/pyflakes_before.txt` (Expected: nothing new), the full suite (Expected: `N + 7`, all pass; rerun once on exit 139).
- [ ] **Step 2:** update PROGRESS (the split is done: modules, the forwarding names, the rule "new code goes in the unit, not in
  `MainWindow`") and mark the spec's status "implemented". Commit `docs: main_window split done`.
- [ ] **Step 3:** `review-package` from the merge base, then one fresh review on the most capable model with the Review Focus
  above and the ledger's rulings; sort findings, fix Critical/Important with a failing test first, defer the rest in the final message.
- [ ] **Step 4:** offer (do not assume) a short look at the real window; merge and push only when the person says so. No release
  of its own: the split ships with the next feature release.
