# ui_sticky_panel.py - '크게' 모드 우측 컬럼의 편집 가능한 미니 스티키 패널
import logging
import sqlite3

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import Dialog, FluentIcon as FIF, TransparentToolButton

import database as db
from ui_sticky import STICKY_HEADER_COLORS, _TodoTextEdit

_logger = logging.getLogger("app_error")


class _PanelTodoEdit(_TodoTextEdit):
    focused = Signal()

    def focusInEvent(self, event):
        self.focused.emit()
        super().focusInEvent(event)


class StickyMiniCard(QWidget):
    """우측 패널용 편집 가능한 미니 스티키 카드."""
    focused = Signal(object)
    delete_requested = Signal(int)

    def __init__(
            self, note_id: int, content: str, color: str, parent=None,
            *, decryption_failed: bool = False
    ):
        super().__init__(parent)
        self.note_id = note_id
        self._color = color
        self._holiday_theme = None  # 공휴일 테마(표시 전용). 노트 색과 따로 쥔다
        self._decryption_failed = decryption_failed
        self.setObjectName("stickyMiniCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_hex = STICKY_HEADER_COLORS.get(color, color)
        self._strip = QWidget(self)
        self._strip.setObjectName("miniStrip")
        self._strip.setFixedHeight(8)
        self._strip.setAttribute(Qt.WA_StyledBackground, True)
        self._strip.setStyleSheet(
            f"#miniStrip{{background:{header_hex};"
            "border-top-left-radius:8px;border-top-right-radius:8px;}"
        )
        layout.addWidget(self._strip)

        self.delete_btn = TransparentToolButton(FIF.CLOSE, self._strip)
        self.delete_btn.setFixedSize(16, 16)
        self.delete_btn.setToolTip("휴지통으로")
        self.delete_btn.move(0, 0)
        self.delete_btn.clicked.connect(self._on_delete)

        self.text_edit = _PanelTodoEdit(self)
        self.text_edit.focused.connect(lambda: self.focused.emit(self))
        if content.strip().startswith("<"):
            self.text_edit.setHtml(content)
        else:
            self.text_edit.setPlainText(content)
        self.text_edit.setStyleSheet(
            "QTextEdit{background:transparent;border:none;font-size:13px;padding:6px;}"
        )
        self.text_edit.setMinimumHeight(90)
        if self._decryption_failed:
            self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self._apply_color_style(color)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._auto_save)
        self.text_edit.textChanged.connect(lambda: self._save_timer.start(2000))

    def _render_strip(self) -> None:
        """위 띠를 그린다. 공휴일 테마가 있으면 테마 띠 색, 없으면 노트 색의 머리색."""
        theme = self._holiday_theme
        header_hex = (theme.band if theme is not None
                      else STICKY_HEADER_COLORS.get(self._color, self._color))
        self._strip.setStyleSheet(
            f"#miniStrip{{background:{header_hex};"
            "border-top-left-radius:8px;border-top-right-radius:8px;}"
        )

    def set_holiday_theme(self, theme) -> None:
        """공휴일 테마(HolidayTheme 또는 None)를 위 띠에만 입힌다. DB에는 쓰지 않는다."""
        self._holiday_theme = theme
        self._render_strip()

    def _apply_color_style(self, hex_color: str):
        self._color = hex_color
        self._render_strip()
        c = QColor(hex_color)
        r, g, b = c.red(), c.green(), c.blue()
        br, bg, bb = max(0, r - 30), max(0, g - 30), max(0, b - 30)
        self.setStyleSheet(
            f"#stickyMiniCard{{background:rgba({r},{g},{b},255);"
            f"border:1px solid rgba({br},{bg},{bb},180);border-radius:8px;}}"
        )

    def apply_color(self, hex_color: str):
        """배경색 변경 + DB 저장 + 카드 외형 갱신."""
        self._color = hex_color
        self._apply_color_style(hex_color)
        try:
            db.update_sticky_note(self.note_id, color=hex_color)
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 스티키 색상 저장 실패 (id=%s): %s", self.note_id, e)

    def _auto_save(self) -> bool:
        if self._decryption_failed:
            return False
        try:
            db.update_sticky_note(self.note_id, content=self.text_edit.toHtml())
            self.text_edit.document().setModified(False)
            return True
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 스티키 저장 실패 (id=%s): %s", self.note_id, e)
            self.text_edit.document().setModified(True)
            self._save_timer.start(2000)
            return False

    def flush_pending_save(self) -> bool:
        """디바운스 중인 편집만 즉시 저장한다."""
        if not self._save_timer.isActive() and not self.text_edit.document().isModified():
            return True
        self._save_timer.stop()
        if self._auto_save():
            return True
        self._save_timer.start(2000)
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.delete_btn.move(self.width() - self.delete_btn.width() - 2, -4)

    def _confirm_delete(self) -> bool:
        dlg = Dialog(
            "노트 정리",
            "이 노트를 휴지통으로 이동하시겠습니까?\n휴지통에서 다시 복구할 수 있습니다.",
            self,
        )
        dlg.yesButton.setText("휴지통으로")
        dlg.cancelButton.setText("취소")
        accepted = bool(dlg.exec())
        dlg.deleteLater()
        return accepted

    def _on_delete(self):
        if not self._confirm_delete():
            return
        self.delete_requested.emit(self.note_id)

    def save(self) -> bool:
        """디바운스 무시 즉시 저장."""
        if self._decryption_failed:
            return False
        self._save_timer.stop()
        if self._auto_save():
            return True
        self._save_timer.start(2000)
        return False


