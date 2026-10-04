"""최초 설치 분기와 선택값의 실제 DB/화면/백업 왕복."""
import sqlite3
import zipfile
from contextlib import closing

import pytest
from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog

import database as db
import security
from ui_first_run import FirstRunSizeDialog


@pytest.fixture
def fresh_dir(app_dir, monkeypatch):
    # app_dir의 UI 폐기 가드는 유지하되 별도 빈 합성 데이터 경로를 사용한다.
    folder = app_dir.parent / "fresh" / "MyDesktopCalendar"
    folder.mkdir(parents=True)
    monkeypatch.setattr(db, "APP_DIR", folder)
    monkeypatch.setattr(db, "DB_FILE", folder / "calendar.db")
    monkeypatch.setattr(security, "APP_DIR", folder)
    monkeypatch.setattr(security, "SALT_FILE", folder / ".salt")
    return folder


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_first_choice_persists_in_database_backup_and_main(fresh_dir, scale, qtbot):
    import main
    from ui_main import MainCalendarWindow
    assert main._initialize_database(lambda: scale)
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == scale
    bundle = next((fresh_dir / "backups").glob("calendar_auto_*.cnbak"))
    with zipfile.ZipFile(bundle) as archive:
        with open(fresh_dir / "snapshot.db", "wb") as stream:
            stream.write(archive.read("calendar.db"))
    with closing(sqlite3.connect(fresh_dir / "snapshot.db")) as connection:
        assert connection.execute("SELECT value FROM app_settings WHERE key='calendar_scale'").fetchone()[0] == scale
    for _ in range(2):
        assert main._initialize_database(lambda: pytest.fail("기존 사용자는 선택창 생략"))
        window = MainCalendarWindow()
        assert window._current_calendar_scale() == scale
        assert window._sticky_in_panel_mode is (scale == "large")
        if scale == "compact":
            assert window.maximumWidth() == 380
            assert window.sidebar.isHidden()
        else:
            assert window.maximumWidth() > 460
            assert not window.sidebar.isHidden()
            assert window.schedule_panel.parent() is window._expanded_row
        window.deleteLater()
        qtbot.wait(10)


def test_cancel_repeats_without_database_salt_or_backup(fresh_dir):
    import main
    for _ in range(2):
        assert main._initialize_database(lambda: None) is False
        assert db.inspect_startup_data_health().code == "fresh"
        assert not list(fresh_dir.iterdir())


@pytest.mark.parametrize("value", ["medium", "", "invalid", None])
def test_existing_database_never_prompts_or_overwrites(app_dir, value):
    import main
    if value is None:
        with db._connection() as connection:
            connection.execute("DELETE FROM app_settings WHERE key=?", (db.SETTING_CALENDAR_SCALE,))
            connection.commit()
    else:
        db.save_setting(db.SETTING_CALENDAR_SCALE, value)
    main._initialize_database(lambda: pytest.fail("기존 DB에 설정창 표시"))
    assert db.get_setting(db.SETTING_CALENDAR_SCALE, "missing") == (value if value is not None else "missing")
    db.migrate(initial_calendar_scale="large")
    assert db.get_setting(db.SETTING_CALENDAR_SCALE, "missing") == (value if value is not None else "missing")


@pytest.mark.parametrize("residue", [".salt", "calendar.db-wal", "calendar.db-shm", "backups/calendar_old.db", "calendar.db"])
def test_incomplete_or_corrupt_dataset_does_not_prompt(fresh_dir, residue):
    import main
    path = fresh_dir / residue
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"preserve")
    with pytest.raises(db.DataHealthError):
        main._initialize_database(lambda: pytest.fail("손상 데이터에 설정창 표시"))
    assert path.read_bytes() == b"preserve"


def test_invalid_initial_size_does_not_create_database(fresh_dir):
    import main
    with pytest.raises(ValueError):
        main._initialize_database(lambda: "huge")
    with pytest.raises(ValueError):
        db.migrate(initial_calendar_scale="huge")
    assert not list(fresh_dir.iterdir())


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_initial_scale_export_import_round_trip(fresh_dir, scale):
    import main
    assert main._initialize_database(lambda: scale)
    db.add_schedule("2026-10-04", "크기 왕복 검사")
    exported = db.export_all_data()
    salt = security.SALT_FILE.read_bytes()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact" if scale != "compact" else "large")
    db.import_all_data(exported)
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == scale
    assert security.SALT_FILE.read_bytes() == salt


def test_factory_reset_keeps_existing_startup_path(app_dir):
    import main
    db.reset_database()
    security.reset_salt()
    assert main._initialize_database(lambda: pytest.fail("Factory Reset 후 최초 설정 표시"))
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "compact"


def test_initial_database_write_failure_propagates(fresh_dir, monkeypatch):
    import main
    def fail(**kwargs):
        raise sqlite3.OperationalError("injected initial write failure")
    monkeypatch.setattr(db, "migrate", fail)
    with pytest.raises(sqlite3.OperationalError):
        main._initialize_database(lambda: "medium")
    assert not db.DB_FILE.exists()


