"""화면 글자 따기 도구 창·등록·아이콘 (가짜 엔진·가짜 스크린샷, 실제 화면을 찍지 않는다)."""
import re
import sys
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap, QTextCursor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
from app_paths import resource_root
import database as db
import optional_mini_apps
import ui_main
from screen_text import APP
from screen_text.engine import ModelIntegrityError, RecognitionCancelled
from screen_text.layout import Grid, GridCell, RecognizedBoxes, TextBox
from screen_text.window import CONTENT_HEIGHT, CONTENT_WIDTH, SHADOW_MARGIN, ScreenTextWindow

ROOT = Path(__file__).resolve().parents[1]
TABLE = [
    TextBox(10, 10, 30, 16, "구분", 0.99), TextBox(120, 10, 70, 16, "점검 사업장", 0.99), TextBox(260, 10, 30, 16, "위반", 0.99),
    TextBox(12, 34, 30, 16, "대전", 0.99), TextBox(140, 34, 16, 16, "42", 0.99), TextBox(265, 34, 8, 16, "3", 0.99),
    TextBox(12, 58, 30, 16, "충북", 0.99), TextBox(140, 58, 16, 16, "5l", 0.95), TextBox(265, 58, 8, 16, "4", 0.99),
]
SENTENCE = [TextBox(0, 0, 200, 16, "환경 점검 결과 알림", 0.99)]
# 윗줄에 '42'가 있고 아랫줄의 '4'(점수 0.5)만 불확실한 문장형 두 줄(표가 아님)
SUBSTRING = [TextBox(0, 0, 30, 16, "합계", 0.99), TextBox(60, 0, 20, 16, "42", 0.99), TextBox(0, 30, 10, 16, "4", 0.5)]
# 3칸 표, 한 줄 문장, 2칸 표: 좁은 표의 3번째 칸은 비어 있는 채움 칸이 된다
MIXED_WIDTH = [
    TextBox(10, 0, 30, 16, "가", 0.99), TextBox(120, 0, 30, 16, "나", 0.99), TextBox(260, 0, 30, 16, "다", 0.99),
    TextBox(10, 24, 30, 16, "1", 0.99), TextBox(120, 24, 30, 16, "2", 0.99), TextBox(260, 24, 30, 16, "3", 0.99),
    TextBox(10, 48, 200, 16, "중간 문장", 0.99),
    TextBox(10, 72, 30, 16, "라", 0.99), TextBox(120, 72, 30, 16, "마", 0.99),
    TextBox(10, 96, 30, 16, "4", 0.99), TextBox(120, 96, 30, 16, "5", 0.99),
]


class IgnoresCancelEngine:
    """취소 여부를 보지 않고 늦게 결과를 돌려주는 엔진(실행 번호로 버려지는지 확인용)."""

    def __init__(self, gate):
        self.gate = gate

    def recognize(self, rgb, cancelled):
        self.gate.wait(5)
        return list(TABLE)


class FakeEngine:
    def __init__(self, boxes=(), gate=None, error=None):
        self.boxes, self.gate, self.error, self.calls = list(boxes), gate, error, 0

    def recognize(self, rgb, cancelled):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(5)
        if cancelled():
            raise RecognitionCancelled
        if self.error is not None:
            raise self.error
        return list(self.boxes)


def shot(fill="white"):
    pixmap = QPixmap(400, 300)
    pixmap.fill(QColor(fill))
    return [(QRect(0, 0, 400, 300), pixmap)]


def image(width=120, height=40):
    picture = QImage(width, height, QImage.Format_RGB888)
    picture.fill(QColor("white"))
    return picture


@pytest.fixture
def make(qtbot):
    def factory(engine=None, grab=None, engine_factory=None):
        win = ScreenTextWindow(None, engine_factory=engine_factory or (lambda: engine or FakeEngine(TABLE)),
                               grab=grab or shot)
        qtbot.addWidget(win)
        win.show_near(QRect(100, 100, 64, 48), QGuiApplication.primaryScreen().availableGeometry())
        qtbot.waitExposed(win)
        return win
    return factory


def recognized(qtbot, win, picture=None):
    win._on_captured(picture or image())
    qtbot.waitUntil(lambda: win.stack.currentWidget() is not win.busy_page, timeout=5000)


def test_intro_state_offline_note_and_focus(make):
    win = make()
    assert win.stack.currentWidget() is win.intro_page
    assert win.capture_button.isEnabled() and not win.message_label.isVisible()
    assert "인터넷 없이" in win.offline_label.text()
    assert win.size().width() <= 460 + 48


def test_capture_flow_shows_preview_table_tab_and_unsure(qtbot, make):
    win = make()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    assert not win.isVisible()
    overlay = win._capture.overlays[0]
    qtbot.waitExposed(overlay)
    qtbot.mousePress(overlay, Qt.LeftButton, pos=QPoint(10, 10))
    qtbot.mouseMove(overlay, QPoint(209, 109))
    qtbot.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(209, 109))
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page, timeout=5000)
    assert win.isVisible()
    assert 0 < win.preview.pixmap().height() <= 90
    assert win.table_tab.isVisible() and win.table_tab.isChecked()
    assert win.status_label.text() == "확인 필요 1곳"
    item = win.table.item(2, 1)
    assert item.text() == "5l" and item.background().color() == QColor("#FFE58A")


def test_text_only_result_hides_table_tab(qtbot, make):
    win = make(FakeEngine(SENTENCE))
    recognized(qtbot, win)
    assert not win.table_tab.isVisible() and win.text_tab.isChecked()
    assert win.text_edit.toPlainText() == "환경 점검 결과 알림"
    assert win.status_label.text() == "불확실한 곳 없음"


