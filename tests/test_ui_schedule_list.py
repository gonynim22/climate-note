"""v4.1 일정 목록 줄(시각 열·아이콘·기간 글자)·편집·반복 삭제·검색 꼬리 회귀. 합성 데이터만 쓴다."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRect, Qt
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
import ui_schedule_emoji
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


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_edit_one_occurrence_fields_and_whole_edit_keep_override(qtbot, scale, tmp_path):
    sid = db.add_schedule("2026-10-05", "원본 회의", options=WEEKLY)
    win = main_window(qtbot, scale=scale)
    item = win.schedule_list.item(0)
    menu = win._build_schedule_context_menu(item)
    qtbot.addWidget(menu)
    menu.menuActions()[0].trigger()
    assert win._schedule_editor is None  # 메뉴 클릭에서 편집기를 동기로 만들지 않음
    qtbot.waitUntil(lambda: win._schedule_editor is not None)
    editor = win._schedule_editor
    assert "이 날만 수정" in editor.summary_label.text()
    assert editor.options().repeat_rule == ""
    QApplication.processEvents()
    row_rect = win.schedule_list.visualItemRect(item)
    for control in [editor.edit, editor.summary_label, editor.color_button]:
        top_left = control.mapTo(win.schedule_list.viewport(), QPoint(0, 0))
        assert row_rect.contains(top_left)
        bottom_right = top_left + QPoint(control.width() - 1, control.height() - 1)
        assert row_rect.contains(bottom_right)
        assert win.schedule_list.viewport().rect().contains(top_left)
        assert win.schedule_list.viewport().rect().contains(bottom_right)
    assert win.grab().save(str(tmp_path / (scale + "-occurrence-editor.png")))
    editor.edit.setText("현장 회의")
    qtbot.mouseClick(editor.color_button, Qt.LeftButton)  # 노랑 → 하늘(2번 슬롯)
    editor.options_button.open_popup()
    card = editor.options_button._popup
    assert not card.row_widgets["repeat"].isVisible()
    assert not card.row_widgets["period"].isVisible()
    card._change(ScheduleOptions(start_time="14:00", alarm_before=30))
    editor.options_button.close_popup()
    assert win._finish_current_edit(True)
    qtbot.waitUntil(lambda: texts(win) == ["현장 회의"] and win.schedule_list.item(0).data(Qt.UserRole + 8))
    result = db.get_schedules("2026-10-12")[0]
    assert result["options"] == ScheduleOptions(start_time="14:00", alarm_before=30)
    assert result["color"] == "#4CC9F0"
    assert "이 날만 수정됨" in rows(win)[0].schedule_text_label.toolTip()
    win._on_edit_schedule(win.schedule_list.item(0), scope="series")
    editor = win._schedule_editor
    assert editor.edit.text() == "원본 회의"
    assert editor.options() == WEEKLY
    assert editor.color() == db.DEFAULT_SCHEDULE_COLOR
    editor.edit.setText("전체 회의")
    assert win._finish_current_edit(True)
    qtbot.waitUntil(lambda: texts(win) == ["현장 회의"] and win._schedule_editor is None)
    assert db.get_schedule(sid)["content"] == "전체 회의"
    assert db.get_schedules("2026-10-12")[0]["content"] == "현장 회의"


def test_occurrence_open_cancel_and_unchanged_save_do_not_create_row(qtbot):
    db.add_schedule("2026-10-05", "원본", options=WEEKLY)
    win = main_window(qtbot)
    before = db.export_all_data()
    for save in (False, True):
        win._on_edit_schedule(win.schedule_list.item(0), scope="occurrence")
        assert win._finish_current_edit(save)
        assert db.export_all_data() == before


def test_failed_occurrence_save_keeps_editor_and_blocks_date_move(qtbot, monkeypatch):
    db.add_schedule("2026-10-05", "원본", options=WEEKLY)
    win = main_window(qtbot)
    win._on_edit_schedule(win.schedule_list.item(0), scope="occurrence")
    editor = win._schedule_editor
    editor.edit.setText("저장해야 할 내용")
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic")
    monkeypatch.setattr(db, "update_schedule_occurrence", fail)
    win._on_date_selected("2026-10-13")
    assert win._selected_date == "2026-10-12"
    assert win._schedule_editor is editor
    assert editor.edit.text() == "저장해야 할 내용"
    assert win._save_schedule_edit() is False


@pytest.mark.parametrize("action", ["reload", "lock", "hide"])
def test_queued_occurrence_edit_is_cancelled_by_lifecycle(qtbot, action):
    db.add_schedule("2026-10-05", "원본", options=WEEKLY)
    win = main_window(qtbot)
    before = db.export_all_data()
    win._queue_schedule_edit(win.schedule_list.item(0), "occurrence")
    if action == "reload":
        win._load_schedules()
    elif action == "lock":
        win._is_locked = True
        win._close_schedule_emoji_popups()
    else:
        win.hide()
    QApplication.processEvents()
    assert win._schedule_editor is None
    assert db.export_all_data() == before


def test_double_click_repeat_offers_scope_and_cancel_writes_nothing(qtbot, monkeypatch):
    db.add_schedule("2026-10-05", "원본", options=WEEKLY)
    win = main_window(qtbot)
    shown = []
    monkeypatch.setattr(ui_main.RoundMenu, "exec", lambda self, pos: shown.append(self))
    before = db.export_all_data()
    win.schedule_list.itemDoubleClicked.emit(win.schedule_list.item(0))
    assert [a.text() for a in shown[0].menuActions()] == ["이 날만 수정", "반복 전체 수정"]
    win._close_schedule_emoji_popups()
    assert win._schedule_editor is None
    assert db.export_all_data() == before


@pytest.mark.parametrize("keyboard", [False, True])
def test_actual_scope_menu_input_opens_editor_and_escape_cancels(qtbot, keyboard):
    db.add_schedule("2026-10-05", "원본 회의", options=WEEKLY)
    win = main_window(qtbot)
    before = db.export_all_data()
    win._on_schedule_double_clicked(win.schedule_list.item(0))
    menu = win._schedule_menu
    qtbot.waitUntil(lambda: menu.isVisible())
    item = menu.view.item(0)
    if keyboard:
        menu.view.setCurrentItem(item)
        menu.view.setFocus()
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    else:
        qtbot.mouseClick(menu.view.viewport(), Qt.LeftButton, pos=menu.view.visualItemRect(item).center())
    qtbot.waitUntil(lambda: win._schedule_editor is not None)
    editor = win._schedule_editor
    assert "이 날만 수정" in editor.summary_label.text()
    editor.edit.setFocus()
    qtbot.keyClick(editor.edit, Qt.Key_Escape)
    assert win._schedule_editor is None
    assert db.export_all_data() == before


def test_tooltip_preserves_html_like_source_and_export(qtbot):
    from PySide6.QtGui import QTextDocument
    from ui_text import plain_tooltip
    source = '<b>그대로</b> &amp; <img src="x">\n두 번째  줄'
    db.add_schedule("2026-10-12", source)
    win = main_window(qtbot)
    doc = QTextDocument()
    doc.setHtml(rows(win)[0].schedule_text_label.toolTip())
    assert doc.toPlainText() == source
    assert db.get_schedules("2026-10-12")[0]["content"] == source
    assert plain_tooltip("일반 내용") == "일반 내용"


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
    assert "첫 날짜(10월 5일)" in card.series_note.text()
    assert "따로 수정한 회차는 일반 일정" in card.series_note.text()


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
    for index, expected in ((0, ["편집", "삭제"]), (1, ["이 날만 수정", "반복 전체 수정", "이 날만 삭제", "반복 전체 삭제"])):
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


# ─── 편집 색(B안 · 앞 색 원, 2026-11-10) ─────────────────────────────

def circle_fill(button):
    """색 원 가운데 화소, 곧 화면에 그려진 채움색."""
    image = button.grab().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).name().upper()


def open_editor(win, index=0, scope="series"):
    win._on_edit_schedule(win.schedule_list.item(index), scope=scope)
    QApplication.processEvents()
    return win._schedule_editor


@pytest.mark.parametrize("current,expected", [
    ("#FFD166", "#4CC9F0"), ("#4CC9F0", "#FF6B6B"), ("#FF6B6B", "#FFD166"),
    ("#4cc9f0", "#FF6B6B"),            # 대소문자만 다른 슬롯 값도 그 슬롯이다(표시색 규칙과 같음)
    ("#123456", "#FFD166"), ("", "#FFD166"), (None, "#FFD166"),  # 팔레트 밖은 1번부터
])
def test_next_schedule_color_follows_slot_order(current, expected):
    assert ui_schedule_emoji.next_schedule_color(current, db.SCHEDULE_COLOR_SLOTS) == expected


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_edit_color_circle_cycles_display_colors_and_saves_slot(qtbot, scale):
    db.save_schedule_palette(("#80CFA9", "#8FA8FF", "#F28BB5"))
    sid = db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot, scale=scale)
    editor = open_editor(win)
    button = editor.color_button
    assert button.isVisible()
    assert circle_fill(button) == "#80CFA9"  # 저장값은 노랑 슬롯, 화면은 설정 표시색
    seen = []
    for _ in range(4):
        qtbot.mouseClick(button, Qt.LeftButton)
        seen.append((editor.color(), circle_fill(button)))
    assert seen == [("#4CC9F0", "#8FA8FF"), ("#FF6B6B", "#F28BB5"),
                    ("#FFD166", "#80CFA9"), ("#4CC9F0", "#8FA8FF")]
    assert db.get_schedule(sid)["color"] == "#FFD166"  # 누르기만으로는 저장하지 않는다
    qtbot.keyClick(editor.edit, Qt.Key_Return)
    assert win._schedule_editor is None
    stored = db.get_schedule(sid)
    assert (stored["color"], stored["content"]) == ("#4CC9F0", "회의")
    qtbot.waitUntil(lambda: win.schedule_list.item(0).data(Qt.UserRole + 2) == "#4CC9F0")
    cell = win._day_cells["2026-10-12"]
    if scale == "compact":
        assert cell._event_colors == ["#8FA8FF"]
    else:
        assert "#8FA8FF" in cell._chips_layout.itemAt(0).widget().styleSheet()


def test_color_click_keeps_editing_and_input_focus(qtbot):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    before = db.export_all_data()
    editor = open_editor(win)
    item = win._editing_item
    assert win.focusWidget() is editor.edit
    qtbot.mouseClick(editor.color_button, Qt.LeftButton)
    qtbot.wait(50)  # 편집 영역 포커스 검사(0ms 타이머)가 돌 시간을 준다
    assert win._schedule_editor is editor and win._editing_item is item
    assert win.focusWidget() is editor.edit  # 원을 눌러도 글자 입력 포커스는 그대로다
    assert db.export_all_data() == before


def test_escape_cancels_text_and_color_together(qtbot):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    before = db.export_all_data()
    editor = open_editor(win)
    editor.edit.setText("바뀐 회의")
    qtbot.mouseClick(editor.color_button, Qt.LeftButton)
    qtbot.keyClick(editor.edit, Qt.Key_Escape)
    assert win._schedule_editor is None
    assert db.export_all_data() == before
    assert texts(win) == ["회의"]
    assert win.schedule_list.item(0).data(Qt.UserRole + 2) == db.DEFAULT_SCHEDULE_COLOR


def test_outside_palette_color_kept_until_clicked_then_starts_at_first_slot(qtbot):
    sid = db.add_schedule("2026-10-12", "가져온 일정", "#123456")
    win = main_window(qtbot)
    editor = open_editor(win)
    assert circle_fill(editor.color_button) == "#123456"
    editor.edit.setText("고친 일정")
    qtbot.keyClick(editor.edit, Qt.Key_Return)
    stored = db.get_schedule(sid)
    assert (stored["content"], stored["color"]) == ("고친 일정", "#123456")  # 내용만 고친 저장
    editor = open_editor(win)
    qtbot.mouseClick(editor.color_button, Qt.LeftButton)
    assert editor.color() == "#FFD166"
    qtbot.keyClick(editor.edit, Qt.Key_Return)
    assert db.get_schedule(sid)["color"] == "#FFD166"


def test_repeat_series_and_occurrence_edit_use_one_front_circle(qtbot):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=WEEKLY)
    db.add_schedule("2026-10-12", "오전 점검", options=ScheduleOptions(start_time="09:00"))
    win = main_window(qtbot)
    assert texts(win) == ["오전 점검", "주간 회의"]
    plain = open_editor(win, 0)
    plain_height = plain.height()  # 요약 한 줄이 있는 일반 일정의 편집기
    assert win._finish_current_edit(False)
    editor = open_editor(win, 1, scope="series")
    row = win.schedule_list.itemWidget(win._editing_item)
    circles = row.findChildren(ui_schedule_emoji.SmoothCircleButton)
    assert [c for c in circles if c.isVisible()] == [editor.color_button]
    assert editor.height() == plain_height  # 반복 일정에만 붙던 색 줄이 없다
    qtbot.mouseClick(editor.color_button, Qt.LeftButton)
    qtbot.keyClick(editor.edit, Qt.Key_Return)
    assert db.get_schedule(sid)["color"] == "#4CC9F0"
    qtbot.waitUntil(lambda: win.schedule_list.item(1).data(Qt.UserRole + 2) == "#4CC9F0")  # 목록을 다시 읽음
    editor = open_editor(win, 1, scope="occurrence")
    assert editor.color() == "#4CC9F0"
    qtbot.mouseClick(editor.color_button, Qt.LeftButton)
    qtbot.keyClick(editor.edit, Qt.Key_Return)
    by_text = {s["content"]: s for s in db.get_schedules("2026-10-12")}
    assert by_text["주간 회의"]["color"] == "#FF6B6B" and by_text["주간 회의"]["is_override"]
    assert db.get_schedule(sid)["color"] == "#4CC9F0"  # 이 날만 수정은 원본 색을 바꾸지 않는다
    assert db.get_schedules("2026-10-19")[0]["color"] == "#4CC9F0"


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_edit_circle_takes_dot_place_without_changing_row_height(qtbot, scale):
    db.add_schedule("2026-10-12", "종일 일정")
    db.add_schedule("2026-10-12", "오전 점검", options=ScheduleOptions(start_time="09:00"))
    win = main_window(qtbot, scale=scale)
    for index in range(2):  # 한 줄 편집기, 요약 줄이 있는 편집기
        item = win.schedule_list.item(index)
        row = win.schedule_list.itemWidget(item)
        dot = row.schedule_color_dot
        dot_left = dot.x()
        editor = open_editor(win, index)
        circle = editor.color_button
        circle_rect = QRect(circle.mapTo(row, QPoint(0, 0)), circle.size())
        assert not dot.isVisible()
        assert circle_rect.x() == dot_left  # 줄 앞 색 점 자리
        edit_mid = editor.edit.mapTo(row, QPoint(0, editor.edit.height() // 2)).y()
        assert abs(circle_rect.center().y() - edit_mid) <= 1  # 입력칸 줄에 맞춘다
        margins = row.layout().contentsMargins()
        assert item.sizeHint().height() == (
            editor.sizeHint().height() + margins.top() + margins.bottom())  # 원이 줄을 늘리지 않는다
        assert row.rect().contains(circle_rect)
        assert win._finish_current_edit(False)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.processEvents()
        assert dot.isVisible()
        assert not isValid(circle)


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
@pytest.mark.parametrize("scope", ["series", "occurrence"])
def test_editor_row_fits_list_width_without_horizontal_scroll(qtbot, scale, scope):
    """원(22px)이 색 점(16px)보다 넓어도 편집 줄이 목록 폭을 넘겨 가로 스크롤을 만들지 않는다.

    넘기면 가로 스크롤바가 보이는 높이를 줄여 요약 줄이 가려진다(1.5배 크게에서 실제로 났다).
    """
    db.add_schedule("2026-10-05", "원본 회의", options=WEEKLY)
    win = main_window(qtbot, scale=scale)
    editor = open_editor(win, scope=scope)
    item = win._editing_item
    viewport = win.schedule_list.viewport()
    assert item.sizeHint().width() <= viewport.width()
    assert not win.schedule_list.horizontalScrollBar().isVisible()
    for control in (editor.edit, editor.summary_label, editor.color_button):
        rect = QRect(control.mapTo(viewport, QPoint(0, 0)), control.size())
        assert viewport.rect().contains(rect), (control, rect, viewport.rect())


@pytest.mark.parametrize("factor", ["1.25", "1.5"])
def test_editor_row_fits_list_at_scale_factors(factor):
    """QT_SCALE_FACTOR는 프로세스 단위라 하위 프로세스에서 같은 배치 검사를 돌린다."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_ui_schedule_list.py::test_editor_row_fits_list_width_without_horizontal_scroll"],
        env={**os.environ, "QT_SCALE_FACTOR": factor},
        cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]


