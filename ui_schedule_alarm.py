"""일정 알림 엔진과 알림 카드 (v4.1).

앱이 켜져 있을 때만 알린다(Windows 알림 센터는 쓰지 않는다). 알림 처리 시각
`schedule_alarm_seen_at`은 카드를 띄울 때와, 알림 켜진 일정이 있을 때의 정상 종료 때만 쓴다.
"""
import logging
import sqlite3
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

import database as db
import schedule_rules as rules
from popup_border_fix import remove_dwm_border
from ui_schedule_options import ElidedLabel, icon_pixmap

_logger = logging.getLogger("app_error")

LOOKBACK = timedelta(hours=12)       # 이보다 오래된 알림은 알리지 않는다
MISSED_AFTER = timedelta(minutes=2)  # 이보다 늦게 확인한 알림은 '놓친 알림'
SNOOZE = timedelta(minutes=5)
MAX_INTERVAL_MS = 60_000
CARD_WIDTH = 320
CARD_MARGIN = 16
SCREEN_GAP = 12
MAX_ROWS = 3
UNREADABLE = "내용을 읽을 수 없는 일정"


def _parse_seen(value: str) -> datetime | None:
    """저장된 처리 시각. 읽을 수 없거나 시간대가 붙은 값은 없는 것으로 본다(현지 시각과 견줄 수 없다)."""
    try:
        parsed = datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    if parsed is not None and parsed.tzinfo is not None:
        return None
    return parsed


class ScheduleAlarmScheduler(QObject):
    """단발 타이머로 다음 알림(최대 60초 뒤)마다 확인한다. 시계 함수는 바꿔 넣을 수 있다(시험용)."""

    alarms_ready = Signal(list, bool)  # (AlarmItem 목록, 모두 놓친 알림인지)

    def __init__(self, parent=None, *, now=None):
        super().__init__(parent)
        self._now = now or datetime.now
        self._running = False
        self._last_check = None
        self._fired = {}  # 이미 띄운 알림 키 -> 알림 시각(확인 창 12시간이 지나면 지운다)
        self._snoozed = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.check)

    def is_running(self) -> bool:
        return self._running

    def last_check(self):
        return self._last_check

    def start(self) -> None:
        """시작: 저장된 처리 시각(최대 12시간 전)부터 지금까지를 확인한다. 키가 없으면 지금부터."""
        if self._running:
            self.refresh()
            return
        now = self._now()
        try:
            seen = _parse_seen(db.get_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT, ""))
        except (sqlite3.Error, OSError) as exc:
            _logger.error("일정 알림 처리 시각 읽기 실패: %s", exc)
            seen = None
        self._last_check = max(seen, now - LOOKBACK) if seen is not None else now
        self._running = True
        self.check()

    def stop(self, *, persist: bool = False) -> None:
        """멈춘다. persist면 알림 켜진 일정이 있을 때만 마지막 확인 시각을 남긴다."""
        self._timer.stop()
        if persist and self._running and self._last_check is not None:
            try:
                if db.has_schedule_alarms():
                    db.save_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT,
                                    self._last_check.isoformat(timespec="seconds"))
            except (sqlite3.Error, OSError) as exc:
                _logger.error("일정 알림 처리 시각 저장 실패: %s", exc)
        self._running = False
        self._snoozed.clear()
        self._fired.clear()  # 초기화 뒤에는 일정 번호가 다시 시작한다.

    def refresh(self) -> None:
        """일정이 바뀐 뒤: 지난 알림은 다시 울리지 않고 다음 확인 시각만 다시 맞춘다."""
        if self._running:
            self._schedule_next(self._now())

    def resume(self) -> None:
        """절전 복귀: 바로 확인한다(2분 넘은 것은 놓친 알림)."""
        if self._running:
            self.check()

    def check(self) -> None:
        if not self._running:
            return
        now = self._now()
        try:
            self._check_at(now)
        finally:
            self._schedule_next(now)  # 중간에 예외가 나도 단발 타이머는 반드시 다시 건다.

    def _check_at(self, now) -> None:
        mark = self._last_check or now
        if mark - now > LOOKBACK:
            mark = now  # 시계를 크게 되돌렸으면 지금부터 다시 센다(이미 띄운 것은 _fired가 막는다).
        # 확인한 가장 늦은 시각(mark)은 되돌리지 않는다: 시계가 조금 뒤로 가도 지난 알림이 다시 울리지 않는다.
        after = max(mark, now - LOOKBACK)
        found = self._load(after, now) if now > after else []
        fresh = [item for item in found if item.key not in self._fired]
        again = []  # '5분 뒤 다시'로 돌아온 알림: 놓친 알림이 아니다.
        for key, (item, until) in list(self._snoozed.items()):
            if until <= now:
                del self._snoozed[key]
                if self._still_scheduled(item):
                    again.append(item)
        self._last_check = max(mark, now)
        self._fired = {key: when for key, when in self._fired.items() if when >= now - LOOKBACK}
        due = fresh + again
        if due:
            due.sort(key=lambda item: (item.due, item.schedule_id))
            self._fired.update((item.key, item.due) for item in due)
            try:
                # 저장하는 값은 되돌아가지 않는다(확인한 가장 늦은 시각).
                db.save_setting(db.SETTING_SCHEDULE_ALARM_SEEN_AT,
                                self._last_check.isoformat(timespec="seconds"))
            except (sqlite3.Error, OSError) as exc:
                _logger.error("일정 알림 처리 시각 저장 실패: %s", exc)
            # 놓친 알림은 시작·복귀 때 확인 창에서 찾은 것만이다. 다시 알림은 놓친 것이 아니다.
            missed = not again and all(now - item.due > MISSED_AFTER for item in fresh)
            self.alarms_ready.emit(due, missed)

    def snooze(self, items) -> None:
        """'5분 뒤 다시': 메모리에만 두며 종료하면 사라진다."""
        if not self._running:
            return
        until = self._now() + SNOOZE
        for item in items:
            self._snoozed[item.key] = (item, until)
        self._schedule_next(self._now())

    def _load(self, after, until) -> list:
        try:
            return db.get_alarm_occurrences(after, until)
        except (sqlite3.Error, OSError) as exc:
            _logger.error("일정 알림 확인 실패: %s", exc)
            return []

    def _still_scheduled(self, item) -> bool:
        """다시 알릴 때 그 일정·날짜·알림 시각이 아직 그대로인지 본다(삭제·변경 반영)."""
        found = self._load(item.due - timedelta(seconds=1), item.due)
        return any(other.key == item.key for other in found)

    def _schedule_next(self, now) -> None:
        if not self._running:
            return
        interval = MAX_INTERVAL_MS  # 계산 중 예외가 나도 이 간격으로 타이머는 다시 걸린다.
        try:
            horizon = now + timedelta(milliseconds=MAX_INTERVAL_MS)
            candidates = [item.due for item in self._load(now, horizon) if item.key not in self._fired]
            candidates += [until for _item, until in self._snoozed.values()]
            if candidates:
                wait = (min(candidates) - now).total_seconds() * 1000 + 50
                interval = max(50, min(MAX_INTERVAL_MS, int(wait)))
        finally:
            self._timer.start(interval)


