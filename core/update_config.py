"""
Where Pane looks for updates and which key it trusts (decisions D1 and D2 of
docs/superpowers/specs/2026-10-13-auto-update-design.md).

D1: the public repository's Releases hold `latest.json` and the installer; "latest" is the newest release, so every
release must carry a `latest.json`.
D2: `latest.json` is signed with Ed25519; only the public half lives here, the private key never enters the repository.
"""

import os

# PANE_UPDATE_MANIFEST_URL points a test build at a local server (the manifest must still carry a valid signature,
# and the trusted key below has no override).
UPDATE_MANIFEST_URL = os.environ.get("PANE_UPDATE_MANIFEST_URL") or "https://github.com/swprk47/Pane/releases/latest/download/latest.json"
UPDATE_PUBLIC_KEY_HEX = "9746c3afaa8f8f48e58cfa4ae8d5c95c8414edd6e67e6311a75d23b7f4ac7137"          # Ed25519 public key (the private half is not in the repository)
CHECK_INTERVAL_SECONDS = 86400      # an automatic check at most once a day
