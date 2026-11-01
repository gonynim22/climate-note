import sqlite3
import json
import logging
import os
import tempfile
import hashlib
import shutil
import uuid
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
import security
from app_info import APP_VERSION
from schedule_rules import (
    AlarmItem, ScheduleOptions, alarm_times, occurrence_dates, occurrence_sort_key, iter_occurrence_dates,
    parse_date, validate_options,
)
from security import APP_DIR, encrypt, decrypt, legacy_decrypt, audit, validate_app_path

_logger = logging.getLogger("app_error")

DB_FILE = APP_DIR / "calendar.db"
EXPORT_FORMAT_VERSION = 4
CURRENT_SCHEMA_VERSION = 19
AUTO_BACKUP_FORMAT = "climatenote-auto-backup"
AUTO_BACKUP_FORMAT_VERSION = 1
AUTO_BACKUP_KEEP_DAYS = 5
_AUTO_BACKUP_KEY_CHECK = b"climatenote-auto-backup-v1"

# ─── 설정 키 상수 ──────────────────────────────────────────────
SETTING_PRIVACY_PIN = "privacy_pin"
SETTING_DESKTOP_MODE = "desktop_mode"
SETTING_USE_PRIVACY_LOCK = "use_privacy_lock"
SETTING_SHOW_LUNAR = "show_lunar"
# v4.6 공휴일 테마(화면 전용). 값 "1"/"0", 키가 없으면 켜짐으로 본다. 마이그레이션에 넣지 않는다.
SETTING_HOLIDAY_THEME_ENABLED = "holiday_theme_enabled"
SETTING_SHOW_LAW_SEARCH = "show_law_search"
SETTING_CALENDAR_X = "calendar_x"
SETTING_CALENDAR_Y = "calendar_y"
SETTING_CALENDAR_POSITION = "calendar_position"  # top-left, top-right, bottom-left, bottom-right
SETTING_TARGET_SCREEN = "target_screen"
SETTING_CALENDAR_SCREEN = "calendar_screen"  # 화면 식별 정보와 저장 당시 작업 영역 원점
SETTING_SHOW_SIDEBAR = "show_sidebar"
SETTING_APP_FONT = "app_font"
SETTING_APP_OPACITY = "app_opacity"          # 전체 창 투명도 "30"~"100" (v3.0)
SETTING_CALENDAR_SCALE = "calendar_scale"    # compact / medium / large (v3.0)
SETTING_KEEP_ON_SHOW_DESKTOP = "keep_on_show_desktop"  # Win+D/모두최소화에도 유지 "1"/"0"
SETTING_CALENDAR_POSITION_MODE = "calendar_position_mode"  # corner / free (v3.3)
SETTING_CALENDAR_MOVE_ENABLED = "calendar_move_enabled"  # v3.9a J안부터 읽지 않음. 기존 행·Export 값은 보존
SETTING_SCHEDULE_ALARM_SEEN_AT = "schedule_alarm_seen_at"  # v4.1: 여기까지의 알림은 처리함(Export 제외)
# Export에 넣지 않고 Import에서도 쓰지 않는 설정(평문 PIN, 이 PC의 알림 처리 시각)
EXPORT_EXCLUDED_SETTINGS = frozenset({SETTING_PRIVACY_PIN, SETTING_SCHEDULE_ALARM_SEEN_AT})

# v4.1(DB v18): 일정 표에 열만 더한다. 이름 → 고정 SQL(외부 값이 섞이지 않는 상수).
SCHEDULE_V18_COLUMNS = (
    ("start_time", "ALTER TABLE schedules ADD COLUMN start_time TEXT NOT NULL DEFAULT ''"),
    ("end_date", "ALTER TABLE schedules ADD COLUMN end_date TEXT NOT NULL DEFAULT ''"),
    ("repeat_rule", "ALTER TABLE schedules ADD COLUMN repeat_rule TEXT NOT NULL DEFAULT ''"),
    ("repeat_until", "ALTER TABLE schedules ADD COLUMN repeat_until TEXT NOT NULL DEFAULT ''"),
    ("repeat_skip", "ALTER TABLE schedules ADD COLUMN repeat_skip TEXT NOT NULL DEFAULT ''"),
    ("alarm_before", "ALTER TABLE schedules ADD COLUMN alarm_before INTEGER"),
)
SCHEDULE_V19_COLUMNS = (
    ("series_id", "ALTER TABLE schedules ADD COLUMN series_id INTEGER"),
    ("original_date", "ALTER TABLE schedules ADD COLUMN original_date TEXT NOT NULL DEFAULT ''"),
)
SETTING_SCHEDULE_COLOR_1 = "schedule_color_1"
SETTING_SCHEDULE_COLOR_2 = "schedule_color_2"
SETTING_SCHEDULE_COLOR_3 = "schedule_color_3"


DEFAULT_APP_FONT = "Malgun Gothic"
DEFAULT_APP_OPACITY = "100"
DEFAULT_CALENDAR_SCALE = "compact"
DEFAULT_KEEP_ON_SHOW_DESKTOP = "1"
DEFAULT_CALENDAR_POSITION_MODE = "corner"
MIN_APP_OPACITY = 30
CALENDAR_SCALES = ("compact", "medium", "large")
DEFAULT_STICKY_COLOR = "#FFFA8E"
STICKY_TRASH_LIMIT = 50  # 휴지통 최대 보관 개수(초과 시 오래된 것부터 자동 영구삭제)
DEFAULT_DDAY_COLOR = "#C4D5FF"
DEFAULT_FOCUS_MODE = "25/5"
DEFAULT_SCHEDULE_COLOR = "#FFD166"
SCHEDULE_COLORS = [
    ("#FFD166", "노랑"),
    ("#4CC9F0", "파랑"),
    ("#FF6B6B", "빨강"),
]
# 일정 행에는 아래 3개 canonical 색상만 저장한다. 사용자 설정은 표시색만
# 바꾸며 기존 schedules.color 값을 갱신하지 않는다(구버전/Export 호환 보존).
SCHEDULE_COLOR_SLOTS = tuple(color for color, _name in SCHEDULE_COLORS)
SCHEDULE_COLOR_OPTIONS = (
    ("#FFD166", "노랑"),
    ("#4CC9F0", "하늘"),
    ("#FF6B6B", "코랄"),
    ("#FF9F68", "주황"),
    ("#80CFA9", "초록"),
    ("#62CBBF", "민트"),
    ("#8FA8FF", "인디고"),
    ("#B197FC", "보라"),
    ("#F28BB5", "분홍"),
    ("#AAB4C3", "회색"),
)
SCHEDULE_COLOR_SETTING_KEYS = (
    SETTING_SCHEDULE_COLOR_1,
    SETTING_SCHEDULE_COLOR_2,
    SETTING_SCHEDULE_COLOR_3,
)
DEFAULT_SCHEDULE_PALETTE = SCHEDULE_COLOR_SLOTS
FOCUS_MODES = {
    "25/5": ("짧은 집중", 25, 5),
    "50/10": ("깊은 집중", 50, 10),
    "75/15": ("몰입 블록", 75, 15),
}


# ─── 헬퍼 ─────────────────────────────────────────────────────
def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_decrypt_with_status(
        ciphertext: str, fallback: str = ""
) -> tuple[str, bool]:
    """복호화 결과와 실패 여부를 함께 반환한다."""
    if not ciphertext:
        return "", False
    try:
        return decrypt(ciphertext), False
    except (InvalidToken, ValueError, TypeError):
        try:
            return legacy_decrypt(ciphertext), False
        except (InvalidToken, ValueError, TypeError):
            return fallback, True


def _safe_decrypt(ciphertext: str, fallback: str = "") -> str:
    """복호화 시도 (새 키 → 구 키 순), 실패 시 fallback 반환"""
    return _safe_decrypt_with_status(ciphertext, fallback)[0]


def _decrypt_for_export(ciphertext: str, table: str, row_id: int) -> str:
    """Export에서는 복호화 실패를 숨기지 않고 전체 작업을 중단한다."""
    if not ciphertext:
        return ""
    try:
        return decrypt(ciphertext)
    except (InvalidToken, ValueError, TypeError):
        try:
            return legacy_decrypt(ciphertext)
        except (InvalidToken, ValueError, TypeError) as exc:
            _logger.error("Export 복호화 실패: %s id=%s", table, row_id)
            raise ValueError(
                f"내보내기 중 {table} id={row_id} 데이터 복호화에 실패했습니다."
            ) from exc


# ─── DB 연결 ──────────────────────────────────────────────────
def _connect(
        db_file: Path | None = None, *, enable_wal: bool = True,
        read_only: bool = False,
) -> sqlite3.Connection:
    resolved = validate_app_path(
        DB_FILE if db_file is None else Path(db_file), "DB"
    )
    if read_only:
        conn = sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro", uri=True, timeout=5
        )
        conn.execute("PRAGMA query_only = ON")
    else:
        conn = sqlite3.connect(str(resolved), timeout=5)
    if enable_wal and not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _connection(
        db_file: Path | None = None, *, enable_wal: bool = True,
        read_only: bool = False,
):
    conn = _connect(
        db_file, enable_wal=enable_wal, read_only=read_only
    )
    try:
        yield conn
    finally:
        conn.close()


@dataclass(frozen=True)
class DataHealthReport:
    ok: bool
    code: str
    version: int = 0
    encrypted_count: int = 0
    failed_count: int = 0
    legacy_count: int = 0
    failed_locations: tuple[str, ...] = ()


class DataHealthError(RuntimeError):
    def __init__(self, report: DataHealthReport):
        super().__init__(f"데이터 건강 검사 실패: {report.code}")
        self.report = report


# 보호 표·열 구조를 검사하는 가장 낮은 DB 버전. v17부터 모든 보호 표가 있으며(v4.0a는 v17에서
# 검사했다), CURRENT_SCHEMA_VERSION이 올라가도 v17 DB의 검사가 빠지지 않게 고정한다.
_STRUCTURE_CHECKED_FROM = 17
_PROTECTED_COLUMNS = (
    ("schedules", "content"),
    ("memos", "content"),
    ("sticky_notes", "content"),
    ("dday_widgets", "name"),
    ("focus_widgets", "goal"),
    ("focus_sessions", "goal"),
)


def inspect_startup_data_health() -> DataHealthReport:
    """기존 DB를 변경하지 않고 구조와 암호문 복호화 가능성을 검사한다."""
    if not DB_FILE.exists():
        sidecars = (
            DB_FILE.with_name(f"{DB_FILE.name}-wal"),
            DB_FILE.with_name(f"{DB_FILE.name}-shm"),
        )
        backup_dir = APP_DIR / "backups"
        has_backup = backup_dir.exists() and any(
            backup_dir.glob("calendar_*")
        )
        if (
            security.SALT_FILE.exists()
            or any(path.exists() for path in sidecars)
            or has_backup
        ):
            return DataHealthReport(False, "incomplete_dataset")
        return DataHealthReport(True, "fresh")

    encrypted_rows: list[tuple[str, int, str]] = []
    try:
        with _connection(enable_wal=False, read_only=True) as conn:
            conn.execute("BEGIN")
            checks = [
                row[0] for row in conn.execute("PRAGMA integrity_check")
            ]
            if checks != ["ok"]:
                return DataHealthReport(False, "database_invalid")

            version = int(
                conn.execute("PRAGMA user_version").fetchone()[0]
            )
            if version > CURRENT_SCHEMA_VERSION:
                return DataHealthReport(False, "schema_newer", version)
            if version <= 0:
                return DataHealthReport(False, "schema_invalid", version)

            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if version >= _STRUCTURE_CHECKED_FROM:
                required = {table for table, _column in _PROTECTED_COLUMNS}
                if not required.issubset(tables):
                    return DataHealthReport(
                        False, "schema_invalid", version
                    )
            if version >= 18 and "schedules" in tables:
                schedule_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(schedules)")
                }
                if not {name for name, _sql in SCHEDULE_V18_COLUMNS} <= schedule_columns:
                    return DataHealthReport(False, "schema_invalid", version)
                if version >= 19:
                    if not {name for name, _sql in SCHEDULE_V19_COLUMNS} <= schedule_columns:
                        return DataHealthReport(False, "schema_invalid", version)
                    try:
                        _validate_schedule_links(conn.execute("SELECT * FROM schedules").fetchall())
                    except ValueError:
                        return DataHealthReport(False, "schema_invalid", version)

            for table, column in _PROTECTED_COLUMNS:
                if table not in tables:
                    continue
                columns = {
                    row[1] for row in conn.execute(
                        f"PRAGMA table_info({table})"
                    )
                }
                if "id" not in columns or column not in columns:
                    if version >= _STRUCTURE_CHECKED_FROM:
                        return DataHealthReport(
                            False, "schema_invalid", version
                        )
                    continue
                for row in conn.execute(
                    f"SELECT id, {column} FROM {table}"  # noqa: S608
                ):
                    ciphertext = row[column]
                    if ciphertext:
                        encrypted_rows.append(
                            (table, int(row["id"]), ciphertext)
                        )
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return DataHealthReport(False, "database_invalid")

    if not encrypted_rows:
        if security.SALT_FILE.exists():
            try:
                security.read_existing_salt()
            except (OSError, ValueError):
                return DataHealthReport(
                    False, "salt_invalid", version=version
                )
        return DataHealthReport(
            True, "healthy", version=version, encrypted_count=0
        )

    try:
        salt = security.read_existing_salt()
    except FileNotFoundError:
        return DataHealthReport(
            False, "salt_missing", version, len(encrypted_rows)
        )
    except (OSError, ValueError):
        return DataHealthReport(
            False, "salt_invalid", version, len(encrypted_rows)
        )

    current_fernet = Fernet(security.derive_key(salt))
    legacy_fernet = Fernet(security.derive_legacy_key(salt))
    failed_locations: list[str] = []
    legacy_count = 0
    total_failed = 0
    for table, row_id, ciphertext in encrypted_rows:
        try:
            current_fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
            continue
        except (InvalidToken, UnicodeError, ValueError, TypeError):
            pass
        try:
            legacy_fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
            legacy_count += 1
        except (InvalidToken, UnicodeError, ValueError, TypeError):
            total_failed += 1
            if len(failed_locations) < 5:
                failed_locations.append(f"{table}:{row_id}")

    if total_failed:
        return DataHealthReport(
            False,
            "decrypt_failed",
            version,
            len(encrypted_rows),
            total_failed,
            legacy_count,
            tuple(failed_locations),
        )

    return DataHealthReport(
        True,
        "healthy",
        version,
        len(encrypted_rows),
        0,
        legacy_count,
    )


