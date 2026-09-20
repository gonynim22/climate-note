"""Display labels must leave the existing editable and persisted document intact."""
import os
from pathlib import Path
from time import monotonic

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetricsF, QTextCursor

import database as db
from sticky_file_links import FileLink
from ui_sticky import _TodoTextEdit, StickyNoteWindow
from ui_sticky_panel import StickySidePanel
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
    edit.viewport().update()


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
