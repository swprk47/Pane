# Pane in-app update: design

Date: 2026-10-13. Status: decided by the user the same day: D1 = public GPLv3 repository, D2 = signed manifest in 1.3 (see "Decisions").

## Why

Friends who use Pane have to be sent every new installer by hand and run it themselves ("too much hassle", and the
maintainer finds sending files tiresome too). Wanted: the app tells them a new version exists and installs it in one
click.

## What it is (and is not)

- On start-up, at most once a day, in the background, Pane asks one small file (the manifest) for the newest version.
- If it is newer than `core.version.APP_VERSION`, a quiet notice offers **[지금 업데이트] / [나중에]**. Nothing is
  installed without that click ("auto" = one click, not silent).
- On click Pane downloads the installer (~70 MB), checks it, starts it silently (`/SILENT`), the installer closes
  Pane, replaces it and starts it again.
- Off switch in the settings. Zero cost when off or when nothing is due (no thread, no network). No new heavy
  dependency (the roadmap's "lightness rule", PROGRESS §8-0).

## Why it is feasible with what exists

- The installer (`installer/pane.iss`, Inno Setup) has a fixed `AppId`, so a new version replaces the installed one;
  `CloseApplications=yes` closes a running Pane (verified in the 1.2.0 upgrade test).
- Installs are per-user by default (`PrivilegesRequired=lowest`): the update needs no administrator prompt.
- `core/version.py` is already the single version source.

## Design

1. **Manifest**: `latest.json` = `{"payload": "<json string>", "signature": "<base64 ed25519>"}`; the payload holds
   `version`, `url`, `sha256`, `size`, `notes`. The app embeds the public key; the private key stays with the
   maintainer (never in the repository). The signature is the real safeguard: Pane is unsigned (no Authenticode),
   so a hosting or account compromise must not be able to push code to every friend.
2. **Download**: to a temp folder, `size` and SHA-256 checked, atomic rename; a bad file is deleted, never run.
3. **Install**: `Pane-<v>-setup.exe /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELAUNCH`, plus
   `/CURRENTUSER` for a per-user install or `/ALLUSERS` (UAC) for an all-users one. `/RELAUNCH` is new: the installer
   starts the app again after a silent update (today `skipifsilent` stops that).
4. **Never** from source runs (only the frozen app updates), never over a lower or equal version (no downgrade), never
   while a file is playing (the notice shows on the start screen, in 정보, and in the settings; not over video).
5. **Release side**: `tools/update_manifest.py` signs and writes `latest.json` next to the installer; the release
   steps are written down in `docs/RELEASING.md`.

## Decisions (2026-10-13)

- **D1: public repository `swprk47/Pane`, source included, license GPLv3.** `latest.json` and the installer are Releases assets of that same repository (`https://github.com/swprk47/Pane/releases/latest/download/latest.json`; every release must carry a `latest.json`, because "latest" resolves against the newest release). The history is rewritten first so the author email becomes a GitHub noreply address (done while the repository is still private, then force-pushed, then made public). Compatible licenses checked: python-mpv GPLv2+ or LGPLv2.1+, pywinstyles CC0, PySide6 LGPL-3.0 or GPL-3.0, the libmpv/FFmpeg build GPLv3. Free code signing for open-source projects (SignPath Foundation) becomes possible later.
- **D2: Ed25519-signed manifest (PyNaCl) in 1.3**, because a client that ships without signature checking can never be protected afterwards. The private key stays on the maintainer's PC only, backed up.

### Options that were weighed for D1

**Where do `latest.json` and the installer live?** Friends' PCs must read it without a login, and the repository
is private.

| Option | What | Cost / risk |
|---|---|---|
| A (recommended) | a small **public** GitHub repo `Pane-releases` with only Releases (`latest.json` + installer as assets; URL `https://github.com/<user>/Pane-releases/releases/latest/download/latest.json`) | free, stable URLs, upload by web like now. Makes the binaries public: libmpv is GPLv3 (PROGRESS §7), so public distribution should come with the license decision (publish Pane's source under GPL, or offer it) |
| B | an unlisted static host (e.g. a public bucket with a long random path) | keeps distribution as limited as today; needs one more account, the URL is only "secret by obscurity" |
| C | keep the private repo and give each friend a token | rejected: a token inside the app can be extracted |

The code does not depend on the choice: it is one constant (`UPDATE_MANIFEST_URL`).

**D2: signature or only HTTPS + SHA-256?** Recommended: Ed25519 via PyNaCl (a ~1 MB wheel, installer growth to be
measured). Without it, whoever controls the hosting account controls every friend's PC.

## Known limits

- Friends on 1.2.0 have no updater: they need one last manual install of the first version that has it.
- No code signing (SmartScreen); a PC with Smart App Control may still refuse to run the installer: Pane then keeps
  the file and opens its folder, the update is done by hand like today.
- An all-users install asks for administrator rights (UAC) when the installer starts.
