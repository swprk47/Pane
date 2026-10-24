"""The update notice: the card, where it appears and when, the about-dialog button and the settings switch."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import QWidget

from core.updater import Manifest
from ui.update_card import UpdateCard

MANIFEST = Manifest(version="1.3.0", url="https://example.com/Pane-1.3.0-setup.exe", sha256="a" * 64, size=70_000_000,
                    notes="재생바에 시간이 보여요")


def render(widget) -> QImage:
    img = QImage(widget.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return img


def lit_pixels(img, threshold=200) -> int:
    return sum(1 for y in range(img.height()) for x in range(img.width())
               if img.pixelColor(x, y).red() > threshold and img.pixelColor(x, y).alpha() > threshold)


# --- the card on its own -----------------------------------------------------------------------

@pytest.fixture
def card(qapp):
    host = QWidget()
    host.resize(900, 600)
    host.show()
    c = UpdateCard(host)
    yield c
    host.close()


def test_the_card_is_hidden_until_there_is_something_to_say(card):
    assert not card.isVisible() and card.mode == "hidden"


def test_an_offer_names_the_version_and_has_an_update_button_and_a_close_button(card):
    card.show_offer("1.3.0", "재생바에 시간이 보여요")
    assert card.isVisible() and card.mode == "offer"
    assert "1.3.0" in card.title_text and card.btn_update.isVisible() and card.btn_close.isVisible()
    assert "재생바" in card.toolTip(), "the release notes are in the tooltip"


def test_the_buttons_say_what_was_chosen(card):
    got = []
    card.update_clicked.connect(lambda: got.append("update"))
    card.dismissed.connect(lambda: got.append("dismissed"))
    card.show_offer("1.3.0")
    card.btn_update.click()
    card.btn_close.click()
    assert got == ["update", "dismissed"]


def test_progress_shows_the_amount_and_hides_the_buttons(card):
    card.show_offer("1.3.0")
    card.show_progress(29_000_000, 70_000_000)
    assert card.mode == "progress" and "1.3.0" in card.title_text
    assert "29MB / 70MB" in card.detail_text and "41%" in card.detail_text
    assert not card.btn_update.isVisible() and not card.btn_close.isVisible(), "nothing to press while it downloads"


def test_the_progress_bar_is_drawn_in_proportion(card):
    card.show_offer("1.3.0")
    card.show_progress(10, 100)
    low = lit_pixels(render(card))
    card.show_progress(90, 100)
    high = lit_pixels(render(card))
    assert high > low + 100, (low, high)


def test_installing_says_pane_will_restart(card):
    card.show_installing()
    assert card.mode == "installing" and "다시 시작" in card.detail_text and not card.btn_update.isVisible()


def test_a_failure_shows_the_reason_and_a_retry_button(card):
    got = []
    card.update_clicked.connect(lambda: got.append(1))
    card.show_failure("업데이트를 설치하지 못했어요: the download was cut off")
    assert card.mode == "failed" and "cut off" in card.detail_text
    assert card.btn_update.isVisible() and card.btn_update.text() == "다시 시도" and card.btn_close.isVisible()
    card.btn_update.click()
    assert got == [1]


def test_hiding_resets_the_card(card):
    card.show_offer("1.3.0")
    card.hide_card()
    assert not card.isVisible() and card.mode == "hidden"


def test_the_card_actually_paints_text_and_a_panel(card):
    card.show_offer("1.3.0")
    img = render(card)
    assert lit_pixels(img) > 60, "the title and the button text are drawn in white"
    assert img.pixelColor(img.width() // 2, 2).alpha() > 0, "the glass panel is drawn"


def test_a_long_failure_message_is_cut_to_the_card(card):
    card.show_failure("x" * 500)
    img = render(card)
    assert img.width() == UpdateCard.WIDTH


@pytest.mark.parametrize("text", ["<b>굵게</b> & <i>x</i>", "줄 하나\n줄 둘", "<img src=x> a &lt; b", "plain"])
def test_the_tooltip_shows_the_notes_and_the_failure_as_plain_text_not_as_html(card, text):
    from PySide6.QtGui import QTextDocument, Qt as QtGuiQt

    def shown(tooltip):
        doc = QTextDocument()
        doc.setHtml(tooltip) if QtGuiQt.mightBeRichText(tooltip) else doc.setPlainText(tooltip)
        return doc.toPlainText()

    card.show_offer("1.3.0", text)
    assert shown(card.toolTip()).strip() == text
    card.show_failure(text)
    assert shown(card.toolTip()).strip() == text


def test_a_long_tooltip_can_still_wrap(card):
    card.show_failure("긴 이유 " * 40)
    assert "\xa0" not in card.toolTip(), "no unbreakable spaces: a long message must wrap, not run off the screen"
