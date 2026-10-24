# Bookmarks and Chapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mark places of a video with one key, see them as amber pins on the seek bar, jump back by click / key / list panel; show chapter starts as thin gaps of the bar with the chapter name in the hover pill; chapters switchable in Settings.

**Architecture:** Pure logic in `core/bookmarks.py` (no Qt); `AppSettings` stores bookmarks per video like the resume positions; `TimelineSlider` gets `set_marks()` (pins drawn after the fill, gaps cut out of the groove and fill with a clip); `SeekTimeTip` learns a dot and a lighter detail text; a `BookmarkPanel` (modelled on `TrackPopup`) lists them; `MainWindow` wires keys, pill texts, the panel and the settings switch.

**Tech Stack:** Python 3.14, PySide6, python-mpv (`chapter-list`), pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-24-bookmarks-chapters-design.md` (read it first; mockups on the design canvas "Pane 북마크·챕터 시안").

## Global Constraints

- Branch `feature/bookmarks-chapters`. Commits as the steps say, English messages ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Never `git stash`. Tests never touch the real `HKCU\Software\Pane` (`tests/conftest.py` isolates settings as `PaneTest`).
- Bookmark pin: amber `#FFC857`, **4 × 18 px**, radius 2; within **6 px** of the pointer **5 × 24 px** with a 1.5 px white (alpha 230) outline. Hit radius for a click / hover: **6 px**.
- Chapter gap: **2 px** at rest, **3 px** while the bar is hovered (`GlassSlider._hover` 0..1: `2 + _hover`), not painted at all (the video shows through); none for the first chapter; skipped when the gap is closer than **10 px** to the previous kept gap; **no gaps at all above 60**.
- Store: `bookmarks` JSON dict path → `[{"t": float (2 decimals), "name": str}]`, sorted by `t`; **100 per video**, **200 videos** (least recently changed first out). `name == ""` shows as the time (`format_clock`).
- Add: not within **1.0 s** of an existing one (pill `이미 북마크가 있어요 <time>`), else pill `북마크 <time>`. Previous = last `t < now − 1.0`, next = first `t > now + 0.5`; none: pill `이전 북마크가 없어요` / `다음 북마크가 없어요`. Keys: `B` add, `Shift+B` panel, `Alt+←` / `Alt+→` jump (never the 5 s seek).
- Pill priority: bookmark under the pointer > chapter > plain time. Chapter text: `<title>` (no title: `챕터 N`) then the time, lighter. Bookmark text: amber dot, name or time, then the time.
- Chapters: read when mpv reports the file loaded; keep those with `0 <= time < length` and at least 1 s after the previous; fewer than 2 kept = none. **Deviation from the spec text** ("drop `time <= 0`"): the first chapter (time 0) is kept so that the pill can name it and a two-chapter file works; it simply gets no gap (a gap is drawn for every kept chapter with `time > 0.5`). Ledger it as a ruling when executing. Setting `chapters_visible` (default on), Settings > 일반 row title `재생바에 챕터 표시`; off = no gaps and no chapter name.
- Cost when unused: no marks = the slider paints exactly as before; nothing created until needed (the panel on first use).
- New control button `bookmarks` after `subtitle`; saved layouts get it **once** by migration (`LAYOUT_ADDITIONS`, settings key `layout_additions_version`), never a layout reset (`LAYOUT_VERSION` stays 5).

## Review Focus

- Typing in the panel's rename field must never trigger `B`, `Space`, `←` … of the player. Task 9.
- `Alt+←/→` must never also seek 5 s; `B` / `Alt+←/→` with no video or an unknown length do nothing. Task 9.
- A bookmark beyond the video's length (the file was replaced) must not be drawn and must not be jumped to; still listed, dimmed. Tasks 4, 7, 9.
- Broken settings values (non-number `t`, non-string name, a list that is not a list) must never stop the app. Tasks 1, 2.
- A video with neither bookmarks nor chapters must paint pixel-identically to before. Task 4.
- The layout migration must keep the owner's layout, add the button once, and not bring it back after the owner removed it. Task 6.

---

## File Structure

- Create `core/bookmarks.py`, `ui/bookmark_panel.py`, `tests/test_bookmarks.py`, `tests/test_bookmark_store.py`, `tests/test_timeline_marks.py`, `tests/test_bookmark_panel.py`, `tests/test_bookmark_window.py`.
- Modify `core/settings.py`, `core/player_engine.py`, `ui/glass_slider.py`, `ui/timeline_slider.py`, `ui/overlay.py` (`SeekTimeTip`), `ui/icons.py`, `ui/glass_controller.py`, `ui/settings_panel.py`, `ui/main_window.py`, docs.

