import database as db
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_enforce_keeps_newest_focus(app_dir):
    ids = [db.create_focus_widget(f"목표{i}", "25/5") for i in range(3)]
    result = db.enforce_widget_limits()
    assert result["focus"] == 2
    assert [w["id"] for w in db.get_open_focus_widgets()] == [ids[-1]]


def test_enforce_keeps_newest_five_dday(app_dir):
    ids = [db.create_dday_widget(f"D{i}", "2026-12-31") for i in range(7)]
    result = db.enforce_widget_limits()
    assert result["dday"] == 2
    assert sorted(w["id"] for w in db.get_open_dday_widgets()) == sorted(ids[2:])


def test_enforce_is_idempotent(app_dir):
    for i in range(3):
        db.create_focus_widget(f"g{i}", "25/5")
    db.enforce_widget_limits()
    assert db.enforce_widget_limits() == {"focus": 0, "dday": 0}


def test_enforce_preserves_closed_widget_data(app_dir):
    db.create_focus_widget("보존1", "25/5")
    db.create_focus_widget("보존2", "25/5")
    db.enforce_widget_limits()
    with db._connection() as conn:
        rows = conn.execute("SELECT goal FROM focus_widgets ORDER BY id").fetchall()
    assert len(rows) == 2
    assert db.decrypt(rows[0]["goal"]) == "보존1"


def test_main_enforces_focus_keeps_newest(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    ids = [db.create_focus_widget(f"목표{i}", db.DEFAULT_FOCUS_MODE) for i in range(3)]
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert list(win._focus_windows.keys()) == [ids[-1]]
    assert win._widget_trim_result["focus"] == 2


def test_main_enforces_dday_keeps_newest_five(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    ids = [db.create_dday_widget(f"D{i}", "2026-12-31") for i in range(7)]
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    assert sorted(win._dday_windows.keys()) == sorted(ids[2:])
    assert win._widget_trim_result["dday"] == 2


def test_focus_at_limit_counts_registry_not_visibility(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._focus_windows = {1: _RegistryOnlyWindow()}
    assert win._focus_at_limit() is True
    win._focus_windows = {}
    assert win._focus_at_limit() is False


def test_dday_at_limit_is_five(app_dir, qtbot, qapp):
    from ui_main import MainCalendarWindow
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._dday_windows = {i: _RegistryOnlyWindow() for i in range(5)}
    assert win._dday_at_limit() is True
    win._dday_windows = {i: _RegistryOnlyWindow() for i in range(4)}
    assert win._dday_at_limit() is False


class _RegistryOnlyWindow:
    def hide(self):
        pass
