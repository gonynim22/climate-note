"""일정 이모지 선택의 입력·포커스·저장·창 수명 회귀."""
import os
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QLineEdit
from shiboken6 import isValid
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
import database as db
import ui_main
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow
from ui_schedule_emoji import (
    SCHEDULE_EMOJIS, ScheduleEmojiPopup, apply_schedule_emoji, popup_position,
)
from ui_search import SearchWindow


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


def main_window(qtbot, scale="compact", content=None):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    if content is not None:
        db.add_schedule("2026-09-09", content, "#4CC9F0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    win._current_year, win._current_month = 2026, 9
    win._refresh_calendar()
    win._on_date_selected("2026-09-09")
    QApplication.processEvents()
    return win


def open_picker(qtbot, button):
    qtbot.mouseClick(button, Qt.LeftButton)
    qtbot.waitUntil(lambda: button._popup is not None and button._popup.isVisible())
    return button._popup


def pick(qtbot, popup, emoji):
    button = next(b for b in popup.buttons if b.text() == (emoji or "없음"))
    qtbot.mouseClick(button, Qt.LeftButton)


@pytest.mark.parametrize("original,emoji,expected", [
    ("회의", "📌", "📌 회의"),
    ("📌 회의", "⭐", "⭐ 회의"),
    ("✉️ 메일", "📌", "📌 메일"),
    ("📌 회의", "", "회의"),
    ("회의 후 🎉 행사", "", "회의 후 🎉 행사"),
    ("👩🏽‍💻 업무 🇰🇷", "📌", "📌 👩🏽‍💻 업무 🇰🇷"),
    ("📌회의", "", "📌회의"),
    ("📌  공백 유지", "✉️", "✉️  공백 유지"),
    ("", "📌", "📌 "),
])
def test_prefix_edit_preserves_unicode_body_and_undo(qtbot, original, emoji, expected):
    edit = QLineEdit(original)
    qtbot.addWidget(edit)
    edit.selectAll()
    apply_schedule_emoji(edit, emoji)
    assert edit.text() == expected
    if expected != original:
        edit.undo()
        assert edit.text() == original
        edit.redo()
        assert edit.text() == expected


@pytest.mark.parametrize("emoji,name", SCHEDULE_EMOJIS)
def test_all_palette_choices_can_be_saved(qtbot, emoji, name):
    win = main_window(qtbot)
    win.schedule_input.setText("주간 업무보고")
    popup = open_picker(qtbot, win.schedule_emoji_button)
    assert len(popup.buttons) == 17
    assert any(b.accessibleName() == name for b in popup.buttons)
    pick(qtbot, popup, emoji)
    assert db.get_schedules("2026-09-09") == []  # 선택은 입력 편집일 뿐이다.
    qtbot.waitUntil(lambda: win.schedule_input.hasFocus())
    qtbot.keyClick(win.schedule_input, Qt.Key_Return)
    saved = db.get_schedules("2026-09-09")
    assert saved[0]["content"] == emoji + " 주간 업무보고"
    assert saved[0]["color"] == db.DEFAULT_SCHEDULE_COLOR
    assert win.schedule_input.text() == ""


def test_add_failure_keeps_emoji_and_title(qtbot, monkeypatch):
    win = main_window(qtbot)
    win.schedule_input.setText("📌 보존할 회의")
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")
    monkeypatch.setattr(db, "add_schedule", fail)
    win._on_add_schedule()
    assert win.schedule_input.text() == "📌 보존할 회의"
    assert win.schedule_list.count() == 0


def test_inline_picker_focus_replace_remove_and_enter(qtbot):
    win = main_window(qtbot, "large", "📌 회의")
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    editor = win._schedule_editor
    popup = open_picker(qtbot, editor.emoji_button)
    assert win._editing_item is item
    pick(qtbot, popup, "✉️")
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    assert win._editing_item is item
    assert editor.edit.text() == "✉️ 회의"
    assert db.get_schedules("2026-09-09")[0]["content"] == "📌 회의"
    popup = open_picker(qtbot, editor.emoji_button)
    pick(qtbot, popup, "")
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    qtbot.keyClick(editor.edit, Qt.Key_Return)
    assert win._editing_item is None
    assert db.get_schedules("2026-09-09")[0]["content"] == "회의"
    assert item.data(Qt.UserRole + 2) == "#4CC9F0"


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_inline_emoji_button_fits_row_before_and_after_edit(qtbot, scale):
    win = main_window(qtbot, scale, "📚 교육 일정")
    item = win.schedule_list.item(0)
    row = win.schedule_list.itemWidget(item)
    for save in (False, True):
        win._on_edit_schedule(item)
        editor = win._schedule_editor
        qtbot.waitUntil(lambda: editor.edit.hasFocus())
        QApplication.processEvents()
        appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
        if appdata:
            assert row.grab().save(str(
                Path(appdata).parent / f"schedule-emoji-inline-{scale}.png"
            ))
        # 실제 목록 배치가 버튼 하단까지 확보해야 한다. sizeHint만 검사하면
        # QListWidget의 item padding과 아직 숨겨진 편집기를 놓칠 수 있다.
        assert editor.rect().contains(editor.emoji_button.geometry())
        assert row.rect().contains(editor.geometry())
        assert editor.edit.height() >= editor.edit.sizeHint().height()
        editor.edit.setText("⭐ 변경한 일정")
        assert win._finish_current_edit(save)
        QApplication.processEvents()
        label = row.schedule_text_label
        assert row.rect().contains(label.geometry())
        assert label.height() >= label.sizeHint().height()
    assert db.get_schedules("2026-09-09")[0]["content"] == "⭐ 변경한 일정"


def test_keyboard_picker_escape_and_unchanged_rows(qtbot):
    win = main_window(qtbot, content="📌 회의")
    with db._connection() as conn:
        before = tuple(conn.execute("SELECT * FROM schedules").fetchone())
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    editor = win._schedule_editor
    editor.emoji_button.setFocus()
    qtbot.keyClick(editor.emoji_button, Qt.Key_Return)
    popup = editor.emoji_button._popup
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Right)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    assert editor.edit.text() == "⭐ 회의"
    qtbot.keyClick(editor.edit, Qt.Key_Escape)
    assert item.data(Qt.UserRole + 1) == "📌 회의"

    win._on_edit_schedule(item)
    editor = win._schedule_editor
    popup = open_picker(qtbot, editor.emoji_button)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    assert win._editing_item is item  # 첫 Escape는 팝업만 취소한다.
    qtbot.keyClick(editor.edit, Qt.Key_Escape)
    with db._connection() as conn:
        assert tuple(conn.execute("SELECT * FROM schedules").fetchone()) == before