def normalize_schedule_palette(values) -> tuple[str, str, str]:
    """설정값을 허용된 서로 다른 3색으로 보정하되 DB에는 쓰지 않는다."""
    allowed = {
        color.upper(): color
        for color, _name in SCHEDULE_COLOR_OPTIONS
    }
    raw_values = list(values)
    normalized: list[str] = []
    for index, fallback in enumerate(DEFAULT_SCHEDULE_PALETTE):
        raw = raw_values[index] if index < len(raw_values) else fallback
        color = allowed.get(str(raw).strip().upper())
        if color is None or color in normalized:
            color = fallback
        if color in normalized:
            color = next(
                option
                for option, _name in SCHEDULE_COLOR_OPTIONS
                if option not in normalized
            )
        normalized.append(color)
    return tuple(normalized)


def get_schedule_palette() -> tuple[str, str, str]:
    """현재 일정 3슬롯의 표시색을 반환한다. 누락/손상 설정은 기본값으로 보정한다."""
    placeholders = ", ".join("?" for _key in SCHEDULE_COLOR_SETTING_KEYS)
    with _connection() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
            SCHEDULE_COLOR_SETTING_KEYS,
        ).fetchall()
    stored = {row["key"]: row["value"] for row in rows}
    return normalize_schedule_palette(
        stored.get(key, fallback)
        for key, fallback in zip(SCHEDULE_COLOR_SETTING_KEYS, DEFAULT_SCHEDULE_PALETTE)
    )


def save_schedule_palette(colors) -> None:
    """서로 다른 허용색 3개를 하나의 트랜잭션으로 저장한다."""
    values = tuple(str(color).strip().upper() for color in colors)
    allowed = {color for color, _name in SCHEDULE_COLOR_OPTIONS}
    if len(values) != len(SCHEDULE_COLOR_SLOTS):
        raise ValueError("일정 색상은 정확히 3개여야 합니다.")
    if len(set(values)) != len(values) or any(color not in allowed for color in values):
        raise ValueError("일정 색상은 허용된 서로 다른 3색이어야 합니다.")

    with _connection() as conn:
        for key, color in zip(SCHEDULE_COLOR_SETTING_KEYS, values):
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, color),
            )
        conn.commit()


def schedule_display_color(stored_color: str, palette=None) -> str:
    """DB canonical 슬롯 색상을 사용자 표시색으로 변환한다.

    팔레트 밖의 기존/가져온 커스텀 색상은 원문 그대로 반환해 데이터 의미를
    보존한다. ``None``/빈 값은 첫 번째 canonical 슬롯으로 취급한다.
    """
    raw = stored_color or DEFAULT_SCHEDULE_COLOR
    normalized = str(raw).strip().upper()
    slot_lookup = {
        color.upper(): index
        for index, color in enumerate(SCHEDULE_COLOR_SLOTS)
    }
    slot_index = slot_lookup.get(normalized)
    if slot_index is None:
        return raw
    display_palette = (
        get_schedule_palette()
        if palette is None
        else normalize_schedule_palette(palette)
    )
    return display_palette[slot_index]


# ─── 암호화 키 마이그레이션 (MAC → MachineGuid) ────────────────
def _try_migrate_encryption() -> None:
    """구 키(MAC 기반)로 암호화된 데이터를 새 키(MachineGuid 기반)로 재암호화"""
    migrated = 0
    skipped = 0
    try:
        with _connection() as conn:
            # schedules
            for row in conn.execute("SELECT id, content FROM schedules").fetchall():
                if not row["content"]:
                    continue
                try:
                    decrypt(row["content"])  # 새 키로 복호화 성공 → 이미 마이그레이션됨
                except (InvalidToken, ValueError, TypeError):
                    try:
                        plaintext = legacy_decrypt(row["content"])  # 구 키로 복호화 시도
                        conn.execute(
                            "UPDATE schedules SET content = ? WHERE id = ?",
                            (encrypt(plaintext), row["id"])
                        )
                        migrated += 1
                    except (InvalidToken, ValueError, TypeError):
                        skipped += 1
                        _logger.warning("암호화 마이그레이션 실패: schedules id=%s", row["id"])

            # memos
            for row in conn.execute("SELECT id, content FROM memos").fetchall():
                if not row["content"]:
                    continue
                try:
                    decrypt(row["content"])
                except (InvalidToken, ValueError, TypeError):
                    try:
                        plaintext = legacy_decrypt(row["content"])
                        conn.execute(
                            "UPDATE memos SET content = ? WHERE id = ?",
                            (encrypt(plaintext), row["id"])
                        )
                        migrated += 1
                    except (InvalidToken, ValueError, TypeError):
                        skipped += 1
                        _logger.warning("암호화 마이그레이션 실패: memos id=%s", row["id"])

            # sticky_notes
            for row in conn.execute("SELECT id, content FROM sticky_notes").fetchall():
                if not row["content"]:
                    continue
                try:
                    decrypt(row["content"])
                except (InvalidToken, ValueError, TypeError):
                    try:
                        plaintext = legacy_decrypt(row["content"])
                        conn.execute(
                            "UPDATE sticky_notes SET content = ? WHERE id = ?",
                            (encrypt(plaintext), row["id"])
                        )
                        migrated += 1
                    except (InvalidToken, ValueError, TypeError):
                        skipped += 1
                        _logger.warning("암호화 마이그레이션 실패: sticky_notes id=%s", row["id"])

            # dday_widgets
            for row in conn.execute("SELECT id, name FROM dday_widgets").fetchall():
                if not row["name"]:
                    continue
                try:
                    decrypt(row["name"])
                except (InvalidToken, ValueError, TypeError):
                    try:
                        plaintext = legacy_decrypt(row["name"])
                        conn.execute(
                            "UPDATE dday_widgets SET name = ? WHERE id = ?",
                            (encrypt(plaintext), row["id"])
                        )
                        migrated += 1
                    except (InvalidToken, ValueError, TypeError):
                        skipped += 1
                        _logger.warning("암호화 마이그레이션 실패: dday_widgets id=%s", row["id"])

            # focus_widgets
            try:
                focus_rows = conn.execute("SELECT id, goal FROM focus_widgets").fetchall()
            except sqlite3.Error:
                focus_rows = []
            for row in focus_rows:
                if not row["goal"]:
                    continue
                try:
                    decrypt(row["goal"])
                except (InvalidToken, ValueError, TypeError):
                    try:
                        plaintext = legacy_decrypt(row["goal"])
                        conn.execute(
                            "UPDATE focus_widgets SET goal = ? WHERE id = ?",
                            (encrypt(plaintext), row["id"])
                        )
                        migrated += 1
                    except (InvalidToken, ValueError, TypeError):
                        skipped += 1
                        _logger.warning("암호화 마이그레이션 실패: focus_widgets id=%s", row["id"])

            # focus_sessions
            try:
                session_rows = conn.execute("SELECT id, goal FROM focus_sessions").fetchall()
            except sqlite3.Error:
                session_rows = []
            for row in session_rows:
                if not row["goal"]:
                    continue
                try:
                    decrypt(row["goal"])
                except (InvalidToken, ValueError, TypeError):
                    try:
                        plaintext = legacy_decrypt(row["goal"])
                        conn.execute(
                            "UPDATE focus_sessions SET goal = ? WHERE id = ?",
                            (encrypt(plaintext), row["id"])
                        )
                        migrated += 1
                    except (InvalidToken, ValueError, TypeError):
                        skipped += 1
                        _logger.warning("암호화 마이그레이션 실패: focus_sessions id=%s", row["id"])

            if migrated > 0:
                conn.commit()
                audit("암호화 키 마이그레이션", f"성공: {migrated}건 재암호화")
            if skipped > 0:
                audit("암호화 키 마이그레이션", f"복호화 불가 {skipped}건 건너뜀")
    except (sqlite3.Error, OSError) as e:
        audit("암호화 키 마이그레이션", f"실패: {e}")


