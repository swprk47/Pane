"""
The update logic, without Qt: version comparison and the signed manifest (this module grows with the verified
download and the installer launch, see docs/superpowers/plans/2026-10-13-auto-update.md).

A manifest is ``{"payload": "<json text>", "signature": "<base64 ed25519>"}``; the signature covers the exact payload
bytes. Pane is not code-signed, so this signature is what keeps a compromised hosting account from pushing code to
every user: nothing in the payload is read before it verifies.
"""
import base64
import binascii
import hashlib
import http.client
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from nacl.exceptions import BadSignatureError, CryptoError
from nacl.signing import VerifyKey

from core.version import APP_VERSION

_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_LOCAL_HOSTS = ("127.0.0.1", "localhost")          # (plain http is only accepted for a local test server)
MANIFEST_LIMIT = 64 * 1024                          # a manifest is a few hundred bytes: anything bigger is not one
CHUNK = 64 * 1024
DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP = 0x00000008, 0x00000200


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


class UpdateError(Exception):
    """The network or the download failed (nothing wrong with the signature: that is a ManifestError)."""


def _open(url: str, timeout: float):
    request = urllib.request.Request(url, headers={"User-Agent": f"Pane/{APP_VERSION}"})
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"the server answered {e.code}")
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as e:
        raise UpdateError(f"could not reach {url}: {e}")


def fetch_manifest(url: str, public_key: bytes, timeout: float = 10.0) -> Manifest:
    """The verified manifest at `url`. UpdateError when the server cannot be reached or answers an error,
    ManifestError when what it sends is not a manifest signed with `public_key`."""
    with _open(url, timeout) as response:
        try:
            raw = response.read(MANIFEST_LIMIT + 1)
        except (OSError, http.client.HTTPException) as e:
            raise UpdateError(f"the answer was cut off: {e}")
    if len(raw) > MANIFEST_LIMIT:
        raise ManifestError("too large to be a manifest")
    return parse_manifest(raw, public_key)


def download_installer(manifest: Manifest, dest_dir, progress: Optional[Callable[[int, int], None]] = None,
                       timeout: float = 30.0) -> Path:
    """Download the installer the manifest names into `dest_dir` and return its path. The bytes go to a `.part` file
    first and are renamed only when the size and the SHA-256 match the manifest; on any failure the `.part` file is
    removed and an earlier good copy is left alone."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"Pane-{manifest.version}-setup.exe"
    part = final.with_name(final.name + ".part")
    try:
        with _open(manifest.url, timeout) as response:
            declared = response.headers.get("Content-Length")
            if declared is not None and declared.isdigit() and int(declared) != manifest.size:
                raise UpdateError("the file is not the size the manifest says")
            sha = hashlib.sha256()
            done = 0
            with open(part, "wb") as out:
                while True:
                    try:
                        chunk = response.read(CHUNK)
                    except (OSError, http.client.HTTPException) as e:
                        raise UpdateError(f"the download was cut off: {e}")
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > manifest.size:
                        raise UpdateError("the file is bigger than the manifest says")
                    out.write(chunk)
                    sha.update(chunk)
                    if progress:
                        progress(done, manifest.size)
        if done != manifest.size:
            raise UpdateError("the download is incomplete")
        if sha.hexdigest() != manifest.sha256:
            raise UpdateError("the file does not match its checksum")
        os.replace(part, final)
        return final
    finally:
        part.unlink(missing_ok=True)


def install_scope(exe_dir, localappdata) -> str:
    """"user" when the app is installed under the user's own profile (a per-user install: no administrator prompt),
    else "machine" (an all-users install)."""
    return "user" if Path(exe_dir).resolve().is_relative_to(Path(localappdata).resolve()) else "machine"


def installer_command(path, scope: str) -> list:
    """The silent update command line: close the running Pane, install without questions, start Pane again
    (/RELAUNCH is read by installer/pane.iss), over the same kind of install as the one running."""
    flags = {"user": "/CURRENTUSER", "machine": "/ALLUSERS"}
    if scope not in flags:
        raise ValueError(f"unknown install scope: {scope!r}")
    return [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH", flags[scope]]


def launch_installer(path, scope: str) -> None:
    """Start the installer and return at once: it closes this app itself. A failure (a policy blocking the file, say)
    is an UpdateError that names the file, so it can be run by hand."""
    try:
        subprocess.Popen(installer_command(path, scope), creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                         close_fds=True)
    except OSError as e:
        raise UpdateError(f"could not start the installer ({e}); it is saved at {path}")
