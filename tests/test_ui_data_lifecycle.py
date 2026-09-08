"""가져오기·초기화·잠금 전후의 실제 DB/편집기 수명 회귀 검사."""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import database as db
import security
import ui_main
import ui_settings
from show_desktop_guard import ShowDesktopKeeper
from ui_main import MainCalendarWindow
from ui_sticky import StickyNoteWindow


@pytest.fixture(autouse=True)
def quiet_native_layer(app_dir, monkeypatch):
    # 이 파일은 데이터/Qt 객체 수명을 검사한다. native 레이어 검사는 별도다.
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_apply_topmost", lambda *a, **k: None)
    monkeypatch.setattr(ShowDesktopKeeper, "_pin_to_desktop_layer", lambda self: False)
    monkeypatch.setattr(MainCalendarWindow, "_warn_keep_desktop_unavailable_once", lambda self: None)
    for kind in ("info", "success", "warning", "error"):
        monkeypatch.setattr(ui_main.InfoBar, kind, lambda *a, **k: None)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")


def _main(qtbot, scale="compact", focus=False):
    note_id = db.create_sticky_note("memo")
    db.update_sticky_note(note_id, content="원래 저장한 메모")
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    if focus:
        db.create_focus_widget("기존 집중 목표", "25/5")
        db.create_dday_widget("기존 D-Day", "2026-12-31")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    QApplication.processEvents()
    return win, note_id


