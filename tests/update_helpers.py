"""Shared test helpers for the update tests: a signed manifest, and a real HTTP server on 127.0.0.1."""
import base64
import hashlib
import http.server
import json
import threading

import nacl.signing
import pytest

from core.updater import Manifest

GOOD = {"version": "1.3.0", "url": "https://example.com/Pane-1.3.0-setup.exe", "sha256": "a" * 64, "size": 123456, "notes": "새 기능"}


def signed(payload, key=None):
    """(raw manifest bytes, public key bytes) with the payload signed by `key` (a fresh key by default)."""
    key = key or nacl.signing.SigningKey.generate()
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    signature = base64.b64encode(key.sign(text.encode("utf-8")).signature).decode("ascii")
    return json.dumps({"payload": text, "signature": signature}).encode("utf-8"), bytes(key.verify_key)


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
