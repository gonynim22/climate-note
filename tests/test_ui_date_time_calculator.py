"""합성 Qt 창에서 날짜·시간 계산기의 입력·결과·기록·배율을 검증한다."""
from copy import deepcopy
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QLineEdit, QPushButton, QStyle,
    QStyleOptionButton, QWidget,
)
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
import database as db
from ui_date_time_calculator import DateTimeCalculatorWindow, MODES


@pytest.fixture(autouse=True)
def isolated_ui(app_dir, qapp):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def calculator(qtbot):
    win = DateTimeCalculatorWindow()
    qtbot.addWidget(win)
    win.show_near(QRect(10, 10, 64, 48), QApplication.primaryScreen().availableGeometry())
    assert QTest.qWaitForWindowExposed(win)
    assert QTest.qWaitForWindowActive(win)
    return win


def click(qtbot, win, widget):
    if win.body.isAncestorOf(widget):
        win.body_scroll.ensureWidgetVisible(widget, 8, 12)
    if isinstance(widget, QCheckBox):
        # 늘어난 행의 빈 여백은 QCheckBox 클릭 영역이 아니므로 표시된 박스를 누른다.
        option = QStyleOptionButton()
        widget.initStyleOption(option)
        indicator = widget.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, widget)
        qtbot.mouseClick(widget, Qt.LeftButton, pos=indicator.center())
    else:
        qtbot.mouseClick(widget, Qt.LeftButton)


def type_text(qtbot, win, widget, text):
    click(qtbot, win, widget)
    qtbot.waitUntil(widget.hasFocus)
    qtbot.keyClick(widget, Qt.Key_A, Qt.ControlModifier)
    qtbot.keyClicks(widget, text)


def choose(combo, value):
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def capture(win, name):
    QApplication.processEvents()
    appdata = os.environ.get('CLIMATENOTE_TEST_APPDATA')
    if appdata:
        target = Path(appdata).parent / f'date-time-{name}.png'
        assert win.grab().save(str(target))


def test_time_difference_uses_actual_input_and_preserves_seconds(qtbot):
    win = calculator(qtbot)
    fields = win.fields['difference']
    assert win.result_label.text() == '419분'
    assert win.result_detail.text() == '6시간 59분'
    assert '25,140초' in win.result_note.text()
    type_text(qtbot, win, fields['end_time'], '18:59:30')
    assert win.result_label.text() == '419분 30초'
    assert win._seconds == 25170
    type_text(qtbot, win, fields['break_minutes'], '30')
    assert win.result_label.text() == '389분 30초'
    assert win.result_detail.text() == '6시간 29분 30초'
    qtbot.keyClick(fields['break_minutes'], Qt.Key_Return)
    assert len(win.history) == 1
    assert win.history[0]['values']['end_time'] == '18:59:30'
    assert win.history[0]['values']['break_minutes'] == '30'


@pytest.mark.parametrize('policy,expected', [
    ('exact', '419.5'), ('floor', '419'), ('nearest', '420'), ('ceil', '420'),
])
def test_explicit_minute_copy_policy_never_changes_original_seconds(qtbot, policy, expected):
    win = calculator(qtbot)
    win.fields['difference']['end_time'].setText('18:59:30')
    choose(win.copy_mode, policy)
    click(qtbot, win, win.copy_button)
    assert QApplication.clipboard().text() == expected
    assert win.result_label.text() == '419분 30초'
    assert win._seconds == 25170
    click(qtbot, win, win.save_button)
    assert win.history[0]['values']['end_time'] == '18:59:30'


def test_midnight_is_explicit_and_break_cannot_exceed_interval(qtbot):
    win = calculator(qtbot)
    f = win.fields['difference']
    f['start_time'].setText('23:30')
    f['end_time'].setText('00:15:30')
    assert win.result_label.text() == '—'
    assert not win.copy_button.isEnabled()
    click(qtbot, win, f['next_day'])
    assert win.result_label.text() == '45분 30초'
    f['break_minutes'].setText('46')
    assert win.error_label.isVisible()
    assert win.result_label.text() == '—'
    assert win._seconds is None
    assert win._copy_text is None
    f['break_minutes'].setText('45')
    assert win.result_label.text() == '0분 30초'


