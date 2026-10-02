"""바로가기 메뉴 → 실제 대화상자와 예약 호출 수명 회귀."""
import json
import os
from pathlib import Path
import sys

import pytest

from tools.smoke_release import managed_launch


@pytest.mark.parametrize("operation", ["file", "folder", "rename", "repair"])
@pytest.mark.parametrize("outcome", ["accept", "cancel"])
def test_shortcut_real_menu_dialog_survives_in_subprocess(tmp_path, operation, outcome):
    # 접근 위반이 돌아와도 전체 pytest를 죽이지 않도록 소유한 Job 안에서 검사.
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "tools/smoke_release.py"), "_launch",
               sys.executable, "-X", "faulthandler",
               str(root / "tests/shortcut_dialog_probe.py"), str(tmp_path), operation, outcome]
    log = tmp_path / "dialog.log"
    with managed_launch(command, os.environ.copy(), log) as (_job, process):
        code = process.wait(timeout=30)
    with open(log, encoding="utf-8", errors="replace") as stream:
        log_text = stream.read()
    assert code == 0, log_text
    with open(tmp_path / "result.json", encoding="utf-8") as stream:
        result = json.load(stream)
    assert result["ok"], result


@pytest.mark.parametrize("action", ["file", "folder", "rename", "repair"])
@pytest.mark.parametrize("cancel", ["hide", "owner_hide", "disable", "lock", "tray", "reload", "delete"])
def test_pending_shortcut_action_does_not_outlive_ui(qtbot, app_dir, monkeypatch, action, cancel):
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from ui_main import ShortcutSlot

    owner = QWidget()
    qtbot.addWidget(owner)
    layout = QVBoxLayout(owner)
    slot = ShortcutSlot(1, owner)
    layout.addWidget(slot)
    owner.show()
    calls = []
    methods = {"file": "_select_file", "folder": "_select_folder",
               "rename": "_rename", "repair": "_show_registration_menu"}
    monkeypatch.setattr(slot, methods[action], lambda: calls.append(action))
    menu = slot._build_registration_menu() if action in ("file", "folder") else slot._build_manage_menu()
    qtbot.addWidget(menu)
    menu.menuActions()[action in ("folder", "repair")].trigger()
    assert calls == []
    if cancel == "hide":
        slot.hide()
        slot.show()  # 다시 표시해도 이전 예약을 되살리지 않는다.
    elif cancel == "owner_hide":
        owner.hide()
        owner.show()
    elif cancel == "disable":
        owner.setEnabled(False)
    elif cancel == "lock":
        owner._is_locked = True
    elif cancel == "tray":
        owner._hidden_to_tray = True
    elif cancel == "reload":
        slot.update_data("새 데이터", "")
    else:
        slot.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qtbot.wait(25)
    assert calls == []


def test_lock_unlock_cancels_pending_shortcut_dialog(qtbot, app_dir, monkeypatch):
    import database as db
    from ui_main import MainCalendarWindow

    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    slot = win.sidebar.slots[0]
    calls = []
    monkeypatch.setattr(slot, "_select_file", lambda: calls.append(True))
    menu = slot._build_registration_menu()
    qtbot.addWidget(menu)
    menu.menuActions()[0].trigger()
    win._lock()
    win._unlock()
    qtbot.wait(25)
    assert calls == []
