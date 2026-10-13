# Seek-bar thumbnails — design

Date: 2026-10-13. Status: written, waiting for the owner's review. Roadmap source: PROGRESS.md §8-4 ("재생바 미리보기",
step 2: thumbnails; step 1, the time under the pointer, shipped in 1.3).

## Intent (agreed in conversation)

- **Goal:** find a place in a long video, above all a lecture recording, quickly: sweep the seek bar and see the picture
  that belongs to that time.
- **Constraints (PROGRESS.md §8-0, the lightness rule):** the cost when the feature is not used is zero; the cost while
  it is used is measured and written into PROGRESS.md; 4K 60 fps playback must not be harmed without a switch that
  fixes it; no heavy dependency.
- **Success:** hovering the seek bar shows a small picture above the existing time pill; playback does not stutter on
  the owner's normal videos; with the feature off Pane behaves exactly as 1.3.0.

## What the owner chose

- **Look: mockup "C", gap narrowed.** A 160×90 picture (not a card around it) and, directly below it, the time pill
  that exists today (`SeekTimeTip`), unchanged. The gap between picture and pill is **6 px**; the picture has a 1 px
  white 40 % border and 10 px corners like the pill's glass edge. The picture is centred on the same x as the pill and
  is kept inside the video area like the pill is.
- **Default: the picture follows the pointer** while it moves over the bar.
- **Two switches in Settings > 성능**, applied at once and saved like the existing ones:
  1. `재생바 썸네일` (default on).
  2. `마우스를 멈췄을 때만 표시` (default off; dimmed while switch 1 is off). When on, the picture is not shown while
     the pointer moves; about 0.3 s after it stops the picture appears; moving again hides only the picture (the pill
     stays).
- Everything is chosen by the user; nothing switches itself by video size. (An automatic mode was considered and
  declined.)

## Components

### `core/thumbnails.py` — makes the pictures (no Qt widgets)

`ThumbnailProvider(QObject)`, one per main window.

- A **second mpv instance**, created on the first request after a video is loaded: `vo=null`, `ao=null`, `aid=no`,
  `sid=no`, `pause=yes`, `hr-seek=no` (nearest keyframe, fast), `hwdec=no` (keyframes only; avoids sharing the GPU
  decoder with the playing video), `idle=yes`, `keep-open=yes`, `input-default-bindings=no`.
  It loads the same file as the player (`loadfile`, paused).
- `request(path: str, seconds: float)`; the picture comes back through the signal `thumbnail_ready(path, bucket, QImage)`.
  Requests run on **one worker thread**; while one runs only the newest later request is kept ("latest wins"); older
  ones are dropped.
- A picture is taken with mpv's `screenshot-raw` after `seek <t> absolute+keyframes`; mpv scales it (`vf=scale`) to
  twice the logical box so it is sharp on 200 % displays; the widget scales it down.
- **Box and aspect ratio:** logical height 90 px, width = height × the video's aspect ratio, clamped to 90..160 px
  (a tall video gets a narrow picture, a very wide one is cut to 160 px wide and letter-boxed, never stretched).
- **Cache:** per file, key = `int(seconds / 2)` (a 2 s bucket); at most 60 pictures, least recently used goes first.
  A hit is answered at once from the cache, without touching mpv.
- **Lifetime:** the instance is closed (`terminate`) after **10 s** without a request; the cache stays until the video
  changes. A new file, a closed file, or the window closing: pending requests are dropped, the cache is cleared and
  the instance is terminated.
- **No video track** (audio files) or unreadable file: `request` does nothing. Any error while making a picture is
  logged once (`[thumbnails] ...`) and the picture is simply not shown; no dialog.
- Switch 1 off: `request` returns at once and the instance is never created.

### `ui/overlay.py` — `ThumbnailTip` (draws one picture)

An overlay child of the central widget like `SeekTimeTip` (`_OverlayBase`), hidden until used. `show_at(image, x_center,
y_bottom, bounds)` puts the picture with its bottom edge `y_bottom`, centred on `x_center`, inside `bounds`;
`hide_tip()` hides it. It paints the image with rounded corners and the border; it keeps no history. Its size is the
image's logical size.

