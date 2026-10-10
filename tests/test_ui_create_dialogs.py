"""디자인 점검 17번: D-Day 만들기·집중 모드 추가 창(창 안 제목, 달력, D-day 미리보기, 여백)."""
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QDate, QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QCalendarWidget, QWidget

from ui_dday import DDayCreateDialog
from ui_focus import FocusCreateDialog


def _dialog(qtbot, **kwargs):
    dlg = DDayCreateDialog(**kwargs)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


def _set_date(dlg, value):
    dlg.year_input.setText(str(value.year))
    dlg.month_input.setText(str(value.month))
    dlg.day_input.setText(str(value.day))
    QApplication.processEvents()


def test_title_inside_dialog(qtbot):
    assert _dialog(qtbot).title_label.text() == "D-Day 만들기"
    assert _dialog(qtbot, name="마감", target_date="2026-12-31").title_label.text() == "D-Day 편집"


def test_preview_shows_dday_and_weekday(qtbot):
    dlg = _dialog(qtbot)
    target = date.today() + timedelta(days=13)
    _set_date(dlg, target)
    weekday = "월화수목금토일"[target.weekday()]
    assert dlg.preview_label.text() == f"D-13 · {target.month}월 {target.day}일({weekday})"
    _set_date(dlg, date.today())
    assert dlg.preview_label.text().startswith("D-Day")
    dlg.month_input.setText("13")
    assert dlg.preview_label.text() == "날짜를 확인하세요"


def test_calendar_button_fills_date_fields_korean_sunday_first(qtbot):
    dlg = _dialog(qtbot)
    dlg.calendar_button.click()
    popup = dlg.calendar_popup
    assert isinstance(popup, QCalendarWidget) and popup.isVisible()
    assert popup.firstDayOfWeek() == Qt.Sunday
    assert popup.locale().language() == popup.locale().Language.Korean
    popup.clicked.emit(QDate(2027, 3, 5))
    QApplication.processEvents()
    assert (dlg.year_input.text(), dlg.month_input.text(), dlg.day_input.text()) == ("2027", "3", "5")
    assert not popup.isVisible()


@pytest.mark.parametrize("make", [lambda: DDayCreateDialog(), lambda: FocusCreateDialog()])
def test_all_controls_fit_inside_dialog(qtbot, make):
    dlg = make()
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    for child in dlg.findChildren(QWidget):
        if child.isVisible() and child.parent() is dlg:
            assert dlg.rect().contains(QRect(child.mapTo(dlg, QPoint()), child.size())), child


def test_focus_dialog_has_same_title_frame(qtbot):
    dlg = FocusCreateDialog()
    qtbot.addWidget(dlg)
    assert dlg.title_label.text() == "집중 모드 추가"
