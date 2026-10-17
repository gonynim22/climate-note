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


def test_editor_summary_and_option_save_apply_to_whole_series(qtbot):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    editor = win._schedule_editor
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    QApplication.processEvents()
    assert editor.summary_label.text() == "10:00 · 10분 전 · 매주 월요일 · 모든 날에 적용"
    assert editor.summary_label.isVisible()
    row = win.schedule_list.itemWidget(item)
    assert row.rect().contains(editor.geometry())
    assert editor.rect().contains(editor.options_button.geometry())
    editor.options_button.set_options(ScheduleOptions(start_time="10:00", repeat_rule="weekly",
                                                      alarm_before=30))
    assert win._finish_current_edit(True)
    assert db.get_schedules("2026-10-19")[0]["options"].alarm_before == 30
    qtbot.waitUntil(lambda: win.schedule_list.item(0).data(Qt.UserRole + 4).alarm_before == 30)
    assert win.schedule_list.item(0).data(Qt.UserRole) == sid


def test_text_only_edit_keeps_option_tooltip(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    win._schedule_editor.edit.setText("주간 업무 회의")
    assert win._finish_current_edit(True)
    label = win.schedule_list.itemWidget(item).schedule_text_label
    assert label.text() == "주간 업무 회의"
    assert label.toolTip().splitlines()[0] == "주간 업무 회의"
    assert "알림: 10분 전" in label.toolTip()


def test_turning_off_repeat_from_another_day_explains_first_date(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0))
    button = win._schedule_editor.options_button
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    card = button._popup
    qtbot.mouseClick(card.repeat_chips[""], Qt.LeftButton)
    assert card.series_note.isVisible()
    assert card.series_note.text() == "반복을 끄면 첫 날짜(10월 5일) 하루만 남습니다"


def test_failed_option_save_keeps_editor_and_blocks_navigation(qtbot, monkeypatch):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0))
    editor = win._schedule_editor
    editor.options_button.set_options(ScheduleOptions(start_time="09:00"))

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(db, "update_schedule", fail)
    assert win._finish_current_edit(True) is False
    win._on_date_selected("2026-10-13")
    assert win._selected_date == "2026-10-12"
    assert win._schedule_editor is editor
    assert db.get_schedules("2026-10-12")[0]["options"] == ScheduleOptions()


def test_reload_waits_while_another_row_is_being_edited(qtbot):
    db.add_schedule("2026-10-12", "첫째")
    db.add_schedule("2026-10-12", "둘째")
    win = main_window(qtbot)
    first, second = win.schedule_list.item(0), win.schedule_list.item(1)
    win._on_edit_schedule(first)
    win._schedule_editor.options_button.set_options(ScheduleOptions(start_time="09:00"))
    win._on_edit_schedule(second)  # 첫째 저장(목록 다시 만들기는 미룸) 뒤 둘째 편집
    QApplication.processEvents()
    assert win._editing_item is second
    assert win._list_reload_pending is True
    assert win._finish_current_edit(False)
    qtbot.waitUntil(lambda: not win._list_reload_pending)
    assert texts(win) == ["둘째", "첫째"]  # 시각 있는 첫째가 뒤로 간다.


def test_repeat_trash_offers_this_day_or_whole_series(qtbot, monkeypatch):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    item = win.schedule_list.item(0)
    row = win.schedule_list.itemWidget(item)
    row.delete_button.click()
    assert len(shown) == 1
    actions = [a for a in shown[0].menuActions() if not a.isSeparator()]
    assert [a.text() for a in actions] == ["이 날만 삭제", "반복 전체 삭제"]
    actions[0].trigger()
    assert win.schedule_list.count() == 0
    assert db.get_schedules("2026-10-12") == []
    assert [s["id"] for s in db.get_schedules("2026-10-19")] == [sid]
    win._on_date_selected("2026-10-19")
    menu = win._build_repeat_delete_menu(win.schedule_list.item(0))
    qtbot.addWidget(menu)
    [a for a in menu.menuActions() if not a.isSeparator()][1].trigger()
    assert db.get_schedules("2026-10-26") == []
    with db._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0


def test_single_day_trash_deletes_immediately(qtbot, monkeypatch):
    db.add_schedule("2026-10-12", "하루 일정")
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    win.schedule_list.itemWidget(win.schedule_list.item(0)).delete_button.click()
    assert shown == []
    assert db.get_schedules("2026-10-12") == []


