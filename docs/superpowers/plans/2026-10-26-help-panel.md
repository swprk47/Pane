# The shortcut help panel (`?`) — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a help panel listing Pane's shortcuts, mouse gestures and a few tips, opened by `?`, a right-click menu entry and a title-bar button.

**Architecture:** three new files (`ui/help_content.py` data, `ui/help_panel.py` the glass panel in two layouts, `ui/help_flow.py` the open / close / layout logic, owned by the window as `window.help`), plus small hooks in the title bar, the key router, the context menu and the window. A drift-guard test ties the key router to the help data.

**Tech Stack:** Python 3.14 (`./.venv/Scripts/python.exe`), PySide6, pytest, pyflakes.

**Spec:** `docs/superpowers/specs/2026-10-26-help-panel-design.md` (approved 2026-10-26). Mock-ups: the /design canvas "Pane 단축키 도움말 시안" (A2 centred, B drawer, buttons ②). Throw-away mock code: `scratch/help_mock.py` (colours, sizes and strings below are taken from it).

## Global Constraints

- `./.venv/Scripts/python.exe` only; never `python -` (waits for stdin); write patch scripts to `scratch/` with the Write tool, apply one replacement with `scratch/apply.py <file> <old> <new>` (`\n` = newline), try a mutation with `scratch/mutate.py <file> <old> <new> <pytest args>` (it restores the file).
- Commits in English ending `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; branch `feature/help-panel`; merge `--no-ff` and push only when the owner says so; never `git stash`.
- New code goes in a unit, not into `MainWindow` (PROGRESS rule after the split). The window only creates `self.help` and connects.
- Anything that opens a real window, moves the mouse (`--run-e2e`) or touches the registry needs the owner's go-ahead first.
- The full suite may die once with exit code 139/132 (known native crash): run it again once.
- Style numbers (from the spec and the mock): body `QColor(11, 13, 19, 242)` under `paint_glass_panel(p, rect, 18, calm=True)`; dim `QColor(0, 0, 0, 215)`; key chips 13 px bold, background `rgba(255,255,255,0.16)`, border `1px solid rgba(255,255,255,0.26)`, radius 6, padding `3px 9px`; descriptions 14 px `rgba(255,255,255,0.92)`; group titles 13 px bold `#9FC5FF`; tips 13 px `rgba(255,255,255,0.88)`; font `"Segoe UI Variable Text", "Segoe UI", sans-serif`.
- Sizes: centred panel `min(900, W - 80) × min(640, H - 92)` centred in the video area (`W × H`); drawer 420 px wide, `14` px from the right edge, top at `46`, bottom margin `14`, height `H - 46 - 14` (at most 640).

## Rulings made while planning

- **Layout threshold.** The spec says "centred when no video and the area is at least 940 × 680", but the default window is 1060 × 640, so a friend's first home screen would show the drawer. Ruling: the centred panel shrinks to the window (sizes above) and its body scrolls when the content does not fit (the right column is about 640 px tall); the rule becomes **centred when no video is loaded and the area is at least 720 × 460, else the drawer**. The spec text was updated together with this plan. Cost if wrong: on a default window the right column scrolls a little (the fade shows it).

## Review Focus

1. On the default 1060 × 640 window the centred panel must fit between the title bar and the bottom edge and every line must be reachable (scroll) (Tasks 3, 4).
2. `?` typed in the bookmark rename field is a character, never a command (Task 5).
3. Opening a video, or returning to the home screen after a file error, while the help is open closes it (no stale layout) (Task 4).
4. `Esc` closes the help before it does anything else (leaves full screen, closes the bookmark list, …) and, in the centred layout, never leaks through (Task 5).
5. The centred (modal) layout must swallow keys and mouse clicks: `Space` must not pause the video behind the dim, and a click on the dim must not reach the video (Tasks 3, 5).

---

### Task 1: The help content and the drift guard

**Files:** Create `ui/help_content.py`, `tests/test_help_content.py`.

