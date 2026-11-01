# ui_dday_panel.py - '크게' 모드 우측 컬럼의 편집 가능한 미니 D-Day 패널
import logging
import sqlite3
from datetime import date

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QLabel, QHBoxLayout, QGridLayout, QVBoxLayout, QWidget, QSizePolicy

import database as db
from ui_dday import dday_cover_color, _dday_font, _CoverIconButton

_logger = logging.getLogger("app_error")


class _ElidedLabel(QLabel):
    """긴 한 줄 텍스트가 카드/그리드 폭을 밀어내지 않도록 말줄임표 처리."""

    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self._full_text = text or ""
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(self._full_text)
        self._update_elide()

    def _update_elide(self):
        width = self.contentsRect().width()
        if width <= 0:
            width = 80
        QLabel.setText(
            self,
            QFontMetrics(self.font()).elidedText(
                self._full_text, Qt.ElideRight, width
            ),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()


class DDayMiniCard(QWidget):
    """우측 패널용 미니 D-Day 카드(더블클릭 편집, X 삭제)."""
    edit_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, widget_id, data, parent=None):
        super().__init__(parent)
        self.widget_id = widget_id
        self._name = data.get("name", "")
        self._target_date = data.get("target_date", "")
        self._color = data.get("color", db.DEFAULT_DDAY_COLOR)
        self._holiday_theme = None  # 공휴일 테마(표시 전용). 저장색과 따로 쥔다
        self.setObjectName("ddayMiniCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(56)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 6, 5, 7)
        outer.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(2)
        self.name_label = _ElidedLabel(self._name, self)
        self.name_label.setFont(_dday_font(11, QFont.Weight.DemiBold))  # 글자는 최소 11px(디자인 점검 16번)
        self.name_label.setStyleSheet(
            "color:rgba(255,255,255,217);background:transparent;"
        )
        top.addWidget(self.name_label, 1)

        self.close_btn = _CoverIconButton(16, 1.8, 128, self)
        self.close_btn.setToolTip("삭제")
        self.close_btn.clicked.connect(lambda: self.delete_requested.emit(self.widget_id))
        top.addWidget(self.close_btn, 0, Qt.AlignTop)
        outer.addLayout(top)

        outer.addStretch(1)

        self.count_label = QLabel("", self)
        self.count_label.setFont(_dday_font(16, QFont.Weight.ExtraBold))
        self.count_label.setStyleSheet("background:transparent;")
        outer.addWidget(self.count_label, 0, Qt.AlignLeft)

        self._apply_color(self._color)
        self._update_countdown()

    def _apply_color(self, hex_color):
        self._color = hex_color
        self._render_cover()

    def _render_cover(self) -> None:
        """지금 보일 커버 색(테마가 있으면 테마, 없으면 저장색)으로 카드를 그린다."""
        theme = self._holiday_theme
        cover = theme.cover if theme is not None else dday_cover_color(self._color)
        self.setStyleSheet(
            f"#ddayMiniCard{{background:{cover};"
            "border:none;border-radius:12px;}"
        )

    def set_holiday_theme(self, theme) -> None:
        """공휴일 테마(HolidayTheme 또는 None)를 화면에만 입힌다. DB에는 쓰지 않는다."""
        self._holiday_theme = theme
        self._render_cover()

    def _update_countdown(self):
        try:
            target = date.fromisoformat(self._target_date)
        except (ValueError, TypeError):
            self.count_label.setText("?")
            return
        delta = (target - date.today()).days
        if delta > 0:
            self.count_label.setText(f"D-{delta}")
            self.count_label.setStyleSheet("color:#FFFFFF;background:transparent;")
        elif delta == 0:
            self.count_label.setText("D-Day")
            self.count_label.setStyleSheet("color:#FFFFFF;background:transparent;")
        else:
            self.count_label.setText(f"D+{abs(delta)}")
            self.count_label.setStyleSheet(
                "color:rgba(255,255,255,140);background:transparent;"
            )

    def refresh(self):
        self._update_countdown()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.edit_requested.emit(self.widget_id)


class DDayActionCard(QWidget):
    """D-Day 그리드의 빈 칸을 채우는 추가/제한 안내 카드."""
    clicked = Signal()
    ADD_DASH_PATTERN = [6.0, 5.0]

    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self._hovered = False
        self.setObjectName("ddayActionCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(54)
        self.setCursor(Qt.PointingHandCursor if mode == "add" else Qt.ArrowCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 5, 6, 5)
        outer.setSpacing(0)

        # 좁은 칸에서 두 줄로 깨지지 않게 한 줄 11px로 쓴다(디자인 점검 16번).
        title = QLabel("+ D-Day 추가" if mode == "add" else "최대 5개 · 삭제 후 추가", self)
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(mode != "add")
        title.setStyleSheet(
            "font-size:11px;font-weight:700;background:transparent;"
        )
        outer.addWidget(title, 1)

        if mode == "add":
            self.setStyleSheet(
                "#ddayActionCard{background:transparent;border:none;color:#6B7280;}"
            )
        else:
            self.setStyleSheet(
                "#ddayActionCard{background:#F6F7F9;border:1px solid #E0E3EA;"
                "border-radius:8px;color:#8A9099;}"
            )

    def paintEvent(self, event):
        if self.mode != "add":
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
        painter.setBrush(QColor("#F2F4F8" if self._hovered else "#F7F8FA"))
        pen = QPen(QColor("#9AA6BA" if self._hovered else "#C3CAD6"))
        pen.setWidthF(1.4)
        pen.setDashPattern(self.ADD_DASH_PATTERN)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 8, 8)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mode == "add" and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class DDaySidePanel(QWidget):
    """'크게' 모드 우측 컬럼의 미니 D-Day 패널(3열 그리드)."""
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    create_requested = Signal()
    _COLS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ddaySidePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(170)
        self.setStyleSheet(
            "#ddaySidePanel{background:#FFFFFF;border:1px solid rgba(206,210,216,180);"
            "border-top:none;}"
        )
        self._cards = []
        self._action_card = None
        self._holiday_theme = None  # reload()로 만드는 카드에도 입히려고 기억한다

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        title = QLabel("D-Day", self)
        title.setStyleSheet("font-size:13px;font-weight:700;color:#212121;")
        outer.addWidget(title)

        self._grid_host = QWidget(self)
        self._grid_host.setObjectName("ddayMiniGrid")
        self._grid_host.setStyleSheet("#ddayMiniGrid{background:transparent;}")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        for c in range(self._COLS):
            self._grid.setColumnStretch(c, 1)
        outer.addWidget(self._grid_host, 0, Qt.AlignTop)

        self._empty_label = QLabel("표시할 D-Day가 없습니다.", self)
        self._empty_label.setStyleSheet("color:#888888;font-size:12px;")
        outer.addWidget(self._empty_label)
        outer.addStretch(1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60_000)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start()

    def set_holiday_theme(self, theme) -> None:
        """공휴일 테마(HolidayTheme 또는 None)를 기억하고 지금 있는 카드에 입힌다. 화면 전용."""
        self._holiday_theme = theme
        for card in self._cards:
            card.set_holiday_theme(theme)

    def reload(self):
        for card in self._cards:
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards = []
        if self._action_card is not None:
            self._grid.removeWidget(self._action_card)
            self._action_card.deleteLater()
            self._action_card = None
        try:
            widgets = db.get_open_dday_widgets()
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 D-Day 목록 조회 실패: %s", e)
            widgets = []
        for idx, w in enumerate(widgets):
            card = DDayMiniCard(w["id"], w, self._grid_host)
            card.set_holiday_theme(self._holiday_theme)
            card.edit_requested.connect(self.edit_requested.emit)
            card.delete_requested.connect(self.delete_requested.emit)
            row, col = divmod(idx, self._COLS)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)

        if len(widgets) < 5:
            self._action_card = DDayActionCard("add", self._grid_host)
            self._action_card.clicked.connect(self.create_requested.emit)
            idx = len(widgets)
        else:
            self._action_card = DDayActionCard("limit", self._grid_host)
            idx = 5
        row, col = divmod(idx, self._COLS)
        self._grid.addWidget(self._action_card, row, col)
        self._empty_label.setVisible(not self._cards)

    def _refresh_all(self):
        for card in self._cards:
            card.refresh()