# ─── 스키마 마이그레이션 ───────────────────────────────────────
def migrate(*, initial_calendar_scale: str | None = None) -> None:
    """PRAGMA user_version으로 스키마 버전 관리"""
    if initial_calendar_scale is not None and initial_calendar_scale not in CALENDAR_SCALES:
        raise ValueError("지원하지 않는 최초 캘린더 크기입니다.")
    is_new_database = not DB_FILE.exists()
    with _connection() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        if version == 0:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    color      TEXT DEFAULT '#FFD166'
                );
                CREATE TABLE IF NOT EXISTS memos (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sticky_notes (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    type      TEXT NOT NULL DEFAULT 'memo',
                    content   TEXT NOT NULL DEFAULT '',
                    x_pos     INTEGER NOT NULL DEFAULT 100,
                    y_pos     INTEGER NOT NULL DEFAULT 100,
                    width     INTEGER NOT NULL DEFAULT 300,
                    height    INTEGER NOT NULL DEFAULT 400,
                    is_open   INTEGER NOT NULL DEFAULT 1,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    color     TEXT DEFAULT '#FFFDD2'
                );
                CREATE TABLE IF NOT EXISTS dday_widgets (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    x_pos       INTEGER NOT NULL DEFAULT 100,
                    y_pos       INTEGER NOT NULL DEFAULT 100,
                    is_open     INTEGER NOT NULL DEFAULT 1,
                    color       TEXT DEFAULT '#D6EEFF'
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL
                );
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('privacy_pin', '0000');
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('desktop_mode', '0');
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('show_law_search', '1');
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('app_font', 'Malgun Gothic');
            """)
            if is_new_database and initial_calendar_scale is not None:
                # 새 설치(처음 실행 크기 선택)·초기화의 기본값. 바로가기 사이드바는 켜짐(2026-10-11)이며,
                # 아래 v9의 INSERT OR IGNORE '0'은 이미 있는 이 행을 덮지 않는다. 기존 DB 값은 그대로 둔다.
                conn.executemany(
                    "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                    ((SETTING_CALENDAR_SCALE, initial_calendar_scale), (SETTING_SHOW_SIDEBAR, "1")),
                )
            conn.execute("PRAGMA user_version = 8")
            conn.commit()
            version = 8

        if version == 1:
            conn.execute(
                "ALTER TABLE sticky_notes ADD COLUMN color TEXT DEFAULT '#FFFDD2'"
            )
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
            version = 2

        if version == 2:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL
                );
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('privacy_pin', '0000');
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('desktop_mode', '0');
            """)
            conn.execute("PRAGMA user_version = 3")
            conn.commit()
            version = 3

        if version == 3:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('use_privacy_lock', '0')"
            )
            conn.execute("PRAGMA user_version = 4")
            conn.commit()
            version = 4

        if version == 4:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('show_lunar', '0')"
            )
            conn.execute("PRAGMA user_version = 5")
            conn.commit()
            version = 5

        if version == 5:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('show_law_search', '1')"
            )
            conn.execute("PRAGMA user_version = 6")
            conn.commit()
            version = 6

        if version == 6:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dday_widgets (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    x_pos       INTEGER NOT NULL DEFAULT 100,
                    y_pos       INTEGER NOT NULL DEFAULT 100,
                    is_open     INTEGER NOT NULL DEFAULT 1,
                    color       TEXT DEFAULT '#D6EEFF'
                )
            """)
            conn.execute("PRAGMA user_version = 7")
            conn.commit()
            version = 7

        if version == 7:
            conn.execute(
                "ALTER TABLE schedules ADD COLUMN color TEXT DEFAULT '#FFD166'"
            )
            conn.execute("PRAGMA user_version = 8")
            conn.commit()
            version = 8

        if version == 8:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS shortcuts (
                    id   INTEGER PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT ''
                );
                INSERT OR IGNORE INTO shortcuts (id, name, path) VALUES (1, '', '');
                INSERT OR IGNORE INTO shortcuts (id, name, path) VALUES (2, '', '');
                INSERT OR IGNORE INTO shortcuts (id, name, path) VALUES (3, '', '');
                INSERT OR IGNORE INTO shortcuts (id, name, path) VALUES (4, '', '');
                INSERT OR IGNORE INTO shortcuts (id, name, path) VALUES (5, '', '');
                INSERT OR IGNORE INTO app_settings (key, value) VALUES ('show_sidebar', '0');
            """)
            conn.execute("PRAGMA user_version = 9")
            conn.commit()
            version = 9

        if version == 9:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('app_font', 'Malgun Gothic')"
            )
            conn.execute("PRAGMA user_version = 10")
            conn.commit()
            version = 10

        if version == 10:
            conn.execute(
                """
                UPDATE app_settings
                   SET value = ?
                 WHERE key = ?
                   AND value IN ('Pretendard', 'Pretendard Variable', 'Noto Sans KR')
                """,
                (DEFAULT_APP_FONT, SETTING_APP_FONT),
            )
            conn.execute("PRAGMA user_version = 11")
            conn.commit()
            version = 11

        if version == 11:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS focus_widgets (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal          TEXT NOT NULL DEFAULT '',
                    mode_key      TEXT NOT NULL DEFAULT '25/5',
                    focus_minutes INTEGER NOT NULL DEFAULT 25,
                    break_minutes INTEGER NOT NULL DEFAULT 5,
                    x_pos         INTEGER NOT NULL DEFAULT 160,
                    y_pos         INTEGER NOT NULL DEFAULT 160,
                    is_open       INTEGER NOT NULL DEFAULT 1,
                    is_pinned     INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS focus_sessions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    widget_id       INTEGER,
                    goal            TEXT NOT NULL DEFAULT '',
                    mode_key        TEXT NOT NULL DEFAULT '25/5',
                    focus_minutes   INTEGER NOT NULL DEFAULT 25,
                    break_minutes   INTEGER NOT NULL DEFAULT 5,
                    started_at      TEXT NOT NULL,
                    ended_at        TEXT NOT NULL,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    completed       INTEGER NOT NULL DEFAULT 0,
                    focus_rating    INTEGER,
                    distraction     TEXT NOT NULL DEFAULT '없음',
                    created_at      TEXT NOT NULL
                );
            """)
            conn.execute("PRAGMA user_version = 12")
            conn.commit()
            version = 12

        if version == 12:
            # 스티키 노트 휴지통(soft-delete) 컬럼 추가
            conn.execute(
                "ALTER TABLE sticky_notes ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                "ALTER TABLE sticky_notes ADD COLUMN deleted_at TEXT NOT NULL DEFAULT ''"
            )
            conn.execute("PRAGMA user_version = 13")
            conn.commit()
            version = 13

        if version == 13:
            # v3.0: 전체 투명도 + 확장 캘린더 크기 설정 추가 (스키마 변경 없음, 멱등)
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (SETTING_APP_OPACITY, DEFAULT_APP_OPACITY),
            )
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (SETTING_CALENDAR_SCALE, DEFAULT_CALENDAR_SCALE),
            )
            conn.execute("PRAGMA user_version = 14")
            conn.commit()
            version = 14

        if version == 14:
            # v3.1: 바로가기 6번째 슬롯 시드 (멱등, 기존 1~5 보존)
            conn.execute(
                "INSERT OR IGNORE INTO shortcuts (id, name, path) VALUES (6, '', '')"
            )
            conn.execute("PRAGMA user_version = 15")
            conn.commit()
            version = 15

        if version == 15:
            # 바탕화면 유지(Win+D/모두최소화 면역) 설정 추가 (스키마 변경 없음, 멱등)
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (SETTING_KEEP_ON_SHOW_DESKTOP, DEFAULT_KEEP_ON_SHOW_DESKTOP),
            )
            conn.execute("PRAGMA user_version = 16")
            conn.commit()
            version = 16

        if version == 16:
            # v3.3: 일정 3슬롯 표시색 + 캘린더 위치 모드.
            # 기존 schedules 행은 건드리지 않고 설정 기본값만 멱등하게 시드한다.
            for key, color in zip(
                SCHEDULE_COLOR_SETTING_KEYS, DEFAULT_SCHEDULE_PALETTE
            ):
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                    (key, color),
                )
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                (SETTING_CALENDAR_POSITION_MODE, DEFAULT_CALENDAR_POSITION_MODE),
            )
            conn.execute("PRAGMA user_version = 17")
            conn.commit()
            version = 17

        if version == 17:
            # v4.1: 일정 시각·기간·반복·알림 열 추가. 기존 행의 값은 읽거나 쓰지 않는다.
            # 열 추가와 버전 표시를 한 트랜잭션으로 묶어 중간에 실패하면 모두 되돌린다.
            if conn.in_transaction:
                conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = {row[1] for row in conn.execute("PRAGMA table_info(schedules)")}
                for name, statement in SCHEDULE_V18_COLUMNS:
                    if name not in existing:
                        conn.execute(statement)
                conn.execute("PRAGMA user_version = 18")
                conn.execute("COMMIT")
            except sqlite3.Error:
                # 디스크 가득 참·I/O 오류 등은 SQLite가 스스로 되돌린다. 그때 ROLLBACK을 또 하면
                # "no transaction is active"가 진짜 오류를 가리므로, 열려 있을 때만 되돌린다.
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            version = 18

        if version == 18:
            # 연결 열만 추가한다. 기존 본문·옵션·ID는 읽거나 다시 쓰지 않는다.
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = {row[1] for row in conn.execute("PRAGMA table_info(schedules)")}
                for name, statement in SCHEDULE_V19_COLUMNS:
                    if name not in existing:
                        conn.execute(statement)
                conn.execute("PRAGMA user_version = 19")
                conn.execute("COMMIT")
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    # 암호화 키 마이그레이션 (MAC → MachineGuid)
    _try_migrate_encryption()


# ─── schedules CRUD ───────────────────────────────────────────
_SCHEDULE_SELECT = (
    "SELECT id, date, content, created_at, color, start_time, end_date, "
    "repeat_rule, repeat_until, repeat_skip, alarm_before, series_id, original_date FROM schedules "
)
_SCHEDULE_INSERT = (
    "INSERT INTO schedules (date, content, created_at, color, start_time, end_date, "
    "repeat_rule, repeat_until, repeat_skip, alarm_before) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _decrypt_schedule(ciphertext: str) -> tuple[str, bool]:
    """일정 본문 복호화(구 키 재시도). 실패하면 ('[복호화 오류]', True)."""
    return _safe_decrypt_with_status(ciphertext, "[복호화 오류]")


def _validate_schedule_links(rows, *, id_field="id", parent_field="series_id") -> None:
    """DB 건강 검사와 v4 Import가 공유하는 수정 회차 관계 계약."""
    by_id = {}
    for row in rows:
        sid = row[id_field]
        if type(sid) is not int or sid <= 0 or sid in by_id:
            raise ValueError("일정 ID가 올바르지 않습니다.")
        by_id[sid] = row
    pairs = set()
    for row in rows:
        parent_id = row[parent_field]
        original = row["original_date"]
        if parent_id is None:
            if original != "":
                raise ValueError("일반 일정에 수정 회차 날짜가 있습니다.")
            continue
        if type(parent_id) is not int or parent_id not in by_id or parent_id == row[id_field]:
            raise ValueError("수정 회차의 원본이 올바르지 않습니다.")
        parent = by_id[parent_id]
        if parent[parent_field] is not None or not parent["repeat_rule"]:
            raise ValueError("수정 회차의 원본은 반복 일정이어야 합니다.")
        validate_options(parent["date"], ScheduleOptions(repeat_rule=parent["repeat_rule"], end_date=parent["end_date"]))
        if original != row["date"] or parse_date(original) < parse_date(parent["date"]):
            raise ValueError("수정 회차 날짜가 올바르지 않습니다.")
        if any(row[field] for field in ("end_date", "repeat_rule", "repeat_until", "repeat_skip")):
            raise ValueError("수정 회차에는 반복·기간을 지정할 수 없습니다.")
        validate_options(original, ScheduleOptions(start_time=row["start_time"], alarm_before=row["alarm_before"]))
        pair = (parent_id, original)
        if pair in pairs:
            raise ValueError("같은 날짜의 수정 회차가 중복되었습니다.")
        pairs.add(pair)


def _candidate_rows(conn, first: str, last: str, extra: str = "") -> list:
    """[first, last]에 나타날 수 있는 행만 고른다(펼치기는 schedule_rules가 한다).

    extra는 코드에 적힌 고정 SQL 조건만 받는다(사용자 입력을 넣지 않는다).
    """
    where = "WHERE date <= ? AND (date >= ? OR end_date >= ? OR repeat_rule != '')"
    if extra:
        where += " AND " + extra
    return conn.execute(
        _SCHEDULE_SELECT + where + " ORDER BY id ASC", (last, first, first)
    ).fetchall()


def _occurrence_days(row, first: str, last: str, window) -> tuple[ScheduleOptions, list[str]]:
    """(이 행에 실제로 쓸 세부 설정, 나타나는 날 목록).

    window는 (first, last)를 날짜로 파싱한 쌍이고, 조회 날짜 형식이 ISO가 아니면 None이다.
    펼칠 수 없는 행은 자기 날짜 하루로만 보이며 기간·반복을 내세우지 않는다.
    """
    options = ScheduleOptions.from_row(row)
    # 저장된 문자열 그대로 비교한다(형식이 조금 다른 옛 날짜도 지금처럼 동작).
    single = [row["date"]] if first <= row["date"] <= last else []
    if not options.end_date and not options.repeat_rule:
        return options, single
    if window is None:
        # ISO가 아닌 조회(옛 형식 날짜 검색 등)에는 반복·기간을 펼칠 수 없으니 조용히 건너뛴다.
        return options, []
    try:
        found = occurrence_dates(row["date"], options, *window)
    except ValueError as exc:
        _logger.warning("일정 반복·기간 해석 실패 (id=%s): %s", row["id"], exc)
        plain = replace(options, end_date="", repeat_rule="", repeat_until="", repeat_skip=())
        return plain, single
    return options, [day.isoformat() for day in found]


def _schedule_entry(row, day: str, options: ScheduleOptions, content: str, failed: bool) -> dict:
    is_period = bool(options.end_date)
    return {
        "id": row["id"],
        "date": row["date"],
        "content": content,
        "created_at": row["created_at"],
        "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
        "_decryption_failed": failed,
        "options": options,
        "occurrence_date": day,
        # 기간은 전체 범위, 하루·반복은 그 날 하루가 이 항목의 범위다.
        "span_start": row["date"] if is_period else day,
        "span_end": options.end_date if is_period else day,
        "start_time": options.start_time,
        # 기간은 첫날에만 시각을 보이고, 반복은 나타나는 날마다 보인다.
        "shows_time": bool(options.start_time) and (not is_period or day == row["date"]),
        "series_id": row["series_id"] or (row["id"] if options.repeat_rule else None),
        "is_override": row["series_id"] is not None,
    }


def _expand_rows(rows, first: str, last: str) -> dict[str, list[dict]]:
    try:
        window = (parse_date(first), parse_date(last))
    except ValueError:
        window = None
    result: dict[str, list[dict]] = {}
    overridden = {(row["series_id"], row["original_date"]) for row in rows if row["series_id"] is not None}
    for row in rows:
        options, found = _occurrence_days(row, first, last, window)
        if not found:
            continue
        content, failed = _decrypt_schedule(row["content"])
        for day in found:
            if (row["id"], day) in overridden:
                continue
            result.setdefault(day, []).append(_schedule_entry(row, day, options, content, failed))
    for entries in result.values():
        entries.sort(key=lambda e: occurrence_sort_key(e["shows_time"], e["start_time"], e["id"]))
    return result


def get_schedules(date: str) -> list[dict]:
    """그 날 나타나는 일정(하루·기간·반복)을 순서대로 반환한다(복호화)."""
    with _connection() as conn:
        rows = _candidate_rows(conn, date, date)
    return _expand_rows(rows, date, date).get(date, [])


def get_occurrences(start: str, end: str) -> dict[str, list[dict]]:
    """[start, end] 날짜마다 나타나는 일정(달력 한 화면용, 정렬·복호화)."""
    with _connection() as conn:
        rows = _candidate_rows(conn, start, end)
    return _expand_rows(rows, start, end)


def get_schedule(schedule_id: int) -> dict:
    """전체 편집은 현재 표시 회차 대신 원본 행의 본문·옵션을 읽는다."""
    with _connection() as conn:
        row = conn.execute(_SCHEDULE_SELECT + "WHERE id = ?", (schedule_id,)).fetchone()
    if row is None:
        raise ValueError("일정이 없습니다.")
    content, failed = _decrypt_schedule(row["content"])
    return _schedule_entry(row, row["date"], ScheduleOptions.from_row(row), content, failed)


def get_all_schedule_dates() -> set[str]:
    """원본 시작일 기준 날짜 목록(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    with _connection() as conn:
        rows = conn.execute("SELECT DISTINCT date FROM schedules").fetchall()
        return {row["date"] for row in rows}


def get_all_schedule_date_colors() -> dict[str, list[str]]:
    """원본 시작일 기준 날짜별 고유 색(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    with _connection() as conn:
        rows = conn.execute("SELECT date, color FROM schedules").fetchall()
        result: dict[str, set[str]] = {}
        for row in rows:
            color = row["color"] or DEFAULT_SCHEDULE_COLOR
            result.setdefault(row["date"], set()).add(color)
        color_order = {c[0]: i for i, c in enumerate(SCHEDULE_COLORS)}
        return {
            date: sorted(colors, key=lambda c: color_order.get(c, 99))
            for date, colors in result.items()
        }


def get_all_schedule_date_counts() -> dict[str, int]:
    """원본 시작일 기준 날짜별 일정 수(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT date, COUNT(*) AS n FROM schedules GROUP BY date"
        ).fetchall()
        return {row["date"]: row["n"] for row in rows}


def get_schedules_for_month(year: int, month: int) -> dict[str, list[dict]]:
    """원본 시작일 기준 그 달 일정(반복·기간 미전개). 화면은 get_occurrences를 쓴다."""
    month_prefix = f"{year:04d}-{month:02d}-"
    with _connection() as conn:
        rows = conn.execute(
            "SELECT date, content, color FROM schedules "
            "WHERE date LIKE ? ORDER BY date ASC, id ASC",
            (f"{month_prefix}%",),
        ).fetchall()
        result: dict[str, list[dict]] = {}
        for row in rows:
            result.setdefault(row["date"], []).append({
                "content": _safe_decrypt(row["content"], "[복호화 오류]"),
                "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
            })
        return result


def add_schedule(date: str, content: str, color: str = DEFAULT_SCHEDULE_COLOR, *,
                 options: ScheduleOptions | None = None) -> int:
    """일정 추가(본문 암호화). 세부 설정이 있으면 먼저 검증하고 실패하면 아무것도 쓰지 않는다."""
    options = options or ScheduleOptions()
    if not options.is_default:
        options = validate_options(date, options)
    with _connection() as conn:
        cur = conn.execute(
            _SCHEDULE_INSERT,
            (date, encrypt(content), _now_str(), color, *options.to_db_values()),
        )
        conn.commit()
        return cur.lastrowid


def update_schedule(schedule_id: int, content: str = None, color: str = None, *,
                    options: ScheduleOptions | None = None) -> None:
    """일정 수정. options를 주면 세부 설정 여섯 칸을 한 번에 바꾼다(검증 실패 시 아무것도 안 씀)."""
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if options is not None:
            row = conn.execute(_SCHEDULE_SELECT + "WHERE id = ?", (schedule_id,)).fetchone()
            if row is None:
                raise ValueError("수정할 일정이 없습니다.")
            if not options.is_default:
                options = validate_options(row["date"], options)
            if row["series_id"] is not None and (options.repeat_rule or options.end_date):
                raise ValueError("수정 회차에는 반복·기간을 지정할 수 없습니다.")
            if row["repeat_rule"] and not options.repeat_rule:
                conn.execute("UPDATE schedules SET series_id = NULL, original_date = '' WHERE series_id = ?",
                             (schedule_id,))
        if content is not None:
            conn.execute(
                "UPDATE schedules SET content = ? WHERE id = ?",
                (encrypt(content), schedule_id),
            )
        if color is not None:
            conn.execute(
                "UPDATE schedules SET color = ? WHERE id = ?",
                (color, schedule_id),
            )
        if options is not None:
            conn.execute(
                "UPDATE schedules SET start_time = ?, end_date = ?, repeat_rule = ?, "
                "repeat_until = ?, repeat_skip = ?, alarm_before = ? WHERE id = ?",
                (*options.to_db_values(), schedule_id),
            )
        conn.commit()


def update_schedule_occurrence(series_id: int, day: str, content: str, color: str, *,
                               options: ScheduleOptions) -> int:
    """그 날의 본문·색상·시각·알림 스냅샷을 저장한다. 전체 변경 뒤에도 독립적으로 유지한다."""
    options = validate_options(day, options)
    if options.repeat_rule or options.end_date:
        raise ValueError("이 날만 수정에서는 반복·기간을 바꿀 수 없습니다.")
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        parent = conn.execute(_SCHEDULE_SELECT + "WHERE id = ?", (series_id,)).fetchone()
        if parent is None or parent["series_id"] is not None or not parent["repeat_rule"]:
            raise ValueError("반복 원본이 없습니다.")
        current = conn.execute(_SCHEDULE_SELECT + "WHERE series_id = ? AND original_date = ?",
                               (series_id, day)).fetchone()
        if current is None:
            target = parse_date(day)
            if not occurrence_dates(parent["date"], ScheduleOptions.from_row(parent), target, target):
                raise ValueError("그 날에는 이 일정이 없습니다.")
            cursor = conn.execute(
                "INSERT INTO schedules (date, content, created_at, color, start_time, alarm_before, "
                "series_id, original_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (day, encrypt(content), _now_str(), color, options.start_time, options.alarm_before, series_id, day),
            )
            sid = cursor.lastrowid
        else:
            sid = current["id"]
            conn.execute("UPDATE schedules SET content = ?, color = ?, start_time = ?, alarm_before = ? WHERE id = ?",
                         (encrypt(content), color, options.start_time, options.alarm_before, sid))
        conn.commit()
        return sid


def skip_schedule_occurrence(schedule_id: int, day: str) -> None:
    """반복 일정의 그 날 하나만 지운다(건너뛴 날에 더함).

    끝 날짜가 있는 반복에서 남은 날이 없어지면 보이지 않는 빈 행이 남지 않도록
    같은 트랜잭션에서 행도 지운다. 끝 날짜가 없는 반복은 행을 그대로 둔다.
    """
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(_SCHEDULE_SELECT + "WHERE id = ?", (schedule_id,)).fetchone()
        if row is None:
            raise ValueError("일정이 없습니다.")
        options = ScheduleOptions.from_row(row)
        if not options.repeat_rule:
            raise ValueError("반복 일정이 아닙니다.")
        target = parse_date(day)
        modified = conn.execute("SELECT id FROM schedules WHERE series_id = ? AND original_date = ?",
                                (schedule_id, day)).fetchone()
        if modified is None and not occurrence_dates(row["date"], options, target, target):
            raise ValueError("그 날에는 이 일정이 없습니다.")
        updated = validate_options(row["date"], replace(options, repeat_skip=options.repeat_skip + (day,)))
        if modified is not None:
            conn.execute("DELETE FROM schedules WHERE id = ?", (modified["id"],))
        has_children = conn.execute("SELECT 1 FROM schedules WHERE series_id = ? LIMIT 1", (schedule_id,)).fetchone()
        if not has_children and updated.repeat_until and next(iter_occurrence_dates(
                row["date"], updated, parse_date(row["date"]), parse_date(updated.repeat_until)), None) is None:
            conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        else:
            conn.execute(
                "UPDATE schedules SET repeat_skip = ? WHERE id = ?",
                (",".join(updated.repeat_skip), schedule_id),
            )
        conn.commit()


def get_alarm_occurrences(after: datetime, until: datetime) -> list[AlarmItem]:
    """after < 알림 ≤ until 인 알림을 알림 시각·ID 순으로 반환한다."""
    if until <= after:
        return []
    first = date.fromordinal(max(date.min.toordinal(), after.date().toordinal() - 1)).isoformat()
    last = date.fromordinal(min(date.max.toordinal(), until.date().toordinal() + 2)).isoformat()
    with _connection() as conn:
        # 알림 OFF 수정 회차도 원본 알림을 억제하므로 필터 전에 함께 읽는다.
        rows = _candidate_rows(conn, first, last)
    overridden = {(row["series_id"], row["original_date"]) for row in rows if row["series_id"] is not None}
    items = []
    for row in rows:
        options = ScheduleOptions.from_row(row)
        if options.alarm_before is None:
            continue
        try:
            dues = alarm_times(row["date"], options, after, until)
        except ValueError as exc:
            _logger.warning("일정 알림 시각 계산 실패 (id=%s): %s", row["id"], exc)
            continue
        if not dues:
            continue
        content, failed = _decrypt_schedule(row["content"])
        for day, due in dues:
            if (row["id"], day.isoformat()) in overridden:
                continue
            items.append(AlarmItem(
                row["id"], day.isoformat(), due, content,
                row["color"] or DEFAULT_SCHEDULE_COLOR, options.start_time, failed,
            ))
    items.sort(key=lambda item: (item.due, item.schedule_id))
    return items


def has_schedule_alarms() -> bool:
    """알림이 켜진 일정이 하나라도 있는지(정상 종료 때 알림 처리 시각을 남길지 판단)."""
    with _connection() as conn:
        return conn.execute(
            "SELECT 1 FROM schedules WHERE alarm_before IS NOT NULL LIMIT 1"
        ).fetchone() is not None


def delete_schedule(schedule_id: int) -> None:
    """일반 일정 또는 반복 전체 삭제. 수정 회차 단독 삭제는 skip API만 사용한다."""
    with _connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT series_id FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        if row is not None and row["series_id"] is not None:
            raise ValueError("수정 회차는 이 날만 삭제를 사용해야 합니다.")
        conn.execute("DELETE FROM schedules WHERE id = ? OR series_id = ?", (schedule_id, schedule_id))
        conn.commit()


# ─── memos CRUD ───────────────────────────────────────────────
def get_memo(date: str) -> str:
    """특정 날짜 자유 메모 조회 (복호화)"""
    with _connection() as conn:
        row = conn.execute(
            "SELECT content FROM memos WHERE date = ?", (date,)
        ).fetchone()
        if row is None:
            return ""
        return _safe_decrypt(row["content"], "[복호화 오류]")


def search_all(keyword: str, limit: int = 500) -> list[dict]:
    """모든 일정과 메모를 복호화 후 키워드 검색 (커서 순회, 최대 limit건)"""
    keyword_lower = keyword.lower()
    results = []
    with _connection() as conn:
        # 일정 검색 (cursor iteration)
        for row in conn.execute(_SCHEDULE_SELECT):
            content = _safe_decrypt(row["content"])
            if not content:
                continue
            if not keyword_lower or keyword_lower in content.lower():
                # 규칙에 어긋난 저장값은 읽기와 같은 기준으로 기본값 취급(엉뚱한 기간 표시 방지).
                options = ScheduleOptions.from_row(row)
                results.append({
                    "type": "일정",
                    "date": row["date"],
                    "content": content,
                    "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
                    "end_date": options.end_date,
                    "repeat_rule": options.repeat_rule,
                    "is_override": row["series_id"] is not None,
                })
                if len(results) >= limit:
                    break

        # 메모 검색 (cursor iteration)
        if len(results) < limit:
            for row in conn.execute("SELECT id, date, content, updated_at FROM memos"):
                content = _safe_decrypt(row["content"])
                if not content:
                    continue
                if not keyword_lower or keyword_lower in content.lower():
                    results.append({
                        "type": "메모",
                        "date": row["date"],
                        "content": content,
                        "color": "#E0E0E0"  # 메모는 회색으로 통일
                    })
                    if len(results) >= limit:
                        break

        # 날짜순 정렬
        results.sort(key=lambda x: x["date"], reverse=True)
        return results


def save_memo(date: str, content: str) -> None:
    """자유 메모 저장 (없으면 INSERT, 있으면 UPDATE)"""
    with _connection() as conn:
        now = _now_str()
        encrypted = encrypt(content)
        exists = conn.execute(
            "SELECT id FROM memos WHERE date = ?", (date,)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE memos SET content = ?, updated_at = ? WHERE date = ?",
                (encrypted, now, date)
            )
        else:
            conn.execute(
                "INSERT INTO memos (date, content, updated_at) VALUES (?, ?, ?)",
                (date, encrypted, now)
            )
        conn.commit()


# ─── sticky_notes CRUD ────────────────────────────────────────
def get_open_sticky_notes() -> list[dict]:
    """is_open=1인 스티키 노트 전체 조회"""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sticky_notes WHERE is_open = 1 AND is_deleted = 0"
        ).fetchall()
        result = []
        for row in rows:
            content, failed = _safe_decrypt_with_status(row["content"])
            result.append({
                "id": row["id"],
                "type": row["type"],
                "content": content,
                "x_pos": row["x_pos"],
                "y_pos": row["y_pos"],
                "width": row["width"],
                "height": row["height"],
                "is_open": row["is_open"],
                "is_pinned": row["is_pinned"],
                "color": row["color"] or DEFAULT_STICKY_COLOR,
                "_decryption_failed": failed,
            })
        return result