**Interfaces — Produces:**
- `KEY_GROUPS: list[tuple[str, list[tuple[tuple[str, ...], str]]]]` — `(group title, [(chips, description)])`; `chips` is the tuple of key labels shown as separate chips.
- `MOUSE: list[tuple[str, str]]` — `(gesture, description)`; `TIPS: list[str]`; `ALL_CHIPS: set[str]` — every chip label in `KEY_GROUPS`.
- Strings exactly as in the spec's "Content" section (groups 재생, 소리 · 자막, 북마크, 화면 · 파일; the chips: `Space` · `[` `]` · `\` `Backspace` · `←` `→` · `,` `.` · `PageUp` `PageDown` · `↑` `↓` · `M` · `C` · `Z` `X` · `Ctrl+Z` · `B` · `Shift+B` · `Alt+←` `→` · `F` `Enter` · `P` · `I` · `Ctrl+O` · `Ctrl+S` · `?` · `Esc`).

- [ ] **Step 1: failing tests** in `tests/test_help_content.py`: `test_every_group_has_rows_and_no_chip_repeats_inside_a_group` (non-empty, each row has ≥ 1 chip, no empty text, no repeated chip inside one group); `test_the_mouse_lines_and_tips_are_not_empty` (6 mouse lines, 3 tips); and the guard `test_every_key_the_router_handles_is_in_the_help`:

```python
KEY_TOKENS = {   # Qt key constant used by KeyRouter -> the chip that shows it in the help
    "Key_Space": "Space", "Key_BracketLeft": "[", "Key_BracketRight": "]", "Key_Backslash": "\\", "Key_Backspace": "Backspace",
    "Key_Left": "←", "Key_Right": "→", "Key_Comma": ",", "Key_Period": ".", "Key_Less": "PageUp", "Key_Greater": "PageDown",
    "Key_PageUp": "PageUp", "Key_PageDown": "PageDown", "Key_Up": "↑", "Key_Down": "↓", "Key_M": "M", "Key_C": "C",
    "Key_Z": "Z", "Key_X": "X", "Key_B": "B", "Key_F": "F", "Key_Return": "Enter", "Key_P": "P", "Key_I": "I",
    "Key_O": "Ctrl+O", "Key_S": "Ctrl+S", "Key_Escape": "Esc", "Key_Question": "?", "Key_Slash": "?",
}

def test_every_key_the_router_handles_is_in_the_help():
    source = (ROOT / "ui" / "key_bindings.py").read_text(encoding="utf-8")
    used = set(re.findall(r"Qt\.(Key_\w+)", source))
    assert used <= set(KEY_TOKENS), f"a key the router uses has no help line: {sorted(used - set(KEY_TOKENS))}"
    assert {KEY_TOKENS[k] for k in used} <= ALL_CHIPS
```
  and `test_the_extra_chips_of_the_help_exist` (`Ctrl+Z`, `Shift+B`, `Alt+←` are in `ALL_CHIPS`).
- [ ] **Step 2:** run the file. Expected: FAIL (module missing). **Step 3:** write `ui/help_content.py` (data only, no Qt imports; `ALL_CHIPS` computed from `KEY_GROUPS`). **Step 4:** run. Expected: PASS. Mutation: delete the `Ctrl+O` row → the guard fails.
- [ ] **Step 5:** commit `feat: the help's content and a test that keeps it in step with the keys`.

### Task 2: The title-bar button and the divider that stays

**Files:** Modify `ui/icons.py` (a `help` icon), `ui/title_bar.py`, `tests/test_update_button.py` (one test); Create `tests/test_help_button.py`.

**Interfaces — Produces:** `GlassTitleBar.btn_help` (`GlassButton` flat, 28, `icon_px=14`, radius 8, tooltip `단축키 도움말 (?)`), `GlassTitleBar.help_clicked = Signal()`; `btn_help` is in `_buttons()`; `set_update_visible(visible)` now toggles **only** `btn_update` (`sep_update` stays visible).

