"""네 번째 미니앱의 실제 선택창·드롭·수명과 합성 데이터 보존."""
import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

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
    assert win.output_directory == tmp_path and win.save_combo.currentText() == tmp_path.name
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
    assert "한글" in win.setting_description.text() and win.check_button.isVisible()


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
    files = [tmp_path / name for name in ("a.hwp", "b.hwp")]
    for file in files:
        file.touch()
    win.add_files(files)
    win.fit_to_screen(QRect(0, 0, *size))
    QApplication.processEvents()
    assert win.width() <= size[0] and win.height() <= size[1]
    for control in (win.start_button, win.settings_box, win.list_button, win.clear_button, win.file_header):
        assert control.isVisible()
        assert win.surface.rect().contains(QRect(control.mapTo(win.surface, control.rect().topLeft()), control.size()))
    win.entries[0].state, win.entries[0].detail = "실패", "합성 실패"
    win.entries[1].state, win.entries[1].output = "완료", str(tmp_path / "b.hwpx")
    win._batch_finished("")
    QApplication.processEvents()
    for control in (win.open_button, win.new_button, win.comparison, win.result_note):
        assert control.isVisible()
        assert win.surface.rect().contains(QRect(control.mapTo(win.surface, control.rect().topLeft()), control.size()))
    root = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if root:
        assert win.grab().save(str(Path(root).parent / f"hwp-converter-{size[0]}x{size[1]}.png"))


def make_image(path, color=Qt.blue):
    from PySide6.QtGui import QImage
    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(str(path))
    return path


def capture(win, name):
    QApplication.processEvents()
    root = os.environ.get("CLIMATENOTE_TEST_APPDATA")
    if root:
        assert win.grab().save(str(Path(root).parent / f"file-converter-{name}.png"))


def test_real_image_flow_previews_comparison_and_no_automatic_open(qtbot, tmp_path, monkeypatch):
    source = make_image(tmp_path / "현장사진.jpg")
    before = source.read_bytes()
    opened = []
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    win = window(qtbot)
    capture(win, "drop")
    win.add_files([source])
    qtbot.waitUntil(lambda: not win.probe.busy, timeout=15000)
    assert win.pages.currentWidget() is win.pick_page
    assert list(win.format_buttons) == ["jpg_small", "png", "pdf_bundle", "webp", "bmp", "ico"]
    assert win.target_id == "jpg_small" and not win.head_preview.image.isNull()
    assert win.settings_box.height() == 96 and "320 × 180" in win.file_info.text()
    capture(win, "pick")
    win.start_button.click()
    assert win.busy and not win.settings_box.isEnabled() and not win.acceptDrops()
    qtbot.waitUntil(lambda: not win.busy, timeout=20000)
    assert win.pages.currentWidget() is win.result_page and win.entries[0].state == "완료"
    output = Path(win.entries[0].output)
    assert output.is_file() and source.read_bytes() == before and not opened
    assert win.bars.source_bytes == len(before) and win.bars.output_bytes == output.stat().st_size
    assert win.entries[0].result_preview
    capture(win, "result")
    win.open_button.click()
    assert len(opened) == 1 and opened[0].toLocalFile() == str(tmp_path).replace("\\", "/")
    win.again_button.click()
    assert win.pages.currentWidget() is win.pick_page and len(win.entries) == 1
    win.clear_button.click()
    assert not win.entries and win.pages.currentWidget() is win.drop_page


@pytest.mark.parametrize("size", [(1000, 900), (480, 500), (420, 500)])
def test_all_image_settings_and_panels_fit(qtbot, tmp_path, size):
    win = window(qtbot)
    win.add_files([make_image(tmp_path / "image.jpg")])
    qtbot.waitUntil(lambda: not win.probe.busy, timeout=15000)
    win.fit_to_screen(QRect(0, 0, *size))
    for target in list(win.format_buttons):
        win.select_target(target)
        QApplication.processEvents()
        assert win.settings_box.height() == 96
        assert win.width() <= size[0] and win.height() <= size[1]
        for widget in [win.start_button, win.file_header, win.save_combo, *win.option_combos.values()]:
            assert win.surface.rect().contains(QRect(widget.mapTo(win.surface, widget.rect().topLeft()), widget.size()))
        capture(win, f"pick-{target}-{size[0]}x{size[1]}")
    win.clear_entries()
    win.open_map()
    QApplication.processEvents()
    assert win.content.rect().contains(win._overlay.geometry())
    assert win._overlay.rect().contains(win._overlay.panel.geometry())
    capture(win, f"map-{size[0]}x{size[1]}")


