"""The bookmark control button and the one-time layout migration that gives saved layouts the button."""
import json

import pytest
from PySide6.QtWidgets import QPushButton, QWidget

from core.settings import open_settings
from ui.glass_controller import (BUTTON_METADATA, DEFAULT_LAYOUT, LAYOUT_ADDITIONS, LAYOUT_ADDITIONS_VERSION,
                                 LAYOUT_VERSION, GlassController)
from ui.icons import SVG_ICONS


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(1000, 600)
    h.show()
    yield h
    h.close()


def save_old_layout(layout, additions_version=None):
    s = open_settings("ControllerLayout")
    s.setValue("button_layout", json.dumps(layout))
    s.setValue("layout_version", LAYOUT_VERSION)
    if additions_version is not None:
        s.setValue("layout_additions_version", additions_version)
    return s


OLD = {"left": ["time_label"], "center": ["play_pause"], "right": ["screenshot", "subtitle", "volume", "settings"]}


def test_the_default_layout_has_the_bookmark_button_after_the_subtitle_button():
    right = DEFAULT_LAYOUT["right"]
    assert right[right.index("subtitle") + 1] == "bookmarks"
    assert BUTTON_METADATA["bookmarks"] == {"name": "북마크", "icon_name": "bookmark"}
    assert LAYOUT_ADDITIONS == [("bookmarks", "right", "subtitle")] and LAYOUT_ADDITIONS_VERSION == 1


def test_a_saved_layout_gets_the_button_once_after_the_subtitle_button_and_keeps_everything_else(host):
    s = save_old_layout(OLD)
    c = GlassController(host)
    assert c.current_layout == {"left": ["time_label"], "center": ["play_pause"],
                                "right": ["screenshot", "subtitle", "bookmarks", "volume", "settings"]}
    assert int(s.value("layout_additions_version")) == 1
    assert json.loads(s.value("button_layout")) == c.current_layout, "stored, so the owner's later edits start from it"


def test_a_removed_button_does_not_come_back(host):
    save_old_layout(OLD)
    first = GlassController(host)
    gone = {z: [k for k in keys if k != "bookmarks"] for z, keys in first.current_layout.items()}
    first._save_layout(gone)
    assert GlassController(host).current_layout == gone


def test_a_layout_without_a_subtitle_button_gets_it_at_the_end_of_the_right_zone(host):
    save_old_layout({"left": [], "center": ["play_pause"], "right": ["volume", "settings"]})
    assert GlassController(host).current_layout["right"] == ["volume", "settings", "bookmarks"]


def test_a_layout_that_already_has_the_button_is_left_alone(host):
    layout = {"left": [], "center": [], "right": ["bookmarks", "subtitle"]}
    save_old_layout(layout)
    assert GlassController(host).current_layout == layout


def test_a_fresh_install_gets_the_default_and_the_marker(host):
    c = GlassController(host)
    assert c.current_layout == DEFAULT_LAYOUT
    assert int(open_settings("ControllerLayout").value("layout_additions_version")) == LAYOUT_ADDITIONS_VERSION


def test_clicking_the_button_emits_bookmarks_clicked(host, qapp):
    c = GlassController(host)
    c.show()
    qapp.processEvents()
    got = []
    c.bookmarks_clicked.connect(lambda: got.append(1))
    assert c.btn_bookmarks.toolTip() == "북마크 (Shift+B)"
    c.btn_bookmarks.click()
    assert got == [1]


def test_the_layout_editor_lists_the_new_button():
    assert BUTTON_METADATA["bookmarks"]["icon_name"] in SVG_ICONS
