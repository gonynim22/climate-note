# tests/test_database.py - DB CRUD, 마이그레이션, 백업 테스트
import json
import shutil
import zipfile

import pytest
import security
import database as db


# ─── 마이그레이션 ─────────────────────────────────────────────

class TestMigration:
    def test_fresh_install_is_current_version(self, app_dir):
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION

    def test_fresh_has_color_column_in_schedules(self, app_dir):
        with db._connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(schedules)").fetchall()]
        assert "color" in cols

    def test_v7_to_v8_adds_color_column(self, app_dir):
        """v7 DB를 시뮬레이션 후 migrate() 실행 시 color 컬럼 추가"""
        with db._connection() as conn:
            conn.execute("DROP TABLE schedules")
            conn.execute("""
                CREATE TABLE schedules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # v13 휴지통 컬럼은 v7 시점에 없었으므로 제거 후 시뮬레이션
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 7")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(schedules)").fetchall()]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert "color" in cols
        assert version == db.CURRENT_SCHEMA_VERSION

    def test_fresh_has_trash_columns_in_sticky_notes(self, app_dir):
        with db._connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(sticky_notes)").fetchall()]
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_v12_to_v13_adds_trash_columns(self, app_dir):
        """v12 DB를 시뮬레이션 후 migrate() 실행 시 휴지통 컬럼 추가"""
        with db._connection() as conn:
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 12")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(sticky_notes)").fetchall()]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert "is_deleted" in cols and "deleted_at" in cols
        assert version == db.CURRENT_SCHEMA_VERSION

    def test_migrate_is_idempotent(self, app_dir):
        """migrate()를 두 번 호출해도 오류 없이 최신 버전 유지"""
        db.migrate()
        db.migrate()
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION

    def test_v7_to_v8_preserves_existing_data(self, app_dir):
        """v7→v8 마이그레이션 시 기존 일정 데이터와 암호화 내용 보존"""
        with db._connection() as conn:
            conn.execute("DROP TABLE schedules")
            conn.execute("""
                CREATE TABLE schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO schedules (date, content, created_at) VALUES (?, ?, ?)",
                ("2025-01-01", security.encrypt("기존 일정"), "2025-01-01 09:00:00")
            )
            # v13 휴지통 컬럼은 v7 시점에 없었으므로 제거 후 시뮬레이션
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 7")
            conn.commit()

        db.migrate()

        schedules = db.get_schedules("2025-01-01")
        assert len(schedules) == 1
        assert schedules[0]["content"] == "기존 일정"
        assert schedules[0]["color"] == "#FFD166"  # DEFAULT 값 자동 적용

    def test_idempotent_migration(self, app_dir):
        """migrate() 반복 호출 시 오류 없고 버전 유지"""
        db.migrate()
        db.migrate()
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION

    def test_all_tables_exist(self, app_dir):
        with db._connection() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        expected = {
            "schedules", "memos", "sticky_notes", "dday_widgets",
            "focus_widgets", "focus_sessions", "app_settings", "shortcuts",
        }
        assert expected.issubset(tables)

    def test_fresh_install_has_six_empty_shortcuts(self, app_dir):
        shortcuts = db.get_shortcuts()

        assert [s["id"] for s in shortcuts] == [1, 2, 3, 4, 5, 6]
        assert all(s["name"] == "" and s["path"] == "" for s in shortcuts)

    def test_migration_v15_adds_sixth_shortcut(self, app_dir):
        """app_dir 픽스처가 최신 migrate() 실행 → 바로가기 6개 존재."""
        rows = db.get_shortcuts()
        assert len(rows) == 6
        assert any(r["id"] == 6 for r in rows)

    def test_migration_v15_preserves_existing_and_idempotent(self, app_dir):
        """v14 상태(1~5만 존재)에서 migrate 시 기존 데이터 보존 + 멱등."""
        with db._connection() as conn:
            for i in range(1, 6):
                conn.execute(
                    "UPDATE shortcuts SET name=?, path=? WHERE id=?",
                    (f"name{i}", f"C:/app{i}.exe", i),
                )
            conn.execute("DELETE FROM shortcuts WHERE id = 6")
            conn.execute("PRAGMA user_version = 14")
            conn.commit()

        db.migrate()

        rows = {r["id"]: r for r in db.get_shortcuts()}
        assert len(rows) == 6
        assert rows[1]["name"] == "name1"
        assert rows[5]["path"] == "C:/app5.exe"
        assert rows[6]["name"] == ""
        assert rows[6]["path"] == ""

        # 멱등성: 다시 실행해도 6개 유지
        db.migrate()
        assert len(db.get_shortcuts()) == 6

    def test_migration_v16_adds_keep_on_show_desktop_default_on(self, app_dir):
        """app_dir 픽스처가 최신 migrate() 실행 → 최신 버전 + 기본 ON."""
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION
        assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"

    def test_migration_v16_preserves_existing_and_idempotent(self, app_dir):
        """v15 상태에서 사용자 설정 보존 + 멱등하게 v16 시드."""
        with db._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                (db.SETTING_APP_OPACITY, "55"),
            )
            conn.execute(
                "DELETE FROM app_settings WHERE key = ?",
                (db.SETTING_KEEP_ON_SHOW_DESKTOP,),
            )
            conn.execute("PRAGMA user_version = 15")
            conn.commit()

        db.migrate()

        assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "1"
        assert db.get_setting(db.SETTING_APP_OPACITY) == "55"  # 기존 설정 무손상
        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_SCHEMA_VERSION

        # 멱등: 사용자가 "0"으로 바꾼 상태에서 v15→v16 블록이 다시 실행돼도 값 보존
        db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
        with db._connection() as conn:
            conn.execute("PRAGMA user_version = 15")
            conn.commit()
        db.migrate()
        assert db.get_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP) == "0"
        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_SCHEMA_VERSION

    def test_migration_v17_seeds_settings_without_touching_schedules(self, app_dir):
        """v16→v17은 설정만 추가하고 일정 행 원문은 한 바이트도 바꾸지 않는다."""
        db.add_schedule("2026-07-20", "기존 노랑", "#FFD166")
        db.add_schedule("2026-07-21", "기존 파랑", "#4CC9F0")
        db.add_schedule("2026-07-22", "외부 색상", "#ABCDEF")

        with db._connection() as conn:
            before = [
                tuple(row)
                for row in conn.execute(
                    "SELECT id, date, content, created_at, color "
                    "FROM schedules ORDER BY id"
                ).fetchall()
            ]
            conn.execute(
                "DELETE FROM app_settings WHERE key IN (?, ?, ?, ?)",
                (*db.SCHEDULE_COLOR_SETTING_KEYS, db.SETTING_CALENDAR_POSITION_MODE),
            )
            conn.execute("PRAGMA user_version = 16")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            after = [
                tuple(row)
                for row in conn.execute(
                    "SELECT id, date, content, created_at, color "
                    "FROM schedules ORDER BY id"
                ).fetchall()
            ]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert after == before
        assert version == db.CURRENT_SCHEMA_VERSION
        assert db.get_schedule_palette() == db.DEFAULT_SCHEDULE_PALETTE
        assert (
            db.get_setting(db.SETTING_CALENDAR_POSITION_MODE)
            == db.DEFAULT_CALENDAR_POSITION_MODE
        )

    def test_migration_v17_preserves_custom_settings_and_is_idempotent(self, app_dir):
        custom = ("#FF9F68", "#80CFA9", "#B197FC")
        db.save_schedule_palette(custom)
        db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "free")
        with db._connection() as conn:
            conn.execute("PRAGMA user_version = 16")
            conn.commit()

        db.migrate()
        db.migrate()

        assert db.get_schedule_palette() == custom
        assert db.get_setting(db.SETTING_CALENDAR_POSITION_MODE) == "free"
        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_SCHEMA_VERSION

    def test_migration_v17_preserves_all_existing_user_tables_exactly(self, app_dir):
        """v16→v17에서 일정 외 메모·위젯·세션·바로가기 원문도 변하지 않는다."""
        db.add_schedule("2026-07-23", "보존 일정", "#4CC9F0")
        db.save_memo("2026-07-23", "보존 메모")
        note_id = db.create_sticky_note("memo", -320, 140, "#FFFA8E")
        db.update_sticky_note(note_id, content="\uf0c8 보존 할 일")
        dday_id = db.create_dday_widget("보존 D-Day", "2027-01-01", 30, 40)
        focus_id = db.create_focus_widget("보존 집중", "50/10", 50, 60)
        db.create_focus_session(
            focus_id, "보존 집중", "50/10", 50, 10,
            "2026-07-23 09:00:00", "2026-07-23 09:50:00",
            3000, True, 4, "알림",
        )
        db.update_shortcut(1, "보존 바로가기", "C:/Preserve/App.exe")
        db.save_setting(db.SETTING_APP_OPACITY, "73")

        user_tables = (
            "schedules", "memos", "sticky_notes", "dday_widgets",
            "focus_widgets", "focus_sessions", "shortcuts",
        )

        def _snapshot(conn):
            return {
                table: [
                    tuple(row)
                    for row in conn.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"  # noqa: S608
                    ).fetchall()
                ]
                for table in user_tables
            }

        with db._connection() as conn:
            conn.execute(
                "DELETE FROM app_settings WHERE key IN (?, ?, ?, ?)",
                (*db.SCHEDULE_COLOR_SETTING_KEYS, db.SETTING_CALENDAR_POSITION_MODE),
            )
            conn.execute("PRAGMA user_version = 16")
            before_tables = _snapshot(conn)
            before_settings = [
                tuple(row)
                for row in conn.execute(
                    "SELECT key, value FROM app_settings ORDER BY key"
                ).fetchall()
            ]
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            after_tables = _snapshot(conn)
            after_existing_settings = [
                tuple(row)
                for row in conn.execute(
                    "SELECT key, value FROM app_settings "
                    "WHERE key NOT IN (?, ?, ?, ?) ORDER BY key",
                    (*db.SCHEDULE_COLOR_SETTING_KEYS, db.SETTING_CALENDAR_POSITION_MODE),
                ).fetchall()
            ]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        assert after_tables == before_tables
        assert after_existing_settings == before_settings
        assert integrity == "ok"
        assert db.get_setting(db.SETTING_APP_OPACITY) == "73"
        assert db.get_schedule_palette() == db.DEFAULT_SCHEDULE_PALETTE

    def test_migrate_without_first_run_choice_keeps_sidebar_off(self, app_dir):
        # 처음 실행 크기 선택 없이 만든 DB(기존 이전 경로·합성 시험 DB)는 예전 값 그대로 꺼짐이다.
        # 새 설치·초기화의 켜짐 기본값은 tests/test_sidebar_default.py가 본다.
        assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "0"

    def test_fresh_install_app_font_is_malgun_gothic(self, app_dir):
        assert db.get_setting(db.SETTING_APP_FONT) == db.DEFAULT_APP_FONT

    def test_v8_to_v9_adds_shortcuts_and_preserves_data(self, app_dir):
        db.add_schedule("2026-04-21", "v2.6 이전 일정", "#4CC9F0")
        db.save_memo("2026-04-21", "v2.6 이전 메모")

        with db._connection() as conn:
            conn.execute("DROP TABLE IF EXISTS shortcuts")
            conn.execute("DELETE FROM app_settings WHERE key = ?", (db.SETTING_SHOW_SIDEBAR,))
            # v13 휴지통 컬럼은 v8 시점에 없었으므로 제거 후 시뮬레이션
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 8")
            conn.commit()

        db.migrate()

        shortcuts = db.get_shortcuts()
        assert [s["id"] for s in shortcuts] == [1, 2, 3, 4, 5, 6]
        assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "0"
        assert db.get_setting(db.SETTING_APP_FONT) == db.DEFAULT_APP_FONT
        assert db.get_schedules("2026-04-21")[0]["content"] == "v2.6 이전 일정"
        assert db.get_memo("2026-04-21") == "v2.6 이전 메모"

    def test_v9_to_v11_adds_app_font_and_preserves_data(self, app_dir):
        db.add_schedule("2026-04-22", "v2.7 이전 일정", "#FFD166")

        with db._connection() as conn:
            conn.execute("DELETE FROM app_settings WHERE key = ?", (db.SETTING_APP_FONT,))
            # v13 휴지통 컬럼은 v9 시점에 없었으므로 제거 후 시뮬레이션
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 9")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION
        assert db.get_setting(db.SETTING_APP_FONT) == db.DEFAULT_APP_FONT
        assert db.get_schedules("2026-04-22")[0]["content"] == "v2.7 이전 일정"

    def test_v10_to_v11_replaces_removed_font_settings(self, app_dir):
        removed_fonts = ["Pretendard", "Pretendard Variable", "Noto Sans KR"]

        for removed_font in removed_fonts:
            db.save_setting(db.SETTING_APP_FONT, removed_font)

            with db._connection() as conn:
                # v13 휴지통 컬럼은 v10 시점에 없었으므로 제거 후 시뮬레이션
                conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
                conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
                conn.execute("PRAGMA user_version = 10")
                conn.commit()

            db.migrate()

            with db._connection() as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == db.CURRENT_SCHEMA_VERSION
            assert db.get_setting(db.SETTING_APP_FONT) == db.DEFAULT_APP_FONT

    def test_v11_to_v12_adds_focus_tables_and_preserves_data(self, app_dir):
        db.add_schedule("2026-04-27", "v2.8 이전 일정", "#4CC9F0")
        with db._connection() as conn:
            conn.execute("DROP TABLE IF EXISTS focus_widgets")
            conn.execute("DROP TABLE IF EXISTS focus_sessions")
            # v13 휴지통 컬럼은 v11 시점에 없었으므로 제거 후 시뮬레이션
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN is_deleted")
            conn.execute("ALTER TABLE sticky_notes DROP COLUMN deleted_at")
            conn.execute("PRAGMA user_version = 11")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION
        assert {"focus_widgets", "focus_sessions"}.issubset(tables)
        assert db.get_schedules("2026-04-27")[0]["content"] == "v2.8 이전 일정"

    def test_v13_to_v15_adds_opacity_scale_and_shortcut_preserves_all_data(self, app_dir):
        db.add_schedule("2026-06-10", "v13 일정", "#FF6B6B")
        db.save_memo("2026-06-10", "v13 메모")
        db.save_setting(db.SETTING_SHOW_LUNAR, "1")
        with db._connection() as conn:
            conn.execute(
                "DELETE FROM app_settings WHERE key IN (?, ?)",
                (db.SETTING_APP_OPACITY, db.SETTING_CALENDAR_SCALE),
            )
            conn.execute("PRAGMA user_version = 13")
            conn.commit()

        db.migrate()

        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION
        assert db.get_setting(db.SETTING_APP_OPACITY) == db.DEFAULT_APP_OPACITY
        assert db.get_setting(db.SETTING_CALENDAR_SCALE) == db.DEFAULT_CALENDAR_SCALE
        assert db.get_schedules("2026-06-10")[0]["content"] == "v13 일정"
        assert db.get_schedules("2026-06-10")[0]["color"] == "#FF6B6B"
        assert db.get_memo("2026-06-10") == "v13 메모"
        assert db.get_setting(db.SETTING_SHOW_LUNAR) == "1"

    def test_v13_to_v15_idempotent_preserves_custom_values(self, app_dir):
        db.save_setting(db.SETTING_APP_OPACITY, "60")
        db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
        with db._connection() as conn:
            conn.execute("PRAGMA user_version = 13")
            conn.commit()

        db.migrate()
        db.migrate()

        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION
        assert db.get_setting(db.SETTING_APP_OPACITY) == "60"
        assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "large"

    def test_fresh_install_is_current_version_with_new_settings(self, app_dir):
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION
        assert db.get_setting(db.SETTING_APP_OPACITY) == db.DEFAULT_APP_OPACITY
        assert db.get_setting(db.SETTING_CALENDAR_SCALE) == db.DEFAULT_CALENDAR_SCALE

    def test_wal_mode_enabled(self, app_dir):
        with db._connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


