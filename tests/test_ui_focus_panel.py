from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

import database as db


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_source(qtbot, goal="미러"):
    from ui_focus import FocusWidgetWindow
    wid = db.create_focus_widget(goal, "25/5")
    data = next(w for w in db.get_open_focus_widgets() if w["id"] == wid)
    src = FocusWidgetWindow(wid, data)
    qtbot.addWidget(src)
    return src


def test_focus_mini_card_mirrors_progress(app_dir, qtbot, qapp):
    from ui_focus_panel import FocusMiniCard
    cur = datetime(2026, 4, 27, 9, 0, 0)
    src = _make_source(qtbot)
    src.timer_model._now = lambda: cur
    src._start_session()
    cur = cur + timedelta(minutes=5)
    card = FocusMiniCard(src)
    qtbot.addWidget(card)
    card._sync()
    assert card.percent_label.text() == "20%"
    assert card.remaining_label.text() == "20:00"
    assert "미러" in card.goal_label.text()


def test_focus_panel_bind_and_clear(app_dir, qtbot, qapp):
    from ui_focus_panel import FocusSidePanel
    src = _make_source(qtbot)
    panel = FocusSidePanel()
    qtbot.addWidget(panel)
    panel.bind(src)
    assert panel._card is not None
    assert panel._empty_label.isHidden()
    panel.clear()
    assert panel._card is None
    assert not panel._empty_label.isHidden()


def test_focus_card_close_signal(app_dir, qtbot, qapp):
    from ui_focus_panel import FocusMiniCard
    src = _make_source(qtbot)
    card = FocusMiniCard(src)
    qtbot.addWidget(card)
    got = []
    card.close_requested.connect(lambda: got.append(True))
    card.close_btn.click()
    assert got == [True]


def test_focus_panel_close_reemits(app_dir, qtbot, qapp):
    from ui_focus_panel import FocusSidePanel
    src = _make_source(qtbot)
    panel = FocusSidePanel()
    qtbot.addWidget(panel)
    panel.bind(src)
    got = []
    panel.close_requested.connect(lambda: got.append(True))
    panel._card.close_btn.click()
    assert got == [True]
