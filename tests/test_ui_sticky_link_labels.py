"""Display labels must leave the existing editable and persisted document intact."""
import os
from pathlib import Path
from time import monotonic

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetricsF, QInputMethodEvent, QTextCursor
from PySide6.QtWidgets import QApplication

import database as db
from sticky_file_links import FileLink
from ui_sticky import _TodoTextEdit, StickyNoteWindow
from ui_sticky_panel import StickySidePanel, _PanelTodoEdit
import ui_sticky_links as links_ui
from ui_sticky_link_labels import file_type, PAPER, BADGE

ORIGIN = 'a' * 64


@pytest.fixture
def edit(qtbot, monkeypatch):
    monkeypatch.setattr(links_ui, 'file_link_origin', lambda: ORIGIN)
    monkeypatch.setattr(links_ui, 'inspect_file', lambda path: '')
    monkeypatch.setattr(links_ui.QDesktopServices, 'openUrl', lambda url: pytest.fail('unexpected launch'))
    widget = _TodoTextEdit()
    qtbot.addWidget(widget)
    widget.resize(420, 220)
    widget.show()
    return widget


def link_html(label, extension='pdf', origin=ORIGIN, identity='1' * 32):
    href = FileLink(r'C:\synthetic\document.' + extension, origin, identity).href()
    return f'<a href="{href}">{label}</a>'


def settle(edit, qtbot):
    qtbot.waitUntil(lambda: bool(edit.link_label_visuals()))
    edit.cancel_file_links()
    for span in edit._link_spans:
        if span.link:
            edit._link_cache[span.link.path] = (monotonic(), '')
    edit._refresh_link_display()


@pytest.mark.parametrize('extension,expected', [('pdf','PDF'),('HwPx','HWPX'),('xlsx','XLSX'),
    ('docx','DOCX'),('jpg','JPG'),('unknown','FILE'),('','FILE')])
def test_type_badge_uses_path_not_selected_label(extension, expected):
    link = FileLink(r'C:\synthetic\회의 자료' + ('.' + extension if extension else ''), ORIGIN, '1'*32)
    assert file_type(link) == expected
    assert file_type(None) == 'FILE'


@pytest.mark.parametrize('label', ['회의 자료','😀 자료','👩‍💻 자료','é 자료','한','😀','é'])
def test_label_display_preserves_text_formats_copy_and_undo(edit, qtbot, label):
    edit.setHtml('<p>앞 ' + link_html('<b>' + label + '</b>') + ' 뒤</p>')
    settle(edit, qtbot)
    edit.document().clearUndoRedoStacks()
    edit.document().setModified(False)
    before = edit.toHtml(), edit.toPlainText(), edit.document().revision()
    changed = []
    edit.textChanged.connect(lambda: changed.append(True))
    visual = edit.link_label_visuals()[0]
    assert visual.spec.kind == 'PDF'
    assert visual.badge_rect is not None and visual.rect.contains(visual.badge_rect)
    assert visual.glyphs[0][1].x() >= visual.badge_rect.right()
    for boundary, point in visual.glyphs:
        cursor = QTextCursor(edit.document())
        cursor.setPosition(boundary.end)
        assert point.x() + QFontMetricsF(boundary.font).horizontalAdvance(boundary.text) <= edit.cursorRect(cursor).left() - boundary.after + 1
    edit.setTextCursor(edit._span_cursor(edit._link_spans[0]))
    mime = edit.createMimeDataFromSelection()
    assert mime.text() == label
    assert 'PDF' not in mime.text() and 'PDF' not in mime.html()
    edit.viewport().grab()
    edit._origin = 'b'*64
    edit.viewport().grab()
    assert edit.warning_visuals()
    assert (edit.toHtml(), edit.toPlainText(), edit.document().revision()) == before
    assert not changed and not edit.document().isModified()
    assert not edit.document().isUndoAvailable()
    # A real edit is still exactly one undo, without a decoration-only undo step.
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.End)
    edit.setTextCursor(cursor)
    qtbot.keyClicks(edit, 'z')
    edit.undo()
    assert edit.toHtml() == before[0]


