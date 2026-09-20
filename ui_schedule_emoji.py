"""일정 본문의 선두 이모지를 편집하는 공용 선택 도우미."""
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)


SCHEDULE_CONTROL_DIAMETER = 22


SCHEDULE_EMOJIS = (
    ("📌", "중요"), ("⭐", "특별"), ("🔥", "긴급"), ("⏰", "마감"),
    ("🤝", "협의"), ("👥", "회의"), ("📞", "전화"), ("✉️", "메일"),
    ("📝", "작성"), ("📄", "문서"), ("📊", "보고"), ("🎯", "목표"),
    ("📚", "교육"), ("🚗", "출장"), ("🏠", "재택"), ("🎉", "행사"),
)


def schedule_emoji_prefix(text: str) -> str:
    """알려진 이모지와 공백 한 칸만 표식으로 인식한다."""
    return next((emoji + " " for emoji, _ in SCHEDULE_EMOJIS
                 if text.startswith(emoji + " ")), "")


def apply_schedule_emoji(edit: QLineEdit, emoji: str) -> None:
    """선두 표식만 한 번에 교체해 본문과 Undo를 보존한다."""
    if emoji and emoji not in {value for value, _ in SCHEDULE_EMOJIS}:
        raise ValueError("지원하지 않는 일정 이모지입니다.")
    old_prefix = schedule_emoji_prefix(edit.text())
    new_prefix = emoji + " " if emoji else ""
    if old_prefix == new_prefix:
        return
    # QLineEdit의 선택 범위는 Python 코드 포인트 수가 아닌 UTF-16 단위다.
    prefix_units = len(old_prefix.encode("utf-16-le")) // 2
    edit.setSelection(0, prefix_units)
    edit.insert(new_prefix)


def popup_position(anchor, size, available) -> QPoint:
    """버튼 아래(공간 부족 시 위)에 놓고 음수 좌표 작업 영역도 보존한다."""
    x = anchor.left()
    y = anchor.bottom() + 1
    if y + size.height() > available.bottom() + 1:
        y = anchor.top() - size.height()
    return QPoint(
        max(available.left(), min(x, available.right() + 1 - size.width())),
        max(available.top(), min(y, available.bottom() + 1 - size.height())),
    )