# ─── 일정(Schedules) CRUD ────────────────────────────────────

class TestScheduleCRUD:
    def test_add_and_get(self, app_dir):
        sid = db.add_schedule("2025-03-15", "회의", "#FFD166")
        assert sid > 0
        result = db.get_schedules("2025-03-15")
        assert len(result) == 1
        assert result[0]["content"] == "회의"
        assert result[0]["color"] == "#FFD166"

    def test_default_color_applied(self, app_dir):
        db.add_schedule("2025-03-16", "기본")
        result = db.get_schedules("2025-03-16")
        assert result[0]["color"] == db.DEFAULT_SCHEDULE_COLOR

    def test_multiple_schedules_same_date(self, app_dir):
        db.add_schedule("2025-04-01", "일정1", "#FFD166")
        db.add_schedule("2025-04-01", "일정2", "#4CC9F0")
        db.add_schedule("2025-04-01", "일정3", "#FF6B6B")
        assert len(db.get_schedules("2025-04-01")) == 3

    def test_delete_schedule(self, app_dir):
        sid = db.add_schedule("2025-05-01", "삭제")
        db.delete_schedule(sid)
        assert db.get_schedules("2025-05-01") == []

    def test_delete_only_target(self, app_dir):
        sid1 = db.add_schedule("2025-05-02", "남길것")
        sid2 = db.add_schedule("2025-05-02", "지울것")
        db.delete_schedule(sid2)
        result = db.get_schedules("2025-05-02")
        assert len(result) == 1
        assert result[0]["id"] == sid1

    def test_delete_nonexistent_no_error(self, app_dir):
        db.delete_schedule(99999)  # 존재하지 않는 id → 오류 없어야 함

    def test_get_empty_date(self, app_dir):
        assert db.get_schedules("2099-12-31") == []

    def test_content_encrypted_in_db(self, app_dir):
        db.add_schedule("2025-06-01", "비밀 내용")
        with db._connection() as conn:
            row = conn.execute(
                "SELECT content FROM schedules WHERE date='2025-06-01'"
            ).fetchone()
        assert "비밀 내용" not in row["content"]

    def test_decryption_failed_flag(self, app_dir):
        """복호화 불가 데이터 삽입 시 _decryption_failed=True 반환"""
        with db._connection() as conn:
            conn.execute(
                "INSERT INTO schedules (date, content, created_at) VALUES (?, ?, ?)",
                ("2025-07-01", "완전히_잘못된_암호문_xyz", "2025-07-01 00:00:00")
            )
            conn.commit()
        result = db.get_schedules("2025-07-01")
        assert result[0]["_decryption_failed"] is True
        assert result[0]["content"] == "[복호화 오류]"

    def test_all_three_colors(self, app_dir):
        for color, _ in db.SCHEDULE_COLORS:
            db.add_schedule("2025-08-01", f"일정 {color}", color)
        result = db.get_schedules("2025-08-01")
        assert {s["color"] for s in result} == {c[0] for c in db.SCHEDULE_COLORS}