def _import_file(win, app_dir, monkeypatch, **sections):
    win._on_settings()
    settings = win._settings_window
    settings.import_pin.setText("1234")
    payload = json.dumps({"format_version": 2, **sections}).encode("utf-8")
    path = app_dir / "synthetic.enc"
    with open(path, "wb") as stream:
        stream.write(security.encrypt_with_pin(payload, "1234"))
    monkeypatch.setattr(ui_settings.QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    return settings


@pytest.mark.parametrize("scale", ["compact", "large"])
def test_import_reuses_editors_and_running_timer(qtbot, app_dir, monkeypatch, scale):
    win, note_id = _main(qtbot, scale, focus=True)
    original = win._sticky_windows[note_id]
    focus = next(iter(win._focus_windows.values()))
    dday = next(iter(win._dday_windows.values()))
    focus._start_session()
    editor = win._sticky_side_panel._cards[0] if scale == "large" else original
    settings = _import_file(win, app_dir, monkeypatch,
                            schedules=[{"date": "2026-09-08", "content": "가져온 일정"}])
    editor.text_edit.setPlainText("가져오기 직전 최신 편집")
    settings._on_import()
    assert db.get_schedules("2026-09-08")
    assert win._sticky_windows[note_id] is original
    assert next(iter(win._focus_windows.values())) is focus
    assert next(iter(win._dday_windows.values())) is dday
    assert focus.timer_model.status == "running"
    copies = [w for w in QApplication.topLevelWidgets()
              if isinstance(w, StickyNoteWindow) and w.note_id == note_id]
    assert copies == [original]
    active = win._sticky_side_panel._cards[0] if scale == "large" else original
    assert active.text_edit.toPlainText() == "가져오기 직전 최신 편집"
    active.text_edit.setPlainText("가져온 뒤 저장한 편집")
    assert active.save()
    assert win.prepare_for_quit()
    assert "가져온 뒤 저장한 편집" in db.get_open_sticky_notes()[0]["content"]


def test_import_refreshes_large_panel_without_losing_existing_edit(qtbot, app_dir, monkeypatch):
    win, note_id = _main(qtbot, "large")
    note = {"type": "memo", "content": "가져온 메모", "x_pos": 200, "y_pos": 200,
            "width": 220, "height": 210, "is_open": 1, "is_pinned": 0}
    settings = _import_file(win, app_dir, monkeypatch, sticky_notes=[note])
    win._sticky_side_panel._cards[0].text_edit.setPlainText("기존 패널의 최신 편집")
    settings._on_import()
    cards = {card.note_id: card for card in win._sticky_side_panel._cards}
    assert set(cards) == {n["id"] for n in db.get_open_sticky_notes()}
    assert len(cards) == 2
    assert cards[note_id].text_edit.toPlainText() == "기존 패널의 최신 편집"


@pytest.mark.parametrize("operation", ["import", "reset"])
def test_data_change_stops_before_backup_when_latest_save_fails(qtbot, app_dir, monkeypatch, operation):
    win, note_id = _main(qtbot)
    settings = _import_file(win, app_dir, monkeypatch,
                            schedules=[{"date": "2026-09-08", "content": "추가 금지"}])
    win._sticky_windows[note_id].text_edit.setPlainText("미저장 최신 원본")
    original_update = db.update_sticky_note

    def fail_content(target, **kwargs):
        if "content" in kwargs:
            raise sqlite3.OperationalError("synthetic write failure")
        return original_update(target, **kwargs)

    monkeypatch.setattr(db, "update_sticky_note", fail_content)
    calls = []
    monkeypatch.setattr(db, "backup_before_operation", lambda op: calls.append(op))
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    getattr(settings, f"_on_{operation}")()
    assert calls == []
    assert db.get_schedules("2026-09-08") == []
    assert win._sticky_windows[note_id].text_edit.toPlainText() == "미저장 최신 원본"
    assert win._sticky_windows[note_id]._save_timer.isActive()


@pytest.mark.parametrize("scale", ["compact", "large"])
def test_reset_disposes_old_editors_and_timers_before_id_reuse(qtbot, app_dir, monkeypatch, scale):
    win, note_id = _main(qtbot, scale, focus=True)
    win._on_settings()
    settings = win._settings_window
    old_windows = (list(win._sticky_windows.values()) + list(win._focus_windows.values())
                   + list(win._dday_windows.values()))
    old_panels = [p for p in (win._sticky_side_panel, win._focus_side_panel,
                             win._dday_side_panel) if p is not None]
    editor = win._sticky_side_panel._cards[0] if scale == "large" else old_windows[0]
    editor.text_edit.setPlainText("초기화 직전 보호할 최신 원본")
    old_focus = next(iter(win._focus_windows.values()))
    now = datetime(2026, 9, 8, 12, 0)
    old_focus.timer_model._now = lambda: now
    old_focus._start_session()
    monkeypatch.setattr(old_focus, "_ask_break", lambda: False)
    backup_contents = []
    original_backup = db.backup_before_operation

    def record_backup(operation):
        backup_contents.append(db.get_open_sticky_notes()[0]["content"])
        return original_backup(operation)

    monkeypatch.setattr(db, "backup_before_operation", record_backup)
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    settings._on_reset()
    assert "초기화 직전 보호할 최신 원본" in backup_contents[0]
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert all(not isValid(w) for w in old_windows + old_panels)
    assert not any(w in win._show_desktop_keeper._guarded for w in old_windows)
    win._on_new_sticky_note()
    new = next(iter(win._sticky_windows.values()))
    assert new.note_id == note_id
    new.text_edit.setPlainText("초기화 후 새 메모")
    assert new.save()
    now += timedelta(minutes=26)
    qtbot.wait(2300)
    assert "초기화 후 새 메모" in db.get_open_sticky_notes()[0]["content"]
    assert db.get_focus_sessions() == []
    assert list((app_dir / "backups").glob("calendar_before_reset_*.cnbak"))


def test_reset_backup_failure_keeps_live_widgets(qtbot, app_dir, monkeypatch):
    win, note_id = _main(qtbot, focus=True)
    win._on_settings()
    old = win._sticky_windows[note_id]
    focus = next(iter(win._focus_windows.values()))
    focus._start_session()
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)

    def fail_backup(operation):
        raise OSError("synthetic backup failure")

    monkeypatch.setattr(db, "backup_before_operation", fail_backup)
    win._settings_window._on_reset()
    assert win._sticky_windows[note_id] is old
    assert focus.timer_model.status == "running"
    assert isValid(old) and focus._tick_timer.isActive()
    assert db.get_open_sticky_notes()[0]["id"] == note_id


