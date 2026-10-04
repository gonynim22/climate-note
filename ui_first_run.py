"""DB를 만들기 전에 표시하는 최초 크기 선택. 미리보기는 순수 벡터 그림이다."""
from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QBoxLayout, QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout,
)
from qfluentwidgets import isDarkTheme
from shiboken6 import isValid


SETUP_WINDOW_TITLE = "기후노트 — 처음 설정"
SIZE_CHOICES = (
    ("compact", "기본", "작게 띄워두기", "작업 화면 옆에 작은 캘린더를 두고 사용해요."),
    ("medium", "중간", "일정도 함께 보기", "달력과 일정 목록을 나란히 넉넉하게 봐요."),
    ("large", "크게", "위젯까지 한눈에", "달력·일정·메모와 위젯을 한 화면에 모아요."),
)


class _SizeCard(QPushButton):
    def __init__(self, choice, parent):
        super().__init__(parent)
        self.scale, self.label, self.caption, _ = choice
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setAccessibleName(f"{self.label}: {self.caption}")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(0, 64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event):
        dark = isDarkTheme()
        selected = self.isChecked()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#60A5FA" if dark else "#2563EB") if selected else
                      QColor("#475569" if dark else "#DDE4EE"), 2 if selected else 1))
        p.setBrush(QColor(("#203656" if dark else "#EFF6FF") if selected else
                          ("#263140" if dark else "#FFFFFF")))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 12, 12)
        stacked = self.height() < 130
        if stacked:
            preview = QRectF(14, 12, min(105, self.width() * .28), self.height() - 24)
            text_x, text_y = preview.right() + 16, self.height() / 2 - 22
        else:
            preview = QRectF(15, 22, self.width() - 30, self.height() - 103)
            text_x, text_y = 18, self.height() - 65
        self._draw_preview(p, preview, dark)
        font = QFont(self.font())
        font.setPixelSize(17)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#F1F5F9" if dark else "#01295F"))
        p.drawText(QRectF(text_x, text_y, self.width() - text_x - 32, 26), self.label)
        font.setPixelSize(12)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor("#BCCBDD" if dark else "#64748B"))
        p.drawText(QRectF(text_x, text_y + 27, self.width() - text_x - 12, 22), self.caption)
        mark = QRectF(self.width() - 31, text_y + 4, 14, 14)
        p.setPen(QPen(QColor("#60A5FA" if dark else "#2563EB") if selected else
                      QColor("#94A3B8"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(mark)
        if selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#60A5FA" if dark else "#2563EB"))
            p.drawEllipse(mark.adjusted(3.5, 3.5, -3.5, -3.5))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#60A5FA" if dark else "#2563EB"), 1, Qt.DotLine))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(6, 6, -6, -6), 9, 9)

    def _draw_preview(self, p, bounds, dark):
        # 160×100의 동일한 화면 안에서 세 크기의 상대적인 면적을 비교한다.
        p.save()
        ratio = min(bounds.width() / 160, bounds.height() / 100)
        p.translate(bounds.center().x() - 80 * ratio, bounds.center().y() - 50 * ratio)
        p.scale(ratio, ratio)
        p.setPen(QPen(QColor("#64748B" if dark else "#C1CDDE"), 1.5))
        p.setBrush(QColor("#172435" if dark else "#E9EFF7"))
        p.drawRoundedRect(QRectF(1, 1, 158, 91), 5, 5)
        p.drawLine(80, 93, 80, 98)
        p.drawLine(60, 99, 100, 99)
        x, y, w, h = {"compact": (112, 27, 40, 58),
                       "medium": (58, 24, 94, 61), "large": (8, 8, 144, 77)}[self.scale]
        p.setPen(QPen(QColor("#9EBAE4"), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(x, y, w, h), 3, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2563EB"))
        p.drawRoundedRect(QRectF(x + 4, y + 5, w * .38, 3), 1, 1)
        grid_w = w - 8 if self.scale == "compact" else w * .55
        for row in range(5):
            for col in range(7):
                p.setBrush(QColor("#93B6EC" if (row, col) == (2, 3) else "#DBE5F3"))
                p.drawRoundedRect(QRectF(x + 4 + col * grid_w / 7, y + 15 + row * (h - 22) / 5,
                                         grid_w / 7 - 1.5, (h - 22) / 5 - 2), 1, 1)
        if self.scale != "compact":
            for row in range(4):
                p.setBrush(QColor(("#DBEAFE", "#FEF3C7", "#DCFCE7", "#EDE9FE")[row]))
                p.drawRoundedRect(QRectF(x + grid_w + 8, y + 15 + row * (h - 22) / 4,
                                         w - grid_w - 12, (h - 22) / 4 - 3), 2, 2)
        p.restore()


class FirstRunSizeDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(SETUP_WINDOW_TITLE)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.selected_scale = "compact"
        self.cards = []
        self._connected_screen = None
        self.setObjectName("firstRun")
        dark = isDarkTheme()
        self.setStyleSheet(f"""
            QDialog#firstRun {{ background: {'#182230' if dark else '#FFFFFF'};
                border: 1px solid {'#475569' if dark else '#DDE4EE'}; border-radius: 12px; }}
            QLabel {{ color: {'#F1F5F9' if dark else '#01295F'}; background: transparent; }}
            QLabel#muted {{ color: {'#BCCBDD' if dark else '#64748B'}; font-size: 12px; }}
            QPushButton {{ font-size: 13px; padding: 8px 16px; border-radius: 7px;
                color: {'#F1F5F9' if dark else '#334155'};
                background: {'#263140' if dark else '#F1F5F9'}; border: 1px solid transparent; }}
            QPushButton:focus {{ border: 1px solid #60A5FA; }}
            QPushButton#start {{ color: white; background: #2563EB; font-weight: bold; }}
            QPushButton#start:hover {{ background: #1D4ED8; }}
            QPushButton#close {{ padding: 0; background: transparent; font-size: 20px; }}
        """)
        self.root = QVBoxLayout(self)
        # 세로 → 가로 변경 직후 Qt가 이전 최소 높이를 강제하지 않게 한다.
        self.root.setSizeConstraint(QLayout.SetNoConstraint)
        self.root.setContentsMargins(24, 18, 24, 22)
        self.root.setSpacing(10)
        header = QHBoxLayout()
        self.brand = QLabel("기후노트  ·  처음 설정")
        self.brand.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.brand.installEventFilter(self)
        header.addWidget(self.brand, 1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("close")
        self.close_button.setAccessibleName("종료")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setAutoDefault(True)
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        self.root.addLayout(header)
        self.heading = QLabel("어떤 크기로 시작할까요?")
        self.heading.setStyleSheet("font-size: 25px; font-weight: bold;")
        self.heading.setWordWrap(True)
        self.root.addWidget(self.heading)
        self.subtitle = QLabel("크기를 선택하면 이 모습으로 시작해요.")
        self.subtitle.setObjectName("muted")
        self.root.addWidget(self.subtitle)
        self.cards_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.cards_layout.setSpacing(12)
        for choice in SIZE_CHOICES:
            card = _SizeCard(choice, self)
            card.clicked.connect(lambda checked=False, scale=choice[0]: self._select(scale))
            card.installEventFilter(self)
            self.cards_layout.addWidget(card, 1)
            self.cards.append(card)
        self.root.addLayout(self.cards_layout, 1)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setStyleSheet("font-size: 13px;")
        self.root.addWidget(self.description)
        self.hint = QLabel("나중에 설정에서 언제든 바꿀 수 있어요.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.root.addWidget(self.hint)
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_button = QPushButton("종료")
        self.cancel_button.setAutoDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.start_button = QPushButton("이 크기로 시작 →")
        self.start_button.setObjectName("start")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.accept)
        actions.addWidget(self.start_button)
        self.root.addLayout(actions)
        self._select("compact")
        self.setTabOrder(self.close_button, self.cards[0])
        self.setTabOrder(self.cards[0], self.cards[1])
        self.setTabOrder(self.cards[1], self.cards[2])
        self.setTabOrder(self.cards[2], self.cancel_button)
        self.setTabOrder(self.cancel_button, self.start_button)
        self.cards[0].setFocus()

    def _select(self, scale):
        self.selected_scale = scale
        for card, choice in zip(self.cards, SIZE_CHOICES):
            card.setChecked(choice[0] == scale)
            if choice[0] == scale:
                self.description.setText(choice[3])

    def _step(self, direction):
        index = next(i for i, c in enumerate(self.cards) if c.scale == self.selected_scale)
        card = self.cards[(index + direction) % len(self.cards)]
        self._select(card.scale)
        card.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.brand and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton and self.windowHandle():
                self.windowHandle().startSystemMove()
        if watched in self.cards and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down):
                self._step(-1 if event.key() in (Qt.Key_Left, Qt.Key_Up) else 1)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Right, Qt.Key_Down):
            self._step(-1 if event.key() in (Qt.Key_Left, Qt.Key_Up) else 1)
        else:
            super().keyPressEvent(event)

    def fit_to_available_geometry(self, area):
        width, height = min(680, area.width() - 24), min(500, area.height() - 24)
        narrow = width < 580
        self.cards_layout.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        self.root.setContentsMargins(16 if narrow else 24, 14, 16 if narrow else 24, 16)
        self.root.setSpacing(6 if height < 470 else 10)
        self.cards_layout.setSpacing(6 if height < 470 else 12)
        self.heading.setStyleSheet(f"font-size: {20 if narrow else 25}px; font-weight: bold;")
        self.resize(width, height)
        self.move(area.center() - self.rect().center())

    def _screen_changed(self, screen):
        if self._connected_screen is not None and isValid(self._connected_screen):
            self._connected_screen.availableGeometryChanged.disconnect(self.fit_to_available_geometry)
        self._connected_screen = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self.fit_to_available_geometry)
            self.fit_to_available_geometry(screen.availableGeometry())

    def showEvent(self, event):
        super().showEvent(event)
        if self._connected_screen is None:
            self.windowHandle().screenChanged.connect(self._screen_changed)
            self._screen_changed(self.screen())
