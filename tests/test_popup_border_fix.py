"""popup_border_fix 테스트 (pytest-qt).

Win11 DWM 창 테두리를 RoundMenu 팝업에서 제거하는 우회의 동작 검증.
DWM 속성의 시각 결과 자체는 화면 캡처 없이는 검증 불가하므로,
API 호출 성공(S_OK)과 필터 배선(Show 시 적용, 이벤트 비소비)을 검증한다.
"""
import sys

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import RoundMenu, Action, FluentIcon as FIF

from popup_border_fix import (
    remove_dwm_border,
    install_popup_border_fix,
    _PopupBorderFilter,
)

_IS_WIN11 = sys.getwindowsversion().build >= 22000


@pytest.mark.skipif(not _IS_WIN11, reason="DWMWA_BORDER_COLOR는 Win11 전용")
def test_remove_dwm_border_succeeds_on_shown_window(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    assert remove_dwm_border(w) is True  # S_OK


def test_remove_dwm_border_none_widget_is_safe():
    class _NoWinId:
        def winId(self):
            raise RuntimeError("no native window")

    assert remove_dwm_border(_NoWinId()) is False  # 예외 없이 False


def test_install_returns_filter_and_attaches_to_app(qtbot):
    app = QApplication.instance()
    filt = install_popup_border_fix(app)
    try:
        assert isinstance(filt, _PopupBorderFilter)
        assert filt.parent() is app
    finally:
        if filt is not None:
            app.removeEventFilter(filt)
            filt.deleteLater()


def test_filter_applies_on_menu_show_and_does_not_consume(qtbot, monkeypatch):
    app = QApplication.instance()
    filt = install_popup_border_fix(app)
    assert filt is not None

    applied = []
    monkeypatch.setattr(
        "popup_border_fix.remove_dwm_border", lambda w: applied.append(w) or True
    )
    try:
        menu = RoundMenu(parent=None)
        menu.addAction(Action(FIF.MENU, "테스트", menu))
        menu.show()
        qtbot.waitUntil(lambda: len(applied) >= 1, timeout=2000)
        assert applied[0] is menu  # RoundMenu 자신에 적용됨
        assert menu.isVisible()  # 이벤트를 소비하지 않아 정상 표시
        menu.hide()
    finally:
        app.removeEventFilter(filt)
        filt.deleteLater()


def test_filter_ignores_non_menu_widgets(qtbot, monkeypatch):
    app = QApplication.instance()
    filt = install_popup_border_fix(app)
    assert filt is not None

    applied = []
    monkeypatch.setattr(
        "popup_border_fix.remove_dwm_border", lambda w: applied.append(w) or True
    )
    try:
        w = QWidget()
        qtbot.addWidget(w)
        w.show()
        qtbot.waitExposed(w)
        assert applied == []  # 일반 위젯에는 적용 안 함
    finally:
        app.removeEventFilter(filt)
        filt.deleteLater()