def test_dataset_appearing_during_setup_is_not_overwritten(fresh_dir):
    import main
    def choose():
        db.DB_FILE.write_bytes(b"external-data")
        return "large"
    with pytest.raises(db.DataHealthError):
        main._initialize_database(choose)
    assert db.DB_FILE.read_bytes() == b"external-data"


def test_dialog_keyboard_selection_and_accept(qtbot):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    dialog.cards[0].setFocus()
    qtbot.waitUntil(lambda: dialog.cards[0].hasFocus())
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Right)
    assert dialog.selected_scale == "medium"
    assert dialog.cards[1].hasFocus()
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Right)
    assert dialog.selected_scale == "large"
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Space)
    assert dialog.cards[2].isChecked()
    assert sum(card.isChecked() for card in dialog.cards) == 1
    qtbot.keyClick(dialog.focusWidget(), Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted


@pytest.mark.parametrize("accept", [True, False])
def test_startup_dialog_adapter_returns_choice_or_cancellation(qapp, monkeypatch, accept):
    import main
    import ui_first_run
    dialog = FirstRunSizeDialog()
    dialog._select("medium")
    monkeypatch.setattr(ui_first_run, "FirstRunSizeDialog", lambda: dialog)
    QTimer.singleShot(0, dialog.accept if accept else dialog.reject)
    assert main._choose_initial_calendar_scale() == ("medium" if accept else None)


@pytest.mark.parametrize("close", ["escape", "title", "button", "window", "title_enter", "button_enter"])
def test_dialog_cancel_returns_rejected(qtbot, close):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.mouseClick(dialog.cards[1], Qt.LeftButton)
    if close == "escape":
        qtbot.keyClick(dialog, Qt.Key_Escape)
    elif close == "window":
        dialog.close()
    elif close.endswith("_enter"):
        button = dialog.close_button if close == "title_enter" else dialog.cancel_button
        dialog.activateWindow()
        button.setFocus()
        qtbot.waitUntil(button.hasFocus)
        qtbot.keyClick(dialog.focusWidget(), Qt.Key_Return)
    else:
        qtbot.mouseClick(dialog.close_button if close == "title" else dialog.cancel_button, Qt.LeftButton)
    assert dialog.result() == QDialog.Rejected
    assert not dialog.isVisible()


@pytest.mark.parametrize("width,height", [(1000, 900), (700, 550), (540, 500), (400, 600), (800, 400)])
def test_dialog_controls_fit_small_work_area(qtbot, width, height):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)
    # 아래 QRect는 합성 화면이다. 실제 다중 모니터 이동 통지는 별도 검사한다.
    dialog.windowHandle().screenChanged.disconnect(dialog._screen_changed)
    area = QRect(20, 30, width, height)
    dialog.fit_to_available_geometry(area)
    qtbot.wait(20)
    assert area.contains(dialog.geometry())
    controls = [*dialog.cards, dialog.heading, dialog.subtitle, dialog.description,
                dialog.hint, dialog.start_button, dialog.cancel_button, dialog.close_button]
    for control in controls:
        assert dialog.rect().contains(control.geometry()), (control, control.geometry(), dialog.rect())
    for card in dialog.cards:
        assert card.width() >= 175 or card.height() < 130
        assert not card.geometry().intersects(dialog.description.geometry())
    assert not dialog.hint.geometry().intersects(dialog.start_button.geometry())


def test_work_area_round_trip_reflows_without_old_minimum(qtbot):
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)
    dialog.windowHandle().screenChanged.disconnect(dialog._screen_changed)
    for width, height in [(1000, 900), (400, 600), (800, 400), (320, 600), (1000, 900)]:
        area = QRect(0, 0, width, height)
        dialog.fit_to_available_geometry(area)
        qtbot.wait(20)
        assert area.contains(dialog.geometry()), (area, dialog.geometry())


def test_removed_screen_does_not_leave_invalid_signal_connection(qtbot, qapp):
    from shiboken6 import delete
    class Screen(QObject):
        availableGeometryChanged = Signal(QRect)
        def availableGeometry(self):
            return QRect(0, 0, 540, 500)
    dialog = FirstRunSizeDialog()
    qtbot.addWidget(dialog)
    screen = Screen()
    dialog._screen_changed(screen)
    delete(screen)
    dialog._screen_changed(qapp.primaryScreen())
    assert qapp.primaryScreen().availableGeometry().contains(dialog.geometry())


def test_release_setup_confirmation_refuses_unowned_window(monkeypatch):
    from tools import smoke_release
    monkeypatch.setattr(smoke_release, "windows_in_job", lambda job: [])
    with pytest.raises(ValueError, match="소유한"):
        smoke_release.accept_first_run_setup(object(), {"hwnd": 123, "pid": 456})
