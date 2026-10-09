"""디자인 점검 9번: 검색·휴지통 창을 설정 창과 같은 흰 카드·선 아이콘으로 맞춘다."""
import inspect

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

import database as db
import ui_search
import ui_trash
from ui_search import SearchWindow
from ui_trash import StickyTrashWindow
from ui_window_card import WindowCard

NOTION_COLORS = ("#37352f", "#f7f7f5", "#ebeced", "#ededed")


def _shown(qtbot, cls):
    win = cls()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    QApplication.processEvents()
    return win


@pytest.mark.parametrize("cls,title", [(SearchWindow, "일정 / 메모 검색"), (StickyTrashWindow, "스티키 노트 휴지통")])
def test_window_uses_white_card_with_line_icon_title(qtbot, app_dir, cls, title):
    win = _shown(qtbot, cls)
    card = win.card
    assert isinstance(card, WindowCard)
    assert card.title_label.text() == title  # 컬러 이모지 없이
    assert not card.icon_label.pixmap().isNull()
    image = card.grab().toImage()
    ratio = image.devicePixelRatio()
    inner = QPoint(card.width() - 6, card.height() - 6)
    assert image.pixelColor(int(inner.x() * ratio), int(inner.y() * ratio)).name() == "#ffffff"


@pytest.mark.parametrize("module", [ui_search, ui_trash])
def test_tables_drop_notion_palette(module):
    source = inspect.getsource(module).lower()
    for color in NOTION_COLORS:
        assert color not in source, color


def test_search_shows_empty_state_before_and_after_no_results(qtbot, app_dir):
    win = _shown(qtbot, SearchWindow)
    assert win.empty_label.isVisible() and not win.result_table.isVisible()
    assert "검색어를 입력" in win.empty_label.text()

    win.search_input.setText("없는검색어")
    win._on_search()
    QApplication.processEvents()
    assert win.empty_label.isVisible() and not win.result_table.isVisible()
    assert win.empty_label.text() == "검색 결과가 없습니다."

    db.add_schedule("2026-10-10", "수질 점검", "#4CC9F0")
    win.search_input.setText("점검")
    win._on_search()
    QApplication.processEvents()
    assert win.result_table.isVisible() and not win.empty_label.isVisible()
    assert win.result_table.rowCount() == 1
