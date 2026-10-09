# ui_mini_app_frame.py - 미니앱 공용 창 틀(디자인 점검 5번 B안)의 어두운 제목줄
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from app_paths import resource_root

FRAME_DARK = "#23252B"      # 제목줄과 왼쪽 메뉴
FRAME_SURFACE = "#FDFDFB"   # 본문
TITLE_BAR_HEIGHT = 48
TITLE_BAR_COMPACT_HEIGHT = 40
TITLE_ICON_SIZE = 22


def mini_app_icon_path(app_id: str) -> Path:
    """주머니와 같은 미니앱 아이콘. 경로는 resource_root()만 기준으로 만든다."""
    return resource_root() / "resources" / "icons" / "mini_apps" / f"{app_id}.svg"


class MiniAppTitleBar(QFrame):
    """앱 아이콘 · 이름 · 닫기(×). 창 끌기는 창이 이 위젯에 eventFilter를 걸어 처리한다.

    아이콘과 이름은 마우스를 받지 않아 누르기가 제목줄로 전달된다.
    """

    def __init__(self, title, icon_path, on_close, parent=None):
        super().__init__(parent)
        self.setObjectName("miniAppTitleBar")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setStyleSheet(f"""
            QFrame#miniAppTitleBar {{ background:{FRAME_DARK}; border:0;
                border-top-left-radius:16px; border-top-right-radius:16px; }}
            QLabel#miniAppTitle {{ color:#F4F5F2; font-size:15px; font-weight:bold; background:transparent; }}
            QLabel#miniAppIcon {{ background:transparent; }}
            QPushButton#miniAppClose {{ background:transparent; color:#C9CED8; border:1px solid transparent;
                border-radius:8px; font-size:20px; padding:0; }}
            QPushButton#miniAppClose:hover {{ background:#343740; color:#FFFFFF; }}
            QPushButton#miniAppClose:focus {{ border-color:#90ACD0; }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(10)
        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("miniAppIcon")
        self.icon_label.setFixedSize(TITLE_ICON_SIZE, TITLE_ICON_SIZE)
        self.icon_label.setPixmap(QIcon(str(icon_path)).pixmap(TITLE_ICON_SIZE, TITLE_ICON_SIZE))
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("miniAppTitle")
        for label in (self.icon_label, self.title_label):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        layout.addStretch()
        self.close_button = QPushButton("×", self)
        self.close_button.setObjectName("miniAppClose")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.setAccessibleName(f"{title} 닫기")
        self.close_button.clicked.connect(on_close)
        layout.addWidget(self.close_button)

    def set_compact(self, compact: bool) -> None:
        self.setFixedHeight(TITLE_BAR_COMPACT_HEIGHT if compact else TITLE_BAR_HEIGHT)