@pytest.mark.parametrize("state", ["_is_locked", "_hidden_to_tray"])
def test_color_circle_ignores_clicks_while_locked_or_hidden(qtbot, state):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    editor = open_editor(win)
    setattr(win, state, True)
    try:
        editor.color_button.click()
        assert editor.color() == db.DEFAULT_SCHEDULE_COLOR
    finally:
        setattr(win, state, False)


def test_keyboard_reaches_circle_space_cycles_and_enter_saves(qtbot):
    sid = db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    editor = open_editor(win)
    circle = editor.color_button
    assert circle.toolTip() == "누를 때마다 다음 색"
    assert circle.accessibleName() == "일정 색상 노랑 — 누를 때마다 다음 색"
    for _ in range(3):  # 입력칸 → 스마일 → 시계 → 색 원
        if win.focusWidget() is circle:
            break
        qtbot.keyClick(win.focusWidget(), Qt.Key_Tab)
        QApplication.processEvents()
    assert win.focusWidget() is circle
    assert win._schedule_editor is editor  # 편집 영역 안에서의 이동은 편집을 끝내지 않는다
    qtbot.keyClick(circle, Qt.Key_Space)
    assert editor.color() == "#4CC9F0"
    assert circle.accessibleName() == "일정 색상 하늘 — 누를 때마다 다음 색"
    qtbot.keyClick(circle, Qt.Key_Return)
    assert win._schedule_editor is None
    assert db.get_schedule(sid)["color"] == "#4CC9F0"


