"""Seek-bar thumbnails: the box maths, the cache (Task 2) and the provider with its hidden mpv (Task 3)."""
import pytest
from PySide6.QtGui import QImage

from core import thumbnails
from core.thumbnails import ThumbnailCache, ThumbnailProvider, bucket_of, thumbnail_box


# --- box, bucket, cache (Task 2) ----------------------------------------------------------------

@pytest.mark.parametrize("aspect,expected", [
    (16 / 9, (160, 90)), (1.0, (90, 90)), (9 / 16, (90, 90)), (21 / 9, (160, 90)), (4 / 3, (120, 90)),
    (0, (160, 90)), (-1, (160, 90)), (float("nan"), (160, 90)),
])
def test_thumbnail_box_clamps_the_width(aspect, expected):
    assert thumbnail_box(aspect) == expected


@pytest.mark.parametrize("sec,b", [(0, 0), (1.99, 0), (2.0, 1), (3.5, 1), (125.3, 62), (-4, 0)])
def test_bucket_of_is_two_second_steps(sec, b):
    assert bucket_of(sec) == b


def _img():
    return QImage(2, 2, QImage.Format_RGB32)


def test_the_cache_keeps_the_most_recently_used_sixty():
    c = ThumbnailCache(limit=3)
    for i in range(3):
        c.put(("f", i), _img())
    assert c.get(("f", 0)) is not None                      # 0 is now the newest
    c.put(("f", 3), _img())
    assert c.get(("f", 1)) is None and c.get(("f", 0)) is not None and len(c) == 3
    c.clear()
    assert len(c) == 0


# --- the provider (Task 3) ------------------------------------------------------------------------
# sample.mp4 has ONE keyframe: tests that need different pictures use exact=True.

def test_a_request_returns_a_picture_of_the_right_size(qapp, sample_video, pump):
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append((b, img)))
    p.set_file(sample_video)
    p.request(sample_video, 1.5)
    assert pump(lambda: got, timeout=10)
    b, img = got[0]
    assert b == 0 and (img.width(), img.height()) == (320, 180) and not img.isNull()
    p.shutdown()


def test_different_times_give_different_pictures(qapp, sample_video, pump):
    p = ThumbnailProvider(exact=True)
    got = {}
    p.thumbnail_ready.connect(lambda path, b, img: got.__setitem__(b, img))
    p.set_file(sample_video)
    p.request(sample_video, 0.2)
    p.request(sample_video, 2.8)
    assert pump(lambda: 1 in got, timeout=10)
    p.request(sample_video, 0.2)                                       # bucket 0 again (it may have been dropped as stale)
    assert pump(lambda: 0 in got, timeout=10) and got[0] != got[1]
    p.shutdown()


def test_the_same_two_second_bucket_is_made_once_and_then_served_from_the_cache(qapp, sample_video, pump, monkeypatch):
    p = ThumbnailProvider(exact=True)
    made, got = [], []
    real = p._grab
    monkeypatch.setattr(p, "_grab", lambda sec: made.append(sec) or real(sec))
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 1.1)
    assert pump(lambda: got, timeout=10)
    p.request(sample_video, 1.9)                                       # same bucket: answered synchronously from the cache
    assert got == [0, 0] and len(made) == 1
    p.shutdown()


def test_only_the_newest_of_several_quick_requests_is_made(qapp, sample_video, pump, monkeypatch):
    p = ThumbnailProvider(exact=True)
    made, got = [], []
    real = p._grab
    monkeypatch.setattr(p, "_grab", lambda sec: made.append(sec) or real(sec))
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    for sec in (0.1, 0.9, 2.1, 2.9):                                   # buckets 0, 0, 1, 1: the pointer sweeps on
        p.request(sample_video, sec)
    assert pump(lambda: 1 in got, timeout=10)
    assert len(made) <= 2 and 2.9 in made, "the newest request is made; at most the first one was already running"
    p.shutdown()


def test_nothing_is_created_while_thumbnails_are_off(qapp, sample_video, monkeypatch):
    created = []
    monkeypatch.setattr(thumbnails.mpv, "MPV", lambda **kw: created.append(kw))
    p = ThumbnailProvider()
    p.set_enabled(False)
    p.set_file(sample_video)
    p.request(sample_video, 1.0)
    assert created == [] and p.has_instance is False
    p.shutdown()


def test_the_instance_closes_after_ten_idle_seconds_and_returns_on_demand(qapp, sample_video, pump):
    now = [100.0]
    p = ThumbnailProvider(exact=True, clock=lambda: now[0])
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 0.2)
    assert pump(lambda: got, timeout=10) and p.has_instance
    now[0] += 9.9
    p._tick_idle()
    assert p.has_instance
    now[0] += 0.2
    p._tick_idle()
    assert not p.has_instance
    p.request(sample_video, 2.5)
    assert pump(lambda: 1 in got, timeout=10) and p.has_instance
    p.shutdown()


