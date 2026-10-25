# The shortcut help panel (`?`) — design

Date: 2026-10-26. Status: decisions taken in chat with the owner; to be reviewed as written.
Mock-ups (real home screen + real glass painting, throw-away): the /design canvas "Pane 단축키 도움말 시안"
(A2 = the centred panel with better legibility, B = the right drawer, buttons ②).

## Why

Pane has about 27 keyboard shortcuts and a few mouse gestures, written down only in the README and the release notes. A
friend who installs Pane never sees them. A help panel inside the app lists them where they are needed.

## What the owner decided

- **Opening:** the `?` key, a new right-click menu entry `단축키 (?)`, and a button on the title bar: `PIP ⟳ ? |` (right
  after the update-check button, before the divider that precedes the window buttons).
- **Content:** the keys (in groups), the mouse gestures, and a few tips.
- **Look:** on the **home screen** (no video) a centred, two-column panel over a dimmed window (mock "A2"); **while a video is
  open** a drawer at the right edge that leaves the video visible and playing (mock "B"). Both: an almost opaque dark body
  under the glass edge (the first mock let the logo show through and was hard to read), bigger text, group titles in a soft
  blue.
- **Playback is not touched** when the help opens (the video goes on playing).

## Behaviour

- **Toggle.** `?` (also Shift+/ and the keypad-less layouts: `Qt.Key_Question`, or `Qt.Key_Slash` with Shift), the menu entry
  and the title-bar button open it when it is closed and close it when it is open. `Esc` closes it (before the other things
  `Esc` does: next-video card, bookmark list, track popup, info panel, full screen, PIP). A click on the dim (centred layout)
  closes it.
- **Layout choice (decided each time it opens):** centred when no video is loaded **and** the video area is at least
  940 × 680 px; otherwise the drawer. (The window can be as small as 640 × 380, and the PIP window 480 × 270: there the drawer
  is the only layout that fits; its content scrolls.)
- **Keys while it is open.** Centred layout: it is modal, like the settings panel: only `Esc` and `?` do anything, every other
  key is swallowed. Drawer: it is a reference sheet, so every shortcut keeps working (that is how you try what you read);
  `?` and `Esc` close it.
- **The help closes by itself** when a video is opened or the player returns to the home screen (the layout would be the
  wrong one), and is re-placed when the window is resized or goes full screen.
- **A name being typed** in the bookmark list still owns the keyboard: `?` typed there is a character, not a command (the
  existing guard in `KeyRouter` is before the new key).
- **Nothing is created until the first time it opens**; after that the panel is kept (hidden) and only re-filled when shown.

## Content (the single place: `ui/help_content.py`, plain data)

Groups (keys → description), exactly as in the mock:

- 재생: `Space` 재생 / 일시정지 · `[ ]` 배속 −0.1 / +0.1 (Shift: 0.05) · `\ Backspace` 배속 1.0x로 · `← →` 5초 이동 (Shift: 1초) ·
  `, .` 1프레임 뒤 / 앞 (일시정지 중) · `PageUp PageDown` 이전 / 다음 영상
- 소리 · 자막: `↑ ↓` 볼륨 +5 / −5 · `M` 음소거 · `C` 자막 켜기 / 끄기 · `Z X` 자막 싱크 ∓0.1초 (Shift: 오디오) · `Ctrl+Z` 싱크 초기화
- 북마크: `B` 지금 위치를 북마크로 저장 · `Shift+B` 북마크 목록 · `Alt+← →` 이전 / 다음 북마크
- 화면 · 파일: `F Enter` 전체화면 · `P` PIP 모드 · `I` 재생 정보 · `Ctrl+O` 파일 열기 · `Ctrl+S` 화면 캡처 · `?` 이 도움말 ·
  `Esc` 닫기 · 전체화면 나가기
- 마우스: 클릭 재생 / 일시정지 · 더블클릭 전체화면 · 드래그 창 이동 · 우클릭 메뉴 · 재생바 클릭해서 이동, 올리면 시간과 장면 ·
  노란 핀 클릭하면 그 북마크로
