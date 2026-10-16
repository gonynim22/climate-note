"""일정 세부 설정(시각·알림·기간·반복) 화면 부품 (v4.1).

입력줄과 더블클릭 편집기가 함께 쓴다. 카드는 이모지 팝업과 같은 수명 규칙을 따른다:
한 번에 하나, 닫히면 deleteLater, 늦게 도착한 신호는 무시, 포커스 복원은 버튼 소유 타이머.
카드 안에서는 다른 팝업(드롭다운·QCalendarWidget·메뉴)을 띄우지 않는다.
"""
import calendar
import logging
from dataclasses import replace
from datetime import date, timedelta

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

import holidays
import schedule_rules as rules
from popup_border_fix import remove_dwm_border
from schedule_rules import ScheduleOptions

_logger = logging.getLogger("app_error")

SCHEDULE_CONTROL_DIAMETER = 22
SHADOW_MARGIN = 16
CARD_WIDTH = 330
ICON_COLOR = "#475569"
ACTIVE_COLOR = "#2563EB"
TIMED_ALARM_CHOICES = ((None, "없음"), (0, "정시"), (10, "10분 전"),
                       (30, "30분 전"), (60, "1시간 전"), (1440, "하루 전"))
ALLDAY_ALARM_CHOICES = ((None, "없음"), (0, "당일 오전 9시"), (1440, "하루 전 오전 9시"))
REPEAT_CHOICES = (("", "안 함"), ("daily", "매일"), ("weekdays", "평일"),
                  ("weekly", "매주"), ("monthly", "매월"), ("yearly", "매년"))
REPEAT_ONLY_ONE_DAY = "반복 일정은 하루만 고를 수 있습니다"
PERIOD_NO_REPEAT = "여러 날 일정은 반복할 수 없습니다"

CARD_QSS = (
    "QFrame#scheduleOptionsCard{background:#FFFFFF;border:1px solid #D9E1EC;border-radius:12px;}"
    "#scheduleOptionsCard QLabel{background:transparent;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsTitle{color:#172B4D;font-size:13px;font-weight:bold;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsRowLabel{color:#64748B;font-size:12px;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsNote{color:#B45309;font-size:11px;}"
    "#scheduleOptionsCard QLabel#scheduleOptionsHint{color:#94A3B8;font-size:11px;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]{background:#FFFFFF;border:1px solid #CBD5E1;"
    "border-radius:13px;color:#334155;font-size:12px;padding:0px 9px;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:hover{background:#F8FAFC;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:checked{background:#EFF6FF;"
    "border:1px solid #2563EB;color:#1D4ED8;font-weight:bold;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:disabled{background:#F8FAFC;"
    "border:1px solid #E2E8F0;color:#A3ACB9;}"
    "#scheduleOptionsCard QPushButton[segment=\"true\"]:focus{border:2px solid #2563EB;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsCaption{background:transparent;border:0px;"
    "color:#334155;font-size:12px;text-align:left;padding:0px;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsCaption:hover,"
    "#scheduleOptionsCard QPushButton#scheduleOptionsCaption:focus{color:#1D4ED8;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsClear{background:transparent;border:0px;"
    "color:#64748B;font-size:12px;padding:0px 2px;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsClear:hover,"
    "#scheduleOptionsCard QPushButton#scheduleOptionsClear:focus{color:#B91C1C;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsDone{background:#2563EB;border:1px solid #2563EB;"
    "border-radius:6px;color:#FFFFFF;font-size:12px;font-weight:bold;padding:0px 14px;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsDone:hover{background:#1D4ED8;}"
    "#scheduleOptionsCard QPushButton#scheduleOptionsDone:focus{border:2px solid #1E3A8A;}"
    "#scheduleOptionsCard QLineEdit#scheduleOptionsTime{background:#FFFFFF;border:1px solid #CBD5E1;"
    "border-radius:6px;color:#172B4D;font-size:12px;padding:0px 6px;}"
    "#scheduleOptionsCard QLineEdit#scheduleOptionsTime:focus{border:2px solid #2563EB;}"
    "#scheduleOptionsCard QLineEdit#scheduleOptionsTime[invalid=\"true\"]{border:2px solid #DC2626;}"
    "#scheduleOptionsCard QLabel#scheduleMiniTitle{color:#172B4D;font-size:12px;font-weight:bold;}"
    "#scheduleOptionsCard QLabel#scheduleMiniWeekday{color:#64748B;font-size:11px;}"
    "#scheduleOptionsCard QLabel#scheduleMiniWeekday[tone=\"sun\"]{color:#D32F2F;}"
    "#scheduleOptionsCard QLabel#scheduleMiniWeekday[tone=\"sat\"]{color:#1565C0;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniNav{background:transparent;border:0px;"
    "border-radius:4px;color:#475569;font-size:14px;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniNav:hover,"
    "#scheduleOptionsCard QPushButton#scheduleMiniNav:focus{background:#EFF6FF;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay{background:transparent;border:0px;"
    "border-radius:4px;color:#1A1A1A;font-size:11px;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[tone=\"sun\"]{color:#D32F2F;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[tone=\"sat\"]{color:#1565C0;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay:hover{background:#EFF6FF;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay:focus{border:1px solid #2563EB;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[role=\"in\"]{background:#DBEAFE;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay[role=\"end\"]{background:#2563EB;"
    "color:#FFFFFF;font-weight:bold;}"
    "#scheduleOptionsCard QPushButton#scheduleMiniDay:disabled{background:transparent;color:#CBD5E1;}"
)


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