def create_sticky_note(note_type: str = "memo", x: int = 200, y: int = 200,
                       color: str = DEFAULT_STICKY_COLOR) -> int:
    """새 스티키 노트 생성, 생성된 id 반환"""
    with _connection() as conn:
        cur = conn.execute(
            """INSERT INTO sticky_notes
               (type, content, x_pos, y_pos, width, height, is_open, is_pinned, color)
               VALUES (?, ?, ?, ?, 300, 400, 1, 0, ?)""",
            (note_type, encrypt(""), x, y, color)
        )
        conn.commit()
        return cur.lastrowid


def update_sticky_note(note_id: int, **kwargs) -> None:
    """스티키 노트 필드 부분 업데이트"""
    allowed = {"type", "content", "x_pos", "y_pos", "width", "height",
               "is_open", "is_pinned", "color"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    # content는 암호화
    if "content" in fields:
        fields["content"] = encrypt(fields["content"])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [note_id]

    with _connection() as conn:
        conn.execute(
            f"UPDATE sticky_notes SET {set_clause} WHERE id = ?",  # noqa: S608
            values
        )
        conn.commit()


def purge_sticky_note(note_id: int) -> None:
    """스티키 노트 영구 삭제(되돌릴 수 없음). 휴지통 '영구 삭제'에서 호출."""
    with _connection() as conn:
        conn.execute("DELETE FROM sticky_notes WHERE id = ?", (note_id,))
        conn.commit()


def trash_sticky_note(note_id: int) -> None:
    """스티키 노트를 휴지통으로 이동(soft-delete). 닫기에서 호출."""
    with _connection() as conn:
        conn.execute(
            "UPDATE sticky_notes SET is_deleted = 1, deleted_at = ?, is_open = 0 WHERE id = ?",
            (_now_str(), note_id)
        )
        _enforce_trash_cap(conn)
        conn.commit()


def restore_sticky_note(note_id: int) -> None:
    """휴지통의 스티키 노트를 복구(원래 위치/내용 유지)."""
    with _connection() as conn:
        conn.execute(
            "UPDATE sticky_notes SET is_deleted = 0, is_open = 1, deleted_at = '' WHERE id = ?",
            (note_id,)
        )
        conn.commit()


def empty_sticky_trash() -> None:
    """휴지통의 모든 스티키 노트 영구 삭제."""
    with _connection() as conn:
        conn.execute("DELETE FROM sticky_notes WHERE is_deleted = 1")
        conn.commit()


def get_trashed_sticky_notes() -> list[dict]:
    """is_deleted=1인 스티키 노트 조회(최근 삭제순). 미리보기용 content 복호화."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sticky_notes WHERE is_deleted = 1 "
            "ORDER BY deleted_at DESC, id DESC"
        ).fetchall()
        result = []
        for row in rows:
            content, failed = _safe_decrypt_with_status(row["content"])
            result.append({
                "id": row["id"],
                "content": content,
                "color": row["color"] or DEFAULT_STICKY_COLOR,
                "deleted_at": row["deleted_at"],
                "_decryption_failed": failed,
            })
        return result


def _enforce_trash_cap(conn) -> None:
    """휴지통이 STICKY_TRASH_LIMIT를 넘으면 오래된 것부터 영구삭제(같은 커넥션 사용)."""
    count = conn.execute(
        "SELECT COUNT(*) FROM sticky_notes WHERE is_deleted = 1"
    ).fetchone()[0]
    excess = count - STICKY_TRASH_LIMIT
    if excess > 0:
        conn.execute(
            "DELETE FROM sticky_notes WHERE id IN ("
            "  SELECT id FROM sticky_notes WHERE is_deleted = 1"
            "  ORDER BY deleted_at ASC, id ASC LIMIT ?"
            ")",
            (excess,)
        )
        _logger.info(
            "휴지통 한도(%d) 초과로 오래된 스티키 노트 %d개 영구삭제",
            STICKY_TRASH_LIMIT, excess
        )


# ─── dday_widgets CRUD ────────────────────────────────────────
def get_open_dday_widgets() -> list[dict]:
    """is_open=1인 D-Day 위젯 전체 조회"""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM dday_widgets WHERE is_open = 1 ORDER BY id"
        ).fetchall()
        return [{
            "id": row["id"],
            "name": _safe_decrypt(row["name"], "[복호화 오류]"),
            "target_date": row["target_date"],
            "x_pos": row["x_pos"],
            "y_pos": row["y_pos"],
            "is_open": row["is_open"],
            "color": row["color"] or DEFAULT_DDAY_COLOR,
        } for row in rows]


def create_dday_widget(name: str, target_date: str,
                       x: int = 100, y: int = 100,
                       color: str = DEFAULT_DDAY_COLOR) -> int:
    """새 D-Day 위젯 생성, 생성된 id 반환"""
    with _connection() as conn:
        cur = conn.execute(
            """INSERT INTO dday_widgets (name, target_date, x_pos, y_pos, is_open, color)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (encrypt(name), target_date, x, y, color)
        )
        conn.commit()
        return cur.lastrowid


