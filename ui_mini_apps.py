"""개발자 제공 미니앱의 실행 주머니(A안 앱 런처). 사용자 데이터나 DB에 접근하지 않는다."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLayout, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from app_paths import resource_root
from fluent_icons import fluent_icon

TILE_WIDTH, TILE_HEIGHT = 104, 100
POCKET_WIDTH, POCKET_HEIGHT = 252, 280
SHADOW_MARGIN = 24
TILE_SLOTS = 4


def mini_app_icon(name: str) -> QIcon:
    """번들 `resources/icons/mini_apps/<name>.svg`. 경로는 resource_root()만 기준으로 만든다."""
    return QIcon(str(resource_root() / "resources" / "icons" / "mini_apps" / f"{name}.svg"))


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
        self.setIcon(mini_app_icon("launcher"))
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(64, 48)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QToolButton{background:#FFFFFF;border:1px solid #D9E1EC;"
            "border-radius:10px;color:#253447;font-size:11px;font-weight:bold;}"
            "QToolButton:hover{background:#F5F8FC;}"
            "QToolButton:checked{background:#EAF2FE;border-color:#8DB4F0;color:#1D4ED8;}"
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
    money_notation_requested = Signal()
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
            "QFrame#miniAppsCard{background:#FFFFFF;border:1px solid #D9E1EC;border-radius:16px;}"
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
        header_widget.setFixedHeight(48)
        header_widget.setStyleSheet("QFrame#miniAppsHeader{background:transparent;border:0;}")
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(18, 0, 10, 0)
        header.setSpacing(6)
        title = QLabel("미니앱", header_widget)
        title.setObjectName("miniAppsTitle")
        title.setStyleSheet("color:#172B4D;font-size:15px;font-weight:bold;")
        header.addWidget(title)
        self.count_label = QLabel(header_widget)
        self.count_label.setObjectName("miniAppsCount")
        self.count_label.setStyleSheet("color:#7A8699;font-size:11px;padding-top:3px;")
        header.addWidget(self.count_label)
        header.addStretch()
        self.close_button = QToolButton(header_widget)
        self.close_button.setText("×")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setAccessibleName("미니앱 주머니 닫기")
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setStyleSheet(
            "QToolButton{background:transparent;border:0;border-radius:8px;color:#7A8699;font-size:19px;}"
            "QToolButton:hover,QToolButton:focus{background:#F1F4F8;color:#253447;}"
        )
        self.close_button.clicked.connect(self.dismiss)
        header.addWidget(self.close_button)
        layout.addWidget(header_widget)
        tiles = QWidget(self.card)
        tiles_layout = QVBoxLayout(tiles)
        # 오른쪽 8px 뒤의 6px은 앱이 5개 이상일 때의 스크롤바 자리다.
        # 카드 테두리 1px이 위아래 2px을 차지하므로 48+6+100+10+100+14+2=280이다.
        tiles_layout.setContentsMargins(16, 6, 8, 14)
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
        self.apps_grid.setHorizontalSpacing(12)
        self.apps_grid.setVerticalSpacing(10)
        self.apps_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.apps_grid.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.apps_scroll.setWidget(content)
        tiles_layout.addWidget(self.apps_scroll)
        layout.addWidget(tiles, 1)
        self.converter_card = self.add_app(
            "단위 환산기", "unit_converter", "길이·무게·온도·환경 단위 환산",
            self.unit_converter_requested.emit, icon=mini_app_icon("unit_converter"),
        )
        self.converter_card.setObjectName("unitConverterCard")
        self.date_time_card = self.add_app(
            "날짜·시간\n계산기", "date_time", "날짜·근무일·시간 차이·시간 합산",
            self.date_time_calculator_requested.emit, icon=mini_app_icon("date_time"),
        )
        self.date_time_card.setObjectName("dateTimeCalculatorCard")
        self.date_time_card.setAccessibleName("날짜·시간 계산기 실행")
        self.money_card = self.add_app(
            "금액·숫자\n표기", "money_notation", "공문서 금액·억·만 읽기·금액 단위 환산",
            self.money_notation_requested.emit, icon=mini_app_icon("money_notation"),
        )
        self.money_card.setObjectName("moneyNotationCard")
        self.money_card.setAccessibleName("금액·숫자 표기 도우미 실행")
        for index in range(self._app_count, TILE_SLOTS):
            card = self._make_tile("준비 중", mini_app_icon("upcoming"))
            card.setObjectName(f"upcomingMiniApp{index}")
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
        card.setIconSize(QSize(48, 48))
        card.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        card.setFocusPolicy(Qt.StrongFocus)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            "QToolButton{background:transparent;border:2px solid transparent;border-radius:12px;"
            "color:#253447;font-size:12px;padding:4px 2px 2px 2px;}"
            "QToolButton:hover{background:#F2F6FC;}"
            "QToolButton:pressed{background:#E7EEF9;}"
            "QToolButton:focus{border-color:#2563EB;}"
            "QToolButton:disabled{background:transparent;color:#9AA6B5;}"
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
        self.count_label.setText(f"{self._app_count}개")
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
