"""
Reads codec / decoder / stream details from a running mpv and turns them into
display rows for the media-info panel (and plain text for copying).

`read_media_info(mpv)` returns raw values (None when mpv does not know them yet);
`describe(info)` formats them as [(section, [(label, value), ...]), ...].
Both are pure apart from reading mpv, so the formatting is unit-testable.
"""

DASH = "—"

# key -> mpv property
_PROPERTIES = {
    # video
    "video_format": "video-format",
    "video_codec": "video-codec",
    "video_profile": "current-tracks/video/codec-profile",
    "width": "video-params/w",
    "height": "video-params/h",
    "pixel_format": "video-params/pixelformat",
    "colormatrix": "video-params/colormatrix",
    "colorlevels": "video-params/colorlevels",
    "container_fps": "container-fps",
    "actual_fps": "estimated-vf-fps",
    "video_bitrate": "video-bitrate",
    "hwdec": "hwdec-current",
    # audio
    "audio_format": "audio-codec-name",
    "audio_codec": "audio-codec",
    "audio_samplerate": "audio-params/samplerate",
    "audio_channels": "audio-params/hr-channels",
    "audio_bitrate": "audio-bitrate",
    # file
    "path": "path",
    "container": "file-format",
    "file_size": "file-size",
    "duration": "duration",
    # playback
    "speed": "speed",
    "vo": "current-vo",
    "dropped_vo": "frame-drop-count",
    "dropped_decoder": "decoder-frame-drop-count",
}


def read_media_info(mpv) -> dict:
    """Snapshot of everything we show. Unavailable properties come back as None."""
    info = {}
    for key, prop in _PROPERTIES.items():
        try:
            info[key] = mpv._get_property(prop)
        except Exception:
            info[key] = None
    return info


# --- formatting helpers ----------------------------------------------------

def format_bitrate(bps) -> str:
    if not bps:
        return DASH
    bps = float(bps)
    return f"{bps / 1e6:.1f} Mbps" if bps >= 1e6 else f"{bps / 1e3:.0f} kbps"


def format_bytes(n) -> str:
    if not n:
        return DASH
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def format_duration(seconds) -> str:
    if not seconds:
        return DASH
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_clock(seconds) -> str:
    """A position as a clock: 2:36, or 1:02:45 from one hour on (unlike format_duration, 0 is "0:00", not a dash)."""
    s = int(max(0, seconds or 0))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_fps(fps) -> str:
    return f"{float(fps):.2f} fps" if fps else DASH


def describe_decoder(hwdec) -> str:
    """Hardware or software decoding, in plain words."""
    if not hwdec or hwdec == "no":
        return "CPU (소프트웨어)"
    copy = " (프레임 복사)" if str(hwdec).endswith("-copy") else ""
    return f"GPU · {hwdec}{copy}"


def _video_codec_text(info) -> str:
    short = (info.get("video_format") or "").upper()
    long_ = info.get("video_codec")
    if not short and not long_:
        return DASH
    profile = info.get("video_profile")
    head = short + (f" · {profile}" if profile else "")
    return head or long_


def describe(info: dict) -> list:
    """[(section title, [(label, value), ...]), ...] in display order."""
    has_video = bool(info.get("video_format") or info.get("video_codec"))
    sections = []

    w, h = info.get("width"), info.get("height")
    video = [
        ("코덱", _video_codec_text(info)),
        ("상세", info.get("video_codec") or DASH),
        ("디코더", describe_decoder(info.get("hwdec")) if has_video else DASH),
        ("해상도", f"{w} × {h}" if w and h else DASH),
        ("프레임레이트", format_fps(info.get("container_fps"))),
        ("비트레이트", format_bitrate(info.get("video_bitrate"))),
        ("픽셀 형식", " · ".join(x for x in (info.get("pixel_format"), info.get("colormatrix"), info.get("colorlevels")) if x) or DASH),
    ]
    sections.append(("비디오", video))

    has_audio = bool(info.get("audio_format") or info.get("audio_codec"))
    audio = [("코덱", (info.get("audio_format") or "").upper() or DASH if has_audio else "오디오 없음")]
    if has_audio:
        audio += [
            ("상세", info.get("audio_codec") or DASH),
            ("샘플레이트", f"{int(info['audio_samplerate']) / 1000:g} kHz" if info.get("audio_samplerate") else DASH),
            ("채널", str(info.get("audio_channels") or DASH)),
            ("비트레이트", format_bitrate(info.get("audio_bitrate"))),
        ]
    sections.append(("오디오", audio))

    sections.append(("파일", [
        ("컨테이너", info.get("container") or DASH),
        ("크기", format_bytes(info.get("file_size"))),
        ("길이", format_duration(info.get("duration"))),
    ]))

    dropped = (info.get("dropped_vo") or 0) + (info.get("dropped_decoder") or 0)
    sections.append(("재생", [
        ("배속", f"{float(info['speed']):.2f}x" if info.get("speed") else DASH),
        ("실제 FPS", format_fps(info.get("actual_fps"))),
        ("버려진 프레임", f"{dropped} (출력 {info.get('dropped_vo') or 0} · 디코더 {info.get('dropped_decoder') or 0})"),
        ("출력", info.get("vo") or DASH),
    ]))
    return sections


def to_plain_text(sections: list) -> str:
    lines = []
    for title, rows in sections:
        lines.append(f"[{title}]")
        lines += [f"{label}: {value}" for label, value in rows]
        lines.append("")
    return "\n".join(lines).strip()