- 팁: (1) 배속과 오디오·자막 선택은 영상마다 기억돼요. 처음 여는 영상은 같은 폴더에서 마지막으로 쓴 값으로 시작해요.
  (2) 강의 영상은 B로 "다시 볼 곳"을 찍어 두세요. 재생바의 노란 핀이나 Alt+←/→로 돌아가요.
  (3) 목소리가 먹먹하면 설정 > 오디오의 "강의 음성"을 켜 보세요.

## Components (follows the rule: new code goes in a unit, not in `MainWindow`)

- `ui/help_content.py` — `KEY_GROUPS`, `MOUSE`, `TIPS` (data only, no Qt).
- `ui/help_panel.py` — `HelpPanel(QFrame)`: builds the chips and rows from the data; `set_layout(kind)`
  (`"centered"` / `"drawer"`); `place(viewport_rect)`; the dim for the centred layout; a scroll area for the drawer.
  Paints an almost opaque body (`QColor(11, 13, 19, 242)`) under `paint_glass_panel(..., calm=True)`; key chips 13 px bold,
  descriptions 14 px, group titles 13 px `#9FC5FF`; the dim is `QColor(0, 0, 0, 215)`.
- `ui/help_flow.py` — `HelpFlow(window)` (created like `marks` and `updates`): `toggle()`, `open()`, `close()`,
  `is_open()`, `layout_kind()`, `relayout()`; owns the panel; called by the key router, the menu, the button.
- `ui/title_bar.py` — `btn_help` (flat, 28 px, a new `help` icon in `ui/icons.py`, tooltip `단축키 도움말 (?)`), signal
  `help_clicked`. **The divider beside the update button now stays visible while a video is open** (it separates the window
  buttons from the rest, and the help button is always there); only the update button is home-only. This changes
  `set_update_visible` and the existing test that asserts the divider hides.
- `ui/context_menu.py` — one more entry `단축키 (?)` just before `설정...`; the characterization test that pins the menu
  list gets the new line (a deliberate edit, with its reason in the commit).
- `ui/key_bindings.py` — `?` handled right after the settings-panel check and the rename guard; `Esc` closes the help first;
  while the centred layout is open all other keys are swallowed.
- `ui/main_window.py` — creates `self.help = HelpFlow(self)`, connects `title_bar.help_clicked`, closes the help in
  `load_media_file` / `_show_file_problem`, re-places it in `_reposition_floating_widgets`, `help` raised with the other
  floating widgets.

## Drift guard

A test lists every `Qt.Key_*` that `KeyRouter.handle` uses (read from the source text of `ui/key_bindings.py`), maps each to
the token shown in the help (`Key_Space` → `Space`, `Key_BracketLeft` / `Key_BracketRight` → `[` `]`, …), and fails when a key
is not in the map or its token is not in `KEY_GROUPS`. A new shortcut without a help line fails the suite. (The README table
and the release notes are checked the same way as today by `tests/test_release.py`; the README gets the `?` row.)

## Tests (outline; the plan has the exact ones)

- the data: every group non-empty, no duplicate keys inside a group, the drift guard above;
- the panel: builds from the data, both layouts, the drawer scrolls, an almost opaque body (pixel check that the dim and the
  home screen's logo do not show through the text area), stays inside the window at 640 × 380 and 480 × 270;
- the flow: `?` toggles; `Esc` closes before anything else; the layout choice (home and large → centred; a video → drawer;
  small window → drawer); modal keys in the centred layout, shortcuts still work in the drawer; closes on opening a video;
- the title-bar button (position, tooltip, shown always, divider stays) and the menu entry;
- wiring "exactly once" like `tests/test_split_wiring.py`; the existing e2e file is not affected.

## Out of scope

`Ctrl+G` (shelved: the mouse and the bookmarks cover it), a searchable help, rebinding keys, translation, a button on the
controls bar (it would need a layout migration for saved layouts), a "show this the first time" tour.

## Done when

`?`, the menu entry and the button open and close the help; the right layout shows in each state; the drift guard is in
place; the suite is green; the e2e mouse tests still pass; a short look at the real window (opened with the owner's go-ahead)
shows the panel legible over a playing video and on the home screen; README, CHANGELOG, release notes and PROGRESS mention it.
