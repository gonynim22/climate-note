"""바로가기 사이드바 기본값(2026-10-11 사용자 A안): 새 설치·초기화는 켜짐, 기존 DB 값은 그대로 둔다."""
import pytest
from PySide6.QtWidgets import QLabel

import database as db
import security
from ui_settings import SettingsWindow


@pytest.fixture
def empty_dir(app_dir, monkeypatch):
    """app_dir의 UI 정리 가드는 유지하고 DB가 아직 없는 합성 폴더를 쓴다(새 설치 재현)."""
    folder = app_dir.parent / "new-install" / "MyDesktopCalendar"
    folder.mkdir(parents=True)
    monkeypatch.setattr(db, "APP_DIR", folder)
    monkeypatch.setattr(db, "DB_FILE", folder / "calendar.db")
    monkeypatch.setattr(security, "APP_DIR", folder)
    monkeypatch.setattr(security, "SALT_FILE", folder / ".salt")
    return folder


@pytest.mark.parametrize("scale", db.CALENDAR_SCALES)
def test_new_install_turns_sidebar_on(empty_dir, scale):
    db.migrate(initial_calendar_scale=scale)  # 처음 실행 크기 선택 뒤의 새 DB
    assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "1"
    assert db.get_setting(db.SETTING_CALENDAR_SCALE) == scale


@pytest.mark.parametrize("saved", ["0", "1"])
def test_existing_database_keeps_sidebar_value(empty_dir, saved):
    db.migrate()
    db.save_setting(db.SETTING_SHOW_SIDEBAR, saved)
    db.migrate(initial_calendar_scale="compact")  # 이미 DB가 있으면 새 설치 기본값을 쓰지 않는다
    assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == saved


def test_factory_reset_turns_sidebar_on(app_dir):
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
    db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
    db.reset_database()
    assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "1"
    assert db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE) == "compact"


def test_settings_switch_names_its_scope(qtbot, app_dir):
    win = SettingsWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    labels = [label for label in win.findChildren(QLabel) if label.text() == "기본 크기 바로가기"]
    assert len(labels) == 1
    label = labels[0]
    assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width()  # 잘리지 않음
    assert win.sidebar_switch.toolTip() == "기본 크기에서 바로가기 열을 보입니다. 중간·크게에서는 늘 보입니다."
