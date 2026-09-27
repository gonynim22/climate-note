"""합성 Qt 창에서 금액·숫자 표기 도우미의 입력·결과·복사·기록을 검증한다."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QPushButton, QScrollArea, QWidget
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
import database as db
from ui_money_notation import MODES, MoneyNotationWindow


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, qapp):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def helper(qtbot):
    win = MoneyNotationWindow()
    qtbot.addWidget(win)
    win.show_near(QRect(10, 10, 64, 48), QApplication.primaryScreen().availableGeometry())
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    return win


def type_text(qtbot, widget, text):
    qtbot.mouseClick(widget, Qt.LeftButton)
    qtbot.waitUntil(widget.hasFocus)
    qtbot.keyClick(widget, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClicks(widget, text)


def choose(combo, value):
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def capture(win, name):
    QApplication.processEvents()
    appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if appdata:
        assert win.grab().save(str(Path(appdata).parent / f"money-notation-{name}.png"))


def test_window_frame_matches_date_time_calculator(qtbot):
    win = helper(qtbot)
    win.fit_to_screen(QRect(0, 0, 1000, 900))
    QApplication.processEvents()
    assert win.size().width() == 528 and win.size().height() == 668
    assert win.surface.size().width() == 480 and win.surface.size().height() == 620
    assert win.title_label.text() == "금액·숫자 표기 도우미"
    assert list(MODES.values()) == ["금액 표기", "큰 수 읽기", "단위 환산"]
    assert win.mode == "amount" and win.mode_buttons["amount"].isChecked()
    assert win.rail.width() == 108


def test_amount_mode_official_notation_and_copy_formats(qtbot):
    win = helper(qtbot)
    assert win.result_caption.text() == "공문서 금액 표기"
    assert win.result_label.text() == "금113,560원"
    assert win.result_detail.text().replace("\u200b", "") == "(금일십일만삼천오백육십원)"
    assert win.result_note.text() == "읽기: 십일만 삼천오백육십 원"
    assert win.copy_preview_text.full_text() == "금113,560원(금일십일만삼천오백육십원)"
    expected = {"official": "금113,560원(금일십일만삼천오백육십원)",
                "hangul": "금일십일만삼천오백육십원", "digits": "113,560"}
    for key, text in expected.items():
        choose(win.copy_format, key)
        qtbot.mouseClick(win.copy_button, Qt.LeftButton)
        assert QApplication.clipboard().text() == text
        assert win.copy_preview_text.full_text() == text
    choose(win.copy_format, "official")
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    assert "\u200b" not in QApplication.clipboard().text()
    type_text(qtbot, win.fields["amount"]["value"], "1000000")
    assert win.result_detail.text().replace("\u200b", "") == "(금일백만원)"
    assert win.result_detail.property("strong") is True
    assert "제2조" in win.law_box.text()


@pytest.mark.parametrize("mode,key,value,message", [
    ("amount", "value", "12.5", "정수만 입력할 수 있습니다."),
    ("amount", "value", "0", "금액은 1원 이상 1경 미만이어야 합니다."),
    ("amount", "value", "1,2,3", "숫자와 세 자리 쉼표만 입력할 수 있습니다."),
    ("read", "value", "", "값을 입력하세요."),
    ("read", "value", "10000000000000000", "절댓값 1경 미만까지 지원합니다."),
    ("convert", "value", "1.1234567", "소수는 6자리까지 입력할 수 있습니다."),
    ("convert", "value", "10,000,000,000,000", "절댓값 1경 미만까지 지원합니다."),
])
def test_invalid_input_clears_result_and_blocks_copy_and_record(qtbot, mode, key, value, message):
    win = helper(qtbot)
    win.select_mode(mode)
    QApplication.clipboard().setText("원래 클립보드")
    win.fields[mode][key].setText(value)
    assert win.error_label.isVisible() and win.error_label.text() == message
    assert win.result_label.text() == "—"
    assert not win.copy_button.isEnabled() and not win.save_button.isEnabled()
    assert win.copy_preview_text.full_text() == "—"
    win.copy_result()
    win.save_recent()
    assert QApplication.clipboard().text() == "원래 클립보드"
    assert win.history == []
    if mode == "convert":
        assert all(label.full_text() == "—" for _name, label in win.unit_rows.values())


def test_read_mode_scopes_unit_and_copy(qtbot):
    win = helper(qtbot)
    win.select_mode("read")
    assert win.result_label.text() == "12억 3456만 7890원"
    assert win.result_detail.text() == "십이억 삼천사백오십육만 칠천팔백구십 원"
    assert win.result_note.text() == "1,234,567,890원"
    choose(win.fields["read"]["scope"], "man")
    assert win.result_label.text() == "약 12억 3457만원"
    assert win.result_note.text() == "원래 값 1,234,567,890원"
    choose(win.fields["read"]["scope"], "eok")
    assert win.result_label.text() == "약 12.3억원"
    assert win.result_detail.text() == "십이억 삼천만 원"
    choose(win.fields["read"]["scope"], "all")
    # QTest.keyClicks()는 이 Qt 빌드에서 비-ASCII 문자(한글 등)에 네이티브 크래시를 일으켜 setText()로 대체한다.
    unit_field = win.fields["read"]["unit"]
    qtbot.mouseClick(unit_field, Qt.LeftButton)
    qtbot.waitUntil(unit_field.hasFocus)
    unit_field.setText("명")
    assert win.result_label.text() == "12억 3456만 7890명"
    assert win.fields["read"]["unit"].maxLength() == 8
    choose(win.copy_format, "digits")
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    assert QApplication.clipboard().text() == "1,234,567,890"


def test_convert_mode_table_is_exact_and_result_rounds_only_for_display(qtbot):
    win = helper(qtbot)
    win.select_mode("convert")
    assert win.result_label.text() == "12.35억원"
    assert win.result_detail.text() == "= 1,234,567천원"
    assert win.result_note.text() == "표시만 소수 2자리 반올림 · 표는 정확한 값"
    table = {key: value.full_text() for key, (_name, value) in win.unit_rows.items()}
    assert table == {"won": "1,234,567,000", "k": "1,234,567", "m": "1,234.567",
                     "eok": "12.34567", "jo": "0.001234567"}
    assert win.unit_rows["eok"][1].property("hit") is True
    assert win.unit_rows["won"][1].property("hit") is False
    choose(win.fields["convert"]["digits"], -1)
    assert win.result_label.text() == "12.34567억원"
    choose(win.copy_format, "table")
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    assert QApplication.clipboard().text() == (
        "원\t1,234,567,000\n천원\t1,234,567\n백만원\t1,234.567\n억원\t12.34567\n조원\t0.001234567")
    choose(win.fields["convert"]["to"], "jo")
    assert win.unit_rows["jo"][1].property("hit") is True


def test_mode_inputs_and_copy_format_are_kept_per_mode(qtbot):
    win = helper(qtbot)
    win.fields["amount"]["value"].setText("5,000")
    choose(win.copy_format, "hangul")
    win.select_mode("read")
    assert win.copy_format.currentData() == "notation"
    win.select_mode("amount")
    assert win.fields["amount"]["value"].text() == "5,000"
    assert win.copy_format.currentData() == "hangul"
    assert win.result_label.text() == "금5,000원"


def test_recent_history_records_restores_deduplicates_and_limits(qtbot):
    win = helper(qtbot)
    qtbot.keyClick(win.fields["amount"]["value"], Qt.Key_Return)
    win.select_mode("read")
    choose(win.fields["read"]["scope"], "man")
    win.save_recent()
    win.select_mode("convert")
    win.save_recent()
    win.save_recent()
    assert [entry["mode"] for entry in win.history] == ["convert", "read", "amount"]
    assert win.history[2]["label"] == "금액 표기 · 금113,560원"
    assert win.recent_combo.count() == 4
    win.fields["read"]["value"].setText("5")
    win.restore_recent(win.history[1])
    assert win.mode == "read"
    assert win.fields["read"]["value"].text() == "1,234,567,890"
    assert win.result_label.text() == "약 12억 3457만원"
    assert win.fields["convert"]["value"].text() == "1,234,567"
    win.select_mode("amount")
    for index in range(14):
        win.fields["amount"]["value"].setText(str(index + 1))
        win.save_recent()
    assert len(win.history) == 12
    assert win.history[0]["values"]["value"] == "14"


@pytest.mark.parametrize("key", [Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter])
def test_focused_mode_and_action_buttons_support_keyboard(qtbot, key):
    win = helper(qtbot)
    mode = win.mode_buttons["convert"]
    mode.setFocus()
    qtbot.waitUntil(mode.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), key)
    assert win.mode == "convert"
    win.save_button.setFocus()
    qtbot.waitUntil(win.save_button.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), key)
    assert len(win.history) == 1 and win.history[0]["mode"] == "convert"


def test_dropdown_esc_closes_list_only_then_esc_hides_window(qtbot):
    win = helper(qtbot)
    qtbot.mouseClick(win.copy_format, Qt.LeftButton)
    qtbot.waitUntil(win.copy_format.view().isVisible)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    qtbot.waitUntil(lambda: not win.copy_format.view().isVisible())
    assert win.isVisible()
    win.close_button.setFocus()
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    assert not win.isVisible()


def test_hide_owned_popups_closes_open_list(qtbot):
    win = helper(qtbot)
    win.select_mode("convert")
    combo = win.fields["convert"]["to"]
    combo.showPopup()
    qtbot.waitUntil(combo.view().isVisible)
    win.hide_owned_popups()
    qtbot.waitUntil(lambda: not combo.view().isVisible())
    capture(win, "convert")


LONGEST = {
    "amount": {"value": "9,999,999,999,999,999"},
    "read": {"value": "-9,999,999,999,999,999", "unit": "만톤CO2eq"},
    "convert": {"value": "-9,999,999,999.999999"},
}
ERRORS = {"amount": "0", "read": "1,2,3", "convert": "1.1234567"}


@pytest.mark.parametrize("mode", list(MODES))
@pytest.mark.parametrize("state", ["normal", "error", "longest"])
@pytest.mark.parametrize("size", [QSize(1000, 900), QSize(480, 500), QSize(420, 500)])
def test_all_modes_fit_work_area_without_scroll_or_clipping(qtbot, mode, state, size):
    win = helper(qtbot)
    win.select_mode(mode)
    if state == "error":
        win.fields[mode]["value"].setText(ERRORS[mode])
    elif state == "longest":
        for key, value in LONGEST[mode].items():
            win.fields[mode][key].setText(value)
        if mode == "convert":
            choose(win.fields["convert"]["from"], "won")
            choose(win.fields["convert"]["to"], "jo")
            choose(win.fields["convert"]["digits"], -1)
    available = QRect(QPoint(0, 0), size)
    win.fit_to_screen(available)
    QApplication.processEvents()
    assert available.contains(win.geometry())
    assert not win.findChildren(QScrollArea)
    assert win.error_label.isVisible() == (state == "error")
    assert win.title_label.width() >= win.title_label.fontMetrics().horizontalAdvance(win.title_label.text())
    for control in win.page_widgets[mode].findChildren(QWidget):
        if isinstance(control, (QLineEdit, QComboBox, QPushButton, QLabel)) and control.isVisible():
            rectangle = QRect(control.mapTo(win.body, QPoint()), control.size())
            assert win.body.rect().contains(rectangle), (control.accessibleName(), rectangle, win.body.rect())
            assert control.height() >= control.fontMetrics().height()
    preview = QRect(win.copy_preview.mapTo(win.body, QPoint()), win.copy_preview.size())
    assert win.body.rect().contains(preview)
    for name, button in win.mode_buttons.items():
        assert button.width() >= button.fontMetrics().horizontalAdvance(MODES[name]) + 14
    for control in (win.body, win.error_label, win.result_card, win.copy_format,
                    win.copy_button, win.save_button, win.recent_combo, win.status_label):
        if control.isVisible():
            rectangle = QRect(control.mapTo(win.surface, QPoint()), control.size())
            assert win.surface.rect().contains(rectangle), (control.objectName(), rectangle, win.surface.rect())
    for label in (win.result_caption, win.result_label, win.result_detail, win.result_note):
        if label.isVisible():
            rectangle = QRect(label.mapTo(win.result_card, QPoint()), label.size())
            assert win.result_card.rect().contains(rectangle)
            if label.text():
                assert label.height() >= label.fontMetrics().height()
    main_font = win.result_label.font()
    from PySide6.QtGui import QFontMetrics
    assert QFontMetrics(main_font).horizontalAdvance(win.result_label.text()) <= win.result_label.width()
    assert win.body.geometry().bottom() < win.result_card.geometry().top()
    assert win.result_card.geometry().bottom() < win.copy_button.geometry().top()
    assert win.copy_button.geometry().bottom() < win.recent_combo.geometry().top()
    capture(win, f"{mode}-{state}-{size.width()}x{size.height()}")


def test_returning_from_short_work_area_restores_full_layout_and_keeps_inputs(qtbot):
    win = helper(qtbot)
    win.select_mode("read")
    win.fields["read"]["value"].setText("5,000")
    win.save_recent()
    original = list(win.history)
    win.fit_to_screen(QRect(0, 0, 420, 500))
    QApplication.processEvents()
    assert not win.mode_title.isVisible() and not win.status_label.isVisible()
    assert win.result_label.text() == "5000원"
    win.fit_to_screen(QRect(0, 0, 1000, 900))
    QApplication.processEvents()
    assert win.size() == QSize(528, 668)
    assert win.mode_title.isVisible() and win.status_label.isVisible() and win.result_note.isVisible()
    assert win.law_box.text().count("\n") == 1
    assert win.history == original
    assert win.fields["read"]["value"].text() == "5,000"
