"""세 번째 미니앱(금액·숫자 표기)의 실행·소유 수명과 기존 데이터 보존을 합성 환경에서 검증한다."""
import sqlite3

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qfluentwidgets.common.font import fontFamilies, setFontFamilies
from shiboken6 import isValid

from app_fonts import apply_app_font
import database as db
import security
import ui_main
import ui_settings
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def activate(win):
    win.show()
    win.raise_()
    win.activateWindow()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)


def main_window(qtbot):
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    activate(main)
    return main


def open_money(qtbot, main, *, keyboard=False):
    activate(main)
    qtbot.mouseClick(main.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: main._mini_apps_popup is not None)
    pocket = main._mini_apps_popup
    assert QTest.qWaitForWindowExposed(pocket)
    assert QTest.qWaitForWindowActive(pocket)
    if keyboard:
        pocket.money_card.setFocus()
        qtbot.waitUntil(pocket.money_card.hasFocus)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    else:
        qtbot.mouseClick(pocket.money_card, Qt.LeftButton)
    win = main._money_notation
    assert win is not None
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    assert main._mini_apps_popup is None
    assert not main.sidebar.mini_apps_button.isChecked()
    assert not main._mini_apps_focus_timer.isActive()
    return win


def open_all_with_history(qtbot, main):
    main._open_unit_converter()
    converter = main._unit_converter
    converter.input.setText("42")
    converter.save_recent()
    main._open_date_time_calculator()
    calculator = main._date_time_calculator
    calculator.save_recent()
    money = open_money(qtbot, main)
    money.save_recent()
    assert len(converter.history.items) == len(calculator.history) == len(money.history) == 1
    return converter, calculator, money


@pytest.mark.parametrize("keyboard", [False, True])
def test_third_tile_opens_one_reusable_window(qtbot, keyboard):
    main = main_window(qtbot)
    money = open_money(qtbot, main, keyboard=keyboard)
    money.save_recent()
    history = list(money.history)
    money.close()
    assert not money.isVisible()
    assert main._money_notation is money
    assert open_money(qtbot, main, keyboard=keyboard) is money
    assert money.history == history
    assert main._unit_converter is None and main._date_time_calculator is None


def test_three_apps_keep_independent_sessions(qtbot):
    main = main_window(qtbot)
    converter, calculator, money = open_all_with_history(qtbot, main)
    assert money.parentWidget() is main
    money_history = list(money.history)
    calculator.save_recent()
    converter.input.setText("84")
    converter.save_recent()
    assert money.history == money_history
    money.close()
    assert converter.isVisible() and calculator.isVisible()
    assert open_money(qtbot, main) is money
    assert money.history == money_history


@pytest.mark.parametrize("action", ["lock", "tray", "sidebar", "hide", "reset_prepare"])
def test_lifecycle_hides_money_window_without_losing_history(qtbot, action):
    main = main_window(qtbot)
    _converter, _calculator, money = open_all_with_history(qtbot, main)
    history = list(money.history)
    combo = money.copy_format
    combo.showPopup()
    qtbot.waitUntil(combo.view().isVisible)
    if action == "lock":
        main._lock()
        assert not money.isEnabled()
        main._open_money_notation()
        assert not money.isVisible()
        main._unlock()
    elif action == "tray":
        main._minimize_to_tray()
        main._open_money_notation()
        assert not money.isVisible()
        main.toggle_visibility()
    elif action == "sidebar":
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
        main._apply_sidebar_visibility()
        main._open_money_notation()
    elif action == "hide":
        main.hide()
        main.show()
    else:
        main._discard_data_widgets()
    assert main._money_notation is money
    assert not money.isVisible()
    assert not combo.view().isVisible()
    assert money.history == history
    if action == "lock":
        main._open_money_notation()
        assert money.isEnabled() and money.isVisible()


@pytest.mark.parametrize("action", ["scale", "screen"])
def test_layout_changes_preserve_money_window(qtbot, action):
    main = main_window(qtbot)
    _converter, _calculator, money = open_all_with_history(qtbot, main)
    history = list(money.history)
    if action == "scale":
        db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
        main._apply_calendar_scale()
    else:
        main._on_screen_changed()
    assert main._money_notation is money
    assert money.isVisible()
    assert money.history == history
    assert money.screen().availableGeometry().contains(money.geometry())


