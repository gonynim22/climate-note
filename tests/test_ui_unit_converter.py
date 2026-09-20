"""합성 데이터에서 환산기 실제 입력·창 수명·기존 저장 불변과 렌더를 확인한다."""
import os
from pathlib import Path
import sqlite3

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from qfluentwidgets.common.font import fontFamilies, setFontFamilies
from shiboken6 import isValid

from app_fonts import apply_app_font
import database as db
import security
import ui_main
import ui_settings
from ui_main import MainCalendarWindow
from ui_unit_converter import UnitConverterWindow
from unit_converter import parse_number


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


def activate(qtbot, win):
    win.show()
    win.raise_()
    win.activateWindow()
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)


def converter(qtbot):
    win = UnitConverterWindow()
    qtbot.addWidget(win)
    activate(qtbot, win)
    return win


def main_window(qtbot, scale="compact"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    activate(qtbot, main)
    return main


def open_converter(qtbot, main, keyboard=False):
    activate(qtbot, main)
    qtbot.mouseClick(main.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: main._mini_apps_popup is not None)
    pocket = main._mini_apps_popup
    assert QTest.qWaitForWindowExposed(pocket)
    assert QTest.qWaitForWindowActive(pocket)
    if keyboard:
        pocket.converter_card.setFocus()
        qtbot.waitUntil(pocket.converter_card.hasFocus)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    else:
        qtbot.mouseClick(pocket.converter_card, Qt.LeftButton)
    win = main._unit_converter
    assert win is not None
    assert QTest.qWaitForWindowActive(win)
    qtbot.waitUntil(win.input.hasFocus)
    assert main._mini_apps_popup is None
    assert not main.sidebar.mini_apps_button.isChecked()
    return win


def capture(win, name):
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        assert win.grab().save(str(Path(appdata).parent / f"unit-converter-{name}.png"))


def test_input_swap_other_unit_and_recent_keyboard(qtbot):
    win = converter(qtbot)
    win.input.setFocus()
    qtbot.keyClick(win.input, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClicks(win.input, "123.456789012345")
    assert win._result == pytest.approx(48.6050350442303)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert len(win.history.items) == 1
    win.swap_button.setFocus()
    qtbot.waitUntil(win.swap_button.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert win.from_combo.currentData() == "in"
    assert win._result == pytest.approx(123.456789012345, rel=1e-14)
    assert len(win.history.items) == 1  # 버튼 Enter가 기록 저장으로 전파되지 않는다.
    qtbot.mouseClick(win._row_widgets["m"][0], Qt.LeftButton)
    assert win.to_combo.currentData() == "m"
    assert win._result == pytest.approx(1.23456789012345)
    chip = win.recent_content.findChild(QPushButton, "recentCalculation")
    qtbot.mouseClick(chip, Qt.LeftButton)
    assert win.input.text() == "123.456789012345"
    assert win.from_combo.currentData() == "cm"
    assert win.to_combo.currentData() == "in"
    assert win.input.hasFocus()


def test_invalid_input_and_invalid_domain_do_not_save_or_swap(qtbot):
    win = converter(qtbot)
    for text in ("12abc", "1,23", "1e999", "", "-"):
        win.input.setText(text)
        assert win.input.text() == text
        assert win.result_label.text() == "—"
        assert not win.swap_button.isEnabled()
        win.save_recent()
        assert not win.history.items
    win.select_category("fuel")
    win.input.setText("0")
    assert win._result is None
    assert "0보다" in win.status_label.toolTip()
    capture(win, "invalid-fuel")
    win.input.setText("1,000")
    assert win._result == pytest.approx(.1)


@pytest.mark.parametrize("cid", ["len", "energy", "co2", "pm", "db", "cook", "fuel"])
def test_render_categories_and_actual_geometry(qtbot, cid):
    win = converter(qtbot)
    button = win.category_buttons[cid]
    win.category_scroll.ensureWidgetVisible(button)
    button.setFocus()
    qtbot.waitUntil(button.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert win.category_id == cid
    win.input.setText("123456.789")
    win.save_recent()
    QApplication.processEvents()
    assert win.size().width() == 340
    assert win.size().height() == 460
    for control in (win.input, win.from_combo, win.to_combo, win.result_label, win.close_button):
        point = control.mapTo(win, QPoint())
        assert win.rect().contains(point)
        assert point.x()+control.width() <= win.width()
        assert point.y()+control.height() <= win.height()
    assert win.result_label.fontMetrics().horizontalAdvance(win.result_label.text()) <= win.result_label.width()
    assert win.other_scroll.viewport().height() > 40
    assert win.from_combo.currentData(Qt.ToolTipRole)
    capture(win, cid)


def test_combo_escape_closes_dropdown_before_window(qtbot):
    win = converter(qtbot)
    win.to_combo.setFocus()
    qtbot.waitUntil(win.to_combo.hasFocus)
    qtbot.keyClick(win.to_combo, Qt.Key_Down, Qt.AltModifier)
    qtbot.waitUntil(win.to_combo.view().isVisible)
    popup = win.to_combo.view().window()
    assert QTest.qWaitForWindowExposed(popup)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert not win.to_combo.view().isVisible()
    assert win.to_combo.currentData() != "in"
    win.to_combo.showPopup()
    qtbot.waitUntil(win.to_combo.view().isVisible)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    assert win.isVisible()
    assert not win.to_combo.view().isVisible()
    win.input.setFocus()
    qtbot.keyClick(win.input, Qt.Key_Escape)
    assert not win.isVisible()


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_pocket_launch_reuse_close_and_no_focus_theft(qtbot, scale):
    main = main_window(qtbot, scale)
    win = open_converter(qtbot, main, keyboard=scale=="medium")
    win.input.setText("42")
    qtbot.keyClick(win.input, Qt.Key_Return)
    win.close()
    assert open_converter(qtbot, main) is win
    assert win.input.text() == "42"
    assert len(win.history.items) == 1
    assert len(main.findChildren(UnitConverterWindow)) == 1
    assert win.screen().availableGeometry().contains(win.geometry())


@pytest.mark.parametrize("action", ["lock", "tray", "hide", "sidebar", "reset_prepare"])
def test_hiding_cancels_owned_popup_and_preserves_session(qtbot, action):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.input.setText("42")
    win.save_recent()
    win.to_combo.showPopup()
    qtbot.waitUntil(win.to_combo.view().isVisible)
    if action == "lock":
        main._lock()
        main._open_unit_converter()
        assert not win.isEnabled()
        main._unlock()
    elif action == "tray":
        main._minimize_to_tray()
        main._open_unit_converter()
        main.toggle_visibility()
    elif action == "hide":
        main.hide()
        main.show()
    elif action == "sidebar":
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
        main._apply_sidebar_visibility()
    else:
        main._discard_data_widgets()
    assert not win.isVisible()
    assert not win.to_combo.view().isVisible()
    assert win.input.text() == "42"
    assert len(win.history.items) == 1


def test_scale_change_keeps_calculation_and_failed_quit_keeps_window(qtbot, monkeypatch):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.input.setText("24")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    main._apply_calendar_scale()
    assert main._unit_converter is win
    assert win.isVisible()
    assert parse_number(win.input.text()) == 24
    monkeypatch.setattr(main, "save_all_sticky_notes", lambda: False)
    assert not main.prepare_for_quit()
    assert main._unit_converter is win
    monkeypatch.setattr(main, "save_all_sticky_notes", lambda: True)
    assert main.prepare_for_quit()
    assert main._unit_converter is None
    qtbot.waitUntil(lambda: not isValid(win))


def test_failed_schedule_save_blocks_converter(qtbot, monkeypatch):
    main = main_window(qtbot)
    monkeypatch.setattr(main, "_save_schedule_edit", lambda: False)
    main._open_unit_converter()
    assert main._unit_converter is None


def test_calculations_preserve_all_existing_data(qtbot, tmp_path):
    for sid in range(1, 7):
        db.update_shortcut(sid, f"기존 {sid}", str(tmp_path / f"{sid}.txt"))
    db.add_schedule("2026-09-20", "📌 기존 일정", "#FFD166")
    db.save_memo("2026-09-20", "메모 원문")
    note = db.create_sticky_note()
    db.update_sticky_note(note, content="<p>기존 스티키</p>")
    db.create_dday_widget("기념일", "2026-12-31")
    db.create_focus_widget("기존 목표")
    main = main_window(qtbot)
    with db._connection() as conn:
        before = tuple(conn.iterdump())
    salt = security.SALT_FILE.read_bytes()
    exported = db.export_all_data()
    for cid in ("len", "temp", "db", "fuel", "co2"):
        win = open_converter(qtbot, main)
        win.select_category(cid)
        win.input.setText("12.3456789")
        win.swap()
        win.save_recent()
        win.close()
    with db._connection() as conn:
        assert tuple(conn.iterdump()) == before
    assert db.export_all_data() == exported
    assert security.SALT_FILE.read_bytes() == salt


@pytest.mark.parametrize("failure", [None, "backup", "database"])
def test_only_successful_factory_reset_discards_calculation(qtbot, monkeypatch, failure):
    main = main_window(qtbot)
    win = open_converter(qtbot, main)
    win.input.setText("42")
    win.save_recent()
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
        assert main._unit_converter is win
        assert win.input.text() == "42"
        assert len(win.history.items) == 1
    else:
        assert main._unit_converter is None
        qtbot.waitUntil(lambda: not isValid(win))


def test_disconnected_screen_and_smaller_work_area_are_clamped(qtbot, monkeypatch):
    win = converter(qtbot)
    available = QRect(-1280, 20, 1280, 700)
    class Screen:
        def availableGeometry(self):
            return available
    monkeypatch.setattr(QApplication, "screenAt", lambda point: Screen())
    win.move(3000, 2000)
    win.fit_to_screen()
    assert available.contains(win.geometry())
    available = QRect(0, 0, 340, 400)
    win.fit_to_screen()
    assert available.contains(win.geometry())
