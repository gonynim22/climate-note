# ui_trash.py - 스티키 노트 휴지통 창 (복구 / 영구삭제 / 비우기)
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QTextDocument

from qfluentwidgets import (
    PrimaryPushButton, PushButton, BodyLabel, CaptionLabel, MessageBox,
)

import database as db

_logger = logging.getLogger("app_error")


def _preview_text(html: str, limit: int = 40) -> str:
    """HTML 본문을 한 줄 평문 미리보기로 변환."""
    doc = QTextDocument()
    doc.setHtml(html or "")
    text = doc.toPlainText().replace("\n", " ").strip()
    if not text:
        return "(빈 노트)"
    return text[:limit] + ("..." if len(text) > limit else "")


class StickyTrashWindow(QWidget):
    """삭제된 스티키 노트를 보고 복구/영구삭제하는 창."""
    restore_requested = Signal(int)  # 복구할 note_id를 메인 창에 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("휴지통")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setMinimumSize(440, 480)
        self.resize(440, 480)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = BodyLabel("🗑️ 스티키 노트 휴지통", self)
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.count_label = CaptionLabel("", self)
        self.count_label.setStyleSheet("color: gray;")
        layout.addWidget(self.count_label)

        # 빈 상태 안내
        self.empty_label = BodyLabel("휴지통이 비어 있습니다.", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #9aa0a6; padding: 40px;")
        layout.addWidget(self.empty_label)

        # 결과 테이블
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["색상", "내용", "삭제 시각"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setShowGrid(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #37352f;
                border: 1px solid #ededed;
                border-radius: 4px;
                gridline-color: #ededed;
                outline: none;
            }
            QTableWidget::item { padding: 8px 12px; border-bottom: none; }
            QTableWidget::item:selected { background-color: #ebeced; color: #37352f; }
            QHeaderView::section {
                background-color: #f7f7f5;
                color: #37352f;
                padding: 8px 12px;
                font-weight: 500;
                font-size: 13px;
                border: none;
                border-bottom: 1px solid #ededed;
            }
        """)
        layout.addWidget(self.table, 1)

        # 버튼 줄
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.restore_btn = PrimaryPushButton("복구", self)
        self.restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self.restore_btn)

        self.purge_btn = PushButton("영구 삭제", self)
        self.purge_btn.clicked.connect(self._on_purge)
        btn_row.addWidget(self.purge_btn)

        btn_row.addStretch(1)

        self.empty_btn = PushButton("휴지통 비우기", self)
        self.empty_btn.clicked.connect(self._on_empty)
        btn_row.addWidget(self.empty_btn)

        layout.addLayout(btn_row)

    def _refresh(self):
        """휴지통 목록을 다시 읽어 테이블 갱신."""
        try:
            items = db.get_trashed_sticky_notes()
        except (OSError, ValueError) as e:
            _logger.error("휴지통 목록 로드 실패: %s", e)
            items = []

        self.table.setRowCount(len(items))
        for row, it in enumerate(items):
            color_item = QTableWidgetItem("")
            color_item.setBackground(QColor(it["color"]))
            color_item.setData(Qt.UserRole, it["id"])  # 행 식별용 note_id

            content_item = QTableWidgetItem(_preview_text(it["content"]))
            content_item.setToolTip(_preview_text(it["content"], 200))

            when = (it["deleted_at"] or "")[:16]  # YYYY-MM-DD HH:MM
            when_item = QTableWidgetItem(when)

            self.table.setItem(row, 0, color_item)
            self.table.setItem(row, 1, content_item)
            self.table.setItem(row, 2, when_item)

        has_items = len(items) > 0
        self.empty_label.setVisible(not has_items)
        self.table.setVisible(has_items)
        self.restore_btn.setEnabled(has_items)
        self.purge_btn.setEnabled(has_items)
        self.empty_btn.setEnabled(has_items)
        self.count_label.setText(f"휴지통: {len(items)}개" if has_items else "")

    def _selected_note_id(self):
        """선택된 행의 note_id 반환(없으면 None)."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_restore(self):
        note_id = self._selected_note_id()
        if note_id is None:
            return
        self.restore_requested.emit(note_id)
        self._refresh()

    def _on_purge(self):
        note_id = self._selected_note_id()
        if note_id is None:
            return
        dlg = MessageBox(
            "영구 삭제",
            "이 노트를 영구히 삭제할까요?\n되돌릴 수 없습니다.",
            self
        )
        dlg.yesButton.setText("영구 삭제")
        dlg.cancelButton.setText("취소")
        if dlg.exec():
            db.purge_sticky_note(note_id)
            self._refresh()

    def _on_empty(self):
        if self.table.rowCount() == 0:
            return
        dlg = MessageBox(
            "휴지통 비우기",
            "휴지통의 모든 노트를 영구히 삭제할까요?\n되돌릴 수 없습니다.",
            self
        )
        dlg.yesButton.setText("모두 삭제")
        dlg.cancelButton.setText("취소")
        if dlg.exec():
            db.empty_sticky_trash()
            self._refresh()