def test_label_background_badge_and_inline_warning_pixels(edit, qtbot):
    edit.setHtml('<p>앞 ' + link_html('회의 자료') + ' 뒤</p>')
    settle(edit, qtbot)
    edit.clearFocus()
    image = edit.viewport().grab().toImage()
    colors = {image.pixelColor(x,y).name() for x in range(image.width()) for y in range(image.height())}
    assert PAPER.name() in colors and BADGE.name() in colors
    visual = edit.link_label_visuals()[0]
    edit._origin = 'b'*64
    warning, _ = edit.warning_visuals()[0]
    assert warning.left() > visual.rect.right()
    cursor = QTextCursor(edit.document())
    cursor.setPosition(edit._link_spans[0].end)
    assert warning.right() < edit.cursorRect(cursor).left()
    qtbot.mouseClick(edit.viewport(), Qt.LeftButton, pos=warning.center().toPoint())
    assert edit._link_menu is not None
    edit.cancel_file_links()


def test_badge_ctrl_click_and_context_menu_target_link(edit, qtbot, monkeypatch):
    edit.setHtml(link_html('회의 자료'))
    settle(edit, qtbot)
    requested = []
    monkeypatch.setattr(edit, 'open_file_link', lambda span, folder=False: requested.append(span))
    visual = edit.link_label_visuals()[0]
    point = visual.badge_rect.center().toPoint()
    qtbot.mouseClick(edit.viewport(), Qt.LeftButton, pos=point)
    assert not requested
    qtbot.mouseClick(edit.viewport(), Qt.LeftButton, Qt.ControlModifier, pos=point)
    assert requested == [edit._link_spans[0]]


def test_adjacent_links_and_shifted_blocks_keep_distinct_badges(edit, qtbot):
    edit.setHtml('<p>머리</p><p>' + link_html('첫 문서', 'pdf') +
                 link_html('둘째 문서', 'xlsx', identity='2'*32) + ' 뒤</p>')
    settle(edit, qtbot)
    cursor = QTextCursor(edit.document())
    cursor.setPosition(0)
    cursor.insertText('앞에 새 문구 ')
    visuals = edit.link_label_visuals()
    assert [v.spec.kind for v in visuals] == ['PDF','XLSX']
    assert [v.span for v in visuals] == edit._link_spans
    assert visuals[0].rect.right() < visuals[1].rect.left()