def update_dday_widget(widget_id: int, **kwargs) -> None:
    """D-Day 위젯 필드 부분 업데이트"""
    allowed = {"name", "target_date", "x_pos", "y_pos", "is_open", "color"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    if "name" in fields:
        fields["name"] = encrypt(fields["name"])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [widget_id]

    with _connection() as conn:
        conn.execute(
            f"UPDATE dday_widgets SET {set_clause} WHERE id = ?",  # noqa: S608
            values
        )
        conn.commit()


def delete_dday_widget(widget_id: int) -> None:
    """D-Day 위젯 삭제"""
    with _connection() as conn:
        conn.execute("DELETE FROM dday_widgets WHERE id = ?", (widget_id,))
        conn.commit()


# ─── focus_widgets CRUD ───────────────────────────────────────
def _focus_mode_values(mode_key: str) -> tuple[str, int, int]:
    label, focus_minutes, break_minutes = FOCUS_MODES.get(mode_key, FOCUS_MODES[DEFAULT_FOCUS_MODE])
    return label, focus_minutes, break_minutes


def get_open_focus_widgets() -> list[dict]:
    """is_open=1인 집중 모드 위젯 전체 조회"""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM focus_widgets WHERE is_open = 1 ORDER BY id"
        ).fetchall()
        return [{
            "id": row["id"],
            "goal": _safe_decrypt(row["goal"], "[복호화 오류]"),
            "mode_key": row["mode_key"] or DEFAULT_FOCUS_MODE,
            "focus_minutes": row["focus_minutes"],
            "break_minutes": row["break_minutes"],
            "x_pos": row["x_pos"],
            "y_pos": row["y_pos"],
            "is_open": row["is_open"],
            "is_pinned": row["is_pinned"],
            "created_at": row["created_at"],
        } for row in rows]


def create_focus_widget(goal: str = "", mode_key: str = DEFAULT_FOCUS_MODE,
                        x: int = 160, y: int = 160, is_pinned: int = 0) -> int:
    """새 집중 모드 위젯 생성, 생성된 id 반환"""
    _label, focus_minutes, break_minutes = _focus_mode_values(mode_key)
    with _connection() as conn:
        cur = conn.execute(
            """INSERT INTO focus_widgets
               (goal, mode_key, focus_minutes, break_minutes, x_pos, y_pos, is_open, is_pinned, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (encrypt(goal), mode_key, focus_minutes, break_minutes, x, y, is_pinned, _now_str())
        )
        conn.commit()
        return cur.lastrowid


def update_focus_widget(widget_id: int, **kwargs) -> None:
    """집중 모드 위젯 필드 부분 업데이트"""
    allowed = {
        "goal", "mode_key", "focus_minutes", "break_minutes",
        "x_pos", "y_pos", "is_open", "is_pinned",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    if "mode_key" in fields and ("focus_minutes" not in fields or "break_minutes" not in fields):
        _label, focus_minutes, break_minutes = _focus_mode_values(fields["mode_key"])
        fields.setdefault("focus_minutes", focus_minutes)
        fields.setdefault("break_minutes", break_minutes)

    if "goal" in fields:
        fields["goal"] = encrypt(fields["goal"])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [widget_id]

    with _connection() as conn:
        conn.execute(
            f"UPDATE focus_widgets SET {set_clause} WHERE id = ?",  # noqa: S608
            values
        )
        conn.commit()


def delete_focus_widget(widget_id: int) -> None:
    """집중 모드 위젯 삭제"""
    with _connection() as conn:
        conn.execute("DELETE FROM focus_widgets WHERE id = ?", (widget_id,))
        conn.commit()


# ─── 위젯 개수 제한 정리 ───────────────────────────────────────
def enforce_widget_limits() -> dict[str, int]:
    """집중(1)·D-Day(5) 상한 초과분을 is_open=0으로 정리한다.

    최신(id 큰) N개만 남기고 나머지를 닫는다(행 삭제 아님, 데이터 보존).
    멱등하며, 정리된 개수를 {"focus": n, "dday": m} 로 반환한다.
    """
    trimmed = {"focus": 0, "dday": 0}
    limits = (("focus", "focus_widgets", 1), ("dday", "dday_widgets", 5))
    with _connection() as conn:
        for kind, table, keep in limits:
            rows = conn.execute(
                f"SELECT id FROM {table} WHERE is_open = 1 ORDER BY id DESC"  # noqa: S608
            ).fetchall()
            excess = [row["id"] for row in rows[keep:]]
            for widget_id in excess:
                conn.execute(
                    f"UPDATE {table} SET is_open = 0 WHERE id = ?",  # noqa: S608
                    (widget_id,),
                )
            trimmed[kind] = len(excess)
        conn.commit()
    return trimmed


def create_focus_session(widget_id: int | None, goal: str, mode_key: str,
                         focus_minutes: int, break_minutes: int,
                         started_at: str, ended_at: str,
                         elapsed_seconds: int, completed: bool,
                         focus_rating: int | None = None,
                         distraction: str = "없음") -> int:
    """집중 세션 회고 기록을 저장하고 생성된 id를 반환"""
    with _connection() as conn:
        cur = conn.execute(
            """INSERT INTO focus_sessions
               (widget_id, goal, mode_key, focus_minutes, break_minutes,
                started_at, ended_at, elapsed_seconds, completed,
                focus_rating, distraction, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                widget_id, encrypt(goal), mode_key, focus_minutes, break_minutes,
                started_at, ended_at, elapsed_seconds, 1 if completed else 0,
                focus_rating, distraction or "없음", _now_str(),
            )
        )
        conn.commit()
        return cur.lastrowid


