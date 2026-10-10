"""네 번째 미니앱의 실제 선택창·드롭·수명과 합성 데이터 보존."""
import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

import database as db
import security
import ui_document_converter as module
import ui_main
import optional_mini_apps
import ui_settings
import hwp_conversion_runner
from hwp_conversion import ConversionEnvironment
from ui_main import MainCalendarWindow


@pytest.fixture(autouse=True)
def isolated(app_dir, qapp, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(module, "detect_environment", lambda: ConversionEnvironment(Path("hwp.exe"), Path("HwpxConverter.exe")))
    old = qapp.testAttribute(Qt.AA_DontUseNativeDialogs)
    qapp.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    yield
    qapp.setAttribute(Qt.AA_DontUseNativeDialogs, old)


def window(qtbot):
    win = module.DocumentConverterWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_real_file_picker_accept_cancel_and_drag_share_registration(qtbot, tmp_path):
    source = tmp_path / "선택 문서.hwp"
    source.write_bytes(b"synthetic")
    win = window(qtbot)
    qtbot.mouseClick(win.add_button, Qt.LeftButton)
    dialog = win._dialog
    qtbot.waitUntil(dialog.isVisible)
    dialog.selectFile(str(source))
    dialog.accept()
    qtbot.waitUntil(lambda: win._dialog is None)
    assert [entry.source for entry in win.entries] == [source]
    win.select_files()
    win._dialog.reject()
    assert len(win.entries) == 1
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    enter = QDragEnterEvent(win.rect().center(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(win, enter)
    drop = QDropEvent(QPointF(win.rect().center()), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(win, drop)
    assert enter.isAccepted() and drop.isAccepted() and len(win.entries) == 1


def test_real_folder_picker_and_hide_cancels_pending_selection(qtbot, tmp_path):
    win = window(qtbot)
    win.select_folder()
    dialog = win._dialog
    dialog.selectFile(str(tmp_path))
    dialog.accept()
    assert win.output_directory == tmp_path and not win.same_folder.isChecked()
    win.select_files()
    dialog = win._dialog
    win.hide()
    assert win._dialog is None and not dialog.isVisible()
    assert not win.entries


def test_missing_hwp_disables_conversion_with_explanation(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "detect_environment", lambda: ConversionEnvironment(None, Path("HwpxConverter.exe")))
    win = window(qtbot)
    source = tmp_path / "a.hwp"
    source.touch()
    win.add_files([source])
    assert not win.start_button.isEnabled()
    assert "한글" in win.environment_label.text()


def test_batch_failure_continues_and_retry_only_failed(qtbot, tmp_path, monkeypatch):
    win = window(qtbot)
    files = [tmp_path / name for name in ("a.hwp", "b.hwp")]
    for file in files:
        file.touch()
    win.add_files(files)
    calls = []
    monkeypatch.setattr(win.runner, "start", lambda source, directory: calls.append((source, directory)))
    win.start_conversion()
    assert calls[0][0] == files[0]
    win.runner.finished.emit(False, "", "합성 실패")
    qtbot.waitUntil(lambda: len(calls) == 2)
    win.runner.finished.emit(True, str(tmp_path / "b.hwpx"), "완료")
    assert [e.state for e in win.entries] == ["실패", "완료"]
    win.retry_failed()
    assert calls[-1][0] == files[0]
    win.runner.finished.emit(True, str(tmp_path / "a.hwpx"), "완료")
    assert [e.state for e in win.entries] == ["완료", "완료"]
    assert len(calls) == 3


@pytest.mark.parametrize("size", [(1000, 900), (480, 500), (420, 500)])
def test_controls_fit_small_screens(qtbot, size, tmp_path):
    win = window(qtbot)
    # 재시도·폴더 열기는 실패·결과가 있을 때만 보이므로(디자인 점검 21번) 그 상태를 만들어 함께 잰다.
    files = [tmp_path / name for name in ("a.hwp", "b.hwp")]
    for file in files:
        file.touch()
    win.add_files(files)
    win.entries[0].state = "실패"
    win.entries[1].state, win.entries[1].output = "완료", str(tmp_path / "b.hwpx")
    win._update_controls()
    win.fit_to_screen(QRect(0, 0, *size))
    QApplication.processEvents()
    assert win.width() <= size[0] and win.height() <= size[1]
    for control in (win.start_button, win.retry_button, win.open_button, win.remove_button, win.clear_button, win.file_list):
        assert control.isVisible()
        assert win.surface.rect().contains(QRect(control.mapTo(win.surface, control.rect().topLeft()), control.size()))
    root = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if root:
        assert win.grab().save(str(Path(root).parent / f"hwp-converter-{size[0]}x{size[1]}.png"))


@pytest.mark.parametrize("action", ["lock", "tray", "hide", "sidebar", "reset_prepare", "screen", "quit"])
def test_main_lifecycle_owns_fourth_app_and_preserves_data(qtbot, action, monkeypatch):
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", ())
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    main.show()
    qtbot.waitExposed(main)
    security.create_initial_salt()
    with db._connection() as conn:
        before = tuple(conn.iterdump())
    salt = security.SALT_FILE.read_bytes()
    main._toggle_mini_apps()
    pocket = main._mini_apps_popup
    assert pocket.count_label.text() == "4개"
    qtbot.mouseClick(pocket.document_card, Qt.LeftButton)
    win = main._document_converter
    assert win is not None and win.isVisible()
    win.close()
    main._open_document_converter()
    assert main._document_converter is win and win.isVisible()
    win.select_files()
    dialog = win._dialog
    if action == "lock":
        main._lock()
        assert not win.isEnabled()
        main._open_document_converter()
        assert not win.isVisible()
    elif action == "tray":
        main._minimize_to_tray()
    elif action == "hide":
        main.hide()
    elif action == "sidebar":
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
        main._apply_sidebar_visibility()
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    elif action == "reset_prepare":
        main._discard_data_widgets()
    elif action == "screen":
        main._on_screen_changed()
    else:
        assert main.prepare_for_quit()
        assert main._document_converter is None
    assert not dialog.isVisible()
    assert win._dialog is None
    if action != "screen":
        assert not win.isVisible()
    if action != "quit":
        with db._connection() as conn:
            assert tuple(conn.iterdump()) == before
    assert security.SALT_FILE.read_bytes() == salt


def test_schedule_save_failure_blocks_open(qtbot, monkeypatch):
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    main.show()
    monkeypatch.setattr(main, "_save_schedule_edit", lambda: False)
    main._open_document_converter()
    assert main._document_converter is None


@pytest.mark.parametrize("failure", [None, "backup", "database"])
def test_reset_discards_only_on_success_and_never_deletes_documents(qtbot, tmp_path, monkeypatch, failure):
    from shiboken6 import isValid
    source, output = tmp_path / "source.hwp", tmp_path / "source.hwpx"
    source.write_bytes(b"original")
    output.write_bytes(b"converted")
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    main.show()
    main._open_document_converter()
    win = main._document_converter
    win.add_files([source])
    win.entries[0].output = str(output)
    main._on_settings()
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    for kind in ("success", "error"):
        monkeypatch.setattr(ui_settings.InfoBar, kind, lambda **kw: None)
    if failure:
        def fail(*args):
            raise OSError("synthetic failure")
        monkeypatch.setattr(db, "backup_before_operation" if failure == "backup" else "reset_database", fail)
    main._settings_window._on_reset()
    if failure:
        assert main._document_converter is win and len(win.entries) == 1
    else:
        assert main._document_converter is None
        qtbot.waitUntil(lambda: not isValid(win))
    assert source.read_bytes() == b"original" and output.read_bytes() == b"converted"


@pytest.mark.parametrize("action", ["hide", "lock", "tray", "screen", "discard", "quit"])
def test_lifecycle_cancels_actual_worker_and_pending_queue(qtbot, tmp_path, monkeypatch, action):
    script = tmp_path / "waiting_worker.py"
    script.write_text("import time; time.sleep(60)", encoding="utf-8")
    monkeypatch.setattr(hwp_conversion_runner, "worker_command", lambda *args: (sys.executable, [str(script)]))
    files = [tmp_path / f"file{i}.hwp" for i in range(2)]
    for file in files:
        file.write_bytes(b"original")
    db.add_schedule("2026-10-03", "기존 일정", "#FFD166")
    db.save_memo("2026-10-03", "기존 메모")
    main = MainCalendarWindow()
    qtbot.addWidget(main)
    main.show()
    main._open_document_converter()
    win = main._document_converter
    with db._connection() as conn:
        snapshot = tuple(conn.iterdump())
    exported, salt = db.export_all_data(), security.SALT_FILE.read_bytes()
    win.add_files(files)
    win.start_conversion()
    qtbot.waitUntil(lambda: win.runner._process.processId() != 0)
    if action == "hide":
        win.hide()
    elif action == "lock":
        main._lock()
    elif action == "tray":
        main._minimize_to_tray()
    elif action == "screen":
        main._on_screen_changed()
    elif action == "discard":
        main._discard_document_converter()
    else:
        monkeypatch.setattr(main, "_save_schedule_edit", lambda: False)
        assert not main.prepare_for_quit() and win.busy
        monkeypatch.setattr(main, "_save_schedule_edit", lambda: True)
        assert main.prepare_for_quit()
    if action not in ("discard", "quit"):
        qtbot.waitUntil(lambda: not win.runner.busy)
        assert [entry.state for entry in win.entries] == ["취소", "취소"]
    assert not list(tmp_path.glob("*.hwpx"))
    assert not list(tmp_path.glob(".climatenote-hwp-*"))
    assert all(file.read_bytes() == b"original" for file in files)
    if action != "quit":
        with db._connection() as conn:
            assert tuple(conn.iterdump()) == snapshot
        assert db.export_all_data() == exported
    assert security.SALT_FILE.read_bytes() == salt
