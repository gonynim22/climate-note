# tests/test_ui_sticky.py - 스티키 노트 UI 테스트
import sqlite3

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QTextCursor
from PySide6.QtWidgets import QApplication

import database as db
from ui_sticky import STICKY_COLORS, StickyNoteWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sticky(qtbot, app_dir, qapp):
    """테스트용 스티키 노트 창을 생성해 반환한다."""
    note_id = db.create_sticky_note(note_type="memo", x=100, y=100)
    note_data = {"content": "", "x_pos": 100, "y_pos": 100,
                 "width": 300, "height": 400,
                 "color": db.DEFAULT_STICKY_COLOR}
    win = StickyNoteWindow(note_id, note_data)
    qtbot.addWidget(win)
    return win


def test_strike_button_removed(sticky):
    """리그레션: 기존 strike_btn이 더 이상 존재하지 않는다."""
    assert not hasattr(sticky, "strike_btn")


def test_todo_button_exists(sticky):
    """todo_btn이 헤더에 존재하고 올바른 라벨/툴팁을 가진다."""
    assert hasattr(sticky, "todo_btn")
    assert sticky.todo_btn.text() == "✓"
    assert sticky.todo_btn.toolTip() == "할 일 추가"
    assert sticky.todo_btn.isCheckable() is False


def test_sticky_palette_uses_v26_colors_without_names():
    """v2.6 스티키 배경 팔레트가 지정 색상이며 hover 이름은 비어 있어야 한다."""
    assert STICKY_COLORS == [
        ("#FFFA8E", ""), ("#D0FFF1", ""),
        ("#FFD8FB", ""), ("#C4D5FF", ""),
    ]


def test_decryption_failed_sticky_refuses_to_overwrite_ciphertext(
        app_dir, qtbot, qapp):
    """복호화 실패로 열린 스티키는 빈 화면을 원문 위에 저장하지 않는다."""
    note_id = db.create_sticky_note(note_type="memo", x=100, y=100)
    db.update_sticky_note(note_id, content="보존할 암호문")
    with db._connection(enable_wal=False, read_only=True) as conn:
        before = conn.execute(
            "SELECT content FROM sticky_notes WHERE id = ?", (note_id,)
        ).fetchone()[0]
    note_data = {
        "content": "", "x_pos": 100, "y_pos": 100,
        "width": 300, "height": 400,
        "color": db.DEFAULT_STICKY_COLOR,
        "_decryption_failed": True,
    }
    win = StickyNoteWindow(note_id, note_data)
    qtbot.addWidget(win)

    assert win.save() is False

    with db._connection(enable_wal=False, read_only=True) as conn:
        after = conn.execute(
            "SELECT content FROM sticky_notes WHERE id = ?", (note_id,)
        ).fetchone()[0]
    assert after == before


def test_sticky_color_is_opaque(sticky):
    """스티키 노트 배경/헤더 색상은 투명도 0%(alpha 255)로 적용되어야 한다."""
    sticky._apply_color("#D0FFF1", save=False)

    assert "background: rgba(208, 255, 241, 255);" in sticky.container.styleSheet()
    assert "background: rgba(168, 240, 220, 255);" in sticky.header_widget.styleSheet()


def test_todo_insert_on_empty_line(qtbot, sticky):
    """빈 줄에서 todo_btn 클릭 시 그 줄이 '\uf0c8 '로 바뀐다."""
    # 초기 상태: content=="" → 본문 비어있음
    assert sticky.text_edit.toPlainText() == ""

    qtbot.mouseClick(sticky.todo_btn, Qt.LeftButton)

    assert sticky.text_edit.toPlainText() == "\uf0c8 "


