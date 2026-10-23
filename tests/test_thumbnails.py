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
