"""Isolated documents/files only. External launches are always intercepted."""
import os
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor

import database as db
import security
import ui_sticky_links as links_ui
from sticky_file_links import FileLink, decode
from ui_sticky import _TodoTextEdit, StickyNoteWindow
from ui_sticky_panel import StickySidePanel

ORIGIN = 'a' * 64


@pytest.fixture(autouse=True)
def isolated_links(monkeypatch):
    monkeypatch.setattr(links_ui, 'file_link_origin', lambda: ORIGIN)
    monkeypatch.setattr(links_ui.QDesktopServices, 'openUrl', lambda url: pytest.fail('unexpected external launch'))


@pytest.fixture
def edit(qtbot):
    widget = _TodoTextEdit()
    qtbot.addWidget(widget)
    widget.resize(260, 180)
    widget.show()
    return widget


@pytest.fixture
def file_path(tmp_path):
    path = tmp_path / '보고서 & # % 한글 😀.txt'
    path.write_text('synthetic file', encoding='utf-8')
    return str(path)


def select(edit, start, end):
    cursor = edit.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.KeepAnchor)
    edit.setTextCursor(cursor)
    return cursor


def connect(qtbot, edit, file_path):
    edit.connect_paths([file_path])
    qtbot.waitUntil(lambda: bool(edit._link_spans), timeout=5000)
    return edit._link_spans[0]


def test_selected_multiformat_roundtrip_unlink_undo(qtbot, edit, file_path):
    edit.setHtml('<p>앞 <b><span style="color:#7B1FA2">문서</span></b> <i>보기😀</i> 뒤</p>')
    before = edit.toPlainText()
    select(edit, 2, 10)
    span = connect(qtbot, edit, file_path)
    assert edit.toPlainText() == before
    html = edit.toHtml()
    edit.setHtml(html)
    span = edit._link_spans[0]
    assert span.link.path == file_path
    edit.unlink(span)
    assert edit.toPlainText() == before
    assert not edit._link_spans
    fmt = select(edit, 2, 3).charFormat()
    assert fmt.fontWeight() == 700
    assert fmt.foreground().color() == QColor('#7B1FA2')
    assert not fmt.fontUnderline()
    edit.undo()
    assert edit._link_spans
    edit.redo()
    assert not edit._link_spans


def test_plain_legacy_and_arbitrary_anchor_are_unchanged(edit, qtbot):
    edit.setHtml('<p>☐ 구형 <b>문서😀</b> <a href="https://example.com">참고</a></p>')
    qtbot.wait(10)
    before = edit.toHtml()
    modified = edit.document().isModified()
    edit._links_changed()
    edit.viewport().grab()
    assert edit.toHtml() == before
    assert edit.document().isModified() == modified
    assert not edit._link_spans and not edit._link_poll.isActive()
    assert not edit._warning_rail.isVisible()


def test_warning_display_does_not_change_document(qtbot, edit, file_path):
    connect(qtbot, edit, file_path)
    qtbot.waitUntil(lambda: not edit._link_poll.isActive())
    edit.document().clearUndoRedoStacks()
    edit.document().setModified(False)
    before = edit.toHtml(), edit.toPlainText()
    changes = []
    edit.textChanged.connect(lambda: changes.append(True))
    edit._origin = 'b' * 64
    edit._warning_rail.grab()
    assert edit.warning_visuals()
    assert (edit.toHtml(), edit.toPlainText()) == before
    assert not changes and not edit.document().isModified()
    assert not edit.document().isUndoAvailable()
    assert '다른 PC' in edit.link_error(edit._link_spans[0])


def test_other_pc_same_path_requires_reselection(qtbot, edit, file_path, monkeypatch):
    span = connect(qtbot, edit, file_path)
    edit._origin = 'b' * 64
    requested = []
    monkeypatch.setattr(edit, 'choose_file_link', lambda span=None: requested.append(span))
    edit.open_file_link(span)
    assert requested == [span]
    before = edit.toPlainText()
    edit.connect_paths([file_path], edit._span_cursor(span), span)
    qtbot.waitUntil(lambda: edit._link_spans[0].link.origin == 'b' * 64)
    assert edit.toPlainText() == before
    identity = edit._link_spans[0].link.identity
    edit.setHtml(edit.toHtml())
    assert edit._link_spans[0].link.identity == identity
    opened = []
    monkeypatch.setattr(links_ui.QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    edit.open_file_link(edit._link_spans[0])
    qtbot.waitUntil(lambda: len(opened) == 1)
    assert opened[0].toLocalFile().replace('/', '\\') == file_path


def test_add_drop_one_undo_and_boundary_input(qtbot, edit, file_path, tmp_path):
    second = tmp_path / 'second.txt'
    second.write_text('synthetic', encoding='utf-8')
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(file_path), QUrl.fromLocalFile(str(second))])
    edit.insertFromMimeData(mime)
    qtbot.waitUntil(lambda: len(edit._link_spans) == 2)
    assert len(edit.toPlainText().splitlines()) == 2
    edit.undo()
    assert edit.toPlainText() == ''
    edit.redo()
    cursor = edit.textCursor()
    cursor.movePosition(QTextCursor.End)
    edit.setTextCursor(cursor)
    end = cursor.position()
    qtbot.keyClicks(edit, ' tail')
    assert edit._link_at(end) is None
    assert edit.toPlainText().endswith(' tail')


