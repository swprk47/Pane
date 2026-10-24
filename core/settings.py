import json
import os
from PySide6.QtCore import QSettings

from core import bookmarks

APP_NAME = "Pane"
LEGACY_APP_NAME = "GlassPlayer"  # name used before the rename


def open_settings(group: str) -> QSettings:
    """Open QSettings(APP_NAME, group); on first use copy over the old
    GlassPlayer values so resume positions, layout and presets survive."""
    new = QSettings(APP_NAME, group)
    if not new.allKeys():
        old = QSettings(LEGACY_APP_NAME, group)
        for key in old.allKeys():
            new.setValue(key, old.value(key))
        new.sync()
    return new

class AppSettings:
    """
    Persistent application settings manager for Pane.
    Tracks recent files, resume playback positions, and user preferences.
    """
    def __init__(self):
        self.settings = open_settings("AppSettings")

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

    # --- what is remembered per video: its speed and its audio / subtitle choice ------------------------------------
    # A video's own values win; a field it has none of falls back to the last values set in the same folder (a lecture
    # series keeps its speed from one week to the next). Streams have no folder.

    MEMORY_VIDEOS, MEMORY_FOLDERS = 100, 30

    @staticmethod
    def _folder_key(file_path: str):
        if not file_path or "://" in file_path:
            return None
        return os.path.normcase(os.path.dirname(os.path.abspath(file_path)))

    @staticmethod
    def _track_memory(value):
        """A remembered track: {"lang": str, "title": str} with at least one of them; None when it is anything else."""
        if not isinstance(value, dict):
            return None
        lang, title = value.get("lang", ""), value.get("title", "")
        if not isinstance(lang, str) or not isinstance(title, str) or not (lang or title):
            return None
        return {"lang": lang, "title": title}

    @classmethod
    def _clean_memory(cls, entry) -> dict:
        """Only the fields that are valid; an entry that is not even a dict is nothing."""
        if not isinstance(entry, dict):
            return {}
        out = {}
        speed = entry.get("speed")
        if isinstance(speed, (int, float)) and not isinstance(speed, bool) and 0 < speed < 100:
            out["speed"] = round(float(speed), 2)
        audio = cls._track_memory(entry.get("audio"))
        if audio:
            out["audio"] = audio
        sub = entry.get("sub")
        if sub == "off":
            out["sub"] = "off"
        elif cls._track_memory(sub):
            out["sub"] = cls._track_memory(sub)
        return out

    def get_playback_memory(self, file_path: str) -> dict:
        """{"speed": float, "audio": {...}, "sub": {...} or "off"}: only the fields known for this video or its folder."""
        mine = self._clean_memory(self._get_dict("playback_memory").get(file_path))
        key = self._folder_key(file_path)
        folder = self._clean_memory(self._get_dict("folder_memory").get(key)) if key else {}
        return {**folder, **mine}

    def save_playback_memory(self, file_path: str, update_folder: bool = True, **fields) -> None:
        """Remember `speed`, `audio`, `sub` for this video, and (unless update_folder is False: a deliberate exception such
        as resetting the speed of one hard video) as the folder's last values."""
        clean = self._clean_memory({k: v for k, v in fields.items() if k in ("speed", "audio", "sub")})
        if not file_path or not clean:
            return
        self._remember("playback_memory", file_path, clean, self.MEMORY_VIDEOS)
        key = self._folder_key(file_path)
        if update_folder and key:
            self._remember("folder_memory", key, clean, self.MEMORY_FOLDERS)

    def _remember(self, store: str, key: str, fields: dict, limit: int) -> None:
        data = self._get_dict(store)
        entry = self._clean_memory(data.pop(key, None))
        entry.update(fields)
        data[key] = entry                                  # (last in the order = most recently set)
        while len(data) > limit:
            del data[next(iter(data))]
        self._set_dict(store, data)

    # --- bookmarks: places of a video marked to look at again (see core/bookmarks.py) --------------------------------

    BOOKMARK_VIDEOS = 200

    def get_bookmarks(self, file_path: str) -> list:
        """The video's bookmarks, [{"t": seconds, "name": str}] sorted by time; anything broken in the store is ignored."""
        data = self._get_dict("bookmarks")
        return bookmarks.clean(data.get(file_path)) if isinstance(data, dict) else []

    def save_bookmarks(self, file_path: str, items: list) -> None:
        """Remember the video's bookmarks (an empty list forgets the video); it becomes the most recently changed video."""
        if not file_path:
            return
        data = self._get_dict("bookmarks")
        if not isinstance(data, dict):
            data = {}
        data.pop(file_path, None)
        cleaned = bookmarks.clean(items)
        if cleaned:
            data[file_path] = cleaned
        while len(data) > self.BOOKMARK_VIDEOS:
            del data[next(iter(data))]
        self._set_dict("bookmarks", data)

    def get_chapters_visible(self) -> bool:
        """Chapter starts as gaps of the seek bar, and their names in the hover pill (on by default)."""
        return str(self.settings.value("chapters_visible", True)).lower() not in ("false", "0")

    def set_chapters_visible(self, enabled: bool) -> None:
        self.settings.setValue("chapters_visible", bool(enabled))

    def get_duration(self, file_path: str) -> float:
        """Length in seconds remembered for a file (0.0 when never seen): the start screen's progress line."""
        return float(self._get_dict("durations").get(file_path, 0.0))

    def save_duration(self, file_path: str, duration: float):
        if not file_path or duration <= 0:
            return
        durations = self._get_dict("durations")
        if durations.get(file_path) == round(duration, 2):
            return
        durations.pop(file_path, None)
        durations[file_path] = round(duration, 2)
        while len(durations) > 50:
            del durations[next(iter(durations))]
        self._set_dict("durations", durations)

    def add_recent_file(self, file_path: str):
        """Add file path to recent files list (max 10)."""
        recent = self.get_recent_files()
        if file_path in recent:
            recent.remove(file_path)
        recent.insert(0, file_path)
        recent = recent[:10]
        self.settings.setValue("recent_files", json.dumps(recent))

    def remove_recent_file(self, file_path: str):
        """Forget a file (one that turned out not to open must not be offered for resuming)."""
        recent = [p for p in self.get_recent_files() if p != file_path]
        self.settings.setValue("recent_files", json.dumps(recent))

    def get_recent_files(self) -> list:
        raw = self.settings.value("recent_files", "[]")
        try:
            return json.loads(raw)
        except Exception:
            return []

    def get_auto_next(self) -> bool:
        """Play the next video of the folder when one ends (on by default)."""
        return str(self.settings.value("auto_next", True)).lower() not in ("false", "0")

    def set_auto_next(self, enabled: bool):
        self.settings.setValue("auto_next", bool(enabled))

    def get_hwdec_enabled(self) -> bool:
        """GPU video decoding (on by default; the escape hatch for PCs where it misbehaves)."""
        return str(self.settings.value("hwdec_enabled", True)).lower() not in ("false", "0")

    def set_hwdec_enabled(self, enabled: bool):
        self.settings.setValue("hwdec_enabled", bool(enabled))

    def get_thumbnails_enabled(self) -> bool:
        """The picture above the time when the pointer is over the seek bar (on by default)."""
        return str(self.settings.value("thumbnails_enabled", True)).lower() not in ("false", "0")

    def set_thumbnails_enabled(self, enabled: bool):
        self.settings.setValue("thumbnails_enabled", bool(enabled))

    def get_thumbnails_on_stop(self) -> bool:
        """Show that picture only after the pointer rests (off by default: it follows the pointer)."""
        return str(self.settings.value("thumbnails_on_stop", False)).lower() in ("true", "1")

    def set_thumbnails_on_stop(self, enabled: bool):
        self.settings.setValue("thumbnails_on_stop", bool(enabled))

    def get_lecture_audio(self) -> bool:
        """The "lecture voice" audio preset (off by default)."""
        return str(self.settings.value("lecture_audio", False)).lower() in ("true", "1")

    def set_lecture_audio(self, enabled: bool):
        self.settings.setValue("lecture_audio", bool(enabled))

    def get_update_check_enabled(self) -> bool:
        """The automatic daily check for a newer Pane (on by default; the "check now" button always works)."""
        return str(self.settings.value("update_check_enabled", True)).lower() not in ("false", "0")

    def set_update_check_enabled(self, enabled: bool):
        self.settings.setValue("update_check_enabled", bool(enabled))

    def get_last_update_check(self) -> float:
        """When the last successful check happened (seconds since the epoch; 0 = never)."""
        try:
            return float(self.settings.value("last_update_check", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def set_last_update_check(self, when: float):
        self.settings.setValue("last_update_check", float(when))

    def get_update_offer_version(self) -> str:
        """The newer version the last check found and that is not installed yet ("" = none): shown again at the next
        start, which also checks at once, until it is installed or dismissed."""
        return str(self.settings.value("update_offer_version", ""))

    def set_update_offer_version(self, version: str):
        self.settings.setValue("update_offer_version", str(version))

    def get_update_dismissed_version(self) -> str:
        """The version whose notice the user closed with the X ("" = none); a newer version is announced again."""
        return str(self.settings.value("update_dismissed_version", ""))

    def set_update_dismissed_version(self, version: str):
        self.settings.setValue("update_dismissed_version", str(version))

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