### Task 1: Bookmark and chapter logic (pure)

**Files:** Create `core/bookmarks.py`; Test `tests/test_bookmarks.py`.

**Interfaces — Produces** (all in `core/bookmarks.py`; items are dicts `{"t": float, "name": str}`):
`MAX_PER_VIDEO = 100`; `clean(items) -> list[dict]` (valid items only: `t` a finite non-negative number, `name` a str, else dropped; `t` rounded to 2 decimals; sorted by `t`; not a list = `[]`; capped at 100); `add(items, t) -> (list, added: bool, existing_t: float | None)`; `rename(items, t, name) -> list` and `remove(items, t) -> list` (match `t` within 0.005); `previous(items, now) -> float | None`; `next_after(items, now) -> float | None`; `nearest(marks, x, radius=6.0) -> float | None` (`marks` = `[(t, x_pixel)]`, the closest within `radius`); `display_name(item) -> str` (name or `format_clock(t)`); `chapters_from_mpv(raw, duration) -> list[tuple[float, str]]` (the kept chapters including the one at 0; missing title = `""`; `[]` when fewer than 2 or `raw` is not a list); `chapter_at(chapters, t) -> tuple[int, str] | None` (1-based index of the chapter that contains `t`, title or `챕터 N`; `None` before the first); `gap_ratios(chapter_times, duration, span, min_px=10.0, max_gaps=60) -> list[float]` (positions 0..1 of the gaps to draw: every time `> 0.5`, skipping those closer than `min_px` to the last kept one; `[]` above `max_gaps`).

- [ ] **Step 1: Write the failing tests** (`tests/test_bookmarks.py`), each with the spec's exact numbers:
  - `test_clean_keeps_valid_items_sorted_and_drops_the_rest`: `clean([{"t": 5, "name": "b"}, {"t": "x"}, {"t": -1, "name": ""}, {"t": 2.123, "name": 3}, {"t": 1, "name": "a"}, 7])` == `[{"t": 1.0, "name": "a"}, {"t": 5.0, "name": "b"}]`; `clean("nope") == []`; 150 valid items → 100.
  - `test_add_refuses_a_second_one_within_a_second`: `add([{"t": 10.0, "name": ""}], 10.9)` → `(same list, False, 10.0)`; `add(..., 11.1)` → added, sorted; the 101st is refused (returns `added=False`, `existing_t=None`).
  - `test_rename_and_remove_match_by_time`.
  - `test_previous_and_next_use_the_margins`: bookmarks at 10, 20, 30: `previous(items, 20.5) == 20.0`, `previous(items, 20.0) == 10.0` (not itself: `t < now − 1.0`), `previous(items, 10.5) is None`, `next_after(items, 20.0) == 30.0`, `next_after(items, 20.4) == 30.0`, `next_after(items, 29.6) is None`.
  - `test_nearest_picks_the_closest_pin_within_the_radius`: `nearest([(10, 100.0), (20, 105.0)], 103.0) == 20`, `nearest(..., 120.0) is None`.
  - `test_display_name`: empty name → `"0:34:12"`-style `format_clock`; name kept.
  - `test_chapters_from_mpv_keeps_the_usable_and_needs_two`: raw `[{"time": 0, "title": "Intro"}, {"time": 760, "title": "Graphs"}, {"time": 760.4, "title": "dup"}, {"time": 5000, "title": "late"}, {"time": -1, "title": "bad"}]`, duration 3860 → `[(0.0, "Intro"), (760.0, "Graphs")]`; a list with only `{"time": 0, "title": "Intro"}` → `[]`; `raw` not a list → `[]`; a missing title → `""`.
  - `test_chapter_at_names_the_chapter_under_a_time`: titles and the `챕터 N` fallback.
  - `test_gap_ratios_skip_close_gaps_and_give_up_above_sixty`: chapter times `[0, 760, 1800, 3000]` over 3860 s and 880 px → 3 ratios (none for the one at 0); two chapters 5 px apart → one gap; 70 well-spaced chapters → `[]`.
