# Changelog

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
