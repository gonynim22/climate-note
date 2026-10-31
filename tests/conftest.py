import logging
import os
from pathlib import Path

import pytest

# security/database는 import 시점에 APP_DIR과 audit.log를 초기화한다.
# 테스트 수집 단계부터 실제 AppData를 건드리지 않도록 먼저 경로를 격리한다.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_requested_appdata = os.environ.get("CLIMATENOTE_TEST_APPDATA")
if _requested_appdata:
    _BOOTSTRAP_APPDATA = Path(_requested_appdata).resolve()
    _harness_root = (_PROJECT_ROOT / "output" / "harness").resolve()
    if (
        _BOOTSTRAP_APPDATA == _harness_root
        or not _BOOTSTRAP_APPDATA.is_relative_to(_harness_root)
        or not _harness_root.is_relative_to(_PROJECT_ROOT)
    ):
        raise ValueError("CLIMATENOTE_TEST_APPDATA는 프로젝트 output/harness 하위여야 합니다.")
else:
    _BOOTSTRAP_APPDATA = _PROJECT_ROOT / ".pytest-localappdata"
_BOOTSTRAP_APPDATA.mkdir(parents=True, exist_ok=True)
os.environ["LOCALAPPDATA"] = str(_BOOTSTRAP_APPDATA)
# 앱 모듈은 src/에 있다(B안). runpy로 이 파일만 실행하는 하위 프로세스도 찾게 한다.
import sys
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import security
import database as db


def _dispose_test_windows(previous):
    """테스트가 만든 앱 top-level 창을 DB monkeypatch 해제 전에 폐기한다.

    메인 창과 별도인 플로팅 창은 qtbot에 메인만 등록해도 자동 삭제되지 않는다.
    close()는 저장/확인 팝업을 실행하므로 사용하지 않고, DeferredDelete만 처리한다.
    기존 창 및 Fluent 전역 helper 창은 이 테스트의 소유물로 취급하지 않는다.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            if widget not in previous and type(widget).__module__.startswith("ui_"):
                widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    """각 테스트에 격리된 앱 디렉토리를 제공하는 픽스처.

    security.APP_DIR, database.DB_FILE 등 모듈 전역 변수를 tmp_path로 패치하고
    Fernet 캐시를 초기화하여 테스트 간 상호 오염을 방지한다.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    previous_windows = set(app.topLevelWidgets()) if app is not None else set()
    d = tmp_path / "MyDesktopCalendar"
    d.mkdir()

    # security 모듈 전역 패치
    monkeypatch.setattr(security, "APP_DIR", d)
    monkeypatch.setattr(security, "SALT_FILE", d / ".salt")
    monkeypatch.setattr(security, "AUDIT_LOG_FILE", d / "audit.log")

    # database 모듈 전역 패치
    monkeypatch.setattr(db, "APP_DIR", d)
    monkeypatch.setattr(db, "DB_FILE", d / "calendar.db")

    # Fernet 캐시 초기화 (이전 테스트의 키 오염 방지)
    monkeypatch.setattr(security, "_fernet_cache", None)
    monkeypatch.setattr(security, "_legacy_fernet_cache", None)

    # audit logger 재초기화 (새 경로로)
    logger = logging.getLogger("audit")
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()
    monkeypatch.setattr(security, "audit_logger", security._init_audit_logger())

    # DB 초기 마이그레이션
    db.migrate()

    try:
        yield d
    finally:
        _dispose_test_windows(previous_windows)