def test_copy_table_puts_tsv_and_html_on_clipboard(qtbot, make):
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    mime = QGuiApplication.clipboard().mimeData()
    assert mime.text().splitlines()[0] == "구분\t점검 사업장\t위반"
    assert "<td>점검 사업장</td>" in mime.html()
    assert win.status_label.text() == "복사했습니다"


def test_copy_text_tab_puts_edited_plain_text_only(qtbot, make):
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    win.text_edit.setPlainText("고친 글자")
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    mime = QGuiApplication.clipboard().mimeData()
    assert mime.text() == "고친 글자" and not mime.hasHtml()


def test_editing_unsure_cell_clears_mark_and_refreshes_text_tab(qtbot, make):
    win = make()
    recognized(qtbot, win)
    win.table.item(2, 1).setText("51")
    assert win.status_label.text() == "확인 완료"
    assert win.table.item(2, 1).background().style() == Qt.NoBrush
    assert "충북 51 4" in win.text_edit.toPlainText()


def test_editing_unsure_token_in_text_tab_updates_count(qtbot, make):
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    assert win.status_label.text() == "확인 필요 1곳"
    assert len(win.text_edit.extraSelections()) == 1
    win.text_edit.setPlainText(win.text_edit.toPlainText().replace("5l", "51"))
    assert win.status_label.text() == "확인 완료"
    assert win.text_edit.extraSelections() == []


def test_cancel_during_recognition_discards_late_result(qtbot, make):
    gate = threading.Event()
    win = make(FakeEngine(TABLE, gate=gate))
    win._on_captured(image())
    assert win.stack.currentWidget() is win.busy_page
    qtbot.mouseClick(win.cancel_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.intro_page
    gate.set()
    qtbot.wait(300)
    assert win.stack.currentWidget() is win.intro_page and win._blocks == []


def test_first_recognition_shows_model_loading_note(qtbot, make):
    gate = threading.Event()
    win = make(FakeEngine(TABLE, gate=gate))
    win._on_captured(image())
    assert win.first_load_label.isVisible()
    gate.set()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page, timeout=5000)
    win._on_captured(image())
    assert not win.first_load_label.isVisible()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page, timeout=5000)