def test_context_menu_for_repeat_and_single_rows(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    db.add_schedule("2026-10-12", "하루 일정")
    win = main_window(qtbot)
    for index, expected in ((0, ["편집", "삭제"]), (1, ["편집", "이 날만 삭제", "반복 전체 삭제"])):
        menu = win._build_schedule_context_menu(win.schedule_list.item(index))
        qtbot.addWidget(menu)
        assert [a.text() for a in menu.menuActions() if not a.isSeparator()] == expected


def test_locked_window_ignores_trash_and_skip(qtbot, monkeypatch):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    win._is_locked = True
    item = win.schedule_list.item(0)
    win._on_delete_button(item, item.data(Qt.UserRole), win.schedule_list.itemWidget(item).delete_button)
    win._on_skip_occurrence(item)
    assert shown == []
    assert len(db.get_schedules("2026-10-12")) == 1


@pytest.mark.parametrize("action", ["lock", "tray", "reset", "scale"])
def test_editor_card_closes_on_lifecycle_and_ignores_late_change(qtbot, action):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0))
    button = win._schedule_editor.options_button
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    card = button._popup
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
    assert button.options() == ScheduleOptions()
    assert db.get_schedules("2026-10-12")[0]["options"] == ScheduleOptions()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    assert not isValid(card)


def test_legacy_date_row_still_edits_text_but_not_options(qtbot):
    """Review Focus 1: 형식이 다른 옛 날짜 일정도 보이고 본문을 고칠 수 있으며 화면이 멈추지 않는다."""
    with db._connection() as conn:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-7-1", db.encrypt("옛 형식 일정"), "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    win = main_window(qtbot)
    win._navigate_to_date("2026-7-1")
    assert texts(win) == ["옛 형식 일정"]
    assert not win.schedule_options_button.isEnabled()
    win._on_edit_schedule(win.schedule_list.item(0))
    editor = win._schedule_editor
    assert not editor.options_button.isEnabled()
    editor.options_button.open_popup()
    assert editor.options_button._popup is None
    editor.edit.setText("고친 옛 일정")
    assert win._finish_current_edit(True)
    assert [s["content"] for s in db.get_schedules("2026-7-1")] == ["고친 옛 일정"]
    win._on_date_selected("2026-07-02")
    assert win.schedule_options_button.isEnabled()


def test_search_shows_repeat_and_period_tail_without_changing_data(qtbot):
    db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    db.add_schedule("2026-10-21", "출장 보고", options=ScheduleOptions(end_date="2026-10-23"))
    db.add_schedule("2026-10-22", "일반 회의")
    with db._connection() as conn:
        before = [tuple(r) for r in conn.execute("SELECT * FROM schedules ORDER BY id")]
    search = SearchWindow()
    qtbot.addWidget(search)
    search._on_search(search_all=True)
    cells = {search.result_table.item(row, 0).text(): search.result_table.item(row, 2)
             for row in range(search.result_table.rowCount())}
    assert cells["2026-10-05"].text() == "주간 회의 (매주 월요일 반복)"
    assert cells["2026-10-21"].text() == "출장 보고 (~10.23)"
    assert cells["2026-10-22"].text() == "일반 회의"
    assert cells["2026-10-05"].toolTip() == "주간 회의"
    with db._connection() as conn:
        assert [tuple(r) for r in conn.execute("SELECT * FROM schedules ORDER BY id")] == before


def test_skip_on_last_remaining_day_of_finite_series_removes_row_and_refreshes(qtbot):
    """M2: 끝 날짜가 있는 반복의 마지막 남은 날을 '이 날만 삭제'하면 행도 지워 빈 껍데기를 남기지 않는다."""
    sid = db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(
        start_time="10:00", repeat_rule="weekly", repeat_until="2026-10-12"))
    db.skip_schedule_occurrence(sid, "2026-10-05")
    win = main_window(qtbot)
    assert texts(win) == ["주간 회의"]
    win._on_skip_occurrence(win.schedule_list.item(0))
    assert win.schedule_list.count() == 0
    assert db.get_schedules("2026-10-12") == []
    with db._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0
    assert win._selected_date == "2026-10-12"
