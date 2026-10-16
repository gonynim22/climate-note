"""v4.1 일정 목록 줄(시각 열·아이콘·기간 글자)·편집·반복 삭제·검색 꼬리 회귀. 합성 데이터만 쓴다."""
import sqlite3

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
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
from ui_search import SearchWindow

WEEKLY = ScheduleOptions(start_time="10:00", repeat_rule="weekly", alarm_before=10)


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


def main_window(qtbot, day="2026-10-12", scale="compact"):
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


def rows(win):
    return [win.schedule_list.itemWidget(win.schedule_list.item(i)) for i in range(win.schedule_list.count())]


def texts(win):
    return [row.schedule_text_label.text() for row in rows(win)]


def test_all_day_only_day_keeps_old_row_layout(qtbot):
    db.add_schedule("2026-10-12", "종일 일정")
    win = main_window(qtbot)
    row = rows(win)[0]
    assert row.schedule_time_label is None
    assert row.schedule_period_label is None
    assert row.schedule_icons == []
    assert row.schedule_text_label.toolTip() == "종일 일정"


def test_time_column_order_icons_period_and_tooltip(qtbot):
    late = db.add_schedule("2026-10-12", "오후 점검", options=ScheduleOptions(start_time="16:00"))
    db.add_schedule("2026-10-05", "주간 회의", "#4CC9F0", options=WEEKLY)
    db.add_schedule("2026-10-12", "종일 일정")
    db.add_schedule("2026-10-11", "출장", options=ScheduleOptions(end_date="2026-10-13"))
    win = main_window(qtbot)
    assert texts(win) == ["종일 일정", "출장", "주간 회의", "오후 점검"]
    times = [row.schedule_time_label.text() for row in rows(win)]
    assert times == ["종일", "종일", "10:00", "16:00"]
    assert all(row.schedule_time_label.width() == 40 for row in rows(win))
    weekly_row = rows(win)[2]
    assert weekly_row.schedule_icons == ["repeat", "bell"]
    assert weekly_row.schedule_text_label.toolTip() == (
        "주간 회의\n시작: 10:00\n매주 월요일 반복 · 끝: 계속\n알림: 10분 전")
    assert rows(win)[1].schedule_period_label.text() == "10.11~10.13"
    assert win.count_label.text() == "총 4개"
    item = win.schedule_list.item(3)
    assert item.data(Qt.UserRole) == late
    assert item.data(Qt.UserRole + 5) == "2026-10-12"
    weekly_item = win.schedule_list.item(2)
    assert (weekly_item.data(Qt.UserRole + 4), weekly_item.data(Qt.UserRole + 5),
            weekly_item.data(Qt.UserRole + 6)) == (WEEKLY, "2026-10-05", "2026-10-12")


def test_body_is_plain_text_and_long_text_keeps_delete_button(qtbot):
    content = "<b>굵게 보이면 안 됨</b> " + "아주 긴 일정 제목 " * 30
    db.add_schedule("2026-10-12", content, options=ScheduleOptions(repeat_rule="daily", alarm_before=0))
    win = main_window(qtbot)
    row = rows(win)[0]
    label = row.schedule_text_label
    assert label.text() == content
    assert label.textFormat() == Qt.PlainText
    assert label.minimumSizeHint().width() == 0
    QApplication.processEvents()
    win.schedule_list.setCurrentRow(0)
    assert row.rect().contains(row.delete_button.geometry())
    assert row.rect().contains(row.schedule_text_box.geometry())


def test_new_row_is_highlighted_briefly(qtbot):
    win = main_window(qtbot)
    win.schedule_input.setText("새 일정")
    win._on_add_schedule()
    row = rows(win)[0]
    assert row.objectName() == "scheduleRowNew"
    assert "#EFF6FF" in row.styleSheet()
    qtbot.waitUntil(lambda: row.styleSheet() == "", timeout=2500)
