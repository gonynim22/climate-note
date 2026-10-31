# ui_window_card.py - 검색·휴지통 같은 보조 창의 흰 카드(설정 섹션 카드와 같은 모양, 디자인 점검 9번)
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

CARD_BORDER = "#D7DAE2"   # 설정 섹션 카드 테두리와 같은 값
HEADER_BG = "#F6F6F6"     # 설정 섹션 머리줄과 같은 값
ACCENT = "#2563EB"
TABLE_QSS = """
    QTableWidget { background:#FFFFFF; color:#1A1A1E; border:1px solid #E6E9EF; border-radius:6px;
        gridline-color:#F2F3F6; outline:none; }
    QTableWidget::item { padding:8px 12px; border-bottom:none; }
    QTableWidget::item:selected { background:#EFF4FF; color:#1A1A1E; }
    QHeaderView { background:transparent; border:none; }
    QHeaderView::section { background:#F6F8FB; color:#5B6577; padding:8px 12px; font-weight:600; font-size:12px;
        border:none; border-bottom:1px solid #E6E9EF; border-right:1px solid #F2F3F6; }
    QHeaderView::section:last { border-right:none; }
"""


class WindowCard(QFrame):
    """밝은 머리줄(파랑 선 아이콘 + 굵은 제목)과 본문 레이아웃(`body`)을 가진 흰 카드."""

    def __init__(self, title, icon, parent=None):
        super().__init__(parent)
        self.setObjectName("windowCard")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(f"""
            QFrame#windowCard {{ background:#FFFFFF; border:1px solid {CARD_BORDER}; border-radius:11px; }}
            QWidget#windowCardHeader {{ background:{HEADER_BG}; border:0; border-bottom:1px solid {CARD_BORDER};
                border-top-left-radius:10px; border-top-right-radius:10px; }}
            QLabel#windowCardTitle {{ color:#1A1A1E; font-size:14px; font-weight:bold; background:transparent; }}
            QLabel#windowCardEmpty {{ color:#7A8699; font-size:13px; background:transparent; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        header = QWidget(self)
        header.setObjectName("windowCardHeader")
        header.setAttribute(Qt.WA_StyledBackground)
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(9)
        self.icon_label = QLabel(header)
        self.icon_label.setFixedSize(17, 17)
        self.icon_label.setScaledContents(True)
        self.icon_label.setPixmap(icon.icon(color=QColor(ACCENT)).pixmap(QSize(17, 17)))
        self.title_label = QLabel(title, header)
        self.title_label.setObjectName("windowCardTitle")
        row.addWidget(self.icon_label, 0, Qt.AlignVCenter)
        row.addWidget(self.title_label, 0, Qt.AlignVCenter)
        row.addStretch(1)
        layout.addWidget(header)
        content = QWidget(self)
        layout.addWidget(content, 1)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(10)

    def empty_label(self, text):
        """표가 비었을 때 표 자리에 보이는 가운데 안내 문구."""
        label = QLabel(text, self)
        label.setObjectName("windowCardEmpty")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        return label
