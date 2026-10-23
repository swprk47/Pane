"""The timed "[exit]" lines the app leaves in pane.log when it is closed: where a slow or stuck exit stopped."""
import re
import subprocess
import sys
from pathlib import Path

from core import exit_trace

ROOT = Path(__file__).resolve().parent.parent


def test_stages_print_the_time_since_the_previous_one(capsys, monkeypatch):
    clock = iter([10.0, 10.5, 12.0])
    monkeypatch.setattr(exit_trace.time, "perf_counter", lambda: next(clock))
    exit_trace.begin()
    exit_trace.stage("mpv terminated")
    exit_trace.stage("window closed")
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["[exit] closing", "[exit] mpv terminated (0.50 s)", "[exit] window closed (1.50 s)"]


def test_closing_the_main_window_leaves_every_stage_in_the_log(qapp, capsys):
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    w.close()
    qapp.processEvents()
    out = capsys.readouterr().out
    for stage in ("[exit] closing", "update check stopped", "thumbnails closed", "video surface released", "mpv terminated"):
        assert stage in out, stage
    assert re.search(r"\[exit\] mpv terminated \(\d+\.\d\d s\)", out)


def test_the_interpreter_leaves_a_last_line_when_it_really_ends():
    script = f"import sys; sys.path.insert(0, {str(ROOT)!r}); from core import exit_trace; exit_trace.install_exit_marker(); print('work')"
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20)
    assert done.stdout.splitlines() == ["work", "[exit] interpreter exiting"]


def test_main_wires_the_trace_in():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "exit_trace.install_exit_marker()" in source and 'exit_trace.mark("event loop ended")' in source
