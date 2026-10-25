# Splitting `main_window.py` — design

Date: 2026-10-25. Status: implemented on `refactor/main-window-split` (see PROGRESS §1; the result is 1,023 lines in `main_window.py`, not the hoped-for 900).

## Why

`ui/main_window.py` has grown to 1,612 lines: one `MainWindow` with about 130 methods, mixing the window itself (opening a
video, playback state, full screen, PIP, laying the overlays out) with five features that were added one at a time (the
right-click menu, the keyboard, the seek-bar pill and thumbnails, bookmarks and chapters, the update notice). Every new
feature makes the file bigger and the next one harder to place. Nothing is broken; this is about keeping the next
features cheap.

## Goal and non-goals

**Goal:** the six pieces below live in their own modules, each a small object with one job, and `main_window.py` shrinks
to about 900 lines (the window itself). **Behaviour does not change.** The whole existing suite (911 tests at the time of
writing) passes unchanged after every step.

**Not in scope:** how the overlays are laid out (`_reposition_floating_widgets`), opening a video, playback state,
full screen / PIP, the About box and diagnostics (they stay on the window), the controller (`glass_controller.py`), any
visible change, any new feature, a release of its own (it ships with the next feature release).

## The approach: a hybrid (chosen over mixins and over full composition)

- *Mixins* would only cut the file into pieces; the state would stay mixed in one object. Little gained.
- *Full composition* (everything a controller object) is the cleanest on paper, but playback, full screen, PIP and layout
  are tangled with each other and with all the overlays: doing them at once is where a regression would hide.
- **Hybrid:** move only the clusters that have a clear edge into their own objects; leave the tangled core on
  `MainWindow`. What moves keeps a **thin forwarding name on `MainWindow`** (a property or a one-line method) so that
  callers and tests that use the old name keep working. Tests are changed only when a name truly goes away, and each such
  change is written down with its reason.

## The units (in the order they are moved: lowest risk first)

Each unit is a plain Python object (or a `QObject` child of the window when it owns timers or connects signals) that is
given the window and uses its public overlays (`window.engine`, `window.controller`, `window.osd`, …) and a few private
values (`_current_file`, `_duration`, `_time_pos`). It never reaches into another unit's private state.

1. **`ui/viewport.py` — `VideoViewport`.** A pure move of the class (about 100 lines). `main_window.py` imports it
   (and keeps the name importable).
2. **`ui/context_menu.py` — `show_context_menu(window, global_pos)`.** The menu builder (about 110 lines) as a function;
   `MainWindow.show_context_menu` stays as a one-line call. Before it moves, a characterization test pins the menu's
   entries (their texts and order), because the suite only touches it lightly.
3. **`ui/key_bindings.py` — `KeyRouter(window)` with `handle(event) -> bool`.** `keyPressEvent` (about 160 lines) becomes
   `if not self.keys.handle(event): super().keyPressEvent(event)`. The order of the checks stays exactly as it is (the
   settings panel first, the bookmark keys before the plain arrows, and so on): the order is the behaviour. The router
   calls window methods by their public names.
4. **`ui/seek_tips.py` — `SeekTips(window)`.** Owns `seek_tip`, `thumbnail_tip`, `thumbnail_provider`, the pointer spot,
   the "only when the pointer rests" timer, `thumbnails_on` / `thumbnails_on_stop` and the handlers
   (`show`, `hide`, `request`, `on_ready`, the two switch handlers, `area_changed(viewport_rect)` for what
   `_reposition_floating_widgets` does today). `MainWindow` forwards `seek_tip`, `thumbnail_tip`, `thumbnail_provider`,
   `thumbnails_on`, `thumbnails_on_stop`, `_hide_seek_tips`; `_on_close` calls `tips.shutdown()`.
5. **`ui/bookmark_flow.py` — `BookmarkFlow(window)`.** Owns `bookmarks`, `chapters`, `chapters_on` and the panel, and the
   actions (`add`, `jump`, `rename`, `delete`, `toggle_panel`, `refresh`, `load_chapters`, `seek_to_mark`, the chapter
   switch handler). It also decides what the hover pill says (`pill_for(seconds, x) -> (text, dot, detail)`), which moves
   out of `SeekTips` in the same step (a small edit there). `MainWindow` forwards `bookmarks`, `chapters`, `chapters_on`,
   `bookmark_panel`, `add_bookmark`, `jump_bookmark`, `toggle_bookmark_panel`, `rename_bookmark`, `delete_bookmark`,
   `_load_chapters`, `_on_chapters_changed`, `_refresh_marks`, `_seek_to_mark`. `_time_pos` stays on the window (the
   playback position is shared by several things).
6. **`ui/update_flow.py` — `UpdateFlow(window)`.** Owns `update_card`, `update_checker`, the install-wait timer, the
   installer path, the pending offer, the home-screen check state and the logic (`ask`, the About-box check, the home
   button check, offered / progress / installer ready / failed, start, dismiss, whether the card is blocked, show or hide
   and place it). `MainWindow` forwards `update_card`, `update_checker`, `_on_about_check`, `_ask_for_update`,
   `_check_update_from_home`, `_refresh_update_card`, `_start_update`, `_dismiss_update`; `_on_close` calls
   `updates.request_stop()` (what it does now with the checker, in the same order: stop, wait, trace).

Attribute names on the window for the units: `keys`, `tips`, `marks`, `updates`.

## How each step is done

1. Make sure the cluster is covered by tests that would fail if it broke (add a characterization test where the suite is
   thin: the context menu).
2. Move the code **as it is**: cut and paste, then change only what the move forces (`self.` → `self.window.` for the
   window's things, imports). No logic edit, no tidying in the same commit.
3. Leave the forwarding names; run `python -m pyflakes` on the touched files (it is in the venv) to catch an undefined
   name or an unused import, then the whole suite. Fix by finishing the move, never by editing a test to match.
4. One commit per step (`refactor: move … out of main_window`). A step that cannot be made to pass is reverted; the earlier
   steps stay.

## Things that can go wrong, and the guard for each

- **A signal connected to a bound method of the window** (`engine.x.connect(self._on_x)`) must connect to the unit's
  method after the move, not the old forwarder only: where the forwarder would hide a slow or recursive path, connect
  directly. Checked by the existing behaviour tests.
- **Lifetime.** A unit that owns a `QTimer` or connects signals is a `QObject` with the window as parent, so it dies
  with it. Plain units are plain attributes of the window.
- **Closing.** `_on_close` has a fixed order (update check stopped, thumbnails closed, video surface, mpv; each traced
  in `pane.log`). The order and the trace lines stay exactly; only the calls inside change (`tips.shutdown()`,
  `updates.request_stop()` + `wait_for_done`). `test_exit_trace.py` and the close tests guard it.
- **Construction order.** Units are created where their pieces are created today (`_init_floating_widgets`) and
  `_reposition_floating_widgets` keeps its `hasattr(self, "controller")` guard, because it can run before they exist.
- **Tests that patch a name** (`monkeypatch.setattr(window.update_checker, "check", …)`, `window.osd.show_message`) keep
  working because the forwarders return the very same objects.
- **Circular imports.** Units import from `core` and from other `ui` modules, never from `main_window`.

## Done when

- `main_window.py` is about 900 lines or fewer, and each unit is under 300.
- The suite passes at every step (and at the end: the same number of tests as before, plus the characterization test).
- `python -m pyflakes ui/` reports nothing new.
- Opening a video, the keys, the right-click menu, the hover pill, bookmarks and chapters, the update card and the home
  button all behave as before (the suite covers them; a short look at the real window at the end is offered, not assumed).
