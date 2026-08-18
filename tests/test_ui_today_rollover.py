"""트레이 상주 앱이 자정을 넘길 때 '오늘' 동기화 회귀 테스트.

버그: 오늘 날짜는 __init__에서 date.today()로 1회만 계산되는데, 앱이 트레이에
상주(setQuitOnLastWindowClosed(False))한 채 자정을 넘기면 캘린더가 어제에 박제된다.
'오늘' 버튼만 재계산했다. 다시 보일 때 오늘로 재동기화되어야 한다.
"""
from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from ui_main import MainCalendarWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_sync_jumps_to_today_after_day_change(qtbot, app_dir, qapp):
    """다시 보일 때(날짜 변경됨): 오늘 날짜·이번 달로 이동해 선택한다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    # 어제 생성돼 박제된 상태 모사
    y = date.today() - timedelta(days=1)
    win._today = y.isoformat()
    win._current_year, win._current_month = y.year, y.month
    win._selected_date = y.isoformat()

    win._sync_to_today_if_changed()

    t = date.today()
    assert win._today == t.isoformat()
    assert win._selected_date == t.isoformat()
    assert (win._current_year, win._current_month) == (t.year, t.month)


def test_sync_is_noop_when_same_day(qtbot, app_dir, qapp):
    """같은 날이면 사용자가 보던 달을 강제로 오늘로 옮기지 않는다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._on_next_month()  # 일부러 다음 달로 이동
    viewing = (win._current_year, win._current_month)

    win._sync_to_today_if_changed()  # 오늘은 안 바뀜 → 아무 변화 없어야

    assert (win._current_year, win._current_month) == viewing


def test_rollover_while_visible_refreshes_highlight_keeps_view(qtbot, app_dir, qapp):
    """표시 중 자정을 넘기면 오늘 값만 갱신하고 보던 달·선택은 유지한다."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    assert win.isVisible()
    win._on_next_month()  # 다른 달을 보는 중
    other = (win._current_year, win._current_month)
    win._selected_date = f"{other[0]:04d}-{other[1]:02d}-15"
    win._today = (date.today() - timedelta(days=1)).isoformat()  # 자정 넘김 직전 모사

    win._check_day_rollover()

    assert win._today == date.today().isoformat()      # 오늘 값 갱신
    assert (win._current_year, win._current_month) == other      # 보던 달 유지
    assert win._selected_date == f"{other[0]:04d}-{other[1]:02d}-15"  # 선택 유지


def test_rollover_hidden_does_not_consume_change(qtbot, app_dir, qapp):
    """숨김 상태에서 날짜가 바뀌어도 _today를 소비하지 않아야(다음 show에서 이동하도록)."""
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.hide()
    stale = (date.today() - timedelta(days=1)).isoformat()
    win._today = stale

    win._check_day_rollover()  # 숨김이면 아무 것도 하지 않아야

    assert win._today == stale  # 그대로 → 이후 show 시 _sync가 이동 트리거
