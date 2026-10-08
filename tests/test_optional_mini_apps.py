"""선택형 미니앱 공용 연결부: 등록부·주머니 높이·메인 창 수명 지점 (가짜 앱 사용)."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from qfluentwidgets.common.font import fontFamilies, setFontFamilies
from shiboken6 import isValid

from app_fonts import apply_app_font
from app_paths import resource_root
import database as db
import optional_mini_apps
import ui_main
from ui_main import MainCalendarWindow
from ui_mini_apps import MiniAppSpec, pocket_body_height


class FakeOptionalWindow(QWidget):
    instances = []

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool)
        self.calls = []
        FakeOptionalWindow.instances.append(self)

    def show_near(self, anchor, available):
        self.calls.append("show_near")
        self.show()

    def hide_owned_popups(self):
        self.calls.append("hide_owned_popups")

    def cancel_work(self):
        self.calls.append("cancel_work")

    def fit_to_screen(self, available=None):
        self.calls.append("fit_to_screen")

    def shutdown(self):
        self.calls.append("shutdown")


FAKE = MiniAppSpec(
    app_id="fake", title="가짜\n앱", accessible_name="가짜 앱 실행", description="공용 연결부 검사용",
    icon_path=resource_root() / "resources" / "icons" / "mini_apps" / "upcoming.svg",
    create_window=FakeOptionalWindow,
)


@pytest.fixture(autouse=True)
def isolated(app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", (FAKE,))
    FakeOptionalWindow.instances.clear()
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def window(qtbot):
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    assert QTest.qWaitForWindowExposed(win)
    return win


def open_pocket(qtbot, win):
    qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: win._mini_apps_popup is not None and win._mini_apps_popup.isVisible())
    return win._mini_apps_popup


def open_fake(qtbot, win):
    popup = open_pocket(qtbot, win)
    qtbot.mouseClick(popup.optional_cards["fake"], Qt.LeftButton)
    qtbot.waitUntil(lambda: "fake" in win._optional_windows)
    return win._optional_windows["fake"]


def test_pocket_body_height_by_app_count():
    assert [pocket_body_height(n) for n in (1, 4, 5, 6, 7, 9)] == [280, 280, 390, 390, 390, 390]


def test_pocket_appends_optional_tile_and_grows_to_three_rows(qtbot):
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    assert popup.card.size() == QSize(252, 390)
    assert popup.size() == QSize(300, 438)
    assert popup.apps_grid.count() == 5
    tile = popup.optional_cards["fake"]
    assert popup.apps_grid.itemAtPosition(2, 0).widget() is tile
    assert tile.text() == "가짜\n앱" and tile.accessibleName() == "가짜 앱 실행"
    assert not tile.icon().isNull()
    assert popup.count_label.text() == "5개"
    assert popup.apps_scroll.verticalScrollBar().maximum() == 0
    win._close_mini_apps()


def test_empty_registry_keeps_original_pocket(qtbot, monkeypatch):
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", ())
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    assert popup.card.size() == QSize(252, 280)
    assert popup.apps_grid.count() == 4 and popup.optional_cards == {}
    win._close_mini_apps()


def test_tile_opens_and_reuses_single_window(qtbot):
    win = window(qtbot)
    first = open_fake(qtbot, win)
    assert win._mini_apps_popup is None
    assert first.isVisible() and first.isEnabled()
    second = open_fake(qtbot, win)
    assert second is first and len(FakeOptionalWindow.instances) == 1
    assert first.calls.count("show_near") == 2


def test_locked_main_does_not_open_optional_app(qtbot):
    win = window(qtbot)
    win._lock()
    win._open_optional_mini_app("fake")
    assert win._optional_windows == {}
    win._unlock()


@pytest.mark.parametrize("action", ["lock", "tray", "sidebar", "scale", "reset_before"])
def test_hiding_lifecycle_cancels_and_hides(qtbot, action):
    win = window(qtbot)
    fake = open_fake(qtbot, win)
    fake.calls.clear()
    actions = {
        "lock": win._lock, "tray": win._minimize_to_tray,
        "sidebar": lambda: (db.save_setting(db.SETTING_SHOW_SIDEBAR, "0"), win._apply_sidebar_visibility()),
        # 크기 적용은 사이드바가 사라질 때만 미니앱을 숨긴다(기존 4개 앱과 같은 규칙).
        "scale": lambda: (db.save_setting(db.SETTING_SHOW_SIDEBAR, "0"), win._apply_calendar_scale()),
        "reset_before": win._discard_data_widgets,
    }
    actions[action]()
    assert fake.calls[:2] == ["cancel_work", "hide_owned_popups"]
    assert not fake.isVisible()
    assert fake.isEnabled() == (action != "lock")
    if action == "lock":
        win._unlock()


def test_screen_change_closes_popups_and_fits_without_cancelling(qtbot):
    win = window(qtbot)
    fake = open_fake(qtbot, win)
    fake.calls.clear()
    win._on_screen_changed()
    assert fake.calls == ["hide_owned_popups", "fit_to_screen"]


@pytest.mark.parametrize("route", ["quit", "reset_success"])
def test_quit_and_reset_success_shut_down_and_delete(qtbot, route):
    win = window(qtbot)
    fake = open_fake(qtbot, win)
    if route == "quit":
        assert win.prepare_for_quit()
    else:
        win._on_settings()
        win._settings_window.reset_succeeded.emit()
    assert "shutdown" in fake.calls
    assert win._optional_windows == {}
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(fake)
