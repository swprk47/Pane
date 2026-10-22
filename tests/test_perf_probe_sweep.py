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
