"""The update logic: versions, the signed manifest, the verified download, the installer launch."""
import base64
import json

import pytest

from core.updater import Manifest, ManifestError, is_newer, parse_manifest, parse_version, verify_signature

import nacl.signing


# --- versions ---------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [("1.3.0", (1, 3, 0)), ("v1.3", (1, 3, 0)), ("1.2.10", (1, 2, 10)), (" 2.0.1 ", (2, 0, 1))])
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize("text", ["abc", "", "1.2.3.4", "1..2", "-1.0.0", "1.x.0"])
def test_parse_version_rejects_what_is_not_a_version(text):
    with pytest.raises(ValueError):
        parse_version(text)


@pytest.mark.parametrize("candidate,current,expected", [
    ("1.3.0", "1.2.0", True), ("1.2.10", "1.2.9", True), ("1.2.0", "1.2.0", False),
    ("1.1.9", "1.2.0", False), ("v2.0", "1.9.9", True),
])
def test_is_newer(candidate, current, expected):
    assert is_newer(candidate, current) is expected


# --- the signed manifest --------------------------------------------------------

GOOD = {"version": "1.3.0", "url": "https://example.com/Pane-1.3.0-setup.exe", "sha256": "a" * 64, "size": 123456, "notes": "새 기능"}


def signed(payload, key=None):
    """(raw manifest bytes, public key bytes) with the payload signed by `key` (a fresh key by default)."""
    key = key or nacl.signing.SigningKey.generate()
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    signature = base64.b64encode(key.sign(text.encode("utf-8")).signature).decode("ascii")
    return json.dumps({"payload": text, "signature": signature}).encode("utf-8"), bytes(key.verify_key)


def test_a_correctly_signed_manifest_parses():
    raw, public = signed(GOOD)
    m = parse_manifest(raw, public)
    assert m == Manifest(version="1.3.0", url=GOOD["url"], sha256="a" * 64, size=123456, notes="새 기능")


def test_the_notes_are_optional():
    payload = {k: v for k, v in GOOD.items() if k != "notes"}
    raw, public = signed(payload)
    assert parse_manifest(raw, public).notes == ""


def test_a_manifest_signed_by_another_key_is_rejected():
    raw, _ = signed(GOOD)
    other_public = bytes(nacl.signing.SigningKey.generate().verify_key)
    with pytest.raises(ManifestError):
        parse_manifest(raw, other_public)


def test_a_manifest_whose_payload_was_edited_is_rejected():
    raw, public = signed(GOOD)
    envelope = json.loads(raw)
    envelope["payload"] = envelope["payload"].replace("123456", "123457")           # a different size, the old signature
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(envelope).encode("utf-8"), public)


def test_verify_signature_tells_good_from_bad():
    key = nacl.signing.SigningKey.generate()
    sig = key.sign(b"payload").signature
    assert verify_signature(b"payload", sig, bytes(key.verify_key)) is True
    assert verify_signature(b"payload!", sig, bytes(key.verify_key)) is False
    assert verify_signature(b"payload", b"short", bytes(key.verify_key)) is False


@pytest.mark.parametrize("change", [
    {"sha256": None}, {"url": None}, {"size": None}, {"version": None},          # a field missing
    {"size": "123456"}, {"size": 0}, {"size": -5}, {"size": True},               # a wrong size
    {"sha256": "abc"}, {"sha256": "z" * 64},                                     # not 64 hex characters
    {"url": "http://evil.example/Pane.exe"}, {"url": "ftp://example.com/p.exe"}, {"url": "file:///c:/x.exe"},
    {"version": "latest"},
])
def test_missing_or_mistyped_fields_are_rejected_even_when_signed(change):
    payload = dict(GOOD)
    for k, v in change.items():
        if v is None:
            payload.pop(k)
        else:
            payload[k] = v
    raw, public = signed(payload)
    with pytest.raises(ManifestError):
        parse_manifest(raw, public)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/Pane.exe", "http://localhost/Pane.exe", "https://github.com/swprk47/Pane/x.exe"])
def test_https_or_a_local_address_is_accepted(url):
    raw, public = signed({**GOOD, "url": url})
    assert parse_manifest(raw, public).url == url


@pytest.mark.parametrize("raw", [b"<html>login</html>", b"", b"{}", b'{"payload": 5, "signature": "x"}', b'{"payload": "{}"}', b"[1, 2]", b"\xff\xfe"])
def test_garbage_and_html_are_rejected(raw):
    with pytest.raises(ManifestError):
        parse_manifest(raw, bytes(nacl.signing.SigningKey.generate().verify_key))