def test_todo_insert_on_nonempty_line_creates_new_block(qtbot, sticky):
    """텍스트가 있는 줄에서 todo_btn 클릭 시 새 블록이 아래에 생성된다."""
    sticky.text_edit.setPlainText("Hello")
    # 커서를 "Hello" 끝으로 이동
    cursor = sticky.text_edit.textCursor()
    cursor.movePosition(QTextCursor.End)
    sticky.text_edit.setTextCursor(cursor)

    qtbot.mouseClick(sticky.todo_btn, Qt.LeftButton)

    # 2개 블록: "Hello" / "\uf0c8 "
    text = sticky.text_edit.toPlainText()
    lines = text.split("\n")
    assert lines[0] == "Hello"
    assert lines[1] == "\uf0c8 "


def _block_text_at_cursor(text_edit, block_index: int) -> str:
    """n번째 블록의 텍스트 반환 헬퍼"""
    block = text_edit.document().findBlockByNumber(block_index)
    return block.text()


def _char_format_at(text_edit, position: int):
    """position 위치의 문자 서식 반환 헬퍼"""
    cursor = text_edit.textCursor()
    cursor.setPosition(position)
    cursor.setPosition(position + 1, QTextCursor.KeepAnchor)
    return cursor.charFormat()


def _click_on_document_position(qtbot, text_edit, position: int):
    """지정한 document position의 글자 중앙을 viewport 좌표로 클릭한다.

    cursorRect(cursor)는 caret(삽입 지점)의 rect를 반환하므로,
    position과 position+1 양쪽의 caret rect 중간 지점을 찍어 해당 글자 위에 클릭.
    """
    from PySide6.QtCore import QPoint
    c_before = text_edit.textCursor()
    c_before.setPosition(position)
    r_before = text_edit.cursorRect(c_before)

    c_after = text_edit.textCursor()
    c_after.setPosition(position + 1)
    r_after = text_edit.cursorRect(c_after)

    x = (r_before.left() + r_after.left()) // 2
    y = (r_before.top() + r_before.bottom()) // 2
    qtbot.mouseClick(text_edit.viewport(), Qt.LeftButton, pos=QPoint(x, y))


def test_todo_click_toggles_to_checked(qtbot, sticky):
    """\uf0c8 문자 클릭 시 \uf14a로 바뀌고 그 줄에 dim + 취소선이 적용된다."""
    sticky.text_edit.setPlainText("\uf0c8 우유 사기")

    _click_on_document_position(qtbot, sticky.text_edit, 0)  # \uf0c8 위치

    assert _block_text_at_cursor(sticky.text_edit, 0) == "\uf14a 우유 사기"
    # \uf14a (pos 0): default color, strikeout 없음
    fmt_check = _char_format_at(sticky.text_edit, 0)
    assert fmt_check.foreground().color() == QColor("#000000")
    assert fmt_check.fontStrikeOut() is False
    # 텍스트 부분 (pos 2 = '우'): dim color, strikeout 있음
    fmt_text = _char_format_at(sticky.text_edit, 2)
    assert fmt_text.foreground().color() == QColor("#888888")
    assert fmt_text.fontStrikeOut() is True


def test_todo_click_toggles_back_to_unchecked(qtbot, sticky):
    """\uf14a 문자 클릭 시 \uf0c8로 복귀하고 dim/취소선이 해제된다."""
    # 미리 체크된 상태로 설정
    sticky.text_edit.setPlainText("\uf0c8 우유 사기")
    _click_on_document_position(qtbot, sticky.text_edit, 0)  # 체크
    assert _block_text_at_cursor(sticky.text_edit, 0) == "\uf14a 우유 사기"

    _click_on_document_position(qtbot, sticky.text_edit, 0)  # 다시 클릭 (언체크)

    assert _block_text_at_cursor(sticky.text_edit, 0) == "\uf0c8 우유 사기"
    fmt_check = _char_format_at(sticky.text_edit, 0)
    assert fmt_check.foreground().color() == QColor("#000000")
    fmt_text = _char_format_at(sticky.text_edit, 2)
    assert fmt_text.foreground().color() == QColor("#000000")
    assert fmt_text.fontStrikeOut() is False


