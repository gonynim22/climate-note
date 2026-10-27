"""외부 점검 교차검증의 우선 수정 항목: 합성 데이터·실패 주입 회귀."""
import json
import sqlite3
from datetime import date, datetime
from unittest.mock import Mock

import pytest

import database as db
import security
import schedule_rules as rules


@pytest.fixture
def window(app_dir, qtbot, monkeypatch):
    from show_desktop_guard import ShowDesktopKeeper
    from ui_main import MainCalendarWindow
    monkeypatch.setattr(ShowDesktopKeeper, "_install_foreground_hook", lambda self: None)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win._periodic_save_timer.stop()
    win._schedule_alarm_scheduler.stop()
    return win


@pytest.mark.parametrize("rule", ["daily", "weekdays", "weekly", "monthly", "yearly"])
def test_repeat_date_max_and_alarm_edges(rule):
    options = rules.ScheduleOptions(repeat_rule=rule, repeat_until="9999-12-31", alarm_before=0)
    assert rules.occurrence_dates("9999-12-31", options, date.max, date.max) == [date.max]
    assert rules.alarm_times("9999-12-31", options, datetime(9999, 12, 31), datetime.max) == [
        (date.max, datetime(9999, 12, 31, 9))]
    assert rules.alarm_times("0001-01-01", rules.ScheduleOptions(alarm_before=1440),
                             datetime.min, datetime(1, 1, 2)) == []


def test_skip_long_repeat_stops_after_first_remaining(app_dir, monkeypatch):
    sid = db.add_schedule("2026-01-01", "오래 반복", options=rules.ScheduleOptions(
        repeat_rule="daily", repeat_until="9999-12-31"))
    original = db.iter_occurrence_dates
    yielded = []
    def bounded(*args, **kwargs):
        for day in original(*args, **kwargs):
            yielded.append(day)
            assert len(yielded) <= 1, "남은 일정을 전량 펼치면 안 된다"
            yield day
    monkeypatch.setattr(db, "iter_occurrence_dates", bounded)
    db.skip_schedule_occurrence(sid, "2026-01-01")
    assert yielded == [date(2026, 1, 2)]
    assert not db.get_schedules("2026-01-01")
    assert db.get_schedules("2026-01-02")


def test_corrupt_repeat_visible_without_rewriting_row(app_dir):
    sid = db.add_schedule("2026-10-15", "보존할 본문")
    with db._connection() as conn:
        conn.execute("UPDATE schedules SET repeat_rule='daily', repeat_until='2025-01-01' WHERE id=?", (sid,))
        conn.commit()
    assert db.get_schedules("2026-10-15")[0]["content"] == "보존할 본문"
    with db._connection() as conn:
        assert conn.execute("SELECT repeat_until FROM schedules WHERE id=?", (sid,)).fetchone()[0] == "2025-01-01"


@pytest.mark.parametrize("scale", ["compact", "large"])
def test_periodic_save_failure_retry_and_clean_skip(window, monkeypatch, scale):
    window._on_new_sticky_note()
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    assert window._apply_calendar_scale()
    note_id = next(iter(window._sticky_windows))
    source = window._sticky_side_panel._cards[0] if scale == "large" else window._sticky_windows[note_id]
    source.text_edit.insertPlainText("최신 메모")
    original = db.update_sticky_note
    failed = Mock(side_effect=sqlite3.OperationalError("synthetic write failure"))
    monkeypatch.setattr(db, "update_sticky_note", failed)
    window._periodic_save()
    assert "실패" in window.status_label.text()
    assert source.text_edit.document().isModified()
    saved = Mock(wraps=original)
    monkeypatch.setattr(db, "update_sticky_note", saved)
    window._periodic_save()
    assert not source.text_edit.document().isModified()
    assert "실패" not in window.status_label.text()
    assert "최신 메모" in db.get_open_sticky_notes()[0]["content"]
    count = saved.call_count
    window._periodic_save()
    assert saved.call_count == count


@pytest.mark.parametrize("initial,target", [("compact", "large"), ("large", "medium")])
def test_scale_failed_handoff_keeps_all_modes_and_setting(window, monkeypatch, initial, target):
    db.save_setting(db.SETTING_CALENDAR_SCALE, initial)
    assert window._apply_calendar_scale()
    before = window.size()
    monkeypatch.setattr(window, "save_all_sticky_notes", lambda: False)
    monkeypatch.setattr(window, "_show_sticky_handoff_error", lambda: None)
    db.save_setting(db.SETTING_CALENDAR_SCALE, target)
    assert window._apply_calendar_scale() is False
    assert window.size() == before and window.updatesEnabled()
    assert window._sticky_in_panel_mode == window._dday_in_panel_mode == window._focus_in_panel_mode == (initial == "large")
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == initial
    assert window._current_calendar_scale() == initial


