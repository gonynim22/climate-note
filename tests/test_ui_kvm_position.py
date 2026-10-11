"""KVM placement regressions, using only synthetic app_dir data and screens."""

import json
import pytest
from PySide6.QtCore import QPoint, QRect

import database as db
import security
import ui_main
import ui_settings
from screen_placement import decode_screen, describe_screen, match_screen
from ui_main import MainCalendarWindow


class _Screen:
    def __init__(self, name, geometry):
        self.label = name
        self.rect = geometry
        self.serial = name

    def name(self):
        return self.label

    def serialNumber(self):
        return self.serial

    def manufacturer(self):
        return "Synthetic"

    def model(self):
        return "Monitor"

    def geometry(self):
        return self.rect

    def availableGeometry(self):
        return self.rect

    def physicalDotsPerInch(self):
        return 96


class _Topology:
    def __init__(self, application, left, right):
        self.application = application
        self.left = left
        self.right = right
        self.online = [left, right]

    def __getattr__(self, name):
        return getattr(self.application, name)

    def screens(self):
        return self.online

    def primaryScreen(self):
        return self.left

    def screenAt(self, point):
        return next((s for s in self.online if s.availableGeometry().contains(point)), None)


def _placement(win):
    return (win.x(), win.y(), win.width(), win.height())


def _setup(scale, mode, qtbot, monkeypatch):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._periodic_save_timer.stop()
    win._screen_change_timer.stop()
    topology = _Topology(
        ui_main.QApplication,
        _Screen("left-landscape", QRect(0, 0, 1920, 1080)),
        _Screen("right-portrait", QRect(1920, 0, 1080, 1920)),
    )
    monkeypatch.setattr(ui_main, "QApplication", topology)
    db.save_setting(db.SETTING_TARGET_SCREEN, "1")
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, mode)
    db.save_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
    # A legal position on the right portrait screen for every size, including
    # 20px left/top margins in large mode. No app setting is read from real data.
    db.save_setting(db.SETTING_CALENDAR_X, "1940")
    db.save_setting(db.SETTING_CALENDAR_Y, "20")
    win._apply_calendar_scale()
    return win, topology


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
@pytest.mark.parametrize("movement_enabled", [True, False], ids=["editing", "fixed"])
def test_free_placement_survives_disconnect_and_reconnect(
        app_dir, qtbot, monkeypatch, scale, movement_enabled):
    win, topology = _setup(scale, "free", qtbot, monkeypatch)
    win._calendar_move_editing = movement_enabled
    before = _placement(win)
    original_saved = win._saved_calendar_xy()

    topology.online = [topology.left]
    win._on_screen_changed()
    temporary = _placement(win)
    temporary_saved = win._saved_calendar_xy()
    topology.online = [topology.left, topology.right]
    win._on_screen_changed()
    after = _placement(win)

    assert (after, win._saved_calendar_xy()) == (before, original_saved), (
        f"{scale}: before={before}, temporary={temporary}, after={after}; "
        f"saved {original_saved} -> {temporary_saved} -> {win._saved_calendar_xy()}"
    )


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
def test_corner_placement_survives_disconnect_and_reconnect(
        app_dir, qtbot, monkeypatch, scale):
    win, topology = _setup(scale, "corner", qtbot, monkeypatch)
    before = _placement(win)
    topology.online = [topology.left]
    win._on_screen_changed()
    topology.online = [topology.left, topology.right]
    win._on_screen_changed()
    assert _placement(win) == before


@pytest.mark.parametrize("scale", ["compact", "medium", "large"])
@pytest.mark.parametrize("mode", ["free", "corner"])
def test_target_monitor_survives_screen_list_reordering(
        app_dir, qtbot, monkeypatch, scale, mode):
    win, topology = _setup(scale, mode, qtbot, monkeypatch)
    before = _placement(win)
    topology.online = [topology.right, topology.left]
    win._on_screen_changed()
    assert win._get_target_screen() is topology.right, (
        f"{scale}/{mode}: target changed from right-portrait to "
        f"{win._get_target_screen().label}; before={before}, after={_placement(win)}"
    )
    assert _placement(win) == before


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_recreated_screens_and_restart_restore_saved_device(app_dir, qtbot, monkeypatch, scale):
    win, topology = _setup(scale, "free", qtbot, monkeypatch)
    win._finish_calendar_drag(QPoint(1940, 20))
    before = _placement(win)
    saved = db.get_setting(db.SETTING_CALENDAR_SCREEN)
    topology.online = [topology.left]
    win._on_screen_changed()
    replacement = _Screen("new-connector-name", QRect(1920, 0, 1080, 1920))
    replacement.serial = topology.right.serial
    topology.online = [replacement, topology.left]
    win._on_screen_changed()
    assert win._get_target_screen() is replacement
    assert _placement(win) == before
    reopened = MainCalendarWindow()
    qtbot.addWidget(reopened)
    assert reopened._get_target_screen() is replacement
    assert _placement(reopened) == before
    assert db.get_setting(db.SETTING_CALENDAR_SCREEN) == saved


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_origin_and_temporary_logical_size_changes_preserve_preference(app_dir, qtbot, monkeypatch, scale):
    win, topology = _setup(scale, "free", qtbot, monkeypatch)
    original = _placement(win)
    with db._connection() as conn:
        before = list(conn.iterdump())
    for rect in (QRect(-1080, -200, 1080, 1920), QRect(0, 0, 864, 1536),
                 QRect(1920, 0, 1080, 1920)):
        topology.right.rect = rect
        win._on_screen_changed()
        assert (win.x(), win.y()) == (rect.x() + 20, rect.y() + 20)
    assert _placement(win) == original
    with db._connection() as conn:
        assert list(conn.iterdump()) == before


