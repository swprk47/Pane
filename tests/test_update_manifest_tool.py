"""The release-side tool: make a key pair, sign a manifest for an installer."""
import hashlib
from pathlib import Path

import nacl.signing
import pytest

from core import update_config
from core.updater import ManifestError, parse_manifest
from tools import update_manifest as um

URL = "https://github.com/swprk47/Pane/releases/download/v1.3.0/Pane-1.3.0-setup.exe"


@pytest.fixture
def installer(tmp_path):
    p = tmp_path / "Pane-1.3.0-setup.exe"
    p.write_bytes(b"MZ pretend installer " * 1000)
    return p


@pytest.fixture
def keys(tmp_path):
    private = tmp_path / "private.key"
    public_hex = um.generate_keypair(private)
    return um.load_private_key(private), bytes.fromhex(public_hex), private, public_hex


def test_a_manifest_made_by_the_tool_parses_with_the_matching_public_key(installer, keys):
    private, public, _, _ = keys
    raw = um.make_manifest(installer, "1.3.0", URL, "새 기능이 생겼어요", private)
    m = parse_manifest(raw, public)
    assert m.version == "1.3.0" and m.url == URL and m.notes == "새 기능이 생겼어요"
    assert m.size == installer.stat().st_size
    assert m.sha256 == hashlib.sha256(installer.read_bytes()).hexdigest()


def test_the_manifest_changes_when_the_installer_changes(installer, keys, tmp_path):
    private, public, _, _ = keys
    other = tmp_path / "other.exe"
    other.write_bytes(b"MZ different bytes")
    a = parse_manifest(um.make_manifest(installer, "1.3.0", URL, "", private), public)
    b = parse_manifest(um.make_manifest(other, "1.3.0", URL, "", private), public)
    assert a.sha256 != b.sha256 and a.size != b.size


def test_a_manifest_made_with_another_key_is_not_trusted(installer, keys):
    private, _, _, _ = keys
    stranger = bytes(nacl.signing.SigningKey.generate().verify_key)
    with pytest.raises(ManifestError):
        parse_manifest(um.make_manifest(installer, "1.3.0", URL, "", private), stranger)


def test_the_tool_refuses_to_write_a_manifest_the_app_would_reject(installer, keys):
    private, _, _, _ = keys
    with pytest.raises(ManifestError):
        um.make_manifest(installer, "1.3.0", "ftp://example.com/Pane.exe", "", private)
    with pytest.raises(ManifestError):
        um.make_manifest(installer, "latest", URL, "", private)


def test_keygen_writes_a_private_key_and_returns_its_public_half(keys):
    private, public, path, public_hex = keys
    assert len(private) == 32 and len(public) == 32 and len(public_hex) == 64
    assert bytes(nacl.signing.SigningKey(private).verify_key) == public
    assert path.exists()


def test_keygen_never_overwrites_an_existing_key(keys):
    _, _, path, _ = keys
    before = path.read_text()
    with pytest.raises(FileExistsError):
        um.generate_keypair(path)
    assert path.read_text() == before, "losing the key would mean a manual install for every user"


def test_keygen_refuses_a_place_inside_the_repository():
    with pytest.raises(ValueError):
        um.generate_keypair(um.ROOT / "some.key")


def test_private_keys_are_git_ignored():
    patterns = (um.ROOT / ".gitignore").read_text().split()
    assert "*.key" in patterns


def test_the_command_line_makes_a_key_and_a_manifest(installer, tmp_path):
    key = tmp_path / "cli.key"
    out = tmp_path / "latest.json"
    assert um.main(["keygen", str(key)]) == 0
    assert um.main(["sign", "--installer", str(installer), "--version", "1.3.0", "--url", URL,
                    "--notes", "메모", "--key", str(key), "--out", str(out)]) == 0
    public = bytes(nacl.signing.SigningKey(um.load_private_key(key)).verify_key)
    assert parse_manifest(out.read_bytes(), public).version == "1.3.0"


def test_the_embedded_public_key_is_a_valid_ed25519_key():
    """The key the app trusts: 64 hex characters that form a real Ed25519 public key."""
    hex_key = update_config.UPDATE_PUBLIC_KEY_HEX
    assert len(hex_key) == 64
    nacl.signing.VerifyKey(bytes.fromhex(hex_key))
