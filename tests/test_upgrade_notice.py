"""v4.1 업데이트 1회 안내: 예전 형식 DB를 올린 실행에서만 알리고, 아무것도 저장하지 않는다."""
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Dialog

import database as db
import security
import ui_main
from app_info import APP_VERSION
from show_desktop_guard import ShowDesktopKeeper

FIXTURE = Path(__file__).parent / "fixtures" / "schema_v17.sql"
OLD_VERSION_WINDOW = "데이터 보호를 위해 실행을 중단했습니다"


def _make_v17(app_dir):
    db_file = app_dir / "calendar.db"
    for path in (db_file, app_dir / "calendar.db-wal", app_dir / "calendar.db-shm"):
        path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(FIXTURE.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-10-15", security.encrypt("기존 일정"), "2026-10-14 09:00:00", "#FFD166"))
        conn.execute("PRAGMA user_version = 17")
        conn.commit()
    finally:
        conn.close()


def _dump():
    with db._connection(read_only=True, enable_wal=False) as conn:
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for table in ("app_settings", "schedules", "memos", "sticky_notes")}


def test_initialize_database_reports_upgrade_once(app_dir):
    import main as app_main

    _make_v17(app_dir)
    calls = []
    assert app_main._initialize_database(on_upgrade=calls.append) is True
    assert calls == [17]
    assert app_main._initialize_database(on_upgrade=calls.append) is True  # 이미 새 형식
    assert calls == [17]


def test_initialize_database_does_not_report_fresh_install(app_dir):
    import main as app_main

    for name in ("calendar.db", "calendar.db-wal", "calendar.db-shm"):
        (app_dir / name).unlink(missing_ok=True)
    calls = []
    assert app_main._initialize_database(on_upgrade=calls.append) is True
    assert calls == []


def test_upgrade_notice_text_explains_the_old_version_window():
    text = ui_main.upgrade_notice_text()
    assert f"기후노트 {APP_VERSION}로 업데이트했습니다" in text
    assert f"'{OLD_VERSION_WINDOW}'" in text
    assert "데이터는 바뀌지 않습니다" in text
    assert "이전 버전 EXE 파일과 바탕화면 바로가기는 지워 주세요" in text
    assert "backups" in text


def test_upgrade_notice_dialog_is_modal_fits_and_writes_nothing(qtbot, app_dir, monkeypatch):
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **kw: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    win = ui_main.MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    QApplication.processEvents()
    before = _dump()
    seen = []

    def fake_exec(dialog):
        dialog.show()
        QApplication.processEvents()
        content = dialog.contentLabel
        button_top = dialog.yesButton.mapTo(dialog, QPoint(0, 0)).y()
        seen.append({
            "title": dialog.windowTitle(),
            "label": dialog.windowTitleLabel.text(),
            "text": "".join(content.text().split()),
            "modal": dialog.windowModality(),
            "cancel_hidden": dialog.cancelButton.isHidden(),
            "yes": dialog.yesButton.text(),
            "fits": dialog.rect().contains(content.geometry())
                    and content.height() >= content.heightForWidth(content.width())
                    and content.geometry().bottom() < button_top,
            "on_screen": dialog.screen().availableGeometry().contains(dialog.frameGeometry()),
        })
        dialog.hide()
        return 1

    monkeypatch.setattr(Dialog, "exec", fake_exec)
    win.show_upgrade_notice(17)
    assert seen == [{
        "title": ui_main.UPGRADE_NOTICE_TITLE,
        "label": ui_main.UPGRADE_NOTICE_TITLE,
        "text": "".join(ui_main.upgrade_notice_text().split()),
        "modal": Qt.ApplicationModal,
        "cancel_hidden": True,
        "yes": "확인",
        "fits": True,
        "on_screen": True,
    }]
    assert _dump() == before


def test_release_smoke_looks_for_the_same_notice_title():
    from tools import smoke_release as smoke
    assert smoke.UPGRADE_NOTICE_TITLE == ui_main.UPGRADE_NOTICE_TITLE
