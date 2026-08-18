import pytest
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from ui_sticky import WIDGET_WIDTH, DDAY_HEIGHT
import ui_dday
from ui_dday import DDayWidgetWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _data(**over):
    d = {"name": "마감", "target_date": "2030-01-01",
         "color": "#46679C", "x_pos": 100, "y_pos": 100}
    d.update(over)
    return d


def test_dday_window_reserves_shadow_margin(app_dir, qtbot, qapp):
    win = DDayWidgetWindow(1, _data())
    qtbot.addWidget(win)
    m = ui_dday.SHADOW_MARGIN
    assert win.width() == WIDGET_WIDTH + 2 * m
    assert win.height() == DDAY_HEIGHT + 2 * m


def test_dday_shadow_margin_not_clipped_invariant():
    assert ui_dday.SHADOW_MARGIN >= ui_dday.SHADOW_BLUR + ui_dday.SHADOW_OFFSET_Y


def test_dday_window_has_drop_shadow(app_dir, qtbot, qapp):
    win = DDayWidgetWindow(1, _data())
    qtbot.addWidget(win)
    eff = win.container.graphicsEffect()
    assert isinstance(eff, QGraphicsDropShadowEffect)
    assert eff.blurRadius() == ui_dday.SHADOW_BLUR
    assert eff.yOffset() == ui_dday.SHADOW_OFFSET_Y
    assert eff.color().alpha() == ui_dday.SHADOW_ALPHA


def test_dday_window_has_light_hairline(app_dir, qtbot, qapp):
    win = DDayWidgetWindow(1, _data())
    qtbot.addWidget(win)
    ss = win.container.styleSheet().replace(" ", "")
    assert f"rgba(255,255,255,{ui_dday.HAIRLINE_ALPHA})" in ss
    assert "border:1pxsolid" in ss
    assert "border-radius:18px" in ss
    assert "#46679C" in ss  # 커버색 유지


def test_mini_card_has_no_shadow(app_dir, qtbot, qapp):
    """스코프 경계: 미니 카드에는 그림자를 적용하지 않는다."""
    import database as db
    from ui_dday_panel import DDayMiniCard
    wid = db.create_dday_widget("여행", "2030-01-01")
    data = next(w for w in db.get_open_dday_widgets() if w["id"] == wid)
    card = DDayMiniCard(wid, data)
    qtbot.addWidget(card)
    assert card.graphicsEffect() is None