@pytest.mark.parametrize("key,expected", [
    (Qt.Key_Left, "🤝"), (Qt.Key_Right, "📞"),
    (Qt.Key_Up, "⭐"), (Qt.Key_Down, "📄"), (Qt.Key_Tab, "📞"),
])
def test_picker_keys_reach_focused_button(qtbot, key, expected):
    win = main_window(qtbot)
    win.schedule_input.setText("👥 회의")
    open_picker(qtbot, win.schedule_emoji_button)
    assert QApplication.focusWidget().text() == "👥"
    qtbot.keyClick(QApplication.focusWidget(), key)
    assert QApplication.focusWidget().text() == expected
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Space)
    qtbot.waitUntil(lambda: win.schedule_input.hasFocus())
    assert win.schedule_input.text() == expected + " 회의"
    assert win.schedule_emoji_button._popup is None


def test_focus_leaving_composite_editor_saves(qtbot):
    win = main_window(qtbot, content="회의")
    win._on_edit_schedule(win.schedule_list.item(0))
    editor = win._schedule_editor
    popup = open_picker(qtbot, editor.emoji_button)
    pick(qtbot, popup, "📌")
    qtbot.waitUntil(lambda: editor.edit.hasFocus())
    qtbot.mouseClick(win.schedule_input, Qt.LeftButton)
    qtbot.waitUntil(lambda: win._editing_item is None)
    assert db.get_schedules("2026-09-09")[0]["content"] == "📌 회의"


def test_failed_edit_blocks_reload_and_date_change_then_retries(qtbot, monkeypatch):
    win = main_window(qtbot, "medium", "회의")
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    editor = win._schedule_editor
    editor.edit.setText("⭐ 변경한 회의")
    update = db.update_schedule
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")
    monkeypatch.setattr(db, "update_schedule", fail)
    assert win._finish_current_edit(True) is False
    assert win._load_schedules() is False
    win._on_date_selected("2026-09-10")
    assert win._selected_date == "2026-09-09"
    assert win._schedule_editor is editor
    assert editor.edit.text() == "⭐ 변경한 회의"
    assert item.data(Qt.UserRole + 1) == "회의"
    monkeypatch.setattr(db, "update_schedule", update)
    win._on_date_selected("2026-09-10")
    assert win._selected_date == "2026-09-10"
    chip = win._day_cells["2026-09-09"]._chips_layout.itemAt(0).widget()
    assert chip.toolTip() == "⭐ 변경한 회의"
    assert db.get_schedules("2026-09-10") == []


