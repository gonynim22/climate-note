"""v4.9 날짜 칸 구분선(A안 · 가는 격자선, 설정 스위치 · 기본 꺼짐). 표시 전용이며 합성 데이터만 쓴다.

선은 칸과 칸 사이 1px 틈에만 있고 바깥 틀은 없다. 선을 켜면 오늘·고른 날·공휴일 테마 칸의 채움이 선에서
2px 안쪽으로 들어간다. 끄면(키가 없을 때도) v4.8과 같은 모양이다.
"""
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

import database as db
import holiday_theme as ht
import ui_main
from holidays import KOREAN_HOLIDAYS
from schedule_rules import ScheduleOptions
from ui_main import MainCalendarWindow
from ui_settings import SettingsWindow
from test_ui_calendar_columns import _Screen, _assert_columns_and_headers, _make_window

LINE = "#e3e6ea"
WHITE = "#ffffff"
NAVY = "#01295f"
LIGHT_FILL = (235, 238, 242)  # rgba(1,41,95,20)를 흰 칸 바탕에 얹은 색


@pytest.fixture(autouse=True)
def quiet_desktop(app_dir):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _window(qtbot, scale, *, lines=True, month=(2026, 10)):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    if lines is not None:
        db.save_setting(db.SETTING_CALENDAR_GRID_LINES, "1" if lines else "0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    win._current_year, win._current_month = month
    win._refresh_calendar()
    QApplication.processEvents()
    return win


def _shot(win):
    image = win.grab().toImage()
    return image, image.devicePixelRatio()


def _px(shot, win, widget, x, y):
    """widget 안 논리 좌표 (x, y) 화소의 가운데에 놓인 장치 화소 색."""
    image, ratio = shot
    at = widget.mapTo(win, QPoint(0, 0))
    return image.pixelColor(int((at.x() + x + 0.5) * ratio), int((at.y() + y + 0.5) * ratio))


def _near(color, rgb, tol=3):
    return all(abs(a - b) <= tol for a, b in zip((color.red(), color.green(), color.blue()), rgb))


def _blank(color):
    """흰 바탕(배율이 1이 아니면 채움 가장자리의 부드럽게 한 몇 % 번짐까지는 흰 바탕으로 본다)."""
    return min(color.red(), color.green(), color.blue()) >= 248


def _outer(shot):
    """채움 바깥을 볼 칸 끝에서의 거리(논리 px). 배율 1은 채움 바로 바깥(1px)을 정확히 본다.

    1.25·1.5배는 장치 화소 하나가 채움 경계(2px)에 걸쳐 칸 위치에 따라 최대 25%까지 섞이므로
    (2026-11-11 날짜가 바뀌어 오늘 칸 열이 달라지자 남색이 25% 섞였다) 칸 끝 화소(0px)를 본다.
    """
    return 1 if shot[1] == 1 else 0


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_lines_off_when_key_missing_keeps_previous_look(qtbot, scale):
    win = _window(qtbot, scale, lines=None)
    assert db.get_setting(db.SETTING_CALENDAR_GRID_LINES, "missing") == "missing"
    assert not win._grid_lines_overlay.isVisible()
    assert win.calendar_grid.spacing() == 2 and win._weekday_grid.spacing() == 2
    shot = _shot(win)
    left, right = win._grid_cells[1][2], win._grid_cells[1][3]
    mid = left.height() // 2
    assert right.mapTo(win, QPoint(0, 0)).x() - left.mapTo(win, QPoint(left.width(), 0)).x() == 2
    assert _px(shot, win, left, left.width(), mid).name() == WHITE  # 틈은 흰 바탕 그대로


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_lines_sit_in_gaps_only_without_outer_frame(qtbot, scale):
    win = _window(qtbot, scale)  # 2026년 10월: 1일이 목요일이라 첫 주 앞 네 칸이 빈 칸이다
    rows = win._grid_cells
    assert win._grid_lines_overlay.isVisible()
    assert win.calendar_grid.spacing() == 1 and win._weekday_grid.spacing() == 1
    xs, ys = win._grid_lines_overlay.line_positions()
    assert len(xs) == 6 and len(ys) == len(rows) - 1
    shot = _shot(win)
    for row in (rows[0], rows[-1]):  # 빈 칸 사이에도 선이 이어진다
        for left, right in zip(row, row[1:]):
            mid = left.height() // 2
            gap = left.mapTo(win, QPoint(left.width(), 0)).x()
            assert right.mapTo(win, QPoint(0, 0)).x() == gap + 1  # 틈 1px
            assert _px(shot, win, left, left.width(), mid).name() == LINE
    for upper in rows[:-1]:
        cell = upper[3]
        assert _px(shot, win, cell, cell.width() // 2, cell.height()).name() == LINE
    first, last = rows[0][0], rows[-1][-1]
    assert _px(shot, win, first, -1, first.height() // 2).name() == WHITE   # 왼쪽 바깥
    assert _px(shot, win, first, first.width() // 2, -1).name() == WHITE    # 요일 머리줄과 첫 주 사이
    assert _px(shot, win, last, last.width(), last.height() // 2).name() == WHITE  # 오른쪽 바깥
    assert _px(shot, win, last, last.width() // 2, last.height()).name() == WHITE  # 아래 바깥


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_selected_fill_stays_two_pixels_inside_lines(qtbot, scale):
    win = _window(qtbot, scale)
    for day in range(11, 18):  # 일~토 일곱 열: 칸 위치마다 소수 화소 경계가 다르다
        key = f"2026-10-{day}"
        win._on_date_selected(key)
        QApplication.processEvents()
        cell = win._day_cells[key]
        shot = _shot(win)
        w, h = cell.width(), cell.height()
        mid_x, mid_y = w // 2, h // 2
        o = _outer(shot)
        for x, y in ((o, mid_y), (w - 1 - o, mid_y), (mid_x, o), (mid_x, h - 1 - o), (2, 2)):
            assert _blank(_px(shot, win, cell, x, y)), (key, x, y)  # 선에 붙은 2px과 둥근 모서리는 비운다
        # 배율 1에서는 바로 2px부터 채움이다. 1.25·1.5배는 경계 화소가 섞이므로 한 칸 더 안쪽을 본다.
        inset = 2 if shot[1] == 1 else 3
        for x, y in ((inset, mid_y), (w - 1 - inset, mid_y), (mid_x, inset), (mid_x, h - 1 - inset)):
            assert _near(_px(shot, win, cell, x, y), LIGHT_FILL), (key, x, y)


class _FixedToday(date):
    """'오늘'을 고정한다(오늘 칸이 어느 열에 오든 같은 결과인지 보려고)."""
    fixed = date(2026, 10, 14)

    @classmethod
    def today(cls):
        return cls.fixed


@pytest.mark.parametrize("day", range(11, 18))  # 일~토 일곱 열
def test_compact_today_fill_stays_two_pixels_inside_lines(qtbot, monkeypatch, day):
    monkeypatch.setattr(_FixedToday, "fixed", date(2026, 10, day))
    monkeypatch.setattr(ui_main, "date", _FixedToday)
    win = _window(qtbot, "compact")
    cell = win._day_cells[f"2026-10-{day}"]
    assert cell._is_today
    shot = _shot(win)
    mid_y = cell.height() // 2
    o = _outer(shot)
    assert _blank(_px(shot, win, cell, o, mid_y)) and _blank(_px(shot, win, cell, cell.width() - 1 - o, mid_y))
    inset = 2 if shot[1] == 1 else 3
    assert _px(shot, win, cell, inset, mid_y).name() == NAVY
    assert _px(shot, win, cell, cell.width() - 1 - inset, mid_y).name() == NAVY


def test_holiday_theme_tint_and_dot_stay_inside_fill(qtbot, monkeypatch):
    fixed = ht.resolve_holiday_theme(date(2027, 2, 7), KOREAN_HOLIDAYS)
    monkeypatch.setattr(ht, "current_match", lambda today=None: fixed)
    win = _window(qtbot, "medium", month=(2027, 2))
    cell = win._day_cells["2027-02-08"]
    shot = _shot(win)
    mid_y = cell.height() // 2
    assert _blank(_px(shot, win, cell, _outer(shot), mid_y))
    tint = _px(shot, win, cell, 2, mid_y)
    assert tint.name() != WHITE and tint.name() == fixed.theme.tint.lower()
    dot = cell.findChild(QWidget, "holidayThemeDot")
    fill = cell.rect().adjusted(2, 2, -2, -2)
    assert dot is not None and fill.contains(dot.geometry())


@pytest.mark.parametrize("scale,width,height", [
    ("large", 1080, 1920), ("medium", 1440, 2560), ("compact", 1080, 1920),
])
def test_columns_stay_equal_with_lines(app_dir, qtbot, monkeypatch, scale, width, height):
    db.save_setting(db.SETTING_CALENDAR_GRID_LINES, "1")
    for day in range(1, 29):
        target = date.today().replace(day=day)
        if (target.weekday() + 1) % 7 in (1, 2, 3, 4):
            db.add_schedule(target.isoformat(), "📌 합성 일정 현장 점검 회의 자료 검토 " * 4)
    win = _make_window(scale, _Screen(width, height), qtbot, monkeypatch)
    assert win._grid_lines_overlay.isVisible()
    initial = _assert_columns_and_headers(win)
    win._on_next_month()
    qtbot.wait(50)
    win._on_today()
    qtbot.wait(100)
    assert _assert_columns_and_headers(win) == initial


def test_span_bar_keeps_chip_line_and_covers_vertical_line(app_dir, qtbot, monkeypatch):
    db.save_schedule_palette(("#80CFA9", "#8FA8FF", "#F28BB5"))
    db.add_schedule("2026-10-13", "출장", "#4CC9F0", options=ScheduleOptions(end_date="2026-10-15"))
    db.add_schedule("2026-10-13", "같은 날 회의")
    db.save_setting(db.SETTING_CALENDAR_GRID_LINES, "1")
    # 화면 크기를 고정한다. 합성 배율(1.25·1.5)의 작은 논리 화면에서는 칸에 막대 차선 자리가 없어
    # 막대가 규칙대로 숨고 '+N 더'로 세어진다(구분선과 무관한 기존 동작).
    win = _make_window("medium", _Screen(1920, 1080), qtbot, monkeypatch)
    win._current_year, win._current_month = 2026, 10
    win._refresh_calendar()
    QApplication.processEvents()
    overlay = win._span_overlay
    (bar, rect), = overlay.bar_rects()
    start = win._day_cells["2026-10-13"]
    chip = start._chips_layout.itemAt(start._chips_layout.count() - 1).widget()
    section = win._calendar_section
    chip_left = chip.mapTo(section, QPoint(0, 0)).x() - overlay.x()
    assert rect.left() == chip_left  # 칩과 같은 시작선
    shot = _shot(win)
    gap = start.mapTo(win, QPoint(start.width(), 0)).x()
    y = overlay.mapTo(win, QPoint(0, int(rect.center().y()))).y()
    image, ratio = shot
    color = image.pixelColor(int((gap + 0.5) * ratio), int((y + 0.5) * ratio))
    assert color.name() == "#8fa8ff"  # 막대가 세로선 위를 지나간다


def test_drawing_lines_writes_nothing(qtbot, monkeypatch):
    win = _window(qtbot, "large")
    def boom(*args, **kwargs):
        raise AssertionError("구분선 그리기가 DB에 쓰려 했다")
    for name in dir(db):
        if name.startswith(("save_", "update_", "create_", "add_", "delete_", "trash_",
                            "restore_", "import_", "reset_", "backup_")) and callable(getattr(db, name)):
            monkeypatch.setattr(db, name, boom)
    win._refresh_calendar()
    win._on_next_month()
    win._on_prev_month()
    win.resize(win.width() - 40, win.height())
    QApplication.processEvents()
    assert win.grab().toImage().width() > 0
    assert win._grid_lines_overlay.isVisible()


@pytest.mark.parametrize("failing_key", ["calendar_grid_lines_enabled", "show_lunar"])
def test_failed_setting_read_during_refresh_leaves_no_dead_cells(qtbot, monkeypatch, failing_key):
    """칸을 지운 뒤 설정 읽기가 실패해도 오버레이가 지워진 칸을 쥐고 그리다 오류를 내지 않는다."""
    win = _window(qtbot, "compact")
    assert win._grid_lines_overlay.isVisible()
    real = db.get_setting

    def failing(key, default=""):
        if key == failing_key:
            raise sqlite3.OperationalError("합성 실패")
        return real(key, default)

    monkeypatch.setattr(db, "get_setting", failing)
    with pytest.raises(sqlite3.OperationalError):
        win._refresh_calendar()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)  # 옛 칸이 실제로 지워진다
    QApplication.processEvents()
    win._grid_lines_overlay.update()
    win._span_overlay.update()
    assert win._calendar_section.grab().width() > 0
    xs, ys = win._grid_lines_overlay.line_positions()
    assert (xs, ys) == ([], [])


def test_settings_switch_shares_holiday_row_and_applies_live(qtbot):
    win = _window(qtbot, "medium", lines=None)
    settings = SettingsWindow(on_grid_lines_changed=win._on_grid_lines_setting_changed)
    qtbot.addWidget(settings)
    settings.show()
    qtbot.waitExposed(settings)
    switch = settings.grid_lines_switch
    assert not switch.isChecked()  # 키가 없으면 꺼짐
    rows = [r for r in settings.findChildren(QWidget, "settingsRow")
            if r.isAncestorOf(settings.holiday_theme_switch)]
    assert len(rows) == 1 and rows[0].isAncestorOf(switch)
    assert rows[0].minimumHeight() == 36 and rows[0].height() == 36
    label = next(w for w in rows[0].findChildren(QLabel) if w.text() == "칸 구분선")
    assert label.toolTip() and switch.toolTip() == label.toolTip()
    # 공휴일 테마 스위치는 왼쪽 절반, 칸 구분선 스위치는 다른 행 스위치와 같은 오른쪽 끝
    lunar_right = settings.lunar_switch.mapTo(settings, QPoint(settings.lunar_switch.width(), 0)).x()
    assert switch.mapTo(settings, QPoint(switch.width(), 0)).x() == lunar_right
    holiday_right = settings.holiday_theme_switch.mapTo(
        settings, QPoint(settings.holiday_theme_switch.width(), 0)).x()
    assert holiday_right < label.mapTo(settings, QPoint(0, 0)).x()
    switch.setChecked(True)
    assert db.get_setting(db.SETTING_CALENDAR_GRID_LINES) == "1"
    assert win._grid_lines_overlay.isVisible() and win.calendar_grid.spacing() == 1
    switch.setChecked(False)
    assert db.get_setting(db.SETTING_CALENDAR_GRID_LINES) == "0"
    assert not win._grid_lines_overlay.isVisible() and win.calendar_grid.spacing() == 2


def test_switch_saves_only_its_key(qtbot, monkeypatch):
    saved, calls = [], []
    real_save = db.save_setting
    monkeypatch.setattr(db, "save_setting", lambda k, v: (saved.append((k, v)), real_save(k, v)))
    settings = SettingsWindow(on_grid_lines_changed=lambda: calls.append(1))
    qtbot.addWidget(settings)
    settings.grid_lines_switch.setChecked(True)
    settings.grid_lines_switch.setChecked(False)
    assert saved == [("calendar_grid_lines_enabled", "1"), ("calendar_grid_lines_enabled", "0")]
    assert calls == [1, 1]


def test_import_or_reset_reapplies_switch(qtbot):
    win = _window(qtbot, "compact", lines=None)
    assert not win._grid_lines_overlay.isVisible()
    db.save_setting(db.SETTING_CALENDAR_GRID_LINES, "1")  # 가져온 파일이 켠 경우
    win._on_import_complete()
    QApplication.processEvents()
    assert win._grid_lines_overlay.isVisible() and win.calendar_grid.spacing() == 1


def _line_columns(image, y, x_from, x_to):
    return [x for x in range(x_from, x_to) if image.pixelColor(x, y).name() == LINE]


def test_lines_are_one_device_pixel_wide(qtbot):
    """배율이 1이 아니어도 선은 장치 1픽셀이고 양옆은 흰 바탕이다(흐리거나 두께가 들쭉날쭉하지 않다)."""
    win = _window(qtbot, "medium")
    image, ratio = _shot(win)
    rows = win._grid_cells
    for left, right in zip(rows[2], rows[2][1:]):
        y = int((left.mapTo(win, QPoint(0, left.height() // 2)).y() + 0.5) * ratio)
        start = int(left.mapTo(win, QPoint(left.width() - 1, 0)).x() * ratio)
        end = int((right.mapTo(win, QPoint(1, 0)).x() + 1) * ratio)
        columns = _line_columns(image, y, start, end)
        assert len(columns) == 1, (columns, start, end, ratio)
        assert image.pixelColor(columns[0] - 1, y).name() == WHITE
        assert image.pixelColor(columns[0] + 1, y).name() == WHITE
    cell, below = rows[1][3], rows[2][3]
    x = int((cell.mapTo(win, QPoint(cell.width() // 2, 0)).x() + 0.5) * ratio)
    top = int(cell.mapTo(win, QPoint(0, cell.height() - 1)).y() * ratio)
    bottom = int((below.mapTo(win, QPoint(0, 1)).y() + 1) * ratio)
    hits = [y for y in range(top, bottom) if image.pixelColor(x, y).name() == LINE]
    assert len(hits) == 1, (hits, top, bottom, ratio)


@pytest.mark.parametrize("factor", ["1.25", "1.5"])
def test_lines_and_fill_at_scale_factors(factor):
    """QT_SCALE_FACTOR는 프로세스 단위라 하위 프로세스에서 같은 검사를 돌린다."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_ui_calendar_grid_lines.py::test_lines_are_one_device_pixel_wide",
         "tests/test_ui_calendar_grid_lines.py::test_lines_sit_in_gaps_only_without_outer_frame",
         "tests/test_ui_calendar_grid_lines.py::test_selected_fill_stays_two_pixels_inside_lines"],
        env={**os.environ, "QT_SCALE_FACTOR": factor},
        cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
