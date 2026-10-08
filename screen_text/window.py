"""화면 글자 따기 도구 창. 결과·미리보기는 실행 중 메모리 전용이다.

계약은 docs/SCREEN_TEXT.md를 따른다. 인식 엔진(numpy·onnxruntime)은 처음
인식할 때 작업 스레드에서 불러오고, 사용자가 창을 닫으면 내린다.
"""
import logging
import threading

from PySide6.QtCore import QEvent, QMimeData, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from screen_text.capture import ScreenCapture, grab_screens
from screen_text.layout import Cell, Table, TextLine, build_blocks, has_table, rows_of, to_html, to_plain, to_tsv

_logger = logging.getLogger("app_error")
CONTENT_WIDTH, CONTENT_HEIGHT, SHADOW_MARGIN = 460, 560, 24
CAPTURE_DELAY_MS = 200
PREVIEW_HEIGHT = 90
UNSURE_BACKGROUND = QColor("#FFE58A")
INTRO_TEXT = "복사할 수 없는 이미지나 스캔 문서의 글자를 읽습니다.\n[영역 고르기]를 누른 뒤 화면에서 끌어서 고르세요."
OFFLINE_TEXT = "인터넷 없이 이 PC에서만 처리합니다. 결과는 저장하지 않습니다."
FIRST_LOAD_TEXT = "처음 한 번은 모델을 불러오느라 조금 더 걸립니다."
MESSAGES = {
    "blocked": "보안 프로그램이 화면 캡처를 막아 글자를 딸 수 없습니다.",
    "empty": "고른 영역에서 글자를 찾지 못했습니다.",
    "model": "인식 모델을 확인하지 못했습니다.",
    "failed": "글자를 읽지 못했습니다. 다시 시도해 주세요.",
}
STYLE = """
    QWidget { color:#253447; }
    QWidget#screenTextSurface { background:#FFFFFF; border-radius:16px; }
    QLabel#screenTextTitle { color:#172B4D; font-size:15px; font-weight:bold; }
    QLabel[muted="true"] { color:#677180; font-size:11px; }
    QLabel#screenTextMessage { background:#FFF4E5; color:#8A4B08; border-radius:8px; padding:8px 10px; }
    QLabel#screenTextPreview { background:#F5F7FA; border:1px solid #E1E6ED; border-radius:6px; }
    QLabel#screenTextStatus { background:#FFE58A; color:#5C4200; border-radius:10px; padding:2px 10px; font-size:11px; }
    QLabel#screenTextStatus[done="true"] { background:#EAF2FE; color:#1D4ED8; }
    QPushButton { background:#FFFFFF; border:1px solid #CDD5E0; border-radius:6px; padding:6px 12px; font-size:13px; }
    QPushButton:hover { background:#EDF3FB; border-color:#91AACA; }
    QPushButton:focus { border:1px solid #315C98; }
    QPushButton:disabled { color:#959CA6; background:#F3F4F6; }
    QPushButton[primary="true"] { background:#2563EB; border-color:#2563EB; color:#FFFFFF; font-weight:bold; }
    QPushButton[primary="true"]:disabled { background:#A9C1F2; border-color:#A9C1F2; }
    QPushButton[tab="true"] { background:transparent; border:0; color:#677180; padding:6px 14px; }
    QPushButton[tab="true"]:checked { background:#EAF2FE; color:#1D4ED8; font-weight:bold; }
    QPushButton#screenTextClose { background:transparent; border:0; color:#7A8699; font-size:19px; padding:0 8px; }
    QPlainTextEdit, QTableWidget { border:1px solid #DCE1E8; border-radius:6px; font-size:13px; }
"""


class _Bridge(QObject):
    """작업 스레드 결과를 GUI 스레드로 넘긴다(스레드 간 신호는 큐로 전달된다)."""

    finished = Signal(int, object)
    failed = Signal(int, str)


def _default_engine():
    from screen_text.engine import OcrEngine
    return OcrEngine()


def _image_buffer(image):
    image = image.convertToFormat(QImage.Format_RGB888)
    return image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits())


