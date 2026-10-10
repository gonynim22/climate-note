"""디자인 점검 12번: 기본 크기 날짜 칸은 색 네모로 다 보이지 못한 일정 수만 '+N'으로 보인다."""
import pytest

import database as db
import ui_main
from ui_main import MainCalendarWindow


@pytest.mark.parametrize("colors,count,expected", [
    ([], 0, ""),
    (["#FFD166"], 1, ""),
    (["#FFD166"], 3, "+2"),                         # 같은 색 3개 → 네모 1개 + 2개 더
    (["#FFD166", "#4CC9F0"], 3, "+1"),
    (["#FFD166", "#4CC9F0", "#FF6B6B"], 3, ""),     # 네모 3개가 일정 3개를 다 보인다
    (["#FFD166", "#4CC9F0", "#FF6B6B"], 5, "+2"),
])
def test_count_shows_only_schedules_not_drawn_as_squares(qtbot, colors, count, expected):
    cell = ui_main.CalendarDayButton(10, False, colors, True, "2026-07-10", False, 5, count, "compact")
    qtbot.addWidget(cell)
    assert cell.count_label.text() == expected


def test_live_update_follows_the_same_rule(qtbot, app_dir):
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._current_year, win._current_month = 2026, 7
    win._refresh_calendar()
    win._on_date_selected("2026-07-15")
    win._schedule_color = "#FFD166"
    for text in ("가", "나", "다"):
        win.schedule_input.setText(text)
        win._on_add_schedule()
    assert win._day_cells["2026-07-15"].count_label.text() == "+2"
    assert db.get_all_schedule_date_counts()["2026-07-15"] == 3