def test_todo_toggle_undo_restores_state_in_one_step(sticky):
    """체크 문자와 본문 서식은 Ctrl+Z 한 번에 함께 복원되어야 한다."""
    sticky.text_edit.setPlainText("\uf0c8 우유 사기")
    sticky.text_edit.document().clearUndoRedoStacks()

    sticky.text_edit._toggle_at(0, "\uf0c8")
    sticky.text_edit.undo()

    assert sticky.text_edit.toPlainText() == "\uf0c8 우유 사기"
    fmt_text = _char_format_at(sticky.text_edit, 2)
    assert fmt_text.foreground().color() == QColor("#000000")
    assert fmt_text.fontStrikeOut() is False


def test_legacy_unicode_checkbox_toggles_to_fontawesome(qtbot, sticky):
    """하위 호환: 기존 '☐' 체크박스도 클릭 시 Font Awesome 완료 아이콘으로 토글된다."""
    sticky.text_edit.setPlainText("☐ 레거시 할 일")

    _click_on_document_position(qtbot, sticky.text_edit, 0)

    assert _block_text_at_cursor(sticky.text_edit, 0) == "\uf14a 레거시 할 일"
    fmt_text = _char_format_at(sticky.text_edit, 2)
    assert fmt_text.foreground().color() == QColor("#888888")
    assert fmt_text.fontStrikeOut() is True


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("\uf0c8", "\uf14a"),
        ("\uf14a", "\uf0c8"),
        ("☐", "\uf14a"),
        ("☑", "\uf0c8"),
    ],
)
def test_all_stored_todo_symbols_remain_toggle_compatible(sticky, source, expected):
    """FA·레거시 유니코드 저장 문자는 모두 기존 방식으로 토글되어야 한다."""
    sticky.text_edit.setPlainText(f"{source} 할 일")

    sticky.text_edit._toggle_at(0, source)

    assert sticky.text_edit.toPlainText() == f"{expected} 할 일"


def test_vector_todo_paint_does_not_mutate_html_or_plain_text(qtbot, qapp):
    """벡터 표시는 view-only이며 저장 HTML/문자에 서식을 기록하지 않는다."""
    from ui_sticky import _TodoTextEdit

    edit = _TodoTextEdit()
    qtbot.addWidget(edit)
    edit.resize(260, 120)
    edit.setHtml(
        "<p><span style=\"font-family:'Font Awesome 6 Free';\">"
        "\uf0c8</span> 미완료</p><p>☑ 레거시 완료</p>"
    )
    edit.show()
    qapp.processEvents()

    html_before = edit.toHtml()
    plain_before = edit.toPlainText()
    edit._todo_glyph_highlighter.rehighlight()
    edit.viewport().grab()  # paintEvent까지 실행
    qapp.processEvents()

    assert edit.toHtml() == html_before
    assert edit.toPlainText() == plain_before
    assert plain_before.split("\n") == ["\uf0c8 미완료", "☑ 레거시 완료"]


def test_todo_hitbox_extends_outside_stored_glyph(qtbot, sticky, qapp):
    """글리프 바깥 여백도 22px 히트박스 안이면 체크 토글이 되어야 한다."""
    sticky.text_edit.setPlainText("\uf0c8 넓은 클릭 영역")
    sticky.show()
    qapp.processEvents()

    pos, _char, icon_rect, hit_rect = sticky.text_edit._visible_todo_visuals()[0]
    target = QPoint(int(icon_rect.left() - 2), int(icon_rect.center().y()))
    assert pos == 0
    assert hit_rect.width() >= 20
    assert hit_rect.contains(target)
    assert not icon_rect.contains(target)

    qtbot.mouseClick(sticky.text_edit.viewport(), Qt.LeftButton, pos=target)

    assert sticky.text_edit.toPlainText().startswith("\uf14a ")


