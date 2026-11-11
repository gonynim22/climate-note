"""일정 본문의 선두 이모지를 편집하는 공용 선택 도우미와 일정 인라인 편집기(색 원 포함)."""
import logging

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

import schedule_rules as rules
from schedule_rules import ScheduleOptions
# 지름·팝업 위치는 세부 설정 모듈로 옮겼고, 기존 import 경로를 위해 이 이름으로 다시 내보낸다.
from ui_schedule_options import (  # noqa: F401
    SCHEDULE_CONTROL_DIAMETER, ElidedLabel, ScheduleOptionsButton, popup_position,
)

_logger = logging.getLogger("app_error")


SCHEDULE_EMOJIS = (
    ("📌", "중요"), ("⭐", "특별"), ("🔥", "긴급"), ("⏰", "마감"),
    ("🤝", "협의"), ("👥", "회의"), ("📞", "전화"), ("✉️", "메일"),
    ("📝", "작성"), ("📄", "문서"), ("📊", "보고"), ("🎯", "목표"),
    ("📚", "교육"), ("🚗", "출장"), ("🏠", "재택"), ("🎉", "행사"),
)


COLOR_BUTTON_TOOLTIP_TEXT = "누를 때마다 다음 색"


def next_schedule_color(current, slots):
    """3슬롯 순서(1→2→3→1)로 다음 저장색. 팔레트 밖 색(가져온 사용자 색)은 1번 슬롯부터 시작한다.

    슬롯은 대소문자를 가리지 않고 비교한다(`database.schedule_display_color`와 같은 규칙).
    """
    keys = [str(slot).upper() for slot in slots]
    key = str(current or "").strip().upper()
    if key in keys:
        return slots[(keys.index(key) + 1) % len(slots)]
    return slots[0]