def test_map_focus_escape_backdrop_and_hide(qtbot):
    win = window(qtbot)
    win.activateWindow()
    qtbot.waitUntil(win.isActiveWindow)
    win.open_map()
    panel = win._overlay
    qtbot.waitUntil(lambda: panel.close_button.hasFocus())
    for _ in range(5):
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        assert panel.panel.isAncestorOf(QApplication.focusWidget())
    qtbot.keyClick(QApplication.focusWidget(), Qt.Key_Escape)
    assert win._overlay is None and win.isVisible()
    win.open_map()
    # QTest의 (0,0)은 기본값(위젯 가운데)이라 가림막 안의 실제 좌표를 쓴다.
    qtbot.mouseClick(win._overlay, Qt.LeftButton, pos=win._overlay.rect().topLeft() + module.QPointF(4, 4).toPoint())
    assert win._overlay is None and win.isVisible()
    win.open_map()
    win.hide()
    assert win._overlay is None


def test_mixed_kinds_list_removal_and_result_drop_replaces(qtbot, tmp_path):
    win = window(qtbot)
    a = make_image(tmp_path / "a.jpg")
    b = make_image(tmp_path / "b.png")
    text = tmp_path / "표.csv"
    text.write_bytes("한글".encode("utf-8"))
    win.add_files([a, text, b, a])
    assert len(win.entries) == 2 and "한 번에 한 종류" in win.status_label.text()
    qtbot.waitUntil(lambda: not win.probe.busy, timeout=15000)
    assert win.target_id == "jpg_small" and "jpg" in win.format_buttons
    win.open_list()
    assert win._overlay is not None
    win._remove_entry(win.entries[1])
    assert [e.source for e in win.entries] == [a]
    win.close_overlay()
    qtbot.waitUntil(lambda: not win.probe.busy, timeout=15000)
    win._batch_finished("")
    win.add_files([text])
    qtbot.waitUntil(lambda: not win.probe.busy, timeout=15000)
    assert [e.source for e in win.entries] == [text] and win.target_id == "cp949"
    assert win.other_section.isHidden()


@pytest.mark.parametrize("count", [0, 4, 8, 9, 12])
def test_other_formats_only_scroll_after_eight(qtbot, tmp_path, count):
    win = window(qtbot)
    source = tmp_path / "a.hwp"
    source.touch()
    win.add_files([source])
    win._render_other_formats(list(module.TARGETS)[:count])
    QApplication.processEvents()
    assert win.other_section.isHidden() == (count == 0)
    assert win.other_scroll.height() <= 70
    assert (win.other_scroll.verticalScrollBar().maximum() > 0) == (count > 8)


def test_combo_escape_closes_list_before_window(qtbot, tmp_path):
    win = window(qtbot)
    source = tmp_path / "a.hwp"
    source.touch()
    win.add_files([source])
    win.save_combo.setFocus()
    win.save_combo.showPopup()
    assert win.save_combo.view().isVisible()
    qtbot.keyClick(win.save_combo.view(), Qt.Key_Escape)
    assert not win.save_combo.view().isVisible() and win.isVisible()
    qtbot.keyClick(win.save_combo, Qt.Key_Escape)
    assert not win.isVisible()


@pytest.mark.parametrize("action", ["hide", "disable", "shutdown"])
def test_new_worker_cancelled_by_window_lifecycle(qtbot, tmp_path, monkeypatch, action):
    import file_conversion_runner
    win = window(qtbot)
    source = make_image(tmp_path / "original.jpg")
    original = source.read_bytes()
    win.add_files([source])
    qtbot.waitUntil(lambda: not win.probe.busy, timeout=15000)
    script = tmp_path / "waiting.py"
    script.write_text("import time; time.sleep(60)", encoding="utf-8")
    monkeypatch.setattr(file_conversion_runner, "worker_command", lambda *args: (sys.executable, [str(script)]))
    win.start_conversion()
    qtbot.waitUntil(lambda: win.file_runner._process.processId() != 0)
    assert not win.file_header.isEnabled() and not win.start_button.isVisible()
    win.add_files([make_image(tmp_path / "ignored.png")])
    assert len(win.entries) == 1
    if action == "disable":
        win.setEnabled(False)
    else:
        getattr(win, action)()
    qtbot.waitUntil(lambda: not win.file_runner.busy)
    assert not list(tmp_path.glob(".climatenote-conv-*"))
    assert not list(tmp_path.glob("*작게*"))
    assert source.read_bytes() == original


def test_result_page_counts_pdf_images_and_keeps_cleanup_warning(qtbot, tmp_path):
    win = window(qtbot)
    source = tmp_path / "source.hwp"
    source.touch()
    win.add_files([source])
    entry = win.entries[0]
    entry.state, entry.output, entry.output_count = "완료", str(tmp_path / "pages"), 3
    win.target_id = "pdf_png"
    win._batch_finished("")
    assert win.result_title.text() == "PNG 3개를 만들었어요"
    entry.state, entry.output = "취소", ""
    win._batch_finished("임시 파일 정리를 완료하지 못했습니다")
    assert "정리" in win.result_status.text() and "취소 1개" in win.result_status.text()


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