def test_cancelled_recapture_restores_previous_preview(qtbot, make):
    gate = threading.Event()
    gate.set()
    engine = FakeEngine(TABLE, gate=gate)
    win = make(engine)
    recognized(qtbot, win, image(120, 40))
    first = win.preview.pixmap().size()
    gate.clear()
    win._on_captured(image(300, 200))
    assert win.preview.pixmap().size() != first
    qtbot.mouseClick(win.cancel_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.result_page
    assert win.preview.pixmap().size() == first
    gate.set()


def test_late_result_that_ignores_cancel_is_discarded_by_generation(qtbot, make):
    gate = threading.Event()
    win = make(engine_factory=lambda: IgnoresCancelEngine(gate))
    win._on_captured(image())
    qtbot.mouseClick(win.cancel_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.intro_page
    gate.set()
    qtbot.wait(300)
    assert win.stack.currentWidget() is win.intro_page and win._blocks == []


@pytest.mark.parametrize("kind", ["empty", "failed"])
def test_empty_or_failed_recapture_restores_previous_preview(qtbot, make, kind):
    gate = threading.Event()
    gate.set()
    engine = FakeEngine(TABLE, gate=gate)
    win = make(engine)
    recognized(qtbot, win, image(120, 40))
    first = win.preview.pixmap().size()
    if kind == "empty":
        engine.boxes = []
    else:
        engine.error = ValueError("x")
    win._on_captured(image(300, 200))
    assert win.preview.pixmap().size() != first
    # 이전 결과가 있으면 처음 화면이 아니라 그 결과 화면에 머문다
    qtbot.waitUntil(lambda: win.stack.currentWidget() is not win.busy_page, timeout=5000)
    assert win.stack.currentWidget() is win.result_page
    assert win.preview.pixmap().size() == first
    # 같은 상태에서 다시 고르고 읽는 중 취소해도 처음 결과의 미리보기로 돌아온다
    engine.boxes, engine.error = TABLE, None
    gate.clear()
    win._on_captured(image(300, 200))
    assert win.preview.pixmap().size() != first
    qtbot.mouseClick(win.cancel_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.result_page
    assert win.preview.pixmap().size() == first
    gate.set()


def test_empty_first_capture_leaves_no_preview(qtbot, make):
    win = make(FakeEngine([]))
    recognized(qtbot, win)
    assert win.preview.pixmap().isNull()


def test_unsure_highlight_marks_the_unsure_cell_not_an_earlier_substring(qtbot, make):
    win = make(FakeEngine(SUBSTRING))
    recognized(qtbot, win)
    assert not win.table_tab.isVisible() and win.text_tab.isChecked()
    assert win.text_edit.toPlainText() == "합계 42\n4"
    assert win.status_label.text() == "확인 필요 1곳"
    selections = win.text_edit.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.selectionStart() == len("합계 42\n")
    assert selections[0].cursor.selectedText() == "4"
    # 실제 불확실한 '4'만 '9'로 고치면 확인이 끝난다
    cursor = QTextCursor(win.text_edit.document())
    cursor.setPosition(len("합계 42\n"))
    cursor.setPosition(len("합계 42\n") + 1, QTextCursor.KeepAnchor)
    cursor.insertText("9")
    assert win.text_edit.toPlainText() == "합계 42\n9"
    assert win.status_label.text() == "확인 완료"
    assert win.text_edit.extraSelections() == []


def text_tab_with_unsure_token(qtbot, make):
    """글자 탭에 '5l'(확인 필요 1곳)이 표시된 창과 그 토큰의 문서 위치(시작, 끝)."""
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    assert win.status_label.text() == "확인 필요 1곳"
    marks = win.text_edit.extraSelections()  # 목록을 쥐고 있어야 안의 커서가 살아 있다
    assert len(marks) == 1 and marks[0].cursor.selectedText() == "5l"
    return win, marks[0].cursor.selectionStart(), marks[0].cursor.selectionEnd()


def place_text_cursor(win, position):
    cursor = win.text_edit.textCursor()
    cursor.setPosition(position)
    win.text_edit.setTextCursor(cursor)


def assert_unsure_mark_kept(win, start_text="5l"):
    marks = win.text_edit.extraSelections()
    assert len(marks) == 1 and marks[0].cursor.selectedText() == start_text
    assert win.status_label.text() == "확인 필요 1곳"


@pytest.mark.parametrize("typed", [" ", ".", ","])
def test_typing_right_after_unsure_token_keeps_mark_and_count(qtbot, make, typed):
    win, _, end = text_tab_with_unsure_token(qtbot, make)
    place_text_cursor(win, end)
    qtbot.keyClicks(win.text_edit, typed)
    assert typed in win.text_edit.toPlainText()
    assert_unsure_mark_kept(win)


def test_enter_right_after_unsure_token_keeps_mark_and_count(qtbot, make):
    win, _, end = text_tab_with_unsure_token(qtbot, make)
    before = win.text_edit.toPlainText()
    place_text_cursor(win, end)
    qtbot.keyClick(win.text_edit, Qt.Key_Return)
    assert win.text_edit.toPlainText() != before
    assert_unsure_mark_kept(win)
    # 프로그램으로 줄을 넣어도(insertText) 같다
    place_text_cursor(win, end)
    win.text_edit.textCursor().insertText("\n")
    assert_unsure_mark_kept(win)


def test_typing_before_or_at_start_of_unsure_token_keeps_mark(qtbot, make):
    win, start, _ = text_tab_with_unsure_token(qtbot, make)
    place_text_cursor(win, 0)
    qtbot.keyClicks(win.text_edit, "x")
    assert_unsure_mark_kept(win)
    place_text_cursor(win, start + 1)  # 앞 글자 하나가 늘어난 위치: 토큰의 처음
    qtbot.keyClicks(win.text_edit, "-")
    assert_unsure_mark_kept(win)


@pytest.mark.parametrize("offset", [0, 1])  # 0: 토큰 전체를 바꿈, 1: 'l'만 '1'로 바꿈
def test_real_correction_of_unsure_token_still_clears_mark(qtbot, make, offset):
    win, start, end = text_tab_with_unsure_token(qtbot, make)
    cursor = win.text_edit.textCursor()
    cursor.setPosition(start + offset)
    cursor.setPosition(end, QTextCursor.KeepAnchor)
    cursor.insertText("51"[offset:])
    assert "51" in win.text_edit.toPlainText()
    assert win.status_label.text() == "확인 완료"
    assert win.text_edit.extraSelections() == []


def test_close_while_model_is_loading_does_not_block_or_keep_engine(qtbot, make):
    gate, built = threading.Event(), threading.Event()

    def slow_factory():
        built.set()
        gate.wait(5)
        return FakeEngine(TABLE)

    win = make(engine_factory=slow_factory)
    win._on_captured(image())
    assert built.wait(2)
    started = time.monotonic()
    win.close()
    assert time.monotonic() - started < 1.0
    assert win._engine is None
    gate.set()
    qtbot.wait(300)
    assert win._engine is None
    assert win.stack.currentWidget() is win.intro_page and win._blocks == []


def test_padding_cell_of_narrower_table_is_not_editable_and_ignores_changes(qtbot, make):
    win = make(FakeEngine(MIXED_WIDTH))
    recognized(qtbot, win)
    assert win.table.columnCount() == 3
    item = win.table.item(3, 2)  # 2칸 표의 첫 행, 세 번째 칸
    assert item is not None and not item.flags() & Qt.ItemIsEditable
    item.setText("x")
    # 편집기를 거치지 않는 경로(모델에 직접 값 쓰기)도 오류 없이 무시된다
    win.table.model().setData(win.table.model().index(4, 2), "y")
    win.table.item(3, 0).setText("바뀜")
    assert "바뀜" in win.text_edit.toPlainText()


@pytest.mark.parametrize("how", ["missing", "broken"])
def test_engine_import_failure_is_reported_as_model_problem(qtbot, make, monkeypatch, how):
    if how == "missing":
        monkeypatch.setitem(sys.modules, "screen_text.engine", None)
        win = make()
    else:
        def broken():
            raise ImportError("onnxruntime")
        win = make(engine_factory=broken)
    recognized(qtbot, win)
    assert win.message_label.text() == "인식 모델을 확인하지 못했습니다."
    assert not win.capture_button.isEnabled()


def test_hide_owned_popups_stops_pending_capture(qtbot, make):
    win = make()
    win.start_capture()
    win.hide_owned_popups()
    qtbot.wait(350)
    assert not win._capture.is_active()


def test_screen_change_during_pending_capture_brings_window_back(qtbot, make):
    """영역 고르기를 기다리는 중 화면이 바뀌면 숨겨 둔 창을 취소처럼 다시 보인다(R17)."""
    win = make()
    win.start_capture()
    assert not win.isVisible()
    win.hide_owned_popups(restore=True)
    assert win.isVisible() and win.focusWidget() is win.capture_button
    qtbot.wait(350)
    assert not win._capture.is_active() and win.isVisible()


def test_screen_change_during_overlay_brings_window_back_with_result(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    text = win.text_edit.toPlainText()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    win.hide_owned_popups(restore=True)
    assert not win._capture.is_active()
    assert win.isVisible() and win.stack.currentWidget() is win.result_page
    assert win.focusWidget() is win.copy_button and win.text_edit.toPlainText() == text


def test_screen_change_does_not_show_window_hidden_by_lifecycle(qtbot, make):
    win = make()
    win.hide()  # 트레이·잠금 등으로 숨긴 창
    win.hide_owned_popups(restore=True)
    assert not win.isVisible()
    win.show()
    win.start_capture()
    win.setEnabled(False)  # 잠금
    win.hide_owned_popups(restore=True)
    assert not win.isVisible()


def test_lifecycle_hide_during_overlay_does_not_reopen_window(qtbot, make):
    win = make()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    win.cancel_work()
    win.hide_owned_popups()
    win.hide()
    qtbot.wait(100)
    assert not win.isVisible() and not win._capture.is_active()


def test_escape_on_overlay_brings_window_back(qtbot, make):
    win = make()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    qtbot.keyClick(win._capture.overlays[0], Qt.Key_Escape)
    qtbot.waitUntil(win.isVisible)
    assert win.stack.currentWidget() is win.intro_page


def test_blocked_capture_shows_message(qtbot, make):
    win = make(grab=lambda: shot("black"))
    win.start_capture()
    qtbot.waitUntil(win.isVisible, timeout=2000)
    assert win.message_label.isVisible()
    assert win.message_label.text() == "보안 프로그램이 화면 캡처를 막아 글자를 딸 수 없습니다."


def test_empty_result_shows_message(qtbot, make):
    win = make(FakeEngine([]))
    recognized(qtbot, win)
    assert win.stack.currentWidget() is win.intro_page
    assert win.message_label.text() == "고른 영역에서 글자를 찾지 못했습니다."


def test_model_error_disables_capture_button(qtbot, make):
    win = make(FakeEngine(error=ModelIntegrityError("x")))
    recognized(qtbot, win)
    assert win.message_label.text() == "인식 모델을 확인하지 못했습니다."
    assert not win.capture_button.isEnabled()


def test_engine_failure_is_reported_without_text_in_log(qtbot, make, caplog):
    win = make(FakeEngine(error=ValueError("비밀 글자")))
    recognized(qtbot, win)
    assert win.message_label.text() == "글자를 읽지 못했습니다. 다시 시도해 주세요."
    assert "비밀 글자" not in caplog.text


def test_close_releases_model_but_keeps_result(qtbot, make):
    win = make()
    recognized(qtbot, win)
    assert win._engine is not None
    win.close()
    assert win._engine is None and win._blocks
    win.show_near(QRect(100, 100, 64, 48), QGuiApplication.primaryScreen().availableGeometry())
    assert win.stack.currentWidget() is win.result_page


def test_shutdown_clears_results_preview_and_model(qtbot, make):
    win = make()
    recognized(qtbot, win)
    win.shutdown()
    assert win._blocks == [] and win._engine is None
    assert win.preview.pixmap().isNull()
    assert win.stack.currentWidget() is win.intro_page


def test_app_spec_and_registry():
    assert APP.app_id == "screen_text"
    assert APP.title == "화면 글자\n따기" and APP.accessible_name == "화면 글자 따기 실행"
    assert APP.icon_path == resource_root() / "screen_text" / "icon.svg"
    assert APP in optional_mini_apps.OPTIONAL_MINI_APPS


def test_registered_tile_opens_window_and_lock_hides_it(qtbot, app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    win = ui_main.MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    assert QTest.qWaitForWindowExposed(win)
    qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: win._mini_apps_popup is not None and win._mini_apps_popup.isVisible())
    popup = win._mini_apps_popup
    assert popup.card.height() == 390
    qtbot.mouseClick(popup.optional_cards["screen_text"], Qt.LeftButton)
    qtbot.waitUntil(lambda: "screen_text" in win._optional_windows)
    tool = win._optional_windows["screen_text"]
    assert isinstance(tool, ScreenTextWindow) and tool.isVisible()
    win._lock()
    assert not tool.isVisible() and not tool.isEnabled()
    win._unlock()
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


@pytest.mark.parametrize("scale", [1, 1.25, 1.5])
def test_icon_follows_mini_app_icon_rules(qapp, scale):
    path = resource_root() / "screen_text" / "icon.svg"
    with open(path, encoding="utf-8") as stream:
        text = stream.read()
    for banned in ("<text", "<image", "<filter", "<mask", "<style", "https://", "xlink:href"):
        assert banned not in text
    size = round(48 * scale)
    picture = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    picture.fill(Qt.transparent)
    painter = QPainter(picture)
    QSvgRenderer(str(path)).render(painter, QRectF(0, 0, size, size))
    painter.end()

    def near(color, expected):
        target = QColor(expected)
        return abs(color.red() - target.red()) + abs(color.green() - target.green()) + abs(color.blue() - target.blue()) <= 90

    assert picture.pixelColor(0, 0).alpha() == 0
    assert near(picture.pixelColor(round(size * .16), round(size * .10)), "#FF9A4D")
    assert near(picture.pixelColor(round(size * .84), round(size * .90)), "#D9480F")
    inner = range(round(size * .2), round(size * .8))
    white = sum(1 for x in inner for y in inner
                if picture.pixelColor(x, y).alpha() == 255 and min(picture.pixelColor(x, y).getRgb()[:3]) >= 235)
    assert white >= size


def test_screen_text_is_imported_only_from_registry_build_spec_and_own_tests():
    import subprocess
    pattern = re.compile(r"^\s*(from|import)\s+screen_text\b", re.M)
    # 추적 .py 전체(tests/test_security_scan_rules.py:13 방식). 폴더 위치가 바뀌어도 빈 통과가 되지 않는다.
    names = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode("utf-8").split("\0")
    registry = "src/optional_mini_apps.py"
    offenders, scanned, registry_hit = [], 0, False
    for relative in filter(None, names):
        with open(ROOT / relative, encoding="utf-8") as stream:
            found = bool(pattern.search(stream.read()))
        if relative == registry:
            registry_hit = found
            continue
        if relative.startswith(("tests/test_screen_text_", "screen_text/", "tools/screen_text_lab/")):
            continue
        scanned += 1
        if found:
            offenders.append(relative)
    assert scanned > 0
    assert registry_hit, "등록부가 검사 대상에 없거나 screen_text를 등록하지 않는다"
    assert offenders == []


EMPTY_TEXT = "고른 영역에서 글자를 찾지 못했습니다."
FAILED_TEXT = "글자를 읽지 못했습니다. 다시 시도해 주세요."
BLOCKED_TEXT = "보안 프로그램이 화면 캡처를 막아 글자를 딸 수 없습니다."
MODEL_TEXT = "인식 모델을 확인하지 못했습니다."


def edited_result_page(qtbot, make, engine):
    """첫 인식을 마치고 글자 탭의 글자를 고친 창과 그때의 미리보기 크기."""
    win = make(engine)
    recognized(qtbot, win, image(120, 40))
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    win.text_edit.setPlainText("고친 글자")
    assert win.stack.currentWidget() is win.result_page
    return win, win.preview.pixmap().size()


def assert_result_page_kept(win, preview_size, message):
    assert win.stack.currentWidget() is win.result_page
    assert win.isVisible()
    assert win.text_edit.toPlainText() == "고친 글자"
    assert win.preview.pixmap().size() == preview_size
    assert win.result_message_label.isVisible() and win.result_message_label.text() == message
    assert win.copy_button.isEnabled() and win.again_button.isEnabled()


def test_result_page_message_is_hidden_by_default(qtbot, make):
    win, _ = edited_result_page(qtbot, make, FakeEngine(TABLE))
    assert win.result_message_label.isHidden() and not win.result_message_label.isVisible()


@pytest.mark.parametrize("kind,message", [("empty", EMPTY_TEXT), ("failed", FAILED_TEXT)])
def test_empty_or_failed_recapture_keeps_edited_result_page_with_message(qtbot, make, kind, message):
    engine = FakeEngine(TABLE)
    win, first = edited_result_page(qtbot, make, engine)
    if kind == "empty":
        engine.boxes = []
    else:
        engine.error = ValueError("x")
    win._on_captured(image(300, 200))
    qtbot.waitUntil(lambda: win.stack.currentWidget() is not win.busy_page, timeout=5000)
    assert_result_page_kept(win, first, message)
    assert not win.message_label.isVisible()  # 처음 화면의 안내로 넘어가지 않는다


def test_blocked_recapture_keeps_edited_result_page_with_message(qtbot, make):
    win, first = edited_result_page(qtbot, make, FakeEngine(TABLE))
    win._capture._grab = lambda: shot("black")
    win.start_capture()
    qtbot.waitUntil(win.isVisible, timeout=2000)
    assert_result_page_kept(win, first, BLOCKED_TEXT)
    assert win.focusWidget() is win.copy_button


def test_model_error_on_recapture_keeps_result_page_and_disables_recapture(qtbot, make):
    engine = FakeEngine(TABLE)
    win, first = edited_result_page(qtbot, make, engine)
    engine.error = ModelIntegrityError("x")
    win._on_captured(image(300, 200))
    qtbot.waitUntil(lambda: win.stack.currentWidget() is not win.busy_page, timeout=5000)
    assert win.stack.currentWidget() is win.result_page
    assert win.text_edit.toPlainText() == "고친 글자" and win.preview.pixmap().size() == first
    assert win.result_message_label.isVisible() and win.result_message_label.text() == MODEL_TEXT
    assert not win.again_button.isEnabled() and not win.capture_button.isEnabled()
    assert win.copy_button.isEnabled()


def test_result_page_message_goes_away_on_next_pick_and_success(qtbot, make):
    engine = FakeEngine(TABLE)
    win, _ = edited_result_page(qtbot, make, engine)
    engine.boxes = []
    win._on_captured(image(300, 200))
    qtbot.waitUntil(lambda: win.result_message_label.isVisible(), timeout=5000)
    # 다시 고르기를 시작하면(오버레이 취소로 돌아와도) 지난 안내는 지운다
    win.start_capture()
    assert not win.result_message_label.isVisible()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    win._capture.cancel()
    qtbot.waitUntil(win.isVisible, timeout=2000)
    assert win.stack.currentWidget() is win.result_page and not win.result_message_label.isVisible()
    # 실패한 뒤 성공하면 안내 없이 새 결과가 나온다
    engine.boxes = []
    win._on_captured(image(300, 200))
    qtbot.waitUntil(lambda: win.result_message_label.isVisible(), timeout=5000)
    engine.boxes = TABLE
    win._on_captured(image(300, 200))
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page and not win.result_message_label.isVisible(),
                    timeout=5000)
    assert win.text_edit.toPlainText() != "고친 글자"


def test_shutdown_hides_result_page_message(qtbot, make):
    engine = FakeEngine(TABLE)
    win, _ = edited_result_page(qtbot, make, engine)
    engine.boxes = []
    win._on_captured(image(300, 200))
    qtbot.waitUntil(lambda: win.result_message_label.isVisible(), timeout=5000)
    win.shutdown()
    assert win.result_message_label.isHidden() and win.stack.currentWidget() is win.intro_page


def test_null_captured_image_is_treated_like_cancel(qtbot, make):
    engine = FakeEngine(TABLE)
    win = make(engine)
    win.capture_button.clearFocus()  # 시작 때 이미 [영역 고르기]에 있던 포커스가 아니라 _reappear가 준 것임을 확인한다
    assert win.focusWidget() is None
    win.hide()
    win._on_captured(QImage())
    assert win.isVisible() and win.stack.currentWidget() is win.intro_page
    assert win._cancel_event is None and win._generation == 0 and win.focusWidget() is win.capture_button
    qtbot.wait(150)
    assert engine.calls == 0 and win.stack.currentWidget() is win.intro_page


def test_null_captured_image_leaves_existing_result_page_untouched(qtbot, make):
    engine = FakeEngine(TABLE)
    win, first = edited_result_page(qtbot, make, engine)
    win.copy_button.clearFocus()
    assert win.focusWidget() is not win.copy_button  # 포커스는 _reappear가 [복사]에 준 것이어야 한다
    win.hide()
    calls = engine.calls
    win._on_captured(QImage())
    assert win.isVisible() and win.stack.currentWidget() is win.result_page
    assert win.text_edit.toPlainText() == "고친 글자" and win.preview.pixmap().size() == first
    assert win._cancel_event is None and win.focusWidget() is win.copy_button
    qtbot.wait(150)
    assert engine.calls == calls


TIPS_TEXT = "· 필요한 영역만 고르면 더 빠르고 정확합니다\n· 노란 칸은 인식이 불확실한 곳이니 꼭 확인하세요"


def shown_children(page):
    return [child for child in page.findChildren(QWidget, options=Qt.FindDirectChildrenOnly) if child.isVisible()]


def assert_no_overlap(page):
    rects = {child: child.geometry() for child in shown_children(page)}
    assert rects and all(page.rect().contains(rect) for rect in rects.values())
    items = list(rects.items())
    for index, (first, a) in enumerate(items):
        for second, b in items[index + 1:]:
            assert not a.intersects(b), (first, second)


def test_intro_page_shows_usage_guide_and_tips(qtbot, make):
    win = make()
    assert win.stack.currentWidget() is win.intro_page
    guide = win.intro_guide
    assert guide.isVisible() and guide.is_running()
    assert win.tips_label.text() == TIPS_TEXT and win.tips_label.wordWrap()
    assert win.tips_label.property("muted") is True
    assert win.tips_label.isVisible()
    # 순서: 설명 → 영역 고르기 → 인터넷 없음 안내 → 애니메이션 → 팁. 서로 겹치지 않고 페이지 안에 있다
    assert win.offline_label.geometry().bottom() < guide.geometry().top()
    assert win.tips_label.geometry().top() > guide.geometry().bottom()
    assert guide.height() >= guide.minimumSizeHint().height() and guide.height() >= 160
    assert_no_overlap(win.intro_page)
    win.hide()
    assert not guide.is_running()
    win.show()
    qtbot.waitUntil(guide.is_running, timeout=2000)


def test_intro_guide_stops_when_page_changes_and_resumes(qtbot, make):
    win = make(FakeEngine(TABLE))
    assert win.intro_guide.is_running()
    recognized(qtbot, win)
    assert win.stack.currentWidget() is win.result_page
    assert not win.intro_guide.is_running()
    win.shutdown()
    assert win.stack.currentWidget() is win.intro_page
    assert win.intro_guide.is_running()


def test_window_still_fits_content_size_on_every_page(qtbot, make):
    win = make(FakeEngine(TABLE))
    limit_w, limit_h = CONTENT_WIDTH + 2 * SHADOW_MARGIN, CONTENT_HEIGHT + 2 * SHADOW_MARGIN
    assert win.width() <= limit_w and win.height() <= limit_h
    recognized(qtbot, win)
    win._show_guide()
    for page in (win.intro_page, win.result_page, win.guide_page):
        win.stack.setCurrentWidget(page)
        assert win.minimumSizeHint().width() <= win.width(), page
        assert win.minimumSizeHint().height() <= win.height(), page
    win.stack.setCurrentWidget(win.guide_page)
    assert_no_overlap(win.guide_page)


@pytest.mark.parametrize("height", [520, 440, 410])
def test_small_screen_compresses_the_guide_without_clipping_or_overlap(qtbot, height):
    win = ScreenTextWindow(None, engine_factory=lambda: FakeEngine(TABLE), grab=shot)
    qtbot.addWidget(win)
    win.show_near(QRect(10, 10, 64, 48), QRect(0, 0, 700, height))
    qtbot.waitExposed(win)
    assert win.height() <= height
    assert win.minimumSizeHint().height() <= win.height()
    for guide, page, last in ((win.intro_guide, win.intro_page, win.tips_label), (win.help_guide, win.guide_page, win.back_button)):
        win.stack.setCurrentWidget(page)
        qtbot.waitUntil(lambda: guide.isVisible(), timeout=2000)
        assert guide.height() >= guide.minimumSizeHint().height() >= 160 - 8
        assert guide.rect().adjusted(0, 0, 1, 1).contains(guide.scene_rect().toAlignedRect())
        assert last.geometry().bottom() <= page.rect().bottom()
        assert_no_overlap(page)


def test_result_page_has_help_button_right_of_again_button(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    assert win.help_button.text() == "사용법"
    assert win.help_button.toolTip() == "사용 방법 보기"
    assert win.help_button.accessibleName() == "화면 글자 따기 사용법 보기"
    again, help_rect, copy = win.again_button.geometry(), win.help_button.geometry(), win.copy_button.geometry()
    assert help_rect.left() > again.right() and abs(help_rect.center().y() - again.center().y()) <= 2
    assert copy.right() < again.left()
    assert help_rect.right() <= win.result_page.rect().right()


def test_help_opens_guide_page_and_back_restores_result_untouched(qtbot, make):
    win, preview_size = edited_result_page(qtbot, make, FakeEngine(TABLE))
    status, tab, status_done = win.status_label.text(), win._tab, win.status_label.property("done")
    blocks, spans, rows = win._blocks, list(win._text_spans), list(win._table_rows)
    qtbot.mouseClick(win.help_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.guide_page
    assert win.help_guide.isVisible() and win.help_guide.is_running()
    assert win.back_button.text() == "돌아가기" and win.focusWidget() is win.back_button
    assert win.guide_title_label.text() == "사용 방법" and win.guide_tips_label.text() == TIPS_TEXT
    assert_no_overlap(win.guide_page)
    qtbot.mouseClick(win.back_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.result_page
    assert not win.help_guide.is_running()
    assert win.text_edit.toPlainText() == "고친 글자"
    assert win._tab == tab and win.text_tab.isChecked() and win.result_stack.currentWidget() is win.text_edit
    assert win.status_label.text() == status and win.status_label.property("done") == status_done
    assert win.preview.pixmap().size() == preview_size
    assert win._blocks is blocks and win._text_spans == spans and win._table_rows == rows
    assert win.copy_button.isEnabled() and win.again_button.isEnabled() and win.help_button.isEnabled()


def test_help_round_trip_keeps_table_edit_and_table_tab(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    assert win._tab == "table"
    win.table.item(1, 1).setText("43")
    status, texts = win.status_label.text(), win.text_edit.toPlainText()
    qtbot.mouseClick(win.help_button, Qt.LeftButton)
    qtbot.mouseClick(win.back_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.result_page and win._tab == "table" and win.table_tab.isChecked()
    assert win.table.item(1, 1).text() == "43" and win.status_label.text() == status
    assert win.text_edit.toPlainText() == texts


def test_back_without_results_falls_back_to_intro(qtbot, make):
    win = make()
    win._show_guide()
    assert win.stack.currentWidget() is win.guide_page and win.help_guide.is_running()
    win._close_guide()
    assert win.stack.currentWidget() is win.intro_page and not win.help_guide.is_running()


def test_enter_on_guide_buttons_clicks_them(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    QTest.keyClick(win.help_button, Qt.Key_Return)
    assert win.stack.currentWidget() is win.guide_page
    QTest.keyClick(win.back_button, Qt.Key_Enter)
    assert win.stack.currentWidget() is win.result_page


def test_escape_on_guide_page_still_closes_the_window(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    win._show_guide()
    QTest.keyClick(win.back_button, Qt.Key_Escape)
    assert not win.isVisible() and not win.help_guide.is_running()
    assert win.stack.currentWidget() is win.guide_page  # 닫아도 결과·화면은 다음 열기까지 유지


def test_reopening_on_guide_page_focuses_back_button(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    win._show_guide()
    win.close()
    assert not win.help_guide.is_running()
    win.show_near(QRect(100, 100, 64, 48), QGuiApplication.primaryScreen().availableGeometry())
    qtbot.waitExposed(win)
    assert win.stack.currentWidget() is win.guide_page and win.focusWidget() is win.back_button
    assert win.help_guide.is_running()


def test_lifecycle_calls_work_on_guide_page(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    win._show_guide()
    win.hide_owned_popups()
    win.cancel_work()
    win.fit_to_screen()
    assert win.stack.currentWidget() is win.guide_page and win.help_guide.is_running()
    win.shutdown()
    assert win.stack.currentWidget() is win.intro_page
    assert not win.help_guide.is_running() and win.intro_guide.is_running()
    assert win._blocks == [] and win.text_edit.toPlainText() == ""


def test_model_error_keeps_help_available(qtbot, make):
    win = make(FakeEngine(TABLE))
    recognized(qtbot, win)
    win._model_broken = True
    win._sync_capture_buttons()
    assert not win.again_button.isEnabled() and win.help_button.isEnabled()
    qtbot.mouseClick(win.help_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.guide_page
    qtbot.mouseClick(win.back_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.result_page and not win.again_button.isEnabled()


# ── 고리 모양 글머리 기호: 기호 한 글자만 확인 필요 ──
RING_LINES = [TextBox(0, 0, 200, 16, "ㅇ 연간 배출량", 0.99, 1), TextBox(0, 30, 200, 16, "본문 줄", 0.99)]
RING_TABLE = [
    TextBox(10, 0, 40, 16, "구분", 0.99), TextBox(200, 0, 40, 16, "값", 0.99),
    TextBox(10, 24, 90, 16, "ㅇ 가나", 0.99, 1), TextBox(200, 24, 30, 16, "12", 0.99),
    TextBox(10, 48, 40, 16, "다라", 0.99), TextBox(200, 48, 30, 16, "34", 0.99),
]


def test_ring_symbol_is_the_only_text_marked_and_counted(qtbot, make):
    win = make(FakeEngine(RING_LINES))
    recognized(qtbot, win)
    assert not win.table_tab.isVisible() and win.text_tab.isChecked()
    assert win.text_edit.toPlainText() == "ㅇ 연간 배출량\n본문 줄"
    assert win.status_label.text() == "확인 필요 1곳"
    selections = win.text_edit.extraSelections()
    assert [s.cursor.selectedText() for s in selections] == ["ㅇ"]          # 줄 전체가 아니라 기호 한 글자
    assert selections[0].cursor.selectionStart() == 0


def test_correcting_the_ring_symbol_completes_the_check(qtbot, make):
    win = make(FakeEngine(RING_LINES))
    recognized(qtbot, win)
    cursor = QTextCursor(win.text_edit.document())
    cursor.setPosition(0)
    cursor.setPosition(1, QTextCursor.KeepAnchor)
    cursor.insertText("◦")                                                  # 사용자가 실제 기호로 고쳤다
    assert win.text_edit.toPlainText() == "◦ 연간 배출량\n본문 줄"
    assert win.status_label.text() == "확인 완료"                            # '불확실한 곳 없음'이 아니다
    assert win.text_edit.extraSelections() == []


def test_table_tab_marks_the_cell_with_the_ring_symbol(qtbot, make):
    win = make(FakeEngine(RING_TABLE))
    recognized(qtbot, win)
    assert win.table_tab.isVisible() and win.table_tab.isChecked()
    assert win.status_label.text() == "확인 필요 1곳"
    flagged = win.table.item(1, 0)
    assert flagged.text() == "ㅇ 가나" and flagged.background().color() == QColor("#FFE58A")
    assert win.table.item(2, 0).background().color() != QColor("#FFE58A")


def test_editing_the_marked_table_cell_clears_the_mark_and_refreshes_text(qtbot, make):
    win = make(FakeEngine(RING_TABLE))
    recognized(qtbot, win)
    win.table.item(1, 0).setText("◦ 가나")
    assert win.status_label.text() == "확인 완료"
    assert win.table.item(1, 0).background().color() != QColor("#FFE58A")
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    assert "◦ 가나" in win.text_edit.toPlainText()
    assert win.text_edit.extraSelections() == [] and win.status_label.text() == "확인 완료"


class GridEngine(FakeEngine):
    """실제 엔진처럼 표 격자가 붙은 결과를 돌려준다."""

    def __init__(self, boxes, grids):
        super().__init__(boxes)
        self.grids = grids

    def recognize(self, rgb, cancelled):
        return RecognizedBoxes(super().recognize(rgb, cancelled), self.grids)


MERGED_GRID = Grid(3, 3, (GridCell(0, 0, 2, 1, 0, 0, 100, 60), GridCell(0, 1, 1, 2, 100, 0, 300, 30), GridCell(1, 1, 1, 1, 100, 30, 200, 60),
                          GridCell(1, 2, 1, 1, 200, 30, 300, 60), GridCell(2, 0, 1, 1, 0, 60, 100, 90), GridCell(2, 1, 1, 1, 100, 60, 200, 90),
                          GridCell(2, 2, 1, 1, 200, 60, 300, 90)), 0, 0, 300, 90)
MERGED_BOXES = [TextBox(10, 20, 60, 16, "구분", 0.99), TextBox(120, 5, 100, 16, "실적", 0.99), TextBox(110, 35, 60, 16, "2024", 0.99),
                TextBox(210, 35, 60, 16, "2025", 0.99), TextBox(10, 65, 60, 16, "대전", 0.99), TextBox(110, 65, 60, 16, "42", 0.99), TextBox(210, 65, 60, 16, "51", 0.99)]


def test_merged_cells_from_table_lines_span_in_the_table_tab(qtbot, make):
    win = make(GridEngine(MERGED_BOXES, [MERGED_GRID]))
    recognized(qtbot, win)
    assert win.table_tab.isVisible() and win.table_tab.isChecked()
    assert (win.table.rowCount(), win.table.columnCount()) == (3, 3)
    assert (win.table.rowSpan(0, 0), win.table.columnSpan(0, 1)) == (2, 2)
    assert win.table.item(0, 0).text() == "구분" and win.table.item(0, 1).text() == "실적"
    assert win.table.rowSpan(2, 0) == 1                                     # 뒤에 넣은 행이 병합 칸을 늘리지 않는다
    assert not win.table.item(1, 0).flags() & Qt.ItemIsEditable             # 병합 칸에 덮인 자리


def test_copy_keeps_merged_cells_for_pasting_into_a_document(qtbot, make):
    win = make(GridEngine(MERGED_BOXES, [MERGED_GRID]))
    recognized(qtbot, win)
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    html = QGuiApplication.clipboard().mimeData().html()
    assert 'rowspan="2"' in html and 'colspan="2"' in html


def test_repeat_recognition_clears_old_merged_cells(qtbot, make):
    engines = [GridEngine(MERGED_BOXES, [MERGED_GRID]), FakeEngine(TABLE)]
    win = make(engine_factory=lambda: engines[0])
    recognized(qtbot, win)
    assert win.table.rowSpan(0, 0) == 2
    win._engine = engines[1]
    recognized(qtbot, win)
    assert win.table.rowSpan(0, 0) == 1


CHAR_MARKED = [TextBox(0, 0, 200, 16, "환경 점겁 결과", 0.95, 0, (4,)), TextBox(0, 30, 200, 16, "다음 줄", 0.99)]


def test_low_confidence_character_alone_is_marked(qtbot, make):
    win = make(FakeEngine(CHAR_MARKED))
    recognized(qtbot, win)
    assert win.text_edit.toPlainText() == "환경 점겁 결과\n다음 줄"
    selections = win.text_edit.extraSelections()
    assert [item.cursor.selectedText() for item in selections] == ["겁"]
    assert win.status_label.text() == "확인 필요 1곳"


def test_fixing_the_marked_character_completes_the_check(qtbot, make):
    win = make(FakeEngine(CHAR_MARKED))
    recognized(qtbot, win)
    cursor = QTextCursor(win.text_edit.document())
    cursor.setPosition(4)
    cursor.setPosition(5, QTextCursor.KeepAnchor)
    cursor.insertText("검")
    assert win.text_edit.extraSelections() == [] and win.status_label.text() == "확인 완료"