class SmoothCircleButton(QPushButton):
    """일정 색 원(지름은 부르는 쪽이 정한다). 입력줄과 인라인 편집기가 같은 모양을 쓴다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_color = QColor("white")
        self._is_hovered = False
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, hex_color: str):
        self._bg_color = QColor(hex_color)
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self._bg_color))
        pen = QPen(QColor("black"))
        if self._is_hovered:
            pen.setWidth(2)
            margin = 1.0
        else:
            pen.setWidth(1)
            margin = 0.5
        painter.setPen(pen)
        rect = QRectF(self.rect())
        painter.drawEllipse(rect.adjusted(margin, margin, -margin, -margin))


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
    """[스마일][시계][본문] 한 줄 + 세부 설정 요약 한 줄. 두 팝업까지 하나의 편집 영역이다.

    색 원(`color_button`, B안 2026-11-10)도 편집 영역이다. 편집기가 만들지만 화면에서는 행이
    줄 앞 색 점 자리에 놓는다. 누를 때마다 3슬롯 순서로 다음 색이 되고 설정 표시색으로 보인다.
    """
    finish_requested = Signal(bool)
    summary_changed = Signal()

    def __init__(self, content: str, can_edit, parent=None, *,
                 options: ScheduleOptions | None = None, start: str = "", occurrence: str = "",
                 occurrence_only=False, color=None, palette=(), color_names=None):
        super().__init__(parent)
        self._active = True
        self._can_edit = can_edit
        self._occurrence_only = occurrence_only
        self._color = color
        palette = tuple(palette)  # (저장 슬롯, 표시색) 쌍. zip도 받으므로 한 번만 읽는다.
        self._color_slots = tuple(slot for slot, _display in palette)
        self._display_by_slot = {str(slot).upper(): display for slot, display in palette}
        self._color_names = {str(key).upper(): name for key, name in (color_names or {}).items()}
        self.edit = QLineEdit(content, self)
        self.edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        # 입력칸은 남는 폭을 다 쓰되 줄에 폭을 요구하지 않는다. 요구하면 줄 앞 색 원(22px)까지
        # 더해 편집 줄이 목록보다 넓어지고, 가로 스크롤바가 보이는 높이를 줄여 요약 줄을 가린다.
        self.edit.setSizePolicy(QSizePolicy.Ignored, self.edit.sizePolicy().verticalPolicy())
        self.edit.setStyleSheet(
            "background:#FFFFFF;border:1px solid #0078D4;"
            "border-radius:3px;padding:1px 4px;"
        )
        self.emoji_button = ScheduleEmojiButton(self.edit, self.can_edit, self)
        self.options_button = ScheduleOptionsButton(self.edit, self.can_edit, self,
                                                    occurrence_only=occurrence_only)
        self.options_button.set_context(start, occurrence)
        self.options_button.set_options(options or ScheduleOptions())
        self.summary_label = ElidedLabel("", self)
        # 요약은 그릴 때 말줄임한다(전체 문장은 툴팁). 전체 글자 폭을 요구하면 반복 일정의 긴 요약이
        # 중간·크게 목록(287px)보다 넓어져 가로 스크롤이 생겼다(v4.9 이전부터, 2026-11-10 확인).
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.summary_label.setObjectName("scheduleEditorSummary")
        self.summary_label.setStyleSheet("color:#5B6577;font-size:11px;background:transparent;")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self.emoji_button)
        row.addWidget(self.options_button)
        row.addWidget(self.edit, 1)
        column.addLayout(row)
        column.addWidget(self.summary_label)
        self.color_button = None
        self.color_slot = None
        if color is not None and self._color_slots:
            # 원은 작은 자리(color_slot)에 담아 편집기 레이아웃 밖에 둔다. 부르는 쪽이 줄 앞 색 점
            # 자리에 놓기 전까지 숨긴다. 위 여백은 원을 26px 입력칸 줄 가운데에 맞춘다.
            self.color_slot = QWidget(self)
            self.color_slot.setVisible(False)
            # 원은 클릭 포커스를 받지 않는다. 그러면 Qt가 부모를 거슬러 올라가 클릭 포커스를 줄
            # 위젯을 찾는데(일정 목록이 받아 편집이 끝난다), 이 자리가 먼저 받아 입력칸에 넘긴다.
            self.color_slot.setFocusPolicy(Qt.ClickFocus)
            self.color_slot.setFocusProxy(self.edit)
            self.color_slot.setFixedWidth(SCHEDULE_CONTROL_DIAMETER)
            slot_layout = QVBoxLayout(self.color_slot)
            slot_layout.setContentsMargins(
                0, max(0, (self.emoji_button.height() - SCHEDULE_CONTROL_DIAMETER) // 2), 0, 0)
            slot_layout.setSpacing(0)
            self.color_button = SmoothCircleButton(self.color_slot)
            self.color_button.setFixedSize(SCHEDULE_CONTROL_DIAMETER, SCHEDULE_CONTROL_DIAMETER)
            # 마우스로 눌러도 글자 입력 포커스를 가져가지 않는다. 키보드는 Tab으로 와서 Space.
            self.color_button.setFocusPolicy(Qt.TabFocus)
            self.color_button.setToolTip(COLOR_BUTTON_TOOLTIP_TEXT)
            self.color_button.clicked.connect(self._cycle_color)
            self.color_button.installEventFilter(self)
            slot_layout.addWidget(self.color_button)
            slot_layout.addStretch(1)
            self._sync_color_button()
        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._check_focus)
        self.edit.installEventFilter(self)
        self.emoji_button.installEventFilter(self)
        self.options_button.installEventFilter(self)
        self.edit.returnPressed.connect(lambda: self.finish_requested.emit(True))
        self.emoji_button.popup_closed.connect(lambda: self._focus_timer.start(0))
        self.options_button.popup_closed.connect(lambda: self._focus_timer.start(0))
        self.options_button.options_changed.connect(lambda _options: self._sync_summary())
        self._sync_summary()

    def options(self) -> ScheduleOptions:
        return self.options_button.options()

    def color(self):
        """저장할 색(3슬롯 원래 값, 누르지 않은 팔레트 밖 색은 그대로)."""
        return self._color

    def _cycle_color(self):
        if self.color_button is None or not self.can_edit():
            return
        self._color = next_schedule_color(self._color, self._color_slots)
        self._sync_color_button()

    def _sync_color_button(self):
        # 슬롯이면 설정의 표시색, 팔레트 밖 색이면 그 색 그대로 보인다.
        display = self._display_by_slot.get(str(self._color or "").strip().upper(), self._color)
        self.color_button.set_color(display)
        name = self._color_names.get(str(display).strip().upper(), "사용자 지정 색")
        self.color_button.setAccessibleName(f"일정 색상 {name} — {COLOR_BUTTON_TOOLTIP_TEXT}")

    def _sync_summary(self) -> None:
        options = self.options()
        start = self.options_button.start_date()
        summary = ""
        if start and not options.is_default:
            try:
                summary = rules.options_summary(start, options)
            except ValueError as exc:
                # 일정 내용(날짜·시각 값)은 남기지 않고 예외 종류만 기록한다.
                _logger.warning("일정 편집 요약 실패: %s", type(exc).__name__)
                summary = ""
            if summary and options.repeat_rule:
                summary += " · 모든 날에 적용"
        if self._occurrence_only:
            summary = "이 날만 수정" + (" · " + summary if summary else "")
        self.summary_label.setText(summary)
        self.summary_label.setToolTip(summary)
        self.summary_label.setVisible(bool(summary))
        self.summary_changed.emit()

    def can_edit(self) -> bool:
        return self._active and self._can_edit()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusOut:
            self._focus_timer.start(0)
        elif event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.finish_requested.emit(False)
            return True
        elif (event.type() == QEvent.KeyPress and obj is self.color_button
              and event.key() in (Qt.Key_Return, Qt.Key_Enter)):
            self.finish_requested.emit(True)  # 색 원에서도 Enter는 입력칸과 같이 저장이다.
            return True
        return super().eventFilter(obj, event)

    def _check_focus(self) -> None:
        if (not self.can_edit() or self.emoji_button._popup is not None
                or self.options_button._popup is not None):
            return
        focused = QApplication.focusWidget()
        # 색 원은 행 앞에 놓여 편집기의 자손이 아니므로 따로 본다.
        if focused is not None and (focused is self or self.isAncestorOf(focused)
                                    or focused is self.color_button):
            return
        self.finish_requested.emit(True)

    def deactivate(self) -> None:
        self._active = False
        self._focus_timer.stop()
        self.emoji_button.close_popup()
        self.options_button.close_popup()
