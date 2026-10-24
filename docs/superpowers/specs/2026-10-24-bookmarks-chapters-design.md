# Bookmarks and chapters on the seek bar — design

Date: 2026-10-24. Status: written, waiting for the owner's review. Roadmap source: PROGRESS.md §8-4 ("북마크",
"챕터 표시"), the third piece of the "탐색" group (thumbnails and the time under the pointer shipped in 1.3).
Mockups: the design canvas "Pane 북마크·챕터 시안" (bookmark pins, chapter variants, list panel).

## Intent (agreed in conversation)

- **Goal:** mark places of a (lecture) video to look at again later, find them again at a glance on the seek bar, and see
  where the chapters of a file are.
- **Constraints (PROGRESS.md §8-0):** nothing costs anything while unused (a video without bookmarks or chapters is drawn
  and behaves exactly as today); minimal look; no heavy dependency.
- **Success:** one key press marks the current place without a pause or a dialog; the marks show on the bar; one click or
  one key goes back to them; chapters show quietly and can be switched off.

## What the owner chose

- **Add:** the `B` key (and the new button) saves the current position **at once**; the pill says `북마크 0:34:12`; the name
  is the time by default and can be renamed later in the list. No dialog, no pause.
- **Look of a bookmark: mockup "C".** A **vertical pin** across the bar: amber `#FFC857`, 4 px wide, 18 px tall, rounded;
  while the pointer is within 6 px of it, 5 × 24 px with a thin white outline (as in the mockup).
- **Look of chapters: "C-2" + the name in the pill.** The bar is **cut by a thin gap** at each chapter start (2 px, 3 px
  while the bar is hovered and thicker); nothing is added to the bar. The gap is not painted at all (the video shows
  through). Over the bar the hover pill names the chapter: `<title>  <time>` (no title: `챕터 N  <time>`).
- **Navigate:** click a pin = go to it; the list panel; `Alt+←` / `Alt+→` = previous / next bookmark.
- **List panel:** opened by a **new control button** (after the subtitle button) or `Shift+B`; mockup "북마크 목록 패널".
- **Chapters can be switched off:** Settings > 일반 > `재생바에 챕터 표시` (default on). Off = no gaps **and** no chapter
  name in the pill. Bookmarks are not affected by it.

## Behaviour

### Bookmarks
- **Store:** `AppSettings` keeps, like the resume positions, a JSON dict `bookmarks`: video path → list of
  `{"t": seconds (2 decimals), "name": str}` sorted by `t`; at most **100 per video** and **200 videos** (the least
  recently changed video goes first). Invalid entries are ignored on read (a non-number `t`, a non-string name, `t < 0`).
  A bookmark with `name == ""` is shown by its time.
