"""v4.1 일정 저장(DB v18 마이그레이션·API·Export v3) 회귀. 합성 데이터만 쓴다."""
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import database as db
import security
from schedule_rules import ScheduleOptions

FIXTURE = Path(__file__).parent / "fixtures" / "schema_v17.sql"
V18_COLUMNS = ["start_time", "end_date", "repeat_rule", "repeat_until", "repeat_skip", "alarm_before"]


def _seed_v17(app_dir):
    """v4.0a와 같은 v17 DB를 만든다(고정 DDL + 기존 사용 흔적 + 형식이 다른 옛 날짜)."""
    db_file = app_dir / "calendar.db"
    for path in (db_file, app_dir / "calendar.db-wal", app_dir / "calendar.db-shm"):
        if path.exists():
            path.unlink()
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(FIXTURE.read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
            [
                ("2026-10-01", security.encrypt("월간 업무 계획 점검"), "2026-09-30 09:00:00", "#4CC9F0"),
                ("2026-10-15", security.encrypt("📌 보고서 초안 검토"), "2026-10-14 18:00:00", "#FF6B6B"),
                ("2026-7-1", security.encrypt("형식이 다른 옛 날짜"), "2026-06-30 08:00:00", "#FFD166"),
            ],
        )
        conn.execute("INSERT INTO memos (date, content, updated_at) VALUES (?, ?, ?)",
                     ("2026-10-15", security.encrypt("회의 자료"), "2026-10-15 08:00:00"))
        conn.execute("INSERT INTO sticky_notes (content) VALUES (?)", (security.encrypt("스티키"),))
        conn.execute("INSERT INTO dday_widgets (name, target_date) VALUES (?, ?)",
                     (security.encrypt("마감"), "2026-12-31"))
        conn.execute("INSERT INTO focus_widgets (goal, created_at) VALUES (?, ?)",
                     (security.encrypt("집중"), "2026-10-15 09:00:00"))
        conn.execute(
            "INSERT INTO focus_sessions (widget_id, goal, started_at, ended_at, created_at) VALUES (1, ?, ?, ?, ?)",
            (security.encrypt("기록"), "2026-10-15 09:00:00", "2026-10-15 09:25:00", "2026-10-15 09:25:00"))
        conn.execute("UPDATE shortcuts SET name = ?, path = ? WHERE id = 1", ("업무", "C:/업무"))
        conn.execute("PRAGMA user_version = 17")
        conn.commit()
    finally:
        conn.close()
    return db_file


def _raw_dump(db_file):
    """모든 표의 v17 열 값을 rowid 순서로 그대로 읽는다(v18 새 열은 뺀다)."""
    conn = sqlite3.connect(f"{Path(db_file).as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        dump = {}
        for table in tables:  # 표·열 이름은 sqlite_master·table_info에서 온 값이다
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                       if row[1] not in V18_COLUMNS]
            dump[table] = conn.execute(
                f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid").fetchall()
        return dump
    finally:
        conn.close()


def test_first_start_on_v17_adds_columns_without_touching_existing_values(app_dir):
    import main as app_main

    db_file = _seed_v17(app_dir)
    before = _raw_dump(db_file)
    salt = security.SALT_FILE.read_bytes()

    assert app_main._initialize_database() is True

    assert _raw_dump(db_file) == before
    assert security.SALT_FILE.read_bytes() == salt
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
        columns = [row[1] for row in conn.execute("PRAGMA table_info(schedules)")]
        assert columns == ["id", "date", "content", "created_at", "color", *V18_COLUMNS]
        rows = conn.execute(
            "SELECT start_time, end_date, repeat_rule, repeat_until, repeat_skip, alarm_before FROM schedules"
        ).fetchall()
        assert [tuple(row) for row in rows] == [("", "", "", "", "", None)] * 3
    snapshot = app_dir / "backups" / "calendar_pre_v18_v17.db"
    assert snapshot.is_file()
    assert _raw_dump(snapshot) == before
    assert db.get_schedules("2026-10-15")[0]["content"] == "📌 보고서 초안 검토"
    assert db.get_schedules("2026-7-1")[0]["content"] == "형식이 다른 옛 날짜"


def test_v18_migration_is_idempotent_and_accepts_version_rolled_back(app_dir):
    _seed_v17(app_dir)
    db.migrate()
    db.migrate()
    with db._connection() as conn:
        conn.execute("PRAGMA user_version = 17")  # 외부 도구로 버전만 내린 경우
        conn.commit()
    db.migrate()
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")][5:] == V18_COLUMNS


def test_v18_migration_failure_rolls_back_every_column(app_dir, monkeypatch):
    db_file = _seed_v17(app_dir)
    before = _raw_dump(db_file)
    broken = list(db.SCHEDULE_V18_COLUMNS)
    # 기본값 없는 NOT NULL 열은 행이 있는 표에 더할 수 없어 SQLite가 거절한다(세 번째 열에서 실패).
    broken[2] = ("repeat_rule", "ALTER TABLE schedules ADD COLUMN repeat_rule TEXT NOT NULL")
    monkeypatch.setattr(db, "SCHEDULE_V18_COLUMNS", tuple(broken))

    with pytest.raises(sqlite3.Error):
        db.migrate()

    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")] == [
            "id", "date", "content", "created_at", "color"]
    assert _raw_dump(db_file) == before


def test_fresh_and_reset_databases_get_the_same_v18_schema(app_dir):
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")][5:] == V18_COLUMNS
    db.reset_database()
    with db._connection(enable_wal=False, read_only=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
        assert [row[1] for row in conn.execute("PRAGMA table_info(schedules)")][5:] == V18_COLUMNS


def test_health_reports_newer_schema(app_dir):
    with db._connection() as conn:
        conn.execute("PRAGMA user_version = 19")
        conn.commit()
    report = db.inspect_startup_data_health()
    assert (report.ok, report.code, report.version) == (False, "schema_newer", 19)


def test_health_rejects_v18_without_new_columns(app_dir):
    db_file = _seed_v17(app_dir)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("PRAGMA user_version = 18")
        conn.commit()
    finally:
        conn.close()
    report = db.inspect_startup_data_health()
    assert (report.ok, report.code) == (False, "schema_invalid")


def test_newer_schema_message_explains_update():
    import main as app_main
    _title, content = app_main._data_health_error_message("schema_newer")
    assert "더 새 버전" in content
    assert "변경하지 않았습니다" in content


def test_v17_upgrade_with_legacy_key_rows_keeps_plaintext(app_dir):
    """Review Focus 2: 구 키 암호문 재암호화와 v18 열 추가가 같은 시작에서 일어나도 본문이 같다."""
    import main as app_main

    db_file = _seed_v17(app_dir)
    legacy = Fernet(security.derive_legacy_key(security.read_existing_salt())).encrypt(
        "구 키 일정".encode("utf-8")).decode("ascii")
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-10-20", legacy, "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    finally:
        conn.close()
    security._fernet_cache = None
    security._legacy_fernet_cache = None

    assert app_main._initialize_database() is True

    rows = db.get_schedules("2026-10-20")
    assert [row["content"] for row in rows] == ["구 키 일정"]
    assert rows[0]["options"] == ScheduleOptions()
