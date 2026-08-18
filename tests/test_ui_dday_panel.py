import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import database as db


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_dday_panel_reload_lists_open(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    db.create_dday_widget("마감", "2026-12-31")
    db.create_dday_widget("시험", "2026-11-01")
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    assert len(panel._cards) == 2


def test_dday_panel_empty_state(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    assert len(panel._cards) == 0
    assert panel._action_card.mode == "add"
    assert panel._empty_label.isVisibleTo(panel)


def test_dday_card_shows_countdown(app_dir, qtbot, qapp):
    from ui_dday_panel import DDayMiniCard
    wid = db.create_dday_widget("마감", "2026-06-20")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    card = DDayMiniCard(wid, data)
    qtbot.addWidget(card)
    assert "마감" in card.name_label.text()
    assert card.count_label.text().startswith("D")


def test_dday_panel_uses_grid_no_scroll(app_dir, qtbot, qapp):
    from PySide6.QtWidgets import QGridLayout, QScrollArea
    from ui_dday_panel import DDaySidePanel
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    assert isinstance(panel._grid, QGridLayout)
    assert panel.findChildren(QScrollArea) == []


def test_dday_card_delete_signal(app_dir, qtbot, qapp):
    from ui_dday_panel import DDayMiniCard
    wid = db.create_dday_widget("마감", "2026-06-20")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    card = DDayMiniCard(wid, data)
    qtbot.addWidget(card)
    got = []
    card.delete_requested.connect(got.append)
    card.close_btn.click()
    assert got == [wid]


def test_dday_panel_grid_two_rows_for_five(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    for i in range(5):
        db.create_dday_widget(f"d{i}", "2026-12-31")
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    assert len(panel._cards) == 5
    last = panel._cards[4]
    row, col, _, _ = panel._grid.getItemPosition(panel._grid.indexOf(last))
    assert row == 1  # 3열 → 5번째(idx4)는 2행


def test_dday_panel_add_card_uses_first_empty_slot_and_emits(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    for i in range(4):
        db.create_dday_widget(f"d{i}", "2026-12-31")
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    panel.show()

    assert panel._action_card.mode == "add"
    row, col, _, _ = panel._grid.getItemPosition(panel._grid.indexOf(panel._action_card))
    assert (row, col) == (1, 1)  # 5번째 칸
    got = []
    panel.create_requested.connect(lambda: got.append(True))
    qtbot.mouseClick(panel._action_card, Qt.LeftButton)
    assert got == [True]


def test_dday_add_card_uses_loose_custom_dash_pattern(app_dir, qtbot, qapp):
    from ui_dday_panel import DDayActionCard

    card = DDayActionCard("add")
    qtbot.addWidget(card)

    assert "dashed" not in card.styleSheet()
    assert DDayActionCard.ADD_DASH_PATTERN == [6.0, 5.0]


def test_dday_panel_limit_card_uses_sixth_slot_and_is_disabled(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel
    for i in range(5):
        db.create_dday_widget(f"d{i}", "2026-12-31")
    panel = DDaySidePanel()
    qtbot.addWidget(panel)
    panel.reload()
    panel.show()

    assert panel._action_card.mode == "limit"
    row, col, _, _ = panel._grid.getItemPosition(panel._grid.indexOf(panel._action_card))
    assert (row, col) == (1, 2)  # 6번째 칸
    got = []
    panel.create_requested.connect(lambda: got.append(True))
    qtbot.mouseClick(panel._action_card, Qt.LeftButton)
    assert got == []


def test_dday_panel_long_titles_elide_without_expanding(app_dir, qtbot, qapp):
    from ui_dday_panel import DDaySidePanel

    names = [f"아주 긴 D-Day 제목입니다 {'가나다라마바' * 20} {i}" for i in range(3)]
    for name in names:
        db.create_dday_widget(name, "2026-12-31")

    panel = DDaySidePanel()
    panel.resize(330, 170)
    qtbot.addWidget(panel)
    panel.reload()
    panel.show()
    qapp.processEvents()
    panel.layout().activate()
    qapp.processEvents()

    assert len(panel._cards) == 3
    assert panel.sizeHint().width() <= panel.width()
    assert panel._grid_host.width() <= panel.width()
    for card, full_name in zip(panel._cards, names):
        assert card.width() <= panel._grid_host.width()
        assert card.name_label.toolTip() == full_name
        assert card.name_label.text() != full_name


def test_dday_cover_color_maps_legacy_and_defaults():
    """구 파스텔 저장값은 커버색으로 매핑되고, 미지/빈값은 기본 커버로."""
    from ui_dday import dday_cover_color
    # 구 파스텔 → 커버
    assert dday_cover_color("#C4D5FF") == "#46679C"
    assert dday_cover_color("#FFFA8E") == "#A8801F"
    assert dday_cover_color("#D0FFF1") == "#2E8F6E"
    assert dday_cover_color("#FFD8FB") == "#B25C8B"
    # 이미 커버 hex면 그대로 (대소문자 무관)
    assert dday_cover_color("#46679C") == "#46679C"
    assert dday_cover_color("#2e8f6e") == "#2E8F6E"
    # 미지/빈값 → 기본 커버(sky)
    assert dday_cover_color("") == "#46679C"
    assert dday_cover_color(None) == "#46679C"
    assert dday_cover_color("#123456") == "#46679C"


def test_dday_mini_card_cover_tint_white_count(app_dir, qtbot, qapp):
    """미니 카드: 커버색 배경(테두리 없음) + 흰 카운트."""
    from ui_dday_panel import DDayMiniCard
    wid = db.create_dday_widget("여행", "2030-01-01")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    card = DDayMiniCard(wid, data)
    qtbot.addWidget(card)
    ss = card.styleSheet().replace(" ", "")
    assert "border:none" in ss
    assert "#46679C" in ss  # 기본 저장색(#C4D5FF) → sky 커버
    assert "#FFFFFF" in card.count_label.styleSheet()
    assert card.count_label.text().startswith("D-")
