"""개발자 제공 미니앱의 실행 주머니. 사용자 데이터나 DB에 접근하지 않는다."""
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

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
        self.resize(300, 220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 14, 18)
        layout.setSpacing(8)
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
        layout.addStretch()
        self.converter_card = QToolButton(self)
        self.converter_card.setObjectName("unitConverterCard")
        self.converter_card.setText("단위 환산기\n길이 · 무게 · 온도 등 21개 분류")
        self.converter_card.setAccessibleName("단위 환산기 실행")
        self.converter_card.setToolTip("단위 환산기 열기")
        self.converter_card.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.converter_card.setIcon(fluent_icon("unit_converter", "#46679C", 64))
        self.converter_card.setIconSize(QSize(32, 32))
        self.converter_card.setMinimumHeight(78)
        self.converter_card.setCursor(Qt.PointingHandCursor)
        self.converter_card.setStyleSheet(
            "QToolButton{background:#F4F7FB;border:1px solid #D9E2ED;"
            "border-radius:10px;color:#294B73;font-size:11px;padding:10px;}"
            "QToolButton:hover{background:#EAF1FA;border-color:#96B2D5;}"
            "QToolButton:focus{border:2px solid #46679C;}"
        )
        self.converter_card.clicked.connect(self.unit_converter_requested)
        layout.addWidget(self.converter_card)
        layout.addStretch()

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
            if event.key() != Qt.Key_Escape and self.converter_card.hasFocus():
                self.unit_converter_requested.emit()
            else:
                self.dismiss()
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.dismissed.emit(self._return_focus)
