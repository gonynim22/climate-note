# ui_sticky.py - 스티키 노트 창 UI (메모 전용)
import logging
import sqlite3

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSizeGrip, QPushButton
)

_logger = logging.getLogger("app_error")
from PySide6.QtCore import Qt, QTimer, QPoint, Signal, QRect, QRectF
from PySide6.QtGui import (
    QColor, QGuiApplication, QFont, QTextCharFormat, QPainter, QTextCursor,
    QSyntaxHighlighter, QPen, QPainterPath,
)

from qfluentwidgets import (
    TransparentToolButton,
    FluentIcon as FIF, Dialog,
)

import database as db
from ui_sticky_links import FileLinkTextEdit


# ── 위젯 공통 크기 ────────────────────────────────────────────────
WIDGET_WIDTH = 220
DDAY_HEIGHT = 95

# Font Awesome 6 Free 체크박스 아이콘
_FA_FAMILY    = "Font Awesome 6 Free"
_UNCHECKED    = "\uf0c8"   # fa-square (regular, 아웃라인)
_CHECKED      = "\uf14a"   # fa-square-check (solid, 완료)
# 하위 호환: 기존 유니코드 문자도 클릭/Enter로 인식
_ALL_UNCHECKED = (_UNCHECKED, "☐")
_ALL_CHECKED   = (_CHECKED,   "☑")

# ── 색상 팔레트 ──────────────────────────────────────────────────
STICKY_COLORS = [
    ("#FFFA8E", ""), ("#D0FFF1", ""),
    ("#FFD8FB", ""), ("#C4D5FF", ""),
]

# ── 헤더(상단 바) 진한 색 매핑 ───────────────────────────────────
STICKY_HEADER_COLORS = {
    "#FFFA8E": "#F8F26F",  # 노랑
    "#D0FFF1": "#A8F0DC",  # 민트
    "#FFD8FB": "#F0C0ED",  # 핑크
    "#C4D5FF": "#A8BFEF",  # 하늘
}

# ── 텍스트 색상 팔레트 ────────────────────────────────────────────
TEXT_COLORS = [
    ("#000000", "검정"), ("#D32F2F", "빨강"), ("#1976D2", "파랑"),
    ("#388E3C", "초록"), ("#F57C00", "주황"), ("#7B1FA2", "보라"),
    ("#00838F", "청록"), ("#5D4037", "갈색"),
]

