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


# --- fetching the manifest and downloading the installer (a real HTTP server on 127.0.0.1) ----------

import hashlib
import http.server
import threading

from core.updater import UpdateError, download_installer, fetch_manifest


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.server.routes.get(self.path)
        self.server.requests.append(self.path)
        if route is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body, declared = route
        self.send_response(200)
        self.send_header("Content-Length", str(len(body) if declared is None else declared))
        self.end_headers()
        self.wfile.write(body)                       # (declared bigger than the body: the connection just ends early)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.routes = {}
    srv.requests = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield srv
    srv.shutdown()
    srv.server_close()


INSTALLER = b"MZ-pretend-installer-bytes-" * 5000


def manifest_for(server, body=INSTALLER, **over):
    fields = dict(version="1.3.0", url=server.base + "/Pane-1.3.0-setup.exe", sha256=hashlib.sha256(body).hexdigest(),
                  size=len(body), notes="")
    fields.update(over)
    return Manifest(**fields)


def test_fetch_manifest_from_a_server(server):
    raw, public = signed(GOOD)
    server.routes["/latest.json"] = (raw, None)
    assert fetch_manifest(server.base + "/latest.json", public).version == "1.3.0"


def test_fetch_manifest_with_an_html_login_page_raises_manifest_error(server):
    server.routes["/latest.json"] = (b"<html><body>Sign in to the hotel wifi</body></html>", None)
    with pytest.raises(ManifestError):
        fetch_manifest(server.base + "/latest.json", bytes(nacl.signing.SigningKey.generate().verify_key))


def test_fetch_manifest_refuses_a_huge_answer(server):
    server.routes["/latest.json"] = (b"x" * 200_000, None)
    with pytest.raises(ManifestError):
        fetch_manifest(server.base + "/latest.json", bytes(nacl.signing.SigningKey.generate().verify_key))


def test_fetch_manifest_404_raises_update_error(server):
    with pytest.raises(UpdateError):
        fetch_manifest(server.base + "/missing.json", b"\0" * 32)


def test_fetch_manifest_connection_refused_raises_update_error():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                    # (nobody listens here once the socket is closed)
    with pytest.raises(UpdateError):
        fetch_manifest(f"http://127.0.0.1:{port}/latest.json", b"\0" * 32, timeout=2.0)


def test_download_writes_the_file_and_reports_progress(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    seen = []
    path = download_installer(manifest_for(server), tmp_path / "dl", progress=lambda done, total: seen.append((done, total)))
    assert path == tmp_path / "dl" / "Pane-1.3.0-setup.exe"
    assert path.read_bytes() == INSTALLER
    assert seen and seen[-1] == (len(INSTALLER), len(INSTALLER))
    assert [d for d, _ in seen] == sorted(d for d, _ in seen), "progress only grows"


def test_a_file_with_the_wrong_hash_is_deleted_and_raises(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    wrong = manifest_for(server, sha256="0" * 64)
    with pytest.raises(UpdateError):
        download_installer(wrong, tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == [], "no partial or rejected file is left"


def test_a_truncated_download_is_deleted_and_raises(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER[:1000], len(INSTALLER))
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_file_bigger_than_the_manifest_size_is_stopped(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER + b"extra" * 10_000, None)
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_a_404_for_the_installer_leaves_nothing_behind(server, tmp_path):
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert list((tmp_path / "dl").iterdir()) == []


def test_an_earlier_good_download_survives_a_failed_retry(server, tmp_path):
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER, None)
    good = download_installer(manifest_for(server), tmp_path / "dl")
    server.routes["/Pane-1.3.0-setup.exe"] = (INSTALLER[:10], len(INSTALLER))
    with pytest.raises(UpdateError):
        download_installer(manifest_for(server), tmp_path / "dl")
    assert good.read_bytes() == INSTALLER
