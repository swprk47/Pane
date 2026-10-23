"""tools/perf_probe.py --sweep: the pure helper that walks the pointer along the seek bar (the measurement itself is manual)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from perf_probe import sweep_positions  # noqa: E402


def test_sweep_positions_go_back_and_forth_inside_the_bar():
    duration, span, margin = 600.0, 800.0, 12.0
    assert sweep_positions(duration, span, margin, 0.0) == (0.0, margin)
    sec, x = sweep_positions(duration, span, margin, 1.0)                 # one bar width per second
    assert (sec, x) == (duration, margin + span)
    assert sweep_positions(duration, span, margin, 2.0) == (0.0, margin)  # and back
    sec, x = sweep_positions(duration, span, margin, 0.5)
    assert (sec, x) == (duration / 2, margin + span / 2)
    for t in (0.0, 0.13, 0.99, 1.4, 1.99, 7.3, 123.456):
        sec, x = sweep_positions(duration, span, margin, t)
        assert 0.0 <= sec <= duration and margin <= x <= margin + span


def test_the_latency_tracker_keeps_cache_hits_out_of_the_latency_numbers():
    """A picture that comes straight from the cache took no time to make: counting it as ~0 ms pulled the median down."""
    from perf_probe import LatencyTracker
    now = [100.0]
    t = LatencyTracker(clock=lambda: now[0])
    t.asked(1)
    now[0] += 0.040
    t.answered(1)                                  # made in 40 ms
    t.asked(2)
    t.answered(2, from_cache=True)                 # served at once from the cache
    t.asked(3)
    now[0] += 0.100
    t.answered(3)                                  # made in 100 ms
    t.answered(99)                                 # never asked: ignored
    assert t.cache_hits == 1 and len(t.latencies_ms) == 2
    assert round(t.median_ms) == 70 and round(t.worst_ms) == 100


def test_a_new_ask_for_a_bucket_replaces_the_older_one():
    """An ask that was dropped for a newer one must not make the later answer look slow (the 8 s ghost of the first run)."""
    from perf_probe import LatencyTracker
    now = [0.0]
    t = LatencyTracker(clock=lambda: now[0])
    t.asked(5)
    now[0] += 8.0
    t.asked(5)
    now[0] += 0.030
    t.answered(5)
    assert round(t.worst_ms) == 30


def test_thumb_options_are_parsed_into_mpv_options():
    from perf_probe import parse_thumb_options
    assert parse_thumb_options("") == {}
    assert parse_thumb_options("cache=no,vd_lavc_threads=2,demuxer_max_bytes=1MiB,hr_seek_demux_threshold=0.5") == {
        "cache": "no", "vd_lavc_threads": 2, "demuxer_max_bytes": "1MiB", "hr_seek_demux_threshold": 0.5}