### `ui/main_window.py` — wiring

- `timeline.hover_moved(seconds, x)` already calls `_show_seek_tip`. After the pill is placed, the window asks the
  provider for the picture at `seconds`, and shows it with `ThumbnailTip.show_at` (bottom edge = the pill's top − 6 px).
  `hover_left`, controls hiding and window changes hide both (as the pill is hidden today).
- "Stop mode": a single-shot `QTimer` (300 ms) restarted on every `hover_moved`; the picture is requested and shown
  only when it fires; any movement hides the picture first.
- A loaded picture whose bucket no longer matches the pointer (the pointer moved on) is ignored.
- `controller` / `settings_panel`: two new rows with switches (`switch_thumbnails`, `switch_thumbnails_on_stop`),
  signals `thumbnails_changed(bool)` and `thumbnails_on_stop_changed(bool)` handled exactly like `hwdec_changed`.
- `core/settings.py`: `get/set_thumbnails_enabled` (default True), `get/set_thumbnails_on_stop` (default False).

## Cost and measurement (done before the feature is called finished)

1. **Not used:** with switch 1 off, or before the first hover, no second mpv exists (tested). Memory and CPU equal 1.3.0.
2. **While used,** measured on this PC with the 4K 60 fps video and a 1080p one, playing, sweeping the bar at about
   1 s per bar width: dropped frames with and without thumbnails (the same method as the seek indicator: PROGRESS.md
   §5), picture latency (median and worst), extra memory of the second mpv. Results go into PROGRESS.md.
3. **If the 4K 60 fps result is bad** (more than a handful of dropped frames in a sweep), the owner is asked whether
   switch 2 should become the default; the mechanism is already there. No automatic switching.

## Accuracy

Pictures come from the nearest keyframe (`hr-seek=no`): for a lecture recording the picture can be some seconds off the
time shown. Clicking the bar still seeks exactly (`seek_relative` / seek-bar exact seeks of 1.3). The settings text
does not mention this; if the owner finds the offset confusing the alternative is exact seeks (`hr-seek=yes`),
slower per picture, to be measured then.

## Errors and edge cases

| Case | Behaviour |
|---|---|
| Second mpv cannot start / `screenshot-raw` fails | log one line, no picture, pill as today, retry on the next video |
| Hover before the video is loaded or after it ended | nothing requested |
| New video opened while a request runs | the result is discarded (path/bucket mismatch), cache cleared |
| Window closed during a request | provider stops, instance terminated, no waiting for the worker beyond a short join |
| Duration unknown (streams) | no picture (bucket needs a duration) |
| Pointer at the very ends of the bar | clamped to 0 and to the last second |
| Display scale changes while open | next picture is made at the new scale; cached ones are scaled by the widget |

## Tests (real objects; the second mpv with `tests/assets/sample.mp4`)

- Provider: returns a non-blank picture of the right size for a time; the same 2 s bucket twice makes one mpv
  request; two quick requests answer only the newest; a file without video returns nothing; switch off creates no
  instance; the instance is closed after the idle time (time injected); a new file clears the cache; the aspect-ratio
  clamp for a tall and a wide size.
- `ThumbnailTip`: paints the image inside its rounded border (real render with `render(img, QPoint(), QRegion(),
  QWidget.RenderFlag(0))`), placed 6 px above the pill and kept inside bounds.
- Window: hovering shows pill and picture; leaving hides both; switch 1 off shows only the pill; stop mode shows the
  picture only after the timer; the two switches in the settings panel (second dimmed while first is off) save and
  apply at once; closing the window with a request running does not hang.
- Regression for the lightness rule: a test that no `mpv.MPV` is created by merely opening a video and hovering with
  switch 1 off.

## Out of scope (later, separate designs)

Bookmarks and chapter marks on the bar (the other items of the "탐색" group), drawing chapters in the picture,
thumbnails for the playlist or the start screen, a thumbnail strip, clicking the picture.

## Open points for the owner's review

1. Keyframe accuracy (above): acceptable, or exact pictures at some cost?
2. The idle time (10 s) and the stop delay (0.3 s) are first guesses; the measurement may change them.