- [ ] **Step 1: failing tests** in `tests/test_help_button.py`: `test_the_help_button_sits_after_the_update_button_and_before_the_divider` (layout order `btn_pip`, `btn_update`, `btn_help`, `sep_update`, `btn_min`), `test_it_has_a_tooltip_and_a_28_px_square_and_is_in_the_faded_set`, `test_clicking_it_emits_help_clicked`, `test_the_help_button_and_the_divider_stay_while_a_video_is_open` (call `set_update_visible(False)`: `btn_update` hidden, `btn_help` and `sep_update` shown; again with True). In `tests/test_update_button.py` change `test_it_shows_on_the_home_screen_and_hides_while_a_video_is_open` so that it asserts only `btn_update` hides and shows (the divider assertions go: it now stays; say so in the commit).
- [ ] **Step 2:** run `tests/test_help_button.py`. Expected: FAIL (no `btn_help`). **Step 3:** add the SVG (circle with a question mark, stroke 2, like the mock's `help` icon) to `SVG_ICONS`, create `btn_help` after `btn_update`, signal, `_buttons()`, `set_update_visible`.
- [ ] **Step 4:** run `tests/test_help_button.py tests/test_update_button.py tests/test_split_wiring.py`. Expected: PASS. Mutation: make `set_update_visible` hide the divider again → `test_the_help_button_and_the_divider_stay…` fails.
- [ ] **Step 5:** commit `feat: a help button on the title bar; the divider stays while a video is open`.

### Task 3: The panel

**Files:** Create `ui/help_panel.py`, `tests/test_help_panel.py`.

**Interfaces — Produces:** `class HelpPanel(QFrame)`: `CENTERED = "centered"`, `DRAWER = "drawer"`; signal `close_requested = Signal()` (a click on the dim); `show_as(kind: str, area: QRect) -> None` (builds the body for that kind, sizes and places the panel inside `area` per the Global Constraints, shows the dim for `CENTERED`, raises both); `hide_help() -> None`; `kind -> str`; `is_open() -> bool`; `scroll_area -> QScrollArea`; `fade_top() -> bool` / `fade_bottom() -> bool` (more content above / below the visible part). The body is two columns for `CENTERED` (left: 재생, 소리 · 자막, 북마크; right: 화면 · 파일, 마우스, 팁) and one column for `DRAWER`; a fixed header (`단축키와 사용법`, and `Esc 로 닫기` at the right) above the scroll area; a soft fade painted over the scroll area's top / bottom edge while `fade_*()` is true. The dim (`QWidget` child of the same parent, `QColor(0,0,0,215)`) swallows press / release / double-click / wheel like `settings_panel._Dim` and emits `close_requested` on a press.

- [ ] **Step 1: failing tests** in `tests/test_help_panel.py` (a parent `QWidget` shown at the sizes below): `test_the_centred_panel_is_centred_and_sized_to_the_area` (area 1060×640 → 900×548, centred; area 1920×1080 → 900×640); `test_the_drawer_is_420_wide_at_the_right_and_inside_the_area_even_at_640x380_and_480x270`; `test_the_body_follows_the_data` (the number of key chips found in the body equals the chips in `KEY_GROUPS`; 6 mouse rows; 3 tips; the same for both kinds); `test_the_drawer_scrolls_and_the_fade_cues_follow_the_scroll_position` (small area: scroll bar maximum > 0, `fade_top()` False and `fade_bottom()` True at the start, the reverse at the end, in between both True); `test_the_default_window_centred_panel_reaches_every_line` (area 1060×640: scrolling to the end shows the last tip — `scroll_area.verticalScrollBar().value() == maximum()` and the last tip label's bottom is inside the viewport); `test_the_body_is_almost_opaque` (render the panel over a widget filled with pure red: at a text-free point inside the panel the red channel is < 30); `test_the_dim_covers_the_area_swallows_the_mouse_and_a_press_asks_to_close` (a press on the dim emits `close_requested` once; the dim is under the panel; a release / double-click / wheel on it does not reach a widget below — use a child counter widget); `test_hide_help_hides_the_panel_and_the_dim`.
- [ ] **Step 2:** run the file. Expected: FAIL (module missing). **Step 3:** implement; approach: a `QScrollArea` holding a body `QWidget` rebuilt in `show_as` when `kind` changes (chips as `QLabel`s with the style above, rows as `QHBoxLayout`s with a fixed chip column width: 190 px for 재생 / 소리 · 자막 / 북마크, 150 px for 화면 · 파일, 110 px for the mouse rows, 150 px in the drawer); thin scroll bar styled like `bookmark_panel.SCROLL_QSS`.
- [ ] **Step 4:** run. Expected: PASS. Mutations: lower the body alpha to 120 → the opacity test fails; remove the dim's `mousePressEvent` → the dim test fails.
- [ ] **Step 5:** commit `feat: the help panel (centred and drawer layouts)`.

### Task 4: The flow and the window's wiring

**Files:** Create `ui/help_flow.py`, `tests/test_help_flow.py`; Modify `ui/main_window.py`, `docs/superpowers/specs/2026-10-26-help-panel-design.md` (the layout rule: see "Rulings").

**Interfaces — Produces:** `class HelpFlow(QObject)`: `toggle()`, `open()`, `close()`, `is_open() -> bool`, `is_modal() -> bool` (open and `CENTERED`), `layout_kind() -> str` (`CENTERED` when `window._current_file is None` and the video area `window.viewport.geometry()` is at least 720×460, else `DRAWER`), `relayout()` (re-place when open), `raise_panel()`. The panel (private attribute `_panel`, `None` until the first `open()`) is created on the first `open()` as a child of `window.central_widget` and kept; its `close_requested` closes the help. `MainWindow.help = HelpFlow(self)`; `title_bar.help_clicked` → `help.toggle`; `load_media_file` and `_show_file_problem` call `help.close()`; `_reposition_floating_widgets` calls `help.relayout()` and, with the other floating widgets, `help.raise_panel()` when open.

- [ ] **Step 1: failing tests** in `tests/test_help_flow.py` (the `window` fixture; `sample_video`, `pump` for the video cases): `test_nothing_is_created_before_the_first_open` (`window.help._panel is None`); `test_toggle_opens_and_closes` ; `test_the_home_screen_gets_the_centred_layout_even_in_the_default_window` (default 1060×640); `test_a_loaded_video_gets_the_drawer_and_keeps_playing` (open with a video: kind `drawer`, `engine` not paused by it — assert `window.engine.is_playing()` is unchanged from before); `test_a_small_window_gets_the_drawer_on_the_home_screen` (resize to 640×380); `test_opening_a_video_closes_the_help_and_so_does_a_file_problem` (open, `load_media_file(sample_video)` → closed; open again, `_show_file_problem(path, "gone")` → closed); `test_a_resize_keeps_it_open_and_inside_the_window`; `test_the_title_bar_button_toggles_it_once` (emit `title_bar.help_clicked`; count calls of `window.help.toggle` wrapped by a counter: 1).
- [ ] **Step 2:** run. Expected: FAIL (no `window.help`). **Step 3:** implement the unit and the hooks. **Step 4:** run these plus `tests/test_split_wiring.py tests/test_window.py`. Expected: PASS. Mutation: drop the `help.close()` in `load_media_file` → the closing test fails.
- [ ] **Step 5:** commit `feat: HelpFlow and its wiring in the window`.

### Task 5: The keys

**Files:** Modify `ui/key_bindings.py`; Create `tests/test_help_keys.py`.

**Interfaces — Consumes:** `window.help.toggle()`, `.is_open()`, `.is_modal()`, `.close()`. **Produces:** in `KeyRouter.handle`: (1) right after the settings-panel block: if `window.help.is_modal()`: `Esc` or `?` → `help.close()`; every other key is swallowed (accept, return True); (2) after the bookmark rename guard: `?` (`Qt.Key_Question`, or `Qt.Key_Slash` with Shift; not with Ctrl / Alt) → `window.help.toggle()`, accept, return True; (3) in the `Esc` chain, `window.help.is_open()` → `window.help.close()` as the **first** branch.

- [ ] **Step 1: failing tests** in `tests/test_help_keys.py`: `test_question_mark_toggles_the_help` (a real `QTest.keyClick(window, Qt.Key_Question, Qt.ShiftModifier)` opens it, again closes it; also `Key_Slash` with Shift); `test_a_question_mark_typed_in_the_rename_field_is_a_character` (open the bookmark panel on a loaded video, start a rename, send `?` to the field: the help stays closed and the field holds `?`; then a `?` sent through `window.keyPressEvent` while editing does nothing — the guard still comes first); `test_escape_closes_the_help_before_leaving_full_screen` (loaded video, full screen on, help open: first `Esc` closes only the help, the second leaves full screen); `test_the_centred_help_swallows_other_keys_and_the_dim_swallows_clicks` (home: help open; counters on `window.toggle_mute`, `window.engine.toggle_play`, `window.toggle_fullscreen`; `M`, `Space`, `F` → counters 0; `Esc` closes it); `test_in_the_drawer_the_shortcuts_still_work` (loaded video: help open; `M` → `toggle_mute` called once; the help stays open); `test_the_router_checks_the_help_after_the_settings_panel` (settings panel open and help open → `Esc` closes the settings panel, as before).
- [ ] **Step 2:** run. Expected: FAIL. **Step 3:** implement per the Interfaces block. **Step 4:** run these plus `tests/test_window.py tests/test_bookmark_window.py tests/test_split_wiring.py tests/test_help_content.py`. Expected: PASS (the drift guard now sees `Key_Question` and `Key_Slash`, both mapped). Mutations: move the `?` check before the rename guard → the rename-field test fails; remove the modal swallow → the swallow test fails.
- [ ] **Step 5:** commit `feat: ? opens the help; Esc closes it first; the centred help is modal`.

### Task 6: The right-click menu entry

**Files:** Modify `ui/context_menu.py`, `tests/test_split_wiring.py` (the pinned menu list).

- [ ] **Step 1:** in `test_the_right_click_menu_has_these_entries` add `"단축키 (?)"` between the separator after `전체화면 (F)` and `설정...` (so the tail reads `"전체화면 (F)", "---", "단축키 (?)", "설정...", f"Pane 정보 (v{APP_VERSION})", "Pane 종료 (Alt+F4)"`). Add `test_the_menu_entry_toggles_the_help_once` (capture the menu as that test does, trigger the action, assert `window.help.is_open()`, trigger again → closed). **Step 2:** run. Expected: both FAIL. **Step 3:** add `act_help = menu.addAction("단축키 (?)")` connected to `window.help.toggle` right before `설정...`. **Step 4:** run `tests/test_split_wiring.py`. Expected: PASS. Mutation: connect it twice → the once test fails.
- [ ] **Step 5:** commit `feat: 단축키 (?) in the right-click menu` (the commit message says the pinned menu list was edited on purpose).

### Task 7: Docs

**Files:** Modify `README.md`, `release/README_RELEASE.txt`, `CHANGELOG.md`, `PROGRESS.md`, `tests/test_release.py`.

- [ ] **Step 1:** in `tests/test_release.py::test_readme_documents_every_key_binding_in_the_code` add `"Key_Question"` to the code check and require `` `?` `` in the README table and `?` in the release notes' key list. Run. Expected: FAIL.
- [ ] **Step 2:** README table row ``| `?` | 단축키 도움말 (우클릭 메뉴 · 제목 줄의 ? 버튼으로도 열어요) |``; release notes key row `?  단축키 도움말` and one feature line; CHANGELOG `## Unreleased` bullet (`New: a shortcut help panel…`); PROGRESS bullet with the decisions (centred panel on the home screen, drawer while a video is open, playback untouched, `ui/help_*.py`, the drift guard, the layout-threshold ruling). Run `tests/test_release.py`. Expected: PASS.
- [ ] **Step 3:** commit `docs: the help panel`.

### Task 8: Wrap-up

- [ ] **Step 1:** `./.venv/Scripts/python.exe -m pyflakes ui` (Expected: the six old warnings, nothing new); the full suite (Expected: all pass; rerun once on exit 139/132); `wc -l ui/main_window.py` (Expected: not more than about 20 lines above 1,023).
- [ ] **Step 2 (ask first; it opens a real window):** launch from source with isolated settings (`scratch/run_try_update.py`-style, a fresh `APP_NAME`) and look at the home screen (centred), a playing video (drawer, video keeps playing, shortcuts work while it is open), `?`, the menu entry, the button, the scroll fade; delete the temporary registry keys afterwards.
- [ ] **Step 3 (ask first; it moves the mouse):** `pytest tests/test_input_e2e.py --run-e2e`. Expected: 9 passed.
- [ ] **Step 4:** `review-package` from the merge base, one fresh review on the most capable model with the Review Focus above and the ledger's rulings; fix Critical / Important with a failing test first; list the rest as deferred. Then ask whether to merge and push; no release of its own (it goes out with the next release).
