"""금액·숫자 표기 도우미 창. 입력·최근 기록·창 위치는 실행 중 메모리 전용.

날짜·시간 계산기와 같은 치수·색의 독립 창이다(창 틀 중복은 v3.8c 설계에서 허용).
계산 규칙은 money_notation.py, 계약은 docs/MONEY_NOTATION.md를 따른다.
"""
from copy import deepcopy

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)

from money_notation import (
    MONEY_UNITS, NotationError, convert_money, exact_text, format_decimal,
    official_amount, parse_decimal, parse_integer, read_number, reading_hangul,
)
from ui_converter_combo import ConverterCombo

WINDOW_WIDTH, WINDOW_HEIGHT, SHADOW_MARGIN = 480, 620, 24
MODES = {"amount": "금액 표기", "read": "큰 수 읽기", "convert": "단위 환산"}
COPY_FORMATS = {
    "amount": (("공문서 병기", "official"), ("한글만", "hangul"), ("숫자만", "digits")),
    "read": (("억·만 표기", "notation"), ("한글 읽기", "hangul"), ("숫자만", "digits")),
    "convert": (("결과 값", "value"), ("전체 단위 목록", "table")),
}
READ_SCOPES = (("전체 자리", "all"), ("만 단위까지(반올림)", "man"), ("억 단위(소수 1자리)", "eok"))
DIGIT_CHOICES = (("자동", -1), ("0자리", 0), ("1자리", 1), ("2자리", 2), ("3자리", 3))
UNIT_NAMES = {key: name for key, name, _factor in MONEY_UNITS}
LAW_LINES = (
    "근거 「행정업무의 운영 및 혁신에 관한 규정 시행규칙」 제2조 — 금액은 아라비아 숫자로 쓰되, "
    "숫자 다음에 괄호를 하고 한글로 적습니다.",
    "예) 금113,560원(금일십일만삼천오백육십원)",
)
DEFAULT_STATUS = "이 창의 입력과 최근 12개는 실행 중에만 유지됩니다."
STYLE = """
    QWidget { color:#292C33; }
    QWidget#moneySurface { background:#FDFDFB; border-radius:16px; }
    QWidget#moneyRail { background:#23252B; border-bottom-left-radius:16px; }
    QLineEdit { background:white; border:1px solid #CDD5E0; border-radius:6px; padding:4px 8px; }
    QLineEdit:focus { border:1px solid #577AAA; }
    QPushButton { background:#FFFFFF; border:1px solid #CDD5E0; border-radius:6px; padding:4px 8px; }
    QPushButton:hover { background:#EDF3FB; border-color:#91AACA; }
    QPushButton:focus { border:1px solid #315C98; }
    QPushButton:disabled { color:#959CA6; background:#F3F4F6; }
    QPushButton[modeButton="true"] { background:transparent; color:#BFC5CF; border:0; padding:10px 7px; text-align:left; }
    QPushButton[modeButton="true"]:checked { background:#3C4657; color:white; }
    QPushButton[modeButton="true"]:focus { border:1px solid #90ACD0; }
    QFrame#moneyResult { background:#EDF3FC; border:1px solid #CBD9ED; border-radius:10px; }
    QFrame#copyPreview { background:#F5F7FA; border:1px solid #E1E6ED; border-radius:6px; }
    QLabel[muted="true"] { color:#636A76; font-size:11px; }
    QLabel#lawBox { background:#F5F7FA; border:1px solid #E1E6ED; border-radius:8px; padding:6px 9px; color:#4E5663; font-size:11px; }
    QLabel#copyPreviewText { color:#1E385C; font-size:12px; }
    QLabel#resultDetail { font-size:12px; color:#4E627D; }
    QLabel#resultDetail[strong="true"] { font-size:14px; font-weight:bold; color:#1E385C; }
    QLabel[unitRow="true"] { padding:0 8px; border-bottom:1px solid #EEF1F5; font-size:12px; }
    QLabel[unitRow="true"][hit="true"] { background:#EDF3FC; color:#1E385C; font-weight:bold; }
"""


