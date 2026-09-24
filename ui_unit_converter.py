"""개발자 제공 단위 환산기. 계산·최근 기록은 실행 중 메모리에만 존재한다."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from unit_converter import (
    CATEGORIES, CATEGORY_BY_ID, GROUP_COLORS, ConversionConditions, RecentHistory,
    convert, crosses_concentration_basis, format_number, parse_number,
)
from ui_conversion_conditions import ConversionConditionsPanel, condition_summary
from ui_converter_combo import ConverterCombo

CONVERTER_WIDTH = 440
CONVERTER_HEIGHT = 580
CONVERTER_SHADOW_MARGIN = 24


def result_text(category_id, from_id, to_id, value, conditions):
    approximate = crosses_concentration_basis(category_id, from_id, to_id) and (
        category_id == "gas_fraction" or conditions.water_approximation)
    return ("≈ " if approximate else "") + format_number(value)


class UnitCombo(ConverterCombo):
    """닫힌 상태에는 기호, 목록에는 전체 단위 이름과 정의를 표시한다."""
    def display_text(self):
        return self.currentData(Qt.UserRole + 1) or ""

    def showPopup(self):
        screen = self.screen()
        width = max(self.width(), min(320, screen.availableGeometry().width()))
        self.view().setMinimumWidth(width)
        super().showPopup()


class UnitConverterWindow(QWidget):
    shadow_margin = CONVERTER_SHADOW_MARGIN

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("unitConverter")
        self.setWindowTitle("단위 환산기 · 기후노트")
        self.setAccessibleName("단위 환산기")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(1.0)
        self.resize(CONVERTER_WIDTH + 2 * self.shadow_margin, CONVERTER_HEIGHT + 2 * self.shadow_margin)
        self.category_id = "len"
        self.history = RecentHistory()
        self._drag_origin = None
        self._row_widgets = {}
        self._result = None
        self._conditions = ConversionConditions()
        self._selecting_category = False
        self._restoring_recent = False
        self.setStyleSheet("""
            QWidget { color:#292C33; }
            QWidget#converterSurface { background:#FDFDFB; border-radius:16px; }
            QWidget#converterBody { background:#FDFDFB; border-top-right-radius:16px; border-bottom-right-radius:16px; }
            QWidget#converterRail { background:#23252B; border-top-left-radius:16px; border-bottom-left-radius:16px; }
            QScrollArea { background:transparent; border:0; }
            QScrollArea > QWidget > QWidget { background:transparent; }
            QScrollBar:vertical { width:5px; background:transparent; margin:0; }
            QScrollBar:horizontal { height:5px; background:transparent; margin:0; }
            QScrollBar::handle { background:#CDD0D2; border-radius:2px; min-height:18px; min-width:18px; }
            QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
            QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
            QToolButton#converterClose, QToolButton#converterSwap { background:transparent; border:1px solid transparent; border-radius:6px; }
            QToolButton#converterClose:hover, QToolButton#converterClose:focus,
            QToolButton#converterSwap:hover, QToolButton#converterSwap:focus { background:#EDF1F5; border-color:#B4C5DB; }
            QPushButton#otherUnit { background:transparent; border:1px solid transparent; border-radius:6px; }
            QPushButton#otherUnit:hover, QPushButton#otherUnit:focus { background:#F0F2F4; border-color:#CDD5E0; }
            QPushButton#recentCalculation { background:#FFFFFF; border:1px solid #E1E3DF; border-radius:6px; padding:4px 7px; font-size:11px; color:#5C616A; }
            QPushButton#recentCalculation:hover, QPushButton#recentCalculation:focus { border-color:#8099BB; color:#33549E; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.shadow_margin, self.shadow_margin, self.shadow_margin, self.shadow_margin)
        self.surface = QWidget(self)
        self.surface.setObjectName("converterSurface")
        self.surface.setAttribute(Qt.WA_StyledBackground)
        outer.addWidget(self.surface)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.surface.setGraphicsEffect(shadow)
        root = QHBoxLayout(self.surface)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        rail = QWidget(self.surface)
        self.category_rail = rail
        rail.setObjectName("converterRail")
        rail.setFixedWidth(132)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(6, 12, 5, 8)
        rail_layout.setSpacing(6)
        brand = QLabel("▪  단위 환산", rail)
        brand.setStyleSheet("color:#F4F5F2;font-size:14px;font-weight:bold;padding:0 2px 5px;")
        rail_layout.addWidget(brand)
        self.category_scroll = self._scroll(rail)
        category_content = QWidget()
        categories_layout = QVBoxLayout(category_content)
        categories_layout.setContentsMargins(0, 0, 1, 0)
        categories_layout.setSpacing(0)
        self.category_buttons = {}
        for group, (cover, _, _) in GROUP_COLORS.items():
            group_label = QLabel(group)
            group_label.setStyleSheet("color:#A1A5AF;font-size:12px;padding:6px 5px 2px;")
            categories_layout.addWidget(group_label)
            for category in (c for c in CATEGORIES if c.group == group):
                button = QToolButton(category_content)
                button.setCheckable(True)
                button.setFixedHeight(28)
                button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                button.setAccessibleName(category.name)
                button.setToolTip(category.name)
                button.setCursor(Qt.PointingHandCursor)
                button.installEventFilter(self)
                button.setStyleSheet(
                    "QToolButton{border:1px solid transparent;border-radius:6px;background:transparent;}"
                    "QToolButton:hover{background:#343740;}"
                    f"QToolButton:checked{{background:{cover};}}"
                    "QToolButton:focus{border-color:#D9E5F9;}"
                    "QLabel{color:#ECEEF2;background:transparent;}"
                )
                row = QHBoxLayout(button)
                row.setContentsMargins(3, 0, 3, 0)
                row.setSpacing(3)
                symbol = QLabel(category.symbol)
                symbol.setFixedWidth(40)
                symbol.setAlignment(Qt.AlignCenter)
                symbol.setStyleSheet("font-size:12px;font-weight:bold;")
                name = QLabel(category.name)
                name.setStyleSheet("font-size:13px;")
                for label in (symbol, name):
                    label.setAttribute(Qt.WA_TransparentForMouseEvents)
                    row.addWidget(label)
                row.addStretch()
                button.clicked.connect(lambda checked=False, cid=category.id: self.select_category(cid))
                categories_layout.addWidget(button)
                self.category_buttons[category.id] = button
        categories_layout.addStretch()
        self.category_scroll.setWidget(category_content)
        rail_layout.addWidget(self.category_scroll)
        root.addWidget(rail)

        body = QWidget(self.surface)
        body.setObjectName("converterBody")
        body.setMinimumHeight(520)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.header = QWidget(body)
        self.header.setFixedHeight(44)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(14, 4, 8, 2)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size:14px;font-weight:bold;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.close_button = QToolButton()
        self.close_button.setObjectName("converterClose")
        self.close_button.setText("×")
        self.close_button.setStyleSheet("font-size:19px;")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.setAccessibleName("단위 환산기 닫기")
        self.close_button.clicked.connect(self.close)
        self.close_button.installEventFilter(self)
        header_layout.addWidget(self.close_button)
        for target in (self.header, self.title_label):
            target.installEventFilter(self)
        body_layout.addWidget(self.header)
        self.conditions_panel = ConversionConditionsPanel(body)
        self.basis_label = self.conditions_panel.summary
        body_layout.addWidget(self.conditions_panel)

        fields = QWidget(body)
        fields_layout = QVBoxLayout(fields)
        fields_layout.setContentsMargins(16, 3, 16, 0)
        fields_layout.setSpacing(6)
        self.input = QLineEdit("100")
        self.input.setObjectName("converterInput")
        self.input.setAccessibleName("환산할 숫자")
        self.input.setMaxLength(96)
        self.input.setStyleSheet("QLineEdit{background:transparent;border:0;font-size:28px;padding:0;color:#292C33;}")
        self.input.setFixedHeight(42)
        self.from_combo = UnitCombo()
        self.from_combo.setAccessibleName("입력 단위")
        self.from_card = self._card("FROM", self.from_combo, self.input)
        fields_layout.addWidget(self.from_card)
        swap_row = QHBoxLayout()
        swap_row.addStretch()
        self.swap_button = QToolButton()
        self.swap_button.setObjectName("converterSwap")
        self.swap_button.setText("⇅")
        self.swap_button.setStyleSheet("font-size:18px;")
        self.swap_button.setFixedSize(32, 30)
        self.swap_button.setAccessibleName("입력과 결과 단위 바꾸기")
        self.swap_button.setToolTip("입력과 결과 바꾸기")
        self.swap_button.clicked.connect(self.swap)
        self.swap_button.installEventFilter(self)
        swap_row.addWidget(self.swap_button)
        swap_row.addStretch()
        fields_layout.addLayout(swap_row)
        self.result_label = QLabel("—")
        self.result_label.setObjectName("converterResult")
        self.result_label.setAccessibleName("환산 결과")
        self.result_label.setFixedHeight(42)
        self.result_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.result_label.setFocusPolicy(Qt.StrongFocus)
        self.to_combo = UnitCombo()
        self.to_combo.setAccessibleName("결과 단위")
        self.to_card = self._card("TO", self.to_combo, self.result_label)
        fields_layout.addWidget(self.to_card)
        body_layout.addWidget(fields)
        self.status_label = QPushButton()
        self.status_label.setAccessibleName("환산 기준 설명")
        self.status_label.clicked.connect(self.conditions_panel.toggle.click)
        self.status_label.installEventFilter(self)
        self.status_label.setFixedHeight(23)
        self.status_label.setContentsMargins(14, 0, 10, 0)
        self.status_label.setStyleSheet("color:#7B818C;font-size:11px;")
        body_layout.addWidget(self.status_label)
        heading = QLabel("다른 단위")
        heading.setStyleSheet("color:#898E97;font-size:11px;font-weight:bold;padding:0 16px;")
        heading.setFixedHeight(20)
        body_layout.addWidget(heading)
        self.other_scroll = self._scroll(body)
        self.other_content = QWidget()
        self.other_layout = QVBoxLayout(self.other_content)
        self.other_layout.setContentsMargins(8, 0, 8, 5)
        self.other_layout.setSpacing(1)
        self.other_scroll.setWidget(self.other_content)
        body_layout.addWidget(self.other_scroll, 1)

        recent = QWidget(body)
        recent.setFixedHeight(70)
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(10, 5, 10, 6)
        recent_layout.setSpacing(2)
        recent_title = QLabel("최근")
        recent_title.setStyleSheet("font-size:11px;color:#898E97;font-weight:bold;")
        recent_layout.addWidget(recent_title)
        self.recent_scroll = self._scroll(recent, horizontal=True)
        self.recent_content = QWidget()
        self.recent_layout = QHBoxLayout(self.recent_content)
        self.recent_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(5)
        self.recent_scroll.setWidget(self.recent_content)
        self.recent_scroll.setToolTip("Enter로 최근 기록에 추가 · 앱을 종료하면 기록이 사라집니다.")
        recent_layout.addWidget(self.recent_scroll)
        body_layout.addWidget(recent)
        self.body_scroll = self._scroll(self.surface)
        self.body_scroll.setWidget(body)
        root.addWidget(self.body_scroll, 1)
        self.input.textChanged.connect(self.update_results)
        self.input.returnPressed.connect(self.save_recent)
        self.from_combo.currentIndexChanged.connect(self.update_results)
        self.to_combo.currentIndexChanged.connect(self.update_results)
        self.conditions_panel.changed.connect(self.update_results)
        for button in (self.conditions_panel.toggle, self.conditions_panel.reset_button):
            button.installEventFilter(self)
        self.select_category("len")
        self._render_recent()

    @staticmethod
    def _scroll(parent, horizontal=False):
        scroll = QScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded if horizontal else Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff if horizontal else Qt.ScrollBarAsNeeded)
        return scroll

    @staticmethod
    def _card(caption, combo, value):
        card = QWidget()
        card.setObjectName("conversionCard")
        card.setFixedHeight(92)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 7)
        layout.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(5)
        label = QLabel(caption)
        label.setStyleSheet("font-size:11px;color:#858A94;font-weight:bold;")
        row.addWidget(label)
        row.addStretch()
        combo.setMinimumWidth(80)
        combo.setMaximumWidth(168)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(combo, 1)
        layout.addLayout(row)
        layout.addWidget(value)
        return card

    @property
    def category(self):
        return CATEGORY_BY_ID[self.category_id]

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()

    def select_category(self, category_id):
        self._selecting_category = True
        category = CATEGORY_BY_ID[category_id]
        self.category_id = category_id
        self.title_label.setText(category.name)
        self.title_label.setToolTip(category.note)
        self.conditions_panel.set_category(category_id)
        for cid, button in self.category_buttons.items():
            button.setChecked(cid == category_id)
        self.category_scroll.ensureWidgetVisible(self.category_buttons[category_id])
        _, ink, soft = GROUP_COLORS[category.group]
        self.from_card.setStyleSheet("QWidget#conversionCard{background:#F1F3F5;border-radius:10px;}")
        self.to_card.setStyleSheet(f"QWidget#conversionCard{{background:{soft};border:1px solid {soft};border-radius:10px;}}")
        self.result_label.setStyleSheet(f"color:{ink};font-weight:bold;")
        for combo, default in zip((self.from_combo, self.to_combo), category.defaults):
            combo.blockSignals(True)
            combo.clear()
            for unit in category.units:
                combo.addItem(f"{unit.label} · {unit.symbol}", unit.id)
                index = combo.count()-1
                combo.setItemData(index, unit.symbol, Qt.UserRole+1)
                combo.setItemData(index, f"{unit.label} · {unit.symbol}\n{category.note}", Qt.ToolTipRole)
            combo.setCurrentIndex(combo.findData(default))
            combo.blockSignals(False)
        self._clear_layout(self.other_layout)
        self._row_widgets = {}
        for unit in category.units:
            button = QPushButton()
            button.setObjectName("otherUnit")
            button.setFixedHeight(31)
            button.setAccessibleName(f"결과 단위를 {unit.label}로 변경")
            button.setCursor(Qt.PointingHandCursor)
            button.installEventFilter(self)
            row = QHBoxLayout(button)
            row.setContentsMargins(6, 0, 6, 0)
            row.setSpacing(5)
            name, value = QLabel(unit.symbol), QLabel("—")
            name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            name.setStyleSheet("font-size:12px;color:#646A76;")
            value.setStyleSheet("font-size:12px;font-weight:bold;")
            for label in (name, value):
                label.setAttribute(Qt.WA_TransparentForMouseEvents)
            row.addWidget(name, 1)
            row.addWidget(value)
            button.clicked.connect(lambda checked=False, uid=unit.id: self.to_combo.setCurrentIndex(self.to_combo.findData(uid)))
            self.other_layout.addWidget(button)
            self._row_widgets[unit.id] = (button, value)
        self.other_layout.addStretch()
        self._selecting_category = False
        self.update_results()

    def update_results(self):
        if self._selecting_category or self._restoring_recent:
            return
        from_id, to_id = self.from_combo.currentData(), self.to_combo.currentData()
        if not from_id or not to_id:
            return
        self._result = None
        error = ""
        number = None
        self.conditions_panel.set_units(from_id, to_id)
        self._conditions = None
        try:
            self._conditions = self.conditions_panel.conditions()
            number = parse_number(self.input.text())
            if number is not None:
                self._result = convert(self.category_id, from_id, to_id, number, conditions=self._conditions)
        except ValueError as exc:
            error = str(exc)
        self.result_label.setText(result_text(self.category_id, from_id, to_id, self._result, self._conditions)
                                 if self._result is not None else "—")
        self.result_label.setToolTip(repr(self._result) if self._result is not None else error)
        self._fit_result_font()
        self.swap_button.setEnabled(self._result is not None)
        message = error or ("숫자를 입력하세요" if number is None else "환산 기준 ⓘ")
        metrics = self.status_label.fontMetrics()
        self.status_label.setText(metrics.elidedText(message, Qt.ElideRight, max(50, self.status_label.width()-24)))
        self.status_label.setToolTip(error or self.category.note)
        self.status_label.setAccessibleDescription(error or self.category.note)
        self.status_label.setStyleSheet(f"color:{'#BB4040' if error else '#7B818C'};font-size:11px;"
                                       "background:transparent;border:0;text-align:left;padding-left:14px;")
        for combo in (self.from_combo, self.to_combo):
            combo.setToolTip(combo.currentData(Qt.ToolTipRole))
        for unit in self.category.units:
            button, label = self._row_widgets[unit.id]
            button.setVisible(unit.id not in (from_id, to_id))
            text = "—"
            detail = ""
            if number is not None and self._conditions is not None:
                try:
                    value = convert(self.category_id, from_id, unit.id, number, conditions=self._conditions)
                    text = result_text(self.category_id, from_id, unit.id, value, self._conditions)
                    detail = repr(value)
                except ValueError as exc:
                    detail = str(exc)
            label.setText(text)
            button.setToolTip(f"{unit.label} · {unit.symbol}\n{detail}")

    def _fit_result_font(self):
        font = QFont(self.font())
        font.setBold(True)
        for size in (28, 25, 22, 19, 16, 14):
            font.setPixelSize(size)
            if QFontMetrics(font).horizontalAdvance(self.result_label.text()) <= self.result_label.width():
                break
        self.result_label.setFont(font)

    def swap(self):
        if self._result is None:
            return
        value = repr(self._result)
        source, target = self.from_combo.currentIndex(), self.to_combo.currentIndex()
        for combo, index in ((self.from_combo, target), (self.to_combo, source)):
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        self.input.setText(value)
        self.update_results()

    def save_recent(self):
        if self._result is None:
            return
        self.history.add(self.category_id, self.from_combo.currentData(), self.to_combo.currentData(), self.input.text(),
                         conditions=self._conditions)
        self._render_recent()

    def _render_recent(self):
        self._clear_layout(self.recent_layout)
        if not self.history.items:
            label = QLabel("Enter로 최근 기록에 추가")
            label.setStyleSheet("color:#8A909A;font-size:11px;")
            self.recent_layout.addWidget(label)
        for entry in self.history.items:
            category = CATEGORY_BY_ID[entry.category_id]
            source, target = category.unit(entry.from_id), category.unit(entry.to_id)
            result = convert(entry.category_id, source.id, target.id, entry.value, conditions=entry.conditions)
            rendered = result_text(entry.category_id, source.id, target.id, result, entry.conditions)
            text = f"{format_number(entry.value)} {source.symbol} → {rendered} {target.symbol}"
            if entry.category_id == "water":
                text += " · 물 기준" if entry.conditions.water_approximation else f" · 밀도 {format_number(entry.conditions.density_kg_l)}"
            elif entry.category_id == "gas_fraction" and entry.conditions.molar_mass is not None:
                text += f" · {entry.conditions.gas_id or '기체'}"
            elif entry.conditions.temperature_difference:
                text += " · 온도차"
            button = QPushButton(text)
            button.setObjectName("recentCalculation")
            button.installEventFilter(self)
            button.setToolTip(f"{category.name} · {source.label} → {target.label}\n{entry.text}\n"
                              + condition_summary(entry.category_id, entry.conditions))
            button.clicked.connect(lambda checked=False, r=entry: self.restore_recent(r))
            self.recent_layout.addWidget(button)
            button.ensurePolished()
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(text) + 20)
        self.recent_layout.addStretch()

    def restore_recent(self, entry):
        self._restoring_recent = True
        try:
            self.select_category(entry.category_id)
            self.conditions_panel.restore(entry.conditions)
            self.from_combo.setCurrentIndex(self.from_combo.findData(entry.from_id))
            self.to_combo.setCurrentIndex(self.to_combo.findData(entry.to_id))
            self.input.setText(entry.text)
        finally:
            self._restoring_recent = False
        self.update_results()
        self.input.setFocus()

    def fit_to_screen(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        # 좁은 화면에서는 내용의 최소 너비를 먼저 확보하고 그림자 여백/blur를 줄인다.
        content_width = (self.category_rail.width() + self.body_scroll.widget().minimumSizeHint().width()
                         + self.body_scroll.verticalScrollBar().sizeHint().width())
        margin = min(self.shadow_margin, max(0, (available.width()-content_width)//2))
        self.layout().setContentsMargins(margin, margin, margin, margin)
        shadow = self.surface.graphicsEffect()
        shadow.setBlurRadius(max(0, margin-4))
        shadow.setOffset(0, min(4, margin))
        shadow.setEnabled(margin > 0)
        self.resize(min(CONVERTER_WIDTH + 2 * margin, available.width()),
                    min(CONVERTER_HEIGHT + 2 * margin, available.height()))
        self.move(
            max(available.left(), min(self.x(), available.right()+1-self.width())),
            max(available.top(), min(self.y(), available.bottom()+1-self.height())),
        )

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.KeyPress and isinstance(watched, QAbstractButton)
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)):
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
        self.from_combo.hidePopup()
        self.to_combo.hidePopup()
        self.conditions_panel.gas_picker.hidePopup()
        self.conditions_panel.temperature_mode.hidePopup()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "result_label"):
            self._fit_result_font()
