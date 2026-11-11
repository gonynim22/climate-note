"""열린 설정창이 가져오기·초기화 뒤 DB 값을 보인다(2026-11-11, v4.9 최종 수정).

전에는 일정 색과 인터넷 스위치만 맞추고 나머지 컨트롤은 다시 열 때까지 예전 값을 보였다.
값만 바꾸고 설정 처리기(저장·적용)는 부르지 않는다. 적용은 메인 창이 가져오기·초기화 콜백에서 한다.
"""
import json
import sqlite3

import database as db
import security
import ui_settings
from ui_settings import SettingsWindow

OLD = {db.SETTING_APP_OPACITY: "90", db.SETTING_WIDGET_OPACITY: "80", db.SETTING_CALENDAR_SCALE: "compact",
       db.SETTING_SHOW_LUNAR: "0", db.SETTING_HOLIDAY_THEME_ENABLED: "1", db.SETTING_CALENDAR_GRID_LINES: "0",
       db.SETTING_SHOW_SIDEBAR: "0", db.SETTING_SHOW_LAW_SEARCH: "1", db.SETTING_USE_PRIVACY_LOCK: "0",
       db.SETTING_KEEP_ON_SHOW_DESKTOP: "0", db.SETTING_CALENDAR_POSITION: "bottom-right",
       db.SETTING_APP_FONT: "Malgun Gothic"}
NEW = {db.SETTING_APP_OPACITY: "60", db.SETTING_WIDGET_OPACITY: "45", db.SETTING_CALENDAR_SCALE: "large",
       db.SETTING_SHOW_LUNAR: "1", db.SETTING_HOLIDAY_THEME_ENABLED: "0", db.SETTING_CALENDAR_GRID_LINES: "1",
       db.SETTING_SHOW_SIDEBAR: "1", db.SETTING_SHOW_LAW_SEARCH: "0", db.SETTING_USE_PRIVACY_LOCK: "1",
       db.SETTING_KEEP_ON_SHOW_DESKTOP: "1", db.SETTING_CALENDAR_POSITION: "top-left",
       db.SETTING_APP_FONT: "system:기후노트시험글꼴"}
PALETTE = ("#FF9F68", "#80CFA9", "#B197FC")
SHOWN_OLD = {"opacity": (90, 90, 80, 80), "scale": "compact", "lunar": False, "holiday": True, "grid": False,
             "sidebar": False, "law": True, "lock": (False, False), "keep": False, "position": ["bottom-right"],
             "font": "Malgun Gothic", "palette": tuple(db.DEFAULT_SCHEDULE_PALETTE)}
SHOWN_NEW = {"opacity": (60, 60, 45, 45), "scale": "large", "lunar": True, "holiday": False, "grid": True,
             "sidebar": True, "law": False, "lock": (True, True), "keep": True, "position": ["top-left"],
             "font": "system:기후노트시험글꼴", "palette": tuple(db.DEFAULT_SCHEDULE_PALETTE)}


def _window(qtbot, calls):
    def spy(name):
        return lambda *args: calls.append(name)

    handlers = {"on_lunar_changed": spy("lunar"), "on_law_search_changed": spy("law_search"),
                "on_position_changed": spy("position"), "on_monitor_selected": spy("monitor"),
                "on_sidebar_changed": spy("sidebar"), "on_opacity_changed": spy("opacity"),
                "on_scale_changed": spy("scale"), "on_keep_changed": spy("keep"),
                "on_holiday_theme_changed": spy("holiday_theme"), "on_grid_lines_changed": spy("grid_lines"),
                "on_internet_access_changed": spy("internet_access"),
                "on_schedule_colors_changed": spy("schedule_colors")}
    win = SettingsWindow(on_import_callback=spy("import"), on_reset_callback=spy("reset"), **handlers)
    qtbot.addWidget(win)
    return win


def _shown(win):
    """컨트롤이 지금 보이는 값."""
    return {
        "opacity": (win.opacity_slider.value(), win.opacity_value_label.value(),
                    win.widget_opacity_slider.value(), win.widget_opacity_value_label.value()),
        "scale": win.scale_picker.current_scale(),
        "lunar": win.lunar_switch.isChecked(),
        "holiday": win.holiday_theme_switch.isChecked(),
        "grid": win.grid_lines_switch.isChecked(),
        "sidebar": win.sidebar_switch.isChecked(),
        "law": win.law_search_switch.isChecked(),
        "lock": (win.privacy_switch.isChecked(), not win.pin_container.isHidden()),
        "keep": win.keep_desktop_switch.isChecked(),
        "position": [key for key, button in win._position_btns.items()
                     if "background:#2563EB" in button.styleSheet()],
        "font": win.font_combo.itemData(win.font_combo.currentIndex()),
        "palette": win.schedule_color_picker.colors(),
    }


def _save(values):
    for key, value in values.items():
        db.save_setting(key, value)


def test_open_window_shows_imported_settings(qtbot, app_dir, monkeypatch):
    payload = json.dumps({"format_version": 2, "settings": NEW}).encode("utf-8")
    path = app_dir / "settings.enc"
    path.write_bytes(security.encrypt_with_pin(payload, "1234"))
    _save(OLD)
    calls = []
    win = _window(qtbot, calls)
    assert _shown(win) == SHOWN_OLD
    win.import_pin.setText("1234")
    monkeypatch.setattr(ui_settings.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(db, "backup_before_operation", lambda operation: True)

    win._on_import()

    assert calls == ["import"]  # 처리기는 하나도 불리지 않는다(메인 창이 가져오기 콜백에서 적용한다)
    assert {key: db.get_setting(key) for key in NEW} == NEW  # 가져온 값을 예전 값으로 덮어쓰지 않는다
    assert _shown(win) == SHOWN_NEW


def test_import_still_succeeds_when_showing_settings_fails(qtbot, app_dir, monkeypatch):
    # 가져오기는 이미 끝났다. 컨트롤을 다시 보이다 DB 읽기가 실패해도 '가져오기 실패'로 보이면 안 된다.
    payload = json.dumps({"format_version": 2, "settings": NEW}).encode("utf-8")
    path = app_dir / "settings.enc"
    path.write_bytes(security.encrypt_with_pin(payload, "1234"))
    calls, errors = [], []
    win = _window(qtbot, calls)
    win.import_pin.setText("1234")
    monkeypatch.setattr(ui_settings.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(db, "backup_before_operation", lambda operation: True)
    monkeypatch.setattr(ui_settings.InfoBar, "error", lambda *args, **kwargs: errors.append(kwargs.get("title")))

    def locked():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(win, "_show_saved_settings", locked)
    win._on_import()
    assert calls == ["import"]
    assert errors == []
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "large"


def test_open_window_shows_defaults_after_reset(qtbot, app_dir, monkeypatch):
    _save(NEW)
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    db.save_schedule_palette(PALETTE)
    calls = []
    win = _window(qtbot, calls)
    assert _shown(win) == {**SHOWN_NEW, "palette": PALETTE}
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    monkeypatch.setattr(db, "backup_before_operation", lambda operation: True)

    win._on_reset()

    assert calls == ["reset"]
    fresh = _window(qtbot, [])  # 초기화 뒤 새로 연 창과 같아야 한다
    assert _shown(win) == _shown(fresh)
    assert _shown(win)["scale"] == "compact" and _shown(win)["opacity"] == (100, 100, 100, 100)
    assert _shown(win)["palette"] == tuple(db.DEFAULT_SCHEDULE_PALETTE)  # 한 칸만 바꿔도 예전 색이 섞여 저장되지 않는다
    assert win.internet_switch.isChecked() is False