def _set_property(widget, name, value):
    """동적 속성을 바꾸고 QSS를 다시 적용한다."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ElidedLabel(QLabel):
    """전체 문자열을 보관하고 폭에 맞게 말줄임한다. 툴팁은 전체 문자열이다."""

    def __init__(self, text=""):
        super().__init__()
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full = text
        self.setToolTip(text)
        self._apply()

    def full_text(self):
        return self._full

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()

    def _apply(self):
        width = self.contentsRect().width()
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, width) if width > 0 else self._full
        super().setText(shown)


class MoneyNotationWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("moneyNotation")
        self.setWindowTitle("금액·숫자 표기 도우미 · 기후노트")
        self.setAccessibleName("금액·숫자 표기 도우미")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(1.0)
        base_font = QFont(self.font())
        base_font.setPixelSize(13)
        self.setFont(base_font)
        self.history = []
        self.fields = {mode: {} for mode in MODES}
        self.mode = "amount"
        self._copy_choice = {mode: 0 for mode in MODES}
        self._outputs = {}
        self._label = ""
        self._valid = False
        self._updating = False
        self._drag_origin = None
        self._placed = False
        self._form_notes = []
        self._result_min_height = 43
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.surface = QWidget(self)
        self.surface.setObjectName("moneySurface")
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
        self._build_header(surface_layout)
        area = QHBoxLayout()
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(0)
        surface_layout.addLayout(area, 1)
        self._build_rail(area)
        self._build_right(area)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(2500)
        self._status_timer.timeout.connect(lambda: self.status_label.setText(DEFAULT_STATUS))
        self.resize(WINDOW_WIDTH + 2 * SHADOW_MARGIN, WINDOW_HEIGHT + 2 * SHADOW_MARGIN)
        self.select_mode("amount")

    # ── 구성 ──
    def _build_header(self, parent_layout):
        self.header = QWidget()
        self.header.setFixedHeight(52)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(18, 8, 12, 8)
        self.title_label = QLabel("금액·숫자 표기 도우미")
        self.title_label.setStyleSheet("font-size:15px;font-weight:bold;")
        header.addWidget(self.title_label)
        header.addStretch()
        self.close_button = self._button("×", self.close)
        self.close_button.setAccessibleName("금액·숫자 표기 도우미 닫기")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setStyleSheet("font-size:20px;padding:0;border:0;")
        header.addWidget(self.close_button)
        parent_layout.addWidget(self.header)
        for widget in (self.header, self.title_label):
            widget.installEventFilter(self)

    def _build_rail(self, area):
        self.rail = QWidget()
        self.rail.setObjectName("moneyRail")
        self.rail.setAttribute(Qt.WA_StyledBackground)
        self.rail.setFixedWidth(108)
        nav = QVBoxLayout(self.rail)
        nav.setContentsMargins(7, 18, 7, 12)
        nav.setSpacing(5)
        brand = QLabel("NUMBER")
        brand.setStyleSheet("color:#959CAA;font-size:11px;padding:0 5px 8px;")
        nav.addWidget(brand)
        self.mode_buttons = {}
        for mode, label in MODES.items():
            button = self._button(label, lambda checked=False, m=mode: self.select_mode(m))
            button.setProperty("modeButton", True)
            button.setCheckable(True)
            button.setFixedHeight(40)
            self.mode_buttons[mode] = button
            nav.addWidget(button)
        nav.addStretch()
        area.addWidget(self.rail)

    def _build_right(self, area):
        right = QWidget()
        self.right_layout = QVBoxLayout(right)
        self.right_layout.setContentsMargins(18, 17, 18, 16)
        self.right_layout.setSpacing(7)
        self.mode_title = QLabel()
        self.mode_title.setStyleSheet("font-size:18px;font-weight:bold;")
        self.right_layout.addWidget(self.mode_title)
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(7)
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
        self._build_amount()
        self._build_read()
        self._build_convert()
        body_layout.addStretch()
        self.copy_preview = QFrame()
        self.copy_preview.setObjectName("copyPreview")
        self.copy_preview.setFixedHeight(28)
        preview = QHBoxLayout(self.copy_preview)
        preview.setContentsMargins(10, 0, 10, 0)
        preview.setSpacing(8)
        preview.addWidget(self._note("복사 미리보기"))
        self.copy_preview_text = ElidedLabel()
        self.copy_preview_text.setObjectName("copyPreviewText")
        self.copy_preview_text.setAccessibleName("복사 미리보기")
        preview.addWidget(self.copy_preview_text, 1)
        body_layout.addWidget(self.copy_preview)
        self.right_layout.addWidget(self.body, 1)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color:#AA2828;font-size:12px;")
        self.error_label.setAccessibleName("입력 오류")
        self.error_label.hide()
        self.right_layout.addWidget(self.error_label)
        self.result_card = QFrame()
        self.result_card.setObjectName("moneyResult")
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_layout.setContentsMargins(14, 12, 14, 12)
        self.result_layout.setSpacing(4)
        self.result_caption = QLabel()
        self.result_caption.setStyleSheet("color:#315C98;font-size:11px;")
        self.result_label = QLabel()
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.result_label.setMinimumHeight(43)
        self.result_detail = QLabel()
        self.result_detail.setObjectName("resultDetail")
        self.result_detail.setWordWrap(True)
        self.result_detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.result_note = self._note("")
        for widget in (self.result_caption, self.result_label, self.result_detail, self.result_note):
            self.result_layout.addWidget(widget)
        self.right_layout.addWidget(self.result_card)
        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.copy_format = ConverterCombo()
        self.copy_format.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.copy_format.setMinimumWidth(0)
        self.copy_format.view().setMinimumWidth(200)
        self.copy_format.setAccessibleName("복사 형식")
        self.copy_format.currentIndexChanged.connect(self._copy_format_changed)
        actions.addWidget(self.copy_format, 1)
        self.copy_button = self._button("복사", self.copy_result)
        self.save_button = self._button("기록", self.save_recent)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        self.right_layout.addLayout(actions)
        self.recent_combo = ConverterCombo()
        self.recent_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.recent_combo.setMinimumWidth(0)
        self.recent_combo.setAccessibleName("최근 계산 12개")
        self.recent_combo.addItem("최근 계산 · Enter로 기록", None)
        self.recent_combo.activated.connect(self._restore_index)
        self.right_layout.addWidget(self.recent_combo)
        self.status_label = self._note(DEFAULT_STATUS)
        self.right_layout.addWidget(self.status_label)
        area.addWidget(right, 1)

    def _build_amount(self):
        layout = self.page_widgets["amount"].layout()
        layout.addWidget(self._input("amount", "value", "금액(원)", "113,560", big=True))
        layout.addWidget(self._form_note("정수 원 단위 · 쉼표는 있어도 없어도 됩니다."))
        self.law_box = QLabel("\n".join(LAW_LINES))
        self.law_box.setObjectName("lawBox")
        self.law_box.setWordWrap(True)
        self.law_box.setToolTip("\n".join(LAW_LINES))
        layout.addWidget(self.law_box)

    def _build_read(self):
        layout = self.page_widgets["read"].layout()
        layout.addWidget(self._input("read", "value", "숫자", "1,234,567,890", big=True))
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._input("read", "unit", "단위(선택)", "원", max_length=8), 1)
        row.addWidget(self._combo_field("read", "scope", "표시 범위", READ_SCOPES), 1)
        layout.addLayout(row)
        layout.addWidget(self._form_note("예산서·통계표의 긴 숫자를 억·만 단위로 읽습니다. 음수는 − 로 표시합니다."))

    def _build_convert(self):
        layout = self.page_widgets["convert"].layout()
        layout.addWidget(self._input("convert", "value", "값", "1,234,567", big=True))
        row = QHBoxLayout()
        row.setSpacing(7)
        units = tuple((name, key) for key, name, _factor in MONEY_UNITS)
        row.addWidget(self._combo("convert", "from", "입력 단위", units, "k"), 1)
        arrow = QLabel("→")
        arrow.setProperty("muted", True)
        row.addWidget(arrow)
        row.addWidget(self._combo("convert", "to", "결과 단위", units, "eok"), 1)
        digits = self._combo("convert", "digits", "소수 자릿수", DIGIT_CHOICES, 2)
        digits.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        digits.setFixedWidth(96)
        row.addWidget(digits)
        layout.addLayout(row)
        table = QWidget()
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)
        self.unit_rows = {}
        for row_index, (key, name, _factor) in enumerate(MONEY_UNITS):
            name_label = QLabel(name)
            name_label.setFixedWidth(70)
            value_label = ElidedLabel("—")
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setAccessibleName(f"{name} 값")
            for label in (name_label, value_label):
                label.setProperty("unitRow", True)
                label.setFixedHeight(20)
            grid.addWidget(name_label, row_index, 0)
            grid.addWidget(value_label, row_index, 1)
            self.unit_rows[key] = (name_label, value_label)
        grid.setColumnStretch(1, 1)
        layout.addWidget(table)

    def _button(self, text, slot):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        button.installEventFilter(self)
        return button

    @staticmethod
    def _note(text):
        label = QLabel(text)
        label.setProperty("muted", True)
        label.setWordWrap(True)
        return label

    def _form_note(self, text):
        label = self._note(text)
        self._form_notes.append(label)
        return label

    def _input(self, mode, key, label, value, *, big=False, max_length=26):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._note(label))
        edit = QLineEdit(value)
        edit.setAccessibleName(label)
        edit.setObjectName(f"{mode}_{key}")
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        edit.setMaxLength(max_length)
        if big:
            edit.setStyleSheet("font-size:21px;")
        edit.textChanged.connect(self.update_results)
        edit.returnPressed.connect(self.save_recent)
        edit.installEventFilter(self)
        layout.addWidget(edit)
        self.fields[mode][key] = edit
        return container

    def _combo(self, mode, key, accessible, items, default=None):
        combo = ConverterCombo()
        combo.setAccessibleName(accessible)
        combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        combo.setMinimumWidth(0)
        for title, value in items:
            combo.addItem(title, value)
        if default is not None:
            combo.setCurrentIndex(combo.findData(default))
        combo.currentIndexChanged.connect(self.update_results)
        self.fields[mode][key] = combo
        return combo

    def _combo_field(self, mode, key, label, items):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._note(label))
        layout.addWidget(self._combo(mode, key, label, items))
        return container

    # ── 모드·계산 ──
    def select_mode(self, mode):
        if self.copy_format.count():
            self._copy_choice[self.mode] = self.copy_format.currentIndex()
        self.mode = mode
        self.pages.setCurrentWidget(self.page_widgets[mode])
        self.mode_title.setText(MODES[mode])
        for key, button in self.mode_buttons.items():
            button.setChecked(key == mode)
        # QStackedWidget의 숨긴 페이지 최소 높이가 현재 모드에 전파되지 않게 한다.
        for key, page in self.page_widgets.items():
            page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred if key == mode else QSizePolicy.Ignored)
        self.copy_format.blockSignals(True)
        self.copy_format.clear()
        for title, value in COPY_FORMATS[mode]:
            self.copy_format.addItem(title, value)
        self.copy_format.setCurrentIndex(self._copy_choice[mode])
        self.copy_format.blockSignals(False)
        _set_property(self.result_detail, "strong", mode == "amount")
        self.update_results()

    def update_results(self, *args):
        if self._updating or not hasattr(self, "status_label"):
            return
        self._valid = False
        self._outputs = {}
        self._label = ""
        try:
            caption, main, detail, note, outputs, label = getattr(self, f"_compute_{self.mode}")()
        except NotationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            self.result_caption.setText("계산 결과")
            self.result_label.setText("—")
            self.result_detail.setText("입력을 확인하세요.")
            self.result_note.clear()
            if self.mode == "convert":
                for name_label, value_label in self.unit_rows.values():
                    value_label.set_full_text("—")
                    _set_property(name_label, "hit", False)
                    _set_property(value_label, "hit", False)
        else:
            self.error_label.hide()
            self.result_caption.setText(caption)
            self.result_label.setText(main)
            self.result_detail.setText(detail)
            self.result_note.setText(note)
            self._outputs, self._label, self._valid = outputs, label, True
        self.copy_button.setEnabled(self._valid)
        self.save_button.setEnabled(self._valid)
        self._refresh_preview()
        self._fit_result_font()

    def _compute_amount(self):
        value = parse_integer(self.fields["amount"]["value"].text())
        amount = official_amount(value)
        main = f"금{amount.digits}원"
        outputs = {"official": amount.text, "hangul": f"금{amount.hangul}원", "digits": amount.digits}
        # 표시 전용: 조·억·만 뒤에 폭 없는 공백(ZWSP)을 넣어 자리 경계에서 줄바꿈을 허용한다.
        # 복사되는 outputs/history 라벨은 amount.hangul 원본(ZWSP 없음)을 그대로 쓴다.
        hangul_display = amount.hangul.replace("조", "조\u200b").replace("억", "억\u200b").replace("만", "만\u200b")
        detail = f"(금{hangul_display}원)"
        return ("공문서 금액 표기", main, detail, f"읽기: {reading_hangul(value)} 원",
                outputs, f"금액 표기 · {main}")

    def _compute_read(self):
        controls = self.fields["read"]
        value = parse_integer(controls["value"].text())
        reading = read_number(value, controls["scope"].currentData(), controls["unit"].text())
        note = f"원래 값 {reading.original}" if reading.rounded else reading.original
        outputs = {"notation": reading.notation, "hangul": reading.hangul, "digits": f"{value:,}"}
        return ("큰 수 읽기", reading.notation, reading.hangul, note, outputs, f"큰 수 읽기 · {reading.notation}")

    def _compute_convert(self):
        controls = self.fields["convert"]
        value = parse_decimal(controls["value"].text())
        source, target = controls["from"].currentData(), controls["to"].currentData()
        places = controls["digits"].currentData()
        places = None if places < 0 else places
        values = convert_money(value, source)
        for key, (name_label, value_label) in self.unit_rows.items():
            value_label.set_full_text(exact_text(values[key]))
            _set_property(name_label, "hit", key == target)
            _set_property(value_label, "hit", key == target)
        main = format_decimal(values[target], places) + UNIT_NAMES[target]
        note = ("표시는 소수 6자리까지 · 표는 정확한 값" if places is None
                else f"표시만 소수 {places}자리 반올림 · 표는 정확한 값")
        table = "\n".join(f"{UNIT_NAMES[key]}\t{exact_text(values[key])}" for key, _name, _factor in MONEY_UNITS)
        source_text = f"{exact_text(value)}{UNIT_NAMES[source]}"
        return (f"금액 단위 환산 · {UNIT_NAMES[source]} → {UNIT_NAMES[target]}", main, f"= {source_text}",
                note, {"value": main, "table": table}, f"단위 환산 · {source_text} → {main}")

    def _refresh_preview(self):
        text = self._outputs.get(self.copy_format.currentData(), "") if self._valid else ""
        self.copy_preview_text.set_full_text(text.replace("\n", " / ") if text else "—")

    def _copy_format_changed(self, index):
        self._copy_choice[self.mode] = index
        self._refresh_preview()

    def _set_status(self, text):
        self.status_label.setText(text)
        self._status_timer.start()

    # ── 복사·기록 ──
    def copy_result(self):
        if not self._valid:
            return
        QApplication.clipboard().setText(self._outputs[self.copy_format.currentData()])
        self._set_status("복사했습니다.")

    def save_recent(self):
        if not self._valid:
            return
        entry = {"mode": self.mode, "values": self._values(self.fields[self.mode]), "label": self._label}
        self.history[:] = [old for old in self.history if old != entry]
        self.history.insert(0, deepcopy(entry))
        del self.history[12:]
        self.recent_combo.blockSignals(True)
        self.recent_combo.clear()
        self.recent_combo.addItem("최근 계산 · 선택하면 복원", None)
        for old in self.history:
            self.recent_combo.addItem(old["label"])
            self.recent_combo.setItemData(self.recent_combo.count() - 1, old["label"], Qt.ToolTipRole)
        self.recent_combo.blockSignals(False)
        self._set_status("최근 계산에 기록했습니다.")

    @staticmethod
    def _values(controls):
        return {key: control.text() if isinstance(control, QLineEdit) else control.currentIndex()
                for key, control in controls.items()}

    @staticmethod
    def _set_controls(controls, values):
        for key, value in values.items():
            control = controls[key]
            if isinstance(control, QLineEdit):
                control.setText(value)
            else:
                control.setCurrentIndex(value)

    def _restore_index(self, index):
        if index > 0:
            self.restore_recent(self.history[index - 1])

    def restore_recent(self, entry):
        entry = deepcopy(entry)
        self._updating = True
        self._set_controls(self.fields[entry["mode"]], entry["values"])
        self._updating = False
        self.select_mode(entry["mode"])
        self.focus_input()
        self._set_status("최근 계산을 복원했습니다.")

    # ── 창 ──
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
        compact = available.height() < WINDOW_HEIGHT
        margin = min(SHADOW_MARGIN, max(0, (available.width() - 420) // 2),
                     max(0, (available.height() - WINDOW_HEIGHT) // 2))
        self.header.setFixedHeight(40 if compact else 52)
        self.right_layout.setContentsMargins(12 if compact else 18, 6 if compact else 17,
                                             12 if compact else 18, 6 if compact else 16)
        self.right_layout.setSpacing(4 if compact else 7)
        self.mode_title.setVisible(not compact)
        self.status_label.setVisible(not compact)
        self.result_note.setVisible(not compact)
        self._result_min_height = 32 if compact else 43
        self.result_layout.setContentsMargins(10 if compact else 14, 6 if compact else 12,
                                              10 if compact else 14, 6 if compact else 12)
        self.copy_preview.setFixedHeight(24 if compact else 28)
        self.law_box.setText(LAW_LINES[0] if compact else "\n".join(LAW_LINES))
        for note in self._form_notes:
            note.setVisible(not compact)
            note.parentWidget().setToolTip(note.text())
        for page in self.page_widgets.values():
            page.layout().setSpacing(4 if compact else 7)
        self.body.layout().setSpacing(4 if compact else 7)
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
        self.resize(min(WINDOW_WIDTH + margin * 2, available.width()),
                    min(WINDOW_HEIGHT + margin * 2, available.height()))
        self.move(max(available.left(), min(self.x(), available.right() + 1 - self.width())),
                  max(available.top(), min(self.y(), available.bottom() + 1 - self.height())))

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
        for size in (34, 30, 26, 22, 18, 15, 13):
            font.setPixelSize(size)
            if QFontMetrics(font).horizontalAdvance(self.result_label.text()) <= self.result_label.width():
                break
        self.result_label.setFont(font)
        self.result_label.setMinimumHeight(max(self._result_min_height, QFontMetrics(font).height()))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and isinstance(watched, QAbstractButton) and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                watched.click()
            return True
        if watched in (getattr(self, "header", None), getattr(self, "title_label", None)):
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
        if hasattr(self, "result_label"):
            self._fit_result_font()