class TestSchedulePalette:
    def test_default_palette_keeps_three_canonical_slots(self, app_dir):
        assert len(db.SCHEDULE_COLOR_SLOTS) == 3
        assert db.SCHEDULE_COLOR_SLOTS == tuple(c[0] for c in db.SCHEDULE_COLORS)
        assert len(db.SCHEDULE_COLOR_OPTIONS) == 10
        assert len({c[0] for c in db.SCHEDULE_COLOR_OPTIONS}) == 10
        assert db.get_schedule_palette() == db.DEFAULT_SCHEDULE_PALETTE

    def test_save_palette_changes_display_only_not_schedule_rows(self, app_dir):
        db.add_schedule("2026-07-23", "슬롯 1", db.SCHEDULE_COLOR_SLOTS[0])
        with db._connection() as conn:
            before = tuple(conn.execute(
                "SELECT id, date, content, created_at, color FROM schedules"
            ).fetchone())

        custom = ("#FF9F68", "#80CFA9", "#B197FC")
        db.save_schedule_palette(custom)

        with db._connection() as conn:
            after = tuple(conn.execute(
                "SELECT id, date, content, created_at, color FROM schedules"
            ).fetchone())
        assert after == before
        assert db.get_schedule_palette() == custom
        assert db.get_schedules("2026-07-23")[0]["color"] == "#FFD166"
        assert db.schedule_display_color("#FFD166") == "#FF9F68"

    def test_palette_invalid_and_duplicate_settings_fall_back_distinctly(self, app_dir):
        with db._connection() as conn:
            values = ("not-a-color", "#4cc9f0", "#4CC9F0")
            for key, value in zip(db.SCHEDULE_COLOR_SETTING_KEYS, values):
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.commit()

        palette = db.get_schedule_palette()
        allowed = {color for color, _name in db.SCHEDULE_COLOR_OPTIONS}
        assert len(palette) == 3
        assert len(set(palette)) == 3
        assert all(color in allowed for color in palette)
        assert palette[0] == db.DEFAULT_SCHEDULE_PALETTE[0]
        assert palette[1] == "#4CC9F0"

    def test_save_palette_rejects_invalid_or_duplicate_without_overwrite(self, app_dir):
        original = db.get_schedule_palette()
        with pytest.raises(ValueError):
            db.save_schedule_palette(("#FFD166", "#FFD166", "#FF6B6B"))
        with pytest.raises(ValueError):
            db.save_schedule_palette(("#FFD166", "#4CC9F0", "#123456"))
        assert db.get_schedule_palette() == original

    def test_display_resolver_is_case_insensitive_and_preserves_unknown(self, app_dir):
        custom = ("#FF9F68", "#80CFA9", "#B197FC")
        assert db.schedule_display_color("#ffd166", custom) == "#FF9F68"
        assert db.schedule_display_color(None, custom) == "#FF9F68"
        assert db.schedule_display_color("#ABCDEF", custom) == "#ABCDEF"


# ─── get_all_schedule_date_colors ────────────────────────────

class TestScheduleDateColors:
    def test_single_color(self, app_dir):
        db.add_schedule("2025-08-01", "노랑", "#FFD166")
        result = db.get_all_schedule_date_colors()
        assert result["2025-08-01"] == ["#FFD166"]

    def test_multiple_colors_deduplicated(self, app_dir):
        for _ in range(5):
            db.add_schedule("2025-08-15", "반복", "#FFD166")
        result = db.get_all_schedule_date_colors()
        assert result["2025-08-15"] == ["#FFD166"]

    def test_three_colors_sorted(self, app_dir):
        # 역순으로 추가해도 팔레트 순서 (노랑→파랑→빨강) 유지
        db.add_schedule("2025-09-01", "빨강", "#FF6B6B")
        db.add_schedule("2025-09-01", "노랑", "#FFD166")
        db.add_schedule("2025-09-01", "파랑", "#4CC9F0")
        result = db.get_all_schedule_date_colors()
        assert result["2025-09-01"] == ["#FFD166", "#4CC9F0", "#FF6B6B"]

    def test_empty_db_returns_empty(self, app_dir):
        assert db.get_all_schedule_date_colors() == {}

    def test_null_color_falls_back_to_default(self, app_dir):
        with db._connection() as conn:
            conn.execute(
                "INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, NULL)",
                ("2025-10-01", security.encrypt("NULL 색상"), "2025-10-01 09:00:00")
            )
            conn.commit()
        result = db.get_all_schedule_date_colors()
        assert result["2025-10-01"] == [db.DEFAULT_SCHEDULE_COLOR]

    def test_multiple_dates(self, app_dir):
        db.add_schedule("2025-11-01", "a", "#FFD166")
        db.add_schedule("2025-11-02", "b", "#4CC9F0")
        result = db.get_all_schedule_date_colors()
        assert "2025-11-01" in result
        assert "2025-11-02" in result


# ─── get_all_schedule_date_counts ────────────────────────────

class TestScheduleDateCounts:
    def test_counts_total_per_date(self, app_dir):
        db.add_schedule("2025-08-01", "a", "#FFD166")
        db.add_schedule("2025-08-01", "b", "#FFD166")  # 같은 색도 별개로 카운트
        db.add_schedule("2025-08-01", "c", "#FF6B6B")
        result = db.get_all_schedule_date_counts()
        assert result["2025-08-01"] == 3

    def test_empty_db_returns_empty(self, app_dir):
        assert db.get_all_schedule_date_counts() == {}

    def test_separate_dates(self, app_dir):
        db.add_schedule("2025-09-01", "a", "#FFD166")
        db.add_schedule("2025-09-02", "b", "#FFD166")
        db.add_schedule("2025-09-02", "c", "#4CC9F0")
        result = db.get_all_schedule_date_counts()
        assert result["2025-09-01"] == 1
        assert result["2025-09-02"] == 2


# ─── 월 단위 일정 조회 ────────────────────────────────────────

