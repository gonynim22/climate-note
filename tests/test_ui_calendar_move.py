"""이동 상태·실제 입력·저장 호환성을 합성 데이터로만 검증한다."""
import json
import os
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

import database as db
import security
import ui_main
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def isolated_move_ui(app_dir, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kwargs: None)


def window(qtbot, scale="compact"):
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    qtbot.waitExposed(win)
    qtbot.waitUntil(win.isActiveWindow)
    return win


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_real_mouse_drag_allowed_in_every_size(qtbot, scale):
    win = window(qtbot, scale)
    assert win.calendar_move_button.isChecked()
    # fallback은 기존 사용자의 설정 행을 임의로 추가하지 않는다.
    assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "missing") == "missing"
    start = win.month_label.rect().center()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=start)
    QTest.mouseMove(win.month_label, start + QPoint(40, 25), delay=20)
    assert win._calendar_drag_started
    QTest.mouseRelease(win.month_label, Qt.LeftButton, pos=start + QPoint(40, 25))
    assert win._calendar_drag_offset is None
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
    assert int(db.get_setting(db.SETTING_CALENDAR_X)) == win.x()
    assert int(db.get_setting(db.SETTING_CALENDAR_Y)) == win.y()
    assert win.screen().availableGeometry().contains(win.geometry())


def test_toggle_saves_without_moving_or_editing_and_restores_after_reopen(qtbot):
    note = db.create_sticky_note()
    db.update_sticky_note(note, content="<p>기존 메모</p>")
    win = window(qtbot)
    with db._connection() as conn:
        before_rows = [tuple(row) for row in conn.execute("SELECT * FROM sticky_notes")]
        before_settings = dict(conn.execute("SELECT key,value FROM app_settings"))
    salt = security.SALT_FILE.read_bytes()
    win.schedule_input.setText("📌 아직 입력 중")
    win.schedule_input.setFocus()
    qtbot.waitUntil(win.schedule_input.hasFocus)
    position = win.pos()
    qtbot.mouseClick(win.calendar_move_button, Qt.LeftButton)
    assert win.pos() == position
    assert win.schedule_input.text() == "📌 아직 입력 중"
    assert win.schedule_input.hasFocus()
    assert not win.calendar_move_button.isChecked()
    assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED) == "0"
    assert "OFF" in win.calendar_move_button.toolTip()
    with db._connection() as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM sticky_notes")] == before_rows
        after = dict(conn.execute("SELECT key,value FROM app_settings"))
    assert after == {**before_settings, db.SETTING_CALENDAR_MOVE_ENABLED: "0"}
    assert security.SALT_FILE.read_bytes() == salt
    for scale in db.CALENDAR_SCALES:
        db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
        win._apply_calendar_scale()
        assert not win.calendar_move_button.isChecked()
    # 재실행은 이전 메인/스티키가 새 창의 활성화를 경쟁하지 않는 상태에서 검사한다.
    assert win.prepare_for_quit()
    win._minimize_to_tray()
    win._discard_data_widgets()
    reopened = window(qtbot)
    assert not reopened._calendar_drag_allowed()


def test_keyboard_space_enter_and_mouse_keep_state_in_sync(qtbot):
    win = window(qtbot)
    button = win.calendar_move_button
    search = win.findChild(QWidget, "headerSearchButton")
    search.setFocus(Qt.TabFocusReason)
    qtbot.waitUntil(search.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    qtbot.waitUntil(lambda: QApplication.focusWidget() is button)
    for key, expected in [(Qt.Key_Space, False), (Qt.Key_Return, True), (Qt.Key_Enter, False)]:
        qtbot.keyClick(QApplication.focusWidget(), key)
        assert button.isChecked() is expected
        assert win._calendar_drag_allowed() is expected
        assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED) == str(int(expected))
    qtbot.mouseClick(button, Qt.LeftButton)
    assert button.isChecked()


def test_failed_setting_save_restores_previous_state(qtbot, monkeypatch):
    win = window(qtbot)
    def fail(*args):
        raise sqlite3.OperationalError("synthetic save failure")
    monkeypatch.setattr(db, "save_setting", fail)
    qtbot.mouseClick(win.calendar_move_button, Qt.LeftButton)
    assert win.calendar_move_button.isChecked()
    assert win._calendar_drag_allowed()
    assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "missing") == "missing"


