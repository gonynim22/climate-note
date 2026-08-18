# ui_focus_panel.py - '크게' 모드 우측 컬럼의 집중 모드 미니 패널(라이브 미러)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import TransparentToolButton, FluentIcon as FIF

from ui_focus import FOCUS_ACCENT_COLOR, FocusProgressRing


class FocusMiniCard(QWidget):
    """숨긴 채 살아 있는 FocusWidgetWindow의 타이머를 미러링하는 표시 전용 카드."""

    close_requested = Signal()

    def __init__(self, source_window, parent=None):
        super().__init__(parent)
        self._source = source_window
        self.setObjectName("focusMiniCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "#focusMiniCard{background:rgba(255,255,255,235);"
            "border:1px solid rgba(255,90,69,90);border-radius:8px;}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)

        self.ring = FocusProgressRing(self)
        row.addWidget(self.ring)

        col = QVBoxLayout()
        col.setSpacing(0)
        self.goal_label = QLabel("집중 목표", self)
        self.goal_label.setStyleSheet(
            "font-size:12px;font-weight:700;color:#172033;background:transparent;"
        )
        col.addWidget(self.goal_label)

        sub = QHBoxLayout()
        sub.setSpacing(8)
        self.percent_label = QLabel("0%", self)
        self.percent_label.setStyleSheet(
            f"font-size:14px;font-weight:700;color:{FOCUS_ACCENT_COLOR};background:transparent;"
        )
        sub.addWidget(self.percent_label)
        self.remaining_label = QLabel("00:00", self)
        self.remaining_label.setStyleSheet(
            "font-size:12px;color:#555;background:transparent;"
        )
        sub.addWidget(self.remaining_label)
        sub.addStretch()
        col.addLayout(sub)
        row.addLayout(col, 1)

        self.close_btn = TransparentToolButton(FIF.CLOSE, self)
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setIconSize(QSize(9, 9))
        self.close_btn.setToolTip("종료")
        self.close_btn.clicked.connect(self.close_requested.emit)
        row.addWidget(self.close_btn, 0, Qt.AlignTop)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._sync)
        self._timer.start()
        self._sync()

    def _sync(self):
        src = self._source
        if src is None:
            return
        tm = src.timer_model
        self.ring.set_progress(tm.progress_ratio())
        self.percent_label.setText(f"{tm.progress_percent()}%")
        self.remaining_label.setText(src._format_remaining(tm.remaining_seconds()))
        self.goal_label.setText("휴식 중" if tm.phase == "break" else (src._goal or "집중 목표"))


class FocusSidePanel(QWidget):
    """'크게' 모드 우측 컬럼의 집중 모드 미니 패널(0~1개)."""

    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("focusSidePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(110)
        self.setStyleSheet(
            "#focusSidePanel{background:#FFFFFF;border:1px solid rgba(206,210,216,180);"
            "border-top:none;}"
        )
        self._card = None

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(12, 10, 12, 10)
        self._outer.setSpacing(8)

        title = QLabel("집중 모드", self)
        title.setStyleSheet("font-size:13px;font-weight:700;color:#212121;")
        self._outer.addWidget(title)

        self._empty_label = QLabel("진행 중인 집중 모드가 없습니다.", self)
        self._empty_label.setStyleSheet("color:#888888;font-size:12px;")
        self._outer.addWidget(self._empty_label)
        self._outer.addStretch()

    def bind(self, source_window):
        self.clear()
        self._card = FocusMiniCard(source_window, self)
        self._card.close_requested.connect(self.close_requested.emit)
        self._outer.insertWidget(2, self._card)
        self._empty_label.hide()

    def clear(self):
        if self._card is not None:
            self._outer.removeWidget(self._card)
            self._card.deleteLater()
            self._card = None
        self._empty_label.show()