class _ColorGridPopup(QWidget):
    """색상 선택 팝업 (범용)"""
    color_selected = Signal(str)

    def __init__(self, colors: list, cols: int = 5, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QWidget(self)
        container.setObjectName("colorPickerContainer")
        container.setStyleSheet("""
            #colorPickerContainer {
                background: white;
                border-radius: 8px;
                border: 1px solid rgba(0,0,0,60);
            }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(4)

        for idx, (hex_color, name) in enumerate(colors):
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {hex_color};
                    border-radius: 14px;
                    border: 1px solid rgba(0,0,0,60);
                }}
                QPushButton:hover {{
                    border: 2px solid rgba(0,0,0,140);
                }}
            """)
            btn.clicked.connect(lambda checked=False, c=hex_color: self._on_pick(c))
            grid.addWidget(btn, idx // cols, idx % cols)

    def _on_pick(self, hex_color: str):
        self.color_selected.emit(hex_color)
        self.close()
        self.deleteLater()


def ColorPickerPopup(parent=None):
    """배경 색상 선택 팝업 (하위 호환)"""
    return _ColorGridPopup(STICKY_COLORS, cols=4, parent=parent)


class _TextColorButton(QPushButton):
    """텍스트 색상 버튼 - 'A' 글자 아래 선택된 색상 바 표시 (Word 스타일)"""

    def __init__(self, parent=None):
        super().__init__("A", parent)
        self._bar_color = QColor("#000000")
        self.setFixedSize(24, 22)
        self.setToolTip("텍스트 색상")
        self.setStyleSheet("""
            QPushButton {
                font-size: 12px; font-weight: bold;
                min-width: 24px; max-width: 24px;
                min-height: 22px; max-height: 22px;
                border-radius: 4px;
                border: 1px solid rgba(0,0,0,40);
                background: rgba(255,255,255,120);
                font-family: serif;
            }
            QPushButton:hover { background: rgba(0,0,0,25); }
        """)

    def set_bar_color(self, hex_color: str):
        """색상 바 색상 변경 후 다시 그리기"""
        self._bar_color = QColor(hex_color)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 하단 색상 바 (3px 높이)
        bar_h = 3
        margin = 3
        bar_rect = QRect(margin, self.height() - bar_h - 2,
                         self.width() - margin * 2, bar_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._bar_color)
        painter.drawRoundedRect(bar_rect, 1.0, 1.0)
        painter.end()


class _TodoGlyphHighlighter(QSyntaxHighlighter):
    """저장 문자는 유지한 채 기본 글리프만 화면에서 숨긴다."""

    def __init__(self, document):
        super().__init__(document)
        self._mask_format = QTextCharFormat()
        self._mask_format.setForeground(QColor(0, 0, 0, 0))

    def highlightBlock(self, text):
        for index, char in enumerate(text):
            if char in _ALL_UNCHECKED or char in _ALL_CHECKED:
                self.setFormat(index, 1, self._mask_format)


class _TodoTextEdit(FileLinkTextEdit):
    """체크박스(☐/☑) 클릭 토글을 지원하는 QTextEdit.

    저장된 체크박스 문자는 그대로 유지하고, 화면에는 현대적인 벡터
    체크박스를 그린다. 넓은 히트박스를 클릭하면 상태를 토글하고 해당
    블록 전체의 서식(dim 색·취소선)을 갱신한다.
    """

    _DIM_COLOR = "#888888"
    _DEFAULT_COLOR = "#000000"
    _TODO_ACCENT = QColor("#2563EB")
    _TODO_ACCENT_HOVER = QColor("#1D4ED8")
    _TODO_OUTLINE = QColor("#5B6472")
    _TODO_ICON_SIZE = 15.0
    _TODO_HIT_SIZE = 22.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered_todo_pos = None
        # QSyntaxHighlighter의 표시용 서식은 QTextDocument/toHtml에 저장되지
        # 않는다. 기존 FA/유니코드 문자는 호환 sentinel로 그대로 남긴다.
        self._todo_glyph_highlighter = _TodoGlyphHighlighter(self.document())
        self.viewport().setMouseTracking(True)

    @staticmethod
    def _is_todo_char(char):
        return char in _ALL_UNCHECKED or char in _ALL_CHECKED

    def _visible_todo_visuals(self):
        """보이는 todo의 (pos, char, icon_rect, hit_rect) 목록을 반환한다."""
        viewport = self.viewport()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return []

        first_block = self.cursorForPosition(QPoint(0, 0)).block()
        last_block = self.cursorForPosition(
            QPoint(max(0, viewport.width() - 1), max(0, viewport.height() - 1))
        ).block()
        if not first_block.isValid() or not last_block.isValid():
            return []

        visuals = []
        block = first_block
        last_number = last_block.blockNumber()
        while block.isValid() and block.blockNumber() <= last_number:
            block_text = block.text()
            block_start = block.position()
            for offset, char in enumerate(block_text):
                if not self._is_todo_char(char):
                    continue

                pos = block_start + offset
                before = QTextCursor(self.document())
                before.setPosition(pos)
                after = QTextCursor(self.document())
                after.setPosition(pos + 1)
                before_rect = self.cursorRect(before)
                after_rect = self.cursorRect(after)

                line_height = max(1.0, float(before_rect.height()))
                icon_size = min(
                    self._TODO_ICON_SIZE,
                    max(12.0, line_height - 2.0),
                )
                same_line = abs(after_rect.center().y() - before_rect.center().y()) < 1.0
                advance = (
                    abs(float(after_rect.x() - before_rect.x()))
                    if same_line else icon_size
                )
                icon_x = float(min(before_rect.x(), after_rect.x()))
                if advance > icon_size:
                    icon_x += (advance - icon_size) / 2.0
                icon_y = float(before_rect.y()) + (line_height - icon_size) / 2.0
                icon_rect = QRectF(icon_x, icon_y, icon_size, icon_size)

                hit_rect = QRectF(
                    icon_rect.center().x() - self._TODO_HIT_SIZE / 2.0,
                    icon_rect.center().y() - self._TODO_HIT_SIZE / 2.0,
                    self._TODO_HIT_SIZE,
                    self._TODO_HIT_SIZE,
                )

                # 우측 확장 영역이 본문 첫 글자를 가로채지 않도록 구분 공백
                # 뒤의 caret까지만 허용한다.
                body_pos = pos + 1
                if self.document().characterAt(body_pos) == " ":
                    body_pos += 1
                body_cursor = QTextCursor(self.document())
                body_cursor.setPosition(body_pos)
                body_rect = self.cursorRect(body_cursor)
                if abs(body_rect.center().y() - before_rect.center().y()) < 1.0:
                    body_x = float(body_rect.x())
                    if body_x > icon_rect.center().x():
                        hit_rect.setRight(min(hit_rect.right(), body_x - 0.5))

                visuals.append((pos, char, icon_rect, hit_rect))
            block = block.next()
        return visuals

    def _todo_visual_at_pixel(self, pixel_pos):
        matches = []
        for visual in self._visible_todo_visuals():
            pos, _char, icon_rect, hit_rect = visual
            if hit_rect.contains(pixel_pos):
                center = icon_rect.center()
                distance = (
                    (center.x() - pixel_pos.x()) ** 2
                    + (center.y() - pixel_pos.y()) ** 2
                )
                matches.append((distance, pos, visual))
        if not matches:
            return None
        # 인접한 줄의 22px 히트박스가 겹치면 포인터 중심에 가까운 행을 선택한다.
        return min(matches, key=lambda item: (item[0], item[1]))[2]

    def _checkbox_at_pixel(self, pixel_pos):
        """픽셀 좌표 위의 체크박스를 찾아 (pos, char)를 반환. 없으면 (None, None).

        저장 글리프의 실제 폭보다 넓은 벡터 체크박스 히트박스를 사용한다.
        """
        visual = self._todo_visual_at_pixel(pixel_pos)
        if visual is not None:
            return visual[0], visual[1]
        return None, None

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        for pos, char, icon_rect, _hit_rect in self._visible_todo_visuals():
            hovered = pos == self._hovered_todo_pos
            if hovered:
                hover_rect = icon_rect.adjusted(-3.0, -3.0, 3.0, 3.0)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(37, 99, 235, 30))
                painter.drawRoundedRect(hover_rect, 5.0, 5.0)

            checked = char in _ALL_CHECKED
            if checked:
                painter.setPen(Qt.NoPen)
                painter.setBrush(
                    self._TODO_ACCENT_HOVER if hovered else self._TODO_ACCENT
                )
                painter.drawRoundedRect(icon_rect, 3.5, 3.5)

                check_path = QPainterPath()
                check_path.moveTo(
                    icon_rect.left() + icon_rect.width() * 0.22,
                    icon_rect.top() + icon_rect.height() * 0.52,
                )
                check_path.lineTo(
                    icon_rect.left() + icon_rect.width() * 0.43,
                    icon_rect.top() + icon_rect.height() * 0.72,
                )
                check_path.lineTo(
                    icon_rect.left() + icon_rect.width() * 0.78,
                    icon_rect.top() + icon_rect.height() * 0.30,
                )
                check_pen = QPen(QColor("#FFFFFF"))
                check_pen.setWidthF(2.0)
                check_pen.setCapStyle(Qt.RoundCap)
                check_pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(check_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(check_path)
            else:
                painter.setBrush(QColor(255, 255, 255, 210))
                outline_pen = QPen(
                    self._TODO_ACCENT if hovered else self._TODO_OUTLINE
                )
                outline_pen.setWidthF(1.5)
                painter.setPen(outline_pen)
                painter.drawRoundedRect(
                    icon_rect.adjusted(0.75, 0.75, -0.75, -0.75),
                    3.25,
                    3.25,
                )
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            p, char = self._checkbox_at_pixel(event.position().toPoint())
            if p is not None:
                self._toggle_at(p, char)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """체크박스 위에서 손 모양 커서 표시"""
        p, _ = self._checkbox_at_pixel(event.position().toPoint())
        if p != self._hovered_todo_pos:
            self._hovered_todo_pos = p
            self.viewport().update()
        if p is not None:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered_todo_pos is not None:
            self._hovered_todo_pos = None
            self.viewport().update()
        self.viewport().setCursor(Qt.IBeamCursor)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers():
            cursor = self.textCursor()
            block_text = cursor.block().text()
            _todo_prefixes = tuple(c + " " for c in _ALL_UNCHECKED + _ALL_CHECKED)

            if block_text.startswith(_todo_prefixes):
                _empty_todos = tuple(c + " " for c in _ALL_UNCHECKED + _ALL_CHECKED)
                if block_text in _empty_todos:
                    # 빈 todo: 체크박스 제거 후 일반 줄로 남긴다.
                    block_cur = QTextCursor(cursor.block())
                    block_cur.select(QTextCursor.LineUnderCursor)
                    block_cur.removeSelectedText()
                    fmt = QTextCharFormat()
                    fmt.setForeground(QColor(self._DEFAULT_COLOR))
                    fmt.setFontStrikeOut(False)
                    self.setCurrentCharFormat(fmt)
                    event.accept()
                    return
                else:
                    # 연속 todo: 블록 분리 후 새 블록에 FA 빈 체크박스 삽입.
                    edit_cursor = self.textCursor()
                    edit_cursor.beginEditBlock()
                    try:
                        super().keyPressEvent(event)
                        new_cursor = self.textCursor()
                        fmt = QTextCharFormat()
                        fmt.setForeground(QColor(self._DEFAULT_COLOR))
                        fmt.setFontStrikeOut(False)
                        fa_fmt = QTextCharFormat(fmt)
                        fa_fmt.setFontFamilies([_FA_FAMILY])
                        fa_fmt.setFontWeight(QFont.Normal)
                        new_cursor.insertText(_UNCHECKED, fa_fmt)
                        fmt.setFontWeight(QFont.Normal)
                        new_cursor.setCharFormat(fmt)
                        new_cursor.insertText(" ")

                        # 완료 항목을 중간에서 나누면 뒤쪽 기존 문자가 dim/취소선을
                        # 상속한다. 새 unchecked 항목의 본문만 기본 상태로 복원한다.
                        body_start = new_cursor.position()
                        new_block = new_cursor.block()
                        body_end = (
                            new_block.position() + new_block.length() - 1
                        )
                        if body_start < body_end:
                            body_cursor = QTextCursor(self.document())
                            body_cursor.setPosition(body_start)
                            body_cursor.setPosition(
                                body_end, QTextCursor.KeepAnchor
                            )
                            body_fmt = QTextCharFormat()
                            body_fmt.setForeground(
                                QColor(self._DEFAULT_COLOR)
                            )
                            body_fmt.setFontStrikeOut(False)
                            body_cursor.mergeCharFormat(body_fmt)
                        self.setTextCursor(new_cursor)
                    finally:
                        edit_cursor.endEditBlock()
                    return
        super().keyPressEvent(event)

    def _toggle_at(self, pos: int, current: str):
        """pos 위치의 체크박스 문자를 토글하고 블록 서식을 갱신한다."""
        cursor = QTextCursor(self.document())
        block = self.document().findBlock(pos)
        block_start = block.position()
        block_end = block_start + block.length() - 1  # exclusive of block separator

        cursor.beginEditBlock()
        try:
            if current in _ALL_UNCHECKED:
                # ☐ → ☑: FA solid square-check 삽입 + 본문 dim+취소선
                fa_fmt = QTextCharFormat()
                fa_fmt.setFontFamilies([_FA_FAMILY])
                fa_fmt.setFontWeight(QFont.Black)
                fa_fmt.setForeground(QColor(self._DEFAULT_COLOR))
                cursor.setPosition(pos)
                cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
                cursor.insertText(_CHECKED, fa_fmt)
                text_start = pos + 1
                # 체크박스-텍스트 사이 구분 공백은 서식 적용 제외: 취소선이 아이콘에 붙어 보이는 현상 방지
                if self.document().characterAt(text_start) == " ":
                    text_start += 1
                if text_start < block_end:
                    sel = QTextCursor(self.document())
                    sel.setPosition(text_start)
                    sel.setPosition(block_end, QTextCursor.KeepAnchor)
                    fmt_done = QTextCharFormat()
                    fmt_done.setForeground(QColor(self._DIM_COLOR))
                    fmt_done.setFontStrikeOut(True)
                    sel.mergeCharFormat(fmt_done)
            else:  # _ALL_CHECKED → _UNCHECKED
                # ☑ → ☐: FA regular square 삽입 + 본문 복원
                fa_fmt = QTextCharFormat()
                fa_fmt.setFontFamilies([_FA_FAMILY])
                fa_fmt.setFontWeight(QFont.Normal)
                fa_fmt.setForeground(QColor(self._DEFAULT_COLOR))
                cursor.setPosition(pos)
                cursor.setPosition(pos + 1, QTextCursor.KeepAnchor)
                cursor.insertText(_UNCHECKED, fa_fmt)
                text_start = pos + 1
                # 토글 시 일관성을 위해 체크/언체크 모두 구분 공백 제외
                if self.document().characterAt(text_start) == " ":
                    text_start += 1
                if text_start < block_end:
                    sel = QTextCursor(self.document())
                    sel.setPosition(text_start)
                    sel.setPosition(block_end, QTextCursor.KeepAnchor)
                    fmt_reset = QTextCharFormat()
                    fmt_reset.setForeground(QColor(self._DEFAULT_COLOR))
                    fmt_reset.setFontStrikeOut(False)
                    sel.mergeCharFormat(fmt_reset)
        finally:
            cursor.endEditBlock()


def toggle_bold(text_edit, on: bool) -> None:
    fmt = QTextCharFormat()
    fmt.setFontWeight(QFont.Bold if on else QFont.Normal)
    text_edit.mergeCurrentCharFormat(fmt)


def bold_state(text_edit) -> bool:
    return text_edit.currentCharFormat().fontWeight() >= QFont.Bold


def apply_text_color(text_edit, hex_color: str) -> None:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(hex_color))
    text_edit.mergeCurrentCharFormat(fmt)


def insert_todo(text_edit) -> None:
    """현재 블록이 비어있으면 그 자리에, 아니면 새 블록에 todo를 넣는다."""
    cursor = text_edit.textCursor()
    clean_fmt = QTextCharFormat()
    clean_fmt.setForeground(QColor("#000000"))
    clean_fmt.setFontStrikeOut(False)

    if cursor.block().text() != "":
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.insertBlock()
    fa_fmt = QTextCharFormat(clean_fmt)
    fa_fmt.setFontFamilies([_FA_FAMILY])
    fa_fmt.setFontWeight(QFont.Normal)
    cursor.insertText(_UNCHECKED, fa_fmt)
    clean_fmt.setFontWeight(QFont.Normal)
    cursor.setCharFormat(clean_fmt)
    cursor.insertText(" ")

    text_edit.setTextCursor(cursor)
    text_edit.setFocus()


class StickyFormatToolbar(QWidget):
    """패널 등에서 재사용하는 공용 서식 툴바."""
    bold_toggled = Signal(bool)
    todo_requested = Signal()
    link_requested = Signal()
    text_color_picked = Signal(str)
    bg_color_picked = Signal(str)

    _BTN_STYLE = """
        QPushButton {
            font-size: 12px; font-weight: bold;
            min-width: 24px; max-width: 24px;
            min-height: 22px; max-height: 22px;
            border-radius: 4px;
            border: 1px solid rgba(0,0,0,40);
            background: rgba(255,255,255,120);
        }
        QPushButton:hover { background: rgba(0,0,0,25); }
        QPushButton:checked { background: rgba(0,120,212,60); border: 1px solid #0078D4; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.bg_btn = QPushButton(self)
        self.bg_btn.setFixedSize(24, 22)
        self.bg_btn.setToolTip("배경 색상")
        self.bg_btn.setFocusPolicy(Qt.NoFocus)
        self.bg_btn.clicked.connect(self._pick_bg_color)
        layout.addWidget(self.bg_btn)

        self.bold_btn = QPushButton("B", self)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setToolTip("굵게")
        self.bold_btn.setFocusPolicy(Qt.NoFocus)
        self.bold_btn.setStyleSheet(self._BTN_STYLE + "QPushButton { font-family: serif; }")
        self.bold_btn.clicked.connect(
            lambda checked=False: self.bold_toggled.emit(self.bold_btn.isChecked())
        )
        layout.addWidget(self.bold_btn)

        self.todo_btn = QPushButton("✓", self)
        self.todo_btn.setToolTip("할 일 추가")
        self.todo_btn.setFocusPolicy(Qt.NoFocus)
        self.todo_btn.setStyleSheet(self._BTN_STYLE)
        self.todo_btn.clicked.connect(lambda checked=False: self.todo_requested.emit())
        layout.addWidget(self.todo_btn)

        self.text_color_btn = _TextColorButton(self)
        self.text_color_btn.setFocusPolicy(Qt.NoFocus)
        self.text_color_btn.clicked.connect(self._pick_text_color)
        layout.addWidget(self.text_color_btn)

        self.link_btn = TransparentToolButton(FIF.LINK, self)
        self.link_btn.setFixedSize(24, 22)
        self.link_btn.setFocusPolicy(Qt.NoFocus)
        self.link_btn.setToolTip("파일 연결 (열기: Ctrl+클릭)")
        self.link_btn.clicked.connect(lambda: self.link_requested.emit())
        layout.addWidget(self.link_btn)

        layout.addStretch()

    def set_bold_state(self, on: bool) -> None:
        self.bold_btn.setChecked(on)

    def set_bg_swatch(self, hex_color: str) -> None:
        self.bg_btn.setStyleSheet(
            f"QPushButton {{ background: {hex_color}; border-radius: 4px;"
            "border: 1px solid rgba(0,0,0,60); }"
            "QPushButton:hover { border: 2px solid rgba(0,0,0,140); }"
        )

    def _pick_text_color(self):
        popup = _ColorGridPopup(TEXT_COLORS, cols=4, parent=self)
        popup.color_selected.connect(self._on_text_color)
        pos = self.text_color_btn.mapToGlobal(QPoint(0, self.text_color_btn.height() + 4))
        popup.move(pos)
        popup.show()

    def _on_text_color(self, hex_color: str):
        self.text_color_btn.set_bar_color(hex_color)
        self.text_color_picked.emit(hex_color)

    def _pick_bg_color(self):
        popup = _ColorGridPopup(STICKY_COLORS, cols=4, parent=self)
        popup.color_selected.connect(self.bg_color_picked.emit)
        pos = self.bg_btn.mapToGlobal(QPoint(0, self.bg_btn.height() + 4))
        popup.move(pos)
        popup.show()


class StickyNoteWindow(QWidget):
    """독립적인 프레임리스 반투명 스티키 노트 창 (메모 전용)"""
    note_closed = Signal(int)  # note_id를 전달하여 부모에서 참조 정리

    def __init__(self, note_id: int, note_data: dict, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self._drag_pos = None
        self._decryption_failed = bool(
            note_data.get("_decryption_failed", False)
        )

        content = note_data.get("content", "")
        x = note_data.get("x_pos", 200)
        y = note_data.get("y_pos", 200)
        w = note_data.get("width", 300)
        h = note_data.get("height", 400)
        color = note_data.get("color", db.DEFAULT_STICKY_COLOR)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Window |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(x, y, w, h)
        self.setMinimumSize(WIDGET_WIDTH, DDAY_HEIGHT)

        self._build_ui(content, color)
        if self._decryption_failed:
            self.text_edit.setReadOnly(True)

        # 자동 저장 타이머 (2초 디바운스)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._auto_save_content)

        # 크기 저장 타이머 (500ms 디바운스)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._save_geometry)

    def _build_ui(self, content: str, color: str):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 컨테이너 (외형 테두리 + 전체 배경) ──
        self.container = QWidget(self)
        self.container.setObjectName("stickyContainer")
        outer.addWidget(self.container)

        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 헤더 위젯 (진한 색 상단 바) ──
        self.header_widget = QWidget(self.container)
        self.header_widget.setObjectName("stickyHeader")
        self.header_widget.setAttribute(Qt.WA_StyledBackground, True)
        hdr_layout = QHBoxLayout(self.header_widget)
        hdr_layout.setContentsMargins(8, 8, 8, 6)
        hdr_layout.setSpacing(4)
        main_layout.addWidget(self.header_widget)

        # 색상 선택 버튼
        self.color_btn = QPushButton(self)
        self.color_btn.setFixedSize(24, 22)
        self.color_btn.setToolTip("배경 색상 변경")
        self.color_btn.clicked.connect(self._on_color_btn_clicked)
        hdr_layout.addWidget(self.color_btn)

        # ── 서식 버튼 ──
        _fmt_style = """
            QPushButton {
                font-size: 12px; font-weight: bold;
                min-width: 24px; max-width: 24px;
                min-height: 22px; max-height: 22px;
                border-radius: 4px;
                border: 1px solid rgba(0,0,0,40);
                background: rgba(255,255,255,120);
            }
            QPushButton:hover { background: rgba(0,0,0,25); }
            QPushButton:checked { background: rgba(0,120,212,60); border: 1px solid #0078D4; }
        """

        self.bold_btn = QPushButton("B", self)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setToolTip("굵게")
        self.bold_btn.setStyleSheet(_fmt_style + "QPushButton { font-family: serif; }")
        self.bold_btn.clicked.connect(self._toggle_bold)
        hdr_layout.addWidget(self.bold_btn)

        self.todo_btn = QPushButton("✓", self)
        self.todo_btn.setCheckable(False)
        self.todo_btn.setToolTip("할 일 추가")
        self.todo_btn.setStyleSheet(_fmt_style)
        self.todo_btn.clicked.connect(self._insert_todo)
        hdr_layout.addWidget(self.todo_btn)

        self.text_color_btn = _TextColorButton(self)
        self.text_color_btn.clicked.connect(self._on_text_color_btn)
        hdr_layout.addWidget(self.text_color_btn)

        self.link_btn = TransparentToolButton(FIF.LINK, self)
        self.link_btn.setFixedSize(24, 22)
        self.link_btn.setFocusPolicy(Qt.NoFocus)
        self.link_btn.setToolTip("파일 연결 (열기: Ctrl+클릭)")
        self.link_btn.clicked.connect(lambda: self.text_edit.choose_file_link())
        hdr_layout.addWidget(self.link_btn)

        hdr_layout.addStretch()

        # 닫기 버튼
        close_btn = TransparentToolButton(FIF.CLOSE, self)
        close_btn.setToolTip("닫기")
        close_btn.clicked.connect(self._on_close)
        hdr_layout.addWidget(close_btn)

        # ── 본문 영역 (텍스트 + 그립) ──
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(8, 6, 8, 8)
        body_layout.setSpacing(0)
        main_layout.addLayout(body_layout, 1)

        # ── 텍스트 편집 ──
        self.text_edit = _TodoTextEdit(self)
        # HTML이면 setHtml, 아니면 setPlainText (하위 호환)
        if content.strip().startswith("<"):
            self.text_edit.setHtml(content)
        else:
            self.text_edit.setPlainText(content)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                font-size: 13px;
            }
        """)
        self.text_edit.cursorPositionChanged.connect(self._update_format_buttons)
        self.text_edit.textChanged.connect(lambda: self._save_timer.start(2000))
        body_layout.addWidget(self.text_edit, 1)

        # ── 크기 조절 그립 ──
        grip_bar = QHBoxLayout()
        grip_bar.addStretch()
        grip = QSizeGrip(self)
        grip_bar.addWidget(grip)
        body_layout.addLayout(grip_bar)

        # 색상 적용 (저장 없이)
        self._apply_color(color, save=False)

    def _insert_todo(self):
        insert_todo(self.text_edit)

    def _apply_color(self, hex_color: str, save: bool = True):
        """배경 색상 적용 및 선택적 DB 저장"""
        self._color = hex_color
        try:
            c = QColor(hex_color)
            r, g, b = c.red(), c.green(), c.blue()
        except (ValueError, AttributeError):
            r, g, b = 255, 253, 210

        # 테두리 색 (본문보다 어둡게)
        br = max(0, r - 30)
        bg = max(0, g - 30)
        bb = max(0, b - 30)

        # 헤더 색 (매핑에서 조회, 없으면 자동 계산)
        header_hex = STICKY_HEADER_COLORS.get(hex_color)
        if header_hex:
            hc = QColor(header_hex)
            hr, hg, hb = hc.red(), hc.green(), hc.blue()
        else:
            hr, hg, hb = max(0, r - 20), max(0, g - 20), max(0, b - 20)

        self.container.setStyleSheet(f"""
            #stickyContainer {{
                background: rgba({r}, {g}, {b}, 255);
                border-radius: 10px;
                border: 1px solid rgba({br}, {bg}, {bb}, 180);
            }}
        """)
        self.header_widget.setStyleSheet(f"""
            #stickyHeader {{
                background: rgba({hr}, {hg}, {hb}, 255);
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid rgba({br}, {bg}, {bb}, 80);
            }}
        """)
        self.color_btn.setStyleSheet(f"""
            QPushButton {{
                background: {hex_color};
                border-radius: 4px;
                border: 1px solid rgba(0,0,0,60);
            }}
            QPushButton:hover {{
                border: 2px solid rgba(0,0,0,140);
            }}
        """)

        if save:
            db.update_sticky_note(self.note_id, color=hex_color)

    def _toggle_bold(self):
        toggle_bold(self.text_edit, self.bold_btn.isChecked())

    def _on_text_color_btn(self):
        popup = _ColorGridPopup(TEXT_COLORS, cols=4, parent=self)
        popup.color_selected.connect(self._apply_text_color)
        btn_global = self.text_color_btn.mapToGlobal(
            QPoint(0, self.text_color_btn.height() + 4)
        )
        popup.move(btn_global)
        popup.show()

    def _apply_text_color(self, hex_color: str):
        self._text_color = hex_color
        apply_text_color(self.text_edit, hex_color)
        self.text_color_btn.set_bar_color(hex_color)

    def _update_format_buttons(self):
        self.bold_btn.setChecked(bold_state(self.text_edit))

    def _on_color_btn_clicked(self):
        popup = _ColorGridPopup(STICKY_COLORS, cols=4, parent=self)
        popup.color_selected.connect(lambda c: self._apply_color(c, save=True))
        btn_global = self.color_btn.mapToGlobal(QPoint(0, self.color_btn.height() + 4))
        popup.move(btn_global)
        popup.show()

    def _on_close(self):
        """닫기 확인 → 휴지통으로 이동(soft-delete)"""
        dlg = Dialog(
            "노트 정리",
            "이 노트를 휴지통으로 이동하시겠습니까?\n휴지통에서 다시 복구할 수 있습니다.",
            None,
        )
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dlg.setFixedSize(360, 220)
        dlg.contentLabel.setWordWrap(True)
        center = self.frameGeometry().center()
        dlg.move(center.x() - dlg.width() // 2, center.y() - dlg.height() // 2)
        dlg.yesButton.setText("휴지통으로")
        dlg.cancelButton.setText("취소")
        accepted = bool(dlg.exec())
        dlg.deleteLater()
        if accepted:
            if not self.save():
                self._save_timer.start(2000)
                return
            db.trash_sticky_note(self.note_id)
            self.note_closed.emit(self.note_id)
            self.close()

    def save(self) -> bool:
        """현재 내용 저장 (외부 호출용)"""
        if self._decryption_failed:
            return False
        self._save_timer.stop()
        if self._auto_save_content():
            return True
        self._save_timer.start(2000)
        return False

    def _auto_save_content(self) -> bool:
        """현재 내용 자동 저장 (HTML 형식)"""
        if self._decryption_failed:
            return False
        try:
            content = self.text_edit.toHtml()
            db.update_sticky_note(self.note_id, content=content)
            return True
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("스티키 노트 자동 저장 실패 (id=%s): %s", self.note_id, e)
            return False

    # ─── 드래그 이동 ────────────────────────────────────────────
    @staticmethod
    def _snap_px():
        screen = QGuiApplication.primaryScreen()
        if screen:
            return max(1, round(screen.physicalDotsPerInch() * 5 / 25.4))
        return 19

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            snap = self._snap_px()
            new_pos.setX(round(new_pos.x() / snap) * snap)
            new_pos.setY(round(new_pos.y() / snap) * snap)
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            db.update_sticky_note(
                self.note_id,
                x_pos=self.x(), y_pos=self.y()
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_resize_timer"):
            snap = self._snap_px()
            w = max(self.minimumWidth(), round(self.width() / snap) * snap)
            h = max(self.minimumHeight(), round(self.height() / snap) * snap)
            if w != self.width() or h != self.height():
                self.blockSignals(True)
                self.resize(w, h)
                self.blockSignals(False)
            self._resize_timer.stop()
            self._resize_timer.start(500)

    def _save_geometry(self):
        db.update_sticky_note(
            self.note_id,
            width=self.width(), height=self.height()
        )

    def show_window(self):
        db.update_sticky_note(self.note_id, is_open=1)
        self.show()
