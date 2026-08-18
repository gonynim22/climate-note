import logging
import os
from pathlib import Path

import pytest

# security/database는 import 시점에 APP_DIR과 audit.log를 초기화한다.
# 테스트 수집 단계부터 실제 AppData를 건드리지 않도록 먼저 경로를 격리한다.
_BOOTSTRAP_APPDATA = Path(__file__).resolve().parent.parent / ".pytest-localappdata"
_BOOTSTRAP_APPDATA.mkdir(exist_ok=True)
os.environ["LOCALAPPDATA"] = str(_BOOTSTRAP_APPDATA)

import security
import database as db


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    """각 테스트에 격리된 앱 디렉토리를 제공하는 픽스처.

    security.APP_DIR, database.DB_FILE 등 모듈 전역 변수를 tmp_path로 패치하고
    Fernet 캐시를 초기화하여 테스트 간 상호 오염을 방지한다.
    """
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

    yield d