class TestScheduleMonthEvents:
    def test_groups_by_date_with_content_and_color(self, app_dir):
        db.add_schedule("2025-08-01", "회의", "#FFD166")
        db.add_schedule("2025-08-01", "점심", "#4CC9F0")
        db.add_schedule("2025-08-15", "보고", "#FF6B6B")
        result = db.get_schedules_for_month(2025, 8)
        assert set(result.keys()) == {"2025-08-01", "2025-08-15"}
        assert result["2025-08-01"] == [
            {"content": "회의", "color": "#FFD166"},
            {"content": "점심", "color": "#4CC9F0"},
        ]
        assert result["2025-08-15"] == [{"content": "보고", "color": "#FF6B6B"}]

    def test_order_matches_schedule_list(self, app_dir):
        db.add_schedule("2025-09-10", "첫째", "#FFD166")
        db.add_schedule("2025-09-10", "둘째", "#FFD166")
        db.add_schedule("2025-09-10", "셋째", "#FFD166")
        contents = [
            e["content"] for e in db.get_schedules_for_month(2025, 9)["2025-09-10"]
        ]
        list_order = [s["content"] for s in db.get_schedules("2025-09-10")]
        assert contents == ["첫째", "둘째", "셋째"] == list_order

    def test_only_requested_month_and_zero_pad(self, app_dir):
        db.add_schedule("2025-07-31", "7월말", "#FFD166")
        db.add_schedule("2025-08-01", "8월초", "#FFD166")
        db.add_schedule("2025-01-15", "1월", "#FFD166")
        db.add_schedule("2025-12-15", "12월", "#FFD166")
        assert list(db.get_schedules_for_month(2025, 8).keys()) == ["2025-08-01"]
        assert list(db.get_schedules_for_month(2025, 1).keys()) == ["2025-01-15"]

    def test_content_round_trip_decrypted(self, app_dir):
        secret = "비밀 일정 · #1"
        db.add_schedule("2025-10-05", secret, "#4CC9F0")
        assert db.get_schedules_for_month(2025, 10)["2025-10-05"][0]["content"] == secret

    def test_empty_month_returns_empty_dict(self, app_dir):
        assert db.get_schedules_for_month(2030, 1) == {}


# ─── 메모(Memo) CRUD ─────────────────────────────────────────

class TestMemoCRUD:
    def test_save_and_get(self, app_dir):
        db.save_memo("2025-03-15", "오늘의 메모")
        assert db.get_memo("2025-03-15") == "오늘의 메모"

    def test_get_empty_date(self, app_dir):
        assert db.get_memo("2099-01-01") == ""

    def test_upsert_same_date(self, app_dir):
        db.save_memo("2025-04-01", "처음")
        db.save_memo("2025-04-01", "수정")
        assert db.get_memo("2025-04-01") == "수정"

    def test_content_encrypted(self, app_dir):
        db.save_memo("2025-04-02", "비밀 메모")
        with db._connection() as conn:
            row = conn.execute(
                "SELECT content FROM memos WHERE date='2025-04-02'"
            ).fetchone()
        assert "비밀 메모" not in row["content"]

    def test_korean_and_special_chars(self, app_dir):
        text = "기후에너지환경부 !@#$%^&*() 보문산불주먹 👊"
        db.save_memo("2025-05-05", text)
        assert db.get_memo("2025-05-05") == text


# ─── 스티키 노트 CRUD ─────────────────────────────────────────

class TestStickyNoteCRUD:
    def test_create_and_get(self, app_dir):
        nid = db.create_sticky_note("memo", 100, 200, "#FFFDD2")
        notes = db.get_open_sticky_notes()
        assert any(n["id"] == nid for n in notes)

    def test_update_content(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="<b>굵은</b> 텍스트")
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["content"] == "<b>굵은</b> 텍스트"

    def test_update_color(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, color="#D6FFE8")
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["color"] == "#D6FFE8"

    def test_update_position(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, x_pos=500, y_pos=300)
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["x_pos"] == 500
        assert note["y_pos"] == 300

    def test_purge(self, app_dir):
        nid = db.create_sticky_note()
        db.purge_sticky_note(nid)
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
        assert not any(n["id"] == nid for n in db.get_trashed_sticky_notes())

    def test_trash_moves_to_trash_not_deleted(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="휴지통 갈 내용")
        db.trash_sticky_note(nid)
        # 열린 목록에서는 사라지고
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())
        # 휴지통에는 남으며 내용이 보존됨
        trashed = db.get_trashed_sticky_notes()
        match = next(t for t in trashed if t["id"] == nid)
        assert match["content"] == "휴지통 갈 내용"
        assert match["deleted_at"] != ""

    def test_restore_keeps_position_and_content(self, app_dir):
        nid = db.create_sticky_note("memo", 333, 444, "#D0FFF1")
        db.update_sticky_note(nid, content="복구될 내용", width=250, height=260)
        db.trash_sticky_note(nid)
        db.restore_sticky_note(nid)
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["content"] == "복구될 내용"
        assert note["x_pos"] == 333 and note["y_pos"] == 444
        assert note["width"] == 250 and note["height"] == 260
        assert note["color"] == "#D0FFF1"
        # 휴지통에서는 사라짐
        assert not any(t["id"] == nid for t in db.get_trashed_sticky_notes())

    def test_empty_trash_removes_all_trashed_only(self, app_dir):
        live = db.create_sticky_note()
        t1 = db.create_sticky_note()
        t2 = db.create_sticky_note()
        db.trash_sticky_note(t1)
        db.trash_sticky_note(t2)
        db.empty_sticky_trash()
        assert db.get_trashed_sticky_notes() == []
        # 라이브 노트는 유지
        assert any(n["id"] == live for n in db.get_open_sticky_notes())

    def test_trash_cap_purges_oldest(self, app_dir):
        ids = [db.create_sticky_note() for _ in range(db.STICKY_TRASH_LIMIT + 1)]
        for nid in ids:
            db.trash_sticky_note(nid)
        trashed = db.get_trashed_sticky_notes()
        assert len(trashed) == db.STICKY_TRASH_LIMIT
        # 가장 먼저(가장 오래) 휴지통에 들어간 노트가 자동 영구삭제됨
        trashed_ids = {t["id"] for t in trashed}
        assert ids[0] not in trashed_ids
        assert ids[-1] in trashed_ids

    def test_trashed_not_in_open_list(self, app_dir):
        nid = db.create_sticky_note()
        db.trash_sticky_note(nid)
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())

    def test_closed_not_in_open_list(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, is_open=0)
        assert not any(n["id"] == nid for n in db.get_open_sticky_notes())

    def test_default_color(self, app_dir):
        nid = db.create_sticky_note()
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["color"] == db.DEFAULT_STICKY_COLOR

    def test_update_no_fields_no_error(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid)  # 아무 필드 없음 → 오류 없어야 함

    def test_empty_content_on_create(self, app_dir):
        nid = db.create_sticky_note()
        note = next(n for n in db.get_open_sticky_notes() if n["id"] == nid)
        assert note["content"] == ""


# ─── D-Day 위젯 CRUD ─────────────────────────────────────────

class TestDDayWidgetCRUD:
    def test_create_and_get(self, app_dir):
        wid = db.create_dday_widget("목표일", "2026-12-31")
        widgets = db.get_open_dday_widgets()
        assert any(w["id"] == wid for w in widgets)

    def test_name_decrypted(self, app_dir):
        db.create_dday_widget("프로젝트 마감", "2026-06-30")
        widgets = db.get_open_dday_widgets()
        assert any(w["name"] == "프로젝트 마감" for w in widgets)

    def test_update(self, app_dir):
        wid = db.create_dday_widget("이름", "2026-01-01")
        db.update_dday_widget(wid, name="새 이름", target_date="2026-06-01")
        w = next(x for x in db.get_open_dday_widgets() if x["id"] == wid)
        assert w["name"] == "새 이름"
        assert w["target_date"] == "2026-06-01"

    def test_delete(self, app_dir):
        wid = db.create_dday_widget("삭제", "2026-01-01")
        db.delete_dday_widget(wid)
        assert not any(w["id"] == wid for w in db.get_open_dday_widgets())

    def test_default_color(self, app_dir):
        wid = db.create_dday_widget("test", "2026-01-01")
        w = next(x for x in db.get_open_dday_widgets() if x["id"] == wid)
        assert w["color"] == db.DEFAULT_DDAY_COLOR

    def test_past_date_allowed(self, app_dir):
        wid = db.create_dday_widget("과거", "2020-01-01")
        w = next(x for x in db.get_open_dday_widgets() if x["id"] == wid)
        assert w["target_date"] == "2020-01-01"


# ─── 집중 모드 위젯 CRUD ─────────────────────────────────────

