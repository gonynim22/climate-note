"""v4.1 달력: 나타나는 일정 개수·색, 중간·크게 칩 시각과 여러 날 막대 회귀. 합성 데이터만 쓴다."""
import os
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

import database as db
from schedule_rules import ScheduleOptions
from show_desktop_guard import ShowDesktopKeeper
from ui_main import CalendarDayButton, MainCalendarWindow


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
    assert chips[0].toolTip() == "종일 일정"
    tooltip = QTextDocument()
    tooltip.setHtml(chips[1].toolTip())
    assert tooltip.toPlainText() == "14:00 <b>회의</b>"
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


def overlay_x(win, cell, x):
    return cell.mapTo(win._calendar_section, QPoint(x, 0)).x() - win._span_overlay.x()


def bars(win):
    return {(bar.segment.key, bar.segment.row): (bar, rect) for bar, rect in win._span_overlay.bar_rects()}


def test_bars_follow_columns_lanes_and_break_at_week_edges(qtbot, monkeypatch):
    long_id = db.add_schedule("2026-10-08", "출장 " * 20, "#4CC9F0",
                              options=ScheduleOptions(start_time="09:00", end_date="2026-10-12"))
    short_id = db.add_schedule("2026-10-09", "교육", options=ScheduleOptions(end_date="2026-10-10"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    found = bars(win)
    first_bar, first = found[(long_id, 1)]
    second_bar, second = found[(long_id, 2)]
    lane_bar, lane = found[(short_id, 1)]
    start_cell, sat_cell = win._day_cells["2026-10-08"], win._day_cells["2026-10-10"]
    sun_cell, end_cell = win._day_cells["2026-10-11"], win._day_cells["2026-10-12"]
    assert first.left() == overlay_x(win, start_cell, 6)
    assert first.right() == overlay_x(win, sat_cell, sat_cell.width())
    assert second.left() == overlay_x(win, sun_cell, 0)
    assert second.right() == overlay_x(win, end_cell, end_cell.width() - 4)
    assert (first_bar.segment.starts, first_bar.segment.ends) == (True, False)
    assert (second_bar.segment.starts, second_bar.segment.ends) == (False, True)
    assert first_bar.text.startswith("09:00 출장") and not second_bar.text.startswith("09:00")
    assert lane_bar.segment.lane == 1
    assert lane.top() == first.top() + start_cell.chip_height + start_cell.chip_spacing
    assert first.height() == start_cell.chip_height == 16
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        assert win.grab().save(str(Path(appdata).parent / "calendar-span-medium.png"))


def test_bar_from_previous_month_has_square_start_next_to_blank_cells(qtbot, monkeypatch):
    """Review Focus 5: 달 첫 주 빈칸 옆에서 지난달부터 이어진 막대는 왼쪽 끝이 각지다."""
    span = db.add_schedule("2026-09-29", "월말 출장", options=ScheduleOptions(end_date="2026-10-02"))
    win = calendar_window(qtbot, monkeypatch, "large")
    bar, rect = bars(win)[(span, 0)]
    first_cell = win._day_cells["2026-10-01"]
    assert (bar.segment.first_col, bar.segment.starts, bar.segment.ends) == (4, False, True)
    assert rect.left() == overlay_x(win, first_cell, 0)
    assert rect.height() == 22


def test_cells_reserve_bar_lanes_and_count_hidden_ones(qtbot, monkeypatch):
    for index in range(4):
        db.add_schedule("2026-10-13", f"기간 {index}", options=ScheduleOptions(end_date="2026-10-15"))
    for index in range(3):
        db.add_schedule("2026-10-14", f"하루 {index}")
    win = calendar_window(qtbot, monkeypatch, "medium")
    cell = win._day_cells["2026-10-14"]
    layout = cell.chips_layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    slots = [w for w in widgets if w.objectName() == "calendarSpanSlot"]
    chips = [w for w in widgets if w.objectName() != "calendarSpanSlot"]
    assert len(slots) == min(4, cell.span_lane_cap)
    shown_bars = [b for b, _rect in win._span_overlay.bar_rects() if b.segment.row == 2]
    assert len(shown_bars) == len(slots)
    hidden_lanes = 4 - len(slots)
    if hidden_lanes or len(chips) < 3:
        shown_singles = len(chips) - 1
        assert chips[-1].text() == f"+{3 - shown_singles + hidden_lanes} 더"
    assert not cell.count_label.isVisibleTo(cell)  # 중간·크게는 '+N' 숫자 대신 칩을 쓴다


@pytest.mark.parametrize("scale,screen", [("large", (864, 1536)), ("medium", (1440, 2560))])
def test_bars_do_not_change_column_widths_and_follow_resize(qtbot, monkeypatch, scale, screen):
    win = calendar_window(qtbot, monkeypatch, scale, screen=screen)
    before = [win.calendar_grid.cellRect(1, col).width() for col in range(7)]
    span = db.add_schedule("2026-10-06", "아주 긴 기간 일정 제목 " * 10,
                           options=ScheduleOptions(end_date="2026-10-16"))
    win._refresh_month_data()
    qtbot.wait(80)
    widths = [win.calendar_grid.cellRect(1, col).width() for col in range(7)]
    assert widths == before
    assert max(widths) - min(widths) <= 1
    section = win.right_content.findChild(QWidget, "calendarSection")
    headers = [item for item in section.findChildren(QGridLayout)
               if item is not win.calendar_grid and item.count() == 7]
    assert len(headers) == 1
    win.resize(win.width() - 40, win.height())
    qtbot.wait(120)
    _bar, rect = bars(win)[(span, 1)]
    assert rect.left() == overlay_x(win, win._day_cells["2026-10-06"], 6)


def test_scale_switch_hides_and_shows_bars(qtbot, monkeypatch):
    db.add_schedule("2026-10-13", "기간", options=ScheduleOptions(end_date="2026-10-15"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    assert win._span_overlay.isVisible()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win._apply_calendar_scale()
    QApplication.processEvents()
    assert win._span_overlay.isHidden()
    assert win._day_cells["2026-10-14"]._count == 1
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win._apply_calendar_scale()
    qtbot.wait(120)
    assert win._span_overlay.isVisible()
    assert all(rect.height() == 22 for _bar, rect in win._span_overlay.bar_rects())


def test_period_is_a_bar_not_a_chip(qtbot, monkeypatch):
    db.add_schedule("2026-10-13", "기간", options=ScheduleOptions(end_date="2026-10-14"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    layout = win._day_cells["2026-10-13"].chips_layout
    names = [layout.itemAt(i).widget().objectName() for i in range(layout.count())]
    assert names == ["calendarSpanSlot"]


def test_db_error_during_rebuild_clears_overlay_instead_of_keeping_deleted_cells(qtbot, monkeypatch):
    """칸을 새로 만든 직후 월 조회가 실패해도 막대 오버레이가 삭제된 옛 칸을 쥐고 있지 않다."""
    db.add_schedule("2026-10-13", "기간", options=ScheduleOptions(end_date="2026-10-15"))
    win = calendar_window(qtbot, monkeypatch, "medium")
    assert win._span_overlay.isVisible() and win._span_overlay.bar_rects()
    real = db.get_occurrences

    def broken(*_args, **_kwargs):
        raise sqlite3.Error("합성 조회 실패")

    monkeypatch.setattr(db, "get_occurrences", broken)
    win._refresh_calendar()
    qtbot.wait(150)  # 옛 칸의 deleteLater가 처리될 때까지
    assert win._span_overlay.bar_rects() == []
    assert win._span_overlay.bars() == []
    assert win._span_overlay.isHidden()
    assert not win._span_overlay.grab().isNull()  # 그려도 예외가 없다(pytest-qt가 이벤트 루프 예외를 실패로 센다)
    monkeypatch.setattr(db, "get_occurrences", real)
    win._refresh_month_data()
    qtbot.wait(80)
    assert win._span_overlay.isVisible() and len(win._span_overlay.bar_rects()) == 1


def row_budget_cell(qtbot, rows):
    """칩 자리가 정확히 rows줄인 중간 칸(화면 크기와 무관하게 칸 크기를 고정한다)."""
    cell = CalendarDayButton(14, False, [], True, "2026-10-14", False, 3, 0, "expanded",
                             calendar_scale="medium")
    qtbot.addWidget(cell)
    per = cell.chip_height + cell.chip_spacing
    cell.setFixedSize(120, 33 + rows * per + 1)  # 숫자 26 + 위 여백 4 + 아래 여백 3
    cell.show()
    qtbot.waitUntil(lambda: cell.chips_container.height() // per == rows)
    return cell


@pytest.mark.parametrize("rows", [2, 3, 4])
@pytest.mark.parametrize("lanes", [[], [0], [0, 1], [0, 1, 2], [2], [1, 0]])
@pytest.mark.parametrize("singles", [0, 1, 2, 3, 5])
def test_cell_rows_never_exceed_budget_and_overflow_counts_everything(qtbot, rows, lanes, singles):
    """막대 차선이 있어도 칸은 칩 자리 예산을 넘지 않고, '+N 더'는 못 보인 막대·일정을 다 센다."""
    cell = row_budget_cell(qtbot, rows)
    events = [{"content": f"하루 {i}", "color": "#FFD166"} for i in range(singles)]
    cell.set_events(events, span_lanes=lanes)
    layout = cell.chips_layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    slots = [w for w in widgets if w.objectName() == "calendarSpanSlot"]
    rest = [w for w in widgets if w.objectName() != "calendarSpanSlot"]
    overflow = [w for w in rest if w.text().endswith(" 더")]
    chips = [w for w in rest if not w.text().endswith(" 더")]
    assert len(widgets) <= rows
    assert len(slots) == min(max(lanes, default=-1) + 1, cell.span_lane_cap)
    hidden = sum(1 for lane in lanes if lane >= len(slots))
    if overflow:
        assert overflow == rest[-1:]
        assert overflow[0].text() == f"+{singles - len(chips) + hidden} 더"
    else:
        assert hidden == 0 and len(chips) == singles


def test_two_bars_and_two_singles_keep_the_row_budget_and_week_heights(qtbot, monkeypatch):
    """두 막대 + 하루 일정 둘이 한 날에 몰려도 그 칸은 하루 일정 셋과 같은 줄 수·최소 높이이고 주 줄도 커지지 않는다."""
    win = calendar_window(qtbot, monkeypatch, "medium")

    def heights():
        return [win.calendar_grid.cellRect(row, 0).height() for row in range(win.calendar_grid.rowCount())]

    db.add_schedule("2026-10-13", "기간 하나", options=ScheduleOptions(end_date="2026-10-15"))
    db.add_schedule("2026-10-14", "기간 둘", options=ScheduleOptions(end_date="2026-10-16"))
    db.add_schedule("2026-10-14", "하루 하나")
    db.add_schedule("2026-10-14", "하루 둘")
    for index in range(3):  # 막대 없는 기존 규칙의 3줄 칸(비교 기준)
        db.add_schedule("2026-10-21", f"기준 {index}")
    win._refresh_month_data()
    qtbot.wait(120)
    crowded, reference = win._day_cells["2026-10-14"], win._day_cells["2026-10-21"]
    assert crowded.chips_layout.count() == reference.chips_layout.count()
    assert crowded.minimumSizeHint().height() == reference.minimumSizeHint().height()
    assert max(heights()) - min(heights()) <= 1  # 남는 픽셀 나눔 1px 외에는 모든 주 줄이 같다