def get_focus_sessions() -> list[dict]:
    """저장된 집중 세션 회고 목록 조회"""
    with _connection() as conn:
        rows = conn.execute("SELECT * FROM focus_sessions ORDER BY id ASC").fetchall()
        return [{
            "id": row["id"],
            "widget_id": row["widget_id"],
            "goal": _safe_decrypt(row["goal"], "[복호화 오류]"),
            "mode_key": row["mode_key"],
            "focus_minutes": row["focus_minutes"],
            "break_minutes": row["break_minutes"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "elapsed_seconds": row["elapsed_seconds"],
            "completed": row["completed"],
            "focus_rating": row["focus_rating"],
            "distraction": row["distraction"],
            "created_at": row["created_at"],
        } for row in rows]


# ─── Export / Import ──────────────────────────────────────────
def _export_options(row) -> ScheduleOptions:
    """내보낼 일정 세부 설정. 저장값이 서로 어긋나 가져오기 검증을 넘지 못하면 덜 해치는 쪽으로 낮춘다.

    표시용 fallback과 별개로 필드마다 정리한 뒤 여러 필드에 걸친 규칙을 검사한다.
    그런 행 하나가 백업 파일 전체를 가져올 수 없게 만들지 않도록, 가져오기와
    같은 validate_options를 통과하는 첫 후보를 쓴다. DB는 바꾸지 않는다.
    """
    options = ScheduleOptions.from_row(row, normalize_relations=False)
    candidates = (
        options,
        replace(options, repeat_skip=()),
        replace(options, repeat_until="", repeat_skip=()),
        replace(options, repeat_rule="", repeat_until="", repeat_skip=()),
        replace(options, end_date="", repeat_rule="", repeat_until="", repeat_skip=()),
        ScheduleOptions(),
    )
    for index, candidate in enumerate(candidates):
        if candidate.is_default:
            chosen = candidate  # 가져오기도 기본값은 검증하지 않는다(옛 형식 날짜 보존)
        else:
            try:
                chosen = validate_options(row["date"], candidate)
            except ValueError:
                continue
        if index:
            _logger.warning("Export 일정 세부 설정 조정: schedules id=%s", row["id"])
        return chosen
    return ScheduleOptions()  # 마지막 후보가 기본값이라 여기에는 닿지 않는다


def export_all_data() -> str:
    """모든 데이터를 평문 JSON으로 직렬화 (Export 전 단계)"""
    with _connection() as conn:
        # 여러 테이블을 하나의 시점으로 읽어 Export 중 변경이 섞이지 않게 한다.
        conn.execute("BEGIN")
        schedules = []
        schedule_rows = conn.execute("SELECT * FROM schedules ORDER BY id ASC").fetchall()
        _validate_schedule_links(schedule_rows)
        for row in schedule_rows:
            options = _export_options(row)
            schedules.append({
                "source_id": row["id"],
                "series_source_id": row["series_id"],
                "original_date": row["original_date"],
                "date": row["date"],
                "content": _decrypt_for_export(row["content"], "schedules", row["id"]),
                "created_at": row["created_at"],
                "color": row["color"] or DEFAULT_SCHEDULE_COLOR,
                "start_time": options.start_time,
                "end_date": options.end_date,
                "repeat_rule": options.repeat_rule,
                "repeat_until": options.repeat_until,
                "repeat_skip": list(options.repeat_skip),
                "alarm_before": options.alarm_before,
            })

        memos = [{
            "date": row["date"],
            "content": _decrypt_for_export(
                row["content"], "memos", row["id"]
            ),
            "updated_at": row["updated_at"],
        } for row in conn.execute("SELECT * FROM memos")]

        sticky_notes = [{
            "type": row["type"],
            "content": _decrypt_for_export(
                row["content"], "sticky_notes", row["id"]
            ),
            "x_pos": row["x_pos"],
            "y_pos": row["y_pos"],
            "width": row["width"],
            "height": row["height"],
            "is_open": row["is_open"],
            "is_pinned": row["is_pinned"],
            "color": row["color"] or DEFAULT_STICKY_COLOR,
            "is_deleted": row["is_deleted"],
            "deleted_at": row["deleted_at"],
        } for row in conn.execute("SELECT * FROM sticky_notes")]

        dday_widgets = [{
            "name": _decrypt_for_export(
                row["name"], "dday_widgets", row["id"]
            ),
            "target_date": row["target_date"],
            "x_pos": row["x_pos"],
            "y_pos": row["y_pos"],
            "is_open": row["is_open"],
            "color": row["color"] or DEFAULT_DDAY_COLOR,
        } for row in conn.execute("SELECT * FROM dday_widgets")]

        focus_widgets = [{
            "source_id": row["id"],
            "goal": _decrypt_for_export(
                row["goal"], "focus_widgets", row["id"]
            ),
            "mode_key": row["mode_key"] or DEFAULT_FOCUS_MODE,
            "focus_minutes": row["focus_minutes"],
            "break_minutes": row["break_minutes"],
            "x_pos": row["x_pos"],
            "y_pos": row["y_pos"],
            "is_open": row["is_open"],
            "is_pinned": row["is_pinned"],
            "created_at": row["created_at"],
        } for row in conn.execute("SELECT * FROM focus_widgets")]

        focus_sessions = [{
            "widget_id": row["widget_id"],
            "goal": _decrypt_for_export(
                row["goal"], "focus_sessions", row["id"]
            ),
            "mode_key": row["mode_key"] or DEFAULT_FOCUS_MODE,
            "focus_minutes": row["focus_minutes"],
            "break_minutes": row["break_minutes"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "elapsed_seconds": row["elapsed_seconds"],
            "completed": row["completed"],
            "focus_rating": row["focus_rating"],
            "distraction": row["distraction"],
            "created_at": row["created_at"],
        } for row in conn.execute("SELECT * FROM focus_sessions")]

        # app_settings 전체 백업 (평문 PIN과 이 PC의 알림 처리 시각은 제외)
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM app_settings")
            if row["key"] not in EXPORT_EXCLUDED_SETTINGS
        }
        shortcuts = [
            dict(row)
            for row in conn.execute(
                "SELECT id, name, path FROM shortcuts ORDER BY id ASC"
            )
        ]

        return json.dumps({
            "format_version": EXPORT_FORMAT_VERSION,
            "schedules": schedules,
            "memos": memos,
            "sticky_notes": sticky_notes,
            "dday_widgets": dday_widgets,
            "focus_widgets": focus_widgets,
            "focus_sessions": focus_sessions,
            "shortcuts": shortcuts,
            "settings": settings,
        }, ensure_ascii=False)


def _validate_import_field(
        item: dict, section: str, index: int, field: str,
        expected_type, *, required: bool = False, allow_none: bool = False
) -> None:
    """Import 항목의 한 필드를 쓰기 전에 구조적으로 검증한다."""
    if field not in item:
        if required:
            raise ValueError(
                f"{section}[{index}].{field} 필드가 필요합니다."
            )
        return

    value = item[field]
    if value is None and allow_none:
        return
    if expected_type is int:
        valid = isinstance(value, int) and not isinstance(value, bool)
    else:
        valid = isinstance(value, expected_type)
    if not valid:
        raise ValueError(
            f"{section}[{index}].{field} 형식이 올바르지 않습니다."
        )
    if expected_type is int and not -(2 ** 63) <= value <= 2 ** 63 - 1:
        raise ValueError(
            f"{section}[{index}].{field} 값이 SQLite 범위를 벗어났습니다."
        )


def _validate_import_flag(
        item: dict, section: str, index: int, field: str,
        *, required: bool = False
) -> None:
    """SQLite boolean 필드는 0/1 또는 bool만 허용한다."""
    _validate_import_field(
        item, section, index, field, (int, bool), required=required
    )
    if field in item and item[field] not in (0, 1, False, True):
        raise ValueError(
            f"{section}[{index}].{field} 값이 올바르지 않습니다."
        )


def _validate_import_geometry(item: dict, section: str, index: int, fields) -> None:
    """SQLite int64로 저장돼도 Qt의 int32 좌표/크기로 복원할 수 있어야 한다."""
    for field in fields:
        if field in item and not -(2 ** 31) <= item[field] <= 2 ** 31 - 1:
            raise ValueError(
                f"{section}[{index}].{field} 값이 화면 좌표/크기 범위를 벗어났습니다."
            )


def _import_options(item: dict) -> ScheduleOptions:
    """v3 일정 항목의 세부 설정(없는 키는 기본값)."""
    return ScheduleOptions(
        start_time=item.get("start_time", ""),
        end_date=item.get("end_date", ""),
        repeat_rule=item.get("repeat_rule", ""),
        repeat_until=item.get("repeat_until", ""),
        repeat_skip=tuple(item.get("repeat_skip", [])),
        alarm_before=item.get("alarm_before"),
    )


def _validate_import_payload(data) -> dict:
    """전체 Import payload를 검증하고 쓰기 가능한 형태로 정규화한다."""
    if not isinstance(data, dict):
        raise ValueError("가져오기 데이터의 최상위 형식은 객체여야 합니다.")

    version = data.get("format_version", 1)
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
        or version > EXPORT_FORMAT_VERSION
    ):
        raise ValueError(
            f"지원하지 않는 format_version입니다: {version!r}"
        )

    list_sections = (
        "schedules", "memos", "sticky_notes", "dday_widgets",
        "focus_widgets", "focus_sessions", "shortcuts",
    )
    for section in list_sections:
        items = data.get(section, [])
        if not isinstance(items, list):
            raise ValueError(f"{section} 섹션은 목록이어야 합니다.")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{section}[{index}]는 객체여야 합니다.")

    for index, item in enumerate(data.get("schedules", [])):
        for field in ("date", "content"):
            _validate_import_field(
                item, "schedules", index, field, str, required=True
            )
        for field in ("created_at", "color"):
            _validate_import_field(
                item, "schedules", index, field, str
            )
        if version >= 3:
            for field in ("start_time", "end_date", "repeat_rule", "repeat_until"):
                _validate_import_field(item, "schedules", index, field, str)
            skips = item.get("repeat_skip", [])
            if not isinstance(skips, list) or not all(isinstance(day, str) for day in skips):
                raise ValueError(f"schedules[{index}].repeat_skip 형식이 올바르지 않습니다.")
            _validate_import_field(item, "schedules", index, "alarm_before", int, allow_none=True)
            options = _import_options(item)
            if not options.is_default:
                try:
                    validate_options(item["date"], options)
                except ValueError as exc:
                    raise ValueError(f"schedules[{index}] 세부 설정이 올바르지 않습니다: {exc}") from exc

    if version >= 4:
        schedules = data.get("schedules", [])
        for index, item in enumerate(schedules):
            _validate_import_field(item, "schedules", index, "source_id", int, required=True)
            _validate_import_field(item, "schedules", index, "series_source_id", int, required=True, allow_none=True)
            _validate_import_field(item, "schedules", index, "original_date", str, required=True)
        # v3의 선택 필드는 v4에서도 기본값을 허용하되 관계 검증에는 명시적으로 채운다.
        normalized = [dict(start_time="", end_date="", repeat_rule="", repeat_until="",
                           repeat_skip=[], alarm_before=None) | item for item in schedules]
        _validate_schedule_links(normalized, id_field="source_id", parent_field="series_source_id")

    for index, item in enumerate(data.get("memos", [])):
        for field in ("date", "content"):
            _validate_import_field(
                item, "memos", index, field, str, required=True
            )
        _validate_import_field(
            item, "memos", index, "updated_at", str
        )

    for index, item in enumerate(data.get("sticky_notes", [])):
        _validate_import_field(
            item, "sticky_notes", index, "type", str, required=True
        )
        for field in ("x_pos", "y_pos", "width", "height"):
            _validate_import_field(
                item, "sticky_notes", index, field, int, required=True
            )
        _validate_import_geometry(
            item, "sticky_notes", index, ("x_pos", "y_pos", "width", "height")
        )
        for field in ("width", "height"):
            if item[field] <= 0:
                raise ValueError(
                    f"sticky_notes[{index}].{field} 값이 올바르지 않습니다."
                )
        for field in ("is_open", "is_pinned"):
            _validate_import_flag(
                item, "sticky_notes", index, field, required=True
            )
        for field in ("content", "color", "deleted_at"):
            _validate_import_field(
                item, "sticky_notes", index, field, str
            )
        _validate_import_flag(
            item, "sticky_notes", index, "is_deleted"
        )

    for index, item in enumerate(data.get("dday_widgets", [])):
        _validate_import_field(
            item, "dday_widgets", index, "target_date", str, required=True
        )
        for field in ("name", "color"):
            _validate_import_field(
                item, "dday_widgets", index, field, str
            )
        for field in ("x_pos", "y_pos"):
            _validate_import_field(
                item, "dday_widgets", index, field, int
            )
        _validate_import_geometry(item, "dday_widgets", index, ("x_pos", "y_pos"))
        _validate_import_flag(
            item, "dday_widgets", index, "is_open"
        )

    focus_source_ids = set()
    for index, item in enumerate(data.get("focus_widgets", [])):
        for field in ("source_id", "focus_minutes", "break_minutes",
                      "x_pos", "y_pos"):
            _validate_import_field(
                item, "focus_widgets", index, field, int
            )
        _validate_import_geometry(item, "focus_widgets", index, ("x_pos", "y_pos"))
        for field in ("goal", "mode_key", "created_at"):
            _validate_import_field(
                item, "focus_widgets", index, field, str
            )
        for field in ("is_open", "is_pinned"):
            _validate_import_flag(
                item, "focus_widgets", index, field
            )
        if version >= 2:
            _validate_import_field(
                item, "focus_widgets", index, "source_id", int,
                required=True,
            )
            source_id = item["source_id"]
            if source_id <= 0 or source_id in focus_source_ids:
                raise ValueError(
                    f"focus_widgets[{index}].source_id 값이 올바르지 않습니다."
                )
            focus_source_ids.add(source_id)

    for index, item in enumerate(data.get("focus_sessions", [])):
        _validate_import_field(
            item, "focus_sessions", index, "widget_id", int,
            allow_none=True,
        )
        for field in ("focus_minutes", "break_minutes", "elapsed_seconds"):
            _validate_import_field(
                item, "focus_sessions", index, field, int
            )
        _validate_import_field(
            item, "focus_sessions", index, "focus_rating", int,
            allow_none=True,
        )
        for field in ("goal", "mode_key", "started_at", "ended_at",
                      "distraction", "created_at"):
            _validate_import_field(
                item, "focus_sessions", index, field, str
            )
        _validate_import_flag(
            item, "focus_sessions", index, "completed"
        )

    shortcut_ids = set()
    for index, item in enumerate(data.get("shortcuts", [])):
        _validate_import_field(
            item, "shortcuts", index, "id", int, required=True
        )
        for field in ("name", "path"):
            _validate_import_field(
                item, "shortcuts", index, field, str, required=True
            )
        shortcut_id = item["id"]
        if shortcut_id not in range(1, 7) or shortcut_id in shortcut_ids:
            raise ValueError(
                f"shortcuts[{index}].id 값이 올바르지 않습니다."
            )
        shortcut_ids.add(shortcut_id)

    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("settings 섹션은 객체여야 합니다.")
    for key, value in settings.items():
        if not isinstance(key, str) or (
            value is not None
            and not isinstance(value, (str, int, float, bool))
        ):
            raise ValueError("settings 항목 형식이 올바르지 않습니다.")

    validated = dict(data)
    validated["format_version"] = version
    return validated


