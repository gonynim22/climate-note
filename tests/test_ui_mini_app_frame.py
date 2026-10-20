"""미니앱 공용 창 틀(디자인 점검 5번 B안): 다섯 창이 같은 어두운 제목줄을 쓰는지 검사."""
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QStyle, QStyleOptionButton

import database as db
import ui_document_converter
from hwp_conversion import ConversionEnvironment
from ui_mini_app_frame import FRAME_DARK, FRAME_SURFACE, TITLE_BAR_HEIGHT, MiniAppCheckBox, MiniAppTitleBar

WINDOWS = {
    "unit": ("ui_unit_converter", "UnitConverterWindow", "단위 환산기", True),
    "date": ("ui_date_time_calculator", "DateTimeCalculatorWindow", "날짜·시간 계산기", True),
    "money": ("ui_money_notation", "MoneyNotationWindow", "금액·숫자 표기 도우미", True),
    "doc": ("ui_document_converter", "DocumentConverterWindow", "파일 변환", False),
    "text": ("screen_text.window", "ScreenTextWindow", "화면 글자 따기", False),
}


@pytest.fixture(autouse=True)
def isolated(app_dir, qapp, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(ui_document_converter, "detect_environment",
                        lambda: ConversionEnvironment(Path("hwp.exe"), Path("HwpxConverter.exe")))


def _open(qtbot, key):
    module_name, class_name, _, _ = WINDOWS[key]
    module = __import__(module_name, fromlist=[class_name])
    win = getattr(module, class_name)()
    qtbot.addWidget(win)
    available = QApplication.primaryScreen().availableGeometry()
    if hasattr(win, "show_near"):
        win.show_near(QRect(available.left() + 80, available.top() + 80, 64, 48), available)
    else:  # 단위 환산기는 메인이 위치를 정한 뒤 fit_to_screen → show로 연다(ui_main._open_unit_converter).
        win.move(available.left() + 156, available.top() + 80)
        win.fit_to_screen()
        win.show()
    assert QTest.qWaitForWindowExposed(win)
    QApplication.processEvents()
    return win


def _pixel(win, widget, point):
    image = win.surface.grab().toImage()
    ratio = image.devicePixelRatio()
    at = widget.mapTo(win.surface, point)
    return image.pixelColor(int(at.x() * ratio), int(at.y() * ratio)).name()


@pytest.mark.parametrize("key", WINDOWS)
def test_title_bar_spans_top_of_surface(qtbot, key):
    _, _, title, _ = WINDOWS[key]
    win = _open(qtbot, key)
    bar = win.title_bar
    assert isinstance(bar, MiniAppTitleBar)
    assert bar.mapTo(win.surface, QPoint()) == QPoint(0, 0)
    assert bar.width() == win.surface.width()
    assert bar.height() == TITLE_BAR_HEIGHT
    assert bar.title_label.text() == title
    assert not bar.icon_label.pixmap().isNull()
    assert bar.close_button.toolTip() == "닫기 (Esc)"
    assert bar.close_button.accessibleName() == f"{title} 닫기"
    assert win.close_button is bar.close_button
    # 제목 글자 위쪽 빈 곳은 어두운 바탕이다.
    assert _pixel(win, bar, QPoint(bar.width() // 2, 4)) == FRAME_DARK.lower()


@pytest.mark.parametrize("key", WINDOWS)
def test_menu_is_dark_and_body_is_light(qtbot, key):
    _, _, _, has_menu = WINDOWS[key]
    win = _open(qtbot, key)
    if has_menu:
        rail = win.category_rail if key == "unit" else win.rail
        assert _pixel(win, rail, QPoint(2, rail.height() - 30)) == FRAME_DARK.lower()
    else:
        surface = win.surface
        assert _pixel(win, surface, QPoint(surface.width() - 8, surface.height() // 2)) == FRAME_SURFACE.lower()


@pytest.mark.parametrize("key", WINDOWS)
def test_title_bar_drag_moves_window_and_close_by_enter(qtbot, key):
    win = _open(qtbot, key)
    bar = win.title_bar
    start = win.pos()
    press_at = QPointF(bar.width() / 2, bar.height() / 2)
    global_at = QPointF(bar.mapToGlobal(press_at.toPoint()))
    for kind, delta, buttons in ((QEvent.MouseButtonPress, QPointF(0, 0), Qt.LeftButton),
                                 (QEvent.MouseMove, QPointF(-30, 20), Qt.LeftButton),
                                 (QEvent.MouseButtonRelease, QPointF(-30, 20), Qt.NoButton)):
        event = QMouseEvent(kind, press_at + delta, global_at + delta, Qt.LeftButton, buttons, Qt.NoModifier)
        QApplication.sendEvent(bar, event)
    QApplication.processEvents()
    available = win.screen().availableGeometry()
    # 놓으면 fit_to_screen이 창을 화면 안으로 되돌린다(150% 같은 낮은 논리 화면에서는 아래로 못 내려간다).
    expected_y = min(start.y() + 20, available.bottom() + 1 - win.height())
    assert win.pos() == QPoint(start.x() - 30, expected_y)
    assert available.contains(win.frameGeometry())

    bar.close_button.setFocus()
    QTest.keyClick(bar.close_button, Qt.Key_Return)
    QApplication.processEvents()
    assert not win.isVisible()


def test_document_converter_actions_stay_blue(qtbot):
    # v4.4 D안의 그림·화살표는 보라, 주 동작·선택은 공통 파랑이다.
    win = _open(qtbot, "doc")
    assert "#2563EB" in win.styleSheet()
    assert win.start_button.property("primary") is True


@pytest.mark.parametrize("key", ["date"])
def test_checkboxes_draw_white_check_on_app_blue(qtbot, key):
    """디자인 점검 8번: Windows 기본 체크(파랑 위 어두운 체크) 대신 앱 파랑 상자 + 흰 체크."""
    win = _open(qtbot, key)
    boxes = [box for box in win.findChildren(QCheckBox) if box.isVisible()]
    assert boxes and all(isinstance(box, MiniAppCheckBox) for box in boxes)
    box = boxes[0]
    for checked in (False, True):
        box.setChecked(checked)
        QApplication.processEvents()
        option = QStyleOptionButton()
        box.initStyleOption(option)
        rect = box.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, box)
        assert rect.width() == 18 and rect.height() == 18  # 16px 안쪽 + 1px 테두리(Fluent 체크와 같은 크기)
        image = box.grab().toImage()
        ratio = image.devicePixelRatio()

        def pixel(fx, fy):
            return image.pixelColor(int((rect.x() + rect.width() * fx) * ratio),
                                    int((rect.y() + rect.height() * fy) * ratio))

        if checked:
            assert pixel(0.15, 0.85).name() == "#2563eb"  # 체크 선이 없는 상자 안쪽
            assert pixel(0.6, 0.5).lightness() > 200      # 흰 체크 선
        else:
            assert pixel(0.5, 0.5).name() == "#ffffff"
