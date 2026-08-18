"""설정창 '바탕화면 고정' 토글 테스트."""
from unittest.mock import MagicMock

from qfluentwidgets import BodyLabel, SwitchButton

import database as db
import ui_main
from ui_main import MainCalendarWindow
from ui_settings import SettingsWindow


def test_settings_has_keep_desktop_switch_default_on(app_dir, qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    assert isinstance(w.keep_desktop_switch, SwitchButton)
    assert w.keep_desktop_switch.isChecked() is True  # 기본 ON


def test_settings_uses_desktop_pin_label(app_dir, qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    labels = [label.text() for label in w.findChildren(BodyLabel)]

    assert "바탕화면 고정" in labels
    assert "바탕화면 유지" not in labels


def test_toggle_off_saves_and_calls_back(app_dir, qtbot):
    calls = {"n": 0}
    w = SettingsWindow(on_keep_changed=lambda: calls.__setitem__("n", calls["n"] + 1))
    qtbot.addWidget(w)

    w.keep_desktop_switch.setChecked(False)

    assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "0"
    assert calls["n"] >= 1


def test_toggle_back_on_saves(app_dir, qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    w.keep_desktop_switch.setChecked(False)
    w.keep_desktop_switch.setChecked(True)
    assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"


def test_hook_failure_warns_once_after_main_window_is_shown(
    app_dir, qtbot, monkeypatch
):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "1")
    monkeypatch.setattr(
        ui_main.ShowDesktopKeeper,
        "is_operational",
        lambda self: False,
    )
    warning = MagicMock()
    monkeypatch.setattr(ui_main.InfoBar, "warning", warning)

    w = MainCalendarWindow()
    qtbot.addWidget(w)
    assert warning.call_count == 0

    w.show()
    qtbot.waitUntil(lambda: warning.call_count == 1)

    assert warning.call_args.kwargs["title"] == "바탕화면 고정"
    assert "일반 창으로 동작합니다" in warning.call_args.kwargs["content"]
    assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"

    w.hide()
    w.show()
    qtbot.wait(20)
    assert warning.call_count == 1


def test_turning_keep_on_warns_once_when_hook_is_unavailable(
    app_dir, qtbot, monkeypatch
):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    monkeypatch.setattr(
        ui_main.ShowDesktopKeeper,
        "is_operational",
        lambda self: False,
    )
    warning = MagicMock()
    monkeypatch.setattr(ui_main.InfoBar, "warning", warning)

    w = MainCalendarWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.wait(20)
    assert warning.call_count == 0

    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "1")
    w._on_keep_desktop_changed()
    assert warning.call_count == 1
    assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"

    w._on_keep_desktop_changed()
    assert warning.call_count == 1