def import_all_data(json_str: str) -> dict[str, int]:
    """검증된 JSON을 기존 DB에 병합하고 privacy_pin 외 설정도 복원.

    날짜가 같은 메모는 현재 DB 값을 우선한다. 안정적인 원본 식별자가 없는
    일정·위젯은 과거 형식과의 호환을 위해 append하며, 내용 기반 자동 dedup은
    서로 다른 사용자 데이터를 합칠 위험이 있어 수행하지 않는다.
    """
    data = _validate_import_payload(json.loads(json_str))
    with _connection() as conn:
        now = _now_str()
        # 기존 위젯을 우선한다. 초과한 새 행도 삭제하지 않고 닫힌 상태로 보관한다.
        limits = {"sticky_notes": 10, "dday_widgets": 5, "focus_widgets": 1}
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE is_open=1"  # 고정된 내부 표 이름
                + (" AND is_deleted=0" if table == "sticky_notes" else "")
            ).fetchone()[0] for table in limits
        }
        limited = {table: 0 for table in limits}

        def imported_open(table, requested, deleted=False):
            if not requested or deleted:
                return requested
            if counts[table] >= limits[table]:
                limited[table] += 1
                return 0
            counts[table] += 1
            return 1

        schedule_id_map = {}
        schedule_items = data.get("schedules", [])
        if data["format_version"] >= 4:
            schedule_items = sorted(schedule_items, key=lambda s: s["series_source_id"] is not None)
        for s in schedule_items:
            options = _import_options(s) if data["format_version"] >= 3 else ScheduleOptions()
            if not options.is_default:
                options = validate_options(s["date"], options)
            cursor = conn.execute(
                _SCHEDULE_INSERT,
                (s["date"], encrypt(s["content"]), s.get("created_at", now),
                 s.get("color", DEFAULT_SCHEDULE_COLOR), *options.to_db_values()),
            )
            if data["format_version"] >= 4:
                schedule_id_map[s["source_id"]] = cursor.lastrowid
                if s["series_source_id"] is not None:
                    conn.execute("UPDATE schedules SET series_id = ?, original_date = ? WHERE id = ?",
                                 (schedule_id_map[s["series_source_id"]], s["original_date"], cursor.lastrowid))

        for m in data.get("memos", []):
            exists = conn.execute(
                "SELECT id FROM memos WHERE date = ?", (m["date"],)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO memos (date, content, updated_at) VALUES (?, ?, ?)",
                    (
                        m["date"], encrypt(m["content"]),
                        m.get("updated_at", now),
                    )
                )

        for n in data.get("sticky_notes", []):
            conn.execute(
                """INSERT INTO sticky_notes
                   (type, content, x_pos, y_pos, width, height, is_open, is_pinned,
                    color, is_deleted, deleted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (n["type"], encrypt(n.get("content", "")), n["x_pos"], n["y_pos"],
                  n["width"], n["height"], imported_open("sticky_notes", n["is_open"], n.get("is_deleted", 0)), n["is_pinned"],
                 n.get("color", DEFAULT_STICKY_COLOR),
                 n.get("is_deleted", 0), n.get("deleted_at", ""))
            )

        for d in data.get("dday_widgets", []):
            conn.execute(
                """INSERT INTO dday_widgets
                   (name, target_date, x_pos, y_pos, is_open, color)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (encrypt(d.get("name", "")), d["target_date"],
                 d.get("x_pos", 100), d.get("y_pos", 100),
                  imported_open("dday_widgets", d.get("is_open", 1)), d.get("color", DEFAULT_DDAY_COLOR))
            )

        focus_id_map: dict[int, int] = {}
        for f in data.get("focus_widgets", []):
            mode_key = f.get("mode_key", DEFAULT_FOCUS_MODE)
            _label, default_focus, default_break = _focus_mode_values(mode_key)
            cursor = conn.execute(
                """INSERT INTO focus_widgets
                   (goal, mode_key, focus_minutes, break_minutes, x_pos, y_pos,
                    is_open, is_pinned, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    encrypt(f.get("goal", "")), mode_key,
                    f.get("focus_minutes", default_focus),
                    f.get("break_minutes", default_break),
                    f.get("x_pos", 160), f.get("y_pos", 160),
                    imported_open("focus_widgets", f.get("is_open", 1)), f.get("is_pinned", 0),
                    f.get("created_at", now),
                )
            )
            source_id = f.get("source_id")
            if source_id is not None:
                focus_id_map[source_id] = cursor.lastrowid

        for s in data.get("focus_sessions", []):
            mode_key = s.get("mode_key", DEFAULT_FOCUS_MODE)
            _label, default_focus, default_break = _focus_mode_values(mode_key)
            widget_id = None
            if data["format_version"] >= 2:
                widget_id = focus_id_map.get(s.get("widget_id"))
            conn.execute(
                """INSERT INTO focus_sessions
                   (widget_id, goal, mode_key, focus_minutes, break_minutes,
                    started_at, ended_at, elapsed_seconds, completed,
                    focus_rating, distraction, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    widget_id, encrypt(s.get("goal", "")), mode_key,
                    s.get("focus_minutes", default_focus),
                    s.get("break_minutes", default_break),
                    s.get("started_at", now), s.get("ended_at", now),
                    s.get("elapsed_seconds", 0), s.get("completed", 0),
                    s.get("focus_rating"), s.get("distraction", "없음"),
                    s.get("created_at", now),
                )
            )

        for shortcut in data.get("shortcuts", []):
            current = conn.execute(
                "SELECT name, path FROM shortcuts WHERE id = ?",
                (shortcut["id"],),
            ).fetchone()
            # 병합은 현재 사용자 설정을 우선한다. 비어 있거나 누락된 슬롯만
            # 백업 값으로 채워 정상 v2 payload의 빈 슬롯이 현재 값을 지우지 않는다.
            if current is None:
                conn.execute(
                    """INSERT INTO shortcuts (id, name, path)
                       VALUES (?, ?, ?)""",
                    (shortcut["id"], shortcut["name"], shortcut["path"]),
                )
            elif not (current["name"] or current["path"]):
                conn.execute(
                    "UPDATE shortcuts SET name = ?, path = ? WHERE id = ?",
                    (
                        shortcut["name"], shortcut["path"],
                        shortcut["id"],
                    ),
                )

        # 설정 복원 (평문 PIN·알림 처리 시각 제외, None 값 건너뜀)
        for key, value in data.get("settings", {}).items():
            if key in EXPORT_EXCLUDED_SETTINGS or value is None:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

        conn.commit()


    return limited


# ─── Shortcuts CRUD ──────────────────────────────────────────
def get_shortcuts() -> list[dict]:
    with _connection() as conn:
        rows = conn.execute("SELECT id, name, path FROM shortcuts ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]


def update_shortcut(shortcut_id: int, name: str, path: str) -> None:
    with _connection() as conn:
        conn.execute("UPDATE shortcuts SET name = ?, path = ? WHERE id = ?", (name, path, shortcut_id))
        conn.commit()


# ─── Settings CRUD ───────────────────────────────────────────
def get_setting(key: str, default: str = "") -> str:
    with _connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def save_setting(key: str, value: str) -> None:
    with _connection() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def save_settings(values: dict[str, str]) -> None:
    """서로 연결된 위치·화면 설정을 모두 저장하거나 모두 보존한다."""
    with _connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            values.items(),
        )
        conn.commit()


def upgrade_privacy_pin() -> bool:
    """기존 PIN만 같은 키의 검증값으로 옮긴다. 다른 설정·본문·salt는 바꾸지 않는다."""
    with _connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (SETTING_PRIVACY_PIN,)).fetchone()
        if row is None or not security.is_legacy_privacy_pin(row[0]):
            return False
        hashed = security.hash_privacy_pin(row[0])
        conn.execute("UPDATE app_settings SET value=? WHERE key=? AND value=?",
                     (hashed, SETTING_PRIVACY_PIN, row[0]))
        conn.commit()
    return True


# ─── Maintenance & Backup ─────────────────────────────────────
def _snapshot_is_valid(
        snapshot_path: Path, *, expected_version: int | None = None
) -> bool:
    """스냅샷이 SQLite 무결성 검사와 선택적 버전 검사를 통과하는지 확인한다."""
    try:
        with _connection(snapshot_path, enable_wal=False) as conn:
            checks = [
                row[0] for row in conn.execute("PRAGMA quick_check").fetchall()
            ]
            if checks != ["ok"]:
                return False
            if expected_version is not None:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version != expected_version:
                    return False
        return True
    except (sqlite3.Error, OSError, ValueError):
        return False


def _file_size_and_sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as source_file:
        while chunk := source_file.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


_TEMP_DB_SIDECAR_SUFFIXES = ("-wal", "-shm")


def _temp_db_sidecars(temp_db: Path) -> tuple[Path, ...]:
    return tuple(
        temp_db.with_name(f"{temp_db.name}{suffix}")
        for suffix in _TEMP_DB_SIDECAR_SUFFIXES
    )


def _remove_temp_db(temp_db: Path, label: str) -> None:
    """임시 DB와 -wal/-shm 짝 파일을 함께 지운다.

    WAL 원본의 backup 사본은 WAL 표시를 물려받는다. 이 사본을 읽기 전용으로
    열면 SQLite가 짝 파일을 만들고, 닫을 때 지우지 못한다.
    """
    for path in (temp_db, *_temp_db_sidecars(temp_db)):
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            _logger.warning("%s 정리 실패: %s", label, exc)


def cleanup_stale_backup_sidecars() -> None:
    """v4.0까지의 백업 검증이 남긴 임시 DB 짝 파일만 골라 지운다.

    짝 .db가 남은 묶음(비정상 종료 흔적)과 내용이 있는 -wal은 건드리지 않는다.
    읽기 전용 검증이 만든 -wal은 항상 비어 있다. 실패는 시작을 막지 않는다.
    """
    for folder, prefix in (
        (APP_DIR, ".backup-validate-"),
        (APP_DIR / "backups", ".auto-snapshot-"),
    ):
        try:
            temp_dbs = {
                sidecar.with_name(sidecar.name[:-len(suffix)])
                for suffix in _TEMP_DB_SIDECAR_SUFFIXES
                for sidecar in folder.glob(f"{prefix}*.db{suffix}")
            }
        except OSError as exc:
            _logger.warning("백업 임시 짝 파일 검색 실패: %s", exc)
            continue
        for temp_db in sorted(temp_dbs):
            wal, shm = _temp_db_sidecars(temp_db)
            try:
                if temp_db.exists():
                    continue
                if wal.exists() and wal.stat().st_size != 0:
                    continue
            except OSError as exc:
                _logger.warning("백업 임시 짝 파일 확인 실패: %s", exc)
                continue
            for sidecar in (wal, shm):
                try:
                    if sidecar.exists():
                        sidecar.unlink()
                except OSError as exc:
                    _logger.warning("백업 임시 짝 파일 정리 실패: %s", exc)