@pytest.mark.parametrize("record", ["", "null", "[]", '{"version":2}', "broken"])
def test_missing_or_invalid_preference_keeps_legacy_setting(app_dir, qtbot, monkeypatch, record):
    win, topology = _setup("large", "free", qtbot, monkeypatch)
    db.save_setting(db.SETTING_CALENDAR_SCREEN, record)
    win._on_screen_changed()
    assert win._get_target_screen() is topology.right
    assert db.get_setting(db.SETTING_CALENDAR_SCREEN) == record


def test_missing_preferred_device_is_not_replaced_by_same_index(app_dir, qtbot, monkeypatch):
    win, topology = _setup("large", "free", qtbot, monkeypatch)
    win._finish_calendar_drag(QPoint(1940, 20))
    before = _placement(win)
    replacement = _Screen(topology.right.label, topology.right.rect)
    replacement.serial = "different-device"
    topology.online = [topology.left, replacement]
    win._on_screen_changed()
    assert win._get_target_screen() is topology.left
    topology.online = [topology.left, topology.right]
    win._on_screen_changed()
    assert _placement(win) == before


def test_ambiguous_or_empty_identity_does_not_guess():
    first = _Screen("connector", QRect(0, 0, 1000, 1000))
    second = _Screen("connector", QRect(1000, 0, 1000, 1000))
    assert match_screen(describe_screen(first), [first, second]) is None
    first.serial = second.serial = ""
    assert match_screen(describe_screen(first), [first, second]) is None
    second.label = "other-connector"
    assert match_screen(describe_screen(first), [second, first]) is first
    first.label = ""
    assert match_screen(describe_screen(first), [first]) is None


def test_monitor_selection_after_reorder_uses_selected_device(app_dir, qtbot, monkeypatch):
    win, topology = _setup("large", "free", qtbot, monkeypatch)
    monkeypatch.setattr(ui_settings, "QApplication", topology)
    settings = ui_settings.SettingsWindow(on_monitor_selected=win._position_to_corner)
    qtbot.addWidget(settings)
    topology.online = [topology.right, topology.left]
    settings._on_monitor_changed(0)  # The displayed first item is the left screen.
    assert win._get_target_screen() is topology.left
    assert (win.width(), win.height()) == (1880, 1040)
    assert db.get_setting(db.SETTING_TARGET_SCREEN) == "1"
    settings._on_monitor_changed(1)
    assert win._get_target_screen() is topology.right
    assert (win.width(), win.height()) == (1040, 1880)


