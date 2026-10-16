"""v4.1 일정 저장(DB v18 마이그레이션·API·Export v3) 회귀. 합성 데이터만 쓴다."""
import logging
import sqlite3
import time
from datetime import datetime
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


def test_add_with_options_and_read_back(app_dir):
    sid = db.add_schedule("2026-10-15", "부서 회의", "#4CC9F0",
                          options=ScheduleOptions(start_time="15:00", repeat_rule="weekly", alarm_before=10))
    entry = db.get_schedules("2026-10-22")[0]
    assert (entry["id"], entry["date"], entry["occurrence_date"], entry["content"]) == (
        sid, "2026-10-15", "2026-10-22", "부서 회의")
    assert entry["options"] == ScheduleOptions(start_time="15:00", repeat_rule="weekly", alarm_before=10)
    assert (entry["shows_time"], entry["start_time"], entry["span_start"], entry["span_end"]) == (
        True, "15:00", "2026-10-22", "2026-10-22")
    assert db.get_schedules("2026-10-21") == []


def test_invalid_options_write_nothing(app_dir):
    with pytest.raises(ValueError):
        db.add_schedule("2026-10-15", "x", options=ScheduleOptions(repeat_rule="daily", end_date="2026-10-16"))
    with db._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0


def test_day_order_all_day_first_then_time(app_dir):
    late = db.add_schedule("2026-10-15", "16시", options=ScheduleOptions(start_time="16:00"))
    allday = db.add_schedule("2026-10-15", "종일")
    early = db.add_schedule("2026-10-15", "9시", options=ScheduleOptions(start_time="09:00"))
    period = db.add_schedule("2026-10-14", "기간", options=ScheduleOptions(start_time="08:00", end_date="2026-10-16"))
    assert [e["id"] for e in db.get_schedules("2026-10-15")] == [allday, period, early, late]
    first_day = db.get_schedules("2026-10-14")
    assert [e["id"] for e in first_day] == [period]
    assert first_day[0]["shows_time"] is True
    assert db.get_schedules("2026-10-15")[1]["shows_time"] is False
    assert (db.get_schedules("2026-10-15")[1]["span_start"],
            db.get_schedules("2026-10-15")[1]["span_end"]) == ("2026-10-14", "2026-10-16")


def test_get_occurrences_expands_repeat_and_period_and_keeps_legacy_strings(app_dir):
    """Review Focus 1: 형식이 다른 옛 날짜는 지금처럼 문자열 그대로만 맞춘다(멈추지 않음)."""
    weekly = db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(start_time="10:00", repeat_rule="weekly"))
    db.add_schedule("2026-10-30", "출장", options=ScheduleOptions(end_date="2026-11-02"))
    with db._connection() as conn:
        conn.execute("INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                     ("2026-10-7", security.encrypt("옛 형식"), "2026-01-01 00:00:00", "#FFD166"))
        conn.commit()
    month = db.get_occurrences("2026-10-01", "2026-10-31")
    assert sorted(day for day, entries in month.items() if any(e["id"] == weekly for e in entries)) == [
        "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]
    assert [e["span_end"] for e in month["2026-10-31"]] == ["2026-11-02"]
    assert "2026-10-7" not in month
    assert [e["content"] for e in db.get_schedules("2026-10-7")] == ["옛 형식"]


def test_skip_occurrence_only_hides_that_day(app_dir):
    sid = db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(repeat_rule="weekly"))
    db.skip_schedule_occurrence(sid, "2026-10-12")
    assert db.get_schedules("2026-10-12") == []
    assert [e["id"] for e in db.get_schedules("2026-10-19")] == [sid]
    assert db.get_schedules("2026-10-19")[0]["options"].repeat_skip == ("2026-10-12",)
    with pytest.raises(ValueError, match="그 날"):
        db.skip_schedule_occurrence(sid, "2026-10-13")
    single = db.add_schedule("2026-10-05", "하루")
    with pytest.raises(ValueError, match="반복"):
        db.skip_schedule_occurrence(single, "2026-10-05")


def test_update_options_replaces_all_fields_and_validates_against_start(app_dir):
    sid = db.add_schedule("2026-10-15", "회의", options=ScheduleOptions(start_time="09:00", alarm_before=10))
    db.update_schedule(sid, options=ScheduleOptions(repeat_rule="daily"))
    assert db.get_schedules("2026-10-16")[0]["options"] == ScheduleOptions(repeat_rule="daily")
    # 둘 다 "반복 없는 일정에 반복 끝 날짜" 규칙이 아니라 저장된 시작일(10-15)과의 비교에서 걸린다.
    for before_start in (ScheduleOptions(end_date="2026-10-14"),
                         ScheduleOptions(repeat_rule="daily", repeat_until="2026-10-01")):
        with pytest.raises(ValueError):
            db.update_schedule(sid, content="바뀌면 안 됨", options=before_start)
        assert db.get_schedules("2026-10-15")[0]["content"] == "회의"
        assert db.get_schedules("2026-10-16")[0]["options"] == ScheduleOptions(repeat_rule="daily")
    db.update_schedule(sid, options=ScheduleOptions())
    assert db.get_schedules("2026-10-16") == []
    with pytest.raises(ValueError, match="없습니다"):
        db.update_schedule(9999, options=ScheduleOptions(start_time="09:00"))


def test_get_alarm_occurrences_window_and_order(app_dir):
    a = db.add_schedule("2026-10-15", "부서 회의", "#4CC9F0",
                        options=ScheduleOptions(start_time="15:00", alarm_before=10))
    b = db.add_schedule("2026-10-16", "보고 마감", options=ScheduleOptions(alarm_before=1440))
    db.add_schedule("2026-10-15", "알림 없음", options=ScheduleOptions(start_time="15:00"))
    items = db.get_alarm_occurrences(datetime(2026, 10, 15, 8, 0), datetime(2026, 10, 15, 15, 0))
    assert [(i.schedule_id, i.occurrence_date, i.due) for i in items] == [
        (b, "2026-10-16", datetime(2026, 10, 15, 9, 0)),
        (a, "2026-10-15", datetime(2026, 10, 15, 14, 50))]
    assert (items[1].content, items[1].start_time, items[1].color) == ("부서 회의", "15:00", "#4CC9F0")
    assert db.get_alarm_occurrences(datetime(2026, 10, 15, 15, 0), datetime(2026, 10, 15, 15, 0)) == []


def test_has_schedule_alarms(app_dir):
    assert db.has_schedule_alarms() is False
    sid = db.add_schedule("2026-10-15", "알림", options=ScheduleOptions(alarm_before=0))
    assert db.has_schedule_alarms() is True
    db.update_schedule(sid, options=ScheduleOptions())
    assert db.has_schedule_alarms() is False


def test_search_results_carry_period_and_repeat(app_dir):
    db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(repeat_rule="weekly"))
    result = db.search_all("주간")[0]
    assert (result["date"], result["repeat_rule"], result["end_date"]) == ("2026-10-05", "weekly", "")


