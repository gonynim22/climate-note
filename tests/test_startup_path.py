"""자동실행 경로 갱신의 검증 환경 안전장치."""

import winreg
from unittest.mock import MagicMock

import main


def test_startup_path_refresh_can_be_disabled_for_isolated_smoke(
        monkeypatch):
    monkeypatch.setenv("CLIMATENOTE_SKIP_STARTUP_REFRESH", "1")
    open_key = MagicMock()
    monkeypatch.setattr(winreg, "OpenKey", open_key)

    main._refresh_startup_path()

    open_key.assert_not_called()


def test_tray_quit_is_blocked_when_preflight_fails():
    app = MagicMock()
    main_window = MagicMock()
    main_window.prepare_for_quit.return_value = False

    assert main._quit(app, main_window) is False
    main_window.prepare_for_quit.assert_called_once_with()
    app.quit.assert_not_called()


def test_tray_quit_runs_after_successful_preflight():
    app = MagicMock()
    main_window = MagicMock()
    main_window.prepare_for_quit.return_value = True

    assert main._quit(app, main_window) is True
    main_window.prepare_for_quit.assert_called_once_with()
    app.quit.assert_called_once_with()


def test_data_health_error_message_promises_no_data_change():
    title, content = main._data_health_error_message("salt_missing")

    assert title == "데이터 보호를 위해 실행을 중단했습니다"
    assert "새 salt를 만들지 않았습니다" in content
    assert "데이터와 기존 백업은 변경하지 않았습니다" in content