def _emit(signal, *args):
    """창이 이미 폐기된 뒤 작업 스레드가 끝나면 신호 대상이 없다. 결과를 버린다."""
    try:
        signal.emit(*args)
    except RuntimeError:
        _logger.debug("화면 글자 따기 창이 폐기된 뒤 결과를 버렸습니다")


def _set_property(widget, name, value):
    if widget.property(name) != value:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class ScreenTextWindow(QWidget):
    def __init__(self, parent=None, engine_factory=_default_engine, grab=grab_screens):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("screenText")
        self.setWindowTitle("화면 글자 따기 · 기후노트")
        self.setAccessibleName("화면 글자 따기")
        self.setAttribute(Qt.WA_TranslucentBackground)
        font = QFont(self.font())
        font.setPixelSize(13)
        self.setFont(font)
        self.setStyleSheet(STYLE)
        self._engine_factory = engine_factory
        self._engine = None
        self._engine_lock = threading.Lock()
        self._generation = 0
        self._cancel_event = None
        self._blocks = []
        self._result_preview = QPixmap()  # 현재 결과를 만든 영역 그림(다시 고르기를 취소하면 되돌린다)
        self._pending_preview = QPixmap()  # 읽는 중인 영역 그림
        self._table_rows = []
        self._unsure_tokens = []
        self._text_unsure_left = 0
        self._had_unsure = False
        self._text_dirty = False
        self._filling = False
        self._model_broken = False
        self._tab = "text"
        self._placed = False
        self._drag_origin = None
        self._bridge = _Bridge(self)
        self._bridge.finished.connect(self._on_finished)
        self._bridge.failed.connect(self._on_failed)
        self._capture = ScreenCapture(self, grab=grab)
        self._capture.captured.connect(self._on_captured)
        self._capture.cancelled.connect(self._reappear)
        self._capture.blocked.connect(self._on_blocked)
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.setInterval(CAPTURE_DELAY_MS)
        self._capture_timer.timeout.connect(self._begin_capture)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(1500)
        self._status_timer.timeout.connect(self._update_status)
        self._build()
        self._show_intro(None)
        self.fit_to_screen()

    # ── 화면 구성 ──
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.surface = QWidget(self)
        self.surface.setObjectName("screenTextSurface")
        self.surface.setAttribute(Qt.WA_StyledBackground)
        outer.addWidget(self.surface)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.surface.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self.surface)
        layout.setContentsMargins(18, 0, 18, 16)
        layout.setSpacing(10)

        self.header = QFrame(self.surface)
        self.header.setFixedHeight(48)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("화면 글자 따기", self.header)
        self.title_label.setObjectName("screenTextTitle")
        header.addWidget(self.title_label)
        header.addStretch()
        self.close_button = QPushButton("×", self.header)
        self.close_button.setObjectName("screenTextClose")
        self.close_button.setAccessibleName("화면 글자 따기 닫기")
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        self.header.installEventFilter(self)
        self.title_label.installEventFilter(self)
        layout.addWidget(self.header)

        self.stack = QStackedWidget(self.surface)
        layout.addWidget(self.stack, 1)

        self.intro_page = QWidget()
        intro = QVBoxLayout(self.intro_page)
        intro.setContentsMargins(0, 0, 0, 0)
        intro.setSpacing(12)
        guide = QLabel(INTRO_TEXT)
        guide.setWordWrap(True)
        intro.addWidget(guide)
        self.message_label = QLabel()
        self.message_label.setObjectName("screenTextMessage")
        self.message_label.setWordWrap(True)
        intro.addWidget(self.message_label)
        self.capture_button = QPushButton("영역 고르기")
        self.capture_button.setProperty("primary", True)
        self.capture_button.setFixedHeight(40)
        self.capture_button.clicked.connect(self.start_capture)
        intro.addWidget(self.capture_button)
        self.offline_label = QLabel(OFFLINE_TEXT)
        self.offline_label.setProperty("muted", True)
        self.offline_label.setWordWrap(True)
        intro.addWidget(self.offline_label)
        intro.addStretch()
        self.stack.addWidget(self.intro_page)

        self.busy_page = QWidget()
        busy = QVBoxLayout(self.busy_page)
        busy.setContentsMargins(0, 0, 0, 0)
        busy.addStretch()
        reading = QLabel("읽는 중…")
        reading.setAlignment(Qt.AlignCenter)
        reading.setStyleSheet("font-size:15px; font-weight:bold;")
        busy.addWidget(reading)
        self.first_load_label = QLabel(FIRST_LOAD_TEXT)
        self.first_load_label.setProperty("muted", True)
        self.first_load_label.setAlignment(Qt.AlignCenter)
        busy.addWidget(self.first_load_label)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.cancel_work)
        busy.addWidget(self.cancel_button, 0, Qt.AlignCenter)
        busy.addStretch()
        self.stack.addWidget(self.busy_page)

        self.result_page = QWidget()
        result = QVBoxLayout(self.result_page)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(8)
        self.preview = QLabel()
        self.preview.setObjectName("screenTextPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(PREVIEW_HEIGHT + 8)
        result.addWidget(self.preview)
        tabs = QHBoxLayout()
        self.text_tab = QPushButton("글자")
        self.table_tab = QPushButton("표 모양")
        group = QButtonGroup(self)
        for button, name in ((self.text_tab, "text"), (self.table_tab, "table")):
            button.setProperty("tab", True)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, tab=name: self._set_tab(tab))
            group.addButton(button)
            tabs.addWidget(button)
        tabs.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("screenTextStatus")
        tabs.addWidget(self.status_label)
        result.addLayout(tabs)
        self.result_stack = QStackedWidget()
        self.text_edit = QPlainTextEdit()
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.table = QTableWidget()
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.result_stack.addWidget(self.text_edit)
        self.result_stack.addWidget(self.table)
        result.addWidget(self.result_stack, 1)
        actions = QHBoxLayout()
        self.copy_button = QPushButton("복사")
        self.copy_button.setProperty("primary", True)
        self.copy_button.clicked.connect(self.copy_result)
        self.again_button = QPushButton("다시 고르기")
        self.again_button.clicked.connect(self.start_capture)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.again_button)
        actions.addStretch()
        result.addLayout(actions)
        note = QLabel(OFFLINE_TEXT)
        note.setProperty("muted", True)
        result.addWidget(note)
        self.stack.addWidget(self.result_page)
        for button in self.findChildren(QPushButton):
            button.installEventFilter(self)

    # ── 수명 규약 (ui_main 공용 연결부가 호출) ──
    def show_near(self, anchor, available):
        if not self._placed:
            self.move(anchor.right() + 12, anchor.top())
            self._placed = True
        self.fit_to_screen(available)
        self._reappear()

    def hide_owned_popups(self):
        """예약된 캡처와 화면 오버레이를 닫는다. 찍은 화면은 버린다."""
        self._capture_timer.stop()
        self._capture.cancel(notify=False)

    def cancel_work(self):
        """진행 중인 인식을 취소한다. 늦게 도착한 결과는 실행 번호로 버린다."""
        busy = self.stack.currentWidget() is self.busy_page
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_event = None
        self._generation += 1
        self._pending_preview = QPixmap()
        if busy:
            if self._blocks:
                self.preview.setPixmap(self._result_preview)
                self._show_result()
            else:
                self.preview.clear()
                self._show_intro(None)

    def fit_to_screen(self, available=None):
        if available is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
        margin = min(SHADOW_MARGIN, max(0, (available.width() - CONTENT_WIDTH) // 2),
                     max(0, (available.height() - CONTENT_HEIGHT) // 2))
        self.layout().setContentsMargins(margin, margin, margin, margin)
        shadow = self.surface.graphicsEffect()
        shadow.setBlurRadius(max(0, margin - 4))
        shadow.setOffset(0, min(4, margin))
        shadow.setEnabled(margin > 0)
        self.resize(min(CONTENT_WIDTH + 2 * margin, available.width()),
                    min(CONTENT_HEIGHT + 2 * margin, available.height()))
        self.move(max(available.left(), min(self.x(), available.right() + 1 - self.width())),
                  max(available.top(), min(self.y(), available.bottom() + 1 - self.height())))

    def release_model(self):
        with self._engine_lock:
            self._engine = None

    def shutdown(self):
        self.hide_owned_popups()
        self.cancel_work()
        self._blocks, self._table_rows, self._unsure_tokens = [], [], []
        self._had_unsure = False
        self._result_preview = self._pending_preview = QPixmap()
        self.preview.clear()
        self._filling = True
        self.text_edit.clear()
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self._filling = False
        self.release_model()
        self._show_intro(None)

    # ── 사용자 동작 ──
    def start_capture(self):
        if not self.isEnabled() or self.stack.currentWidget() is self.busy_page:
            return
        self.hide()
        self._capture_timer.start()

    def copy_result(self):
        mime = QMimeData()
        if self._tab == "table":
            mime.setText(to_tsv(self._blocks))
            mime.setHtml(to_html(self._blocks))
        else:
            mime.setText(self.text_edit.toPlainText())
        QGuiApplication.clipboard().setMimeData(mime)
        self.status_label.setText("복사했습니다")
        _set_property(self.status_label, "done", True)
        self._status_timer.start()

    # ── 캡처와 인식 ──
    def _begin_capture(self):
        if self.isEnabled():
            self._capture.start()

    def _reappear(self):
        self.show()
        self.raise_()
        self.activateWindow()
        target = self.copy_button if self.stack.currentWidget() is self.result_page else self.capture_button
        target.setFocus(Qt.OtherFocusReason)

    def _on_blocked(self):
        self._show_intro("blocked")
        self._reappear()

    def _on_captured(self, image):
        pixmap = QPixmap.fromImage(image)
        if pixmap.height() > PREVIEW_HEIGHT:
            pixmap = pixmap.scaledToHeight(PREVIEW_HEIGHT, Qt.SmoothTransformation)
        if pixmap.width() > CONTENT_WIDTH - 40:
            pixmap = pixmap.scaledToWidth(CONTENT_WIDTH - 40, Qt.SmoothTransformation)
        self._pending_preview = pixmap
        self.preview.setPixmap(pixmap)
        self._generation += 1
        generation, event = self._generation, threading.Event()
        self._cancel_event = event
        self.first_load_label.setVisible(self._engine is None)
        self.stack.setCurrentWidget(self.busy_page)
        threading.Thread(target=self._work, args=(generation, _image_buffer(image), event),
                         name="screen-text-ocr", daemon=True).start()
        self._reappear()
        self.cancel_button.setFocus(Qt.OtherFocusReason)

    def _engine_for_work(self):
        with self._engine_lock:
            if self._engine is None:
                self._engine = self._engine_factory()
            return self._engine

    def _work(self, generation, buffer, event):
        """작업 스레드. Qt 위젯을 만지지 않고 신호로만 결과를 보낸다."""
        from screen_text.engine import ModelIntegrityError, RecognitionCancelled, rgb_from_buffer
        try:
            boxes = self._engine_for_work().recognize(rgb_from_buffer(*buffer), event.is_set)
        except RecognitionCancelled:
            return
        except ModelIntegrityError:
            _emit(self._bridge.failed, generation, "model")
            return
        except Exception as error:  # 작업 스레드 경계: 어떤 오류도 창을 '읽는 중'에 멈춰 두지 않는다
            _logger.error("화면 글자 인식 실패: %s", type(error).__name__)
            _emit(self._bridge.failed, generation, "failed")
            return
        _emit(self._bridge.finished, generation, boxes)

    def _on_finished(self, generation, boxes):
        if generation != self._generation:
            return
        self._cancel_event = None
        blocks = build_blocks(boxes)
        if not blocks:
            self._show_intro("empty")
            return
        self._blocks = blocks
        self._result_preview, self._pending_preview = self._pending_preview, QPixmap()
        self._had_unsure = any(cell.unsure for block in blocks for row in rows_of(block) for cell in row)
        self._tab = "table" if has_table(blocks) else "text"
        self._fill_table()
        self._fill_text()
        self._show_result()

    def _on_failed(self, generation, kind):
        if generation != self._generation:
            return
        self._cancel_event = None
        self._show_intro(kind)

    # ── 결과 표시와 편집 ──
    def _show_intro(self, kind):
        self._model_broken = self._model_broken or kind == "model"
        self.message_label.setText(MESSAGES.get(kind, ""))
        self.message_label.setVisible(kind is not None)
        self.capture_button.setEnabled(not self._model_broken)
        self.stack.setCurrentWidget(self.intro_page)

    def _show_result(self):
        self.stack.setCurrentWidget(self.result_page)
        self.table_tab.setVisible(has_table(self._blocks))
        self._set_tab(self._tab)

    def _set_tab(self, name):
        self._tab = name
        self.text_tab.setChecked(name == "text")
        self.table_tab.setChecked(name == "table")
        self.result_stack.setCurrentWidget(self.text_edit if name == "text" else self.table)
        self._update_status()

    def _fill_text(self):
        self._filling = True
        self.text_edit.setPlainText(to_plain(self._blocks))
        self._filling = False
        self._text_dirty = False
        self._unsure_tokens = [cell.text for block in self._blocks for row in rows_of(block)
                               for cell in row if cell.unsure]
        self._highlight_text()

    def _fill_table(self):
        self._filling = True
        self._table_rows = []
        columns = max([len(block.rows[0]) for block in self._blocks if isinstance(block, Table)] + [1])
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(columns)
        for block in self._blocks:
            for row_index, row in enumerate(rows_of(block)):
                position = self.table.rowCount()
                self.table.insertRow(position)
                self._table_rows.append((block, row_index))
                if isinstance(block, TextLine):
                    item = QTableWidgetItem(" ".join(cell.text for cell in row if cell.text))
                    if any(cell.unsure for cell in row):
                        item.setBackground(UNSURE_BACKGROUND)
                    self.table.setItem(position, 0, item)
                    if columns > 1:
                        self.table.setSpan(position, 0, 1, columns)
                    continue
                for column, cell in enumerate(row):
                    item = QTableWidgetItem(cell.text)
                    if cell.unsure:
                        item.setBackground(UNSURE_BACKGROUND)
                    self.table.setItem(position, column, item)
        self.table.resizeColumnsToContents()
        self._filling = False

    def _on_table_item_changed(self, item):
        if self._filling:
            return
        block, row_index = self._table_rows[item.row()]
        text = item.text()
        if isinstance(block, TextLine):
            if text != " ".join(cell.text for cell in block.cells if cell.text):
                block.cells[:] = [Cell(text)]
        else:
            cell = block.rows[row_index][item.column()]
            if text != cell.text:
                cell.text, cell.unsure = text, False
        self._filling = True
        item.setData(Qt.BackgroundRole, None)
        self._filling = False
        if not self._text_dirty:
            self._fill_text()
        self._update_status()

    def _on_text_changed(self):
        if self._filling:
            return
        self._text_dirty = True
        self._highlight_text()
        self._update_status()

    def _highlight_text(self):
        """확인 필요 글자가 아직 그대로 남은 곳만 노랗게 표시한다."""
        document = self.text_edit.document()
        cursor = QTextCursor(document)
        selections = []
        for token in self._unsure_tokens:
            found = document.find(token, cursor)
            if found.isNull():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = found
            selection.format.setBackground(UNSURE_BACKGROUND)
            selections.append(selection)
            cursor = found
        self._text_unsure_left = len(selections)
        self.text_edit.setExtraSelections(selections)

    def _update_status(self):
        if self._tab == "text":
            left = self._text_unsure_left
        else:
            left = sum(cell.unsure for block in self._blocks for row in rows_of(block) for cell in row)
        if left:
            self.status_label.setText(f"확인 필요 {left}곳")
        else:
            self.status_label.setText("확인 완료" if self._had_unsure else "불확실한 곳 없음")
        _set_property(self.status_label, "done", not left)

    # ── 창 조작 ──
    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and isinstance(watched, QAbstractButton) and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                watched.click()
            return True
        if watched in (getattr(self, "header", None), getattr(self, "title_label", None)):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_origin = (event.globalPosition().toPoint(), self.pos())
                return True
            if event.type() == QEvent.MouseMove and self._drag_origin and event.buttons() & Qt.LeftButton:
                origin, position = self._drag_origin
                self.move(position + event.globalPosition().toPoint() - origin)
                return True
            if event.type() == QEvent.MouseButtonRelease and self._drag_origin:
                self._drag_origin = None
                self.fit_to_screen()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """사용자가 닫으면 작업을 멈추고 모델을 내린다. 결과는 다음 열기까지 유지한다."""
        self.hide_owned_popups()
        self.cancel_work()
        self.release_model()
        super().closeEvent(event)
