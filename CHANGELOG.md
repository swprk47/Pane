# Changelog

## Unreleased
- New control-layout settings: edit the bar the way it looks, drag buttons between the left / centre / right zones, hide them (✕ or drag to the "hidden" row) and bring hidden ones back (this also fixes hidden buttons, such as the frame-step ones, having no way back)
- Fix: applying a new control layout left only the centre buttons (the left / right zones collapsed to 0 px)
- New start screen: big logo, a glass dock with "open" and the last video to go on with (progress line, time, play button), and a lit frame while a file is dragged over the window
- Fix: the pause symbol was showing over the empty window on start-up
- Continuous play: when a video ends, the next video in the same folder (natural file-name order) plays after a 5 s card (a ring around the next-video button counts down; hovering the card holds it) with Cancel / Play now; Shift+, / Shift+. (or PageUp / PageDown) and new controller buttons move between videos; the right-click menu can turn auto-play off
- The frame-step buttons are no longer in the default control layout (still on `,` / `.`, and available in the layout settings); the previous / next video buttons are bigger. Saved layouts are reset once
- Smaller speed panel: presets in a vertical list, pin / current speed / slider in one row at the bottom; click the speed to type one in
- Pressing play on a finished video watches it again
- New glass look for all controls with smooth transitions, floating title bar that hides with the controls, dark glass pause / play symbol, new app icon
- Fixes: controls never auto-hid until the first pause / resume; controls stayed hidden after a pause while hidden; clicking the video reacts at once

## 1.0.0 - 2026-10-04 (first release, private sharing)
- Video player built on libmpv, rendered through the OpenGL render API into a Qt widget
- 0.05x precision speed with up to 6 pinned presets, per-chip delete, fine slider
- Overlay controls on the video (YouTube style), centered transport, vertical volume popup
- Resume position, recent files, PIP (always on top), subtitles auto-load, frame step, screenshots
- Media info panel (I): codec, GPU/CPU decoding, resolution, fps, dropped frames
- Windows installer (Inno Setup): per-user install, optional desktop shortcut, 'Open with' registration for video files, in-place upgrade, clean uninstall
- Serenity-blue glass UI, Pane logo, SVG icons
- Fixes found while preparing the release: PIP flicker, render blocking the UI thread, resume
  position being ignored, title bar double-click, screenshots on localized desktops
- Known limits: 4K 60 fps fullscreen drops ~5-8 % frames; no subtitle sync, audio-track choice or playlist
