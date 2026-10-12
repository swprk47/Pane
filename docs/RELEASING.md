# Releasing Pane

Every release carries two files that the in-app update needs: the installer and a signed `latest.json`. The app asks
`https://github.com/swprk47/Pane/releases/latest/download/latest.json`; "latest" is the newest published release, so
**each release must have its own `latest.json` attached**, or the update check of every installed copy fails (quietly).

## Steps

1. Raise the version in `core/version.py`, run the whole test suite (`python -m pytest`; with the person's
   permission also `--run-e2e`, it moves the cursor).
2. Build and sign (the signing key is a file outside the repository, see "The key" below):

   ```
   python tools/build_release.py --installer --sign-key <path to the private key> --notes "what is new, one line"
   ```

   This writes `dist/Pane-<version>-setup.exe`, `dist/Pane-<version>-win64.zip` and `dist/latest.json`. The installer
   URL inside the manifest is the release asset of the same tag (`.../releases/download/v<version>/...`); another
   host can be given with `--installer-url`.
3. Try the installer on a scratch folder (install, run, upgrade over the previous version, uninstall) as in
   `docs/HISTORY.md`.
4. Tag and push: `git tag v<version>` and `git push origin v<version>` (with the person's go-ahead).
5. On GitHub: Releases, Draft a new release, choose the tag, attach `Pane-<version>-setup.exe` **and `latest.json`**
   (the zip is optional), then Publish. A draft or a pre-release is ignored by "latest", so the update would not be
   offered.
6. Check it: open the `latest/download/latest.json` address above in a browser and look for the new version; in an
   older installed Pane open 정보 and press "업데이트 확인".

## The key

The manifest is signed with an Ed25519 key. The public half is in `core/update_config.py`
(`UPDATE_PUBLIC_KEY_HEX`); the private half is a file made once by `python tools/update_manifest.py keygen <file>`
and must never be committed (`*.key` is git-ignored and the tool refuses a path inside the repository).

- **Back it up** to a second place (offline copy, password manager). Without it no new manifest can be signed.
- **If it is lost or leaked:** make a new key, put its public half in `core/update_config.py` and ship a release.
  Installed copies still trust the old key and reject the new manifests, so everyone has to install that one release
  by hand, once. Nothing else can be done for them, which is why the key matters.

## A bad release

Publish a newer version: the app never offers a version that is not newer than the installed one, so deleting or
re-uploading an older file does not roll anybody back.