def test_schedule_save_failure_blocks_money_window(qtbot, monkeypatch):
    db.add_schedule("2026-09-27", "기존 일정", "#FFD166")
    main = main_window(qtbot)
    main._on_date_selected("2026-09-27")
    main._on_edit_schedule(main.schedule_list.item(0))
    editor = main._schedule_editor
    editor.edit.setText("⭐ 저장할 일정")
    qtbot.waitUntil(editor.edit.hasFocus)
    original_update = db.update_schedule

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic save failure")

    monkeypatch.setattr(db, "update_schedule", fail)
    main._open_money_notation()
    assert main._money_notation is None
    assert editor.edit.text() == "⭐ 저장할 일정"
    assert db.get_schedules("2026-09-27")[0]["content"] == "기존 일정"
    monkeypatch.setattr(db, "update_schedule", original_update)
    main._open_money_notation()
    money = main._money_notation
    assert money is not None and money.isVisible()
    assert db.get_schedules("2026-09-27")[0]["content"] == "⭐ 저장할 일정"


@pytest.mark.parametrize("failure", [None, "backup", "database"])
def test_only_successful_factory_reset_discards_money_session(qtbot, monkeypatch, failure):
    main = main_window(qtbot)
    _converter, _calculator, money = open_all_with_history(qtbot, main)
    history = list(money.history)
    main._on_settings()
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    monkeypatch.setattr(ui_settings.InfoBar, "success", lambda **kw: None)
    monkeypatch.setattr(ui_settings.InfoBar, "error", lambda **kw: None)

    def fail(*args):
        raise OSError("synthetic reset failure")

    if failure:
        monkeypatch.setattr(db, "backup_before_operation" if failure == "backup" else "reset_database", fail)
    main._settings_window._on_reset()
    if failure:
        assert main._money_notation is money
        assert money.history == history
    else:
        assert main._money_notation is None
        qtbot.waitUntil(lambda: not isValid(money))


@pytest.mark.parametrize("failure", ["schedule", "sticky"])
def test_failed_quit_preserves_money_session_until_success(qtbot, monkeypatch, failure):
    main = main_window(qtbot)
    _converter, _calculator, money = open_all_with_history(qtbot, main)
    target = "_save_schedule_edit" if failure == "schedule" else "save_all_sticky_notes"
    monkeypatch.setattr(main, target, lambda: False)
    assert not main.prepare_for_quit()
    assert main._money_notation is money and len(money.history) == 1
    monkeypatch.setattr(main, target, lambda: True)
    assert main.prepare_for_quit()
    assert main._money_notation is None
    qtbot.waitUntil(lambda: not isValid(money))


def test_money_window_preserves_database_export_salt_and_shortcuts(qtbot, tmp_path):
    for sid in range(1, 7):
        db.update_shortcut(sid, f"기존 {sid}", str(tmp_path / f"{sid}.txt"))
    db.add_schedule("2026-09-27", "📌 기존 일정", "#FFD166")
    db.save_memo("2026-09-27", "기존 메모")
    note = db.create_sticky_note()
    db.update_sticky_note(note, content="<p>기존 스티키</p>")
    main = main_window(qtbot)
    qtbot.waitUntil(lambda: all(not w._resize_timer.isActive() for w in main._sticky_windows.values()))
    with db._connection() as conn:
        before = tuple(conn.iterdump())
    exported, salt, shortcuts = db.export_all_data(), security.SALT_FILE.read_bytes(), db.get_shortcuts()
    money = open_money(qtbot, main)
    for mode in ("amount", "read", "convert"):
        money.select_mode(mode)
        money.save_recent()
        money.copy_result()
    money.close()
    assert open_money(qtbot, main) is money
    main._lock()
    main._unlock()
    with db._connection() as conn:
        assert tuple(conn.iterdump()) == before
    assert db.export_all_data() == exported
    assert security.SALT_FILE.read_bytes() == salt
    assert db.get_shortcuts() == shortcuts
    assert [slot.shortcut_id for slot in main.sidebar.slots] == list(range(1, 7))