def test_reconnect_only_selected_adjacent_link(qtbot, edit, file_path, tmp_path):
    first = connect(qtbot, edit, file_path)
    # Same path, separate user choices must stay separate links.
    edit.connect_paths([file_path])
    qtbot.waitUntil(lambda: len(edit._link_spans) == 2)
    second = edit._link_spans[1]
    other = tmp_path / 'other.txt'
    other.write_text('synthetic', encoding='utf-8')
    edit.connect_paths([str(other)], edit._span_cursor(first), first)
    qtbot.waitUntil(lambda: edit._link_spans[0].link.path == str(other))
    assert edit._link_spans[1].link == second.link


@pytest.mark.parametrize('symbol', ['☐', '☑', '\uf0c8', '\uf14a'])
def test_todo_links_preserve_markers_and_toggle(qtbot, edit, file_path, symbol):
    edit.setPlainText(symbol + ' 문서')
    select(edit, 2, 4)
    connect(qtbot, edit, file_path)
    original = edit._link_spans[0].link
    edit._toggle_at(0, symbol)
    assert edit._link_spans[0].link == original
    edit.undo()
    assert edit.toPlainText() == symbol + ' 문서'


def test_cancel_dialog_and_stale_worker_cannot_edit(qtbot, edit, file_path, monkeypatch):
    edit.setPlainText('원본')
    edit.selectAll()
    edit.choose_file_link()
    dialog = edit._link_dialog
    assert dialog is not None
    edit.hide()
    dialog.fileSelected.emit(file_path)
    assert edit.toPlainText() == '원본' and not edit._link_spans
    edit.show()
    gate = Event()
    monkeypatch.setattr(links_ui, 'inspect_file', lambda path: (gate.wait(2), '')[1])
    edit.connect_paths([file_path])
    edit.cancel_file_links()
    edit.setPlainText('새 원본')
    gate.set()
    qtbot.wait(100)
    assert edit.toPlainText() == '새 원본' and not edit._link_spans


def test_failed_or_mixed_drop_is_atomic(qtbot, edit, file_path, tmp_path):
    edit.setPlainText('기존')
    before = edit.toHtml()
    edit.connect_paths([file_path, str(tmp_path / 'bad.exe')])
    qtbot.wait(50)
    assert edit.toHtml() == before and not edit._link_pending


def test_timeout_keeps_editor_responsive_and_never_opens(qtbot, edit, file_path, monkeypatch):
    span = connect(qtbot, edit, file_path)
    qtbot.waitUntil(lambda: not edit._link_poll.isActive())
    gate = Event()
    monkeypatch.setattr(links_ui, '_CHECK_TIMEOUT', 0.05)
    monkeypatch.setattr(links_ui, 'inspect_file', lambda path: (gate.wait(2), '')[1])
    requests = []
    monkeypatch.setattr(edit, 'choose_file_link', lambda span: requests.append(span))
    edit.open_file_link(span)
    qtbot.waitUntil(lambda: bool(requests))
    assert '초과' in edit.link_error(span)
    before = edit.toHtml()
    gate.set()
    qtbot.wait(100)
    assert edit.toHtml() == before