def test_month_expansion_stays_fast_with_many_repeats(app_dir):
    with db._connection() as conn:
        conn.executemany(
            "INSERT INTO schedules (date, content, created_at, color, repeat_rule) VALUES (?, ?, ?, ?, ?)",
            [("2025-01-01", security.encrypt(f"반복 {i}"), "2025-01-01 00:00:00", "#FFD166", "daily")
             for i in range(1000)])
        conn.commit()
    started = time.perf_counter()
    month = db.get_occurrences("2026-10-01", "2026-10-31")
    assert len(month["2026-10-15"]) == 1000
    assert time.perf_counter() - started < 5.0


_OPTION_COLUMNS = "start_time, end_date, repeat_rule, repeat_until, repeat_skip, alarm_before"


def _option_columns(schedule_id):
    with db._connection() as conn:
        return tuple(conn.execute(
            f"SELECT {_OPTION_COLUMNS} FROM schedules WHERE id = ?", (schedule_id,)).fetchone())


def test_content_or_color_update_keeps_all_option_columns(app_dir):
    sid = db.add_schedule("2026-10-05", "주간 회의", "#4CC9F0", options=ScheduleOptions(
        start_time="15:00", repeat_rule="weekly", repeat_until="2026-12-31",
        repeat_skip=("2026-10-12",), alarm_before=10))
    before = _option_columns(sid)
    assert before == ("15:00", "", "weekly", "2026-12-31", "2026-10-12", 10)

    db.update_schedule(sid, content="바뀐 본문")
    assert _option_columns(sid) == before
    db.update_schedule(sid, color="#FF6B6B")
    assert _option_columns(sid) == before
    db.update_schedule(sid, content="또 바뀐 본문", color="#06D6A0")
    assert _option_columns(sid) == before

    entry = db.get_schedules("2026-10-19")[0]
    assert (entry["content"], entry["color"]) == ("또 바뀐 본문", "#06D6A0")
    assert entry["options"] == ScheduleOptions(
        start_time="15:00", repeat_rule="weekly", repeat_until="2026-12-31",
        repeat_skip=("2026-10-12",), alarm_before=10)


