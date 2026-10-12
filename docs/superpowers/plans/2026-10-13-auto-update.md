# In-app update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pane tells its users a newer version exists and installs it in one click, with a signed manifest and a verified installer.

**Architecture:** Pure update logic in `core/updater.py` (version compare, signed manifest, verified download, installer launch) with no Qt, so every case is unit-tested against a local HTTP server. A thin Qt wrapper (`core/update_checker.py`) runs the check on a worker thread at most once a day. The UI (start-screen notice, 정보 dialog, settings switch) only reacts to its signals. The release side signs a manifest next to the installer.

**Tech Stack:** Python 3.14, PySide6, `urllib` (stdlib), PyNaCl (Ed25519), Inno Setup 6 (`installer/pane.iss`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-auto-update-design.md` (read it first; D1 and D2 are decided there: public GPLv3 repository, signed manifest).

## Global Constraints

- Lightness rule (PROGRESS §8-0): zero cost when updates are off or nothing is due (no thread, no network); the only new dependency is PyNaCl; measure the installer size change and record it in PROGRESS.md.
- Nothing is installed without the user's click; the update notice never appears over a playing video.
- Only the frozen app (`getattr(sys, "frozen", False)`) checks for or installs updates; source runs never do.
- Never offer a version that is lower than or equal to `core.version.APP_VERSION` (no downgrade, no replay).
- A downloaded file is run only after its size and SHA-256 match the signed manifest; otherwise it is deleted.
- User-facing text is Korean, sentence style as the rest of the app ("업데이트 확인", "새 버전 1.3.0이 있어요", "지금 업데이트", "나중에"); commit messages are English.
- `AppId` in `installer/pane.iss` never changes. Settings live in `AppSettings` (registry `HKCU\Software\Pane`); tests use the isolated `PaneTest` settings from `tests/conftest.py`.
- Per-user installs update without UAC; an all-users install asks for administrator rights.
- The manifest URL is `https://github.com/swprk47/Pane/releases/latest/download/latest.json`; every release (installer asset) must also carry a `latest.json` asset.
- The repository becomes public under GPLv3 **before** the first update-enabled version (1.3) is released; no secret, personal e-mail or private key is ever committed.
- UI changes follow the project rule: options drawn on a `/design` canvas, user approval, then app code (Task 7 is blocked on that approval).
- No change is committed or merged without the user asking; work is on branch `feature/auto-update`.

## Review Focus

- The host answers with something that is not the manifest (a captive-portal HTML page, an empty body, a 404): no crash, no notice, one quiet log line.
- The newest GitHub release has no `latest.json` asset (forgotten upload) or is a draft/pre-release: the manifest URL 404s; silent for the automatic check, a clear message for the manual one.
- A valid old manifest is served again later (replay) or the manifest names a lower version: ignored.
- The download stops half-way, the disk is full, or the file is larger than the manifest says: the partial file is removed and nothing is launched.
- The app runs from source or the exe sits in a read-only place: no update offered; no installer launched.
- The user closes Pane while the download runs, or clicks [지금 업데이트] twice: one download only, no orphan installer process.
- The installer is started but the user cancels UAC or the PC blocks it: Pane stays usable and says where the file is.

---

## File Structure

- Create `core/updater.py`: pure logic (versions, manifest, signature, download, installer command and launch).
- Create `core/update_config.py`: `UPDATE_MANIFEST_URL` (the GitHub Releases URL above), `UPDATE_PUBLIC_KEY_HEX`, `CHECK_INTERVAL_SECONDS`.
- Create `core/update_checker.py`: `UpdateChecker(QObject)`, the Qt wrapper (worker thread, throttle, signals).
- Modify `core/settings.py`: update-related `AppSettings` accessors.
- Modify `installer/pane.iss`: relaunch after a silent update (`/RELAUNCH`).
- Modify `ui/start_screen.py`, `ui/main_window.py`, `ui/settings_panel.py`: the notice, the 정보 dialog button, the switch (after the design gate).
- Create `tools/update_manifest.py`: key generation and manifest signing; extend `tools/build_release.py`.
- Create `docs/RELEASING.md`; modify `requirements.txt`, `release/THIRD_PARTY_NOTICES.txt`, `PROGRESS.md`, `README.md`.
- Tests: `tests/test_updater.py`, `tests/test_update_checker.py`, `tests/test_update_manifest_tool.py`, `tests/test_update_ui.py`; extend `tests/test_installer.py`, `tests/test_release.py`.

---

### Task 0: Make the repository public (precondition of the 1.3 release; every outward step is confirmed with the user first)

**Files:**
- Create: `LICENSE` (GPLv3 text)
- Modify: `release/LICENSE.txt`, `release/THIRD_PARTY_NOTICES.txt`, `README.md`, `PROGRESS.md`, `docs/HISTORY.md`, `.gitignore` if needed
- Test: `tests/test_release.py`

**Interfaces:** none (repository and documents).

- [ ] **Step 1: Back up** the repository before anything is rewritten: `git bundle create ..\Pane-before-rewrite.bundle --all`, then `git bundle verify ..\Pane-before-rewrite.bundle`.
- [ ] **Step 2: Scan for secrets and personal data** in the tree and in the whole history: `git log -p --all` searched for `token|secret|password|api[_-]?key|BEGIN .* PRIVATE`, and a search of the tracked files for the personal e-mail, the Windows user folder and friends' names. List every hit for the user; decide with them what is rewritten (paths in old document versions are low-risk and may be left).
- [ ] **Step 3: Check provenance** of every tracked asset (`tests/assets/*`, `assets/*`, icons, logo): made by the user or free to redistribute under GPLv3; anything unclear is removed or replaced.
- [ ] **Step 4: Write the license set.** Add `LICENSE` with the GPLv3 text (download it from gnu.org after asking), replace the interim terms in `release/LICENSE.txt` with the GPLv3 notice (the installer shows it), and extend `release/THIRD_PARTY_NOTICES.txt` with the exact mpv build in use (`mpv v0.41.0-1092-g3186d369f`, FFmpeg `N-127117-g98e92563a`, the shinchiro `mpv-winbuild-cmake` release tag) and links to the corresponding sources of mpv, FFmpeg, x264, x265 and libdvdnav; README gets a license section and the line "Corresponding source: https://github.com/swprk47/Pane". Test: `test_license_files_say_gplv3_and_name_the_source` (reads `LICENSE`, `release/LICENSE.txt`, the notices and the README for "GPL", "swprk47/Pane" and the mpv build string; the existing component-list test stays).
- [ ] **Step 5: Remove personal paths** from `PROGRESS.md` and `docs/HISTORY.md` (replace the Windows user folder with `%USERPROFILE%`); no private-key path in any document.
- [ ] **Step 6: Commit** the license, notice and cleanup changes with `docs: GPLv3 license, third-party sources and cleanup for publication` (before the rewrite, so they are part of the pushed history).
- [ ] **Step 7: Rewrite the author e-mail of the history** with `git filter-repo --mailmap` (ask before installing it; the user gives their GitHub noreply address, `<id>+swprk47@users.noreply.github.com`, from GitHub Settings, Emails). Verify: `git log --all --format=%ae` lists only the noreply address, the commit count is unchanged, all tags still exist, and the whole test suite passes.
- [ ] **Step 8: Publish.** With the user's go-ahead: force-push the rewritten branches and tags while the repository is still private, check on github.com that the commits show the noreply address, then the user changes the visibility to Public (Settings, Danger Zone) in the browser. Afterwards open the repository page logged out and check the README, the license and the Releases list.

### Task 1: Versions and the signed manifest

**Files:**
- Create: `core/updater.py`, `core/update_config.py`
- Modify: `requirements.txt` (add `pynacl>=1.5`)
- Test: `tests/test_updater.py`

**Interfaces:**
- Produces:
  - `parse_version(text: str) -> tuple[int, int, int]` (accepts "1.3.0" and "v1.3"; raises `ValueError` otherwise)
  - `is_newer(candidate: str, current: str) -> bool`
  - `@dataclass(frozen=True) class Manifest: version: str; url: str; sha256: str; size: int; notes: str`
  - `class ManifestError(ValueError)`
  - `verify_signature(payload: bytes, signature: bytes, public_key: bytes) -> bool`
  - `parse_manifest(raw: bytes, public_key: bytes) -> Manifest` (`raw` is `{"payload": "<json text>", "signature": "<base64>"}`)
  - `update_config.UPDATE_PUBLIC_KEY_HEX: str`, `UPDATE_MANIFEST_URL: str`, `CHECK_INTERVAL_SECONDS = 86400`

- [ ] **Step 1: Write the failing tests** in `tests/test_updater.py`: `test_parse_version` (parametrized: `"1.3.0" -> (1,3,0)`, `"v1.3" -> (1,3,0)`, `"1.2.10"`; `"abc"`, `""`, `"1.2.3.4"` raise `ValueError`), `test_is_newer` (`1.3.0>1.2.0`, `1.2.10>1.2.9`, equal is False, lower is False), and manifest tests using a key pair made in the test with `nacl.signing.SigningKey.generate()`: `test_a_correctly_signed_manifest_parses`, `test_a_manifest_signed_by_another_key_is_rejected`, `test_a_manifest_whose_payload_was_edited_is_rejected`, `test_missing_or_mistyped_fields_are_rejected` (no `sha256`, `size` a string, `sha256` not 64 hex chars, `url` not `https://` or `http://127.0.0.1`/`localhost` for tests), `test_garbage_and_html_are_rejected` (`b"<html>login</html>"`, `b""`) all raising `ManifestError`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_updater.py -q` and see it fail on the import.
- [ ] **Step 3: Install PyNaCl** (`python -m pip install pynacl`, ask the user first: a download) and implement the functions in `core/updater.py` with `nacl.signing.VerifyKey`; `parse_manifest` verifies the signature over the exact payload bytes before reading any field. Create `core/update_config.py` with the placeholder values and a comment pointing to D1/D2 of the spec.
- [ ] **Step 4: Run the tests**: all pass.
- [ ] **Step 5: Commit** `feat: signed update manifest and version comparison`.

### Task 2: Signing tool and the real key

**Files:**
- Create: `tools/update_manifest.py`
- Modify: `.gitignore` (`*.key`, `update_private*`), `core/update_config.py`
- Test: `tests/test_update_manifest_tool.py`

**Interfaces:**
- Consumes: `core.updater.parse_manifest`, `Manifest`
- Produces:
  - `generate_keypair(private_path: Path) -> str` (writes the private key, returns the public key as hex)
  - `make_manifest(installer: Path, version: str, url: str, notes: str, private_key: bytes) -> bytes` (computes size and SHA-256 itself)
  - CLI: `python tools/update_manifest.py keygen <private.key>` and `... sign --installer <exe> --version <v> --url <url> --notes <text> --key <private.key> --out latest.json`

- [ ] **Step 1: Write the failing tests**: `test_a_manifest_made_by_the_tool_parses_with_the_matching_public_key` (small temp "installer" file; the parsed `sha256`/`size` equal the file's), `test_keygen_writes_a_private_key_and_returns_its_public_half`, `test_the_manifest_changes_when_the_installer_changes` (a different file gives a different `sha256`).
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** the functions and the argparse CLI; Ed25519 via `nacl.signing`.
- [ ] **Step 4: Run the tests**: pass.
- [ ] **Step 5: Generate the real key pair** outside the repository (for example `<Documents>\pane_update_private.key`, tell the user to back it up: losing it means one more manual install for every friend), paste the public hex into `core/update_config.py`. Add a test `test_the_embedded_public_key_is_a_valid_ed25519_key`.
- [ ] **Step 6: Commit** `feat: update manifest signing tool and public key`.

### Task 3: Fetching the manifest and downloading the installer

**Files:**
- Modify: `core/updater.py`
- Test: `tests/test_updater.py` (a `http.server` fixture on `127.0.0.1` serving files from `tmp_path`)

**Interfaces:**
- Consumes: `Manifest`, `parse_manifest`
- Produces:
  - `fetch_manifest(url: str, public_key: bytes, timeout: float = 10.0) -> Manifest`
  - `download_installer(manifest: Manifest, dest_dir: Path, progress: Callable[[int, int], None] | None = None, timeout: float = 30.0) -> Path` (returns `dest_dir / f"Pane-{version}-setup.exe"`)
  - `class UpdateError(Exception)`

- [ ] **Step 1: Write the failing tests**: `test_fetch_manifest_from_a_server`, `test_fetch_manifest_with_an_html_login_page_raises_manifest_error`, `test_fetch_manifest_404_and_connection_refused_raise_update_error`, `test_download_writes_the_file_and_reports_progress` (progress called with growing `done` up to `size`), `test_a_file_with_the_wrong_hash_is_deleted_and_raises`, `test_a_truncated_download_is_deleted_and_raises`, `test_a_file_bigger_than_the_manifest_size_is_stopped`, `test_no_partial_file_is_left_after_a_failure` (the destination folder is empty).
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** with `urllib.request` (explicit `User-Agent: Pane/<version>`), stream in 64 KB chunks into `<name>.part`, check size while reading and SHA-256 at the end, then `os.replace` to the final name; any failure removes the `.part`.
- [ ] **Step 4: Run the tests**: pass.
- [ ] **Step 5: Commit** `feat: fetch the manifest and download the installer with verification`.

### Task 4: Installer launch and the installer script

**Files:**
- Modify: `core/updater.py`, `installer/pane.iss`
- Test: `tests/test_updater.py`, `tests/test_installer.py`

**Interfaces:**
- Produces:
  - `install_scope(exe_dir: Path, localappdata: Path) -> str` returns `"user"` when `exe_dir` is inside `localappdata`, else `"machine"`
  - `installer_command(path: Path, scope: str) -> list[str]`: `[str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH", "/CURRENTUSER" | "/ALLUSERS"]`
  - `launch_installer(path: Path, scope: str) -> None` (starts it detached, does not wait)

- [ ] **Step 1: Write the failing tests**: `test_install_scope_by_folder`, `test_installer_command_for_each_scope`, `test_launch_installer_starts_it_detached_and_does_not_wait` (monkeypatch `subprocess.Popen`, assert `creationflags` has `DETACHED_PROCESS`, `close_fds` true), and in `tests/test_installer.py` `test_the_installer_script_relaunches_after_a_silent_update` (the `[Run]` section has a Pane.exe entry with `nowait` and `Check: WantsRelaunch`, and `WantsRelaunch` looks for `/RELAUNCH`).
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** the three functions; in `pane.iss` add `function WantsRelaunch(): Boolean;` (a `ParamStr` loop like `ShouldDeleteSettings`) and a second `[Run]` line `Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WantsRelaunch`.
- [ ] **Step 4: Run the tests**: pass.
- [ ] **Step 5: Commit** `feat: silent installer launch with relaunch`.

### Task 5: The checker (worker thread, throttle, settings)

**Files:**
- Create: `core/update_checker.py`
- Modify: `core/settings.py`
- Test: `tests/test_update_checker.py`, `tests/test_settings*.py` additions

**Interfaces:**
- Consumes: `fetch_manifest`, `is_newer`, `download_installer`, `launch_installer`, `install_scope`, `update_config`
- Produces:
  - `AppSettings.get_update_check_enabled() -> bool` (default `True`), `set_update_check_enabled(bool)`, `get_last_update_check() -> float` (default `0.0`), `set_last_update_check(float)`
  - `should_check(now: float, last_check: float, interval: float = 86400.0) -> bool` in `core/updater.py`
  - `class UpdateChecker(QObject)`: signals `update_available(object)` (a `Manifest`), `up_to_date()`, `check_failed(str)`, `download_progress(int, int)`, `installer_ready(str)`, `install_failed(str)`; slots `check(manual: bool = False)`, `download_and_install()`; property `busy: bool`; constructor `UpdateChecker(settings: AppSettings, current_version: str, frozen: bool, manifest_url: str, public_key: bytes, parent=None)`

- [ ] **Step 1: Write the failing tests** (a local server and a fake `now`): `test_automatic_check_is_skipped_when_off_or_not_due_or_from_source` (no thread started, no request: the server's request log stays empty), `test_a_manual_check_ignores_the_throttle_and_the_off_switch`, `test_a_newer_version_emits_update_available_and_records_the_time`, `test_equal_or_lower_version_emits_up_to_date_only`, `test_failures_are_silent_for_the_automatic_check_and_reported_for_the_manual_one`, `test_download_and_install_verifies_then_launches_once` (monkeypatched `launch_installer`; a second call while `busy` does nothing), `test_a_bad_download_emits_install_failed_and_does_not_launch`.
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement**: `QThreadPool` with a `QRunnable` for each network job; results come back by queued signals; `check()` returns immediately.
- [ ] **Step 4: Run the tests**: pass.
- [ ] **Step 5: Commit** `feat: background update checker with throttle`.

### Task 6: Design gate (blocks Task 7)

**Files:** none (a `/design` canvas and the user's decision).

- [ ] **Step 1:** Ask the user for the direction, then draw 2 to 3 options on a `/design` canvas (Artifact `quickstart` with `intent: "design"`): where the notice lives (a card on the start screen under the logo like the file-error notice; a bottom-right card like `NextUpCard` shown only when no video plays; a line in the 정보 dialog only), the download progress, and the settings switch (a switch row in the 성능 tab or a new tab).
- [ ] **Step 2:** Wait for the user's choice before Task 7. Record the choice in the spec.

### Task 7: The UI (after Task 6)

**Files:**
- Modify: `ui/start_screen.py`, `ui/main_window.py`, `ui/settings_panel.py`
- Test: `tests/test_update_ui.py`

**Interfaces:**
- Consumes: `UpdateChecker` signals and slots (Task 5)
- Produces (names fixed here; the look follows Task 6): `StartScreen.set_update(version: str, notes: str)`, `StartScreen.clear_update()`, signals `StartScreen.update_requested` and `update_dismissed`, `MainWindow.update_checker`, and a settings switch `SettingsPanel.switch_updates` with signal `updates_changed(bool)`.

- [ ] **Step 1: Write the failing tests** (the UI-state ones as `render()`-based pixel checks plus attribute checks, per PROGRESS §5 #30): `test_the_notice_shows_on_the_start_screen_when_an_update_is_available`, `test_the_notice_never_shows_over_a_playing_video` (it waits and appears when playback stops or a file closes), `test_later_hides_it_for_this_run`, `test_update_button_starts_one_download_and_shows_progress`, `test_the_settings_switch_turns_the_automatic_check_off_and_on`, `test_the_about_dialog_has_a_check_now_button_that_reports_the_result` ("최신 버전이에요" / "확인하지 못했어요").
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** the approved design; start the first automatic check 5 seconds after the window is shown (`QTimer.singleShot`), only when `frozen`.
- [ ] **Step 4: Run the tests, then take real screenshots** of each state (default and 640×380) to check the look.
- [ ] **Step 5: Commit** `feat: update notice, check-now button and settings switch`.

### Task 8: Release tooling and documentation

**Files:**
- Modify: `tools/build_release.py`, `release/THIRD_PARTY_NOTICES.txt`, `README.md`, `PROGRESS.md`
- Create: `docs/RELEASING.md`
- Test: `tests/test_release.py`

**Interfaces:**
- Consumes: `tools.update_manifest.make_manifest`
- Produces: `python tools/build_release.py --installer --sign-key <private.key> --manifest-url <url>` also writes `dist/latest.json`

- [ ] **Step 1: Write the failing tests**: `test_third_party_notices_list_pynacl` (extends the existing component list in `tests/test_release.py`), `test_build_release_writes_a_manifest_when_given_a_key` (calls the manifest function the build uses on a temp file; the full build is not run in tests).
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** the flag; add the PyNaCl entry to `THIRD_PARTY_NOTICES.txt`; write `docs/RELEASING.md` (build, sign, upload `latest.json` and the installer, check the URL, keep the key safe); add a README line for friends (one last manual install, then updates come by themselves); `--hidden-import nacl` if PyInstaller needs it.
- [ ] **Step 4: Run the whole suite**: all pass.
- [ ] **Step 5: Commit** `feat: sign and publish the update manifest at release time`.

### Task 9: Verification (needs the user's permission)

**Files:** none (a checklist run on this PC; record the results in PROGRESS.md).

- [ ] **Step 1: Build** `python tools/build_release.py --installer --sign-key <key> --manifest-url <local url>` for the current version and, from a copy with `core/version.py` raised, a second build; measure the installer size change against 1.2.0 (PyNaCl) and the startup time with the check on and off (no change expected when off).
- [ ] **Step 2: End to end on this PC** (ask first: it installs, closes and starts programs and touches `HKCU\Software\Pane`): serve the newer installer and its signed manifest from `http://127.0.0.1:<port>`, install the older build in a temp folder with `/CURRENTUSER`, start it, see the notice, click [지금 업데이트], and confirm the app closes, the new version installs, starts again and reports the new version. Back up and restore the registry settings as in the 1.2.0 procedure.
- [ ] **Step 3: Failure runs**: tamper with one byte of the served installer (no launch, a message), serve an HTML page as the manifest (silent), and stop the server mid-download (partial file removed).
- [ ] **Step 4: Record** the numbers and results in PROGRESS.md §1 and §8, then ask the user about merging.

---

## Self-review

- **Spec coverage:** public GPLv3 repository and cleanup (Task 0), manifest and signature (Tasks 1, 2), verified download (3), silent install with relaunch and scope (4), once-a-day background check, off switch, source runs excluded (5), notice, check-now, switch (6, 7), release steps and the unsigned-installer limits (8), end-to-end and failure runs (9). D1 and D2 are decided (public repository, signed manifest); the hosting is one constant in `core/update_config.py`.
- **Types:** `Manifest`, `parse_manifest`, `fetch_manifest`, `download_installer`, `install_scope`, `installer_command`, `launch_installer`, `should_check` are defined once (Tasks 1, 3, 4, 5) and used with those names later.
- **Proportion:** nine tasks for a feature that touches one pure module, one Qt wrapper, three UI spots and the release script.