class ScheduleAlarmCard(QWidget):
    """화면 오른쪽 아래 알림 카드. 포커스를 빼앗지 않고 작업 표시줄에 나타나지 않는다."""

    snooze_requested = Signal(list)
    open_date_requested = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setObjectName("scheduleAlarmCard")
        self.setAccessibleName("일정 알림")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._items = []
        self._missed = True
        self._locked = False
        self._now = datetime.now()
        self._screen = None  # show_at이 정한 화면: 크기가 바뀌면 이 화면 오른쪽 아래에 다시 맞춘다.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        self.frame = QFrame(self)
        self.frame.setObjectName("scheduleAlarmFrame")
        self.frame.setFixedWidth(CARD_WIDTH)
        shadow = QGraphicsDropShadowEffect(self.frame)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.frame.setGraphicsEffect(shadow)
        outer.addWidget(self.frame)
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.icon_label = QLabel(self.frame)
        self.icon_label.setFixedSize(16, 16)
        head.addWidget(self.icon_label)
        self.title_label = QLabel(self.frame)
        self.title_label.setObjectName("scheduleAlarmTitle")
        self.title_label.setTextFormat(Qt.PlainText)
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.close_button = QPushButton("×", self.frame)
        self.close_button.setObjectName("scheduleAlarmClose")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setAccessibleName("알림 닫기")
        self.close_button.clicked.connect(self.close)
        head.addWidget(self.close_button)
        layout.addLayout(head)
        self.rows_box = QWidget(self.frame)
        self.rows_layout = QVBoxLayout(self.rows_box)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        layout.addWidget(self.rows_box)
        self.more_label = QLabel(self.frame)
        self.more_label.setObjectName("scheduleAlarmMore")
        self.more_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.more_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.snooze_button = QPushButton("5분 뒤 다시", self.frame)
        self.snooze_button.setObjectName("scheduleAlarmSnooze")
        self.snooze_button.setCursor(Qt.PointingHandCursor)
        self.snooze_button.clicked.connect(self._snooze)
        self.ok_button = QPushButton("확인", self.frame)
        self.ok_button.setObjectName("scheduleAlarmOk")
        self.ok_button.setCursor(Qt.PointingHandCursor)
        self.ok_button.clicked.connect(self.close)
        for button in (self.snooze_button, self.ok_button):
            button.setFixedHeight(28)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._render()

    def items(self) -> list:
        return list(self._items)

    def add_items(self, items, *, missed: bool, locked: bool, now: datetime | None = None) -> None:
        known = {item.key for item in self._items}
        fresh = [item for item in items if item.key not in known]
        self._missed = (self._missed if self._items else True) and missed
        self._items = sorted(self._items + fresh, key=lambda item: (item.due, item.schedule_id))
        self._locked = locked
        self._now = now or datetime.now()
        self._render()

    def set_locked(self, locked: bool) -> None:
        if self._locked != locked:
            self._locked = locked
            self._render()

    def is_locked_view(self) -> bool:
        return self._locked

    def _render(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        count = len(self._items)
        stripe = self._items[0].color if self._items and not self._locked else "#2563EB"
        self.frame.setStyleSheet(
            "QFrame#scheduleAlarmFrame{background:#FFFFFF;border:1px solid #D7DAE2;"
            f"border-left:4px solid {stripe};border-radius:12px;}}"
            "QFrame#scheduleAlarmFrame QLabel{background:transparent;}"
            "QLabel#scheduleAlarmTitle{color:#172B4D;font-size:13px;font-weight:bold;}"
            "QLabel#scheduleAlarmItemTitle{color:#172B4D;font-size:15px;font-weight:bold;}"
            "QLabel#scheduleAlarmItemSub,QLabel#scheduleAlarmMore,QLabel#scheduleAlarmLocked"
            "{color:#5B6577;font-size:12px;}"
            "QPushButton#scheduleAlarmClose{background:transparent;border:0px;border-radius:6px;"
            "color:#7A8699;font-size:17px;}"
            "QPushButton#scheduleAlarmClose:hover{background:#F1F4F8;color:#253447;}"
            "QPushButton#scheduleAlarmSnooze{background:#FFFFFF;border:1px solid #CBD5E1;"
            "border-radius:6px;color:#334155;font-size:12px;padding:0px 12px;}"
            "QPushButton#scheduleAlarmSnooze:hover{background:#F8FAFC;}"
            "QPushButton#scheduleAlarmOk{background:#2563EB;border:1px solid #2563EB;"
            "border-radius:6px;color:#FFFFFF;font-size:12px;font-weight:bold;padding:0px 16px;}"
            "QPushButton#scheduleAlarmOk:hover{background:#1D4ED8;}"
        )
        ratio = self.devicePixelRatioF()
        # 잠금 중에는 건수를 늘 보인다(내용은 가려도 몇 건인지는 알린다).
        self.title_label.setText(f"일정 알림 {count}건" if count > 1 or self._locked else "일정 알림")
        if self._locked:
            self.icon_label.setPixmap(icon_pixmap("lock", 16, "#475569", ratio))
            locked = QLabel("PIN 잠금 중이라 내용을 숨겼습니다.", self.rows_box)
            locked.setObjectName("scheduleAlarmLocked")
            locked.setTextFormat(Qt.PlainText)
            self.rows_layout.addWidget(locked)
            locked.show()
            self.more_label.hide()
        else:
            self.icon_label.setPixmap(icon_pixmap("bell", 16, "#2563EB", ratio))
            for item in self._items[:MAX_ROWS]:
                row = self._row(item)
                self.rows_layout.addWidget(row)
                row.show()  # 열린 카드에 더한 줄은 레이아웃이 늦게 보이므로, 크기를 재기 전에 보인다.
            extra = count - MAX_ROWS
            self.more_label.setText(f"외 {extra}건" if extra > 0 else "")
            self.more_label.setVisible(extra > 0)
        self.snooze_button.setVisible(not self._missed and not self._locked)
        self.frame.layout().activate()
        self.adjustSize()
        if self.isVisible():
            self._anchor()  # 열려 있는 카드는 크기가 바뀌어도 오른쪽 아래에 붙어 있다.

    def _row(self, item) -> QWidget:
        row = QWidget(self.rows_box)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        content = UNREADABLE if item.decryption_failed else item.content
        title = ElidedLabel(f"{item.start_time} {content}" if item.start_time else content, row)
        title.setObjectName("scheduleAlarmItemTitle")
        sub = ElidedLabel(rules.alarm_subtitle(
            item.start_time, date.fromisoformat(item.occurrence_date), self._now), row)
        sub.setObjectName("scheduleAlarmItemSub")
        layout.addWidget(title)
        layout.addWidget(sub)
        return row

    def _anchor(self) -> None:
        """기억한 화면 작업 영역의 오른쪽 아래, 12px 안쪽에 카드 틀이 닿게 옮긴다."""
        screen = self._screen if self._screen is not None and isValid(self._screen) else self.screen()
        if screen is None:
            return
        self.adjustSize()
        available = screen.availableGeometry()
        x = available.right() + 1 - SCREEN_GAP - (self.width() - CARD_MARGIN)
        y = available.bottom() + 1 - SCREEN_GAP - (self.height() - CARD_MARGIN)
        self.move(QPoint(x, y))

    def show_at(self, screen) -> None:
        """screen 작업 영역의 오른쪽 아래, 12px 안쪽에 보인다."""
        self._screen = screen
        self._anchor()
        self.show()
        self.raise_()
        remove_dwm_border(self)

    def _snooze(self) -> None:
        if self._locked:  # 잠금 중에는 다시 알림을 받지 않는다(버튼도 숨겨져 있다).
            return
        self.snooze_requested.emit(list(self._items))
        self.close()

    def mouseReleaseEvent(self, event):
        inside = self.frame.geometry().contains(event.position().toPoint())
        if event.button() == Qt.LeftButton and inside and self._items:
            if not self._locked:
                self.open_date_requested.emit(self._items[0].occurrence_date)
            self.close()
            event.accept()
            return
        super().mouseReleaseEvent(event)