def test_layout_failure_restores_repainting(window, monkeypatch):
    original = db.get_setting
    def fail(key, *args):
        if key == db.SETTING_SHOW_SIDEBAR:
            raise sqlite3.OperationalError("synthetic read failure")
        return original(key, *args)
    monkeypatch.setattr(db, "get_setting", fail)
    with pytest.raises(sqlite3.OperationalError):
        window._apply_calendar_scale()
    assert window.updatesEnabled()


def test_settings_scale_choice_rolls_back_with_failed_handoff(window, qtbot, monkeypatch):
    from ui_settings import SettingsWindow
    settings = SettingsWindow(on_scale_changed=window._apply_calendar_scale)
    qtbot.addWidget(settings)
    monkeypatch.setattr(window, "save_all_sticky_notes", lambda: False)
    monkeypatch.setattr(window, "_show_sticky_handoff_error", lambda: None)
    settings.scale_picker.select("large")
    assert settings.scale_picker.current_scale() == "compact"
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "compact"
    assert not window._sticky_in_panel_mode


def test_settings_pin_is_hidden_and_saved_as_verifier(app_dir, qtbot, monkeypatch):
    import ui_settings
    db.save_setting(db.SETTING_PRIVACY_PIN, "1357")
    settings = ui_settings.SettingsWindow()
    qtbot.addWidget(settings)
    assert settings.privacy_pin_edit.text() == ""
    monkeypatch.setattr(ui_settings.InfoBar, "success", lambda **kw: None)
    settings.privacy_pin_edit.setText("2468")
    settings._on_save_privacy_pin()
    assert settings.privacy_pin_edit.text() == ""
    saved = db.get_setting(db.SETTING_PRIVACY_PIN)
    assert saved != "2468" and security.verify_privacy_pin("2468", saved)
    assert not security.verify_privacy_pin("1357", saved)


@pytest.mark.parametrize("scale", ["compact", "large"])
def test_debounce_failure_keeps_retry_and_survives_panel_reload(window, qtbot, monkeypatch, scale):
    window._on_new_sticky_note()
    db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
    assert window._apply_calendar_scale()
    source = (window._sticky_side_panel._cards[0] if scale == "large"
              else next(iter(window._sticky_windows.values())))
    source.text_edit.setPlainText("타이머 저장 실패 뒤 보존")
    original = db.update_sticky_note
    failed = Mock(side_effect=sqlite3.OperationalError("synthetic debounce failure"))
    monkeypatch.setattr(db, "update_sticky_note", failed)
    source._save_timer.start(1)
    qtbot.waitUntil(lambda: failed.called)
    assert source._save_timer.isActive() and source._save_timer.interval() == 2000
    assert source.text_edit.document().isModified()
    monkeypatch.setattr(db, "update_sticky_note", original)
    if scale == "large":
        assert window._sticky_side_panel.reload()
        assert window._sticky_side_panel._cards[0].text_edit.toPlainText() == "타이머 저장 실패 뒤 보존"
    else:
        window._periodic_save()
    assert "타이머 저장 실패 뒤 보존" in db.get_open_sticky_notes()[0]["content"]


def test_large_sticky_limit_counts_hidden_windows(window, monkeypatch):
    import ui_main
    monkeypatch.setattr(ui_main.InfoBar, "warning", lambda **kw: None)
    for _ in range(10):
        db.create_sticky_note()
    window._on_import_complete()
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    assert window._apply_calendar_scale()
    assert len(window._sticky_windows) == 10
    window._on_new_sticky_note()
    assert len(db.get_open_sticky_notes()) == 10


def test_import_limits_preserve_existing_and_all_imported_data(app_dir):
    sticky = [db.create_sticky_note() for _ in range(10)]
    ddays = [db.create_dday_widget(f"현재 {i}", "2026-12-31") for i in range(5)]
    focus = db.create_focus_widget("진행 중 목표")
    payload = json.loads(db.export_all_data())
    for table in ("sticky_notes", "dday_widgets", "focus_widgets"):
        payload[table] = payload[table][:1]
    payload["sticky_notes"][0]["content"] = "가져온 메모"
    payload["focus_sessions"] = [{"widget_id": payload["focus_widgets"][0]["source_id"], "goal": "가져온 세션"}]
    result = db.import_all_data(json.dumps(payload))
    assert result == {"sticky_notes": 1, "dday_widgets": 1, "focus_widgets": 1}
    assert [n["id"] for n in db.get_open_sticky_notes()] == sticky
    assert {n["id"] for n in db.get_open_dday_widgets()} == set(ddays)
    assert [n["id"] for n in db.get_open_focus_widgets()] == [focus]
    exported = json.loads(db.export_all_data())
    assert len(exported["sticky_notes"]) == 11
    imported = next(n for n in exported["sticky_notes"] if n["content"] == "가져온 메모")
    assert imported["is_open"] == 0
    assert len(exported["dday_widgets"]) == 6
    imported_focus = next(n for n in exported["focus_widgets"] if n["source_id"] != focus)
    assert imported_focus["is_open"] == 0
    assert exported["focus_sessions"][0]["widget_id"] == imported_focus["source_id"]