class TestFocusWidgetCRUD:
    def test_create_and_get(self, app_dir):
        wid = db.create_focus_widget("보고서 초안", "50/10")
        widgets = db.get_open_focus_widgets()
        w = next(x for x in widgets if x["id"] == wid)

        assert w["goal"] == "보고서 초안"
        assert w["mode_key"] == "50/10"
        assert w["focus_minutes"] == 50
        assert w["break_minutes"] == 10

    def test_update_mode_updates_minutes(self, app_dir):
        wid = db.create_focus_widget("집중", "25/5")
        db.update_focus_widget(wid, mode_key="75/15")
        w = next(x for x in db.get_open_focus_widgets() if x["id"] == wid)

        assert w["mode_key"] == "75/15"
        assert w["focus_minutes"] == 75
        assert w["break_minutes"] == 15

    def test_delete(self, app_dir):
        wid = db.create_focus_widget("삭제", "25/5")
        db.delete_focus_widget(wid)
        assert not any(w["id"] == wid for w in db.get_open_focus_widgets())

    def test_session_review_roundtrip(self, app_dir):
        wid = db.create_focus_widget("회고 테스트", "25/5")
        sid = db.create_focus_session(
            wid, "회고 테스트", "25/5", 25, 5,
            "2026-04-27 09:00:00", "2026-04-27 09:25:00",
            1500, True, 4, "알림",
        )
        session = next(s for s in db.get_focus_sessions() if s["id"] == sid)

        assert session["goal"] == "회고 테스트"
        assert session["completed"] == 1
        assert session["focus_rating"] == 4
        assert session["distraction"] == "알림"


# ─── 설정 ────────────────────────────────────────────────────

class TestSettings:
    def test_default_law_search_on(self, app_dir):
        assert db.get_setting(db.SETTING_SHOW_LAW_SEARCH) == "1"

    def test_default_sidebar_off(self, app_dir):
        assert db.get_setting(db.SETTING_SHOW_SIDEBAR) == "0"

    def test_default_app_font_malgun_gothic(self, app_dir):
        assert db.get_setting(db.SETTING_APP_FONT) == db.DEFAULT_APP_FONT

    def test_save_and_get(self, app_dir):
        db.save_setting(db.SETTING_SHOW_LUNAR, "1")
        assert db.get_setting(db.SETTING_SHOW_LUNAR) == "1"

    def test_update_existing(self, app_dir):
        db.save_setting(db.SETTING_SHOW_LUNAR, "0")
        db.save_setting(db.SETTING_SHOW_LUNAR, "1")
        assert db.get_setting(db.SETTING_SHOW_LUNAR) == "1"

    def test_missing_key_returns_default(self, app_dir):
        assert db.get_setting("nonexistent", "기본값") == "기본값"

    def test_all_setting_constants_writable(self, app_dir):
        for key in [
            db.SETTING_PRIVACY_PIN, db.SETTING_DESKTOP_MODE,
            db.SETTING_USE_PRIVACY_LOCK, db.SETTING_SHOW_LUNAR,
            db.SETTING_SHOW_LAW_SEARCH, db.SETTING_TARGET_SCREEN,
            db.SETTING_CALENDAR_POSITION, db.SETTING_SHOW_SIDEBAR,
            db.SETTING_APP_FONT, db.SETTING_CALENDAR_POSITION_MODE,
            *db.SCHEDULE_COLOR_SETTING_KEYS,
        ]:
            db.save_setting(key, "test_val")
            assert db.get_setting(key) == "test_val"


# ─── 바로가기 ─────────────────────────────────────────────────

class TestShortcuts:
    def test_update_shortcut(self, app_dir, tmp_path):
        target = tmp_path / "tool.exe"
        target.write_text("stub", encoding="utf-8")

        db.update_shortcut(3, "테스트 도구", str(target))
        shortcuts = db.get_shortcuts()
        shortcut = next(s for s in shortcuts if s["id"] == 3)

        assert shortcut["name"] == "테스트 도구"
        assert shortcut["path"] == str(target)

    def test_clear_shortcut(self, app_dir, tmp_path):
        target = tmp_path / "tool.exe"
        target.write_text("stub", encoding="utf-8")

        db.update_shortcut(2, "삭제 대상", str(target))
        db.update_shortcut(2, "", "")
        shortcut = next(s for s in db.get_shortcuts() if s["id"] == 2)

        assert shortcut["name"] == ""
        assert shortcut["path"] == ""


# ─── 백업 회전 ────────────────────────────────────────────────

