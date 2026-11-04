"""설정 › 시스템의 '인터넷 접속' 스위치: 기본 꺼짐, 키 하나만 저장, 저장 실패·초기화에도 화면과 값이 어긋나지 않는다."""
import sqlite3

import pytest
from PySide6.QtWidgets import QWidget

import database as db
import ui_settings
from ui_settings import SettingsWindow

TOOLTIP = ("켜면 하루 한 번 GitLab 공개 저장소에서 새 버전이 있는지만 확인합니다. "
           "일정·메모는 보내지 않습니다. 업무망 PC는 꺼 두세요.")


def _window(qtbot, **kw):
    win = SettingsWindow(**kw)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def _system_panel(win):
    grid = win.layout().itemAt(0).layout()
    return grid.itemAtPosition(0, 1).widget().layout().itemAt(2).widget()


def _audits(monkeypatch):
    events = []
    monkeypatch.setattr(ui_settings, "audit", lambda event, result="성공": events.append(event))
    return events


def test_row_sits_between_keep_desktop_and_font(qtbot, app_dir):
    labels = [w.text() for w in _system_panel(_window(qtbot)).findChildren(QWidget, "rowLabel")]
    assert labels == ["자동 실행", "바탕화면 고정", "인터넷 접속", "앱 글꼴"]


def test_switch_off_by_default_and_for_garbage(qtbot, app_dir):
    assert not _window(qtbot).internet_switch.isChecked()
    db.save_setting(db.SETTING_INTERNET_ACCESS, "yes")
    assert not _window(qtbot).internet_switch.isChecked()
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    assert _window(qtbot).internet_switch.isChecked()


def test_tooltip_says_what_is_sent(qtbot, app_dir):
    assert _window(qtbot).internet_switch.toolTip() == TOOLTIP


def test_toggle_saves_key_audits_and_calls_back(qtbot, app_dir, monkeypatch):
    calls, saved = [], []
    events = _audits(monkeypatch)
    real_save = db.save_setting
    monkeypatch.setattr(db, "save_setting", lambda k, v: (saved.append((k, v)), real_save(k, v)))
    win = _window(qtbot, on_internet_access_changed=lambda: calls.append(1))
    win.internet_switch.setChecked(True)
    win.internet_switch.setChecked(False)
    assert saved == [("internet_access_enabled", "1"), ("internet_access_enabled", "0")]
    assert events == ["인터넷 접속 켬", "인터넷 접속 끔"]
    assert calls == [1, 1]


def test_failed_save_restores_switch_and_skips_callback(qtbot, app_dir, monkeypatch):
    """끄기 저장이 실패했는데 화면만 꺼지면 사용자는 꺼진 줄 아는데 요청이 계속 나간다."""
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    calls, attempts = [], []
    events = _audits(monkeypatch)
    win = _window(qtbot, on_internet_access_changed=lambda: calls.append(1))

    def broken(key, value):
        attempts.append(key)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "save_setting", broken)
    win.internet_switch.setChecked(False)
    assert win.internet_switch.isChecked()
    assert calls == []
    assert attempts == ["internet_access_enabled"]
    assert "인터넷 접속 끔" not in events


def test_failed_save_and_read_keep_switch_usable(qtbot, app_dir, monkeypatch):
    """DB를 아예 못 여는 순간: 되돌릴 때 다시 읽으면 신호가 막힌 채 굳어 스위치가 먹통이 된다."""
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    calls = []
    win = _window(qtbot, on_internet_access_changed=lambda: calls.append(1))
    real_save, real_read = db.save_setting, db.get_setting

    def broken(*args):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(db, "save_setting", broken)
    monkeypatch.setattr(db, "get_setting", broken)
    win.internet_switch.setChecked(False)
    assert win.internet_switch.isChecked()
    assert not win.internet_switch.signalsBlocked()

    monkeypatch.setattr(db, "save_setting", real_save)
    monkeypatch.setattr(db, "get_setting", real_read)
    win.internet_switch.setChecked(False)
    assert db.get_setting(db.SETTING_INTERNET_ACCESS, "") == "0"
    assert calls == [1]


@pytest.mark.parametrize("error", [OSError("path"), ValueError("path")])
def test_other_save_errors_restore_switch(qtbot, app_dir, monkeypatch, error):
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    win = _window(qtbot)

    def broken(key, value):
        raise error

    monkeypatch.setattr(db, "save_setting", broken)
    win.internet_switch.setChecked(False)
    assert win.internet_switch.isChecked()


def test_reset_succeeds_even_if_key_cannot_be_read_back(qtbot, app_dir, monkeypatch):
    """초기화는 끝났는데 스위치를 맞추다 실패해 '초기화 실패'로 보이면 안 된다."""
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    win = _window(qtbot)
    succeeded = []
    win.reset_succeeded.connect(lambda: succeeded.append(1))
    real_read = db.get_setting

    def read(key, default=""):
        if key == db.SETTING_INTERNET_ACCESS:
            raise sqlite3.OperationalError("database is locked")
        return real_read(key, default)

    monkeypatch.setattr(db, "get_setting", read)
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    win._on_reset()
    assert succeeded == [1]
    assert not win.internet_switch.isChecked()


def test_reset_with_open_window_turns_switch_off(qtbot, app_dir, monkeypatch):
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    events = _audits(monkeypatch)
    win = _window(qtbot)
    assert win.internet_switch.isChecked()
    monkeypatch.setattr(ui_settings.MessageBox, "exec", lambda self: 1)
    win._on_reset()
    assert not win.internet_switch.isChecked()
    assert db.get_setting(db.SETTING_INTERNET_ACCESS, "missing") == "missing"
    assert "인터넷 접속 끔" not in events
