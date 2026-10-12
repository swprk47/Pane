"""
Where Pane looks for updates and which key it trusts (decisions D1 and D2 of
docs/superpowers/specs/2026-10-13-auto-update-design.md).

D1: the public repository's Releases hold `latest.json` and the installer; "latest" is the newest release, so every
release must carry a `latest.json`.
D2: `latest.json` is signed with Ed25519; only the public half lives here, the private key never enters the repository.
"""

UPDATE_MANIFEST_URL = "https://github.com/swprk47/Pane/releases/latest/download/latest.json"
UPDATE_PUBLIC_KEY_HEX = ""          # the real key is generated and pasted in by tools/update_manifest.py (Task 2)
CHECK_INTERVAL_SECONDS = 86400      # an automatic check at most once a day
