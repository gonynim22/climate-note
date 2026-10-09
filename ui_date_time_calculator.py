"""A안 날짜·시간 계산기. 입력·최근 기록·창 위치는 실행 중 메모리 전용."""
from copy import deepcopy
from datetime import date, datetime, timedelta

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QCheckBox, QFrame, QGraphicsDropShadowEffect,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from date_time_calculator import (
    add_calendar, calendar_difference, difference_seconds, format_duration,
    format_minutes, interval_seconds, minute_value, parse_date, parse_time,
    sum_durations, working_days,
)
from ui_converter_combo import ConverterCombo
from ui_mini_app_frame import MiniAppCheckBox, MiniAppTitleBar, mini_app_icon_path

WINDOW_WIDTH, WINDOW_HEIGHT, SHADOW_MARGIN = 480, 620, 24
MODES = {'difference': '시간 차이', 'calendar': '날짜 연산', 'workdays': '근무일', 'sum': '시간 합산'}


class DateTimeCalculatorWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName('dateTimeCalculator')
        self.setWindowTitle('날짜·시간 계산기 · 기후노트')
        self.setAccessibleName('날짜·시간 계산기')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(1.0)
        base_font = QFont(self.font())
        base_font.setPixelSize(13)
        self.setFont(base_font)
        self.history = []
        self.fields = {mode: {} for mode in MODES}
        self.mode = 'difference'
        self._updating = False
        self._drag_origin = None
        self._placed = False
        self._seconds = None
        self._copy_text = None
        self._valid = False
        self._sum_rows = []
        self._sum_index = 0
        self._sum_indices = {'duration': 0, 'interval': 0}
        self._form_notes = []
        self.setStyleSheet('''
            QWidget { color:#292C33; }
            QWidget#dateTimeSurface { background:#FDFDFB; border-radius:16px; }
            QWidget#dateTimeRail { background:#23252B; border-bottom-left-radius:16px; }
            QLineEdit { background:white; border:1px solid #CDD5E0; border-radius:6px; padding:4px 8px; }
            QLineEdit:focus { border:1px solid #577AAA; }
            QLineEdit:disabled { background:#F0F2F4; color:#86909C; }
            QPushButton { background:#FFFFFF; border:1px solid #CDD5E0; border-radius:6px; padding:4px 8px; }
            QPushButton:hover { background:#EDF3FB; border-color:#91AACA; }
            QPushButton:focus { border:1px solid #315C98; }
            QPushButton:disabled { color:#959CA6; background:#F3F4F6; }
            QPushButton[modeButton="true"] { background:transparent; color:#BFC5CF; border:0; padding:10px 7px; text-align:left; }
            QPushButton[modeButton="true"]:checked { background:#3C4657; color:white; }
            QPushButton[modeButton="true"]:focus { border:1px solid #90ACD0; }
            QFrame#dateTimeResult { background:#EDF3FC; border:1px solid #CBD9ED; border-radius:10px; }
            QCheckBox { spacing:5px; font-size:12px; }
            QLabel[muted="true"] { color:#636A76; font-size:11px; }
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.surface = QWidget(self)
        self.surface.setObjectName('dateTimeSurface')
        self.surface.setAttribute(Qt.WA_StyledBackground)
        outer.addWidget(self.surface)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.surface.setGraphicsEffect(shadow)
        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        # 미니앱 공용 어두운 제목줄. header는 끌기·좁은 화면 처리에 쓰는 기존 이름이다.
        self.title_bar = MiniAppTitleBar('날짜·시간 계산기', mini_app_icon_path('date_time'), self.close, self.surface)
        self.header = self.title_bar
        self.title_label = self.title_bar.title_label
        self.close_button = self.title_bar.close_button
        self.close_button.installEventFilter(self)
        self.title_bar.installEventFilter(self)
        surface_layout.addWidget(self.title_bar)
        area = QHBoxLayout()
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(0)
        surface_layout.addLayout(area, 1)
        self.rail = QWidget()
        self.rail.setObjectName('dateTimeRail')
        self.rail.setAttribute(Qt.WA_StyledBackground)
        self.rail.setFixedWidth(108)
        nav = QVBoxLayout(self.rail)
        nav.setContentsMargins(7, 18, 7, 12)
        nav.setSpacing(5)
        brand = QLabel('계산 종류')
        brand.setStyleSheet('color:#959CAA;font-size:11px;padding:0 5px 8px;')
        nav.addWidget(brand)
        self.mode_buttons = {}
        for mode, label in MODES.items():
            button = self._button(label, lambda checked=False, m=mode: self.select_mode(m))
            button.setProperty('modeButton', True)
            button.setCheckable(True)
            button.setFixedHeight(40)
            self.mode_buttons[mode] = button
            nav.addWidget(button)
        nav.addStretch()
        area.addWidget(self.rail)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.right_layout = right_layout
        right_layout.setContentsMargins(18, 17, 18, 16)
        right_layout.setSpacing(7)
        self.mode_title = QLabel()
        self.mode_title.setStyleSheet('font-size:18px;font-weight:bold;')
        right_layout.addWidget(self.mode_title)
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.pages = QStackedWidget()
        self.pages.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        body_layout.addWidget(self.pages)
        self.page_widgets = {}
        for mode in MODES:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(7)
            self.page_widgets[mode] = page
            self.pages.addWidget(page)
        self._build_difference()
        self._build_calendar()
        self._build_workdays()
        self._build_sum()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color:#AA2828;font-size:12px;')
        self.error_label.setAccessibleName('계산 오류')
        body_layout.addStretch()
        right_layout.addWidget(self.body, 1)
        right_layout.addWidget(self.error_label)
        result = QFrame()
        result.setObjectName('dateTimeResult')
        result_layout = QVBoxLayout(result)
        self.result_layout = result_layout
        self.result_card = result
        result_layout.setContentsMargins(14, 12, 14, 12)
        result_layout.setSpacing(4)
        self.result_caption = QLabel('계산 결과 · 총 분')
        self.result_caption.setStyleSheet('color:#315C98;font-size:11px;')
        self.result_label = QLabel()
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.result_label.setWordWrap(True)
        self.result_label.setMinimumHeight(43)
        self.result_detail = QLabel()
        self.result_detail.setWordWrap(True)
        self.result_detail.setStyleSheet('font-size:12px;color:#4E627D;')
        self.result_note = self._note('')
        for widget in (self.result_caption, self.result_label, self.result_detail, self.result_note):
            result_layout.addWidget(widget)
        right_layout.addWidget(result)
        actions = QHBoxLayout()
        self.copy_mode = ConverterCombo()
        self.copy_mode.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.copy_mode.setMinimumWidth(0)
        self.copy_mode.view().setMinimumWidth(220)
        self.copy_mode.setAccessibleName('복사 형식')
        for title, key in [('결과 전체', 'result'), ('분 숫자(소수 12자리)', 'exact'), ('분 내림', 'floor'), ('분 반올림', 'nearest'), ('분 올림', 'ceil')]:
            self.copy_mode.addItem(title, key)
        self.copy_mode.setToolTip('분 숫자는 최대 소수 12자리. 원본 초는 바뀌지 않습니다.')
        actions.addWidget(self.copy_mode, 1)
        self.copy_button = self._button('복사', self.copy_result)
        self.save_button = self._button('기록', self.save_recent)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        right_layout.addLayout(actions)
        self.recent_combo = ConverterCombo()
        self.recent_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.recent_combo.setMinimumWidth(0)
        self.recent_combo.setAccessibleName('최근 계산 12개')
        self.recent_combo.addItem('최근 계산 · Enter로 기록', None)
        self.recent_combo.activated.connect(self._restore_index)
        right_layout.addWidget(self.recent_combo)
        self.status_label = self._note('이 창의 입력과 최근 12개는 실행 중에만 유지됩니다.')
        right_layout.addWidget(self.status_label)
        area.addWidget(right, 1)
        self.resize(WINDOW_WIDTH + 2 * SHADOW_MARGIN, WINDOW_HEIGHT + 2 * SHADOW_MARGIN)
        self.select_mode('difference')

    def _button(self, text, slot):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        button.installEventFilter(self)
        return button

    @staticmethod
    def _note(text):
        label = QLabel(text)
        label.setProperty('muted', True)
        label.setWordWrap(True)
        return label

    def _form_note(self, text):
        label = self._note(text)
        self._form_notes.append(label)
        return label

    def _input(self, mode, key, label, value, *, time=False):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._note(label))
        edit = QLineEdit(str(value))
        edit.setAccessibleName(label)
        edit.setObjectName(f'{mode}_{key}')
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        edit.setMaxLength(24)
        if time:
            edit.setStyleSheet('font-size:21px;')
            edit.setPlaceholderText('12:00:00')
            edit.setToolTip('24시간제 H:MM 또는 HH:MM:SS')
        elif 'date' in key:
            edit.setPlaceholderText('YYYY-MM-DD')
            edit.setToolTip('연-월-일 · 예: 2026-09-24')
        edit.textChanged.connect(self.update_results)
        edit.returnPressed.connect(self.save_recent)
        edit.installEventFilter(self)
        layout.addWidget(edit)
        self.fields[mode][key] = edit
        return container

    def _check(self, mode, key, title, checked=False):
        box = MiniAppCheckBox(title)
        box.setChecked(checked)
        box.setAccessibleName(title)
        self.fields[mode][key] = box
        box.toggled.connect(self.update_results)
        return box

    def _combo(self, mode, key, items):
        combo = ConverterCombo()
        combo.setAccessibleName(key)
        for title, value in items:
            combo.addItem(title, value)
        self.fields[mode][key] = combo
        combo.currentIndexChanged.connect(self.update_results)
        return combo

    def _build_difference(self):
        mode = 'difference'
        layout = self.page_widgets[mode].layout()
        options = QHBoxLayout()
        options.addWidget(self._check(mode, 'dates', '날짜 포함'))
        options.addWidget(self._check(mode, 'next_day', '다음 날 종료'))
        options.addStretch()
        layout.addLayout(options)
        self.date_fields = QWidget()
        dates = QVBoxLayout(self.date_fields)
        dates.setContentsMargins(0, 0, 0, 0)
        dates.setSpacing(5)
        today = date.today().isoformat()
        date_pair = QHBoxLayout()
        date_pair.setSpacing(8)
        date_pair.addWidget(self._input(mode, 'start_date', '시작 날짜', today))
        date_pair.addWidget(self._input(mode, 'end_date', '종료 날짜', today))
        dates.addLayout(date_pair)
        dates.addWidget(self._check(mode, 'date_only', '시간 없이 날짜만 비교'))
        layout.addWidget(self.date_fields)
        self.clock_fields = QWidget()
        clocks = QHBoxLayout(self.clock_fields)
        clocks.setContentsMargins(0, 0, 0, 0)
        clocks.setSpacing(10)
        clocks.addWidget(self._input(mode, 'start_time', '시작', '12:00', time=True))
        clocks.addWidget(self._input(mode, 'end_time', '종료', '18:59', time=True))
        layout.addWidget(self.clock_fields)
        self.break_field = QWidget()
        rest = QHBoxLayout(self.break_field)
        rest.setContentsMargins(0, 0, 0, 0)
        rest.addWidget(self._note('휴게 공제'))
        edit = QLineEdit('0')
        edit.setAccessibleName('휴게시간 공제 분')
        edit.setFixedWidth(65)
        edit.setMaxLength(6)
        edit.textChanged.connect(self.update_results)
        edit.returnPressed.connect(self.save_recent)
        self.fields[mode]['break_minutes'] = edit
        rest.addWidget(edit)
        rest.addWidget(self._note('분'))
        rest.addStretch()
        self.swap_button = self._button('시작 ↔ 종료', self.swap_dates)
        self.swap_button.setAccessibleName('시작 / 종료 바꾸기')
        rest.addWidget(self.swap_button)
        layout.addWidget(self.break_field)
        self.date_swap_button = self._button('시작 / 종료 바꾸기', self.swap_dates)
        layout.addWidget(self.date_swap_button)
        layout.addWidget(self._form_note('초까지 입력 가능 · 자정을 넘으면 다음 날 종료를 선택하세요.'))

    def _build_calendar(self):
        mode = 'calendar'
        layout = self.page_widgets[mode].layout()
        base = QHBoxLayout()
        base.setSpacing(8)
        base.addWidget(self._input(mode, 'base_date', '기준 날짜', date.today().isoformat()), 3)
        base.addWidget(self._input(mode, 'base_time', '기준 시각', '12:00'), 2)
        layout.addLayout(base)
        layout.addWidget(self._combo(mode, 'operation', [('더하기 +', 1), ('빼기 −', -1)]))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (key, label) in enumerate([('years', '년'), ('months', '월'), ('days', '일'), ('hours', '시간'), ('minutes', '분'), ('seconds', '초')]):
            grid.addWidget(self._input(mode, key, label, 0), i // 3, i % 3)
        layout.addLayout(grid)
        layout.addWidget(self._form_note('년·월을 먼저 계산 · 없는 날짜는 대상 월의 말일로 조정'))

    def _build_workdays(self):
        mode = 'workdays'
        layout = self.page_widgets[mode].layout()
        today = date.today().isoformat()
        dates = QHBoxLayout()
        dates.setSpacing(8)
        dates.addWidget(self._input(mode, 'start_date', '시작 날짜', today))
        dates.addWidget(self._input(mode, 'end_date', '종료 날짜', today))
        layout.addLayout(dates)
        ends = QHBoxLayout()
        ends.addWidget(self._check(mode, 'include_start', '시작일 포함', True))
        ends.addWidget(self._check(mode, 'include_end', '종료일 포함', True))
        layout.addLayout(ends)
        layout.addWidget(self._note('제외할 요일'))
        weekdays = QHBoxLayout()
        weekdays.setSpacing(3)
        for i, label in enumerate('월화수목금토일'):
            weekdays.addWidget(self._check(mode, f'day_{i}', label, i >= 5))
        layout.addLayout(weekdays)
        layout.addWidget(self._check(mode, 'holidays', '공휴일 제외', True))
        self.fields[mode]['holidays'].setToolTip('공휴일 자료: 2025–2027년 · 범위 밖은 공휴일 제외를 끄고 계산')
        layout.addWidget(self._form_note('공휴일 자료: 2025–2027년'))
        self.workdays_swap_button = self._button('시작 / 종료 바꾸기', lambda: self.swap_dates('workdays'))
        layout.addWidget(self.workdays_swap_button)

    def _build_sum(self):
        mode = 'sum'
        layout = self.page_widgets[mode].layout()
        self.sum_kind = self._combo(mode, 'kind', [('기간 합산', 'duration'), ('근무 구간 합산', 'interval')])
        self.sum_kind.currentIndexChanged.disconnect(self.update_results)
        self.sum_kind.currentIndexChanged.connect(self._sum_kind_changed)
        kind_row = QHBoxLayout()
        kind_row.addWidget(self.sum_kind, 1)
        self.sum_kind.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.sum_kind.setMinimumWidth(0)
        self.add_row_button = self._button('+ 추가', lambda: self.add_sum_row())
        kind_row.addWidget(self.add_row_button)
        layout.addLayout(kind_row)
        navigation = QHBoxLayout()
        navigation.setSpacing(4)
        self.previous_row_button = self._button('‹', lambda: self.select_sum_row(self._sum_index - 1))
        self.previous_row_button.setAccessibleName('이전 합산 항목')
        self.next_row_button = self._button('›', lambda: self.select_sum_row(self._sum_index + 1))
        self.next_row_button.setAccessibleName('다음 합산 항목')
        for button in (self.previous_row_button, self.next_row_button):
            button.setFixedWidth(28)
        self.row_position = self._note('')
        self.row_position.setAlignment(Qt.AlignCenter)
        navigation.addWidget(self.previous_row_button)
        navigation.addWidget(self.row_position, 1)
        navigation.addWidget(self.next_row_button)
        self.remove_row_button = self._button('삭제', self._remove_current_row)
        self.remove_row_button.setAccessibleName('이 행 삭제')
        navigation.addWidget(self.remove_row_button)
        layout.addLayout(navigation)
        self.sum_rows_widget = QWidget()
        self.sum_rows_layout = QVBoxLayout(self.sum_rows_widget)
        self.sum_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.sum_rows_layout.setSpacing(0)
        layout.addWidget(self.sum_rows_widget)
        layout.addWidget(self._form_note('전체 항목을 합산합니다. 년·월은 날짜 연산에서 계산하세요.'))
        self._sum_saved = {'duration': None, 'interval': None}
        self._sum_current_kind = 'duration'
        self.add_sum_row()

    def _sum_kind_changed(self):
        if not hasattr(self, '_sum_saved') or self._updating:
            return
        self._sum_saved[self._sum_current_kind] = self._row_values()
        self._sum_indices[self._sum_current_kind] = self._sum_index
        self._sum_current_kind = self.sum_kind.currentData()
        self._replace_rows(self._sum_saved[self._sum_current_kind])
        self.select_sum_row(self._sum_indices[self._sum_current_kind])
        self.update_results()

    def select_sum_row(self, index):
        self._sum_index = max(0, min(index, len(self._sum_rows) - 1))
        for i, (panel, _) in enumerate(self._sum_rows):
            panel.setVisible(i == self._sum_index)
        count = len(self._sum_rows)
        self.row_position.setText(f'{self._sum_index + 1} / {count}' if count else '항목 없음')
        self.previous_row_button.setEnabled(count > 0 and self._sum_index > 0)
        self.next_row_button.setEnabled(self._sum_index + 1 < count)
        self.remove_row_button.setEnabled(count > 0)
        self.add_row_button.setEnabled(count < 24)
        self.page_widgets['sum'].updateGeometry()

    def _remove_current_row(self):
        if self._sum_rows:
            self.remove_sum_row(self._sum_rows[self._sum_index][0])

    def add_sum_row(self, values=None):
        if len(self._sum_rows) >= 24:
            return
        previous = self._updating
        self._updating = True
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        controls = {}
        grid = QGridLayout()
        grid.setSpacing(6)
        if self.sum_kind.currentData() == 'duration':
            sign = ConverterCombo()
            sign.addItem('더하기 +', 1)
            sign.addItem('빼기 −', -1)
            sign.setAccessibleName('기간 더하기/빼기')
            sign.currentIndexChanged.connect(self.update_results)
            controls['sign'] = sign
            layout.addWidget(sign)
            names = [('days', '일', '0'), ('hours', '시간', '0'), ('minutes', '분', '0'), ('seconds', '초', '0')]
        else:
            today = date.today().isoformat()
            names = [('start_date', '시작 날짜', today), ('end_date', '종료 날짜', today), ('start_time', '시작 시각', '18:00'), ('end_time', '종료 시각', '19:00'), ('break_minutes', '휴게 (분)', '0')]
        for i, (key, label, default) in enumerate(names):
            wrapper = QWidget()
            pair = QHBoxLayout(wrapper) if key == 'break_minutes' else QVBoxLayout(wrapper)
            pair.setContentsMargins(0, 0, 0, 0)
            pair.setSpacing(4)
            pair.addWidget(self._note(label))
            edit = QLineEdit(default)
            edit.setAccessibleName(label)
            edit.setMinimumWidth(0)
            edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            edit.setMaxLength(24)
            edit.textChanged.connect(self.update_results)
            edit.returnPressed.connect(self.save_recent)
            edit.installEventFilter(self)
            controls[key] = edit
            pair.addWidget(edit)
            grid.addWidget(wrapper, i // 2, i % 2)
        layout.addLayout(grid)
        self._sum_rows.append((panel, controls))
        self.sum_rows_layout.addWidget(panel)
        if values:
            self._set_controls(controls, values)
        self._updating = previous
        self.select_sum_row(len(self._sum_rows) - 1)
        self.update_results()

    def remove_sum_row(self, panel):
        row = next(row for row in self._sum_rows if row[0] is panel)
        self._sum_rows.remove(row)
        self.sum_rows_layout.removeWidget(panel)
        panel.hide()
        panel.deleteLater()
        self.select_sum_row(self._sum_index)
        self.update_results()

    def _replace_rows(self, rows):
        previous = self._updating
        self._updating = True
        for panel, _ in self._sum_rows:
            self.sum_rows_layout.removeWidget(panel)
            panel.hide()
            panel.deleteLater()
        self._sum_rows = []
        for values in ([{}] if rows is None else rows):
            self.add_sum_row(values)
        self.select_sum_row(0)
        self._updating = previous

    @staticmethod
    def _values(controls):
        return {key: widget.isChecked() if isinstance(widget, QCheckBox) else
                widget.currentData() if isinstance(widget, ConverterCombo) else widget.text()
                for key, widget in controls.items()}

    @staticmethod
    def _set_controls(controls, values):
        for key, value in values.items():
            widget = controls[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, ConverterCombo):
                widget.setCurrentIndex(widget.findData(value))
            else:
                widget.setText(str(value))

    def _row_values(self):
        return [self._values(controls) for _, controls in self._sum_rows]

    @staticmethod
    def _integer(text):
        if not text or not text.isascii() or not text.isdecimal():
            raise ValueError('기간과 휴게시간에는 0 이상의 정수를 입력하세요.')
        value = int(text)
        if value > 999999:
            raise ValueError('기간의 각 항목은 999,999 이하로 입력하세요.')
        return value

    @staticmethod
    def _datetime(date_text, time_text):
        return datetime.combine(parse_date(date_text), parse_time(time_text))

    def select_mode(self, mode):
        self.mode = mode
        self.pages.setCurrentWidget(self.page_widgets[mode])
        self.mode_title.setText(MODES[mode])
        for key, button in self.mode_buttons.items():
            button.setChecked(key == mode)
        # QStackedWidget의 숨긴 페이지 최소 높이가 현재 모드에 전파되지 않게 한다.
        for key, page in self.page_widgets.items():
            page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred if key == mode else QSizePolicy.Ignored)
        self.update_results()

    def swap_dates(self, mode='difference'):
        # clicked(bool)의 인자가 들어오면 현재 시간 차이 페이지를 사용한다.
        mode = mode if isinstance(mode, str) else 'difference'
        controls = self.fields[mode]
        self._updating = True
        for suffix in (('date', 'time') if mode == 'difference' else ('date',)):
            first, last = controls['start_' + suffix], controls['end_' + suffix]
            before = first.text()
            first.setText(last.text())
            last.setText(before)
        self._updating = False
        self.update_results()

    def update_results(self, *args):
        if self._updating or not hasattr(self, 'result_label'):
            return
        self._seconds = None
        self._valid = False
        self._copy_text = None
        self.status_label.setText('이 창의 입력과 최근 12개는 실행 중에만 유지됩니다.')
        d = self._values(self.fields[self.mode])
        try:
            if self.mode == 'difference':
                only = d['dates'] and d['date_only']
                self.date_fields.setVisible(d['dates'])
                self.clock_fields.setVisible(not only)
                self.break_field.setVisible(not only)
                self.date_swap_button.setVisible(only)
                self.fields[self.mode]['next_day'].setEnabled(not d['dates'])
                if only:
                    start = datetime.combine(parse_date(d['start_date']), datetime.min.time())
                    end = datetime.combine(parse_date(d['end_date']), datetime.min.time())
                    seconds = difference_seconds(start, end)
                    self._show_result('계산 결과 · 경과 일수', f'{seconds // 86400:,}일', self._calendar_detail(start, end), '시간 미포함 · 양 끝 날짜 개수와 구분', seconds)
                else:
                    start_day = parse_date(d['start_date']) if d['dates'] else date(2000, 1, 1)
                    end_day = parse_date(d['end_date']) if d['dates'] else start_day + timedelta(days=int(d['next_day']))
                    start = datetime.combine(start_day, parse_time(d['start_time']))
                    end = datetime.combine(end_day, parse_time(d['end_time']))
                    rest = self._integer(d['break_minutes'])
                    if d['dates'] and rest == 0:
                        seconds = difference_seconds(start, end)
                    else:
                        seconds = interval_seconds(start, end, rest)
                    note = f'휴게 {rest:,}분 공제'
                    if d['dates']:
                        note += '\n달력 차이(공제 전): ' + self._calendar_detail(start, end)
                    self._show_seconds(seconds, note)
            elif self.mode == 'calendar':
                base = self._datetime(d['base_date'], d['base_time'])
                result = add_calendar(base, **{key: self._integer(d[key]) for key in ('years', 'months', 'days', 'hours', 'minutes', 'seconds')}, sign=d['operation'])
                self._show_result('계산된 날짜', result.value.date().isoformat(), result.value.strftime('%H:%M:%S'), '년·월 → 일·시간·분·초' + ('\n월말로 조정됨' if result.adjusted else ''))
            elif self.mode == 'workdays':
                result = working_days(parse_date(d['start_date']), parse_date(d['end_date']), excluded_weekdays={i for i in range(7) if d[f'day_{i}']}, exclude_holidays=d['holidays'], include_start=d['include_start'], include_end=d['include_end'])
                self._show_result('계산 결과 · 근무일', f'{result.count:,}일', f'포함된 날짜 {result.total:,}일 중 {result.excluded:,}일 제외', ('공휴일 반영 (2025–2027)' if d['holidays'] else '공휴일 미반영 · 선택한 요일만 제외') + '\n주말과 공휴일은 중복 제외하지 않습니다.')
            else:
                rows = self._row_values()
                values = []
                for index, row in enumerate(rows, 1):
                    try:
                        if d['kind'] == 'duration':
                            seconds = sum(self._integer(row[key]) * factor for key, factor in [('days', 86400), ('hours', 3600), ('minutes', 60), ('seconds', 1)])
                            values.append(row['sign'] * seconds)
                        else:
                            values.append(interval_seconds(self._datetime(row['start_date'], row['start_time']), self._datetime(row['end_date'], row['end_time']), self._integer(row['break_minutes'])))
                    except (ValueError, OverflowError) as exc:
                        raise ValueError(f'{index}번째 항목: {exc}') from exc
                self._show_seconds(sum_durations(values), f'{len(rows)}개 ' + ('기간 합산' if d['kind'] == 'duration' else '구간 합산 · 각 구간을 개별 합산'))
            self.error_label.hide()
            self._valid = True
        except (ValueError, OverflowError) as exc:
            self.error_label.setText(str(exc) or '계산 범위를 벗어났습니다.')
            self.error_label.show()
            self.result_caption.setText('계산 결과')
            self.result_label.setText('—')
            self.result_detail.setText('입력을 확인하세요.')
            self.result_note.clear()
            self.result_card.setToolTip(self.error_label.text())
        self.copy_button.setEnabled(self._valid)
        self.save_button.setEnabled(self._valid)
        self.copy_mode.setEnabled(self._seconds is not None)
        self._fit_result_font()
        self.page_widgets[self.mode].updateGeometry()
        self.pages.updateGeometry()

    @staticmethod
    def _calendar_detail(start, end):
        delta = calendar_difference(start, end)
        parts = [f'{value}{label}' for value, label in [(delta.years, '년'), (delta.months, '개월'), (delta.days, '일'), (delta.hours, '시간'), (delta.minutes, '분'), (delta.seconds, '초')] if value]
        return ('−' if delta.sign < 0 else '') + (' '.join(parts) or '0일')

    def _show_seconds(self, seconds, note):
        self._show_result('계산 결과 · 총 분', format_minutes(seconds), format_duration(seconds), f'총 {seconds:,}초\n{note}', seconds)

    def _show_result(self, caption, main, detail, note, seconds=None):
        self.result_caption.setText(caption)
        self.result_label.setText(main)
        self.result_detail.setText(detail)
        self.result_note.setText(note)
        self.result_card.setToolTip('\n'.join([caption, main, detail, note]))
        self._seconds = seconds
        self._copy_text = '\n'.join([MODES[self.mode], main, detail, note])

    def copy_result(self):
        if not self._valid:
            return
        policy = self.copy_mode.currentData()
        text = self._copy_text if policy == 'result' or self._seconds is None else minute_value(self._seconds, policy)
        QApplication.clipboard().setText(text)
        self.status_label.setText('결과를 복사했습니다.')

    def save_recent(self):
        if not self._valid:
            return
        values = self._values(self.fields[self.mode])
        entry = {'mode': self.mode, 'values': values, 'rows': self._row_values() if self.mode == 'sum' else [], 'label': MODES[self.mode] + ' · ' + self.result_label.text()}
        self.history[:] = [old for old in self.history if old != entry]
        self.history.insert(0, deepcopy(entry))
        del self.history[12:]
        self.recent_combo.clear()
        self.recent_combo.addItem('최근 계산 · 선택하면 복원', None)
        for old in self.history:
            self.recent_combo.addItem(old['label'])
            self.recent_combo.setItemData(self.recent_combo.count() - 1, old['label'], Qt.ToolTipRole)
        self.status_label.setText('최근 계산에 기록했습니다.')

    def _restore_index(self, index):
        if index > 0:
            self.restore_recent(self.history[index - 1])

    def restore_recent(self, entry):
        entry = deepcopy(entry)
        self._updating = True
        if entry['mode'] == 'sum':
            self._sum_saved[self._sum_current_kind] = self._row_values()
            self._sum_indices[self._sum_current_kind] = self._sum_index
        self._set_controls(self.fields[entry['mode']], entry['values'])
        if entry['mode'] == 'sum':
            self._sum_current_kind = entry['values']['kind']
            self._replace_rows(entry['rows'])
            self._sum_saved[self._sum_current_kind] = deepcopy(entry['rows'])
        self._updating = False
        self.select_mode(entry['mode'])
        self.focus_input()

    def focus_input(self):
        for widget in self.page_widgets[self.mode].findChildren(QLineEdit):
            if widget.isVisible() and widget.isEnabled():
                widget.setFocus()
                widget.selectAll()
                break

    def show_near(self, anchor, available):
        if not self._placed:
            self.move(anchor.right() + 12, anchor.top())
            self._placed = True
        self.fit_to_screen(available)
        self.show()
        self.raise_()
        self.activateWindow()
        self.focus_input()

    def fit_to_screen(self, available=None):
        if available is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
        compact = available.height() < 620
        margin = min(SHADOW_MARGIN, max(0, (available.width() - 420) // 2), max(0, (available.height() - 620) // 2))
        self.title_bar.set_compact(compact)
        self.right_layout.setContentsMargins(12 if compact else 18, 6 if compact else 17, 12 if compact else 18, 6 if compact else 16)
        self.right_layout.setSpacing(4 if compact else 7)
        self.mode_title.setVisible(not compact)
        self.status_label.setVisible(not compact)
        self.result_note.setVisible(not compact)
        self.result_label.setMinimumHeight(32 if compact else 43)
        self.result_layout.setContentsMargins(10 if compact else 14, 6 if compact else 12, 10 if compact else 14, 6 if compact else 12)
        for note in self._form_notes:
            note.setVisible(not compact)
            note.parentWidget().setToolTip(note.text())
        for page in self.page_widgets.values():
            page.layout().setSpacing(4 if compact else 7)
        self.layout().setContentsMargins(margin, margin, margin, margin)
        shadow = self.surface.graphicsEffect()
        shadow.setBlurRadius(max(0, margin - 4))
        shadow.setOffset(0, min(4, margin))
        shadow.setEnabled(margin > 0)
        # 숨김/여백 변경의 최소 높이를 안쪽부터 반영한 뒤 native 창을 줄인다.
        for widget in reversed(self.findChildren(QWidget)):
            if widget.layout() is not None:
                widget.layout().activate()
                widget.updateGeometry()
        self.layout().activate()
        self.resize(min(WINDOW_WIDTH + margin * 2, available.width()), min(WINDOW_HEIGHT + margin * 2, available.height()))
        self.move(max(available.left(), min(self.x(), available.right() + 1 - self.width())), max(available.top(), min(self.y(), available.bottom() + 1 - self.height())))

    def hide_owned_popups(self):
        for combo in self.findChildren(ConverterCombo):
            combo.hidePopup()
        popup = QApplication.activePopupWidget()
        owner = popup
        while owner is not None:
            if owner is self:
                popup.close()
                break
            owner = owner.parentWidget()

    def _fit_result_font(self):
        font = QFont(self.font())
        font.setBold(True)
        for size in (34, 30, 26, 22, 18, 15):
            font.setPixelSize(size)
            if QFontMetrics(font).horizontalAdvance(self.result_label.text()) <= self.result_label.width():
                break
        self.result_label.setFont(font)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and isinstance(watched, QAbstractButton) and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                watched.click()
            return True
        if watched in (getattr(self, 'header', None), getattr(self, 'title_label', None)):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_origin = (event.globalPosition().toPoint(), self.pos())
                return True
            if event.type() == QEvent.MouseMove and self._drag_origin and event.buttons() & Qt.LeftButton:
                origin, position = self._drag_origin
                self.move(position + event.globalPosition().toPoint() - origin)
                return True
            if event.type() == QEvent.MouseButtonRelease and self._drag_origin:
                self._drag_origin = None
                self.fit_to_screen()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        self._drag_origin = None
        self.hide_owned_popups()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'result_label'):
            self._fit_result_font()
