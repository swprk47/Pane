"""
Release-side tool for the in-app update: make the signing key once, then sign a manifest for every installer.

    python tools/update_manifest.py keygen <private.key>
    python tools/update_manifest.py sign --installer dist/Pane-1.3.0-setup.exe --version 1.3.0 \
        --url https://github.com/swprk47/Pane/releases/download/v1.3.0/Pane-1.3.0-setup.exe \
        --notes "what is new" --key <private.key> --out dist/latest.json

The private key stays outside the repository (the tool refuses to put it inside) and must be backed up: without it
nothing can be signed for the installed copies, and every user would have to install by hand once more. Upload
`latest.json` as an asset of the same release as the installer (see docs/RELEASING.md).
"""
import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nacl.signing  # noqa: E402

from core.updater import ManifestError, parse_manifest  # noqa: E402


def load_private_key(path) -> bytes:
    """The 32-byte seed stored as hex in the key file."""
    try:
        raw = bytes.fromhex(Path(path).read_text(encoding="utf-8").strip())
    except ValueError:
        raise ValueError(f"{path} is not a Pane update key file")
    if len(raw) != 32:
        raise ValueError(f"{path} is not a Pane update key file")
    return raw


def generate_keypair(private_path) -> str:
    """Write a new private key file (never over an existing one, never inside the repository) and return the public
    key as hex, which goes into core/update_config.py."""
    path = Path(private_path).resolve()
    if ROOT in path.parents:
        raise ValueError("keep the private key outside the repository")
    path.parent.mkdir(parents=True, exist_ok=True)
    key = nacl.signing.SigningKey.generate()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)       # O_EXCL: FileExistsError, never a silent overwrite
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(bytes(key).hex() + "\n")
    return bytes(key.verify_key).hex()


def make_manifest(installer, version: str, url: str, notes: str, private_key: bytes) -> bytes:
    """The signed manifest for `installer`. It is read back with the app's own parser before it is returned, so a
    manifest the app would reject (bad url, bad version) is never written."""
    sha = hashlib.sha256()
    size = 0
    with open(installer, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
            size += len(chunk)
    payload = json.dumps({"version": version, "url": url, "sha256": sha.hexdigest(), "size": size, "notes": notes},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    signing = nacl.signing.SigningKey(private_key)
    signature = base64.b64encode(signing.sign(payload.encode("utf-8")).signature).decode("ascii")
    raw = json.dumps({"payload": payload, "signature": signature}, ensure_ascii=False).encode("utf-8")
    parse_manifest(raw, bytes(signing.verify_key))
    return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1].strip())
    sub = parser.add_subparsers(dest="command", required=True)
    kg = sub.add_parser("keygen", help="make the signing key (once)")
    kg.add_argument("private_key")
    sg = sub.add_parser("sign", help="sign a manifest for an installer")
    sg.add_argument("--installer", required=True)
    sg.add_argument("--version", required=True)
    sg.add_argument("--url", required=True)
    sg.add_argument("--notes", default="")
    sg.add_argument("--key", required=True)
    sg.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "keygen":
            public_hex = generate_keypair(args.private_key)
            print(f"private key written to {args.private_key} (back it up, never commit it)")
            print(f"public key (paste into core/update_config.py as UPDATE_PUBLIC_KEY_HEX): {public_hex}")
        else:
            raw = make_manifest(args.installer, args.version, args.url, args.notes, load_private_key(args.key))
            Path(args.out).write_bytes(raw)
            print(f"manifest written to {args.out}")
    except (FileExistsError, ValueError, ManifestError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
