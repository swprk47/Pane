import json
from PySide6.QtCore import QSettings

class AppSettings:
    """
    Persistent application settings manager for GlassPlayer.
    Tracks recent files, resume playback positions, and user preferences.
    """
    def __init__(self):
        self.settings = QSettings("GlassPlayer", "AppSettings")

    def get_resume_position(self, file_path: str) -> float:
        """Get last playback position in seconds for a specific file."""
        positions = self._get_dict("resume_positions")
        return float(positions.get(file_path, 0.0))

    def save_resume_position(self, file_path: str, position: float):
        """Save playback position in seconds."""
        if not file_path or position < 3.0:  # Don't save if near the start
            return
        positions = self._get_dict("resume_positions")
        positions[file_path] = round(position, 2)
        # Limit stored file positions to last 50
        if len(positions) > 50:
            oldest_key = next(iter(positions))
            del positions[oldest_key]
        self._set_dict("resume_positions", positions)

    def add_recent_file(self, file_path: str):
        """Add file path to recent files list (max 10)."""
        recent = self.get_recent_files()
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        recent = recent[:10]
        self.settings.setValue("recent_files", json.dumps(recent))

    def get_recent_files(self) -> list:
        raw = self.settings.value("recent_files", "[]")
        try:
            return json.loads(raw)
        except Exception:
            return []

    def get_volume(self) -> float:
        return float(self.settings.value("last_volume", 100.0))

    def save_volume(self, volume: float):
        self.settings.setValue("last_volume", volume)

    def _get_dict(self, key: str) -> dict:
        raw = self.settings.value(key, "{}")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _set_dict(self, key: str, val: dict):
        self.settings.setValue(key, json.dumps(val))
