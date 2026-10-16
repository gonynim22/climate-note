# ui_search.py - 일정/메모 검색 창
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor

from qfluentwidgets import (
    LineEdit, PrimaryPushButton, PushButton, CaptionLabel,
    FluentIcon as FIF, TransparentToolButton
)

import database as db
from schedule_rules import ScheduleOptions, search_suffix
from ui_window_card import TABLE_QSS, WindowCard

SEARCH_HINT = "검색어를 입력하고 Enter를 누르세요.\n[전체 검색]은 모든 일정과 메모를 보여 줍니다."
NO_RESULTS = "검색 결과가 없습니다."


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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        # 설정 창과 같은 흰 카드(선 아이콘 제목). 이하 내용은 카드 본문에 둔다.
        self.card = WindowCard("일정 / 메모 검색", FIF.SEARCH, self)
        outer.addWidget(self.card)
        layout = self.card.body

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
        self.result_table.setStyleSheet(TABLE_QSS)
        self.result_table.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.result_table, 1)
        # 결과가 없을 때는 큰 빈 표 대신 안내를 보인다.
        self.empty_label = self.card.empty_label(SEARCH_HINT)
        layout.addWidget(self.empty_label, 1)
        self._show_results(False)

    def _show_results(self, has_rows, message=SEARCH_HINT):
        self.result_table.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.empty_label.setText(message)

    def _on_search(self, search_all=False):
        keyword = "" if search_all else self.search_input.text().strip()
        
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(0)
        
        if not keyword and not search_all:
            self.result_count_label.setText("")
            self.result_table.setSortingEnabled(True)
            self._show_results(False)
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
            if r["type"] == "일정":
                # 반복·기간은 원본 한 줄(시작 날짜)에 표시용 꼬리만 붙인다(저장값은 그대로).
                content_text += search_suffix(r["date"], ScheduleOptions(
                    end_date=r.get("end_date", ""), repeat_rule=r.get("repeat_rule", "")))
            content_item = QTableWidgetItem(content_text)
            content_item.setToolTip(r["content"]) # 마우스를 올리면 전체 내용을 볼 수 있도록
            
            self.result_table.setItem(row, 0, date_item)
            self.result_table.setItem(row, 1, type_item)
            self.result_table.setItem(row, 2, content_item)
            
        self.result_table.setSortingEnabled(True)
        self._show_results(bool(results), NO_RESULTS)

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
