"""모니터 구성 변경(KVM 전환·해상도 변경) 시 캘린더 기하 복원 회귀 테스트.

`medium`/`large`는 화면 크기에 비례하는 스케일이다. 가로 모니터 기준으로
만들어진 창을 세로 모니터로 복원할 때 좌표만 보정하면 폭이 화면을 넘어
우측이 잘린다(설정 버튼이 화면 밖으로 나감).
"""

from PySide6.QtCore import QRect

import database as db
from ui_main import MainCalendarWindow


class _FakeScreen:
    def __init__(self, geometry):
        self._geometry = geometry

    def availableGeometry(self):
        return self._geometry


LANDSCAPE = QRect(0, 0, 1920, 1080)
PORTRAIT = QRect(1920, 0, 1080, 1920)


def _fits_inside(win, screen) -> bool:
    geo = screen.availableGeometry()
    return (
        win.width() <= geo.width()
        and win.height() <= geo.height()
        and geo.left() <= win.x()
        and geo.top() <= win.y()
        and win.x() + win.width() <= geo.left() + geo.width()
        and win.y() + win.height() <= geo.top() + geo.height()
    )


def _make_large_window_on(screen, qtbot, monkeypatch):
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_get_target_screen", lambda: screen)
    win._apply_calendar_scale()
    return win


def test_large_calendar_fits_portrait_monitor_after_screen_change(
        app_dir, qtbot, monkeypatch):
    """KVM 전환으로 가로→세로 모니터로 복원돼도 창이 화면 안에 들어와야 한다."""
    win = _make_large_window_on(_FakeScreen(LANDSCAPE), qtbot, monkeypatch)

    # 전제: 가로 기준 large 폭은 세로 모니터 폭보다 넓다.
    assert win.width() > PORTRAIT.width()

    portrait = _FakeScreen(PORTRAIT)
    monkeypatch.setattr(win, "_get_target_screen", lambda: portrait)
    win._on_screen_changed()

    assert _fits_inside(win, portrait), (
        f"창 {win.width()}x{win.height()} @({win.x()},{win.y()}) 가 "
        f"세로 모니터 {PORTRAIT} 를 벗어남"
    )


def test_large_calendar_fits_landscape_monitor_after_screen_change(
        app_dir, qtbot, monkeypatch):
    """반대 방향(세로→가로)도 같은 규칙이 적용돼야 한다."""
    win = _make_large_window_on(_FakeScreen(PORTRAIT), qtbot, monkeypatch)

    assert win.height() > LANDSCAPE.height()

    landscape = _FakeScreen(LANDSCAPE)
    monkeypatch.setattr(win, "_get_target_screen", lambda: landscape)
    win._on_screen_changed()

    assert _fits_inside(win, landscape), (
        f"창 {win.width()}x{win.height()} @({win.x()},{win.y()}) 가 "
        f"가로 모니터 {LANDSCAPE} 를 벗어남"
    )


def test_screen_change_keeps_scale_geometry_contract(app_dir, qtbot, monkeypatch):
    """복원된 크기는 목적지 화면 기준 스케일 계산 결과와 같아야 한다."""
    win = _make_large_window_on(_FakeScreen(LANDSCAPE), qtbot, monkeypatch)

    portrait = _FakeScreen(PORTRAIT)
    monkeypatch.setattr(win, "_get_target_screen", lambda: portrait)
    win._on_screen_changed()

    expected = win._calendar_scale_geometry("large", portrait)
    assert (win.width(), win.height()) == expected


def test_compact_scale_is_unaffected_by_screen_change(app_dir, qtbot, monkeypatch):
    """compact는 고정 폭이므로 화면이 바뀌어도 폭이 유지돼야 한다."""
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    landscape = _FakeScreen(LANDSCAPE)
    monkeypatch.setattr(win, "_get_target_screen", lambda: landscape)
    win._apply_calendar_scale()
    before = (win.width(), win.height())

    portrait = _FakeScreen(PORTRAIT)
    monkeypatch.setattr(win, "_get_target_screen", lambda: portrait)
    win._on_screen_changed()

    assert (win.width(), win.height()) == before
    assert _fits_inside(win, portrait)