@pytest.mark.parametrize("operation", ["today", "prev_month", "next_month", "search", "data", "quit"])
def test_unsaved_edit_blocks_navigation_and_data_gates(qtbot, monkeypatch, operation):
    win = main_window(qtbot, content="회의")
    win._on_edit_schedule(win.schedule_list.item(0))
    win._schedule_editor.edit.setText("📌 저장 실패한 회의")
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")
    monkeypatch.setattr(db, "update_schedule", fail)
    if operation == "search":
        win._navigate_to_date("2026-10-15")
    elif operation == "data":
        assert win.prepare_for_data_change() is False
    elif operation == "quit":
        assert win.prepare_for_quit() is False
    else:
        getattr(win, "_on_" + operation)()
    assert (win._current_year, win._current_month) == (2026, 9)
    assert win._selected_date == "2026-09-09"
    assert win._schedule_editor.edit.text() == "📌 저장 실패한 회의"


def test_unchanged_and_unreadable_schedules_are_not_rewritten(qtbot):
    win = main_window(qtbot, content="  📌 공백을 보존할 일정  ")
    with db._connection() as conn:
        before = tuple(conn.execute("SELECT * FROM schedules").fetchone())
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    assert win._finish_current_edit(True)
    with db._connection() as conn:
        assert tuple(conn.execute("SELECT * FROM schedules").fetchone()) == before
    win._add_schedule_item(999, "[복호화 오류]", decryption_failed=True)
    win._on_edit_schedule(win.schedule_list.item(1))
    assert win._editing_item is None


@pytest.mark.parametrize("action", ["lock", "tray", "reset"])
@pytest.mark.parametrize("inline", [False, True])
def test_popup_discard_invalidates_late_selection(qtbot, action, inline):
    win = main_window(qtbot, content="회의")
    if inline:
        win._on_edit_schedule(win.schedule_list.item(0))
        button = win._schedule_editor.emoji_button
    else:
        win.schedule_input.setText("새 회의")
        button = win.schedule_emoji_button
    original = button.edit.text()
    popup = open_picker(qtbot, button)
    if action == "lock":
        win._lock()
    elif action == "tray":
        win._minimize_to_tray()
    else:
        win._discard_data_widgets()
    assert not popup.isVisible()
    popup.selected.emit("🔥")  # 이미 큐에 있던 선택을 재현한다.
    assert button.edit.text() == original
    assert db.get_schedules("2026-09-09")[0]["content"] == "회의"
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()
    assert not isValid(popup)
    if action == "lock":
        win.toggle_visibility()
        win.toggle_visibility()
        assert win.schedule_emoji_button._popup is None


def test_repeated_open_close_does_not_keep_popups(qtbot):
    win = main_window(qtbot)
    for _ in range(8):
        popup = open_picker(qtbot, win.schedule_emoji_button)
        win.schedule_emoji_button.open_popup()
        assert win.schedule_emoji_button._popup is popup
        qtbot.keyClick(popup, Qt.Key_Escape)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not isValid(popup)
    assert win.findChildren(ScheduleEmojiPopup) == []


def test_delete_while_editing_cancels_old_callback(qtbot):
    win = main_window(qtbot, content="회의")
    item = win.schedule_list.item(0)
    win._on_edit_schedule(item)
    finish = win._finish_current_edit
    win._schedule_editor.edit.setText("📌 수정 중")
    win._on_delete_schedule(item, item.data(Qt.UserRole))
    assert finish(True) is True
    assert db.get_schedules("2026-09-09") == []


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_display_search_and_popup_geometry(qtbot, scale):
    content = "📌 관계기관 협의회의 " + "긴 제목 " * 20
    win = main_window(qtbot, scale, content)
    item = win.schedule_list.item(0)
    label = win.schedule_list.itemWidget(item).schedule_text_label
    assert label.text() == content
    assert label.toolTip() == content
    if scale != "compact":
        chip = win._day_cells["2026-09-09"]._chips_layout.itemAt(0).widget()
        assert chip.text().startswith("📌")
        assert chip.toolTip() == content
    search = SearchWindow()
    qtbot.addWidget(search)
    search.search_input.setText("협의회의")
    search._on_search()
    assert search.result_table.item(0, 2).text().startswith("📌")
    assert search.result_table.item(0, 2).toolTip() == content
    popup = open_picker(qtbot, win.schedule_emoji_button)
    assert popup.screen().availableGeometry().contains(popup.frameGeometry())
    assert win.schedule_input.width() >= 100
    # 이번 실행의 합성 UI 렌더만 보존한다. 실제 사용자 화면은 캡처하지 않는다.
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        output = Path(appdata).parent
        assert win.grab().save(str(output / f"schedule-emoji-{scale}.png"))
        assert popup.grab().save(str(output / "schedule-emoji-picker.png"))


@pytest.mark.parametrize("anchor", [QRect(-1900, 10, 26, 26), QRect(-30, 1040, 26, 26)])
def test_popup_stays_on_negative_coordinate_monitor(anchor):
    available = QRect(-1920, 0, 1920, 1080)
    size = QSize(180, 210)
    point = popup_position(anchor, size, available)
    assert available.contains(QRect(point, size))