def test_todo_hitbox_does_not_steal_first_body_character(sticky, qapp):
    """넓은 히트박스가 할 일 본문 첫 글자 클릭까지 가로채면 안 된다."""
    sticky.text_edit.setPlainText("\uf0c8 본문")
    sticky.show()
    qapp.processEvents()

    body_cursor = sticky.text_edit.textCursor()
    body_cursor.setPosition(2)
    body_next = sticky.text_edit.textCursor()
    body_next.setPosition(3)
    before_rect = sticky.text_edit.cursorRect(body_cursor)
    after_rect = sticky.text_edit.cursorRect(body_next)
    target = QPoint(
        (before_rect.x() + after_rect.x()) // 2,
        before_rect.center().y(),
    )

    assert sticky.text_edit._checkbox_at_pixel(target) == (None, None)


def test_todo_hover_uses_wide_target_and_pointing_cursor(sticky, qapp):
    """확장 히트박스 hover는 시각 상태와 손 모양 커서를 함께 갱신한다."""
    sticky.text_edit.setPlainText("\uf0c8 hover")
    sticky.show()
    qapp.processEvents()

    _pos, _char, icon_rect, hit_rect = sticky.text_edit._visible_todo_visuals()[0]
    hover_point = QPoint(int(icon_rect.left() - 2), int(icon_rect.center().y()))
    assert hit_rect.contains(hover_point)
    viewport = sticky.text_edit.viewport()
    hover_event = QMouseEvent(
        QEvent.MouseMove,
        QPointF(hover_point),
        QPointF(viewport.mapToGlobal(hover_point)),
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    QApplication.sendEvent(viewport, hover_event)

    assert sticky.text_edit._hovered_todo_pos == 0
    assert sticky.text_edit.viewport().cursor().shape() == Qt.PointingHandCursor

    body_cursor = sticky.text_edit.textCursor()
    body_cursor.setPosition(2)
    body_next = sticky.text_edit.textCursor()
    body_next.setPosition(3)
    before_rect = sticky.text_edit.cursorRect(body_cursor)
    after_rect = sticky.text_edit.cursorRect(body_next)
    body_point = QPoint(
        (before_rect.x() + after_rect.x()) // 2,
        before_rect.center().y(),
    )
    body_event = QMouseEvent(
        QEvent.MouseMove,
        QPointF(body_point),
        QPointF(viewport.mapToGlobal(body_point)),
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    QApplication.sendEvent(viewport, body_event)

    assert sticky.text_edit._hovered_todo_pos is None
    assert sticky.text_edit.viewport().cursor().shape() == Qt.IBeamCursor


def test_enter_on_todo_with_text_continues(qtbot, sticky):
    """\uf0c8 뒤에 텍스트가 있을 때 Enter를 누르면 다음 블록도 '\uf0c8 '로 시작한다."""
    sticky.text_edit.setPlainText("\uf0c8 우유 사기")
    # 커서를 블록 끝으로
    cursor = sticky.text_edit.textCursor()
    cursor.movePosition(QTextCursor.End)
    sticky.text_edit.setTextCursor(cursor)

    qtbot.keyClick(sticky.text_edit, Qt.Key_Return)

    lines = sticky.text_edit.toPlainText().split("\n")
    assert lines[0] == "\uf0c8 우유 사기"
    assert lines[1] == "\uf0c8 "


def test_enter_on_empty_todo_exits(qtbot, sticky):
    """'\uf0c8 '만 있는 빈 todo에서 Enter를 누르면 체크박스가 사라져 일반 줄이 된다."""
    sticky.text_edit.setPlainText("\uf0c8 ")
    cursor = sticky.text_edit.textCursor()
    cursor.movePosition(QTextCursor.End)
    sticky.text_edit.setTextCursor(cursor)

    qtbot.keyClick(sticky.text_edit, Qt.Key_Return)

    # 블록이 하나이고 비어있어야 함
    assert sticky.text_edit.document().blockCount() == 1
    assert sticky.text_edit.toPlainText() == ""


def test_enter_splits_checked_todo_into_clean_unchecked_body(qtbot, sticky):
    """완료 항목 중간을 나눈 새 todo 본문에는 dim/취소선이 남지 않아야 한다."""
    sticky.text_edit.setPlainText("\uf0c8 가나다라마")
    sticky.text_edit._toggle_at(0, "\uf0c8")
    cursor = sticky.text_edit.textCursor()
    cursor.setPosition(sticky.text_edit.toPlainText().index("라"))
    sticky.text_edit.setTextCursor(cursor)

    qtbot.keyClick(sticky.text_edit, Qt.Key_Return)

    assert sticky.text_edit.toPlainText().splitlines() == [
        "\uf14a 가나다",
        "\uf0c8 라마",
    ]
    second_body_pos = sticky.text_edit.toPlainText().index("라")
    fmt_text = _char_format_at(sticky.text_edit, second_body_pos)
    assert fmt_text.foreground().color() == QColor("#000000")
    assert fmt_text.fontStrikeOut() is False


def test_html_roundtrip_preserves_todo_state(qtbot, sticky):
    """체크·미체크 todo를 섞은 문서를 HTML로 저장·재로딩해도 상태가 유지된다.

    사용자 데이터 보존 원칙(CLAUDE.md) 검증.
    """
    sticky.text_edit.setPlainText("\uf0c8 미완료\n\uf0c8 체크할 것")

    # 두 번째 줄 \uf0c8를 토글 (미show 위젯에서 viewport 좌표 맵핑이 붕괴되므로 내부 토글 직접 호출)
    pos_second_box = len("\uf0c8 미완료") + 1
    sticky.text_edit._toggle_at(pos_second_box, "\uf0c8")
    assert sticky.text_edit.toPlainText().split("\n")[1].startswith("\uf14a")

    # HTML 왕복
    html = sticky.text_edit.toHtml()
    from ui_sticky import _TodoTextEdit
    new_edit = _TodoTextEdit()
    qtbot.addWidget(new_edit)
    new_edit.setHtml(html)

    # 텍스트 보존
    text = new_edit.toPlainText()
    lines = text.split("\n")
    assert lines[0] == "\uf0c8 미완료"
    assert lines[1] == "\uf14a 체크할 것"

    # 체크된 줄 서식 보존
    pos_checked_text = text.find("체")
    cursor = new_edit.textCursor()
    cursor.setPosition(pos_checked_text)
    cursor.setPosition(pos_checked_text + 1, QTextCursor.KeepAnchor)
    fmt = cursor.charFormat()
    assert fmt.foreground().color() == QColor("#888888")
    assert fmt.fontStrikeOut() is True

    # 미체크 줄 서식은 기본 (Qt가 기본색을 HTML에 명시하지 않을 수 있으므로 취소선만 검증)
    pos_unchecked_text = text.find("미")
    cursor2 = new_edit.textCursor()
    cursor2.setPosition(pos_unchecked_text)
    cursor2.setPosition(pos_unchecked_text + 1, QTextCursor.KeepAnchor)
    fmt2 = cursor2.charFormat()
    assert fmt2.fontStrikeOut() is False


def test_close_moves_note_to_trash(qtbot, app_dir, qapp, monkeypatch):
    """닫기 확인 시 영구삭제가 아니라 휴지통으로 이동해야 한다."""
    nid = db.create_sticky_note(note_type="memo", x=120, y=130)
    db.update_sticky_note(nid, content="닫을 노트")
    note_data = {"content": "닫을 노트", "x_pos": 120, "y_pos": 130,
                 "width": 300, "height": 400, "color": db.DEFAULT_STICKY_COLOR}
    win = StickyNoteWindow(nid, note_data)
    qtbot.addWidget(win)

    # 확인 팝업을 자동 수락 처리
    monkeypatch.setattr("ui_sticky.Dialog.exec", lambda self: True)

    win._on_close()

    # 열린 목록에서 사라지고 휴지통에 존재
    assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
    assert any(t["id"] == nid for t in db.get_trashed_sticky_notes())


def test_close_flushes_pending_content_before_trash(
        sticky, app_dir, qapp, monkeypatch):
    """닫기 직전 2초 디바운스 중인 본문도 휴지통에 최신값으로 남아야 한다."""
    sticky.text_edit.setPlainText("닫기 직전 수정")
    assert sticky._save_timer.isActive()
    monkeypatch.setattr("ui_sticky.Dialog.exec", lambda self: True)

    sticky._on_close()

    trashed = {
        note["id"]: note for note in db.get_trashed_sticky_notes()
    }
    assert "닫기 직전 수정" in trashed[sticky.note_id]["content"]


def test_close_keeps_note_open_when_pending_save_fails(
        sticky, app_dir, qapp, monkeypatch):
    """최신 본문 저장 실패 시 이전 내용으로 휴지통 이동하지 않는다."""
    sticky.text_edit.setPlainText("저장 실패 내용")
    monkeypatch.setattr("ui_sticky.Dialog.exec", lambda self: True)

    def _fail_update(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated save failure")

    monkeypatch.setattr(db, "update_sticky_note", _fail_update)

    sticky._on_close()

    assert any(
        note["id"] == sticky.note_id for note in db.get_open_sticky_notes()
    )
    assert not any(
        note["id"] == sticky.note_id for note in db.get_trashed_sticky_notes()
    )
    assert sticky._save_timer.isActive()


def test_explicit_save_failure_rearms_retry_timer(
        sticky, app_dir, qapp, monkeypatch):
    """종료 저장이 실패해도 자동 저장 재시도가 사라지면 안 된다."""
    sticky.text_edit.setPlainText("재시도할 내용")

    def _fail_update(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated save failure")

    monkeypatch.setattr(db, "update_sticky_note", _fail_update)

    assert sticky.save() is False
    assert sticky._save_timer.isActive()


def test_close_confirm_dialog_is_top_level_not_clipped(qtbot, app_dir, qapp, monkeypatch):
    """스티키 닫기 확인창은 작은 스티키 내부 오버레이가 아니어야 한다."""
    nid = db.create_sticky_note(note_type="memo", x=120, y=130)
    note_data = {"content": "닫을 노트", "x_pos": 120, "y_pos": 130,
                 "width": 220, "height": 95, "color": db.DEFAULT_STICKY_COLOR}
    win = StickyNoteWindow(nid, note_data)
    qtbot.addWidget(win)
    dialogs = []

    def _capture_exec(dialog):
        dialogs.append(dialog)
        return False

    monkeypatch.setattr("ui_sticky.Dialog.exec", _capture_exec)

    win._on_close()

    assert len(dialogs) == 1
    dialog = dialogs[0]
    assert dialog.parent() is None
    assert dialog.width() >= 360
    assert dialog.height() >= 220
    assert dialog.windowModality() == Qt.ApplicationModal
    assert dialog.windowFlags() & Qt.WindowStaysOnTopHint


def test_delete_color_icon_loads(qapp):
    from fluent_icons import fluent_icon, fluent_icon_path
    assert fluent_icon_path("delete_color").exists()
    icon = fluent_icon("delete_color", size=24)
    assert not icon.isNull()


def test_format_helpers_apply_bold(qtbot, qapp):
    from ui_sticky import _TodoTextEdit, toggle_bold, bold_state
    edit = _TodoTextEdit()
    qtbot.addWidget(edit)
    edit.setPlainText("굵게")
    edit.selectAll()
    toggle_bold(edit, True)
    assert "font-weight" in edit.toHtml()
    assert bold_state(edit) is True