def test_missing_monitor_selection_and_failed_save_preserve_existing_placement(app_dir, qtbot, monkeypatch):
    win, topology = _setup("large", "free", qtbot, monkeypatch)
    monkeypatch.setattr(ui_settings, "QApplication", topology)
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kwargs: None)
    monkeypatch.setattr(ui_settings.InfoBar, "warning", lambda **kwargs: None)
    settings = ui_settings.SettingsWindow(on_monitor_selected=win._position_to_corner)
    qtbot.addWidget(settings)
    original = _placement(win)
    with db._connection() as conn:
        before = dict(conn.execute("SELECT key,value FROM app_settings"))
        conn.execute("""CREATE TRIGGER reject_screen BEFORE INSERT ON app_settings
                     WHEN NEW.key='calendar_screen'
                     BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        conn.commit()
    settings.monitor_combo.setCurrentIndex(0)
    assert settings.monitor_combo.currentIndex() == 1
    assert _placement(win) == original
    topology.online = [topology.right]
    settings.monitor_combo.setCurrentIndex(0)
    assert settings.monitor_combo.currentIndex() == 1
    with db._connection() as conn:
        assert dict(conn.execute("SELECT key,value FROM app_settings")) == before


def test_reset_discards_runtime_screen_preference(app_dir, qtbot, monkeypatch):
    win, topology = _setup("compact", "corner", qtbot, monkeypatch)
    topology.online = [topology.right, topology.left]
    # Explicit settings happen to equal the reset defaults, but the remembered
    # device is different; reset must not retain that device merely by cache key.
    db.save_setting(db.SETTING_TARGET_SCREEN, "0")
    assert win._get_target_screen() is topology.right
    db.reset_database()
    topology.online = [topology.left, topology.right]
    win._on_factory_reset()
    assert win._get_target_screen() is topology.left


@pytest.mark.parametrize("invalid", [
    {"version": True}, {"origin": [True, 0]}, {"origin": [0, "1"]},
    {"origin": [0, 2**31]}, {"serial": None},
])
def test_malformed_screen_record_is_ignored(invalid):
    record = describe_screen(_Screen("screen", QRect(0, 0, 100, 100)))
    record.update(invalid)
    assert decode_screen(json.dumps(record)) is None


def test_placement_save_rolls_back_as_a_group(app_dir, qtbot, monkeypatch):
    win, topology = _setup("large", "free", qtbot, monkeypatch)
    with db._connection() as conn:
        before = dict(conn.execute("SELECT key,value FROM app_settings"))
        conn.execute("""CREATE TRIGGER reject_screen BEFORE INSERT ON app_settings
                     WHEN NEW.key='calendar_screen'
                     BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        conn.commit()
    win.move(1950, 30)
    win._finish_calendar_drag(QPoint(1950, 30))
    with db._connection() as conn:
        assert dict(conn.execute("SELECT key,value FROM app_settings")) == before


def test_preference_roundtrip_and_automatic_recovery_preserve_data(app_dir, qtbot, monkeypatch):
    db.add_schedule("2026-09-22", "🎯 보존할 일정")
    db.save_memo("2026-09-22", "원본 메모")
    win, topology = _setup("large", "free", qtbot, monkeypatch)
    win._finish_calendar_drag(QPoint(1940, 20))
    salt = security.SALT_FILE.read_bytes()
    with db._connection() as conn:
        before = list(conn.iterdump())
    exported = db.export_all_data()
    for online in ([topology.left], [topology.right, topology.left]):
        topology.online = online
        win._on_screen_changed()
    with db._connection() as conn:
        assert list(conn.iterdump()) == before
    assert db.export_all_data() == exported
    encrypted = security.encrypt_with_pin(exported.encode("utf-8"), "1234")
    saved_screen = db.get_setting(db.SETTING_CALENDAR_SCREEN)
    db.save_setting(db.SETTING_CALENDAR_SCREEN, "")
    db.import_all_data(security.decrypt_with_pin(encrypted, "1234").decode("utf-8"))
    win._on_import_complete()
    assert db.get_setting(db.SETTING_CALENDAR_SCREEN) == saved_screen
    assert win._get_target_screen() is topology.right
    assert security.SALT_FILE.read_bytes() == salt
    assert db.CURRENT_SCHEMA_VERSION == 17
    assert json.loads(exported)["format_version"] == 2


def test_floating_widget_coordinates_survive_screen_roundtrip(app_dir, qtbot, monkeypatch):
    note = db.create_sticky_note(x=2100, y=300)
    dday = db.create_dday_widget("기념일", "2026-12-25", x=2300, y=400)
    focus = db.create_focus_widget("집중", x=2400, y=500)
    win, topology = _setup("compact", "free", qtbot, monkeypatch)
    win._on_screen_changed()
    with db._connection() as conn:
        before = list(conn.iterdump())
    windows = [win._sticky_windows[note], win._dday_windows[dday], win._focus_windows[focus]]
    original = [_placement(widget) for widget in windows]
    topology.online = [topology.left]
    win._on_screen_changed()
    topology.online = [topology.left, topology.right]
    win._on_screen_changed()
    assert [_placement(widget) for widget in windows] == original
    with db._connection() as conn:
        assert list(conn.iterdump()) == before


def test_dpi_change_schedules_recovery_and_screen_recovery_cancels_drag(app_dir, qtbot, monkeypatch):
    class Signal:
        def connect(self, callback):
            self.callback = callback

    win, topology = _setup("large", "free", qtbot, monkeypatch)
    screen = topology.right
    for name in ("geometryChanged", "availableGeometryChanged",
                 "logicalDotsPerInchChanged", "physicalDotsPerInchChanged"):
        setattr(screen, name, Signal())
    win._watch_screen_geometry(screen)
    for name in ("logicalDotsPerInchChanged", "physicalDotsPerInchChanged"):
        win._screen_change_timer.stop()
        getattr(screen, name).callback(120)
        assert win._screen_change_timer.isActive()
    win._screen_change_timer.stop()
    win._calendar_drag_started = True
    win._calendar_drag_offset = QPoint(20, 20)
    win._on_screen_changed()
    assert not win._calendar_drag_started
    assert win._calendar_drag_offset is None