def test_toolbar_both_owners_and_encrypted_roundtrip(qtbot, app_dir, file_path, monkeypatch):
    note_id = db.create_sticky_note('memo')
    db.update_sticky_note(note_id, content='☐ 기존 메모')
    note = db.get_open_sticky_notes()[0]
    window = StickyNoteWindow(note_id, note)
    qtbot.addWidget(window)
    window.show()
    clicked = []
    monkeypatch.setattr(window.text_edit, 'choose_file_link', lambda: clicked.append('floating'))
    qtbot.mouseClick(window.link_btn, Qt.LeftButton)
    assert clicked == ['floating']
    select(window.text_edit, 2, 7)
    connect(qtbot, window.text_edit, file_path)
    assert window.save()
    stored = db.get_open_sticky_notes()[0]['content']
    salt = security.SALT_FILE.read_bytes()
    bundle = security.encrypt_with_pin(db.export_all_data().encode('utf-8'), '1234')
    db.import_all_data(security.decrypt_with_pin(bundle, '1234').decode('utf-8'))
    assert all(n['content'] == stored for n in db.get_open_sticky_notes())
    assert security.SALT_FILE.read_bytes() == salt
    assert db.backup_before_operation('import')
    backup = next((app_dir / 'backups').glob('*.cnbak'))
    assert db.validate_backup_bundle(backup)
    db.trash_sticky_note(note_id)
    db.restore_sticky_note(note_id)
    assert next(n for n in db.get_open_sticky_notes() if n['id'] == note_id)['content'] == stored
    panel = StickySidePanel()
    qtbot.addWidget(panel)
    assert panel.reload()
    panel.show()
    card = panel._cards[0]
    panel._set_active_card(card)
    monkeypatch.setattr(card.text_edit, 'choose_file_link', lambda: clicked.append('panel'))
    qtbot.mouseClick(panel._toolbar.link_btn, Qt.LeftButton)
    assert clicked == ['floating', 'panel']
    assert card.text_edit._link_spans[0].link.path == file_path


def test_minimum_width_gutter_wrap_and_scroll(qtbot, edit, file_path):
    edit.resize(200, 100)
    edit.setPlainText('아주 긴 연결 문구 ' * 12)
    edit.selectAll()
    connect(qtbot, edit, file_path)
    edit._origin = 'b' * 64
    edit.verticalScrollBar().setValue(edit.verticalScrollBar().maximum())
    qtbot.wait(10)
    edit._position_rail()
    assert edit._warning_rail.geometry().left() > edit.viewport().geometry().right()
    assert edit._warning_rail.geometry().right() < edit.width()
    assert edit.warning_visuals()
    assert edit._warning_rail.grab().width() > 0


def test_real_missing_file_keeps_text_and_warning(qtbot, edit, file_path, monkeypatch):
    span = connect(qtbot, edit, file_path)
    Path(file_path).unlink()
    monkeypatch.setattr(edit, 'choose_file_link', lambda span: None)
    edit.open_file_link(span)
    qtbot.waitUntil(lambda: '찾을 수 없' in edit.link_error(span))
    assert edit.toPlainText() == Path(file_path).name
    assert edit.warning_visuals()


def test_no_selection_add_and_warning_capture(qtbot, app_dir, file_path):
    note_id = db.create_sticky_note('memo')
    db.update_sticky_note(note_id, content='☐ 보고서 검토\n아래 자료를 확인하세요.\n')
    window = StickyNoteWindow(note_id, db.get_open_sticky_notes()[0])
    qtbot.addWidget(window)
    window.resize(320, 230)
    window.show()
    cursor = window.text_edit.textCursor()
    cursor.movePosition(QTextCursor.End)
    window.text_edit.setTextCursor(cursor)
    connect(qtbot, window.text_edit, file_path)
    window.text_edit._origin = 'b' * 64
    qtbot.wait(20)
    assert window.text_edit.warning_visuals()
    # Native Qt rendering, synthetic note. Captured per harness execution.
    root = os.environ.get('CLIMATENOTE_TEST_APPDATA')
    if root:
        window.grab().save(str(Path(root).parent / 'sticky-file-links.png'))
    window.resize(220, 180)
    qtbot.wait(10)
    assert window.link_btn.geometry().right() < window.width()
    assert window.link_btn.width() == 24


def test_old_dataset_view_never_rewrites_any_row(qtbot, app_dir, file_path):
    db.add_schedule('2026-09-20', '기존 일정😀', '#4CC9F0')
    db.save_memo('2026-09-20', '<b>이전 메모</b>')
    note_id = db.create_sticky_note('memo')
    db.update_sticky_note(note_id, content='☐ 이전 노트😀')
    trash_id = db.create_sticky_note('memo')
    db.update_sticky_note(trash_id, content='휴지통 원본')
    db.trash_sticky_note(trash_id)
    db.create_dday_widget('D-Day 원본', '2026-12-31')
    db.create_focus_widget('집중 원본', '25/5')
    tables = ('schedules', 'memos', 'sticky_notes', 'dday_widgets', 'focus_widgets',
              'focus_sessions', 'shortcuts', 'app_settings')
    def snapshot():
        with db._connection(read_only=True, enable_wal=False) as conn:
            return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in tables}
    before = snapshot()
    salt = security.SALT_FILE.read_bytes()
    window = StickyNoteWindow(note_id, db.get_open_sticky_notes()[0])
    qtbot.addWidget(window)
    window.show()
    window.text_edit.viewport().grab()
    window.text_edit._links_changed()
    qtbot.wait(100)
    assert snapshot() == before
    assert security.SALT_FILE.read_bytes() == salt
    assert not window._save_timer.isActive()