def test_mouse_selection_and_delete_first_link_character(edit, qtbot):
    edit.setHtml('<p>앞 ' + link_html('회의 자료') + ' 뒤</p>')
    settle(edit, qtbot)
    original = edit.toHtml()
    span = edit._link_spans[0]
    cursor = QTextCursor(edit.document())
    cursor.setPosition(span.start)
    start = edit.cursorRect(cursor).center()
    cursor.setPosition(span.end)
    end = edit.cursorRect(cursor).center()
    qtbot.mousePress(edit.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(edit.viewport(), end, delay=10)
    qtbot.mouseRelease(edit.viewport(), Qt.LeftButton, pos=end)
    assert edit.textCursor().selectedText() == '회의 자료'
    cursor.setPosition(span.start)
    cursor.movePosition(QTextCursor.NextCharacter)
    edit.setTextCursor(cursor)
    qtbot.keyClick(edit, Qt.Key_Backspace)
    assert edit.toPlainText() == '앞 의 자료 뒤'
    assert edit.link_label_visuals()[0].glyphs[0][0].text == '의'
    edit.undo()
    assert edit.toHtml() == original


@pytest.mark.parametrize('editor_type', [_TodoTextEdit, _PanelTodoEdit])
@pytest.mark.parametrize('body_px', [11, 12, 13])
def test_compact_badge_clears_border_and_no_space_suffix(editor_type, body_px, qtbot, monkeypatch):
    monkeypatch.setattr(links_ui, 'inspect_file', lambda path: '')
    edit = editor_type()
    qtbot.addWidget(edit)
    edit._origin = ORIGIN
    font = QFont('Malgun Gothic')
    font.setPixelSize(body_px)
    edit.setFont(font)
    edit.resize(420, 150)
    edit.setHtml('<p>앞' + link_html('회의자료') + '다음글자</p>')
    edit.show()
    settle(edit, qtbot)
    visual = edit.link_label_visuals()[0]
    assert visual.spec.badge_font.pixelSize() == 8
    assert visual.badge_rect.height() <= 11
    assert visual.badge_rect.top() - visual.rect.top() >= 2
    assert visual.rect.bottom() - visual.badge_rect.bottom() >= 2
    cursor = QTextCursor(edit.document())
    cursor.setPosition(visual.span.end)
    assert 1.5 <= edit.cursorRect(cursor).left() - visual.rect.right() <= 2.5
    last, point = visual.glyphs[-1]
    end = point.x() + QFontMetricsF(last.font).horizontalAdvance(last.text)
    assert edit.cursorRect(cursor).left() - end <= 7
    assert edit.toPlainText() == '앞회의자료다음글자'
    assert not edit.warning_visuals()
    root = os.environ.get('CLIMATENOTE_TEST_APPDATA')
    if root:
        edit.viewport().grab().save(str(Path(root).parent / f'compact-label-{editor_type.__name__}-{body_px}.png'))


@pytest.mark.parametrize('label', ['자료', '😀', 'é'])
def test_warning_spacing_tracks_status_without_document_change(edit, qtbot, label):
    edit.setHtml('<p>' + link_html(label) + link_html('다음', 'xlsx', identity='2'*32) + '끝</p>')
    settle(edit, qtbot)
    edit.setTextCursor(edit._span_cursor(edit._link_spans[0]))
    edit.document().clearUndoRedoStacks()
    edit.document().setModified(False)
    before = edit.toHtml(), edit.document().revision(), edit.textCursor().selectedText()
    signals = []
    edit.textChanged.connect(lambda: signals.append('textChanged'))
    edit.document().contentsChanged.connect(lambda: signals.append('contentsChanged'))
    normal = edit.link_label_visuals()
    positions = [edit.cursorRect(edit._span_cursor(s)).left() for s in edit._link_spans]
    for _ in range(3):
        # Change only the first link, as an asynchronous missing-file result does.
        edit._link_cache[edit._link_spans[0].link.path] = (monotonic(), '파일 없음')
        missing = edit.link_label_visuals()
        assert missing[0].warning_rect is not None and missing[1].warning_rect is None
        assert missing[0].rect == normal[0].rect
        assert missing[0].warning_rect.right() < missing[1].rect.left()
        assert missing[1].rect.left() - normal[1].rect.left() == pytest.approx(14, abs=.5)
        edit._link_cache[edit._link_spans[0].link.path] = (monotonic(), '')
        assert [v.rect for v in edit.link_label_visuals()] == [v.rect for v in normal]
    assert (edit.toHtml(), edit.document().revision(), edit.textCursor().selectedText()) == before
    assert positions == [edit.cursorRect(edit._span_cursor(s)).left() for s in edit._link_spans]
    assert not signals and not edit.document().isModified() and not edit.document().isUndoAvailable()


def test_warning_reflows_wrapped_label_without_covering_next_character(edit, qtbot):
    edit.resize(180, 240)
    edit.setHtml('<p>' + link_html('회의자료' * 12) + '다음</p>')
    settle(edit, qtbot)
    edit._origin = 'b' * 64
    visuals = edit.link_label_visuals()
    assert len(visuals) > 1
    assert sum(v.badge_rect is not None for v in visuals) == 1
    assert sum(v.warning_rect is not None for v in visuals) == 1
    warning = visuals[-1].warning_rect
    assert warning.right() <= edit.viewport().width()
    cursor = QTextCursor(edit.document())
    cursor.setPosition(edit._link_spans[0].end)
    caret = edit.cursorRect(cursor)
    assert warning.right() < caret.left() or warning.bottom() <= caret.top()


def test_async_status_updates_cursor_geometry_before_paint(edit, qtbot, monkeypatch):
    edit.setHtml('<p>' + link_html('자료') + '다음</p>')
    settle(edit, qtbot)
    span = edit._link_spans[0]
    cursor = QTextCursor(edit.document())
    cursor.setPosition(span.end)
    normal_x = edit.cursorRect(cursor).left()
    before = edit.toHtml(), edit.document().revision()
    callbacks = []
    monkeypatch.setattr(edit, '_start_check', lambda paths, callback: callbacks.append(callback))
    edit._link_cache.clear()
    edit._check_visible_links()
    callbacks.pop()(['파일 없음'])
    # Read native cursor geometry without invoking label_visuals or painting.
    assert edit.cursorRect(cursor).left() - normal_x == pytest.approx(14, abs=.5)
    edit._link_cache.clear()
    edit._check_visible_links()
    callbacks.pop()([''])
    assert edit.cursorRect(cursor).left() == normal_x
    assert (edit.toHtml(), edit.document().revision()) == before


def test_status_update_preserves_active_ime_preedit(edit, qtbot):
    edit.setHtml('<p>' + link_html('자료') + '다음</p>')
    settle(edit, qtbot)
    edit.link_label_visuals()
    cursor = QTextCursor(edit.document())
    cursor.movePosition(QTextCursor.End)
    edit.setTextCursor(cursor)
    edit.setFocus()
    QApplication.sendEvent(edit, QInputMethodEvent('한', []))
    layout = edit.document().begin().layout()
    assert layout.preeditAreaText() == '한'
    before = edit.toHtml(), edit.document().revision(), layout.formats()
    edit._origin = 'b' * 64
    assert edit.link_label_visuals()[0].warning_rect is None
    assert (edit.toHtml(), edit.document().revision(), layout.formats()) == before
    assert layout.preeditAreaText() == '한'
    QApplication.sendEvent(edit, QInputMethodEvent('', []))
    assert not layout.preeditAreaText()
    assert edit.link_label_visuals()[0].warning_rect is not None


@pytest.mark.parametrize('mode', ['floating','panel'])
def test_two_views_labels_toolbar_and_save_roundtrip(qtbot, app_dir, monkeypatch, mode):
    monkeypatch.setattr(links_ui, 'file_link_origin', lambda: ORIGIN)
    monkeypatch.setattr(links_ui, 'inspect_file', lambda path: '')
    monkeypatch.setattr(links_ui.QDesktopServices, 'openUrl', lambda url: pytest.fail('unexpected launch'))
    note_id = db.create_sticky_note('memo')
    html = '<p>☐ ' + link_html('<b>회의 자료</b>') + ' 확인</p><p>' + link_html('월별 실적','xlsx',identity='2'*32) + ' 확인</p>'
    db.update_sticky_note(note_id, content=html)
    if mode == 'floating':
        window = StickyNoteWindow(note_id, db.get_open_sticky_notes()[0])
        edit = window.text_edit
        toolbar = window
        save = window.save
        window.resize(350, 235)
    else:
        window = StickySidePanel()
        window.reload()
        edit = window._cards[0].text_edit
        toolbar = window._toolbar
        save = window.save_all
        window.resize(360, 280)
    qtbot.addWidget(window)
    window.show()
    settle(edit, qtbot)
    assert toolbar.link_btn.size() == toolbar.todo_btn.size()
    assert toolbar.link_btn.focusPolicy() == Qt.NoFocus
    assert 'border: 1px solid' in toolbar.link_btn.styleSheet()
    before = edit.toHtml()
    edit._origin = 'b'*64
    edit.viewport().grab()
    assert edit.toHtml() == before
    save()
    stored = next(n for n in db.get_open_sticky_notes() if n['id'] == note_id)['content']
    assert stored == before
    reload = _TodoTextEdit()
    qtbot.addWidget(reload)
    reload.setHtml(stored)
    assert reload.toPlainText() == edit.toPlainText()
    assert 'PDF' not in reload.toPlainText() and 'XLSX' not in reload.toPlainText()
    root = os.environ.get('CLIMATENOTE_TEST_APPDATA')
    if root:
        window.grab().save(str(Path(root).parent / f'sticky-label-{mode}.png'))