def validate_backup_bundle(path: Path) -> dict:
    """자동백업 묶음을 변경 없이 완전 검증하고 manifest를 반환한다."""
    bundle_path = validate_app_path(Path(path), "자동백업")
    temp_db = None
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            expected = {"calendar.db", ".salt", "manifest.json"}
            if len(names) != 3 or set(names) != expected:
                raise ValueError("자동백업 구성 파일이 올바르지 않습니다.")
            if archive.testzip() is not None:
                raise ValueError("자동백업 압축 데이터가 손상되었습니다.")
            manifest_bytes = archive.read("manifest.json")
            if len(manifest_bytes) > 64 * 1024:
                raise ValueError("자동백업 manifest가 너무 큽니다.")
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            salt = archive.read(".salt")
            if len(salt) != 32:
                raise ValueError("자동백업 salt가 올바르지 않습니다.")

            with tempfile.NamedTemporaryFile(
                    prefix=".backup-validate-", suffix=".db",
                    dir=APP_DIR, delete=False
            ) as temp_file:
                temp_db = Path(temp_file.name)
                with archive.open("calendar.db", "r") as db_member:
                    shutil.copyfileobj(db_member, temp_file)

        if not isinstance(manifest, dict):
            raise ValueError("자동백업 manifest 형식이 올바르지 않습니다.")
        if (
            manifest.get("format") != AUTO_BACKUP_FORMAT
            or manifest.get("format_version") != AUTO_BACKUP_FORMAT_VERSION
            or manifest.get("recovery_scope")
            != "same-machine-same-windows-user"
        ):
            raise ValueError("지원하지 않는 자동백업 형식입니다.")

        db_info = manifest.get("database")
        salt_info = manifest.get("salt")
        if not isinstance(db_info, dict) or not isinstance(salt_info, dict):
            raise ValueError("자동백업 manifest 항목이 올바르지 않습니다.")
        db_size, db_hash = _file_size_and_sha256(temp_db)
        if (
            db_info.get("name") != "calendar.db"
            or db_info.get("size") != db_size
            or db_info.get("sha256") != db_hash
            or salt_info.get("name") != ".salt"
            or salt_info.get("size") != len(salt)
            or salt_info.get("sha256") != _bytes_sha256(salt)
        ):
            raise ValueError("자동백업 hash 검증에 실패했습니다.")

        with _connection(
                temp_db, enable_wal=False, read_only=True
        ) as conn:
            checks = [
                row[0] for row in conn.execute("PRAGMA integrity_check")
            ]
            if checks != ["ok"]:
                raise sqlite3.DatabaseError(
                    "자동백업 DB 무결성 검사에 실패했습니다."
                )
            version = int(
                conn.execute("PRAGMA user_version").fetchone()[0]
            )
        if manifest.get("schema_version") != version:
            raise ValueError("자동백업 스키마 버전이 일치하지 않습니다.")

        token = manifest.get("key_check")
        if not isinstance(token, str):
            raise ValueError("자동백업 키 확인값이 없습니다.")
        plaintext = Fernet(security.derive_key(salt)).decrypt(
            token.encode("ascii")
        )
        if plaintext != _AUTO_BACKUP_KEY_CHECK:
            raise ValueError("현재 Windows 환경의 자동백업이 아닙니다.")
        return manifest
    except (
        zipfile.BadZipFile, json.JSONDecodeError, UnicodeError,
        InvalidToken, KeyError, TypeError,
    ) as exc:
        raise ValueError("자동백업 검증에 실패했습니다.") from exc
    finally:
        if temp_db is not None:
            _remove_temp_db(temp_db, "자동백업 검증 임시파일")


def _create_auto_backup_bundle(target: Path, salt: bytes) -> None:
    target = validate_app_path(target, "자동백업")
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path = None
    archive_path = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=".auto-snapshot-", suffix=".db",
                dir=target.parent, delete=False
        ) as snapshot_file:
            snapshot_path = Path(snapshot_file.name)

        with _connection() as source:
            _create_verified_snapshot(source, snapshot_path)
        with _connection(
                snapshot_path, enable_wal=False, read_only=True
        ) as snapshot:
            version = int(
                snapshot.execute("PRAGMA user_version").fetchone()[0]
            )
            checks = [
                row[0] for row in snapshot.execute("PRAGMA integrity_check")
            ]
            if checks != ["ok"]:
                raise sqlite3.DatabaseError(
                    "자동백업 DB 무결성 검사에 실패했습니다."
                )

        db_size, db_hash = _file_size_and_sha256(snapshot_path)
        manifest = {
            "format": AUTO_BACKUP_FORMAT,
            "format_version": AUTO_BACKUP_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "app_version": APP_VERSION,
            "schema_version": version,
            "recovery_scope": "same-machine-same-windows-user",
            "database": {
                "name": "calendar.db",
                "size": db_size,
                "sha256": db_hash,
            },
            "salt": {
                "name": ".salt",
                "size": len(salt),
                "sha256": _bytes_sha256(salt),
            },
            "key_check": Fernet(security.derive_key(salt)).encrypt(
                _AUTO_BACKUP_KEY_CHECK
            ).decode("ascii"),
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        with tempfile.NamedTemporaryFile(
                prefix=f".{target.name}.", suffix=".tmp",
                dir=target.parent, delete=False
        ) as archive_file:
            archive_path = Path(archive_file.name)
        with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_STORED
        ) as archive:
            archive.write(snapshot_path, "calendar.db")
            archive.writestr(".salt", salt)
            archive.writestr("manifest.json", manifest_bytes)
        with open(archive_path, "rb+") as archive_file:
            archive_file.flush()
            os.fsync(archive_file.fileno())

        validate_backup_bundle(archive_path)
        if security.read_existing_salt() != salt:
            raise ValueError("자동백업 중 salt가 변경되었습니다.")
        if target.exists():
            raise FileExistsError("자동백업 대상이 이미 존재합니다.")
        os.replace(archive_path, target)
        archive_path = None
    finally:
        if snapshot_path is not None:
            _remove_temp_db(snapshot_path, "자동백업 임시파일")
        if archive_path is not None:
            try:
                if archive_path.exists():
                    archive_path.unlink()
            except OSError as exc:
                _logger.warning("자동백업 임시파일 정리 실패: %s", exc)


def _backup_salt(report: DataHealthReport) -> bytes:
    """검증된 데이터셋의 salt를 읽고, 암호문이 없을 때만 최초 생성한다."""
    try:
        return security.read_existing_salt()
    except FileNotFoundError:
        if report.encrypted_count:
            raise
        return security.create_initial_salt()


def backup_before_v35() -> bool:
    """v3.5 첫 실행 전 기존 DB+salt를 회전하지 않는 묶음으로 보존한다."""
    if not DB_FILE.exists():
        return False
    report = inspect_startup_data_health()
    if not report.ok:
        raise DataHealthError(report)

    backup_dir = validate_app_path(APP_DIR / "backups", "백업 폴더")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for existing in sorted(
        backup_dir.glob("calendar_pre_v35_*.cnbak")
    ):
        try:
            validate_backup_bundle(existing)
            return False
        except (OSError, ValueError, sqlite3.Error):
            continue

    salt = _backup_salt(report)
    now = datetime.now()
    target = backup_dir / (
        f"calendar_pre_v35_{now:%Y%m%d_%H%M%S}_"
        f"{uuid.uuid4().hex[:8]}.cnbak"
    )
    _create_auto_backup_bundle(target, salt)
    audit("v3.5 최초 실행 전 백업", "성공")
    return True


def backup_before_operation(operation: str) -> bool:
    """가져오기·초기화 전에 회전하지 않는 현재 상태 묶음을 만든다."""
    if operation not in {"import", "reset", "privacy_pin"}:
        raise ValueError("지원하지 않는 보호 백업 작업입니다.")
    if not DB_FILE.exists():
        return True
    report = inspect_startup_data_health()
    if not report.ok:
        raise DataHealthError(report)

    backup_dir = validate_app_path(APP_DIR / "backups", "백업 폴더")
    backup_dir.mkdir(parents=True, exist_ok=True)
    salt = _backup_salt(report)
    now = datetime.now()
    target = backup_dir / (
        f"calendar_before_{operation}_{now:%Y%m%d_%H%M%S}_"
        f"{uuid.uuid4().hex[:8]}.cnbak"
    )
    _create_auto_backup_bundle(target, salt)
    audit(f"{operation} 전 보호 백업", "성공")
    return True


def _create_verified_snapshot(
        source: sqlite3.Connection, target_path: Path
) -> None:
    """Connection.backup → quick_check → 원자 교체 순서로 스냅샷을 만든다."""
    target = validate_app_path(Path(target_path), "백업")
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
            prefix=f".{target.name}.", suffix=".tmp",
            dir=target.parent, delete=False
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with _connection(temp_path, enable_wal=False) as destination:
            source.backup(destination)
        if not _snapshot_is_valid(temp_path):
            raise sqlite3.DatabaseError(
                "생성된 백업의 SQLite 무결성 검사에 실패했습니다."
            )
        os.replace(temp_path, target)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError as exc:
            _logger.warning("임시 백업 파일 정리 실패: %s", exc)


def backup_before_migration() -> bool:
    """구 DB→현재 스키마 전 최신 원본을 버전별 별도 스냅샷으로 보존한다.

    스냅샷을 만들지 못하면 예외를 전파하여 호출자가 마이그레이션을 중단하게
    한다. 기존 스냅샷은 검증된 최신 임시 스냅샷으로만 원자 교체하므로 실패
    시에도 그대로 남는다. 신규 DB(v0)와 이미 최신인 DB는 별도
    스냅샷 없이 정상 진행한다.
    """
    if not DB_FILE.exists():
        return False

    try:
        with _connection() as source:
            version = source.execute("PRAGMA user_version").fetchone()[0]
            if not 0 < version < CURRENT_SCHEMA_VERSION:
                return False

            backup_dir = validate_app_path(APP_DIR / "backups", "백업 폴더")
            backup_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = (
                backup_dir
                / f"calendar_pre_v{CURRENT_SCHEMA_VERSION}_v{version}.db"
            )
            _create_verified_snapshot(source, snapshot_path)
            if not _snapshot_is_valid(
                snapshot_path, expected_version=version
            ):
                raise sqlite3.DatabaseError(
                    "마이그레이션 전 백업의 검증에 실패했습니다."
                )

        audit(
            f"v{CURRENT_SCHEMA_VERSION} 마이그레이션 전 백업", "성공"
        )
        return True
    except (sqlite3.Error, OSError, ValueError) as exc:
        audit(
            f"v{CURRENT_SCHEMA_VERSION} 마이그레이션 전 백업",
            f"실패: {exc}",
        )
        raise


def backup_database() -> bool:
    """같은 PC 복구용 DB+salt 일일 묶음을 만들고 최대 5일 보존한다."""
    try:
        if not DB_FILE.exists():
            return False

        backup_dir = validate_app_path(APP_DIR / "backups", "백업 폴더")
        backup_dir.mkdir(parents=True, exist_ok=True)
        report = inspect_startup_data_health()
        if not report.ok:
            return False
        salt = _backup_salt(report)
        now = datetime.now()
        date_prefix = f"calendar_auto_{now:%Y%m%d}_"
        existing_today = sorted(
            backup_dir.glob(f"{date_prefix}*.cnbak")
        )
        has_valid_today = False
        for existing in existing_today:
            try:
                validate_backup_bundle(existing)
                has_valid_today = True
                break
            except (OSError, ValueError, sqlite3.Error):
                continue

        if not has_valid_today:
            target = backup_dir / (
                f"{date_prefix}{now:%H%M%S}_"
                f"{uuid.uuid4().hex[:8]}.cnbak"
            )
            _create_auto_backup_bundle(target, salt)

        valid_backups = []
        for path in sorted(backup_dir.glob("calendar_auto_*.cnbak")):
            try:
                validate_backup_bundle(path)
                valid_backups.append(path)
            except (OSError, ValueError, sqlite3.Error):
                continue
        while len(valid_backups) > AUTO_BACKUP_KEEP_DAYS:
            try:
                valid_backups[0].unlink()
                valid_backups.pop(0)
            except OSError as exc:
                _logger.warning("자동백업 보존기간 정리 실패: %s", exc)
                break

        audit("자동 백업", "성공")
        return True
    except (sqlite3.Error, OSError, ValueError) as exc:
        audit("자동 백업", f"실패: {exc}")
        return False


def optimize_database() -> None:
    """SQLite VACUUM 수행"""
    with _connection() as conn:
        try:
            conn.execute("VACUUM")
            audit("DB 최적화(VACUUM)", "성공")
        except sqlite3.Error as e:
            audit("DB 최적화(VACUUM)", f"실패: {e}")
            raise


# ─── Factory Reset ────────────────────────────────────────────
def reset_database() -> None:
    """DB 파일 삭제 후 새 설치와 같은 기본값(기본 크기, 바로가기 켜짐)으로 재생성"""
    if DB_FILE.exists():
        DB_FILE.unlink()
    migrate(initial_calendar_scale=DEFAULT_CALENDAR_SCALE)
    upgrade_privacy_pin()