def test_a_new_file_clears_the_cache_and_drops_a_picture_still_being_made(qapp, sample_video, pump):
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append((path, b)))
    p.set_file(sample_video)
    p.request(sample_video, 1.0)
    p.set_file(None)                                                   # the video was closed before the picture arrived
    pump(None, timeout=1.5)
    assert got == [] and len(p._cache) == 0
    p.shutdown()


def test_a_file_that_mpv_cannot_open_gives_no_picture_no_hang_and_one_log_line(qapp, tmp_path, sample_video, pump, capsys):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video")
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(path))
    p.set_file(str(bad))
    p.request(str(bad), 1.0)
    p.request(str(bad), 5.0)
    pump(None, timeout=3)
    assert got == [] and capsys.readouterr().out.count("[thumbnails]") == 1
    p.set_file(sample_video)                                           # still alive for a good file afterwards
    p.request(sample_video, 1.0)
    assert pump(lambda: got, timeout=10) and got == [sample_video]
    p.shutdown()


def test_shutdown_while_a_request_runs_returns_quickly_and_the_mpv_is_really_closed(qapp, sample_video, monkeypatch):
    import time
    p = ThumbnailProvider(exact=True)
    real = p._shoot
    monkeypatch.setattr(p, "_shoot", lambda sec: (time.sleep(1.6), real(sec))[1])   # outlasts shutdown's one second
    p.set_file(sample_video)
    p.request(sample_video, 1.0)
    time.sleep(0.4)                                                    # the worker is inside the mpv
    t0 = time.time()
    p.shutdown()
    assert time.time() - t0 < 3 and p.has_instance is False
    p._worker.join(10)
    assert not p._worker.is_alive() and p._mpv is None, "the worker closed the mpv when it came out"


def test_a_slow_step_does_not_disable_thumbnails_for_the_file(qapp, sample_video, pump, monkeypatch):
    """A timeout (a slow disk, a missed event) is not "this file has no pictures": the next hover must work."""
    p = ThumbnailProvider(exact=True)
    real, calls, got = p._shoot, [], []

    def flaky(sec):
        calls.append(sec)
        if len(calls) == 1:
            raise TimeoutError("took too long")
        return real(sec)

    monkeypatch.setattr(p, "_shoot", flaky)
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 0.2)
    pump(None, timeout=1.0)
    assert got == [] and sample_video not in p._no_picture
    p.request(sample_video, 2.5)
    assert pump(lambda: 1 in got, timeout=10)
    p.shutdown()


def test_the_worker_is_a_daemon_thread_so_it_can_never_hold_the_process_open(qapp, sample_video, pump):
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 1.0)
    assert p._worker.daemon is True
    assert pump(lambda: got, timeout=10)
    p.shutdown()


# --- robustness (cleanup, stage B) --------------------------------------------------------------------

def test_an_unexpected_error_in_the_worker_does_not_stop_thumbnails_for_the_session(qapp, sample_video, pump, monkeypatch):
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    real_put, calls = p._cache.put, []

    def flaky_put(key, image):
        calls.append(key)
        if len(calls) == 1:
            raise RuntimeError("surprise")
        real_put(key, image)

    monkeypatch.setattr(p._cache, "put", flaky_put)
    p.set_file(sample_video)
    p.request(sample_video, 0.2)
    pump(None, timeout=1.0)
    assert got == []
    p.request(sample_video, 2.5)                                        # the worker must still be there for this one
    assert pump(lambda: 1 in got, timeout=10)
    p.shutdown()


def test_a_close_asked_while_the_mpv_is_being_opened_is_not_lost(qapp, sample_video, monkeypatch):
    p = ThumbnailProvider(exact=True)
    real_open = p._open

    def open_with_a_close_arriving(path):
        p._close_pending = True                                         # the GUI asked for a close at this very moment
        real_open(path)

    monkeypatch.setattr(p, "_open", open_with_a_close_arriving)
    p.set_file(sample_video)
    p._grab(1.0)
    assert p._mpv is None, "the close that was asked for must still happen"
    p.shutdown()


def test_a_screenshot_in_an_unexpected_format_is_refused_instead_of_given_wrong_colours():
    from core.thumbnails import image_from_shot
    ok = image_from_shot({"w": 4, "h": 2, "stride": 16, "format": "bgr0", "data": bytes(32)})
    assert (ok.width(), ok.height()) == (4, 2)
    for bad in ({"w": 4, "h": 2, "stride": 16, "format": "rgba", "data": bytes(32)},
                {"w": 4, "h": 2, "stride": 16, "format": "bgr0", "data": bytes(10)},          # shorter than stride x height
                {"w": 0, "h": 2, "stride": 16, "format": "bgr0", "data": bytes(32)}):
        with pytest.raises(ValueError):
            image_from_shot(bad)


# --- an audio file with cover art (cleanup, stage D) -----------------------------------------------------