@pytest.mark.parametrize("scale", ["compact", "large"])
def test_lock_survives_tray_and_restores_correct_mode(qtbot, scale):
    win, note_id = _main(qtbot, scale, focus=True)
    win._lock()
    win.toggle_visibility()
    win.toggle_visibility()
    assert win._is_locked and win.lock_overlay.isVisible()
    assert not any(w.isVisible() for w in win._sticky_windows.values())
    assert not any(w.isVisible() for w in win._focus_windows.values())
    assert not any(w.isVisible() for w in win._dday_windows.values())
    win._unlock()
    assert win._sticky_windows[note_id].isVisible() == (scale != "large")
    assert next(iter(win._focus_windows.values())).isVisible() == (scale != "large")
    assert next(iter(win._dday_windows.values())).isVisible() == (scale != "large")


@pytest.mark.parametrize("kind", ["search", "settings", "trash"])
def test_lock_hides_auxiliary_windows_and_blocks_reopen(qtbot, kind):
    win, _ = _main(qtbot)
    opener = getattr(win, "_on_open_trash" if kind == "trash" else f"_on_{kind}")
    opener()
    auxiliary = getattr(win, f"_{kind}_window")
    assert auxiliary.isVisible()
    win._lock()
    assert not auxiliary.isVisible()
    assert not auxiliary.isEnabled()
    opener()
    assert getattr(win, f"_{kind}_window") is auxiliary
    assert not auxiliary.isVisible()
    win._unlock()
    opener()
    reopened = getattr(win, f"_{kind}_window")
    assert reopened.isEnabled() and reopened.isVisible()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(auxiliary)


def test_lock_blocks_already_queued_focus_show(qtbot):
    win, _ = _main(qtbot)
    db.create_focus_widget("예약된 표시", "25/5")
    win._load_open_focus_widgets()
    win._lock()
    QApplication.processEvents()
    assert not next(iter(win._focus_windows.values())).isVisible()


def test_reopened_auxiliary_discards_old_window_and_locks_new_one(qtbot):
    win, _ = _main(qtbot)
    win._on_search()
    original = win._search_window
    original.close()
    win._on_search()
    assert win._search_window is not original
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(original)
    win._lock()
    assert not win._search_window.isVisible()


def test_reset_failure_after_start_never_reuses_old_editors(qtbot, monkeypatch):
    win, note_id = _main(qtbot)
    win._on_settings()
    original = win._sticky_windows[note_id]
    original.text_edit.setPlainText("실패해도 보존할 내용")
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)

    def fail_reset():
        raise OSError("synthetic DB replacement failure")

    monkeypatch.setattr(db, "reset_database", fail_reset)
    win._settings_window._on_reset()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(original)
    restored = win._sticky_windows[note_id]
    assert restored.text_edit.toPlainText() == "실패해도 보존할 내용"
    assert "실패해도 보존할 내용" in db.get_open_sticky_notes()[0]["content"]


def test_lock_cancels_active_dialog(qtbot):
    from PySide6.QtWidgets import QDialog
    win, _ = _main(qtbot)
    dialog = QDialog(win)
    dialog.setModal(True)
    dialog.show()
    assert QApplication.activeModalWidget() is dialog
    win._lock()
    assert not dialog.isVisible()
    assert dialog.result() == QDialog.Rejected


def test_locked_focus_completion_saves_without_prompt(qtbot, monkeypatch):
    import ui_focus
    win, _ = _main(qtbot, focus=True)
    focus = next(iter(win._focus_windows.values()))
    now = datetime(2026, 9, 8, 12, 0)
    focus.timer_model._now = lambda: now
    focus._start_session()
    win._lock()
    prompts = []
    monkeypatch.setattr(ui_focus.FocusBreakPromptDialog, "exec", lambda self: prompts.append(True))
    now += timedelta(minutes=26)
    focus._on_tick()
    assert prompts == []
    assert len(db.get_focus_sessions()) == 1
    assert focus.timer_model.status == "ended"
    win._unlock()
    assert focus.isVisible()


def test_queued_show_cannot_restore_widget_discarded_by_reset(qtbot):
    win, _ = _main(qtbot)
    db.create_focus_widget("폐기될 예약 표시", "25/5")
    win._load_open_focus_widgets()
    old = next(iter(win._focus_windows.values()))
    win._discard_data_widgets()
    QApplication.processEvents()
    assert not isValid(old) or not old.isVisible()
