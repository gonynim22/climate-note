# ui_search.py - 일정/메모 검색 창
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from qfluentwidgets import (
    LineEdit, PrimaryPushButton, PushButton, BodyLabel, CaptionLabel,
    FluentIcon as FIF, TransparentToolButton
)

import database as db


class SearchWindow(QWidget):
    """일정/메모 검색 창"""
    date_selected = Signal(str)  # 결과 클릭 시 날짜 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("일정 검색")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setMinimumSize(420, 500)
        self.resize(420, 500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 제목
        title = BodyLabel("📅 일정 / 메모 검색", self)
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # 검색 입력
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.search_input = LineEdit(self)
        self.search_input.setPlaceholderText("검색어를 입력하세요...")
        self.search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self.search_input, 1)

        search_btn = PrimaryPushButton("검색", self)
        search_btn.setFixedWidth(60)
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)

        all_btn = PushButton("전체 검색", self)
        all_btn.setFixedWidth(95)  # 글자가 잘리지 않도록 크기 늘림
        all_btn.setToolTip("모든 일정/메모 보기")
        all_btn.clicked.connect(self._on_search_all)
        search_row.addWidget(all_btn)
        layout.addLayout(search_row)

        # 결과 개수
        self.result_count_label = CaptionLabel("", self)
        self.result_count_label.setStyleSheet("color: gray;")
        layout.addWidget(self.result_count_label)

        # 결과 테이블
        self.result_table = QTableWidget(self)
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["날짜", "구분", "내용"])
        
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.result_table.setSortingEnabled(True)
        self.result_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.result_table.setShowGrid(True)  # 그리드라인 보이게 유지
        self.result_table.setAlternatingRowColors(False)
        
        self.result_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #37352f;
                border: 1px solid #ededed;
                border-radius: 4px;
                gridline-color: #ededed;
                outline: none;
            }
            QTableWidget::item {
                padding: 8px 12px; /* 넉넉한 상하좌우 패딩 */
                border-bottom: none;
            }
            QTableWidget::item:selected {
                background-color: #ebeced; /* 옅은 회색 파스텔톤 선택 배경 */
                color: #37352f;
            }
            QHeaderView::section {
                background-color: #f7f7f5;
                color: #37352f;
                padding: 8px 12px;
                font-weight: 500;
                font-size: 13px;
                text-align: left;
                border: none;
                border-bottom: 1px solid #ededed;
                border-right: 1px solid #ededed;
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QHeaderView {
                background-color: transparent;
                border: none;
            }
        """)
        self.result_table.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.result_table, 1)

    def _on_search(self, search_all=False):
        keyword = "" if search_all else self.search_input.text().strip()
        
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(0)
        
        if not keyword and not search_all:
            self.result_count_label.setText("")
            self.result_table.setSortingEnabled(True)
            return

        results = db.search_all(keyword)
        self.result_count_label.setText(f"검색 결과: {len(results)}건")

        self.result_table.setRowCount(len(results))
        schedule_palette = db.get_schedule_palette()

        for row, r in enumerate(results):
            date_item = QTableWidgetItem(r["date"])
            date_item.setData(Qt.UserRole, r["date"]) # 결과 클릭 시 날짜 필터를 위해 UserRole에 저장
            
            if r["type"] == "일정":
                # 이모지 사각형은 OS 고정색이라 사용자 팔레트를 표현할 수 없다.
                # 일정 행의 canonical 슬롯은 그대로 두고 표시색만 설정에서 해석한다.
                badge = "■"
                badge_color = db.schedule_display_color(
                    r.get("color", ""), schedule_palette
                )
            else:
                badge = "📝" # 메모
                badge_color = None
            
            type_item = QTableWidgetItem(badge)
            type_item.setTextAlignment(Qt.AlignCenter)
            if badge_color is not None:
                type_item.setForeground(QBrush(QColor(badge_color)))
            
            content_text = r["content"].replace('\n', ' ')
            if len(content_text) > 80:
                content_text = content_text[:80] + "..."
            content_item = QTableWidgetItem(content_text)
            content_item.setToolTip(r["content"]) # 마우스를 올리면 전체 내용을 볼 수 있도록
            
            self.result_table.setItem(row, 0, date_item)
            self.result_table.setItem(row, 1, type_item)
            self.result_table.setItem(row, 2, content_item)
            
        self.result_table.setSortingEnabled(True)

    def _on_item_clicked(self, item):
        date_item = self.result_table.item(item.row(), 0)
        if date_item:
            date_str = date_item.data(Qt.UserRole)
            if date_str:
                self.date_selected.emit(date_str)

    def _on_search_all(self):
        """키워드 없이 전체 일정/메모 표시"""
        self._on_search(search_all=True)

    def showEvent(self, event):
        super().showEvent(event)
        self.search_input.setFocus()
        self.search_input.selectAll()