def test_ctrl_click_only_launch_and_keyboard_menu(qtbot, edit, file_path, monkeypatch):
    from PySide6.QtGui import QContextMenuEvent
    span = connect(qtbot, edit, file_path)
    before = edit.toHtml()
    cursor = edit._span_cursor(span)
    cursor.setPosition(span.start + 1)
    point = edit.cursorRect(cursor).center()
    opened = []
    monkeypatch.setattr(links_ui.QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    qtbot.mouseClick(edit.viewport(), Qt.LeftButton, pos=point)
    assert not opened
    qtbot.mouseClick(edit.viewport(), Qt.LeftButton, Qt.ControlModifier, pos=point)
    qtbot.waitUntil(lambda: bool(opened))
    assert edit.toHtml() == before
    edit.setTextCursor(cursor)
    event = QContextMenuEvent(QContextMenuEvent.Keyboard, point, edit.viewport().mapToGlobal(point))
    edit.contextMenuEvent(event)
    assert '다시 연결' in [a.text() for a in edit._link_menu.actions()]
    edit.cancel_file_links()


@pytest.mark.parametrize('mode', ['floating', 'panel'])
@pytest.mark.parametrize('reverse', [False, True])
def test_mouse_selection_button_picker_keeps_label(qtbot, app_dir, file_path, mode, reverse):
    """Use the user's full gesture; do not set a selection programmatically."""
    from PySide6.QtWidgets import QLabel
    note_id = db.create_sticky_note('memo')
    db.update_sticky_note(note_id, content='<p>앞 <b>회의 자료</b> 뒤</p>')
    if mode == 'floating':
        window = StickyNoteWindow(note_id, db.get_open_sticky_notes()[0])
        text = window.text_edit
        button = window.link_btn
        window.resize(330, 230)
    else:
        window = StickySidePanel()
        window.reload()
        text = window._cards[0].text_edit
        button = window._toolbar.link_btn
        window.resize(340, 270)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    text.setFocus()
    qtbot.waitUntil(lambda: text.hasFocus())
    before = text.toHtml()
    cursor = text.textCursor()
    cursor.setPosition(2)
    start = text.cursorRect(cursor).center()
    cursor.setPosition(7)
    end = text.cursorRect(cursor).center()
    if reverse:
        start, end = end, start
    qtbot.mousePress(text.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(text.viewport(), end, delay=10)
    qtbot.mouseRelease(text.viewport(), Qt.LeftButton, pos=end)
    assert text.textCursor().selectedText() == '회의 자료'
    qtbot.mouseClick(button, Qt.LeftButton)
    dialog = text._link_dialog
    assert dialog is not None and dialog.isVisible()
    assert any('연결할 텍스트: 회의 자료' in label.text() for label in dialog.findChildren(QLabel))
    # Moving the editor's live caret while the picker owns focus must not change the target.
    cursor = text.textCursor()
    cursor.movePosition(QTextCursor.End)
    text.setTextCursor(cursor)
    dialog.selectFile(file_path)
    dialog.accept()
    qtbot.waitUntil(lambda: bool(text._link_spans))
    span = text._link_spans[0]
    assert (span.start, span.end) == (2, 7)
    assert text._span_cursor(span).selectedText() == '회의 자료'
    assert span.link.path == file_path
    assert text.toPlainText() == '앞 회의 자료 뒤'
    assert Path(file_path).name not in text.toPlainText()
    assert text._span_cursor(span).charFormat().fontWeight() == 700
    text.setFocus()
    if not reverse:
        # Capture both actual toolbars after the real selection and picker interaction.
        directory = os.environ.get('CLIMATENOTE_TEST_APPDATA')
        if directory:
            window.grab().save(str(Path(directory).parent / f'selected-link-{mode}.png'))
    text.undo()
    assert text.toHtml() == before
    assert not text._link_spans


def test_selected_text_picker_cancel_keeps_html_and_undo(edit, qtbot):
    edit.setHtml('<p>앞 <b>연결할 문구</b> 뒤</p>')
    select(edit, 2, 8)
    edit.document().clearUndoRedoStacks()
    before = edit.toHtml()
    edit.choose_file_link()
    edit._link_dialog.reject()
    assert edit.toHtml() == before
    assert not edit.document().isUndoAvailable()


def test_chain_link_icon_is_bundled_and_renderable(qapp):
    from fluent_icons import fluent_icon, fluent_icon_path
    assert fluent_icon_path('link').is_file()
    assert not fluent_icon('link').isNull()