class TestBackupRotation:
    def test_initialize_database_fresh_install_skips_pre_snapshot(
            self, app_dir):
        for path in (
            app_dir / "calendar.db",
            app_dir / "calendar.db-wal",
            app_dir / "calendar.db-shm",
        ):
            if path.exists():
                path.unlink()

        import main as app_main
        app_main._initialize_database()

        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_SCHEMA_VERSION
        assert not list(
            (app_dir / "backups").glob(f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_*.db")
        )

    def test_initialize_database_current_version_skips_pre_snapshot(
            self, app_dir):
        import main as app_main
        app_main._initialize_database()

        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == db.CURRENT_SCHEMA_VERSION
        assert not list(
            (app_dir / "backups").glob(f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_*.db")
        )

    def test_backup_includes_committed_rows_still_in_wal(
            self, app_dir, monkeypatch):
        """열린 WAL에만 있는 커밋 행도 snapshot 백업에 포함되어야 한다."""
        with db._connection() as held:
            held.execute("PRAGMA wal_autocheckpoint = 0")
            held.execute(
                "INSERT INTO schedules "
                "(date, content, created_at, color) VALUES (?, ?, ?, ?)",
                (
                    "2026-07-24", security.encrypt("WAL 커밋 일정"),
                    "2026-07-24 09:00:00", "#FFD166",
                ),
            )
            held.commit()
            db.backup_database()

            bundle_path = next(
                (app_dir / "backups").glob("calendar_auto_*.cnbak")
            )
            backup_path = app_dir / "wal_snapshot.db"
            with zipfile.ZipFile(bundle_path, "r") as archive:
                with archive.open("calendar.db", "r") as source:
                    with open(backup_path, "wb") as destination:
                        shutil.copyfileobj(source, destination)
            with monkeypatch.context() as isolated:
                isolated.setattr(db, "DB_FILE", backup_path)
                with db._connection() as backup:
                    assert backup.execute(
                        "PRAGMA quick_check"
                    ).fetchone()[0] == "ok"
                    count = backup.execute(
                        "SELECT COUNT(*) FROM schedules "
                        "WHERE date = '2026-07-24'"
                    ).fetchone()[0]
            assert count == 1

    def test_backup_failure_preserves_existing_verified_bundle(
            self, app_dir, monkeypatch):
        """새 묶음 생성 실패가 기존 정상 백업을 훼손하면 안 된다."""
        db.add_schedule("2026-07-24", "기존 백업 내용")
        db.backup_database()
        current_path = next(
            (app_dir / "backups").glob("calendar_auto_*.cnbak")
        )
        backup_path = current_path.with_name(
            "calendar_auto_20000101_000000_legacy.cnbak"
        )
        current_path.rename(backup_path)
        with open(backup_path, "rb") as backup_file:
            before = backup_file.read()
        called = []

        def _injected_failure(target, salt):
            called.append((target, salt))
            raise OSError("injected snapshot failure")

        monkeypatch.setattr(
            db, "_create_auto_backup_bundle", _injected_failure
        )
        db.add_schedule("2026-07-25", "실패 시 포함되면 안 됨")
        db.backup_database()

        assert called
        with open(backup_path, "rb") as backup_file:
            assert backup_file.read() == before

    @pytest.mark.parametrize("legacy_version", (15, 16))
    def test_pre_migration_snapshot_refreshes_latest_legacy_data(
            self, app_dir, monkeypatch, legacy_version):
        """재시도 전 데이터가 늘면 pre-migration snapshot도 최신이어야 한다."""
        db.add_schedule("2026-07-24", "마이그레이션 전 원본")
        with db._connection() as conn:
            conn.execute(f"PRAGMA user_version = {legacy_version}")
            conn.commit()

        assert db.backup_before_migration() is True
        snapshot = (
            app_dir / "backups"
            / f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_v{legacy_version}.db"
        )
        assert snapshot.exists()

        db.add_schedule("2026-07-25", "두 번째 실행 뒤 추가")
        assert db.backup_before_migration() is True

        with monkeypatch.context() as isolated:
            isolated.setattr(db, "DB_FILE", snapshot)
            with db._connection() as backup:
                dates = {
                    row[0] for row in backup.execute(
                        "SELECT date FROM schedules ORDER BY id"
                    ).fetchall()
                }
        assert dates == {"2026-07-24", "2026-07-25"}

    def test_pre_migration_refresh_failure_preserves_previous_snapshot(
            self, app_dir, monkeypatch):
        """최신 snapshot 생성 실패 시 기존 정상본을 훼손하지 않고 중단한다."""
        db.add_schedule("2026-07-24", "기존 스냅샷 내용")
        with db._connection() as conn:
            conn.execute("PRAGMA user_version = 16")
            conn.commit()
        assert db.backup_before_migration() is True

        snapshot = app_dir / "backups" / f"calendar_pre_v{db.CURRENT_SCHEMA_VERSION}_v16.db"
        with open(snapshot, "rb") as snapshot_file:
            before = snapshot_file.read()
        db.add_schedule("2026-07-25", "새로 추가된 원본")

        def _injected_failure(source, target):
            raise OSError("injected snapshot refresh failure")

        monkeypatch.setattr(
            db, "_create_verified_snapshot", _injected_failure
        )
        with pytest.raises(OSError, match="injected"):
            db.backup_before_migration()

        with open(snapshot, "rb") as snapshot_file:
            assert snapshot_file.read() == before
        with db._connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 16
            assert conn.execute(
                "SELECT COUNT(*) FROM schedules"
            ).fetchone()[0] == 2

    @pytest.mark.parametrize("legacy_version", (15, 16))
    def test_pre_migration_snapshot_failure_is_fail_closed(
            self, app_dir, monkeypatch, legacy_version):
        db.add_schedule("2026-07-24", "변경되면 안 되는 원본")
        with db._connection() as conn:
            conn.execute(f"PRAGMA user_version = {legacy_version}")
            conn.commit()
            before = tuple(conn.execute(
                "SELECT id, date, content, created_at, color "
                "FROM schedules WHERE date = '2026-07-24'"
            ).fetchone())

        def _injected_failure(source, target):
            raise OSError("injected pre-migration snapshot failure")

        monkeypatch.setattr(
            db, "_create_verified_snapshot", _injected_failure
        )
        import main as app_main
        with pytest.raises(OSError, match="injected"):
            app_main._initialize_database()

        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            after = tuple(conn.execute(
                "SELECT id, date, content, created_at, color "
                "FROM schedules WHERE date = '2026-07-24'"
            ).fetchone())
        assert version == legacy_version
        assert after == before

    def test_backup_file_created(self, app_dir):
        db.add_schedule("2026-07-24", "자동백업 생성")
        db.backup_database()
        backup_dir = app_dir / "backups"
        assert len(list(backup_dir.glob("calendar_auto_*.cnbak"))) == 1

    def test_max_5_backups(self, app_dir):
        """검증된 새 형식 일일 백업은 최대 5개만 유지한다."""
        db.add_schedule("2026-07-24", "회전 대상")
        backup_dir = app_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        db.backup_database()
        template = next(backup_dir.glob("calendar_auto_*.cnbak"))
        for i in range(7):
            dst = backup_dir / (
                f"calendar_auto_2025010{i + 1}_000000_copy{i}.cnbak"
            )
            shutil.copy2(template, dst)
        template.unlink()

        db.backup_database()  # 8번째 백업

        backups = sorted(backup_dir.glob("calendar_auto_*.cnbak"))
        assert len(backups) == 5

    def test_same_day_backup_keeps_first_verified_bundle(self, app_dir):
        """같은 날 다시 실행해도 먼저 만든 정상 묶음을 덮지 않는다."""
        db.add_schedule("2026-07-24", "첫 정상본")
        db.backup_database()
        backup_dir = app_dir / "backups"
        bundle = next(backup_dir.glob("calendar_auto_*.cnbak"))
        with open(bundle, "rb") as backup_file:
            before = backup_file.read()
        db.add_schedule("2026-07-25", "같은 날 나중 변경")
        db.backup_database()
        db.backup_database()
        same_day = list(backup_dir.glob("calendar_auto_*.cnbak"))
        assert same_day == [bundle]
        with open(bundle, "rb") as backup_file:
            assert backup_file.read() == before

    def test_backup_no_error_without_db(self, app_dir):
        """DB 파일 없어도 오류 없이 처리"""
        (app_dir / "calendar.db").unlink()
        db.backup_database()


# ─── Export / Import ─────────────────────────────────────────

class TestExportImport:
    def test_export_uses_one_read_snapshot_across_tables(
            self, app_dir, monkeypatch):
        """Export 도중 커밋된 다른 테이블 변경이 payload 중간에 섞이지 않는다."""
        db.add_schedule("2026-07-24", "스냅샷 기준 일정")
        original_decrypt = db._decrypt_for_export
        wrote_during_export = False

        def _write_memo_then_decrypt(ciphertext, table, row_id):
            nonlocal wrote_during_export
            if not wrote_during_export:
                wrote_during_export = True
                db.save_memo("2026-07-25", "Export 도중 추가")
            return original_decrypt(ciphertext, table, row_id)

        monkeypatch.setattr(
            db, "_decrypt_for_export", _write_memo_then_decrypt
        )

        payload = json.loads(db.export_all_data())

        assert wrote_during_export is True
        assert payload["memos"] == []
        assert db.get_memo("2026-07-25") == "Export 도중 추가"

    def test_export_aborts_on_decryption_failure(self, app_dir):
        """복호화 불가 행을 빈 문자열로 내보내 성공 처리하면 안 된다."""
        with db._connection() as conn:
            conn.execute(
                "INSERT INTO schedules "
                "(date, content, created_at, color) VALUES (?, ?, ?, ?)",
                ("2026-07-24", "not-a-fernet-token",
                 "2026-07-24 09:00:00", "#FFD166"),
            )
            conn.commit()

        with pytest.raises(ValueError, match="복호화"):
            db.export_all_data()

    def test_export_has_format_version_and_shortcuts_roundtrip(self, app_dir):
        db.update_shortcut(1, "업무 도구", "C:/Tools/work.exe")

        exported = db.export_all_data()
        payload = json.loads(exported)

        assert payload["format_version"] == db.EXPORT_FORMAT_VERSION
        assert payload["shortcuts"] == [{
            "id": 1, "name": "업무 도구", "path": "C:/Tools/work.exe",
        }, *[
            {"id": index, "name": "", "path": ""}
            for index in range(2, 7)
        ]]

        db.reset_database()
        db.import_all_data(exported)
        shortcut = next(s for s in db.get_shortcuts() if s["id"] == 1)
        assert shortcut == {
            "id": 1, "name": "업무 도구", "path": "C:/Tools/work.exe",
        }

    def test_import_shortcuts_fills_empty_slots_but_preserves_current(
            self, app_dir):
        db.update_shortcut(1, "현재 바로가기", "C:/Current.exe")
        payload = json.dumps({
            "format_version": db.EXPORT_FORMAT_VERSION,
            "shortcuts": [
                {"id": 1, "name": "", "path": ""},
                {"id": 2, "name": "백업 바로가기", "path": "C:/Backup.exe"},
            ],
        })

        db.import_all_data(payload)

        shortcuts = {item["id"]: item for item in db.get_shortcuts()}
        assert shortcuts[1]["name"] == "현재 바로가기"
        assert shortcuts[1]["path"] == "C:/Current.exe"
        assert shortcuts[2]["name"] == "백업 바로가기"
        assert shortcuts[2]["path"] == "C:/Backup.exe"

    def test_focus_session_widget_id_is_remapped_on_merge(self, app_dir):
        source_id = db.create_focus_widget("가져올 집중", "25/5")
        db.create_focus_session(
            source_id, "가져올 집중", "25/5", 25, 5,
            "2026-07-24 09:00:00", "2026-07-24 09:25:00",
            1500, True,
        )
        exported = db.export_all_data()

        db.reset_database()
        existing_id = db.create_focus_widget("기존 집중", "50/10")
        db.import_all_data(exported)

        assert [w["id"] for w in db.get_open_focus_widgets()] == [existing_id]
        widgets = {w["source_id"]: w for w in json.loads(db.export_all_data())["focus_widgets"]}
        imported = next(
            s for s in db.get_focus_sessions()
            if s["goal"] == "가져올 집중"
        )
        assert existing_id == 1
        assert widgets[imported["widget_id"]]["goal"] == "가져올 집중"
        assert widgets[imported["widget_id"]]["is_open"] == 0
        assert imported["widget_id"] != existing_id

    @pytest.mark.parametrize("source_ids", ([1, 1], [0]))
    def test_import_rejects_ambiguous_focus_source_ids(
            self, app_dir, source_ids):
        payload = {
            "format_version": db.EXPORT_FORMAT_VERSION,
            "focus_widgets": [
                {"source_id": source_id, "goal": f"집중 {index}"}
                for index, source_id in enumerate(source_ids)
            ],
        }

        with pytest.raises(ValueError, match="source_id"):
            db.import_all_data(json.dumps(payload, ensure_ascii=False))

        assert db.get_open_focus_widgets() == []

    def test_legacy_focus_payload_does_not_link_session_to_wrong_widget(
            self, app_dir):
        source_id = db.create_focus_widget("레거시 집중", "25/5")
        db.create_focus_session(
            source_id, "레거시 집중", "25/5", 25, 5,
            "2026-07-24 09:00:00", "2026-07-24 09:25:00",
            1500, True,
        )
        payload = json.loads(db.export_all_data())
        payload.pop("format_version")
        for widget in payload["focus_widgets"]:
            widget.pop("source_id")

        db.reset_database()
        existing_id = db.create_focus_widget("기존 집중", "50/10")
        db.import_all_data(json.dumps(payload, ensure_ascii=False))

        imported = next(
            s for s in db.get_focus_sessions()
            if s["goal"] == "레거시 집중"
        )
        assert existing_id == 1
        assert imported["widget_id"] is None

    def test_import_preserves_current_memo_on_date_conflict(self, app_dir):
        db.save_memo("2026-07-24", "현재 메모")
        payload = json.dumps({
            "memos": [{
                "date": "2026-07-24",
                "content": "과거 백업 메모",
                "updated_at": "2026-07-01 09:00:00",
            }]
        })

        db.import_all_data(payload)

        assert db.get_memo("2026-07-24") == "현재 메모"

    def test_import_validates_whole_payload_before_writing(self, app_dir):
        payload = json.dumps({
            "schedules": [{
                "date": "2026-07-24", "content": "삽입되면 안 됨",
            }],
            "sticky_notes": [{"content": "필수 필드 누락"}],
        })

        with pytest.raises(ValueError, match="sticky_notes"):
            db.import_all_data(payload)

        assert db.get_schedules("2026-07-24") == []

    @pytest.mark.parametrize(
        ("field", "value"),
        (("width", -1), ("height", 0), ("is_open", 2), ("is_pinned", -7)),
    )
    def test_import_rejects_invalid_sticky_geometry_and_flags(
            self, app_dir, field, value):
        sticky = {
            "type": "memo",
            "content": "커밋되면 안 됨",
            "x_pos": 100,
            "y_pos": 100,
            "width": 300,
            "height": 400,
            "is_open": 1,
            "is_pinned": 0,
        }
        sticky[field] = value

        with pytest.raises(ValueError, match=field):
            db.import_all_data(json.dumps({"sticky_notes": [sticky]}))

        with db._connection() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM sticky_notes"
            ).fetchone()[0] == 0

    def test_import_rejects_integer_outside_sqlite_range(self, app_dir):
        payload = json.dumps({
            "sticky_notes": [{
                "type": "memo",
                "content": "커밋되면 안 됨",
                "x_pos": 10 ** 100,
                "y_pos": 100,
                "width": 300,
                "height": 400,
                "is_open": 1,
                "is_pinned": 0,
            }],
        })

        with pytest.raises(ValueError, match="SQLite 범위"):
            db.import_all_data(payload)

    def test_import_write_failure_rolls_back_transaction(
            self, app_dir, monkeypatch):
        payload = json.dumps({
            "schedules": [
                {"date": "2026-07-24", "content": "첫 번째"},
                {"date": "2026-07-25", "content": "두 번째"},
            ],
        }, ensure_ascii=False)
        real_encrypt = db.encrypt
        calls = 0

        def _fail_second_encrypt(plaintext):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("injected encryption failure")
            return real_encrypt(plaintext)

        monkeypatch.setattr(db, "encrypt", _fail_second_encrypt)
        with pytest.raises(ValueError, match="injected"):
            db.import_all_data(payload)

        assert db.get_schedules("2026-07-24") == []
        assert db.get_schedules("2026-07-25") == []

    def test_import_rejects_newer_format_before_writing(self, app_dir):
        payload = json.dumps({
            "format_version": db.EXPORT_FORMAT_VERSION + 1,
            "schedules": [{
                "date": "2026-07-24", "content": "삽입되면 안 됨",
            }],
        })

        with pytest.raises(ValueError, match="format_version"):
            db.import_all_data(payload)

        assert db.get_schedules("2026-07-24") == []

    def test_roundtrip(self, app_dir):
        db.add_schedule("2025-03-15", "일정1", "#FFD166")
        db.add_schedule("2025-03-15", "일정2", "#4CC9F0")
        db.save_memo("2025-03-15", "메모 내용")
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="스티키 내용")
        db.create_dday_widget("디데이", "2026-01-01")
        focus_id = db.create_focus_widget("집중 목표", "50/10")
        db.create_focus_session(
            focus_id, "집중 목표", "50/10", 50, 10,
            "2026-04-27 10:00:00", "2026-04-27 10:50:00",
            3000, True, 5, "없음",
        )

        exported = db.export_all_data()
        db.reset_database()
        db.import_all_data(exported)

        schedules = db.get_schedules("2025-03-15")
        assert {s["content"] for s in schedules} == {"일정1", "일정2"}
        assert db.get_memo("2025-03-15") == "메모 내용"
        notes = db.get_open_sticky_notes()
        assert any(n["content"] == "스티키 내용" for n in notes)
        assert any(f["goal"] == "집중 목표" for f in db.get_open_focus_widgets())
        assert any(s["goal"] == "집중 목표" and s["focus_rating"] == 5 for s in db.get_focus_sessions())

    def test_export_includes_color(self, app_dir):
        db.add_schedule("2025-04-01", "색상 일정", "#FF6B6B")
        data = json.loads(db.export_all_data())
        s = next(x for x in data["schedules"] if x["content"] == "색상 일정")
        assert s["color"] == "#FF6B6B"

    def test_palette_export_keeps_raw_slot_and_roundtrips_settings(self, app_dir):
        custom = ("#FF9F68", "#80CFA9", "#B197FC")
        db.save_schedule_palette(custom)
        db.add_schedule("2026-07-23", "표시색 분리", "#FFD166")

        exported = db.export_all_data()
        payload = json.loads(exported)
        schedule = next(
            item for item in payload["schedules"]
            if item["content"] == "표시색 분리"
        )
        assert schedule["color"] == "#FFD166"
        assert tuple(
            payload["settings"][key]
            for key in db.SCHEDULE_COLOR_SETTING_KEYS
        ) == custom

        db.reset_database()
        db.import_all_data(exported)
        assert db.get_schedules("2026-07-23")[0]["color"] == "#FFD166"
        assert db.get_schedule_palette() == custom
        assert db.schedule_display_color("#FFD166") == "#FF9F68"

    def test_export_includes_focus_mode(self, app_dir):
        db.create_focus_widget("깊은 일", "50/10")
        data = json.loads(db.export_all_data())
        f = next(x for x in data["focus_widgets"] if x["goal"] == "깊은 일")
        assert f["mode_key"] == "50/10"
        assert f["focus_minutes"] == 50

    def test_internet_access_stays_on_this_pc(self, app_dir):
        assert db.get_setting(db.SETTING_INTERNET_ACCESS, "missing") == "missing"  # 마이그레이션에 넣지 않는다
        db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
        exported = json.loads(db.export_all_data())
        assert db.SETTING_INTERNET_ACCESS not in exported["settings"]
        db.save_setting(db.SETTING_INTERNET_ACCESS, "0")
        exported["settings"][db.SETTING_INTERNET_ACCESS] = "1"  # 손으로 고친 파일이어도 받지 않는다
        db.import_all_data(json.dumps(exported))
        assert db.get_setting(db.SETTING_INTERNET_ACCESS, "") == "0"

    def test_export_includes_settings_excludes_pin(self, app_dir):
        db.save_setting(db.SETTING_APP_OPACITY, "75")
        db.save_setting(db.SETTING_CALENDAR_SCALE, "medium")
        db.save_setting(db.SETTING_SHOW_LUNAR, "1")
        data = json.loads(db.export_all_data())
        assert data["settings"][db.SETTING_APP_OPACITY] == "75"
        assert data["settings"][db.SETTING_CALENDAR_SCALE] == "medium"
        assert data["settings"][db.SETTING_SHOW_LUNAR] == "1"
        assert db.SETTING_PRIVACY_PIN not in data["settings"]

    def test_settings_export_import_roundtrip(self, app_dir):
        db.save_setting(db.SETTING_APP_OPACITY, "40")
        db.save_setting(db.SETTING_CALENDAR_SCALE, "large")
        db.save_setting(db.SETTING_SHOW_LUNAR, "1")
        db.save_setting(db.SETTING_PRIVACY_PIN, "1234")
        exported = db.export_all_data()
        db.reset_database()
        db.import_all_data(exported)
        assert db.get_setting(db.SETTING_APP_OPACITY) == "40"
        assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "large"
        assert db.get_setting(db.SETTING_SHOW_LUNAR) == "1"
        pin = db.get_setting(db.SETTING_PRIVACY_PIN)
        assert pin != "0000" and security.verify_privacy_pin("0000", pin)
        assert not security.verify_privacy_pin("1234", pin)

    def test_holiday_theme_switch_exports_and_roundtrips(self, app_dir):
        """v4.6 공휴일 테마 스위치는 다른 설정처럼 Export/Import에 실린다(키 없음=켜짐, 꺼짐은 보존)."""
        assert db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1") == "1"
        assert db.SETTING_HOLIDAY_THEME_ENABLED not in json.loads(db.export_all_data())["settings"]
        db.save_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "0")
        exported = db.export_all_data()
        assert json.loads(exported)["settings"][db.SETTING_HOLIDAY_THEME_ENABLED] == "0"
        db.reset_database()
        assert db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1") == "1"
        db.import_all_data(exported)
        assert db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1") == "0"

    def test_import_without_settings_section_no_error(self, app_dir):
        old_json = json.dumps({
            "schedules": [], "memos": [], "sticky_notes": [], "dday_widgets": [],
        })
        db.import_all_data(old_json)
        assert db.get_setting(db.SETTING_APP_OPACITY) == db.DEFAULT_APP_OPACITY

    def test_import_no_color_field_uses_default(self, app_dir):
        """구버전 JSON(color 필드 없음) 임포트 시 기본색 적용"""
        old_json = json.dumps({
            "schedules": [
                {"date": "2025-01-01", "content": "구버전 일정",
                 "created_at": "2025-01-01 09:00:00"}
            ],
            "memos": [], "sticky_notes": [], "dday_widgets": []
        })
        db.import_all_data(old_json)
        result = db.get_schedules("2025-01-01")
        assert result[0]["color"] == db.DEFAULT_SCHEDULE_COLOR

    def test_export_empty_db(self, app_dir):
        data = json.loads(db.export_all_data())
        assert data["schedules"] == []
        assert data["memos"] == []

    def test_import_empty_json(self, app_dir):
        db.import_all_data(json.dumps({
            "schedules": [], "memos": [], "sticky_notes": [], "dday_widgets": []
        }))

    def test_import_missing_sections(self, app_dir):
        """일부 섹션 없는 JSON도 오류 없이 처리"""
        db.import_all_data(json.dumps({"schedules": []}))

    def test_export_includes_trashed_sticky(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="휴지통 백업 대상")
        db.trash_sticky_note(nid)
        data = json.loads(db.export_all_data())
        trashed = [s for s in data["sticky_notes"] if s.get("is_deleted") == 1]
        assert len(trashed) == 1
        assert trashed[0]["deleted_at"] != ""

    def test_import_roundtrip_preserves_trash_state(self, app_dir):
        nid = db.create_sticky_note()
        db.update_sticky_note(nid, content="휴지통 왕복")
        db.trash_sticky_note(nid)

        exported = db.export_all_data()
        db.reset_database()
        db.import_all_data(exported)

        # 복원 후에도 휴지통에 존재하고 열린 목록에는 없음
        trashed = db.get_trashed_sticky_notes()
        assert any(t["content"] == "휴지통 왕복" for t in trashed)
        assert all(n["content"] != "휴지통 왕복" for n in db.get_open_sticky_notes())

    def test_import_sticky_without_trash_fields_defaults_live(self, app_dir):
        """구버전 백업(is_deleted/deleted_at 없음) 임포트 시 일반(라이브) 노트로 들어감"""
        old_json = json.dumps({
            "schedules": [], "memos": [],
            "sticky_notes": [{
                "type": "memo", "content": "구버전 노트",
                "x_pos": 100, "y_pos": 100, "width": 300, "height": 400,
                "is_open": 1, "is_pinned": 0, "color": "#FFFA8E",
            }],
            "dday_widgets": [],
        })
        db.import_all_data(old_json)
        notes = db.get_open_sticky_notes()
        assert any(n["content"] == "구버전 노트" for n in notes)
        assert db.get_trashed_sticky_notes() == []


