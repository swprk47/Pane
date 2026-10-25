"""The help button on the title bar (after the update button, before the divider) and the divider that stays."""


def order_of(bar):
    lay = bar.layout()
    return [lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget()]


def test_the_help_button_sits_after_the_update_button_and_before_the_divider(window):
    bar = window.title_bar
    order = order_of(bar)
    names = [bar.btn_pip, bar.btn_update, bar.btn_help, bar.sep_update, bar.btn_min]
    idx = [order.index(w) for w in names]
    assert idx == list(range(idx[0], idx[0] + 5)), "PIP, update, help, divider, minimize follow each other"


def test_it_has_a_tooltip_and_a_28_px_square_and_is_in_the_faded_set(window):
    bar = window.title_bar
    assert bar.btn_help.toolTip() == "단축키 도움말 (?)"
    assert (bar.btn_help.width(), bar.btn_help.height()) == (28, 28)
    assert bar.btn_help in bar._buttons()


def test_clicking_it_emits_help_clicked(window):
    got = []
    window.title_bar.help_clicked.connect(lambda: got.append(1))
    window.title_bar.btn_help.click()
    assert got == [1]


def test_the_help_button_and_the_divider_stay_while_a_video_is_open(window):
    bar = window.title_bar
    bar.set_update_visible(False)
    assert not bar.btn_update.isVisible()
    assert bar.btn_help.isVisible() and bar.sep_update.isVisible()
    bar.set_update_visible(True)
    assert bar.btn_update.isVisible() and bar.btn_help.isVisible() and bar.sep_update.isVisible()
