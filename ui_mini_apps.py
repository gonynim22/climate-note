"""개발자 제공 미니앱의 실행 주머니. 사용자 데이터나 DB에 접근하지 않는다."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLayout, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from app_paths import resource_root
from fluent_icons import fluent_icon

TILE_SIZE = 92
POCKET_WIDTH = 240
POCKET_HEIGHT = 280
SHADOW_MARGIN = 24


def pocket_position(anchor: QRect, size: QSize, available: QRect, *, shadow_margin: int = 0) -> QPoint:
    """버튼 오른쪽 우선, 공간 부족 시 왼쪽, 마지막으로 작업 영역에 보정."""
    gap = 12 if shadow_margin else 8
    x = anchor.right() + 1 + gap - shadow_margin
    if x + size.width() > available.right() + 1:
        x = anchor.left() - size.width() - gap + shadow_margin
    return QPoint(
        max(available.left(), min(x, available.right() + 1 - size.width())),
        max(available.top(), min(anchor.top() - shadow_margin, available.bottom() + 1 - size.height())),
    )


class MiniAppsButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("miniAppsButton")
        self.setText("미니앱")
        self.setAccessibleName("미니앱 주머니")
        self.setToolTip("미니앱 주머니 열기/닫기")
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIcon(fluent_icon("apps", "#174B82", 40))
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(64, 48)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QToolButton{background:#EAF1FA;border:1px solid #C8D8EA;"
            "border-radius:8px;color:#174B82;font-size:11px;font-weight:bold;}"
            "QToolButton:hover{background:#DFEBF9;border-color:#8EB3DD;}"
            "QToolButton:checked{background:#D8E9FC;border-color:#4D8CCD;}"
            "QToolButton:focus{border:2px solid #2563EB;}"
        )

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
        else:
            super().keyPressEvent(event)


class MiniAppTile(QToolButton):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
        else:
            super().keyPressEvent(event)


class MiniAppsPocket(QWidget):
    dismissed = Signal(bool)
    unit_converter_requested = Signal()
    date_time_calculator_requested = Signal()
    shadow_margin = SHADOW_MARGIN

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("miniAppsPocket")
        self.setAccessibleName("미니앱 주머니")
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 바깥의 원래 버튼 클릭이 재전달되어 곧바로 다시 열리는 것을 막는다.
        self.setAttribute(Qt.WA_NoMouseReplay)
        self._return_focus = False
        self.pending_cards = []
        self._app_count = 0
        self.resize(POCKET_WIDTH + 2 * SHADOW_MARGIN, POCKET_HEIGHT + 2 * SHADOW_MARGIN)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.card = QFrame(self)
        self.card.setObjectName("miniAppsCard")
        self.card.setStyleSheet(
            "QFrame#miniAppsCard{background:#FFFFFF;border:1px solid #BCCDE1;border-radius:14px;}"
        )
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.card.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_widget = QFrame(self.card)
        header_widget.setObjectName("miniAppsHeader")
        header_widget.setFixedHeight(54)
        header_widget.setStyleSheet(
            "QFrame#miniAppsHeader{background:#EAF1FA;border:0;border-bottom:1px solid #D6E2EF;"
            "border-top-left-radius:13px;border-top-right-radius:13px;}"
        )
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(16, 0, 10, 0)
        header.setSpacing(7)
        icon = QLabel(header_widget)
        icon.setPixmap(fluent_icon("apps", "#315E91", 40).pixmap(QSize(20, 20)))
        header.addWidget(icon)
        title = QLabel("미니앱", header_widget)
        title.setStyleSheet("color:#01295F;font-size:15px;font-weight:bold;")
        header.addWidget(title)
        header.addStretch()
        self.close_button = QToolButton(header_widget)
        self.close_button.setText("×")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setAccessibleName("미니앱 주머니 닫기")
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QToolButton{background:transparent;border:1px solid transparent;"
            "border-radius:6px;color:#64748B;font-size:20px;}"
            "QToolButton:hover,QToolButton:focus{background:#EDF3FA;border-color:#B8CDE6;}"
        )
        self.close_button.clicked.connect(self.dismiss)
        header.addWidget(self.close_button)
        layout.addWidget(header_widget)
        tiles = QWidget(self.card)
        tiles_layout = QVBoxLayout(tiles)
        # 오른쪽 6px은 항목 증가 시 스크롤바를 위한 공간이다.
        tiles_layout.setContentsMargins(20, 14, 14, 14)
        self.apps_scroll = QScrollArea(tiles)
        self.apps_scroll.setWidgetResizable(True)
        self.apps_scroll.setFrameShape(QFrame.NoFrame)
        self.apps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.apps_scroll.setStyleSheet(
            "QScrollArea,QScrollArea > QWidget > QWidget{background:transparent;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#CBD5E1;border-radius:3px;min-height:24px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
        )
        content = QWidget()
        self.apps_grid = QGridLayout(content)
        self.apps_grid.setContentsMargins(0, 0, 0, 0)
        self.apps_grid.setSpacing(12)
        self.apps_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.apps_grid.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.apps_scroll.setWidget(content)
        tiles_layout.addWidget(self.apps_scroll)
        layout.addWidget(tiles, 1)
        self.converter_card = self.add_app(
            "단위 환산기", "unit_converter", "길이·무게·온도·환경 단위 환산",
            self.unit_converter_requested.emit,
            icon=QIcon(str(resource_root() / "resources" / "images" / "mini_apps" / "unit_converter_tile.png")),
        )
        self.converter_card.setObjectName("unitConverterCard")
        self.date_time_card = self.add_app(
            "날짜·시간\n계산기", "date_time", "날짜·근무일·시간 차이·시간 합산",
            self.date_time_calculator_requested.emit,
            icon=QIcon(str(resource_root() / "resources" / "icons" / "date_time.svg")),
        )
        self.date_time_card.setObjectName("dateTimeCalculatorCard")
        self.date_time_card.setAccessibleName("날짜·시간 계산기 실행")
        self.date_time_card.setIconSize(QSize(42, 42))
        for index in range(2, 4):
            card = self._make_tile("곧 출시\n예정", fluent_icon("apps", "#9BAABC", 64))
            card.setObjectName(f"upcomingMiniApp{index}")
            card.setIconSize(QSize(26, 26))
            card.setAccessibleName("곧 출시 예정")
            card.setEnabled(False)
            card.setFocusPolicy(Qt.NoFocus)
            card.setCursor(Qt.ArrowCursor)
            self.apps_grid.addWidget(card, *divmod(index, 2))
            self.pending_cards.append(card)

    def _make_tile(self, title, icon):
        card = MiniAppTile(self.apps_scroll.widget())
        card.setText(title)
        card.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        card.setIcon(icon)
        card.setIconSize(QSize(52, 52))
        card.setFixedSize(TILE_SIZE, TILE_SIZE)
        card.setFocusPolicy(Qt.StrongFocus)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            "QToolButton{background:#EDF4FD;border:1px solid #C6D7ED;"
            "border-radius:12px;color:#294B73;font-size:11px;font-weight:bold;padding:3px;}"
            "QToolButton:hover{background:#DFEDFF;border-color:#729CCF;}"
            "QToolButton:pressed{background:#D2E4FA;}"
            "QToolButton:focus{border:2px solid #3169AF;}"
            "QToolButton:disabled{background:#F7F9FC;border:1px dashed #CDD6E2;"
            "color:#778699;font-weight:normal;}"
        )
        return card

    def add_app(self, title, icon_name, description, callback, *, icon=None):
        """예정 자리를 순서대로 대체하고 이후 앱은 2열로 추가한다."""
        if self.pending_cards:
            pending = self.pending_cards.pop(0)
            self.apps_grid.removeWidget(pending)
            pending.hide()
            pending.deleteLater()
        card = self._make_tile(title, icon if icon is not None else fluent_icon(icon_name, "#46679C", 104))
        card.setAccessibleName(f"{title} 실행")
        card.setToolTip(description)
        card.clicked.connect(callback)
        row, column = divmod(self._app_count, 2)
        self._app_count += 1
        self.apps_grid.addWidget(card, row, column)
        card.show()
        return card

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.dismiss()
            event.accept()
        else:
            super().mousePressEvent(event)

    def dismiss(self):
        self._return_focus = True
        self.close()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.dismiss()
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.dismissed.emit(self._return_focus)
