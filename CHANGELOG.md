# Changelog

## Unreleased
- Fix: after the window was closed the process could stay alive for up to 10 seconds (30 while an update was downloading) when the update check was waiting on a slow or silent network, which could leave a dead icon on the taskbar if the PC went to sleep just then. Closing now ends the process at once
- Closing the app leaves a few timed `[exit]` lines in `%LOCALAPPDATA%\Pane\pane.log`, so a slow or stuck exit can be traced
- New seek-bar thumbnails: hovering the seek bar shows a small picture of that moment just above the time. Settings > 성능 has two switches: `재생바 썸네일` (on by default) and `마우스를 멈췄을 때만 표시` (off by default; the picture appears only after the pointer rests, which keeps 4K 60 fps playback undisturbed). The picture is taken from the nearest keyframe, so it can be a few seconds off the time shown; clicking still seeks exactly. Nothing extra is created while the feature is off

## 1.3.0 - 2026-10-13
- New in-app update: a few seconds after start Pane checks (at most once a day, only the installed app) whether a newer version exists. A glass card appears at the bottom right while nothing plays; [업데이트] downloads the installer, checks its size and SHA-256, runs it silently, and Pane restarts as the new version. The X on the card stops announcing that version. The check can be switched off in Settings > 일반 > 새 버전 알림, and About > 업데이트 확인 asks at once. The update manifest is signed (Ed25519): a tampered or unsigned manifest or installer is rejected. A copy that was not installed by the setup (unzipped, built from source) is never updated
- Pane is now free software under the GNU GPL v3 or later; the source is at https://github.com/swprk47/Pane (the full license text and the sources of the bundled mpv / FFmpeg are listed in the installer)
- Settings panel got tabs (성능, 오디오, 일반); the diagnostics report can be copied from About; the libmpv build is checked for its license
- Time-seek indicator shows the jump in seconds with single and double arrows, relative seeks are frame exact, and the seek bar shows the time under the pointer
- A clear notice with a hint when a video cannot be opened (missing file, unsupported or damaged file, no access)
- Fix: with the audio filter switched off again the sound could stay silent; videos without an audio track no longer break the filter
- Fix: the grey strip next to the window while resizing is smaller (the acrylic effect was removed)
- Friends on 1.2.0 or older have no updater: install this version by hand once; later versions update from inside Pane

## 1.2.0 - 2026-10-10
- Audio and subtitle tracks: the subtitle button opens a panel with an Audio | Subtitles tab, each listing the tracks as "language · codec / channels" (embedded or external), a subtitle on/off switch, the sync value and "load an external subtitle file". Subtitle sync on `Z` / `X` (0.1 s), audio delay on `Shift+Z` / `Shift+X`, `Ctrl+Z` resets both; the sync starts at 0 for every video
- Windows' own window behaviour: `Win+arrow keys` snap and maximize the window, the window can be dragged to the screen edges, the edges can be dragged to resize it (with the usual resize cursors and minimum size), and the taskbar menu / `Alt+Space` work. The maximize button follows maximizing done by Windows
- New on-screen notices: a dark glass pill that grows out of the top edge of the window and folds back after a second. Value notices (speed, volume, mute, subtitle on/off, sync) now appear only for keyboard shortcuts, since a value changed with the mouse is already visible in its panel; fullscreen, PIP, seek, frame step and next / previous video no longer show one
- The control-layout settings open as a panel inside the player window instead of a second window, which removes the flicker when opening them. The speed and track panels sit just above the seek bar
- The speed range is now 0.25x - 4.0x everywhere (keys, panel slider and typed input; the keys used to reach 4.0x while the panel stopped at 3.0x)
- Fix: after clicking a slider the arrow keys (volume, seek) went to the slider instead of the player
- Fix: the volume notice could show more than 100 % (the sound itself never did)
- Fix: pressing the X button left the window frozen on screen for ~0.4 s while a video played; it now disappears at once
- Known limits: resizing the window while a 4K 60 fps video plays drops frames; entering fullscreen still stalls for ~0.2 s

## 1.1.0 - 2026-10-08
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
