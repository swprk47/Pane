"""The manifest address can be redirected for tests (an environment variable); the trusted key never can."""
import importlib

from core import update_config

DEFAULT = "https://github.com/swprk47/Pane/releases/latest/download/latest.json"


def test_the_manifest_address_can_be_overridden_by_the_environment(monkeypatch):
    monkeypatch.setenv("PANE_UPDATE_MANIFEST_URL", "http://127.0.0.1:8765/latest.json")
    try:
        assert importlib.reload(update_config).UPDATE_MANIFEST_URL == "http://127.0.0.1:8765/latest.json"
    finally:
        monkeypatch.delenv("PANE_UPDATE_MANIFEST_URL")
        importlib.reload(update_config)
    assert update_config.UPDATE_MANIFEST_URL == DEFAULT


def test_the_public_key_ignores_the_environment(monkeypatch):
    before = update_config.UPDATE_PUBLIC_KEY_HEX
    monkeypatch.setenv("PANE_UPDATE_PUBLIC_KEY", "00" * 32)
    monkeypatch.setenv("PANE_UPDATE_PUBLIC_KEY_HEX", "00" * 32)
    try:
        assert importlib.reload(update_config).UPDATE_PUBLIC_KEY_HEX == before
    finally:
        monkeypatch.undo()
        importlib.reload(update_config)