- **Add (`B`, button's "지금 위치" in the panel):** only while a video with a known length is loaded. Position = the
  current playback time (`time-pos`). A bookmark within **1.0 s** of an existing one is not added: the pill says
  `이미 북마크가 있어요 0:34:12`. Else it is saved and the pill says `북마크 0:34:12`.
- **Jump (`Alt+←` / `Alt+→`):** previous = the last bookmark with `t < now − 1.0`; next = the first with `t > now + 0.5`;
  none: the pill says `이전 북마크가 없어요` / `다음 북마크가 없어요`. The jump is an exact seek and shows the pill
  `북마크 0:34:12`. `Alt+←/→` never reaches the normal 5 s seek.
- **Click a pin:** a left press within 6 px of a pin seeks exactly to it (and does not start the drag of the handle at the
  nearby place); anywhere else the bar behaves as today.
- **Hover a pin:** the pill reads `● <name or time>  <time>` with the amber dot.
- **Rename / delete:** in the panel only (pencil: inline edit with Enter = save, Esc = cancel, an empty name = back to the
  time; ✕ = delete at once). Deleting the last one leaves the empty state `아직 북마크가 없어요 · B 로 지금 위치를 저장해요`.
- **Opening another video** shows that video's bookmarks; they are read once when a video is opened.

### Chapters
- Read once per video when mpv reports the file loaded (`chapter-list`: `{"title", "time"}` items): chapters with
  `time <= 0`, beyond the length, or closer than 1 s to the previous one are dropped. Fewer than 2 chapters = no chapters.
- **Gaps:** one at each chapter start except the first. A gap whose neighbours are closer than **10 px** is skipped, and
  with more than **60** gaps none are drawn (the pill still names the chapter).
- Switching `재생바 챕터 표시` off clears the gaps and the names at once.

### The pill
`SeekTimeTip` gets an optional amber dot and a name; priority when several apply: bookmark under the pointer > chapter >
plain time. The thumbnail picture above it is unchanged.

## Components

- `core/bookmarks.py` (no widgets): `normalize(list)`, `add(list, t) -> (list, added: bool, existing_t)`,
  `previous(list, now)`, `next(list, now)`, `pin_near(list, x_of_t, x, radius)`, `chapters_from_mpv(raw, duration)`.
- `core/settings.py`: `get_bookmarks(path)`, `save_bookmarks(path, items)`, `get/set_chapters_visible`.
- `core/player_engine.py`: `chapters() -> list[(time, title)]` read from `chapter-list`.
- `ui/timeline_slider.py` / `ui/glass_slider.py`: `set_marks(bookmark_times, chapter_times)`; the groove and the fill are
  drawn through a clip that leaves out the gaps; pins drawn after the fill and before the handle; `pin_pressed(float)`
  signal for a press on a pin (the slider does the hit test with the same x mapping as the hover).
- `ui/overlay.py` `SeekTimeTip.show_at(..., dot=None)`.
- `ui/bookmark_panel.py` (`BookmarkPanel`): the list, inline rename, delete, "지금 위치"; modelled on `TrackPopup`
  (glass card above the bar, closes on a click elsewhere or Esc).
- `ui/glass_controller.py`: button `bookmarks` (`BUTTON_METADATA`, icon `bookmark`, tooltip `북마크 (Shift+B)`) in the
  default layout after `subtitle`; **saved layouts** get it once, after `subtitle`, through a small versioned migration
  (`LAYOUT_ADDITIONS`, marker `layout_additions_version`), without resetting the layout the owner built.
- `ui/main_window.py`: keys, wiring, the pill texts, the panel, applying the chapter switch.
- `ui/settings_panel.py`: row `재생바에 챕터 표시` in the 일반 tab (signal `chapters_changed`).

## Cost

- No bookmarks and no chapters: nothing is drawn extra, nothing is read beyond one settings lookup and one property read
  when a video opens. The panel is created on first use.
- Drawing: at most 100 pins and 60 gaps; no per-frame work beyond the existing repaint of the bar.

## Errors and edge cases

| Case | Behaviour |
|---|---|
| No video, or length unknown (stream) | `B` / `Alt+←/→` show nothing and do nothing; no pins |
| Bookmark beyond the video's length (file changed) | not drawn, still listed (dimmed); a jump to it is skipped |
| Settings value broken | ignored per item; the app never stops |
| Pins closer than 8 px | all drawn; the one nearest the pointer wins the hover and the click |
| A pin at the very start or end of the bar | drawn inside the bar's margins |
| Window resized while the panel is open | the panel closes (as the track popup does) |
| Rename field open and a key pressed | the keys go to the field, not to the player |
| Chapters off | no gaps, no chapter text; bookmarks unaffected |

## Tests (real objects; mpv with `tests/assets/sample.mp4` where a video is needed)

- `core/bookmarks`: `add` (new, duplicate within 1 s, sorted, the 100 limit), `previous` / `next` with the margins,
  `pin_near`, `chapters_from_mpv` (drops `time <= 0`, beyond the length, too close; fewer than 2 = none).
- Settings: save / read, ordering, limits (100 per video, 200 videos), broken values, `chapters_visible` default on.
- Timeline: gaps are not painted (a real render: the pixel at a gap is transparent, a neighbour is the groove colour), the
  10 px and 60 limits, pins drawn, a press near a pin emits `pin_pressed` and does not move the handle, elsewhere as
  today (the existing `test_seekbar_hover` stays green).
- Pill: texts for time, bookmark, chapter, no-title chapter, the priority.
- Window: `B` adds and shows the pill, a second `B` does not duplicate, `Alt+←/→` jump and never seek 5 s, `Shift+B`
  opens the panel, the panel renames / deletes / jumps, opening another video swaps the pins, the chapter switch removes
  gaps and names, no-video cases are inert.
- Layout: the migration adds the button once after `subtitle` in a saved layout and leaves the rest as it was; the
  default layout contains it.
- Cost: with no bookmarks and no chapters the slider has no marks and paints identically (a pixel comparison with
  `set_marks([], [])`).

## Out of scope

Chapter list or chapter jump keys, bookmark export / import, notes longer than a name, colours or categories of
bookmarks, bookmarks for streams, a thumbnail inside the panel.

## Open points for the owner's review

1. Pin size (4 × 18 px; 5 × 24 px near the pointer): fine, or slimmer?
2. `Alt+←/→` and `Shift+B` as keys: any clash with something you use?
3. The pill priority (bookmark > chapter > time): fine?
