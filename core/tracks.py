"""
Audio / subtitle tracks as the track panel shows them.

`list_tracks(raw, kind)` turns mpv's `track-list` (a list of dicts) into `Track` rows: a name on the left
("한국어", "트랙 4") and a short detail on the right ("AAC · 2ch", "내장 · SRT"). It is pure, so the naming is
unit-testable without a running mpv.
"""
import os
from dataclasses import dataclass

AUDIO = "audio"
SUB = "sub"

_LANGUAGES = {
    "ko": "한국어", "kor": "한국어",
    "en": "영어", "eng": "영어",
    "ja": "일본어", "jpn": "일본어",
    "zh": "중국어", "zho": "중국어", "chi": "중국어",
    "fr": "프랑스어", "fra": "프랑스어", "fre": "프랑스어",
    "de": "독일어", "deu": "독일어", "ger": "독일어",
    "es": "스페인어", "spa": "스페인어",
    "ru": "러시아어", "rus": "러시아어",
    "it": "이탈리아어", "ita": "이탈리아어",
    "pt": "포르투갈어", "por": "포르투갈어",
}

_AUDIO_CODECS = {"eac3": "E-AC3", "truehd": "TrueHD", "mp3": "MP3", "pcm_s16le": "PCM", "pcm_s24le": "PCM"}
_SUB_CODECS = {
    "subrip": "SRT", "srt": "SRT", "ass": "ASS", "ssa": "SSA", "webvtt": "VTT", "mov_text": "TXT",
    "sami": "SMI", "hdmv_pgs_subtitle": "PGS", "dvd_subtitle": "DVD", "dvb_subtitle": "DVB",
    "subviewer": "SUB", "microdvd": "SUB", "text": "TXT",
}
_CHANNELS = {1: "1ch", 2: "2ch", 6: "5.1", 8: "7.1"}


@dataclass(frozen=True)
class Track:
    id: int
    kind: str            # AUDIO or SUB
    name: str
    detail: str
    selected: bool
    external: bool = False


def language_name(code) -> str:
    """'kor' / 'ko' -> '한국어'. Unknown codes show as they are; 'und' / empty -> ''."""
    code = (code or "").strip().lower()
    if not code or code == "und":
        return ""
    return _LANGUAGES.get(code, _LANGUAGES.get(code.split("-")[0], code))


def _audio_detail(t: dict) -> str:
    codec = str(t.get("codec") or "").lower()
    parts = [_AUDIO_CODECS.get(codec, codec.upper())] if codec else []
    channels = t.get("demux-channel-count") or t.get("audio-channels")
    if channels:
        parts.append(_CHANNELS.get(int(channels), f"{int(channels)}ch"))
    return " · ".join(p for p in parts if p)


def _sub_detail(t: dict) -> str:
    codec = str(t.get("codec") or "").lower()
    parts = ["외부" if t.get("external") else "내장"]
    if codec:
        parts.append(_SUB_CODECS.get(codec, codec.upper()))
    return " · ".join(parts)


def _name(t: dict, kind: str, number: int) -> str:
    external = bool(t.get("external"))
    if kind == SUB and external:
        # Two external files in the same language would look identical, so show the file.
        path = t.get("external-filename") or ""
        file_name = os.path.basename(path)
        base = os.path.splitext(file_name)[0]
        title = t.get("title")
        if title == file_name:                  # mpv titles a loose file with its own name
            title = ""
        return title or base or language_name(t.get("lang")) or f"트랙 {number}"
    return language_name(t.get("lang")) or t.get("title") or f"트랙 {number}"


def list_tracks(raw, kind: str) -> list:
    """The `kind` ('audio' or 'sub') tracks of mpv's track-list, in order."""
    tracks = []
    for t in raw or []:
        if t.get("type") != kind:
            continue
        number = len(tracks) + 1
        detail = _audio_detail(t) if kind == AUDIO else _sub_detail(t)
        tracks.append(Track(
            id=int(t["id"]), kind=kind, name=_name(t, kind, number), detail=detail,
            selected=bool(t.get("selected")), external=bool(t.get("external")),
        ))
    return tracks


def format_delay(seconds, unit="초") -> str:
    """0.3 -> '+0.3초', -0.1 -> '-0.1초', 0 -> '0.0초'."""
    value = round(float(seconds or 0.0), 2)
    if abs(value) < 0.005:
        return f"0.0{unit}"
    return f"{value:+.1f}{unit}" if abs(value * 10 - round(value * 10)) < 1e-6 else f"{value:+.2f}{unit}"