def test_date_only_and_dated_time_modes_keep_separate_meanings(qtbot):
    win = calculator(qtbot)
    f = win.fields['difference']
    click(qtbot, win, f['dates'])
    f['start_date'].setText('2026-01-31')
    f['end_date'].setText('2026-02-28')
    f['start_time'].setText('12:00:00')
    f['end_time'].setText('12:00:30')
    assert win._seconds == 28 * 86400 + 30
    assert '1개월 30초' in win.result_note.text()
    assert not f['next_day'].isEnabled()
    click(qtbot, win, f['date_only'])
    assert win.result_label.text() == '28일'
    assert win.result_detail.text() == '1개월'
    assert not f['start_time'].isVisible()
    click(qtbot, win, win.date_swap_button)
    assert win.result_label.text() == '-28일'
    assert '1개월' in win.result_detail.text()
    click(qtbot, win, f['date_only'])
    assert f['start_time'].text() == '12:00:30'
    assert f['end_time'].text() == '12:00:00'
    assert win._seconds == -(28 * 86400 + 30)


def test_calendar_arithmetic_combines_all_six_units_and_reports_month_end(qtbot):
    win = calculator(qtbot)
    click(qtbot, win, win.mode_buttons['calendar'])
    f = win.fields['calendar']
    type_text(qtbot, win, f['base_date'], '2025-01-31')
    for key in ('years', 'months', 'days', 'hours', 'minutes', 'seconds'):
        f[key].setText('1')
    assert win.result_label.text() == '2026-03-01'
    assert win.result_detail.text() == '13:01:01'
    assert '월말' in win.result_note.text()
    assert not win.copy_mode.isEnabled()
    click(qtbot, win, win.copy_button)
    assert '2026-03-01' in QApplication.clipboard().text()
    f['base_date'].setText('2026-03-31')
    for key in ('years', 'days', 'hours', 'minutes', 'seconds'):
        f[key].setText('0')
    choose(f['operation'], -1)
    assert win.result_label.text() == '2026-02-28'
    assert win.result_detail.text() == '12:00:00'


def test_workday_inclusion_holiday_coverage_and_weekday_selection(qtbot):
    win = calculator(qtbot)
    click(qtbot, win, win.mode_buttons['workdays'])
    f = win.fields['workdays']
    type_text(qtbot, win, f['start_date'], '2026-01-01')
    type_text(qtbot, win, f['end_date'], '2026-01-04')
    assert win.result_label.text() == '1일'
    assert '4일 중 3일 제외' in win.result_detail.text()
    click(qtbot, win, win.workdays_swap_button)
    assert win.result_label.text() == '—'
    click(qtbot, win, win.workdays_swap_button)
    assert win.result_label.text() == '1일'
    click(qtbot, win, f['holidays'])
    assert win.result_label.text() == '2일'
    click(qtbot, win, f['include_start'])
    assert win.result_label.text() == '1일'
    click(qtbot, win, f['day_5'])
    assert win.result_label.text() == '2일'
    click(qtbot, win, f['holidays'])
    f['start_date'].setText('2028-01-03')
    f['end_date'].setText('2028-01-07')
    assert win.result_label.text() == '—'
    assert '2025' in win.error_label.text() and '2027' in win.error_label.text()
    click(qtbot, win, f['holidays'])
    assert win.result_label.text() == '4일'
    assert '공휴일 미반영' in win.result_note.text()


@pytest.mark.parametrize('mode,key,value', [
    ('difference', 'end_time', '24:30'),
    ('difference', 'end_time', '12:59:60'),
    ('difference', 'break_minutes', '-1'),
    ('calendar', 'base_date', '2026-02-30'),
    ('calendar', 'years', '1000000'),
    ('workdays', 'start_date', ''),
])
def test_invalid_input_clears_stale_result_and_cannot_copy_or_record(qtbot, mode, key, value):
    win = calculator(qtbot)
    win.select_mode(mode)
    if mode == 'workdays':
        win.fields[mode]['start_date'].setText('2026-01-02')
        win.fields[mode]['end_date'].setText('2026-01-02')
    assert win._valid
    win.save_recent()
    before = deepcopy(win.history)
    QApplication.clipboard().setText('합성 기준 문자열')
    win.fields[mode][key].setText(value)
    assert win.result_label.text() == '—'
    assert not win._valid and win._seconds is None and win._copy_text is None
    assert win.error_label.isVisible()
    assert not win.copy_button.isEnabled() and not win.save_button.isEnabled()
    win.copy_result()
    win.save_recent()
    assert QApplication.clipboard().text() == '합성 기준 문자열'
    assert win.history == before