def test_skip_occurrence_changes_only_repeat_skip(app_dir):
    sid = db.add_schedule("2026-10-05", "주간 회의", "#4CC9F0", options=ScheduleOptions(
        start_time="15:00", repeat_rule="weekly", repeat_until="2026-12-31", alarm_before=10))
    with db._connection() as conn:
        before = tuple(conn.execute(
            "SELECT date, content, created_at, color, start_time, end_date, repeat_rule, "
            "repeat_until, alarm_before FROM schedules WHERE id = ?", (sid,)).fetchone())
    db.skip_schedule_occurrence(sid, "2026-10-12")
    db.skip_schedule_occurrence(sid, "2026-10-26")
    with db._connection() as conn:
        after = tuple(conn.execute(
            "SELECT date, content, created_at, color, start_time, end_date, repeat_rule, "
            "repeat_until, alarm_before FROM schedules WHERE id = ?", (sid,)).fetchone())
    assert after == before
    assert _option_columns(sid)[4] == "2026-10-12,2026-10-26"
    assert db.get_schedules("2026-10-05")[0]["content"] == "주간 회의"


def _insert_raw_schedule(date, content, **columns):
    names = ["date", "content", "created_at", "color", *columns]
    with db._connection() as conn:
        cur = conn.execute(
            f"INSERT INTO schedules ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
            [date, security.encrypt(content), "2026-01-01 00:00:00", "#FFD166", *columns.values()])
        conn.commit()
        return cur.lastrowid


def test_malformed_start_date_on_repeat_or_period_row_does_not_break_reads(app_dir, caplog):
    healthy = db.add_schedule("2026-02-02", "정상 반복", options=ScheduleOptions(repeat_rule="weekly"))
    bad_repeat = _insert_raw_schedule("2026-02-30", "깨진 반복", repeat_rule="weekly", alarm_before=0)
    bad_period = _insert_raw_schedule("2026-02-30", "깨진 기간", end_date="2026-03-05")
    with caplog.at_level(logging.WARNING, logger="app_error"):
        month = db.get_occurrences("2026-02-01", "2026-03-31")
        assert db.get_alarm_occurrences(datetime(2026, 2, 1), datetime(2026, 3, 31)) == []
    assert sorted(day for day, entries in month.items() if any(e["id"] == healthy for e in entries)) == [
        "2026-02-02", "2026-02-09", "2026-02-16", "2026-02-23", "2026-03-02", "2026-03-09",
        "2026-03-16", "2026-03-23", "2026-03-30"]
    fallback = {e["id"]: e for e in month["2026-02-30"]}
    assert set(fallback) == {bad_repeat, bad_period}
    for entry in fallback.values():
        assert (entry["options"].end_date, entry["options"].repeat_rule) == ("", "")
        assert (entry["span_start"], entry["span_end"], entry["occurrence_date"]) == ("2026-02-30",) * 3
        assert entry["content"] in ("깨진 반복", "깨진 기간")
    warned = " ".join(r.getMessage() for r in caplog.records if r.name == "app_error")
    assert f"id={bad_repeat}" in warned and f"id={bad_period}" in warned
    assert f"id={healthy}" not in warned


def test_non_iso_query_date_matches_legacy_row_without_warning(app_dir, caplog):
    _insert_raw_schedule("2026-10-7", "옛 형식")
    db.add_schedule("2026-10-05", "주간 회의", options=ScheduleOptions(repeat_rule="weekly"))
    db.add_schedule("2026-10-05", "출장", options=ScheduleOptions(end_date="2026-10-09"))
    db.add_schedule("2026-10-05", "하루")
    with caplog.at_level(logging.DEBUG, logger="app_error"):
        entries = db.get_schedules("2026-10-7")
    assert [e["content"] for e in entries] == ["옛 형식"]
    assert (entries[0]["occurrence_date"], entries[0]["span_start"], entries[0]["span_end"]) == ("2026-10-7",) * 3
    assert [r for r in caplog.records if r.name == "app_error"] == []


def test_alarm_lower_bound_is_exclusive_and_upper_bound_inclusive(app_dir):
    sid = db.add_schedule("2026-10-15", "회의", options=ScheduleOptions(start_time="15:00", alarm_before=10))
    due = datetime(2026, 10, 15, 14, 50)
    assert db.get_alarm_occurrences(due, datetime(2026, 10, 15, 16, 0)) == []
    assert [i.due for i in db.get_alarm_occurrences(datetime(2026, 10, 15, 14, 49), due)] == [due]
    assert [i.schedule_id for i in db.get_alarm_occurrences(datetime(2026, 10, 15, 14, 49, 59), due)] == [sid]


def test_search_results_ignore_corrupt_end_date(app_dir):
    _insert_raw_schedule("2026-10-05", "깨진 기간", end_date="2026-10-01", repeat_rule="monthly")
    result = db.search_all("깨진")[0]
    assert (result["date"], result["end_date"], result["repeat_rule"]) == ("2026-10-05", "", "monthly")
