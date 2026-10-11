"""캘린더 위치 편집(2026-10-11 J안): 평소 고정, 십자 화살표로 편집 → 머리줄 끌기 → 완료. 합성 데이터로만 검증한다."""
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
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


def drag_header(win, delta=QPoint(40, 25)):
    start = win.month_label.rect().center()
    QTest.mousePress(win.month_label, Qt.LeftButton, pos=start)
    QTest.mouseMove(win.month_label, start + delta, delay=20)
    QTest.mouseRelease(win.month_label, Qt.LeftButton, pos=start + delta)


def controls(win):
    return {
        "search": win.findChild(QWidget, "headerSearchButton"),
        "move": win.calendar_move_button,
        "done": win.calendar_move_done_button,
        "more": win._more_btn,
    }


@pytest.mark.parametrize("legacy", [None, "1", "0"], ids=["no-row", "legacy-on", "legacy-off"])
def test_starts_fixed_and_keeps_legacy_setting_row(qtbot, legacy):
    if legacy is not None:
        db.save_setting(db.SETTING_CALENDAR_MOVE_ENABLED, legacy)
    win = window(qtbot)
    position = win.pos()
    drag_header(win)
    assert win.pos() == position
    assert not win._calendar_move_editing
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "corner"
    # 예전 설정 행은 읽지 않지만 지우거나 새로 만들지도 않는다(Export에도 그대로).
    assert db.get_setting(db.SETTING_CALENDAR_MOVE_ENABLED, "missing") == (legacy or "missing")
    settings = json.loads(db.export_all_data())["settings"]
    assert settings.get(db.SETTING_CALENDAR_MOVE_ENABLED) == legacy


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_move_button_edit_drag_and_done_in_every_size(qtbot, scale):
    win = window(qtbot, scale)
    c = controls(win)
    assert c["move"].isVisible() and not c["done"].isVisible()
    qtbot.mouseClick(c["move"], Qt.LeftButton)
    assert win._calendar_move_editing
    assert c["done"].isVisible()
    assert not any(c[k].isVisible() for k in ("search", "move", "more"))
    drag_header(win)
    assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
    assert int(db.get_setting(db.SETTING_CALENDAR_X)) == win.x()
    assert int(db.get_setting(db.SETTING_CALENDAR_Y)) == win.y()
    assert win.screen().availableGeometry().contains(win.geometry())
    assert win._calendar_move_editing  # 한 번 끌어도 '완료' 전까지 편집 상태
    qtbot.mouseClick(c["done"], Qt.LeftButton)
    assert not win._calendar_move_editing
    assert all(c[k].isVisible() for k in ("search", "move", "more")) and not c["done"].isVisible()
    position = win.pos()
    drag_header(win)
    assert win.pos() == position


def test_edit_mode_keeps_input_focus_and_writes_nothing(qtbot):
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
    qtbot.mouseClick(win.calendar_move_done_button, Qt.LeftButton)
    assert win.pos() == position
    assert win.schedule_input.text() == "📌 아직 입력 중"
    assert win.focusWidget() is win.schedule_input
    with db._connection() as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM sticky_notes")] == before_rows
        assert dict(conn.execute("SELECT key,value FROM app_settings")) == before_settings
    assert security.SALT_FILE.read_bytes() == salt


def test_keyboard_enters_and_leaves_edit_mode(qtbot):
    win = window(qtbot)
    search = win.findChild(QWidget, "headerSearchButton")
    search.setFocus(Qt.TabFocusReason)
    qtbot.waitUntil(search.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
    qtbot.waitUntil(lambda: QApplication.focusWidget() is win.calendar_move_button)
    for key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
        qtbot.keyClick(QApplication.focusWidget(), key)
        assert win._calendar_move_editing
        assert win.focusWidget() is win.calendar_move_done_button
        qtbot.keyClick(QApplication.focusWidget(), key)
        assert not win._calendar_move_editing
        assert win.focusWidget() is win.calendar_move_button
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Space)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)  # '완료'에 포커스가 있어도 Esc는 창까지 올라온다
    assert not win._calendar_move_editing
    assert win.focusWidget() is win.calendar_move_button


def test_escape_on_window_ends_edit_mode(qtbot):
    win = window(qtbot)
    win.calendar_move_button.click()
    qtbot.keyClick(win, Qt.Key_Escape)
    assert not win._calendar_move_editing


def test_move_button_texts_and_plain_arrows(qtbot):
    win = window(qtbot)
    button = win.calendar_move_button
    assert not button.isCheckable()
    assert button.accessibleName() == "캘린더 옮기기"
    assert button.toolTip() == "캘린더 옮기기 · 누른 뒤 머리줄을 끌어 옮깁니다"
    assert win.calendar_move_done_button.text() == "완료"
    assert win.calendar_move_done_button.toolTip() == "위치 편집 끝내기 (Esc)"
    header = win.findChild(QWidget, "headerSection")
    origin = button.mapTo(header, QPoint())
    image = header.grab().toImage()
    ratio = image.devicePixelRatio()

    def pixel(x, y):
        return image.pixelColor(int((origin.x() + x) * ratio), int((origin.y() + y) * ratio))

    header_bg = pixel(-2, 6).name()  # 검색 단추와의 4px 간격은 머리줄 바탕
    assert pixel(6, 6).name() == header_bg       # 채운 상자 없음
    assert pixel(16, 29).name() == header_bg     # 예전 켜짐 점 없음
    assert pixel(10, 22).name() == header_bg     # 예전 꺼짐 사선 자리(8,24)-(24,8) 위, 화살표와 겹치지 않는 점
    assert pixel(16, 16).lightness() > 200       # 가운데 흰 십자 교차점


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_header_geometry_in_both_states(qtbot, scale):
    win = window(qtbot, scale)
    qtbot.wait(30)
    header = win.findChild(QWidget, "headerSection")
    right = win.findChild(QWidget, "headerRightGroup")

    def rect(w):
        return QRect(w.mapTo(header, QPoint()), w.size())

    def month_centered():
        center = win.month_label.mapTo(header, QPoint()).x() + win.month_label.width() / 2
        return abs(center - header.width() / 2) <= 1

    c = controls(win)
    rects = [rect(c[k]) for k in ("search", "move", "more")]
    assert all(header.rect().contains(r) for r in rects)
    assert all(rects[i + 1].left() - rects[i].right() - 1 == 4 for i in range(2))
    assert month_centered()
    assert win.next_btn.mapTo(header, QPoint()).x() + win.next_btn.width() <= rects[0].left()
    if scale == "compact":
        assert win.width() == 380
    win.calendar_move_button.click()
    QApplication.processEvents()
    done = rect(c["done"])
    assert c["done"].size().width() == 52 and c["done"].size().height() == 32
    assert rect(right).contains(done) and done.right() == rect(right).right()
    assert c["done"].fontMetrics().horizontalAdvance("완료") <= 52 - 2 * 8 - 2  # 125/150%에서도 안 잘림
    assert month_centered()
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        target = Path(appdata).parent
        assert win.grab().save(str(target / f"calendar-move-edit-{scale}.png"))
