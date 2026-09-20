# security.py - 하드웨어 키 파생, Fernet 암복호화, 감사 로그
import os
import uuid
import hashlib
import logging
import base64
import tempfile
from pathlib import Path
from datetime import datetime

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ─── 앱 데이터 경로 ────────────────────────────────────────────
APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MyDesktopCalendar"
APP_DIR.mkdir(parents=True, exist_ok=True)

SALT_FILE = APP_DIR / ".salt"
AUDIT_LOG_FILE = APP_DIR / "audit.log"


def validate_app_path(path: Path, label: str = "경로") -> Path:
    """APP_DIR 내부 경로인지 검증"""
    resolved = path.resolve()
    if not str(resolved).startswith(str(APP_DIR.resolve())):
        raise ValueError(f"{label} 조작이 감지되었습니다.")
    return resolved


# ─── 감사 로그 초기화 ──────────────────────────────────────────
def _init_audit_logger() -> logging.Logger:
    logger = logging.getLogger("audit")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] | %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger

audit_logger = _init_audit_logger()


def audit(event: str, result: str = "성공") -> None:
    """감사 로그 기록: [YYYY-MM-DD HH:MM:SS] | 이벤트 | 결과"""
    audit_logger.info("%s | %s", event, result)


# ─── 하드웨어 기반 Salt 및 키 파생 ────────────────────────────
def _get_machine_guid() -> str:
    """Windows 레지스트리에서 MachineGuid 읽기 (설치 시 생성, 재부팅에도 불변)"""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except (OSError, FileNotFoundError):
        # fallback: uuid.getnode() (레지스트리 접근 불가 시)
        return str(uuid.getnode())


def _get_hardware_id() -> str:
    """MachineGuid + OS 사용자명으로 PC 고유 ID 생성 (안정적)"""
    machine_id = _get_machine_guid()
    username = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
    raw = f"{machine_id}:{username}"
    return hashlib.sha256(raw.encode()).hexdigest()


def file_link_origin() -> str:
    """Non-secret link location tag; never reads/creates salt or derives an encryption key."""
    username = os.environ.get("USERNAME", os.environ.get("USER", ""))
    if not username:
        return ""
    return hashlib.sha256(
        ("climatenote-file:v1:" + _get_hardware_id()).encode("utf-8")
    ).hexdigest()


def _get_legacy_hardware_id() -> str:
    """기존 MAC 기반 하드웨어 ID (마이그레이션용)"""
    mac = uuid.getnode()
    username = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
    raw = f"{mac}:{username}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _load_or_create_salt() -> bytes:
    """Salt 파일 로드 또는 신규 생성 (AppData에 분리 저장)"""
    resolved = validate_app_path(SALT_FILE, "Salt 파일")
    if resolved.exists():
        with open(resolved, "rb") as salt_file:
            return salt_file.read()
    salt = os.urandom(32)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=".salt.", suffix=".tmp", dir=resolved.parent,
                delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(salt)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, resolved)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
    return salt


def read_existing_salt() -> bytes:
    """기존 salt를 생성 없이 엄격하게 읽는다."""
    resolved = validate_app_path(SALT_FILE, "Salt 파일")
    with open(resolved, "rb") as salt_file:
        salt = salt_file.read()
    if len(salt) != 32:
        raise ValueError("Salt 파일 길이가 올바르지 않습니다.")
    return salt


def create_initial_salt() -> bytes:
    """보호할 기존 암호문이 없다고 확인된 데이터셋의 최초 salt를 만든다."""
    salt = _load_or_create_salt()
    if len(salt) != 32:
        raise ValueError("Salt 파일 길이가 올바르지 않습니다.")
    return salt


def _derive_fernet_key(material: str, salt: bytes) -> bytes:
    """PBKDF2HMAC(SHA-256, 200,000회)으로 Fernet 키 파생 (공통 로직)"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(material.encode("utf-8")))


def derive_key(salt: bytes | None = None) -> bytes:
    """하드웨어 ID 기반 Fernet 키 파생"""
    if salt is None:
        salt = _load_or_create_salt()
    return _derive_fernet_key(_get_hardware_id(), salt)


def derive_legacy_key(salt: bytes) -> bytes:
    """명시적 salt로 레거시 MAC 기반 키를 파생한다."""
    return _derive_fernet_key(_get_legacy_hardware_id(), salt)


_fernet_cache: Fernet | None = None
_legacy_fernet_cache: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet_cache
    if _fernet_cache is None:
        salt = _load_or_create_salt()
        key = derive_key(salt)
        _fernet_cache = Fernet(key)
    return _fernet_cache


def _get_legacy_fernet() -> Fernet:
    """기존 MAC 기반 키로 생성된 Fernet (마이그레이션용)"""
    global _legacy_fernet_cache
    if _legacy_fernet_cache is None:
        salt = _load_or_create_salt()
        key = _derive_fernet_key(_get_legacy_hardware_id(), salt)
        _legacy_fernet_cache = Fernet(key)
    return _legacy_fernet_cache


# ─── 암복호화 ──────────────────────────────────────────────────
def encrypt(plaintext: str) -> str:
    """평문 문자열을 Fernet(AES-128 CBC)으로 암호화 후 str 반환"""
    try:
        f = _get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    except (ValueError, TypeError, OSError) as e:
        audit("암호화 오류 발생", f"실패: {type(e).__name__}")
        raise


def decrypt(ciphertext: str) -> str:
    """암호화된 문자열을 복호화하여 평문 str 반환"""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (ValueError, TypeError, OSError) as e:
        audit("복호화 오류 발생", f"실패: {type(e).__name__}")
        raise


def legacy_decrypt(ciphertext: str) -> str:
    """기존 MAC 기반 키로 복호화 시도 (마이그레이션용)"""
    f = _get_legacy_fernet()
    return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")


# ─── PIN 기반 Export/Import 암복호화 ──────────────────────────
def _derive_pin_key(pin: str, salt: bytes | None = None) -> bytes:
    """4자리 PIN으로부터 Fernet 키 파생"""
    if salt is None:
        salt = _load_or_create_salt()
    return _derive_fernet_key(pin, salt)


def encrypt_with_pin(data: bytes, pin: str) -> bytes:
    """PIN으로 데이터 암호화 (Export용) — 포맷: [32B salt][Fernet 암호문]"""
    salt = _load_or_create_salt()
    key = _derive_pin_key(pin, salt)
    return salt + Fernet(key).encrypt(data)


def decrypt_with_pin(data: bytes, pin: str) -> bytes:
    """PIN으로 데이터 복호화 (Import용) — 앞 32바이트에서 salt 추출"""
    if len(data) < 32:
        raise ValueError("잘못된 내보내기 파일 형식입니다.")
    salt = data[:32]
    encrypted = data[32:]
    key = _derive_pin_key(pin, salt)
    return Fernet(key).decrypt(encrypted)


# ─── Salt 재생성 (Factory Reset 시 호출) ─────────────────────
def reset_salt() -> None:
    """Salt 파일 삭제 후 재생성, Fernet 캐시 무효화"""
    global _fernet_cache, _legacy_fernet_cache
    _fernet_cache = None
    _legacy_fernet_cache = None
    if SALT_FILE.exists():
        SALT_FILE.unlink()
    _load_or_create_salt()