def draw_icon(painter: QPainter, name: str, rect: QRectF, color) -> None:
    """작은 선 아이콘을 rect(정사각형 권장) 안에 그린다. 그림 파일 없이 QPainter만 쓴다."""
    size = min(rect.width(), rect.height())
    left = rect.x() + (rect.width() - size) / 2
    top = rect.y() + (rect.height() - size) / 2

    def at(fx: float, fy: float) -> QPointF:
        return QPointF(left + fx * size, top + fy * size)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), max(1.0, size / 11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if name == "clock":
        painter.drawEllipse(QRectF(at(0.08, 0.08), at(0.92, 0.92)))
        painter.drawLine(at(0.5, 0.5), at(0.5, 0.25))
        painter.drawLine(at(0.5, 0.5), at(0.69, 0.61))
    elif name == "bell":
        path = QPainterPath(at(0.17, 0.72))
        path.cubicTo(at(0.3, 0.6), at(0.24, 0.16), at(0.5, 0.16))
        path.cubicTo(at(0.76, 0.16), at(0.7, 0.6), at(0.83, 0.72))
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(at(0.42, 0.86), at(0.58, 0.86))
    elif name == "repeat":
        top_path = QPainterPath(at(0.2, 0.58))
        top_path.lineTo(at(0.2, 0.32))
        top_path.lineTo(at(0.76, 0.32))
        painter.drawPath(top_path)
        painter.drawLine(at(0.64, 0.2), at(0.77, 0.32))
        painter.drawLine(at(0.64, 0.44), at(0.77, 0.32))
        bottom_path = QPainterPath(at(0.8, 0.42))
        bottom_path.lineTo(at(0.8, 0.68))
        bottom_path.lineTo(at(0.24, 0.68))
        painter.drawPath(bottom_path)
        painter.drawLine(at(0.36, 0.56), at(0.23, 0.68))
        painter.drawLine(at(0.36, 0.8), at(0.23, 0.68))
    elif name == "calendar":
        painter.drawRoundedRect(QRectF(at(0.12, 0.2), at(0.88, 0.88)), size * 0.1, size * 0.1)
        painter.drawLine(at(0.12, 0.42), at(0.88, 0.42))
        painter.drawLine(at(0.34, 0.08), at(0.34, 0.28))
        painter.drawLine(at(0.66, 0.08), at(0.66, 0.28))
    elif name == "lock":
        painter.drawRoundedRect(QRectF(at(0.2, 0.46), at(0.8, 0.88)), size * 0.08, size * 0.08)
        painter.drawArc(QRectF(at(0.3, 0.14), at(0.7, 0.62)), 0, 180 * 16)
        painter.drawLine(at(0.3, 0.38), at(0.3, 0.46))
        painter.drawLine(at(0.7, 0.38), at(0.7, 0.46))
    elif name == "x":
        painter.drawLine(at(0.28, 0.28), at(0.72, 0.72))
        painter.drawLine(at(0.72, 0.28), at(0.28, 0.72))
    else:
        painter.restore()
        raise ValueError(f"알 수 없는 아이콘입니다: {name}")
    painter.restore()


def icon_pixmap(name: str, size: int, color, device_pixel_ratio: float = 1.0) -> QPixmap:
    """draw_icon을 장치 배율에 맞춘 투명 QPixmap으로 만든다."""
    ratio = max(1.0, float(device_pixel_ratio))
    pixmap = QPixmap(round(size * ratio), round(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        draw_icon(painter, name, QRectF(0, 0, size, size), color)
    finally:
        painter.end()
    return pixmap


class ElidePaintMixin:
    """text()에는 전체 글자를 두고 그릴 때만 오른쪽을 말줄임한다(글자 그대로, 서식 해석 없음)."""

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(rect, self.alignment(), text)


class ElidedLabel(ElidePaintMixin, QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)


class ScheduleOptionsButton(QPushButton):
    """시계 버튼. 세부 설정 값을 보관하고 카드를 연다(입력줄·편집기 공용)."""

    options_changed = Signal(object)
    popup_closed = Signal()

    def __init__(self, edit: QLineEdit, can_edit, parent=None):
        super().__init__(parent)
        self.edit = edit
        self._can_edit = can_edit
        self._popup = None
        self._options = ScheduleOptions()
        self._start = ""
        self._occurrence = ""
        self.setFixedSize(26, 26)
        self.setObjectName("scheduleOptionsButton")
        self.setAccessibleName("일정 세부 설정")
        self.setCursor(Qt.PointingHandCursor)
        # 자식인 세부 카드로 번지지 않도록 #objectName으로 범위를 좁힌다.
        self.setStyleSheet(
            "QPushButton#scheduleOptionsButton{color:#475569;background:transparent;"
            "border:1px solid transparent;border-radius:5px;}"
            "QPushButton#scheduleOptionsButton:hover,QPushButton#scheduleOptionsButton:focus"
            "{background:#EFF6FF;border-color:#2563EB;}"
        )
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_focus)
        self.clicked.connect(self.open_popup)
        self._update_tooltip()

    def options(self) -> ScheduleOptions:
        return self._options

    def start_date(self) -> str:
        return self._start

    def set_context(self, start: str, occurrence: str = "") -> None:
        """기준 날짜(반복·기간의 시작)와 지금 보고 있는 날짜를 정한다.

        형식이 다른 옛 날짜(예: 2026-7-1)의 일정에는 세부 설정을 둘 수 없으므로 버튼을 끈다.
        """
        self._start = start
        self._occurrence = occurrence or start
        try:
            rules.parse_date(start)
            usable = True
        except ValueError:
            usable = False
        self.setEnabled(usable)
        self._update_tooltip()

    def set_options(self, options: ScheduleOptions) -> None:
        """밖에서 값을 바꾼다(알약 ×·날짜 이동·추가 성공). 신호는 내지 않는다."""
        self._options = options
        self._update_tooltip()
        self.update()
        if self._popup is not None:
            self._popup.set_options(options)

    def _update_tooltip(self) -> None:
        if not self.isEnabled():
            self.setToolTip("날짜 형식이 달라 세부 설정을 쓸 수 없는 일정입니다")
            return
        summary = ""
        if self._start and not self._options.is_default:
            try:
                summary = rules.options_summary(self._start, self._options)
            except ValueError as exc:
                # 일정 내용(날짜·시각 값)은 남기지 않고 예외 종류만 기록한다.
                _logger.warning("일정 세부 설정 요약 실패: %s", type(exc).__name__)
                summary = ""
        self.setToolTip(f"세부 설정: {summary}" if summary else "시각·알림·기간·반복")

    def paintEvent(self, event):
        # 클릭/포커스 영역은 26px, 원의 외경은 색 원·스마일과 같은 22px.
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        active = not self._options.is_default
        if not self.isEnabled():
            color = QColor("#94A3B8")
        else:
            color = QColor(ACTIVE_COLOR if active else ICON_COLOR)
        diameter = SCHEDULE_CONTROL_DIAMETER
        x, y = (self.width() - diameter) / 2, (self.height() - diameter) / 2
        painter.setPen(QPen(color, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(x + 0.5, y + 0.5, diameter - 1, diameter - 1))
        center = QPointF(x + diameter / 2, y + diameter / 2)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(center, QPointF(center.x(), y + 6))
        painter.drawLine(center, QPointF(x + 15.5, center.y() + 2.5))
        if active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QRectF(x + diameter - 7, y - 1, 8, 8))
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x + diameter - 6, y, 6, 6))

    def open_popup(self) -> None:
        if (not self._can_edit() or not self.isVisible() or not self.isEnabled()
                or self._popup is not None or not self._start):
            return  # 기준 날짜가 아직 없으면(set_context 전) 카드를 만들지 않는다.
        popup = ScheduleOptionsPopup(self._options, self._start, self._occurrence, self)
        self._popup = popup
        popup.options_changed.connect(lambda options: self._on_popup_changed(popup, options))
        popup.dismissed.connect(lambda restore: self._dismiss(popup, restore))
        popup.size_changed.connect(lambda: self._place(popup))
        self._place(popup)
        popup.show()
        remove_dwm_border(popup)
        popup.focus_first()

    def _place(self, popup) -> None:
        if self._popup is not popup:
            return
        anchor = self.rect().translated(self.mapToGlobal(QPoint(0, 0)))
        screen = QApplication.screenAt(anchor.center()) or self.screen()
        margin = popup.shadow_margin
        card = popup.size() - QSize(2 * margin, 2 * margin)
        point = popup_position(anchor, card, screen.availableGeometry())
        popup.move(point - QPoint(margin, margin))

    def _on_popup_changed(self, popup, options: ScheduleOptions) -> None:
        if self._popup is not popup or not self._can_edit():
            return
        self._options = options
        self._update_tooltip()
        self.update()
        self.options_changed.emit(options)

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
            self._popup = None  # 닫히면서 생기는 포커스 복원과 늦은 변경을 무효화한다.
            popup.close()
            popup.deleteLater()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down):
            self.open_popup()
        else:
            super().keyPressEvent(event)