def make_mp3_with_cover(path):
    """A tiny MP3 (about 1 s of silence) with a PNG cover in an ID3v2 APIC frame. Opened normally mpv lists the cover as a
    video track flagged albumart; the second mpv opens files with the sound off (aid=no), and then mpv finds nothing to
    play in such a file at all: either way no seek-bar picture may come out of a song."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    cover = QImage(32, 32, QImage.Format_RGB32)
    cover.fill(0xFFC81E1E)
    raw = QByteArray()
    buf = QBuffer(raw)
    buf.open(QIODevice.WriteOnly)
    cover.save(buf, "PNG")
    apic = b"\x00" + b"image/png\x00" + b"\x03" + b"\x00" + bytes(raw)
    frame = b"APIC" + len(apic).to_bytes(4, "big") + b"\x00\x00" + apic
    n = len(frame)
    tag = b"ID3" + b"\x03\x00\x00" + bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F]) + frame
    path.write_bytes(tag + (bytes([0xFF, 0xFB, 0x90, 0x04]) + bytes(413)) * 40)      # 40 MPEG frames of 417 bytes


def test_an_audio_file_with_cover_art_gets_no_picture_and_one_log_line(qapp, tmp_path, pump, capsys):
    song = tmp_path / "song.mp3"
    make_mp3_with_cover(song)
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(path))
    p.set_file(str(song))
    p.request(str(song), 0.3)
    pump(None, timeout=3)
    assert got == [], "no seek-bar picture for a song, whatever its cover looks like"
    out = capsys.readouterr().out
    assert str(song) in p._no_picture and out.count("[thumbnails]") == 1
    assert "no video track" in out, "refused when the file is opened, not after a failed screenshot"
    assert p._mpv is None, "and the second mpv is not kept for a song"
    p.shutdown()


# --- the 4K 60 fps budget (cleanup, stage A) ------------------------------------------------------------------

def test_moving_inside_the_step_being_made_does_not_make_it_twice(qapp, sample_video, pump, monkeypatch):
    import threading
    p = ThumbnailProvider(exact=True)
    started, release = threading.Event(), threading.Event()
    made, got = [], []
    real = p._grab

    def slow_grab(sec):
        made.append(sec)
        started.set()
        release.wait(5)
        return real(sec)

    monkeypatch.setattr(p, "_grab", slow_grab)
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 1.1)
    assert started.wait(5)                                              # bucket 0 is being made
    p.request(sample_video, 1.5)                                        # the pointer moves on inside the same 2 s step
    p.request(sample_video, 1.9)
    release.set()
    assert pump(lambda: got, timeout=10)
    pump(None, timeout=0.6)
    assert made == [1.1], "the step was made once, not once per pointer move"
    assert got == [0], "and its picture was delivered once"
    p.shutdown()


def test_closing_an_idle_instance_does_not_block_the_gui_thread(qapp, sample_video, pump):
    import time
    now = [100.0]
    p = ThumbnailProvider(exact=True, clock=lambda: now[0])
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 0.2)
    assert pump(lambda: got, timeout=10) and p.has_instance
    real_terminate = p._mpv.terminate
    p._mpv.terminate = lambda: (time.sleep(0.6), real_terminate())      # a slow shutdown of the second mpv
    now[0] += 11.0
    t0 = time.perf_counter()
    p._tick_idle()
    assert time.perf_counter() - t0 < 0.2, "the GUI thread (which also draws the video) must not wait for it"
    assert p.has_instance is False
    assert pump(lambda: p._mpv is None, timeout=5), "it is closed in the background"
    p.shutdown()


def test_a_request_right_after_a_close_gets_a_fresh_instance_and_a_picture(qapp, sample_video, pump):
    p = ThumbnailProvider(exact=True)
    got = []
    p.thumbnail_ready.connect(lambda path, b, img: got.append(b))
    p.set_file(sample_video)
    p.request(sample_video, 0.2)
    assert pump(lambda: got, timeout=10)
    p.set_file(sample_video)                                            # the video was opened again: a close is asked ...
    p.request(sample_video, 2.5)                                        # ... and a picture is wanted at once
    assert pump(lambda: 1 in got, timeout=10), "not silently dropped because the old instance was still closing"
    p.shutdown()


def test_extra_options_for_the_second_mpv_reach_it(qapp, sample_video, monkeypatch):
    seen = []
    real_mpv = thumbnails.mpv.MPV

    class Spy(real_mpv):                                                # (a subclass: python-mpv looks itself up by name)
        def __init__(self, **kw):
            seen.append(dict(kw))
            super().__init__(**kw)

    monkeypatch.setattr(thumbnails.mpv, "MPV", Spy)
    monkeypatch.setattr(ThumbnailProvider, "EXTRA_OPTIONS", {"cache": "no", "vd_lavc_threads": 2})
    p = ThumbnailProvider(exact=True)
    p.set_file(sample_video)
    assert p._grab(1.0) is not None
    assert seen and seen[0]["cache"] == "no" and seen[0]["vd_lavc_threads"] == 2 and seen[0]["vo"] == "null"
    p.shutdown()
