"""v4.6 공휴일 테마: 설정 스위치와 왼쪽 열 행 높이(36px) 계약.

설정창은 800x560 무스크롤이다. 왼쪽 열에 행 하나를 더할 자리를 만들려고
왼쪽 열(화면 표시·위젯·도구)의 40px 행을 36px로 줄였다. 오른쪽 열은 그대로 40px다.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

import database as db
from ui_settings import SettingsWindow

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _window(qtbot, **kw):
    win = SettingsWindow(**kw)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def _columns(win):
    grid = win.layout().itemAt(0).layout()
    return grid.itemAtPosition(0, 0).widget(), grid.itemAtPosition(0, 1).widget()


def test_switch_row_is_last_in_display_panel(qtbot, app_dir):
    win = _window(qtbot)
    left, _ = _columns(win)
    display = left.layout().itemAt(0).widget()
    labels = [w.text() for w in display.findChildren(QWidget, "rowLabel")]
    assert labels[-2:] == ["음력 및 공휴일", "공휴일 테마"]


def test_switch_default_on_when_key_missing(qtbot, app_dir):
    assert db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "") == ""
    assert _window(qtbot).holiday_theme_switch.isChecked()


def test_switch_reflects_saved_off(qtbot, app_dir):
    db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
    assert not _window(qtbot).holiday_theme_switch.isChecked()


def test_toggle_saves_only_key_and_calls_callback(qtbot, app_dir, monkeypatch):
    calls, saved = [], []
    real_save = db.save_setting
    monkeypatch.setattr(db, "save_setting", lambda k, v: (saved.append((k, v)), real_save(k, v)))
    win = _window(qtbot, on_holiday_theme_changed=lambda: calls.append(1))
    win.holiday_theme_switch.setChecked(False)
    win.holiday_theme_switch.setChecked(True)
    assert saved == [("holiday_theme_enabled", "0"), ("holiday_theme_enabled", "1")]
    assert calls == [1, 1]


def test_callback_is_public_attribute(qtbot, app_dir):
    def callback():
        return None

    win = _window(qtbot, on_holiday_theme_changed=callback)
    assert win.on_holiday_theme_changed is callback
    assert _window(qtbot).on_holiday_theme_changed is None


def test_toggle_without_callback_still_saves(qtbot, app_dir):
    win = _window(qtbot)
    win.holiday_theme_switch.setChecked(False)
    assert db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1") == "0"


def test_layout_fits_without_compression(qtbot, app_dir):
    win = _window(qtbot)
    qtbot.wait(100)
    assert (win.width(), win.height()) == (800, 560)
    assert win.layout().minimumSize().height() <= 560
    for column in _columns(win):
        assert column.height() >= column.sizeHint().height()


def test_left_rows_36_right_rows_40(qtbot, app_dir):
    win = _window(qtbot)
    left, right = _columns(win)
    left_heights = {r.minimumHeight() for r in left.findChildren(QWidget, "settingsRow")}
    right_heights = {r.minimumHeight() for r in right.findChildren(QWidget, "settingsRow")}
    assert 40 not in left_heights and 36 in left_heights
    assert right_heights == {40}


@pytest.mark.parametrize("factor", ["1.25", "1.5"])
def test_layout_fits_at_scale_factors(factor):
    """QT_SCALE_FACTOR는 프로세스 단위이므로 하위 프로세스에서 같은 배치 검사를 돌린다."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_ui_settings_holiday_theme.py::test_layout_fits_without_compression", "-q"],
        env={**os.environ, "QT_SCALE_FACTOR": factor},
        cwd=_PROJECT_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