- [ ] **Step 2: Run** `pytest tests/test_bookmarks.py -q` — Expected: FAIL (`ModuleNotFoundError: core.bookmarks`).
- [ ] **Step 3: Implement** the functions above in `core/bookmarks.py` (import `format_clock` from `core.media_info`).
- [ ] **Step 4: Run** `pytest tests/test_bookmarks.py -q` — Expected: PASS. Mutation check: change the add margin to 0.5 → the margin test fails; restore.
- [ ] **Step 5: Commit** `feat: bookmark and chapter logic`.

### Task 2: Settings store

**Files:** Modify `core/settings.py`; Test `tests/test_bookmark_store.py`.

**Interfaces — Consumes:** `core.bookmarks.clean`. **Produces:** `AppSettings.get_bookmarks(path) -> list[dict]` (cleaned), `save_bookmarks(path, items) -> None` (cleaned; an empty list removes the video's entry; the saved video moves to the end; > 200 videos drop the oldest), `get_chapters_visible() -> bool` (default True), `set_chapters_visible(bool)`. Keys: `bookmarks`, `chapters_visible`.

- [ ] **Step 1: Failing tests:** `test_bookmarks_round_trip_per_video`; `test_an_empty_list_forgets_the_video`; `test_the_two_hundred_video_limit_drops_the_least_recently_changed`; `test_broken_stored_values_are_ignored` (the stored string `"{not json"`, a dict whose value is `"x"`, an item list with junk → `[]` / cleaned); `test_chapters_visible_defaults_to_on_and_is_remembered`.
- [ ] **Step 2:** Run `pytest tests/test_bookmark_store.py -q` — Expected: FAIL (`AttributeError`).
- [ ] **Step 3:** Implement with `_get_dict` / `_set_dict` like `save_resume_position`; move-to-end on save.
- [ ] **Step 4:** Run; Expected: PASS. **Step 5: Commit** `feat: store bookmarks per video and the chapter switch`.

### Task 3: Chapters from the engine

**Files:** Modify `core/player_engine.py`; Test `tests/test_bookmarks.py` (engine part, uses the `engine` fixture).

**Interfaces — Consumes:** `core.bookmarks.chapters_from_mpv`. **Produces:** `PlayerEngine.chapters() -> list[tuple[float, str]]` (reads mpv's `chapter-list`, passes the engine's duration; any error = `[]`).

- [ ] **Step 1: Failing tests:** `test_chapters_of_a_file_without_chapters_is_empty` (`sample.mp4` loaded with `engine` fixture and `pump`); `test_chapters_reads_mpvs_chapter_list` (monkeypatch `engine._track_list`-style: patch `engine.mpv._get_property` for `"chapter-list"` to return three dicts and set `engine._duration = 3860`; expect the cleaned tuples); `test_a_failing_property_read_gives_no_chapters`.
- [ ] **Step 2:** FAIL (`AttributeError: chapters`). **Step 3:** implement next to `audio_tracks`. **Step 4:** PASS. **Step 5: Commit** `feat: the engine's chapters`.

### Task 4: Pins and gaps on the seek bar

**Files:** Modify `ui/glass_slider.py` (`paintEvent`), `ui/timeline_slider.py`; Test `tests/test_timeline_marks.py` (real renders: `widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))`, never `grab()`).

**Interfaces — Consumes:** `core.bookmarks.gap_ratios`, `nearest`. **Produces:** `GlassSlider.track_gaps(margin, span, cy, thickness) -> list[QRectF]` (default `[]`; `paintEvent` draws the groove and the fill through a clip that excludes those rects); `TimelineSlider.set_marks(bookmarks: list[float], chapters: list[float])`, `set_chapters_visible(bool)`, `pin_at(x: float) -> float | None` (seconds of the pin within 6 px of `x`), signal `pin_pressed = Signal(float)`; constants `PIN_COLOR = QColor(255, 200, 87)`, `PIN_W, PIN_H = 4, 18`, `PIN_W_NEAR, PIN_H_NEAR = 5, 24`.

- [ ] **Step 1: Failing tests:**
  - `test_without_marks_the_bar_paints_exactly_as_before`: two sliders (one never touched, one `set_marks([], [])` then `set_chapters_visible(True)`) render to identical images.
  - `test_a_chapter_gap_is_not_painted_and_its_neighbours_are`: duration 3860, chapters `[760, 1800]`, slider width 900: at the gap's x the alpha is 0 on the groove row (transparent background rendered), 2 px left of it > 0; with the played part over it (set_time_pos past it) still 0.
  - `test_the_gap_is_wider_while_the_bar_is_hovered`: `_hover = 1.0` → the transparent run is 3 px, at rest 2.
  - `test_gaps_follow_the_switch_and_the_limits`: `set_chapters_visible(False)` → no gap; 70 chapters → none; two chapters 5 px apart → one.
  - `test_a_pin_is_drawn_amber_four_by_eighteen_and_bigger_near_the_pointer`: pixel at the pin's centre is `PIN_COLOR` (alpha 255), its width 4 px at rest; with `_hover_ratio` at the pin → 5 px wide.
  - `test_a_pin_at_the_very_start_or_end_stays_inside_the_bar`: pins at `0.0` and at the duration are drawn fully inside the widget (no clipped half pin).
  - `test_a_bookmark_beyond_the_length_is_not_drawn`: `set_marks([5000.0], [])` with duration 3860 draws nothing extra.
  - `test_pressing_a_pin_emits_pin_pressed_and_does_not_move_the_handle`: `QTest.mousePress` at the pin's x → `pin_pressed` gets the pin's time, `value()` unchanged, `seek_requested` not emitted; elsewhere `seek_requested` as today.
  - the existing `tests/test_seekbar_hover.py` must stay green.
- [ ] **Step 2:** FAIL. **Step 3:** implement: `paintEvent` builds `QRegion(self.rect())` minus the gap rects (as ints) and `p.setClipRegion` around the groove and fill drawing only, then clears the clip; pins are drawn in `paint_over_track` (after the preview, before the handle). The gap x positions come from `gap_ratios(chapters, duration, span)`; gap width `2 + self._hover`. **Step 4:** run the new file and `tests/test_seekbar_hover.py tests/test_glass_widgets.py` — PASS. Mutation: draw the gap with a solid colour instead of clipping → the transparent-pixel test fails; restore.
- [ ] **Step 5: Commit** `feat: bookmark pins and chapter gaps on the seek bar`.

### Task 5: The hover pill with a dot and a detail

**Files:** Modify `ui/overlay.py`; Test `tests/test_seekbar_hover.py` (add).

**Interfaces — Produces:** `SeekTimeTip.show_at(text, x_center, y_bottom, bounds, dot: QColor | None = None, detail: str = "")` — the amber dot (8 px) before `text` and the lighter `detail` (alpha 180) after it; the pill widens for them; with no dot and no detail it is exactly as before.

- [ ] **Step 1: Failing tests:** `test_the_pill_without_dot_or_detail_is_as_before` (same size and pixels as a pill made by the old call); `test_the_pill_with_a_dot_has_an_amber_pixel_at_its_left_and_is_wider`; `test_the_detail_is_drawn_lighter_than_the_text` (compare the brightest pixel of the detail area with the text area); `test_the_wider_pill_still_stays_inside_the_bounds`.
- [ ] **Step 2:** FAIL. **Step 3:** implement (width = padding + dot + text + gap + detail). **Step 4:** PASS (`tests/test_seekbar_hover.py` whole file). **Step 5: Commit** `feat: the time pill can show a dot and a detail`.

### Task 6: Control button and the layout migration

**Files:** Modify `ui/icons.py` (`bookmark` icon: a ribbon outline in the style of the others), `ui/glass_controller.py`; Test `tests/test_bookmark_button.py` (in the style of `tests/test_controller.py`).

**Interfaces — Produces:** `BUTTON_METADATA["bookmarks"] = {"name": "북마크", "icon_name": "bookmark"}`; `DEFAULT_LAYOUT["right"] = ["screenshot", "subtitle", "bookmarks", "volume", "fullscreen", "settings"]`; `GlassController.bookmarks_clicked = Signal()`, `GlassController.btn_bookmarks` (tooltip `북마크 (Shift+B)`); `LAYOUT_ADDITIONS = [("bookmarks", "right", "subtitle")]`, `LAYOUT_ADDITIONS_VERSION = 1`; `_load_layout` applies the additions to a saved layout once.

- [ ] **Step 1: Failing tests:** `test_the_default_layout_has_the_bookmark_button_after_the_subtitle_button`; `test_a_saved_layout_gets_the_button_once_after_the_subtitle_button_and_keeps_everything_else` (save a custom layout without it; reload: the same order plus the button after `subtitle`; saved marker = 1); `test_a_removed_button_does_not_come_back` (after the migration the owner saves a layout without it; the next load keeps it out); `test_a_layout_without_a_subtitle_button_gets_it_at_the_end_of_the_right_zone`; `test_a_fresh_install_gets_the_default_and_the_marker`; `test_clicking_the_button_emits_bookmarks_clicked`; `test_the_layout_editor_lists_the_new_button` (`BUTTON_METADATA` key with an existing icon).
- [ ] **Step 2:** FAIL. **Step 3:** implement; `_create_widget_for_key("bookmarks")` mirrors `"subtitle"`. **Step 4:** run these and `tests/test_controller.py tests/test_layout_dialog.py tests/test_settings_panel.py` — PASS. **Step 5: Commit** `feat: bookmark button in the controls`.

### Task 7: The list panel

**Files:** Create `ui/bookmark_panel.py`; Test `tests/test_bookmark_panel.py`.

**Interfaces — Consumes:** `core.bookmarks.display_name`, `core.media_info.format_clock`, `ui.glass_button.paint_glass_panel`, the pattern of `ui/track_popup.py` (`toggle_above_widget`, outside-click dismissal through an application event filter, Esc closes). **Produces:** `class BookmarkPanel(QWidget)` with signals `jump_requested(float)`, `add_requested()`, `rename_requested(float, str)`, `delete_requested(float)`; `set_items(items: list[dict], duration: float)` (items beyond `duration` are dimmed and not clickable); `toggle_above_widget(target, align_to=None, above=None)`; property `is_editing -> bool` (a rename field has the focus); fixed width 380; rows 44 px (amber dot, name, time; pencil and ✕ visible on hover); header `북마크` + count + button `지금 위치  B`; empty text `아직 북마크가 없어요 · B 로 지금 위치를 저장해요`; footer hint (`이전 / 다음 북마크: Alt + ← / Alt + →`).

- [ ] **Step 1: Failing tests** (real widget, `qapp`): `test_rows_show_the_name_or_the_time_and_the_time`; `test_the_count_and_the_empty_state`; `test_clicking_a_row_asks_to_jump`; `test_the_add_button_asks_to_add`; `test_the_pencil_opens_an_edit_field_and_enter_saves_the_new_name` (`rename_requested(t, "새 이름")`, `is_editing` True during the edit, False after); `test_escape_cancels_the_edit_and_a_second_escape_closes_the_panel`; `test_an_empty_name_is_saved_as_empty` (back to the time); `test_the_x_asks_to_delete_at_once`; `test_a_bookmark_beyond_the_length_is_dimmed_and_does_not_ask_to_jump`; `test_a_click_outside_closes_it`; `test_typing_in_the_edit_field_does_not_leave_the_panel` (a `QTest.keyClicks(field, "bB ")` leaves the text in the field).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5: Commit** `feat: the bookmark list panel`.

### Task 8: The chapter switch in Settings

**Files:** Modify `ui/settings_panel.py`, `ui/glass_controller.py`, `ui/main_window.py` (persist and keep `self.chapters_on`); Test `tests/test_settings_panel.py` (add), `tests/test_bookmark_window.py` (start it).

**Interfaces — Produces:** `CHAPTERS_ROW = ("재생바에 챕터 표시", "챕터가 있는 영상에서 재생바를 챕터마다 가늘게 끊고, 마우스를 올리면 챕터 이름을 보여 줘요.")`; `SettingsPanel(..., chapters_on: bool = True)` with `chapters_changed = Signal(bool)`, `row_chapters`, `switch_chapters` on the 일반 tab; `GlassController.chapters_changed`, attribute `chapters_on`; `MainWindow.chapters_on` (from settings, kept current) and `MainWindow._on_chapters_changed(bool)` (saves; applies to the slider in Task 9).

- [ ] **Step 1: Failing tests:** `test_the_general_tab_has_the_chapter_switch_on_by_default`; `test_the_switch_saves_at_once_and_updates_the_window` (open settings, toggle, `AppSettings().get_chapters_visible()` False, `window.chapters_on` False); `test_the_panel_keeps_its_size`.
- [ ] **Step 2:** FAIL. **Step 3:** implement like `updates_changed`. **Step 4:** PASS (`tests/test_settings_panel.py tests/test_bookmark_window.py`). **Step 5: Commit** `feat: switch for the chapter marks`.

### Task 9: Wiring in the main window

**Files:** Modify `ui/main_window.py` (and `ui/glass_controller.py` for nothing more than the signal); Test `tests/test_bookmark_window.py`.

**Interfaces — Consumes:** everything above; `window`, `sample_video`, `pump` fixtures; hover is driven by `timeline.hover_moved.emit(seconds, x)` and presses by `QTest.mousePress`. **Produces:** `MainWindow.bookmarks` (the current video's list), `add_bookmark()`, `jump_bookmark(direction: int)`, `toggle_bookmark_panel()`, `_refresh_marks()` (pins and gaps into the slider; called after a video's tracks are ready, after every change and after the chapter switch), `self.bookmark_panel` (created on first use).

- [ ] **Step 1: Failing tests (names; assertions from the spec):**
  - `test_b_adds_a_bookmark_at_the_current_time_and_says_so` (pill text `북마크 0:00`-style, list length 1, pin on the slider) and `test_a_second_b_within_a_second_does_not_duplicate` (pill `이미 북마크가 있어요`).
  - `test_alt_right_and_alt_left_jump_between_bookmarks_and_never_seek_five_seconds` (three bookmarks, positions after each key, `engine` time within 0.1 s; with no earlier / later one the pill says `이전 북마크가 없어요` / `다음 북마크가 없어요` and the position is unchanged).
  - `test_b_and_the_jump_keys_do_nothing_without_a_video` (no pill, no store change).
  - `test_shift_b_and_the_button_open_the_panel_and_the_panel_acts` (jump, rename, delete reach the store and the pins; "지금 위치" adds).
  - `test_keys_typed_in_the_rename_field_never_reach_the_player` (open the panel, start a rename, send `B`, `Space`, `Left` to the field: no bookmark added, playback state and position unchanged).
  - `test_opening_another_video_shows_that_videos_bookmarks` (pins swap) and `test_a_bookmark_beyond_the_length_is_not_drawn_nor_jumped_to`.
  - `test_clicking_a_pin_seeks_exactly_to_it`.
  - `test_the_pill_over_a_pin_shows_the_dot_name_and_time_and_over_a_chapter_the_chapter_name` (monkeypatch `engine.chapters` to three chapters; priority pin > chapter > time; `챕터 N` fallback) and `test_with_the_chapter_switch_off_there_are_no_gaps_and_no_chapter_name`.
  - `test_resizing_the_window_closes_the_panel` and `test_a_video_with_no_chapters_and_no_bookmarks_has_no_marks`.
- [ ] **Step 2:** FAIL. **Step 3:** implement: keys in `keyPressEvent` — handle `Alt` + `Left` / `Right` and `B` / `Shift+B` **before** the plain `Left` / `Right` branch; when `bookmark_panel.is_editing` return early so keys stay in the field; `_show_seek_tip` asks the timeline for a pin under `x` and the chapters (`bookmarks.chapter_at`) for the pill; `engine.tracks_ready` (already emitted once per file) triggers loading bookmarks and chapters; settings `save_bookmarks` after each change. **Step 4:** run `tests/test_bookmark_window.py` plus `tests/test_window.py tests/test_thumbnail_window.py tests/test_playback_memory.py tests/test_seekbar_hover.py` — PASS. Mutations: move the `Alt` branch below the plain `Left` branch → the "never seek five seconds" test fails; drop the `is_editing` guard → the rename-field test fails; restore.
- [ ] **Step 5:** run the whole suite (`python -m pytest -q`). Expected: all pass except the intermittent native crash noted in PROGRESS.md §5 #33 (rerun once if the process dies). **Step 6: Commit** `feat: bookmarks and chapter marks in the main window`.

### Task 10: Docs and a look at the real window

**Files:** Modify `PROGRESS.md`, `CHANGELOG.md`, `release/README_RELEASE.txt` (and the key table in `README.md` / the release notes' key list: `B`, `Shift+B`, `Alt+←/→`); no new tests beyond `tests/test_release.py` staying green (it checks that every key in the code is documented).

- [ ] **Step 1:** Write the notes: PROGRESS §1 bullet (decisions: C pins, C-2 gaps, no dialog, switch, migration, limits), CHANGELOG `## Unreleased` entry, the release notes' feature line and key rows.
- [ ] **Step 2: Look at it** with the isolated-settings screenshot approach used for the thumbnails (`scratch/shot_*.py`, a temporary `APP_NAME`, registry key deleted afterwards): the Big Buck Bunny clip with three bookmarks, hover over a pin, the panel open, and (with a monkeypatched chapter list) the gaps. Show the owner the screenshots; fix only what the owner points out.
- [ ] **Step 3:** `python -m pytest -q`; Expected: green (see the note in Task 9). **Step 4: Commit** `docs: bookmarks and chapter marks`.
