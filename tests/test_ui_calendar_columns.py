"""일정 칩이 날짜 열 너비를 역으로 결정하지 않는지 실제 배치로 검사한다."""

from datetime import date

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QGridLayout, QWidget

import database as db
import security
from ui_main import CalendarDayButton, MainCalendarWindow


class _Screen:
    def __init__(self, width, height):
        self.geometry = QRect(0, 0, width, height)

    def availableGeometry(self):
        return self.geometry


def _seed_weekday_schedules():
    dates = {}
    for day in range(1, 29):
        target = date.today().replace(day=day)
        col = (target.weekday() + 1) % 7
        dates.setdefault(col, target.isoformat())
        if col in (1, 2, 3, 4):
            db.add_schedule(target.isoformat(), "📌 합성 일정 현장 점검 회의 자료 검토 " * 4)
    return dates


def _make_window(scale, screen, qtbot, monkeypatch):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(MainCalendarWindow, "_get_target_screen", lambda self: screen)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(100)
    return win


def _assert_columns_and_headers(win):
    rects = [win.calendar_grid.cellRect(1, col) for col in range(7)]
    widths = [rect.width() for rect in rects]
    assert min(widths) > 0
    assert max(widths) - min(widths) <= 1, widths
    section = win.right_content.findChild(QWidget, "calendarSection")
    # 요일 제목은 같은 부모의 별도 그리드이며 날짜 열 중심과 일치해야 한다.
    headers = [
        item for item in section.findChildren(QGridLayout)
        if item is not win.calendar_grid and item.count() == 7
    ]
    assert len(headers) == 1
    for col, rect in enumerate(rects):
        label = headers[0].itemAtPosition(0, col).widget()
        assert abs(label.geometry().center().x() - rect.center().x()) <= 1
    return widths


@pytest.mark.parametrize("scale,width,height", [
    ("large", 1080, 1920),
    ("large", 864, 1536),
    ("large", 720, 1280),
    ("medium", 1440, 2560),
    ("compact", 1080, 1920),
])
def test_columns_stay_aligned_after_add_month_and_screen_roundtrip(
        app_dir, qtbot, monkeypatch, scale, width, height):
    dates = _seed_weekday_schedules()
    portrait = _Screen(width, height)
    win = _make_window(scale, portrait, qtbot, monkeypatch)
    initial = _assert_columns_and_headers(win)

    for col in (5, 6):
        db.add_schedule(dates[col], "금토 일정 검토 회의")
        win._refresh_cell_for_date(dates[col])
    qtbot.wait(100)
    assert _assert_columns_and_headers(win) == initial

    win._on_next_month()
    qtbot.wait(50)
    win._on_today()
    qtbot.wait(100)
    assert _assert_columns_and_headers(win) == initial

    monkeypatch.setattr(win, "_get_target_screen", lambda: _Screen(1920, 1080))
    win._on_screen_changed()
    qtbot.wait(100)
    _assert_columns_and_headers(win)
    monkeypatch.setattr(win, "_get_target_screen", lambda: portrait)
    win._on_screen_changed()
    qtbot.wait(100)
    assert _assert_columns_and_headers(win) == initial


@pytest.mark.parametrize("scale", ["medium", "large"])
def test_chip_text_fits_actual_width_and_recovers_on_expansion(qtbot, scale):
    text = "📌 전체 합성 일정 제목 — 현장 점검 회의"
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 150)
    cell = CalendarDayButton(
        11, False, [db.DEFAULT_SCHEDULE_COLOR], True, "2026-09-11",
        weekday_col=5, count=1, mode="expanded", calendar_scale=scale, parent=host,
    )
    cell.resize(68, 110)
    cell.set_events([{"content": text, "color": db.DEFAULT_SCHEDULE_COLOR}])
    host.show()
    for width in (68, 360, 68):
        cell.resize(width, 110)
        qtbot.wait(100)
        assert cell.width() == width
        chip = cell._chips_layout.itemAt(0).widget()
        assert chip.toolTip() == text
        assert chip.text()
        assert chip.fontMetrics().horizontalAdvance(chip.text()) <= chip.contentsRect().width()
        assert cell.rect().contains(chip.mapTo(cell, QPoint(0, 0)))
        assert cell.rect().contains(chip.mapTo(cell, chip.rect().bottomRight()))
        if width == 360:
            assert chip.text() == text
        else:
            assert chip.text() != text


def test_calendar_display_roundtrip_preserves_existing_rows_and_salt(
        app_dir, qtbot, monkeypatch):
    _seed_weekday_schedules()
    db.save_memo(date.today().isoformat(), "기존 메모 Unicode ☐ ☑ 👨‍👩‍👧‍👦")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")

    def snapshot():
        with db._connection(read_only=True, enable_wal=False) as conn:
            return (
                [tuple(row) for row in conn.execute("SELECT * FROM schedules ORDER BY id")],
                [tuple(row) for row in conn.execute("SELECT * FROM memos ORDER BY id")],
                [tuple(row) for row in conn.execute("SELECT * FROM app_settings ORDER BY key")],
                conn.execute("PRAGMA user_version").fetchone()[0],
                security.read_existing_salt(),
            )

    before = snapshot()
    exported = db.export_all_data()
    win = _make_window("large", _Screen(864, 1536), qtbot, monkeypatch)
    win._on_next_month()
    qtbot.wait(50)
    win._on_today()
    qtbot.wait(100)
    assert win.prepare_for_quit()
    assert snapshot() == before
    assert db.export_all_data() == exported
