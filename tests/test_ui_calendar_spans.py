"""v4.1 달력: 나타나는 일정 개수·색, 중간·크게 칩 시각과 여러 날 막대 회귀. 합성 데이터만 쓴다."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

import database as db
from schedule_rules import ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow


class _Screen:
    def __init__(self, width, height):
        self.geometry = QRect(0, 0, width, height)

    def availableGeometry(self):
        return self.geometry


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, monkeypatch):
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def calendar_window(qtbot, monkeypatch, scale, year=2026, month=10, screen=(1920, 1080)):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    target = _Screen(*screen)
    monkeypatch.setattr(MainCalendarWindow, "_get_target_screen", lambda self: target)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win._current_year, win._current_month = year, month
    win._refresh_calendar()
    qtbot.wait(120)
    return win


def test_compact_counts_occurrences(qtbot, monkeypatch):
    db.add_schedule("2026-10-13", "기간", "#4CC9F0", options=ScheduleOptions(end_date="2026-10-15"))
    db.add_schedule("2026-10-01", "매일", options=ScheduleOptions(repeat_rule="daily", repeat_until="2026-10-14"))
    db.add_schedule("2026-10-14", "빨강", "#FF6B6B")
    db.add_schedule("2026-10-14", "노랑 둘", "#FFD166")
    win = calendar_window(qtbot, monkeypatch, "compact")
    cell = win._day_cells["2026-10-14"]
    assert cell._count == 4
    assert cell.squares_label.text().count("■") == 3
    assert cell.count_label.text() == "+1"
    assert win._day_cells["2026-10-16"]._count == 0
    assert win._day_cells["2026-10-02"]._count == 1


def test_timed_chip_and_plain_text(qtbot, monkeypatch):
    db.add_schedule("2026-10-14", "<b>회의</b>", options=ScheduleOptions(start_time="14:00"))
    db.add_schedule("2026-10-14", "종일 일정")
    win = calendar_window(qtbot, monkeypatch, "large", screen=(2560, 1440))
    layout = win._day_cells["2026-10-14"]._chips_layout
    chips = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert [chip.toolTip() for chip in chips] == ["종일 일정", "14:00 <b>회의</b>"]
    assert chips[1].text().startswith("14:00 <b>")
    assert chips[1].textFormat() == Qt.PlainText
    assert not chips[1].font().bold()


def test_monthly_31st_shows_on_february_last_day(qtbot, monkeypatch):
    """Review Focus 5: 매월 31일 반복은 2월에 말일(28일)로 보인다."""
    db.add_schedule("2026-01-31", "월말 보고", options=ScheduleOptions(repeat_rule="monthly"))
    win = calendar_window(qtbot, monkeypatch, "compact", month=2)
    assert win._day_cells["2026-02-28"]._count == 1
    assert sum(cell._count for cell in win._day_cells.values()) == 1


def test_cells_are_not_recreated_by_month_refresh(qtbot, monkeypatch):
    win = calendar_window(qtbot, monkeypatch, "medium")
    cells = dict(win._day_cells)
    db.add_schedule("2026-10-20", "반복", options=ScheduleOptions(repeat_rule="weekly"))
    win._refresh_month_data()
    assert win._day_cells == cells
    assert win._day_cells["2026-10-27"]._chips_layout.count() == 1