def test_mode_inputs_and_recent_record_restore_original_seconds(qtbot):
    win = calculator(qtbot)
    f = win.fields['difference']
    f['end_time'].setText('18:59:30')
    f['break_minutes'].setText('20')
    win.save_recent()
    entry = deepcopy(win.history[0])
    f['break_minutes'].setText('40')
    win.select_mode('calendar')
    win.fields['calendar']['months'].setText('3')
    win.select_mode('difference')
    assert f['break_minutes'].text() == '40'
    assert win.result_label.text() == '379분 30초'
    win.select_mode('calendar')
    assert win.fields['calendar']['months'].text() == '3'
    click(qtbot, win, win.recent_combo)
    assert win.recent_combo.view().isVisible()
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down)
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
    assert win.mode == 'difference'
    assert f['break_minutes'].text() == '20'
    assert win.result_label.text() == '399분 30초'
    assert win.history[0] == entry


def test_history_is_deduplicated_and_limited_to_twelve_entries(qtbot):
    win = calculator(qtbot)
    for minute in range(14):
        win.fields['difference']['end_time'].setText(f'13:{minute:02}:30')
        win.save_recent()
    assert len(win.history) == 12
    assert win.history[-1]['values']['end_time'] == '13:02:30'
    win.save_recent()
    assert len(win.history) == 12
    assert win.recent_combo.count() == 13
    win.restore_recent(win.history[-1])
    assert win.result_label.text() == '62분 30초'


def test_duration_sum_signs_switching_and_actual_row_delete(qtbot):
    win = calculator(qtbot)
    click(qtbot, win, win.mode_buttons['sum'])
    first = win._sum_rows[0][1]
    type_text(qtbot, win, first['hours'], '1')
    first['minutes'].setText('30')
    first['seconds'].setText('30')
    click(qtbot, win, win.add_row_button)
    second_panel, second = win._sum_rows[1]
    second['minutes'].setText('20')
    choose(second['sign'], -1)
    assert win.result_label.text() == '70분 30초'
    win.save_recent()
    entry = deepcopy(win.history[0])
    choose(win.sum_kind, 'interval')
    row = win._sum_rows[0][1]
    row['break_minutes'].setText('15')
    assert win.result_label.text() == '45분'
    choose(win.sum_kind, 'duration')
    assert win.result_label.text() == '70분 30초'
    assert len(win._sum_rows) == 2
    second_panel = win._sum_rows[1][0]
    remove = next(button for button in second_panel.findChildren(QPushButton) if button.text() == '삭제')
    click(qtbot, win, remove)
    assert len(win._sum_rows) == 1
    assert win.result_label.text() == '90분 30초'
    win.restore_recent(entry)
    assert len(win._sum_rows) == 2
    assert win.result_label.text() == '70분 30초'
    choose(win.sum_kind, 'interval')
    assert win._sum_rows[0][1]['break_minutes'].text() == '15'


def test_restoring_other_sum_kind_keeps_current_unsaved_inputs(qtbot):
    win = calculator(qtbot)
    win.select_mode('sum')
    win._sum_rows[0][1]['minutes'].setText('25')
    win.save_recent()
    duration_entry = deepcopy(win.history[0])
    choose(win.sum_kind, 'interval')
    win._sum_rows[0][1]['break_minutes'].setText('17')
    win.restore_recent(duration_entry)
    assert win.result_label.text() == '25분'
    choose(win.sum_kind, 'interval')
    assert win._sum_rows[0][1]['break_minutes'].text() == '17'
    assert win.result_label.text() == '43분'


def test_empty_sum_record_restores_zero_rows_and_kind_switch_preserves_it(qtbot):
    win = calculator(qtbot)
    win.select_mode('sum')
    panel = win._sum_rows[0][0]
    remove = next(button for button in panel.findChildren(QPushButton) if button.text() == '삭제')
    click(qtbot, win, remove)
    assert win._sum_rows == []
    assert win.result_label.text() == '0분'
    win.save_recent()
    entry = deepcopy(win.history[0])
    assert entry['rows'] == []
    choose(win.sum_kind, 'interval')
    assert len(win._sum_rows) == 1
    win._sum_rows[0][1]['break_minutes'].setText('17')
    win.restore_recent(entry)
    assert win._sum_rows == []
    assert win.result_label.text() == '0분'
    choose(win.sum_kind, 'interval')
    assert win.result_label.text() == '43분'
    choose(win.sum_kind, 'duration')
    assert win._sum_rows == []
    assert win.result_label.text() == '0분'


