"""개발자 제공 미니앱의 실행 주머니. 사용자 데이터나 DB에 접근하지 않는다."""
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from fluent_icons import fluent_icon


def pocket_position(anchor: QRect, size: QSize, available: QRect) -> QPoint:
    """버튼 오른쪽 우선, 공간 부족 시 왼쪽, 마지막으로 작업 영역에 보정."""
    x = anchor.right() + 9
    if x + size.width() > available.right() + 1:
        x = anchor.left() - size.width() - 8
    return QPoint(
        max(available.left(), min(x, available.right() + 1 - size.width())),
        max(available.top(), min(anchor.top(), available.bottom() + 1 - size.height())),
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

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("miniAppsPocket")
        self.setAccessibleName("미니앱 주머니")
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 바깥의 원래 버튼 클릭이 재전달되어 곧바로 다시 열리는 것을 막는다.
        self.setAttribute(Qt.WA_NoMouseReplay)
        self._return_focus = False
        self.resize(332, 332)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(14)
        header = QHBoxLayout()
        title = QLabel("미니앱", self)
        title.setStyleSheet("color:#01295F;font-size:15px;font-weight:bold;")
        header.addWidget(title)
        header.addStretch()
        self.close_button = QToolButton(self)
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
        layout.addLayout(header)
        self.apps_scroll = QScrollArea(self)
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
        layout.addWidget(self.apps_scroll, 1)
        self.converter_card = self.add_app(
            "단위 환산기", "unit_converter", "길이·무게·온도·환경 단위 환산",
            self.unit_converter_requested.emit,
        )
        self.converter_card.setObjectName("unitConverterCard")

    def add_app(self, title, icon_name, description, callback):
        """개발자가 등록한 타일을 행 우선 2열로 추가한다. 사용자 슬롯과 별개다."""
        card = MiniAppTile(self.apps_scroll.widget())
        card.setText(title)
        card.setAccessibleName(f"{title} 실행")
        card.setToolTip(description)
        card.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        card.setIcon(fluent_icon(icon_name, "#46679C", 80))
        card.setIconSize(QSize(40, 40))
        card.setFixedSize(132, 132)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            "QToolButton{background:#F4F7FB;border:1px solid #D9E2ED;"
            "border-radius:14px;color:#294B73;font-size:13px;font-weight:bold;padding:10px;}"
            "QToolButton:hover{background:#EAF1FA;border-color:#96B2D5;}"
            "QToolButton:focus{border:2px solid #46679C;}"
        )
        card.clicked.connect(callback)
        row, column = divmod(self.apps_grid.count(), 2)
        self.apps_grid.addWidget(card, row, column)
        card.show()
        return card

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#CBD5E1"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)

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