class ScheduleEmojiPopup(QWidget):
    selected = Signal(str)
    dismissed = Signal(bool)

    def __init__(self, current: str, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("scheduleEmojiPopup")
        self.setWindowOpacity(1.0)
        self._return_focus = False
        self.setStyleSheet(
            "#scheduleEmojiPopup{background:#FFFFFF;border:1px solid #CED2D8;}"
            "QPushButton{background:#FFFFFF;border:1px solid transparent;"
            "border-radius:5px;color:#1A1A1A;}"
            "QPushButton:hover,QPushButton:focus{background:#EFF6FF;"
            "border:1px solid #2563EB;}"
            "QPushButton:checked{background:#DBEAFE;border:1px solid #2563EB;}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        grid = QGridLayout()
        grid.setSpacing(4)
        outer.addLayout(grid)
        self.buttons = []
        font = QFont("Segoe UI Emoji")
        font.setPixelSize(22)
        for index, (emoji, name) in enumerate(SCHEDULE_EMOJIS):
            button = QPushButton(emoji, self)
            button.setFont(font)
            button.setFixedSize(36, 36)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setCheckable(True)
            button.setChecked(current == emoji + " ")
            button.clicked.connect(lambda checked=False, value=emoji: self._pick(value))
            grid.addWidget(button, index // 4, index % 4)
            self.buttons.append(button)
        none_button = QPushButton("없음", self)
        none_button.setFixedHeight(28)
        none_button.setAccessibleName("일정 앞 이모지 제거")
        none_button.clicked.connect(lambda: self._pick(""))
        outer.addWidget(none_button)
        self.buttons.append(none_button)
        for button in self.buttons:
            button.installEventFilter(self)
        self.adjustSize()

    def _pick(self, emoji: str) -> None:
        self._return_focus = True
        self.selected.emit(emoji)
        self.close()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in (
            Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
        ):
            # QPushButton의 기본 위/아래 처리가 격자의 열 이동을 가로채지 않게 한다.
            self.keyPressEvent(event)
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._return_focus = True
            self.close()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = self.focusWidget()
            if focused in self.buttons:
                focused.click()
        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            focused = self.focusWidget()
            index = self.buttons.index(focused) if focused in self.buttons else 0
            step = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -4, Qt.Key_Down: 4}
            self.buttons[(index + step[event.key()]) % len(self.buttons)].setFocus()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.dismissed.emit(self._return_focus)


class ScheduleEmojiButton(QPushButton):
    """입력창을 단일 원본으로 사용하며 팝업 콜백의 수명을 관리한다."""
    popup_closed = Signal()

    def __init__(self, edit: QLineEdit, can_edit, parent=None):
        super().__init__(parent)
        self.edit = edit
        self._can_edit = can_edit
        self._popup = None
        self.setFixedSize(26, 26)
        self.setToolTip("일정 이모지 선택")
        self.setAccessibleName("일정 이모지 선택")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton{color:#475569;background:transparent;"
            "border:1px solid transparent;border-radius:5px;}"
            "QPushButton:hover,QPushButton:focus{background:#EFF6FF;border-color:#2563EB;}"
        )
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_focus)
        self.clicked.connect(self.open_popup)

    def paintEvent(self, event):
        # 클릭/포커스 영역은 26px, 원의 외경은 왼쪽 색상 버튼과 같은 22px.
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor("#475569" if self.isEnabled() else "#94A3B8")
        painter.setPen(QPen(color, 1.0))
        painter.setBrush(Qt.NoBrush)
        diameter = SCHEDULE_CONTROL_DIAMETER
        x, y = (self.width() - diameter) / 2, (self.height() - diameter) / 2
        painter.drawEllipse(QRectF(x + 0.5, y + 0.5, diameter - 1, diameter - 1))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        for eye_x in (7.5, 14.5):
            painter.drawEllipse(QPointF(x + eye_x, y + 8.5), 1.15, 1.15)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(x + 6, y + 9, 10, 7), 200 * 16, 140 * 16)

    def open_popup(self) -> None:
        if not self._can_edit() or not self.isVisible() or self._popup is not None:
            return
        popup = ScheduleEmojiPopup(schedule_emoji_prefix(self.edit.text()), self)
        self._popup = popup
        popup.selected.connect(lambda emoji: self._select(popup, emoji))
        popup.dismissed.connect(lambda restore: self._dismiss(popup, restore))
        anchor = self.rect().translated(self.mapToGlobal(QPoint(0, 0)))
        popup.move(popup_position(anchor, popup.size(), self.screen().availableGeometry()))
        popup.show()
        selected = next((b for b in popup.buttons if b.isChecked()), popup.buttons[0])
        selected.setFocus(Qt.PopupFocusReason)

    def _select(self, popup, emoji: str) -> None:
        if self._popup is popup and self._can_edit():
            apply_schedule_emoji(self.edit, emoji)

    def _dismiss(self, popup, restore: bool) -> None:
        if self._popup is not popup:
            return
        self._popup = None
        popup.deleteLater()
        if restore:
            self._restore_timer.start(0)
        self.popup_closed.emit()

    def _restore_focus(self) -> None:
        if self._can_edit() and self.edit.isVisible() and self._popup is None:
            self.edit.setFocus(Qt.PopupFocusReason)

    def close_popup(self) -> None:
        self._restore_timer.stop()
        if self._popup is not None:
            popup = self._popup
            self._popup = None  # 닫히면서 발생하는 포커스 복원과 늦은 선택을 무효화.
            popup.close()
            popup.deleteLater()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
            self.open_popup()
        else:
            super().keyPressEvent(event)


class ScheduleInlineEditor(QWidget):
    finish_requested = Signal(bool)

    def __init__(self, content: str, can_edit, parent=None):
        super().__init__(parent)
        self._active = True
        self._can_edit = can_edit
        self.edit = QLineEdit(content, self)
        self.edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.edit.setStyleSheet(
            "background:#FFFFFF;border:1px solid #0078D4;"
            "border-radius:3px;padding:1px 4px;"
        )
        self.emoji_button = ScheduleEmojiButton(self.edit, self.can_edit, self)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self.emoji_button)
        row.addWidget(self.edit, 1)
        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._check_focus)
        self.edit.installEventFilter(self)
        self.emoji_button.installEventFilter(self)
        self.edit.returnPressed.connect(lambda: self.finish_requested.emit(True))
        self.emoji_button.popup_closed.connect(lambda: self._focus_timer.start(0))

    def can_edit(self) -> bool:
        return self._active and self._can_edit()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusOut:
            self._focus_timer.start(0)
        elif event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.finish_requested.emit(False)
            return True
        return super().eventFilter(obj, event)

    def _check_focus(self) -> None:
        if not self.can_edit() or self.emoji_button._popup is not None:
            return
        focused = QApplication.focusWidget()
        if focused is not None and (focused is self or self.isAncestorOf(focused)):
            return
        self.finish_requested.emit(True)

    def deactivate(self) -> None:
        self._active = False
        self._focus_timer.stop()
        self.emoji_button.close_popup()