class MiniMonthPicker(QWidget):
    """카드 안에 펼치는 작은 달력(일요일 시작). 따로 팝업을 띄우지 않는다."""

    date_picked = Signal(str)
    month_changed = Signal()  # 보이는 달이 바뀜(줄 수가 달라지면 카드 크기도 달라진다)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleMiniMonth")
        self._month = date.today().replace(day=1)
        self._lower = None
        self._upper = None
        self._range_start = None
        self._selected = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.prev_button = self._nav_button("‹", "이전 달", -1)
        self.title_label = QLabel(self)
        self.title_label.setObjectName("scheduleMiniTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.next_button = self._nav_button("›", "다음 달", 1)
        head.addWidget(self.prev_button)
        head.addWidget(self.title_label, 1)
        head.addWidget(self.next_button)
        layout.addLayout(head)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(1)
        for col, name in enumerate("일월화수목금토"):
            label = QLabel(name, self)
            label.setObjectName("scheduleMiniWeekday")
            label.setAlignment(Qt.AlignCenter)
            label.setProperty("tone", "sun" if col == 0 else "sat" if col == 6 else "")
            grid.addWidget(label, 0, col)
        self.day_buttons = []
        for index in range(42):
            button = QPushButton(self)
            button.setObjectName("scheduleMiniDay")
            button.setFixedSize(30, 24)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, i=index: self._pick(i))
            grid.addWidget(button, 1 + index // 7, index % 7)
            self.day_buttons.append(button)
        layout.addLayout(grid)

    def _nav_button(self, text: str, name: str, step: int) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName("scheduleMiniNav")
        button.setFixedSize(26, 22)
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.clicked.connect(lambda: self.show_month(rules.add_months(self._month, step)))
        return button

    def set_state(self, *, month: date, lower: date, upper: date | None,
                  range_start: date | None, selected: date | None) -> None:
        self._lower, self._upper = lower, upper
        self._range_start, self._selected = range_start, selected
        self.show_month(month)

    def show_month(self, month: date) -> None:
        self._month = month.replace(day=1)
        self.title_label.setText(f"{self._month.year}년 {self._month.month}월")
        first_col = (self._month.weekday() + 1) % 7  # 일요일 = 0
        days = calendar.monthrange(self._month.year, self._month.month)[1]
        for index, button in enumerate(self.day_buttons):
            number = index - first_col + 1
            if not 1 <= number <= days:
                button.setText("")
                button.setEnabled(False)
                button.setVisible(index < 35 or first_col + days > 35)
                button.setProperty("day", "")
                button.setProperty("role", "")
                button.setProperty("tone", "")
            else:
                day = self._month.replace(day=number)
                iso = day.isoformat()
                button.setVisible(True)
                button.setText(str(number))
                button.setProperty("day", iso)
                allowed = ((self._lower is None or day >= self._lower)
                           and (self._upper is None or day <= self._upper))
                button.setEnabled(allowed)
                if day == self._selected or (self._range_start is not None and day == self._range_start):
                    role = "end"
                elif (self._range_start is not None and self._selected is not None
                      and self._range_start < day < self._selected):
                    role = "in"
                else:
                    role = ""
                button.setProperty("role", role)
                col = index % 7
                tone = "sun" if col == 0 or holidays.is_holiday(iso) else "sat" if col == 6 else ""
                button.setProperty("tone", tone)
                button.setAccessibleName(rules.korean_date(day))
            button.style().unpolish(button)
            button.style().polish(button)
        self.month_changed.emit()

    def button_for(self, iso: str) -> QPushButton | None:
        return next((b for b in self.day_buttons if b.property("day") == iso), None)

    def _pick(self, index: int) -> None:
        iso = self.day_buttons[index].property("day")
        if iso:
            self.date_picked.emit(iso)


class ScheduleOptionsPopup(QWidget):
    """세부 설정 카드. 칩을 누르는 즉시 값이 바뀌고(options_changed) Esc·바깥·완료는 닫기만 한다."""

    options_changed = Signal(object)
    dismissed = Signal(bool)
    size_changed = Signal()
    shadow_margin = SHADOW_MARGIN

    def __init__(self, options: ScheduleOptions, start: str, occurrence: str = "", parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("scheduleOptionsPopup")
        self.setAccessibleName("일정 세부 설정")
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 바깥의 원래 버튼 클릭이 재전달되어 곧바로 다시 열리는 것을 막는다.
        self.setAttribute(Qt.WA_NoMouseReplay)
        self._return_focus = False
        self._options = options
        self._start = start
        self._start_day = rules.parse_date(start)
        self._occurrence = occurrence or start
        self._was_repeat = bool(options.repeat_rule)
        self._picker_for = ""
        self._reported_size = QSize()  # 마지막으로 size_changed로 알린 크기
        self._rendering = False  # _render 도중 작은 달력이 내는 month_changed는 마지막 한 번만 배치한다.
        self._last_time = options.start_time or "09:00"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.card = QFrame(self)
        self.card.setObjectName("scheduleOptionsCard")
        self.card.setFixedWidth(CARD_WIDTH)
        self.card.setStyleSheet(CARD_QSS)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("세부 설정", self.card)
        title.setObjectName("scheduleOptionsTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.clear_button = QPushButton("모두 지우기", self.card)
        self.clear_button.setObjectName("scheduleOptionsClear")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setToolTip("시각·알림·기간·반복을 모두 기본값으로 되돌립니다")
        self.clear_button.clicked.connect(lambda: self._change(ScheduleOptions()))
        head.addWidget(self.clear_button)
        layout.addLayout(head)

        body = self._row(layout, "시각")
        line = QHBoxLayout()
        line.setSpacing(6)
        self.all_day_chip = self._chip("하루 종일", lambda: self._change(rules.with_start_time(self._options, "")))
        self.timed_chip = self._chip("시각", self._choose_timed)
        self.time_edit = QLineEdit(self.card)
        self.time_edit.setObjectName("scheduleOptionsTime")
        self.time_edit.setFixedSize(62, 26)
        self.time_edit.setPlaceholderText("09:00")
        self.time_edit.setAccessibleName("시작 시각")
        self.time_edit.setToolTip("0930·14:30처럼 입력하고 Enter")
        # 입력 중에는 검사만 하고(틀리면 빨간 테두리), Enter·다른 곳 누르기·닫기 때 반영한다.
        self.time_edit.textEdited.connect(self._on_time_edited)
        self.time_edit.editingFinished.connect(self._commit_time_text)
        line.addWidget(self.all_day_chip)
        line.addWidget(self.timed_chip)
        line.addWidget(self.time_edit)
        line.addStretch(1)
        body.addLayout(line)

        body = self._row(layout, "알림")
        self.timed_alarm_box = QWidget(self.card)
        grid = QGridLayout(self.timed_alarm_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.timed_alarm_chips = {}
        for index, (value, text) in enumerate(TIMED_ALARM_CHOICES):
            chip = self._chip(text, lambda v=value: self._change(replace(self._options, alarm_before=v)))
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(chip, index // 3, index % 3)
            self.timed_alarm_chips[value] = chip
        body.addWidget(self.timed_alarm_box)
        self.all_day_alarm_box = QWidget(self.card)
        row = QHBoxLayout(self.all_day_alarm_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.all_day_alarm_chips = {}
        for value, text in ALLDAY_ALARM_CHOICES:
            chip = self._chip(text, lambda v=value: self._change(replace(self._options, alarm_before=v)))
            row.addWidget(chip)
            self.all_day_alarm_chips[value] = chip
        row.addStretch(1)
        body.addWidget(self.all_day_alarm_box)

        body = self._row(layout, "기간")
        line = QHBoxLayout()
        line.setSpacing(6)
        self.one_day_chip = self._chip("하루", lambda: self._change(replace(self._options, end_date="")))
        self.many_days_chip = self._chip("여러 날", self._choose_many_days)
        line.addWidget(self.one_day_chip)
        line.addWidget(self.many_days_chip)
        line.addStretch(1)
        body.addLayout(line)
        self.period_caption = self._caption(lambda: self._toggle_picker("period"))
        body.addWidget(self.period_caption)
        self.period_picker = MiniMonthPicker(self.card)
        self.period_picker.date_picked.connect(
            lambda iso: self._change(replace(self._options, end_date=iso)))
        self.period_picker.month_changed.connect(self._on_month_changed)
        body.addWidget(self.period_picker)
        self.period_note = self._note(REPEAT_ONLY_ONE_DAY)
        body.addWidget(self.period_note)

        body = self._row(layout, "반복")
        grid = QGridLayout()
        grid.setSpacing(6)
        self.repeat_chips = {}
        for index, (rule, text) in enumerate(REPEAT_CHOICES):
            chip = self._chip(text, lambda r=rule: self._change(rules.with_repeat(self._options, self._start, r)))
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(chip, index // 3, index % 3)
            self.repeat_chips[rule] = chip
        body.addLayout(grid)
        self.repeat_caption = QLabel(self.card)
        self.repeat_caption.setTextFormat(Qt.PlainText)
        self.repeat_caption.setStyleSheet("color:#334155;font-size:12px;")
        body.addWidget(self.repeat_caption)
        self.repeat_note = self._note(PERIOD_NO_REPEAT)
        body.addWidget(self.repeat_note)
        self.series_note = self._note("")
        body.addWidget(self.series_note)

        self.until_row = QWidget(self.card)
        until_layout = QVBoxLayout(self.until_row)
        until_layout.setContentsMargins(0, 0, 0, 0)
        until_layout.setSpacing(0)
        body = self._row(until_layout, "끝", parent=self.until_row)
        line = QHBoxLayout()
        line.setSpacing(6)
        self.forever_chip = self._chip("계속", lambda: self._change(replace(self._options, repeat_until="")),
                                       parent=self.until_row)
        self.until_chip = self._chip("날짜까지", self._choose_until, parent=self.until_row)
        line.addWidget(self.forever_chip)
        line.addWidget(self.until_chip)
        line.addStretch(1)
        body.addLayout(line)
        self.until_caption = self._caption(lambda: self._toggle_picker("until"), parent=self.until_row)
        body.addWidget(self.until_caption)
        self.until_picker = MiniMonthPicker(self.until_row)
        self.until_picker.date_picked.connect(
            lambda iso: self._change(replace(self._options, repeat_until=iso)))
        self.until_picker.month_changed.connect(self._on_month_changed)
        body.addWidget(self.until_picker)
        layout.addWidget(self.until_row)

        foot = QHBoxLayout()
        hint = QLabel("Esc · 바깥을 누르면 닫힘", self.card)
        hint.setObjectName("scheduleOptionsHint")
        foot.addWidget(hint)
        foot.addStretch(1)
        self.done_button = QPushButton("완료", self.card)
        self.done_button.setObjectName("scheduleOptionsDone")
        self.done_button.setFixedHeight(28)
        self.done_button.setCursor(Qt.PointingHandCursor)
        self.done_button.clicked.connect(self.dismiss)
        foot.addWidget(self.done_button)
        layout.addLayout(foot)
        self._render()

    # ── 만들기 도우미 ──
    def _row(self, layout, name: str, parent=None) -> QVBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(name, parent or self.card)
        label.setObjectName("scheduleOptionsRowLabel")
        label.setFixedWidth(30)
        label.setFixedHeight(26)
        row.addWidget(label, 0, Qt.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(6)
        row.addLayout(body, 1)
        layout.addLayout(row)
        return body

    def _chip(self, text: str, slot, parent=None) -> QPushButton:
        chip = QPushButton(text, parent or self.card)
        chip.setProperty("segment", True)
        chip.setCheckable(True)
        chip.setFixedHeight(26)
        chip.setCursor(Qt.PointingHandCursor)
        chip.setFocusPolicy(Qt.StrongFocus)
        # clicked(bool)의 checked가 기본값 인자를 덮어쓰지 않도록 인자 없이 부른다.
        chip.clicked.connect(lambda checked=False: slot())
        return chip

    def _caption(self, slot, parent=None) -> QPushButton:
        caption = QPushButton(parent or self.card)
        caption.setObjectName("scheduleOptionsCaption")
        caption.setCursor(Qt.PointingHandCursor)
        caption.setFlat(True)
        caption.clicked.connect(lambda checked=False: slot())
        return caption

    def _note(self, text: str) -> QLabel:
        note = QLabel(text, self.card)
        note.setObjectName("scheduleOptionsNote")
        note.setTextFormat(Qt.PlainText)
        note.setWordWrap(True)
        return note

    # ── 값 바꾸기 ──
    def options(self) -> ScheduleOptions:
        return self._options

    def set_options(self, options: ScheduleOptions) -> None:
        self._options = options
        self._render()

    def _change(self, options: ScheduleOptions) -> None:
        if options.is_default or not options.end_date:
            if self._picker_for == "period":
                self._picker_for = ""
        if not options.repeat_until and self._picker_for == "until":
            self._picker_for = ""
        if options == self._options:
            self._render()
            return
        self._options = options
        if options.start_time:
            self._last_time = options.start_time
        self._render()
        self.options_changed.emit(options)

    def _choose_timed(self) -> None:
        if not self._options.start_time:
            self._change(rules.with_start_time(self._options, self._last_time))
        else:
            self._render()
        self.time_edit.setFocus(Qt.OtherFocusReason)
        self.time_edit.selectAll()

    def _choose_many_days(self) -> None:
        if not self._options.end_date:
            end = (self._start_day + timedelta(days=1)).isoformat()
            self._picker_for = "period"
            self._change(replace(self._options, end_date=end))
        else:
            self._toggle_picker("period")

    def _choose_until(self) -> None:
        if not self._options.repeat_until:
            until = rules.add_months(self._start_day, 1).isoformat()
            self._picker_for = "until"
            self._change(replace(self._options, repeat_until=until))
        else:
            self._toggle_picker("until")

    def _toggle_picker(self, which: str) -> None:
        self._picker_for = "" if self._picker_for == which else which
        self._render()

    def _on_time_edited(self, text: str) -> None:
        try:
            rules.parse_time_input(text)
        except ValueError:
            self._set_time_invalid(bool(text.strip()))
            return
        self._set_time_invalid(False)

    def _commit_time_text(self) -> None:
        """입력칸 글자를 반영한다. 틀렸으면 마지막 올바른 값으로 되돌린다."""
        if not self._options.start_time:
            return
        try:
            value = rules.parse_time_input(self.time_edit.text())
        except ValueError:
            value = self._options.start_time
        self._set_time_invalid(False)
        self.time_edit.setText(value)
        if value != self._options.start_time:
            self._change(rules.with_start_time(self._options, value))

    def _set_time_invalid(self, invalid: bool) -> None:
        if bool(self.time_edit.property("invalid")) != invalid:
            self.time_edit.setProperty("invalid", invalid)
            self.time_edit.style().unpolish(self.time_edit)
            self.time_edit.style().polish(self.time_edit)

    # ── 그리기 ──
    def _render(self) -> None:
        self._rendering = True
        try:
            self._render_state()
        finally:
            self._rendering = False
        self._relayout()

    def _on_month_changed(self) -> None:
        """달 넘기기로 줄 수(5↔6)가 바뀌면 카드 크기를 맞추고 size_changed로 위치를 다시 잡게 한다."""
        if not self._rendering:
            self._relayout()

    def _render_state(self) -> None:
        options = self._options
        timed = bool(options.start_time)
        period = bool(options.end_date)
        repeat = bool(options.repeat_rule)
        self.all_day_chip.setChecked(not timed)
        self.timed_chip.setChecked(timed)
        self.time_edit.setVisible(timed)
        if timed and not self.time_edit.hasFocus():
            self.time_edit.setText(options.start_time)
        self.timed_alarm_box.setVisible(timed)
        self.all_day_alarm_box.setVisible(not timed)
        for value, chip in self.timed_alarm_chips.items():
            chip.setChecked(options.alarm_before == value)
        for value, chip in self.all_day_alarm_chips.items():
            chip.setChecked(options.alarm_before == value)
        self.one_day_chip.setChecked(not period)
        self.many_days_chip.setChecked(period)
        self.many_days_chip.setEnabled(not repeat)
        self.period_note.setVisible(repeat)
        self.period_caption.setVisible(period)
        if period:
            self.period_caption.setText(rules.period_caption(self._start, options.end_date) + "  ▾")
        show_period_picker = period and self._picker_for == "period"
        self.period_picker.setVisible(show_period_picker)
        if show_period_picker:
            end = rules.parse_date(options.end_date)
            self.period_picker.set_state(
                month=end, lower=self._start_day + timedelta(days=1),
                upper=self._start_day + timedelta(days=rules.MAX_SPAN_DAYS),
                range_start=self._start_day, selected=end)
        for rule, chip in self.repeat_chips.items():
            chip.setChecked(options.repeat_rule == rule)
            chip.setEnabled(not period or rule == "")
        self.repeat_note.setVisible(period)
        self.repeat_caption.setVisible(repeat)
        if repeat:
            self.repeat_caption.setText(rules.repeat_caption(self._start, options.repeat_rule))
        turned_off = self._was_repeat and not repeat and self._occurrence != self._start
        self.series_note.setVisible(turned_off)
        if turned_off:
            self.series_note.setText(
                f"반복을 끄면 첫 날짜({self._start_day.month}월 {self._start_day.day}일) 하루만 남습니다")
        self.until_row.setVisible(repeat)
        self.forever_chip.setChecked(not options.repeat_until)
        self.until_chip.setChecked(bool(options.repeat_until))
        self.until_caption.setVisible(bool(options.repeat_until))
        if options.repeat_until:
            self.until_caption.setText(rules.until_caption(options.repeat_until) + "  ▾")
        show_until_picker = repeat and bool(options.repeat_until) and self._picker_for == "until"
        self.until_picker.setVisible(show_until_picker)
        if show_until_picker:
            until = rules.parse_date(options.repeat_until)
            self.until_picker.set_state(month=until, lower=self._start_day, upper=None,
                                        range_start=None, selected=until)

    def _relayout(self) -> None:
        """카드 크기를 내용에 맞추고, 지난번에 알린 크기와 달라졌으면 size_changed를 낸다.

        칸(위젯) 경계마다 배치 요청이 비동기로 올라가므로 안쪽 칸부터 바깥으로 차례로 맞춘다.
        자식을 보이는 순간 Qt가 창을 먼저 키우기도 해서, 호출 직전 크기가 아니라
        마지막으로 알린 크기와 비교해야 커진 경우에도 위치를 다시 잡는다.
        """
        for widget in (self.period_picker, self.until_picker, self.until_row, self.card, self):
            layout = widget.layout()
            layout.invalidate()
            layout.activate()
        self.adjustSize()
        if self.size() != self._reported_size:
            self._reported_size = self.size()
            self.size_changed.emit()

    # ── 포커스·닫기 ──
    def focus_first(self) -> None:
        chip = self.timed_chip if self._options.start_time else self.all_day_chip
        chip.setFocus(Qt.PopupFocusReason)

    def dismiss(self) -> None:
        self._return_focus = True
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.dismiss()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = self.focusWidget()
            if isinstance(focused, QPushButton):
                focused.click()
            elif focused is self.time_edit:
                self._commit_time_text()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.close()  # 그림자 여백은 카드 바깥이다.
            event.accept()
        else:
            super().mousePressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._commit_time_text()  # 닫기 전에 입력 중인 시각을 반영한다(무효화된 카드면 버튼이 무시).
        self.dismissed.emit(self._return_focus)


class _OptionPill(QWidget):
    """알약 하나: [아이콘 글자 ×]. 본문을 누르면 카드, ×는 그 항목만 지운다."""

    clicked = Signal()
    clear_clicked = Signal()
    HEIGHT = 22
    MAX_WIDTH = 150

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._icon = "clock"
        self._text = ""
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        font = self.font()
        font.setPixelSize(11)
        self.setFont(font)

    def text(self) -> str:
        return self._text

    def set_content(self, icon: str, text: str) -> None:
        self._icon, self._text = icon, text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        width = 8 + 12 + 4 + self.fontMetrics().horizontalAdvance(self._text) + 4 + 12 + 5
        return QSize(min(self.MAX_WIDTH, width), self.HEIGHT)

    def minimumSizeHint(self):
        return QSize(min(self.MAX_WIDTH, 60), self.HEIGHT)

    def clear_rect(self) -> QRectF:
        return QRectF(self.width() - 5 - 12, (self.height() - 12) / 2, 12, 12)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        hovered = self.underMouse()
        painter.setPen(QPen(QColor("#CBD5E1" if hovered else "#E2E8F0"), 1))
        painter.setBrush(QColor("#E9EEF5" if hovered else "#F1F5F9"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10.5, 10.5)
        draw_icon(painter, self._icon, QRectF(8, (self.height() - 12) / 2, 12, 12), "#475569")
        clear = self.clear_rect()
        text_rect = QRectF(24, 0, clear.left() - 4 - 24, self.height())
        painter.setPen(QColor("#334155"))
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(self._text, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        draw_icon(painter, "x", clear, "#64748B")

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.rect().contains(event.position().toPoint()):
            return super().mouseReleaseEvent(event)
        if self.clear_rect().adjusted(-3, -3, 3, 3).contains(event.position()):
            self.clear_clicked.emit()
        else:
            self.clicked.emit()
        event.accept()

    def event(self, event):
        if event.type() in (QEvent.HoverEnter, QEvent.HoverLeave):
            self.update()
        return super().event(event)


class ScheduleOptionsPills(QWidget):
    """입력칸 아래 알약 줄. 값이 있을 때만 보인다(없으면 숨겨 지금 배치와 같다)."""

    open_requested = Signal()
    clear_requested = Signal(str)
    KINDS = ("time", "alarm", "period", "repeat")
    ICONS = {"time": "clock", "alarm": "bell", "period": "calendar", "repeat": "repeat"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleOptionsPills")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.pills = {}
        for kind in self.KINDS:
            pill = _OptionPill(kind, self)
            pill.clicked.connect(self.open_requested)
            pill.clear_clicked.connect(lambda k=kind: self.clear_requested.emit(k))
            pill.hide()
            layout.addWidget(pill)
            self.pills[kind] = pill
        layout.addStretch(1)
        self.hide()

    def set_state(self, start: str, options: ScheduleOptions) -> None:
        texts = {"time": "", "alarm": "", "period": "", "repeat": ""}
        if start and not options.is_default:
            texts = {
                "time": rules.time_pill(options),
                "alarm": "" if options.start_time else rules.alarm_label(options, short=True),
                "period": rules.span_pill(start, options),
                "repeat": rules.repeat_pill(start, options),
            }
        for kind, pill in self.pills.items():
            pill.setVisible(bool(texts[kind]))
            if texts[kind]:
                pill.set_content(self.ICONS[kind], texts[kind])
        self.setVisible(any(texts.values()))

    def visible_texts(self) -> list[str]:
        return [pill.text() for pill in self.pills.values() if not pill.isHidden()]
