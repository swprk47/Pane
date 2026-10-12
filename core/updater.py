"""
The update logic, without Qt: version comparison and the signed manifest (this module grows with the verified
download and the installer launch, see docs/superpowers/plans/2026-10-13-auto-update.md).

A manifest is ``{"payload": "<json text>", "signature": "<base64 ed25519>"}``; the signature covers the exact payload
bytes. Pane is not code-signed, so this signature is what keeps a compromised hosting account from pushing code to
every user: nothing in the payload is read before it verifies.
"""
import base64
import binascii
import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from nacl.exceptions import BadSignatureError, CryptoError
from nacl.signing import VerifyKey

_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_LOCAL_HOSTS = ("127.0.0.1", "localhost")          # (plain http is only accepted for a local test server)


def parse_version(text: str) -> tuple:
    """"1.3.0" or "v1.3" as (1, 3, 0); anything else is a ValueError."""
    m = _VERSION.match((text or "").strip())
    if not m:
        raise ValueError(f"not a version: {text!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


class ManifestError(ValueError):
    """The bytes are not a manifest this build trusts."""


@dataclass(frozen=True)
class Manifest:
    version: str
    url: str
    sha256: str
    size: int
    notes: str = ""


def verify_signature(payload: bytes, signature: bytes, public_key: bytes) -> bool:
    try:
        VerifyKey(public_key).verify(payload, signature)
        return True
    except (BadSignatureError, CryptoError, ValueError, TypeError):
        return False


def _allowed_url(url) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlparse(url)
    if parts.scheme == "https" and parts.hostname:
        return True
    return parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS


def parse_manifest(raw: bytes, public_key: bytes) -> Manifest:
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, AttributeError):
        raise ManifestError("not a manifest")
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), str) \
            or not isinstance(envelope.get("signature"), str):
        raise ManifestError("not a manifest")
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
    except (binascii.Error, ValueError):
        raise ManifestError("bad signature")
    if not verify_signature(envelope["payload"].encode("utf-8"), signature, public_key):
        raise ManifestError("bad signature")

    try:
        data = json.loads(envelope["payload"])
    except ValueError:
        raise ManifestError("bad payload")
    if not isinstance(data, dict):
        raise ManifestError("bad payload")
    version, url, sha256, size = data.get("version"), data.get("url"), data.get("sha256"), data.get("size")
    notes = data.get("notes", "")
    try:
        parse_version(version)
    except ValueError:
        raise ManifestError(f"bad version: {version!r}")
    if not _allowed_url(url):
        raise ManifestError(f"bad url: {url!r}")
    if not isinstance(sha256, str) or not _SHA256.match(sha256):
        raise ManifestError("bad sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ManifestError("bad size")
    if not isinstance(notes, str):
        raise ManifestError("bad notes")
    return Manifest(version=version.strip(), url=url, sha256=sha256.lower(), size=size, notes=notes)