@pytest.mark.parametrize("category,field,cross", [("water", "density_input", "mgl"),
                                                   ("gas_fraction", "gas_pressure_input", "mgm3")])
def test_same_basis_ignores_unneeded_conditions_but_cross_requires_them(qtbot, category, field, cross):
    from ui_conversion_conditions import ConversionConditionsPanel
    from unit_converter import convert
    panel = ConversionConditionsPanel()
    qtbot.addWidget(panel)
    panel.set_category(category)
    panel.set_units("ppm", "ppb")
    getattr(panel, field).clear()
    conditions = panel.conditions()
    assert convert(category, "ppm", "ppb", 1, conditions=conditions) == pytest.approx(1000)
    panel.restore(conditions)
    assert getattr(panel, field).text() == ""
    panel.set_units("ppm", cross)
    with pytest.raises(ValueError):
        panel.conditions()


def test_privacy_hash_randomized_and_legacy_readable():
    first, second = security.hash_privacy_pin("1234"), security.hash_privacy_pin("1234")
    assert first != second and first != "1234"
    for stored in (first, second, "1234"):
        assert security.verify_privacy_pin("1234", stored)
        assert not security.verify_privacy_pin("4321", stored)
    for malformed in ("", "pin$1$broken", first[:-1], first.replace("$", "!")):
        assert not security.verify_privacy_pin("1234", malformed)


def test_startup_pin_upgrade_preserves_ciphertext_salt_and_backup(app_dir):
    import main
    db.save_setting(db.SETTING_PRIVACY_PIN, "1357")
    sid = db.add_schedule("2026-10-18", "그대로 보존")
    with db._connection() as conn:
        cipher = conn.execute("SELECT content FROM schedules WHERE id=?", (sid,)).fetchone()[0]
    salt = security.SALT_FILE.read_bytes()
    assert main._initialize_database()
    stored = db.get_setting(db.SETTING_PRIVACY_PIN)
    assert stored != "1357" and security.verify_privacy_pin("1357", stored)
    with db._connection() as conn:
        assert conn.execute("SELECT content FROM schedules WHERE id=?", (sid,)).fetchone()[0] == cipher
    assert security.SALT_FILE.read_bytes() == salt
    assert list((app_dir / "backups").glob("*privacy_pin*"))
    assert main._initialize_database()
    assert db.get_setting(db.SETTING_PRIVACY_PIN) == stored
    assert "privacy_pin" not in json.loads(db.export_all_data())["settings"]


def test_failed_pin_protection_backup_stops_upgrade(app_dir, monkeypatch):
    import main
    db.save_setting(db.SETTING_PRIVACY_PIN, "1357")
    def fail(*args):
        raise OSError("synthetic backup failure")
    monkeypatch.setattr(db, "backup_before_operation", fail)
    with pytest.raises(OSError):
        main._initialize_database()
    assert db.get_setting(db.SETTING_PRIVACY_PIN) == "1357"


def test_lock_attempt_cooldown_and_success_reset(app_dir, qtbot, monkeypatch):
    import ui_main
    from PySide6.QtWidgets import QWidget
    db.save_setting(db.SETTING_PRIVACY_PIN, security.hash_privacy_pin("1357"))
    parent = QWidget()
    qtbot.addWidget(parent)
    overlay = ui_main.LockOverlay(parent)
    unlocked = Mock()
    overlay.unlocked.connect(unlocked)
    now = [100.0]
    monkeypatch.setattr(ui_main.time, "monotonic", lambda: now[0])
    for _ in range(5):
        overlay.pin_input.setText("0000")
        overlay._check_pin()
    overlay.pin_input.setText("1357")
    overlay._check_pin()
    assert not unlocked.called
    now[0] += 31
    overlay.pin_input.setText("1357")
    overlay._check_pin()
    assert unlocked.call_count == 1 and overlay._pin_failures == 0


def test_transfer_password_policy_legacy_roundtrip_and_wrong_password(app_dir, qtbot, monkeypatch):
    import ui_settings
    from cryptography.fernet import InvalidToken
    win = ui_settings.SettingsWindow()
    qtbot.addWidget(win)
    errors = Mock()
    monkeypatch.setattr(ui_settings.InfoBar, "error", errors)
    assert not win._validate_transfer_password("1234")
    assert win._validate_transfer_password("1234", importing=True)
    assert win._validate_transfer_password("새로운 긴 암호 2026")
    for password in ("1234", "새로운 긴 암호 2026"):
        blob = security.encrypt_with_pin(db.export_all_data().encode(), password)
        assert json.loads(security.decrypt_with_pin(blob, password))["format_version"] == 4
        with pytest.raises(InvalidToken):
            security.decrypt_with_pin(blob, "wrong-password")
    target = app_dir / "old.enc"
    target.write_bytes(security.encrypt_with_pin(b"{}", "1234"))
    monkeypatch.setattr(ui_settings.QFileDialog, "getOpenFileName", lambda *args: (str(target), ""))
    win.import_pin.setText("4321")
    win._on_import()
    assert errors.call_args.kwargs["title"] == "가져오기 실패"
