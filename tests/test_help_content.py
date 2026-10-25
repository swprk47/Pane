"""The help's content: the data is well-formed and stays in step with the keys the router handles."""
import re
from pathlib import Path

from ui.help_content import ALL_CHIPS, KEY_GROUPS, MOUSE, TIPS

ROOT = Path(__file__).resolve().parent.parent

KEY_TOKENS = {   # Qt key constant used by KeyRouter -> the chip that shows it in the help
    "Key_Space": "Space", "Key_BracketLeft": "[", "Key_BracketRight": "]", "Key_Backslash": "\\", "Key_Backspace": "Backspace",
    "Key_Left": "←", "Key_Right": "→", "Key_Comma": ",", "Key_Period": ".", "Key_Less": "PageUp", "Key_Greater": "PageDown",
    "Key_PageUp": "PageUp", "Key_PageDown": "PageDown", "Key_Up": "↑", "Key_Down": "↓", "Key_M": "M", "Key_C": "C",
    "Key_Z": "Z", "Key_X": "X", "Key_B": "B", "Key_F": "F", "Key_Return": "Enter", "Key_P": "P", "Key_I": "I",
    "Key_O": "Ctrl+O", "Key_S": "Ctrl+S", "Key_Escape": "Esc", "Key_Question": "?", "Key_Slash": "?",
}


def test_every_group_has_rows_and_no_chip_repeats_inside_a_group():
    assert KEY_GROUPS
    for title, rows in KEY_GROUPS:
        assert title.strip() and rows
        seen = set()
        for chips, text in rows:
            assert len(chips) >= 1 and all(c.strip() for c in chips)
            assert text.strip()
            for chip in chips:
                assert chip not in seen, f"{chip!r} repeats in {title}"
                seen.add(chip)


def test_the_mouse_lines_and_tips_are_not_empty():
    assert len(MOUSE) == 6 and all(g.strip() and d.strip() for g, d in MOUSE)
    assert len(TIPS) == 3 and all(t.strip() for t in TIPS)


def test_every_key_the_router_handles_is_in_the_help():
    source = (ROOT / "ui" / "key_bindings.py").read_text(encoding="utf-8")
    used = set(re.findall(r"Qt\.(Key_\w+)", source))
    assert used <= set(KEY_TOKENS), f"a key the router uses has no help line: {sorted(used - set(KEY_TOKENS))}"
    assert {KEY_TOKENS[k] for k in used} <= ALL_CHIPS


def test_the_extra_chips_of_the_help_exist():
    assert {"Ctrl+Z", "Shift+B", "Alt+←"} <= ALL_CHIPS