def test_tab_from_color_circle_leaves_editor_and_saves(qtbot):
    """색 원 다음 Tab은 v4.8처럼 편집 영역 밖으로 나가 저장한다(입력칸으로 되돌아 돌지 않는다)."""
    sid = db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    editor = open_editor(win)
    circle = editor.color_button
    inside = {editor.edit, editor.emoji_button, editor.options_button, circle}
    for _ in range(3):
        if win.focusWidget() is circle:
            break
        qtbot.keyClick(win.focusWidget(), Qt.Key_Tab)
        QApplication.processEvents()
    assert win.focusWidget() is circle
    qtbot.keyClick(circle, Qt.Key_Space)
    qtbot.keyClick(circle, Qt.Key_Tab)
    assert win.focusWidget() not in inside
    qtbot.waitUntil(lambda: win._schedule_editor is None)  # 영역 밖 포커스 = 저장
    assert db.get_schedule(sid)["color"] == "#4CC9F0"


def test_shift_tab_from_input_leaves_editor(qtbot):
    db.add_schedule("2026-10-12", "회의")
    win = main_window(qtbot)
    editor = open_editor(win)
    inside = {editor.edit, editor.emoji_button, editor.options_button, editor.color_button}
    assert win.focusWidget() is editor.edit
    qtbot.keyClick(editor.edit, Qt.Key_Backtab)
    assert win.focusWidget() not in inside
