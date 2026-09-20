"""File-link editing shared by floating notes and the large-view cards.

Workers only inspect synthetic/user-selected paths and return strings to a queue.
They never retain a widget, write a database, or launch another application.
"""
from dataclasses import replace
import ntpath
from queue import Empty, Queue
from threading import BoundedSemaphore, Thread
from time import monotonic

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QContextMenuEvent, QDesktopServices, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFileDialog, QMenu, QTextEdit, QToolTip

from security import file_link_origin
from sticky_file_links import PREFIX, UNSUPPORTED, decode, inspect_file, new_link
from ui_sticky_link_labels import (
    FileLabelHighlighter, block_link_spans, label_visuals,
    paint_label_backgrounds, paint_label_details, refresh_warning_spacing,
)

_CHECK_SLOTS = BoundedSemaphore(4)
_CHECK_TIMEOUT = 3.0
_CACHE_SECONDS = 10.0


def _check_paths(paths, results):
    try:
        results.put([inspect_file(path) for path in paths])
    finally:
        _CHECK_SLOTS.release()


class FileLinkTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._link_spans = []
        self._link_cache = {}
        self._link_epoch = 0
        self._link_pending = []
        self._link_dialog = None
        self._link_menu = None
        self._origin = None
        self._link_poll = QTimer(self)
        self._link_poll.setInterval(50)
        self._link_poll.timeout.connect(self._poll_checks)
        self._link_highlighter = FileLabelHighlighter(self.document())
        self.document().contentsChanged.connect(self._links_changed)
        self.viewport().setMouseTracking(True)

    def _allowed(self):
        if self.isReadOnly() or not self.isEnabled() or not self.isVisible():
            return False
        window = self.window()
        return not getattr(window, '_is_locked', False) and not getattr(window, '_hidden_to_tray', False)

    def _current_origin(self):
        if self._origin is None:
            self._origin = file_link_origin()
        return self._origin

    def _ticket(self):
        return self._link_epoch, self.document().revision()

    def _valid_ticket(self, ticket):
        return ticket == self._ticket() and self._allowed()

    def cancel_file_links(self):
        self._link_epoch += 1
        self._link_pending.clear()
        self._link_poll.stop()
        if self._link_dialog is not None:
            self._link_dialog.reject()
        if self._link_menu is not None:
            self._link_menu.close()
        QToolTip.hideText()

    def _links_changed(self):
        self.cancel_file_links()
        spans = []
        block = self.document().begin()
        while block.isValid():
            spans.extend(block_link_spans(block))
            block = block.next()
        self._link_spans = spans
        keys = {s.link.path for s in spans if s.link is not None}
        self._link_cache = {k: v for k, v in self._link_cache.items() if k in keys}
        self.viewport().update()
        self._check_visible_links()

    def _span_cursor(self, span):
        cursor = QTextCursor(self.document())
        cursor.setPosition(span.start)
        cursor.setPosition(span.end, QTextCursor.KeepAnchor)
        return cursor

    def _link_at(self, position):
        return next((s for s in self._link_spans if s.start <= position < s.end), None)

    def link_error(self, span):
        if span.link is None:
            return '연결 정보를 읽을 수 없습니다. 파일을 다시 선택해 주세요.'
        if not self._current_origin() or span.link.origin != self._current_origin():
            return '다른 PC 또는 사용자에서 연결한 파일입니다. 파일을 다시 선택해 주세요.'
        cached = self._link_cache.get(span.link.path)
        return cached[1] if cached else '파일 연결을 확인하는 중입니다.'

    def link_tip(self, span):
        path = span.link.path if span.link else '연결 정보 확인 필요'
        return f'{self._span_cursor(span).selectedText()}\n{path}\n{self.link_error(span) or "Ctrl+클릭으로 파일 열기"}'

    def link_label_visuals(self):
        return label_visuals(self) if self._link_spans else []

    def _refresh_link_display(self):
        # Apply new status geometry before the next input event, not just on paint.
        refresh_warning_spacing(self)
        self.viewport().update()

    def paintEvent(self, event):
        visuals = self.link_label_visuals()
        if visuals:
            paint_label_backgrounds(self, visuals)
        super().paintEvent(event)
        if visuals:
            paint_label_details(self, visuals)

    def warning_visuals(self):
        return [(visual.warning_rect, [visual.span]) for visual in self.link_label_visuals()
                if visual.warning_rect is not None and self.link_error(visual.span)]

    def _span_at_point(self, point):
        return next((v.span for v in self.link_label_visuals() if v.rect.contains(point)), None)

    def _start_check(self, paths, callback):
        if not self._allowed():
            return
        if not _CHECK_SLOTS.acquire(blocking=False):
            callback(['파일 확인이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.'] * len(paths))
            return
        results = Queue(maxsize=1)
        self._link_pending.append((self._ticket(), monotonic(), results, callback, len(paths)))
        Thread(target=_check_paths, args=(tuple(paths), results), daemon=True).start()
        self._link_poll.start()

    def _poll_checks(self):
        pending, self._link_pending = self._link_pending, []
        for ticket, started, queue, callback, count in pending:
            if not self._valid_ticket(ticket):
                continue
            try:
                errors = queue.get_nowait()
            except Empty:
                if monotonic() - started < _CHECK_TIMEOUT:
                    self._link_pending.append((ticket, started, queue, callback, count))
                    continue
                errors = ['파일 확인 시간이 초과되었습니다. 장치를 확인한 뒤 다시 시도해 주세요.'] * count
            callback(errors)
        if not self._link_pending:
            self._link_poll.stop()

    def _check_visible_links(self):
        if not self._allowed():
            return
        paths = list(dict.fromkeys(s.link.path for s in self._link_spans
                     if s.link is not None and s.link.origin == self._current_origin()
                     and (s.link.path not in self._link_cache
                          or monotonic() - self._link_cache[s.link.path][0] > _CACHE_SECONDS)))
        if paths:
            def finished(errors):
                for path, error in zip(paths, errors):
                    self._link_cache[path] = (monotonic(), error)
                self._refresh_link_display()
            self._start_check(paths, finished)

    def _notice(self, text):
        QToolTip.showText(self.mapToGlobal(QPoint(0, 0)), text, self)

    def choose_file_link(self, span=None):
        if not self._allowed():
            return
        # Snapshot the original selection before the file picker takes focus.
        cursor = QTextCursor(self._span_cursor(span) if span else self.textCursor())
        text = cursor.selectedText()
        if ('\u2029' in text or any(c in text for c in '\uf0c8\uf14a☐☑')
                or (span is None and any(s.start < cursor.selectionEnd() and s.end > cursor.selectionStart()
                                        for s in self._link_spans))):
            self._notice('체크박스나 여러 링크를 제외하고 한 문구를 선택해 주세요. 기존 링크는 우클릭으로 다시 연결할 수 있습니다.')
            return
        self.cancel_file_links()
        ticket = self._ticket()
        title = '파일 다시 연결' if span else ('선택한 텍스트에 파일 연결' if text else '파일 링크 추가')
        dialog = QFileDialog(self.window(), title)
        # Qt dialog has an owned lifetime and can always be rejected on lock/hide/reset.
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setLabelText(QFileDialog.Accept, '파일 다시 선택' if span else '연결')
        dialog.setLabelText(QFileDialog.Reject, '취소')
        if text or span:
            # Keep long paths readable without expanding the file picker off-screen.
            from PySide6.QtWidgets import QLabel
            details = QLabel(dialog)
            details.setTextFormat(Qt.PlainText)
            details.setWordWrap(True)
            details.setTextInteractionFlags(Qt.TextSelectableByMouse)
            details.setMaximumWidth(520)
            if span:
                details.setText(f'{text}\n이전: {span.link.path if span.link else "연결 정보 확인 필요"}\n{self.link_error(span)}')
            else:
                details.setText(f'연결할 텍스트: {text}\n파일을 선택해도 이 문구는 그대로 유지됩니다.')
            dialog.layout().addWidget(details, dialog.layout().rowCount(), 0, 1, dialog.layout().columnCount())
        dialog.setNameFilter('로컬 파일 (*)')
        self._link_dialog = dialog

        def chosen(path):
            if self._valid_ticket(ticket):
                self.connect_paths([path], cursor, span)

        def closed(_result):
            if self._link_dialog is dialog:
                self._link_dialog = None
            dialog.deleteLater()

        dialog.fileSelected.connect(chosen)
        dialog.finished.connect(closed)
        dialog.open()

    def connect_paths(self, paths, cursor=None, span=None):
        if not self._allowed() or not paths:
            return
        cursor = QTextCursor(cursor or self.textCursor())
        if span is None and cursor.hasSelection():
            text = cursor.selectedText()
            if (len(paths) != 1 or '\u2029' in text or any(c in text for c in '\uf0c8\uf14a☐☑')
                    or any(s.start < cursor.selectionEnd() and s.end > cursor.selectionStart() for s in self._link_spans)):
                self._notice('체크박스나 기존 링크를 제외하고 한 문구를 선택해 주세요.')
                return
        try:
            links = [new_link(path, self._current_origin()) for path in paths]
        except ValueError as error:
            self._notice(str(error))
            return
        def finished(errors):
            if any(errors):
                self._notice(next(e for e in errors if e))
                return
            for link in links:
                self._link_cache[link.path] = (monotonic(), '')
            self._apply_links(cursor, links, span)
        self._start_check([link.path for link in links], finished)

    def _apply_links(self, cursor, links, span=None):
        cursor.beginEditBlock()
        if cursor.hasSelection() and len(links) == 1:
            self._set_anchor(cursor, links[0], reconnect=span is not None)
        else:
            fmt = QTextCharFormat(cursor.charFormat())
            fmt.setAnchor(False)
            fmt.setAnchorHref('')
            for index, link in enumerate(links):
                if index:
                    cursor.insertText('\n', fmt)
                start = cursor.position()
                cursor.insertText(ntpath.basename(link.path), fmt)
                selected = QTextCursor(cursor)
                selected.setPosition(start, QTextCursor.KeepAnchor)
                self._set_anchor(selected, link)
        cursor.endEditBlock()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self._clear_boundary_anchor()

    def _set_anchor(self, selection, link=None, reconnect=False):
        # Preserve every original font/color run, including UTF-16 surrogate pairs.
        runs = []
        block = self.document().findBlock(selection.selectionStart())
        while block.isValid() and block.position() < selection.selectionEnd():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                start = max(fragment.position(), selection.selectionStart())
                end = min(fragment.position() + fragment.length(), selection.selectionEnd())
                if start < end:
                    runs.append((start, end, fragment.charFormat()))
                it += 1
            block = block.next()
        for start, end, fmt in runs:
            old = decode(fmt.anchorHref())
            underline = old.underline if old else fmt.underlineStyle().value
            if link is None:
                fmt.setAnchor(False)
                fmt.setAnchorHref('')
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle(underline))
            else:
                target = replace(link, underline=underline,
                                 identity=old.identity if reconnect and old else link.identity)
                # Explicit color survives Qt's anchor default on HTML reload.
                if fmt.foreground().style() == Qt.NoBrush:
                    fmt.setForeground(self.palette().text())
                fmt.setAnchor(True)
                fmt.setAnchorHref(target.href())
            cursor = QTextCursor(self.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.setCharFormat(fmt)

    def unlink(self, span):
        if not self._allowed() or span not in self._link_spans:
            return
        cursor = self._span_cursor(span)
        cursor.beginEditBlock()
        self._set_anchor(cursor)
        cursor.endEditBlock()

    def open_file_link(self, span, folder=False):
        if not self._allowed() or span not in self._link_spans:
            return
        if span.link is None or span.link.origin != self._current_origin():
            self.choose_file_link(span)
            return
        path = span.link.path
        def finished(errors):
            self._link_cache[path] = (monotonic(), errors[0])
            self._refresh_link_display()
            if errors[0]:
                self._notice(errors[0])
                self.choose_file_link(span)
                return
            target = ntpath.dirname(path) if folder else path
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(target)):
                self._notice('파일을 열지 못했습니다. 기본 연결 프로그램을 확인해 주세요.')
        self._start_check([path], finished)

    def _add_link_actions(self, menu, span, ticket):
        status = menu.addAction(self.link_error(span) or 'Ctrl+클릭으로 파일 열기')
        status.setEnabled(False)
        for label, operation in (
            ('파일 열기', lambda: self.open_file_link(span)),
            ('파일 위치 열기', lambda: self.open_file_link(span, folder=True)),
            ('다시 연결', lambda: self.choose_file_link(span)),
            ('링크 해제', lambda: self.unlink(span)),
        ):
            action = menu.addAction(label)
            action.triggered.connect(lambda checked=False, op=operation: op() if self._valid_ticket(ticket) else None)

    def show_link_menu(self, spans, global_pos, standard=False):
        if not self._allowed():
            return
        menu = self.createStandardContextMenu() if standard else QMenu(self)
        ticket = self._ticket()
        if standard and spans:
            menu.addSeparator()
        for span in spans:
            target = menu.addMenu(self._span_cursor(span).selectedText()) if len(spans) > 1 else menu
            self._add_link_actions(target, span, ticket)
        self._link_menu = menu
        def closed():
            if self._link_menu is menu:
                self._link_menu = None
            menu.deleteLater()
        menu.aboutToHide.connect(closed)
        menu.popup(global_pos)

    def contextMenuEvent(self, event):
        if not self._allowed():
            return super().contextMenuEvent(event)
        keyboard = event.reason() == QContextMenuEvent.Reason.Keyboard
        position = self.textCursor().position() if keyboard else self.cursorForPosition(event.pos()).position()
        span = (self._link_at(position) or self._link_at(position - 1)) if keyboard else self._span_at_point(event.pos())
        self.show_link_menu([span] if span else [],
                            self.viewport().mapToGlobal(self.cursorRect().center()) if keyboard else event.globalPos(), True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            for rect, spans in self.warning_visuals():
                if rect.contains(event.position()):
                    self.show_link_menu(spans, event.globalPosition().toPoint())
                    event.accept()
                    return
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier:
            point = event.position().toPoint()
            span = self._span_at_point(point)
            if span:
                self.open_file_link(span)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self._span_at_point(event.position()) and event.modifiers() & Qt.ControlModifier:
            self.viewport().setCursor(Qt.PointingHandCursor)

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip and self._allowed():
            span = self._span_at_point(event.pos())
            if span is None:
                span = next((spans[0] for rect, spans in self.warning_visuals() if rect.contains(event.pos())), None)
            if span:
                self._check_visible_links()
                QToolTip.showText(event.globalPos(), self.link_tip(span), self)
                return True
        return super().viewportEvent(event)

    def _clear_boundary_anchor(self):
        cursor = self.textCursor()
        if cursor.hasSelection() or self._link_at(cursor.position()) is not None:
            return
        fmt = cursor.charFormat()
        if fmt.anchorHref().startswith(PREFIX):
            old = decode(fmt.anchorHref())
            fmt.setAnchor(False)
            fmt.setAnchorHref('')
            if old:
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle(old.underline))
            self.setCurrentCharFormat(fmt)

    def keyPressEvent(self, event):
        self._clear_boundary_anchor()
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        self._clear_boundary_anchor()
        super().inputMethodEvent(event)

    def canInsertFromMimeData(self, source):
        return self._allowed() if source.hasUrls() else super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasUrls():
            urls = source.urls()
            if not all(url.isLocalFile() for url in urls):
                self._notice(UNSUPPORTED)
                return
            self.connect_paths([url.toLocalFile() for url in urls])
            return
        self._clear_boundary_anchor()
        super().insertFromMimeData(source)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            self.insertFromMimeData(event.mimeData())
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._check_visible_links()

    def hideEvent(self, event):
        self.cancel_file_links()
        super().hideEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._check_visible_links()
