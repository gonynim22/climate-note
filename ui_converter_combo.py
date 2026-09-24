"""환산기 전용 콤보의 공통 표시와 즉시 팝업. 데이터/설정 저장 없음."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QComboBox, QStyledItemDelegate


class ConverterCombo(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("""
            QComboBox { font-size:13px; padding:2px 6px; }
            QComboBox QAbstractItemView {
                background:#FFFFFF; color:#292C33; border:1px solid #CDD5E0;
                selection-background-color:#E3EAF4; selection-color:#1E385C;
                font-size:13px; padding:4px; outline:0;
            }
            QComboBox QAbstractItemView::item { min-height:28px; padding:0 8px; }
        """)
        # 기본 Windows 콤보 delegate 대신 동일한 QSS 행 표현을 사용한다.
        self.view().setItemDelegate(QStyledItemDelegate(self.view()))

    def display_text(self):
        return self.currentText()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#829BBC" if self.hasFocus() else "#DDDFE3"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)
        painter.setPen(QColor("#3E4653"))
        text_rect = self.rect().adjusted(7, 0, -22, 0)
        text = self.fontMetrics().elidedText(self.display_text(), Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignVCenter, text)
        x, y = self.width()-12, self.height()//2
        painter.setPen(QPen(QColor("#818B9A"), 1.2))
        painter.drawLine(x-3, y-1, x, y+2)
        painter.drawLine(x, y+2, x+3, y-1)

    def showPopup(self):
        # Qt 6.11의 150ms QRollEffect는 부분 이미지→실제 목록 전환을 만든다.
        # 이 동기 호출에만 억제하고 다른 콤보의 애니메이션 설정은 즉시 복원한다.
        animated = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, False)
        try:
            super().showPopup()
        finally:
            QApplication.setEffectEnabled(Qt.UI_AnimateCombo, animated)
