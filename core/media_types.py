"""Video file types Pane opens: used by the Open dialog and by the installer's file association."""

VIDEO_EXTENSIONS = (
    "mp4", "mkv", "avi", "mov", "webm", "wmv", "flv", "m4v", "ts", "mpg", "mpeg", "3gp", "ogv",
)


def open_dialog_filter() -> str:
    patterns = " ".join(f"*.{e}" for e in VIDEO_EXTENSIONS)
    return f"Video Files ({patterns});;All Files (*.*)"