# ─── 검색 ────────────────────────────────────────────────────

class TestSearch:
    def test_keyword_match(self, app_dir):
        db.add_schedule("2025-06-01", "중요 회의")
        db.add_schedule("2025-06-02", "점심 약속")
        results = db.search_all("회의")
        assert len(results) == 1
        assert results[0]["content"] == "중요 회의"

    def test_empty_keyword_returns_all(self, app_dir):
        db.add_schedule("2025-07-01", "일정A")
        db.save_memo("2025-07-01", "메모B")
        assert len(db.search_all("")) >= 2

    def test_no_results(self, app_dir):
        db.add_schedule("2025-08-01", "일정")
        assert db.search_all("없는키워드xyz") == []

    def test_memo_type_returned(self, app_dir):
        db.save_memo("2025-09-01", "중요 메모 내용")
        results = db.search_all("중요 메모")
        assert any(r["type"] == "메모" for r in results)

    def test_results_sorted_date_desc(self, app_dir):
        db.add_schedule("2025-01-01", "구 일정")
        db.add_schedule("2025-12-31", "신 일정")
        results = db.search_all("")
        dates = [r["date"] for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_search_all_returns_color(self, app_dir):
        db.add_schedule("2025-10-01", "색상 일정", "#FF6B6B")
        db.save_memo("2025-10-01", "메모")
        results = db.search_all("")
        s_result = next(r for r in results if r["type"] == "일정" and r["content"] == "색상 일정")
        m_result = next(r for r in results if r["type"] == "메모" and r["content"] == "메모")
        assert s_result["color"] == "#FF6B6B"
        assert m_result["color"] == "#E0E0E0"


# ─── 팩토리 리셋 ──────────────────────────────────────────────

class TestFactoryReset:
    def test_reset_clears_all_data(self, app_dir):
        db.add_schedule("2025-01-01", "삭제될 일정")
        db.save_memo("2025-01-01", "삭제될 메모")
        db.reset_database()
        assert db.get_schedules("2025-01-01") == []
        assert db.get_memo("2025-01-01") == ""

    def test_reset_then_migrate_current_version(self, app_dir):
        db.reset_database()
        with db._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.CURRENT_SCHEMA_VERSION

    def test_reset_then_insert_works(self, app_dir):
        db.reset_database()
        sid = db.add_schedule("2025-03-01", "리셋 후 일정")
        assert sid > 0


@pytest.mark.parametrize("section,field,value", [
    ("sticky_notes", "x_pos", 2 ** 31),
    ("sticky_notes", "y_pos", -(2 ** 31) - 1),
    ("sticky_notes", "width", 2 ** 31),
    ("sticky_notes", "height", 2 ** 31),
    ("dday_widgets", "x_pos", 2 ** 31),
    ("focus_widgets", "y_pos", -(2 ** 31) - 1),
])
def test_import_rejects_unrenderable_widget_geometry_before_writes(app_dir, section, field, value):
    db.add_schedule("2026-10-27", "기존 일정 보존")
    before = db.export_all_data()
    payload = {"format_version": db.EXPORT_FORMAT_VERSION, section: [{
        "type": "memo", "content": "가져올 본문", "name": "가져올 이름",
        "target_date": "2026-12-01", "source_id": 99,
        "x_pos": -1920, "y_pos": 100, "width": 300, "height": 400,
        "is_open": 1, "is_pinned": 0, field: value,
    }]}
    with pytest.raises(ValueError):
        db.import_all_data(json.dumps(payload))
    assert db.export_all_data() == before


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_import_preserves_negative_monitor_coordinates(app_dir, version):
    payload = {"format_version": version,
               "sticky_notes": [{"type": "memo", "content": "원본 메모",
                                 "x_pos": -1920, "y_pos": -1080, "width": 300, "height": 400,
                                 "is_open": 1, "is_pinned": 0}],
               "dday_widgets": [{"name": "원본 D-Day", "target_date": "2026-12-01",
                                 "x_pos": -1920, "y_pos": -1080}],
               "focus_widgets": [{"source_id": 99, "goal": "원본 집중",
                                  "x_pos": -1920, "y_pos": -1080}]}
    db.import_all_data(json.dumps(payload))
    exported = json.loads(db.export_all_data())
    for section in ("sticky_notes", "dday_widgets", "focus_widgets"):
        assert exported[section][0]["x_pos"] == -1920
        assert exported[section][0]["y_pos"] == -1080
    assert exported["sticky_notes"][0]["content"] == "원본 메모"
    assert exported["dday_widgets"][0]["name"] == "원본 D-Day"
    assert exported["focus_widgets"][0]["goal"] == "원본 집중"
