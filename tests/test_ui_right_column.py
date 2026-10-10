"""디자인 점검 16번: 크게 모드 오른쪽 열의 작은 글자와 알 수 없는 버튼."""
from PySide6.QtWidgets import QLabel

import database as db
from ui_dday_panel import DDayActionCard, DDayMiniCard
from ui_sticky import StickyFormatToolbar


def test_dday_card_name_is_at_least_11px(qtbot, app_dir):
    card = DDayMiniCard(1, {"name": "공모전 마감", "target_date": "2026-12-31", "color": db.DEFAULT_DDAY_COLOR})
    qtbot.addWidget(card)
    assert card.name_label.font().pixelSize() == 11


def test_dday_action_cards_are_one_line(qtbot):
    for mode, text in (("add", "+ D-Day 추가"), ("limit", "최대 5개 · 삭제 후 추가")):
        card = DDayActionCard(mode)
        qtbot.addWidget(card)
        labels = card.findChildren(QLabel)
        assert [label.text() for label in labels] == [text]
        assert labels[0].font().pixelSize() == 11 or "font-size:11px" in labels[0].styleSheet()


def test_sticky_background_button_shows_palette_icon(qtbot):
    toolbar = StickyFormatToolbar()
    qtbot.addWidget(toolbar)
    assert toolbar.bg_btn.toolTip() == "배경 색상"
    assert not toolbar.bg_btn.icon().isNull()  # 노트를 고르기 전에도 빈 네모가 아니다
    toolbar.set_bg_swatch("#FFFA8E")
    assert not toolbar.bg_btn.icon().isNull()