class StickySidePanel(QWidget):
    """'크게' 모드 우측 컬럼의 스티키 노트 미니 패널."""
    note_trashed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stickySidePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # 우측 컬럼 맨 아래에 놓여 앱의 우하단 모서리를 이루므로, 우하단만
        # 라운드한다. 나머지 모서리를 각지게 둬야 위(일정 패널)·왼쪽(달력)과
        # 맞붙어 사이로 배경이 새지 않는다.
        self.setStyleSheet(
            "#stickySidePanel{background:#FFFFFF;"
            "border:1px solid rgba(206,210,216,180);"
            "border-top:none;"
            "border-bottom-right-radius:12px;}"
        )
        self._cards = []
        self._active_card = None
        self._holiday_theme = None  # reload()로 만드는 카드에도 입히려고 기억한다

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        title = QLabel("스티키 노트", self)
        title.setStyleSheet("font-size:13px;font-weight:700;color:#212121;")
        outer.addWidget(title)

        from ui_sticky import StickyFormatToolbar
        self._toolbar = StickyFormatToolbar(self)
        self._toolbar.bold_toggled.connect(self._on_bold)
        self._toolbar.todo_requested.connect(self._on_todo)
        self._toolbar.link_requested.connect(self._on_link)
        self._toolbar.text_color_picked.connect(self._on_text_color)
        self._toolbar.bg_color_picked.connect(self._on_bg_color)
        self._toolbar.setEnabled(False)
        outer.addWidget(self._toolbar)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        outer.addWidget(self._scroll, 1)

        self._list = QWidget()
        # 선택자 없는 'background:transparent;'는 자식 QTextEdit의 우클릭 컨텍스트
        # 메뉴(QMenu)까지 전파돼 메뉴가 투명해지는(글자가 비쳐 흐릿한) 회귀를
        # 만든다. objectName으로 스코프해 _list 자신에만 적용한다.
        self._list.setObjectName("stickyMiniList")
        self._list.setStyleSheet("#stickyMiniList{background:transparent;}")
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list)

        self._empty_label = QLabel("표시할 스티키 노트가 없습니다.", self._list)
        self._empty_label.setStyleSheet("color:#888888;font-size:12px;")
        self._list_layout.insertWidget(0, self._empty_label)

    def _flush_pending_cards(self) -> bool:
        """카드 교체 전에 편집 대기 중인 본문을 모두 보존한다."""
        saved = True
        for card in list(self._cards):
            if not card.flush_pending_save():
                saved = False
        return saved

    def set_holiday_theme(self, theme) -> None:
        """공휴일 테마(HolidayTheme 또는 None)를 기억하고 지금 있는 카드에 입힌다. 화면 전용."""
        self._holiday_theme = theme
        for card in self._cards:
            card.set_holiday_theme(theme)

    def reload(self, *, flush_pending: bool = True) -> bool:
        """열린 스티키 노트로 카드 목록을 재구성한다."""
        if flush_pending and not self._flush_pending_cards():
            return False

        try:
            notes = db.get_open_sticky_notes()
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 스티키 목록 조회 실패: %s", e)
            return False

        if self._active_card is not None:
            try:
                self._active_card.text_edit.cursorPositionChanged.disconnect(self._sync_toolbar)
            except (TypeError, RuntimeError) as e:
                _logger.debug("미니 스티키 툴바 연결 해제 생략: %s", e)
        self._active_card = None
        self._toolbar.setEnabled(False)

        for card in self._cards:
            card.text_edit.cancel_file_links()
            card.hide()
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._cards = []

        for note in notes:
            card = StickyMiniCard(
                note["id"], note["content"], note["color"], self._list,
                decryption_failed=note.get("_decryption_failed", False),
            )
            card.set_holiday_theme(self._holiday_theme)
            card.focused.connect(self._set_active_card)
            card.delete_requested.connect(self._on_card_delete)
            self._cards.append(card)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

        self._empty_label.setVisible(not self._cards)
        return True

    def save_all(self) -> bool:
        """모든 카드를 즉시 저장하고 전체 성공 여부를 반환한다."""
        all_saved = True
        for card in list(self._cards):
            try:
                saved = card.save()
            except (RuntimeError, sqlite3.Error, OSError, ValueError) as e:
                saved = False
                _logger.error(
                    "미니 스티키 종료 저장 실패 (id=%s): %s",
                    getattr(card, "note_id", "?"),
                    e,
                )
            if not saved:
                all_saved = False
        return all_saved

    def _set_active_card(self, card):
        if self._active_card is card:
            return
        prev = self._active_card
        if prev is not None:
            try:
                prev.text_edit.cursorPositionChanged.disconnect(self._sync_toolbar)
            except (TypeError, RuntimeError) as e:
                _logger.debug("미니 스티키 툴바 연결 해제 생략: %s", e)
        self._active_card = card
        self._toolbar.setEnabled(True)
        self._toolbar.set_bg_swatch(card._color)
        card.text_edit.cursorPositionChanged.connect(self._sync_toolbar)
        self._sync_toolbar()

    def _sync_toolbar(self):
        if self._active_card is None:
            return
        from ui_sticky import bold_state
        self._toolbar.set_bold_state(bold_state(self._active_card.text_edit))

    def _on_bold(self, on):
        if self._active_card is None:
            return
        from ui_sticky import toggle_bold
        toggle_bold(self._active_card.text_edit, on)

    def _on_link(self):
        if self._active_card is not None:
            self._active_card.text_edit.choose_file_link()

    def _on_todo(self):
        if self._active_card is None:
            return
        from ui_sticky import insert_todo
        insert_todo(self._active_card.text_edit)

    def _on_text_color(self, hex_color):
        if self._active_card is None:
            return
        from ui_sticky import apply_text_color
        apply_text_color(self._active_card.text_edit, hex_color)

    def _on_bg_color(self, hex_color):
        if self._active_card is None:
            return
        self._active_card.apply_color(hex_color)
        self._toolbar.set_bg_swatch(hex_color)

    def _on_card_delete(self, note_id: int):
        # 삭제 대상과 나머지 카드 모두 최근 편집을 먼저 보존한다.
        if not self._flush_pending_cards():
            return
        try:
            db.trash_sticky_note(note_id)
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 스티키 휴지통 이동 실패 (id=%s): %s", note_id, e)
            return
        self.note_trashed.emit(note_id)
        self.reload(flush_pending=False)
