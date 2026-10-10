"""디자인 점검 15번: 중간·크게 모드 날짜 칸(숫자 왼쪽 위, 오늘은 숫자 원, 고른 날 테두리, 요일 글자)."""
from datetime import date

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

import database as db
from ui_main import MainCalendarWindow

NAVY = "#01295f"


@pytest.fixture(autouse=True)
def quiet_desktop(app_dir):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _window(qtbot, scale):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    db.add_schedule(date.today().isoformat(), "오늘 일정", "#4CC9F0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    QApplication.processEvents()
    return win


def _pixel(win, widget, point):
    image = win.grab().toImage()
    ratio = image.devicePixelRatio()
    at = widget.mapTo(win, point)
    return image.pixelColor(int(at.x() * ratio), int(at.y() * ratio))


@pytest.mark.parametrize("scale", ["medium", "large"])
def test_expanded_cell_number_top_left_and_today_circle(qtbot, scale):
    win = _window(qtbot, scale)
    cell = win._day_cells[date.today().isoformat()]
    label = cell.day_label
    assert label.geometry().left() <= 6 and label.geometry().top() <= 6  # 칩과 같은 왼쪽 기준선
    assert label.width() == label.height() == 26
    # 오늘은 숫자 뒤 원만 남색이고, 칸 아래쪽(칩 자리)은 남색으로 덮지 않는다.
    assert _pixel(win, label, QPoint(3, label.height() // 2)).name() == NAVY
    corner = _pixel(win, cell, QPoint(cell.width() - 4, cell.height() - 4))
    assert corner.name() != NAVY and corner.lightness() > 200


@pytest.mark.parametrize("scale", ["medium", "large"])
def test_expanded_selected_day_uses_border_not_fill(qtbot, scale):
    win = _window(qtbot, scale)
    today = date.today()
    other = today.replace(day=1 if today.day != 1 else 2).isoformat()
    win._on_date_selected(other)
    QApplication.processEvents()
    cell = win._day_cells[other]
    assert _pixel(win, cell, QPoint(cell.width() // 2, 1)).name() == NAVY  # 위 2px 테두리(배율 반올림 고려해 y=1)
    inside = _pixel(win, cell, QPoint(cell.width() - 6, cell.height() // 2))
    assert inside.lightness() > 230  # 바탕은 채우지 않는다


@pytest.mark.parametrize("scale,size,align", [
    ("compact", 11, Qt.AlignCenter), ("medium", 12, Qt.AlignLeft), ("large", 13, Qt.AlignLeft)])
def test_weekday_header_size_and_alignment_follow_scale(qtbot, scale, size, align):
    win = _window(qtbot, scale)
    for label in win._weekday_labels:
        assert f"font-size: {size}px" in label.styleSheet()
        assert label.alignment() & align == align


def test_compact_today_keeps_full_navy_cell(qtbot):
    win = _window(qtbot, "compact")
    cell = win._day_cells[date.today().isoformat()]
    assert _pixel(win, cell, QPoint(cell.width() // 2, cell.height() - 4)).name() == NAVY
