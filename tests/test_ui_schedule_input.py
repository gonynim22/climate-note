"""v4.1 입력줄: 시계 버튼·알약·보류 중 세부 설정과 일정 추가 연결 회귀. 합성 데이터만 쓴다."""
import sqlite3

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
import database as db
import ui_main
from schedule_rules import ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch, qapp):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def main_window(qtbot, scale="compact", day="2026-10-15"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    win._on_date_selected(day)
    QApplication.processEvents()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    return win


def open_card(qtbot, button):
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    assert QTest.qWaitForWindowExposed(button._popup)
    return button._popup


def click(qtbot, widget):
    qtbot.mouseClick(widget, Qt.LeftButton)
    QApplication.processEvents()


def test_clock_button_sits_between_smile_and_input(qtbot):
    win = main_window(qtbot)
    clock, smile = win.schedule_options_button, win.schedule_emoji_button
    assert clock.size() == QSize(26, 26)
    assert smile.mapTo(win, QPoint()).x() < clock.mapTo(win, QPoint()).x()
    assert clock.mapTo(win, QPoint()).x() < win.schedule_input.mapTo(win, QPoint()).x()
    clock_center = clock.mapTo(win, QPoint()).y() + clock.height() / 2
    smile_center = smile.mapTo(win, QPoint()).y() + smile.height() / 2
    assert abs(clock_center - smile_center) <= 0.5
    assert win.schedule_input.width() >= 100


def test_add_with_options_saves_then_clears_and_failure_keeps(qtbot, monkeypatch):
    win = main_window(qtbot)
    options = ScheduleOptions(start_time="15:00", repeat_rule="weekly", alarm_before=10)
    win._set_pending_options(options)
    win.schedule_input.setText("부서 회의")
    original = db.add_schedule

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(db, "add_schedule", fail)
    win._on_add_schedule()
    assert win.schedule_input.text() == "부서 회의"
    assert win.schedule_options_button.options() == options
    assert win.schedule_options_pills.visible_texts() == ["15:00 · 10분 전", "매주 목"]
    monkeypatch.setattr(db, "add_schedule", original)
    qtbot.keyClick(win.schedule_input, Qt.Key_Return)
    saved = db.get_schedules("2026-10-22")
    assert [(s["content"], s["options"]) for s in saved] == [("부서 회의", options)]
    assert win.schedule_input.text() == ""
    assert win.schedule_options_button.options() == ScheduleOptions()
    assert win.schedule_options_pills.isHidden()


def test_card_changes_pending_options_without_saving(qtbot):
    win = main_window(qtbot)
    card = open_card(qtbot, win.schedule_options_button)
    click(qtbot, card.repeat_chips["daily"])
    assert win.schedule_options_pills.visible_texts() == ["매일"]
    assert db.get_schedules("2026-10-15") == []


def test_pill_x_clears_only_that_part_and_body_opens_card(qtbot):
    win = main_window(qtbot)
    win._set_pending_options(ScheduleOptions(start_time="09:00", repeat_rule="daily", alarm_before=10))
    QApplication.processEvents()
    pills = win.schedule_options_pills.pills
    qtbot.mouseClick(pills["time"], Qt.LeftButton, pos=pills["time"].clear_rect().center().toPoint())
    assert win.schedule_options_button.options() == ScheduleOptions(repeat_rule="daily")
    qtbot.mouseClick(pills["repeat"], Qt.LeftButton, pos=QPoint(14, 11))
    qtbot.waitUntil(lambda: win.schedule_options_button._popup is not None)
    assert win.schedule_options_button._popup.isVisible()


def test_pending_options_follow_selected_date(qtbot):
    win = main_window(qtbot)
    win._set_pending_options(ScheduleOptions(end_date="2026-10-17"))
    win._on_date_selected("2026-10-20")
    assert win.schedule_options_button.options() == ScheduleOptions(end_date="2026-10-22")
    assert win.schedule_options_pills.visible_texts() == ["~10.22 · 3일"]
    win._set_pending_options(ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-24"))
    win._on_date_selected("2026-10-25")
    assert win.schedule_options_button.options() == ScheduleOptions(repeat_rule="weekly")


def test_hidden_pills_add_no_space_and_align_with_input(qtbot):
    win = main_window(qtbot)
    row = [win.schedule_color_btn, win.schedule_emoji_button, win.schedule_options_button,
           win.schedule_input]
    QApplication.processEvents()
    row_bottom = max(widget.geometry().bottom() for widget in row)
    hidden_gap = win.schedule_list.geometry().top() - row_bottom
    win._set_pending_options(ScheduleOptions(start_time="09:00"))
    QApplication.processEvents()
    pills = win.schedule_options_pills
    assert pills.isVisible()
    assert pills.pills["time"].mapTo(win, QPoint()).x() == win.schedule_input.mapTo(win, QPoint()).x()
    assert win.schedule_list.geometry().top() - row_bottom == hidden_gap + pills.height() + 4
    win._set_pending_options(ScheduleOptions())
    QApplication.processEvents()
    assert win.schedule_list.geometry().top() - row_bottom == hidden_gap


@pytest.mark.parametrize("action", ["lock", "tray", "reset", "scale"])
def test_card_closes_on_lifecycle_and_ignores_late_change(qtbot, action):
    win = main_window(qtbot)
    button = win.schedule_options_button
    win._set_pending_options(ScheduleOptions(repeat_rule="daily"))
    card = open_card(qtbot, button)
    if action == "lock":
        win._lock()
    elif action == "tray":
        win._minimize_to_tray()
    elif action == "reset":
        win._discard_data_widgets()
    else:
        db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
        win._apply_calendar_scale()
    assert not card.isVisible()
    card.options_changed.emit(ScheduleOptions(start_time="11:00"))
    expected = ScheduleOptions() if action == "reset" else ScheduleOptions(repeat_rule="daily")
    assert button.options() == expected  # 초기화 전 폐기만 보류 값을 비운다.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    assert not isValid(card)
    if action == "lock":
        button.open_popup()
        assert button._popup is None  # 잠금 중에는 열지 않는다.


def test_escape_restores_focus_to_schedule_input(qtbot):
    win = main_window(qtbot)
    card = open_card(qtbot, win.schedule_options_button)
    click(qtbot, card.repeat_chips["daily"])
    qtbot.keyClick(card, Qt.Key_Escape)
    qtbot.waitUntil(lambda: win.schedule_input.hasFocus())
    assert win.schedule_options_button.options() == ScheduleOptions(repeat_rule="daily")
