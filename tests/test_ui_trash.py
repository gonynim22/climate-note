# tests/test_ui_trash.py - 휴지통 창 UI 테스트
import pytest
from PySide6.QtWidgets import QApplication

import database as db
from ui_trash import StickyTrashWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def trash_win(qtbot, app_dir, qapp):
    win = StickyTrashWindow()
    qtbot.addWidget(win)
    # Qt에서 자식 위젯의 isVisible()은 최상위 창이 표시돼야 True가 되므로
    # 빈 상태(empty_label) 가시성 검증을 위해 창을 표시한다.
    win.show()
    qtbot.waitExposed(win)
    return win


def test_table_lists_trashed_notes(qtbot, app_dir, qapp):
    nid = db.create_sticky_note()
    db.update_sticky_note(nid, content="삭제된 노트 본문")
    db.trash_sticky_note(nid)

    win = StickyTrashWindow()
    qtbot.addWidget(win)
    assert win.table.rowCount() == 1
    # 미리보기 텍스트가 본문에서 파생됨
    assert "삭제된 노트" in win.table.item(0, 1).text()


def test_empty_state_when_no_trash(trash_win):
    assert trash_win.table.rowCount() == 0
    assert trash_win.empty_label.isVisible()


def test_restore_emits_signal_and_refreshes(qtbot, app_dir, qapp):
    nid = db.create_sticky_note()
    db.trash_sticky_note(nid)
    win = StickyTrashWindow()
    qtbot.addWidget(win)
    win.table.selectRow(0)

    with qtbot.waitSignal(win.restore_requested, timeout=1000) as blocker:
        win._on_restore()
    assert blocker.args == [nid]


def test_purge_removes_row(qtbot, app_dir, qapp, monkeypatch):
    nid = db.create_sticky_note()
    db.trash_sticky_note(nid)
    win = StickyTrashWindow()
    qtbot.addWidget(win)
    win.table.selectRow(0)

    monkeypatch.setattr("ui_trash.MessageBox.exec", lambda self: True)
    win._on_purge()

    assert win.table.rowCount() == 0
    assert db.get_trashed_sticky_notes() == []


def test_empty_trash_clears_all(qtbot, app_dir, qapp, monkeypatch):
    for _ in range(3):
        nid = db.create_sticky_note()
        db.trash_sticky_note(nid)
    win = StickyTrashWindow()
    qtbot.addWidget(win)

    monkeypatch.setattr("ui_trash.MessageBox.exec", lambda self: True)
    win._on_empty()

    assert win.table.rowCount() == 0
    assert db.get_trashed_sticky_notes() == []


def test_main_restore_handler_reopens_note(qtbot, app_dir, qapp):
    from ui_main import MainCalendarWindow
    nid = db.create_sticky_note("memo", 222, 233, "#C4D5FF")
    db.update_sticky_note(nid, content="복구해서 다시 열 노트")
    db.trash_sticky_note(nid)

    win = MainCalendarWindow()
    qtbot.addWidget(win)

    win._restore_sticky_note(nid)

    # db에서 복구되어 열린 목록에 등장
    assert any(n["id"] == nid for n in db.get_open_sticky_notes())
    # 메인이 해당 노트 창을 다시 생성
    assert nid in win._sticky_windows