@pytest.mark.parametrize("action", ("off", "lock", "tray", "scale", "discard"))
def test_in_progress_drag_cancelled_on_lifecycle_change(qtbot, action):
    win = window(qtbot)
    point = win.month_label.rect().center()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=point)
    assert win._calendar_drag_offset is not None
    if action == "off":
        win.calendar_move_button.click()
    elif action == "lock":
        win._lock()
    elif action == "tray":
        win._minimize_to_tray()
    elif action == "scale":
        db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
        win._apply_calendar_scale()
    else:
        win._discard_data_widgets()
    assert win._calendar_drag_offset is None
    assert not win._calendar_drag_started
    QTest.mouseRelease(win.month_label, Qt.LeftButton, pos=point)
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"
    if action in ("lock", "tray"):
        win.calendar_move_button.click()
        assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "missing") == "missing"
        assert not win._calendar_drag_allowed()
        if action == "lock":
            win._unlock()
        else:
            win.toggle_visibility()
        assert win._calendar_drag_allowed()


def test_setting_pin_export_import_and_reset_fallback(qtbot):
    win = window(qtbot)
    qtbot.mouseClick(win.calendar_move_button, Qt.LeftButton)
    db.add_schedule("2026-09-20", "🎯 기존 일정", "#4CC9F0")
    salt = security.SALT_FILE.read_bytes()
    exported = db.export_all_data()
    encrypted = security.encrypt_with_pin(exported.encode("utf-8"), "1234")
    payload = security.decrypt_with_pin(encrypted, "1234").decode("utf-8")
    assert json.loads(payload)["settings"][db.SETTING_CALENDAR_MOVE_ENABLED] == "0"
    db.save_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "1")
    db.import_all_data(payload)
    win._on_import_complete()
    assert not win.calendar_move_button.isChecked()
    assert security.SALT_FILE.read_bytes() == salt
    assert all(s["content"] == "🎯 기존 일정" for s in db.get_schedules("2026-09-20"))
    win._discard_data_widgets()
    db.reset_database()
    win._on_factory_reset()
    assert win.calendar_move_button.isChecked()
    assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "missing") == "missing"
    assert db.CURRENT_SCHEMA_VERSION == 17


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_header_geometry_and_synthetic_capture(qtbot, scale):
    win = window(qtbot, scale)
    qtbot.wait(30)
    header = win.findChild(QWidget, "headerSection")
    controls = [win.findChild(QWidget, "headerSearchButton"), win.calendar_move_button, win._more_btn]
    rects = [QRect(w.mapTo(header, QPoint()), w.size()) for w in controls]
    assert all(header.rect().contains(rect) for rect in rects)
    assert all(rects[i+1].left() - rects[i].right() - 1 == 4 for i in range(2))
    center = win.month_label.mapTo(header, QPoint()).x() + win.month_label.width()/2
    assert abs(center - header.width()/2) <= 1
    assert win.next_btn.mapTo(header, QPoint()).x() + win.next_btn.width() <= rects[0].left()
    if scale == "compact":
        assert win.width() == 380
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        target = Path(appdata).parent
        assert win.grab().save(str(target / f"calendar-move-{scale}-on.png"))
        qtbot.mouseClick(win.calendar_move_button, Qt.LeftButton)
        assert header.grab().save(str(target / f"calendar-move-{scale}-off.png"))


def test_on_state_is_a_small_dot_not_a_filled_box(qtbot):
    """디자인 점검 11번: 켜짐은 연한 파랑 상자 대신 다른 아이콘처럼 투명하게 두고 아래 작은 점으로만 표시한다."""
    win = window(qtbot)
    header = win.findChild(QWidget, "headerSection")
    button = win.calendar_move_button
    origin = button.mapTo(header, QPoint())

    def pixel(x, y):
        image = header.grab().toImage()
        ratio = image.devicePixelRatio()
        return image.pixelColor(int((origin.x() + x) * ratio), int((origin.y() + y) * ratio)).name()

    header_bg = pixel(-2, 6)  # 검색 버튼과의 4px 간격은 머리줄 바탕이다
    for on in (True, False):
        button.setChecked(on)
        QApplication.processEvents()
        assert pixel(6, 6) == header_bg  # 채운 상자·테두리 없음
        assert (pixel(16, 29) == "#93c5fd") is on
