"""
A file that could not be opened, in plain words.

mpv reports a failed load as ``end-file`` with reason "error" and a short ``file_error`` ("unrecognized file format",
"loading failed"), and logs the real cause just before ("Permission denied", "No such file or directory",
"moov atom not found"). ``classify`` turns those, plus what we can see on disk, into a title and a hint for the
start screen. Pure functions, so every case is unit-tested.

Not covered: a file that opens but whose codec cannot be decoded. The bundled mpv has 521 decoders (every common
codec) and no file at hand reproduces it, so that case waits for a real report.
"""
import os
from typing import NamedTuple


class FileProblem(NamedTuple):
    kind: str          # missing | empty | denied | unrecognized | unknown
    title: str
    hint: str
    detail: str        # what mpv said, for the diagnostics report


def classify(path: str, file_error: str = "", log_lines=()) -> FileProblem:
    name = os.path.basename(path) or path
    err = (file_error or "").strip()
    logs = " | ".join(str(line).strip() for line in log_lines if str(line).strip())
    low = logs.lower()
    detail = f"{name}: {err or '-'}" + (f" ({logs})" if logs else "")

    if not os.path.exists(path) or "no such file" in low:
        return FileProblem("missing", f"‘{name}’ 파일을 찾을 수 없어요",
                           "파일이 옮겨졌거나 지워졌어요. 연결이 끊긴 드라이브에 있을 수도 있어요.", detail)
    try:
        empty = os.path.getsize(path) == 0
    except OSError:
        empty = False
    if empty:
        return FileProblem("empty", f"‘{name}’ 파일이 비어 있어요",
                           "복사나 다운로드가 중간에 멈췄을 수 있어요.", detail)
    if "permission denied" in low or "access is denied" in low or "used by another process" in low:
        return FileProblem("denied", f"‘{name}’ 파일을 열 수 없어요",
                           "다른 프로그램이 쓰고 있거나 열 권한이 없어요. 그 프로그램을 닫고 다시 시도해 보세요.", detail)
    if "unrecognized file format" in err.lower():
        return FileProblem("unrecognized", f"‘{name}’ 파일을 열 수 없어요",
                           "영상 파일이 아니거나 손상된 것 같아요. 다운로드가 끝나지 않은 파일일 수도 있어요.", detail)
    return FileProblem("unknown", f"‘{name}’ 파일을 열 수 없어요",
                       "이유를 알 수 없어요. 아래 ‘진단 정보 복사’로 내용을 보내 주시면 원인을 찾아볼게요.", detail)