def test_work_intervals_use_dates_and_reject_reverse_order(qtbot):
    win = calculator(qtbot)
    win.select_mode('sum')
    choose(win.sum_kind, 'interval')
    first = win._sum_rows[0][1]
    first['start_date'].setText('2026-09-24')
    first['end_date'].setText('2026-09-25')
    first['start_time'].setText('23:50')
    first['end_time'].setText('00:20:30')
    first['break_minutes'].setText('10')
    assert win.result_label.text() == '20분 30초'
    click(qtbot, win, win.add_row_button)
    second = win._sum_rows[1][1]
    second['break_minutes'].setText('15')
    assert win.result_label.text() == '65분 30초'
    first['end_date'].setText('2026-09-24')
    assert win.result_label.text() == '—'
    assert '시작보다' in win.error_label.text()


@pytest.mark.parametrize('key', [Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter])
def test_focused_mode_and_action_buttons_support_keyboard(qtbot, key):
    win = calculator(qtbot)
    mode = win.mode_buttons['calendar']
    mode.setFocus()
    qtbot.waitUntil(mode.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), key)
    assert win.mode == 'calendar'
    if win.body.isAncestorOf(win.save_button):
        win.body_scroll.ensureWidgetVisible(win.save_button)
    win.save_button.setFocus()
    qtbot.waitUntil(win.save_button.hasFocus)
    qtbot.keyClick(QApplication.focusWidget(), key)
    assert len(win.history) == 1
    assert win.history[0]['mode'] == 'calendar'


def test_dropdown_after_edit_opens_immediately_selects_and_esc_only_closes_popup(qtbot, qapp):
    win = calculator(qtbot)

    class Shows(QObject):
        def __init__(self):
            super().__init__()
            self.names = []

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Show:
                self.names.append(watched.metaObject().className())
            return False

    shows = Shows()
    qapp.installEventFilter(shows)
    original_effect = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
    try:
        type_text(qtbot, win, win.fields['difference']['end_time'], '18:59:30')
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, True)
        click(qtbot, win, win.copy_mode)
        assert win.copy_mode.view().isVisible()
        assert 'QRollEffect' not in shows.names
        assert QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Down)
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Return)
        assert win.copy_mode.currentData() == 'exact'
        assert not win.copy_mode.view().isVisible()
        click(qtbot, win, win.copy_mode)
        assert win.copy_mode.view().isVisible()
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
        assert not win.copy_mode.view().isVisible()
        assert win.isVisible()
        assert win.copy_mode.currentData() == 'exact'
        win.close_button.setFocus()
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
        assert not win.isVisible()
    finally:
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, original_effect)
        qapp.removeEventFilter(shows)


@pytest.mark.parametrize('mode', list(MODES))
@pytest.mark.parametrize('size', [QSize(1000, 900), QSize(480, 500), QSize(420, 500)])
def test_all_modes_fit_work_area_and_render_without_horizontal_clipping(qtbot, mode, size):
    win = calculator(qtbot)
    win.select_mode(mode)
    if mode == 'difference':
        win.fields[mode]['end_time'].setText('18:59:30')
    elif mode == 'calendar':
        win.fields[mode]['base_date'].setText('2026-01-31')
        win.fields[mode]['months'].setText('1')
    elif mode == 'workdays':
        win.fields[mode]['start_date'].setText('2026-01-01')
        win.fields[mode]['end_date'].setText('2026-01-04')
    else:
        win._sum_rows[0][1]['hours'].setText('6')
        win._sum_rows[0][1]['minutes'].setText('59')
    available = QRect(QPoint(0, 0), size)
    win.fit_to_screen(available)
    QApplication.processEvents()
    assert available.contains(win.geometry())
    assert win.body_scroll.horizontalScrollBar().maximum() == 0
    assert win.title_label.width() >= win.title_label.fontMetrics().horizontalAdvance(win.title_label.text())
    for control in win.page_widgets[mode].findChildren(QWidget):
        if isinstance(control, (QLineEdit, QCheckBox, QComboBox)) and control.isVisible():
            rectangle = QRect(control.mapTo(win.body, QPoint()), control.size())
            assert rectangle.left() >= 0
            assert rectangle.right() < win.body.width()
    for name, button in win.mode_buttons.items():
        assert button.width() >= button.fontMetrics().horizontalAdvance(MODES[name]) + 14
    capture(win, f'{mode}-{size.width()}x{size.height()}')
    if win.body.isAncestorOf(win.copy_button):
        win.body_scroll.ensureWidgetVisible(win.copy_button, 8, 12)
        QApplication.processEvents()
        copy_bounds = QRect(win.copy_button.mapTo(win.body_scroll.viewport(), QPoint()), win.copy_button.size())
        assert win.body_scroll.viewport().rect().contains(copy_bounds)
    else:
        copy_bounds = QRect(win.copy_button.mapTo(win, QPoint()), win.copy_button.size())
        assert win.rect().contains(copy_bounds)
