"""v3.5 장기 데이터 보호 게이트와 자동백업 묶음 검증."""

import os
import json
import shutil
import zipfile

import pytest

import database as db
import security


def test_health_gate_accepts_existing_encrypted_data(app_dir):
    db.add_schedule("2026-08-15", "보존할 일정")

    report = db.inspect_startup_data_health()

    assert report.ok is True
    assert report.code == "healthy"
    assert report.encrypted_count == 1
    assert report.failed_count == 0


def test_health_gate_missing_salt_fails_without_creating_replacement(app_dir):
    db.add_schedule("2026-08-15", "원래 salt가 필요한 일정")
    security._fernet_cache = None
    security._legacy_fernet_cache = None
    security.SALT_FILE.unlink()

    report = db.inspect_startup_data_health()

    assert report.ok is False
    assert report.code == "salt_missing"
    assert not security.SALT_FILE.exists()


def test_health_gate_wrong_salt_fails_without_replacing_it(app_dir):
    db.add_schedule("2026-08-15", "다른 salt로 열면 안 되는 일정")
    wrong_salt = os.urandom(32)
    with open(security.SALT_FILE, "wb") as salt_file:
        salt_file.write(wrong_salt)
    security._fernet_cache = None
    security._legacy_fernet_cache = None

    report = db.inspect_startup_data_health()

    assert report.ok is False
    assert report.code == "decrypt_failed"
    with open(security.SALT_FILE, "rb") as salt_file:
        assert salt_file.read() == wrong_salt


def test_health_gate_empty_database_does_not_create_salt(app_dir):
    assert not security.SALT_FILE.exists()

    report = db.inspect_startup_data_health()

    assert report.ok is True
    assert report.code == "healthy"
    assert report.encrypted_count == 0
    assert not security.SALT_FILE.exists()


def test_health_gate_empty_database_rejects_existing_malformed_salt(app_dir):
    malformed = b"short"
    with open(security.SALT_FILE, "wb") as salt_file:
        salt_file.write(malformed)

    report = db.inspect_startup_data_health()

    assert report.ok is False
    assert report.code == "salt_invalid"
    with open(security.SALT_FILE, "rb") as salt_file:
        assert salt_file.read() == malformed


def test_health_gate_missing_database_with_orphan_salt_is_not_fresh(app_dir):
    for db_path in (
        db.DB_FILE,
        db.DB_FILE.with_name(f"{db.DB_FILE.name}-wal"),
        db.DB_FILE.with_name(f"{db.DB_FILE.name}-shm"),
    ):
        if db_path.exists():
            db_path.unlink()
    with open(security.SALT_FILE, "wb") as salt_file:
        salt_file.write(os.urandom(32))

    report = db.inspect_startup_data_health()

    assert report.ok is False
    assert report.code == "incomplete_dataset"
    assert not db.DB_FILE.exists()


def test_health_gate_rejects_malformed_salt_without_replacing_it(app_dir):
    db.add_schedule("2026-08-15", "잘못된 salt 길이")
    malformed = b"short"
    with open(security.SALT_FILE, "wb") as salt_file:
        salt_file.write(malformed)
    security._fernet_cache = None
    security._legacy_fernet_cache = None

    report = db.inspect_startup_data_health()

    assert report.ok is False
    assert report.code == "salt_invalid"
    with open(security.SALT_FILE, "rb") as salt_file:
        assert salt_file.read() == malformed


def test_health_gate_scans_every_encrypted_user_data_table(app_dir):
    db.add_schedule("2026-08-15", "일정")
    db.save_memo("2026-08-15", "메모")
    sticky_id = db.create_sticky_note()
    db.update_sticky_note(sticky_id, content="스티키")
    db.create_dday_widget("디데이", "2027-01-01")
    focus_id = db.create_focus_widget("집중 목표")
    db.create_focus_session(
        focus_id, "집중 기록", "25/5", 25, 5,
        "2026-08-15 09:00:00", "2026-08-15 09:25:00",
        1500, True,
    )

    report = db.inspect_startup_data_health()

    assert report.ok is True
    assert report.encrypted_count == 6
    assert report.failed_count == 0


def test_health_gate_reports_one_corrupt_ciphertext_without_rewriting(app_dir):
    good_id = db.add_schedule("2026-08-15", "정상 일정")
    bad_id = db.add_schedule("2026-08-16", "손상시킬 일정")
    with db._connection() as conn:
        conn.execute(
            "UPDATE schedules SET content = ? WHERE id = ?",
            ("broken-token", bad_id),
        )
        conn.commit()

    report = db.inspect_startup_data_health()

    assert report.ok is False
    assert report.code == "decrypt_failed"
    assert report.encrypted_count == 2
    assert report.failed_count == 1
    assert report.failed_locations == (f"schedules:{bad_id}",)
    assert db.get_schedules("2026-08-15")[0]["id"] == good_id


def test_auto_backup_bundle_contains_snapshot_salt_and_manifest(app_dir):
    db.add_schedule("2026-08-15", "묶음에 보존할 일정")
    with open(security.SALT_FILE, "rb") as salt_file:
        original_salt = salt_file.read()

    assert db.backup_database() is True

    bundles = list((app_dir / "backups").glob("calendar_auto_*.cnbak"))
    assert len(bundles) == 1
    manifest = db.validate_backup_bundle(bundles[0])
    assert manifest["format"] == "climatenote-auto-backup"
    assert manifest["format_version"] == 1
    assert manifest["schema_version"] == db.CURRENT_SCHEMA_VERSION

    with zipfile.ZipFile(bundles[0], "r") as archive:
        assert set(archive.namelist()) == {
            "calendar.db", ".salt", "manifest.json"
        }
        assert archive.read(".salt") == original_salt
        stored_manifest = json.loads(archive.read("manifest.json"))
        assert stored_manifest == manifest


def test_auto_backup_preserves_settings_when_encrypted_tables_are_empty(
        app_dir, monkeypatch):
    db.save_setting("v34_custom_setting", "화면·바로가기 설정도 사용자 데이터")
    assert not security.SALT_FILE.exists()

    assert db.backup_database() is True

    assert security.read_existing_salt()
    bundle = next((app_dir / "backups").glob("calendar_auto_*.cnbak"))
    extracted = app_dir / "validated-settings-snapshot.db"
    with zipfile.ZipFile(bundle, "r") as archive:
        with archive.open("calendar.db", "r") as source:
            with open(extracted, "wb") as target:
                target.write(source.read())
    monkeypatch.setattr(db, "DB_FILE", extracted)
    assert db.get_setting("v34_custom_setting") == (
        "화면·바로가기 설정도 사용자 데이터"
    )


def test_pre_v35_backup_preserves_existing_settings_only_database(app_dir):
    db.save_setting("v34_custom_setting", "첫 실행 전 설정 보존")
    assert not security.SALT_FILE.exists()

    assert db.backup_before_v35() is True

    bundles = list((app_dir / "backups").glob(
        "calendar_pre_v35_*.cnbak"
    ))
    assert len(bundles) == 1
    assert db.validate_backup_bundle(bundles[0])["schema_version"] == 17


def test_auto_backup_same_day_keeps_first_verified_bundle(app_dir):
    db.add_schedule("2026-08-15", "첫 백업 내용")
    assert db.backup_database() is True
    bundle = next((app_dir / "backups").glob("calendar_auto_*.cnbak"))
    with open(bundle, "rb") as backup_file:
        first_bytes = backup_file.read()

    db.add_schedule("2026-08-16", "같은 날 추가된 내용")
    assert db.backup_database() is True

    bundles = list((app_dir / "backups").glob("calendar_auto_*.cnbak"))
    assert bundles == [bundle]
    with open(bundle, "rb") as backup_file:
        assert backup_file.read() == first_bytes


def test_same_day_backup_still_repairs_excess_retention(app_dir):
    db.add_schedule("2026-08-15", "회전 정리")
    assert db.backup_database() is True
    backup_dir = app_dir / "backups"
    today_bundle = next(backup_dir.glob("calendar_auto_*.cnbak"))
    for index in range(7):
        shutil.copy2(
            today_bundle,
            backup_dir / (
                f"calendar_auto_202501{index + 1:02d}_000000_"
                f"copy{index}.cnbak"
            ),
        )

    assert db.backup_database() is True

    backups = sorted(backup_dir.glob("calendar_auto_*.cnbak"))
    assert len(backups) == db.AUTO_BACKUP_KEEP_DAYS
    assert today_bundle in backups


def test_retention_cleanup_failure_keeps_valid_backup_successful(
        app_dir, monkeypatch):
    db.add_schedule("2026-08-15", "정리 실패와 백업 성공은 분리")
    assert db.backup_database() is True
    backup_dir = app_dir / "backups"
    today_bundle = next(backup_dir.glob("calendar_auto_*.cnbak"))
    for index in range(db.AUTO_BACKUP_KEEP_DAYS):
        shutil.copy2(
            today_bundle,
            backup_dir / (
                f"calendar_auto_202501{index + 1:02d}_000000_"
                f"copy{index}.cnbak"
            ),
        )

    original_unlink = db.Path.unlink

    def _fail_oldest_only(path, *args, **kwargs):
        if path.name.startswith("calendar_auto_20250101_"):
            raise OSError("injected retention cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(db.Path, "unlink", _fail_oldest_only)

    assert db.backup_database() is True
    assert today_bundle.exists()
    assert db.validate_backup_bundle(today_bundle)["format_version"] == 1
    assert len(list(backup_dir.glob("calendar_auto_*.cnbak"))) == 6


def test_auto_backup_missing_salt_does_not_publish_bundle(app_dir):
    db.add_schedule("2026-08-15", "salt 없는 백업 금지")
    security.SALT_FILE.unlink()
    security._fernet_cache = None
    security._legacy_fernet_cache = None

    assert db.backup_database() is False
    assert not list((app_dir / "backups").glob("*.cnbak"))
    assert not security.SALT_FILE.exists()


def test_new_backup_rotation_never_deletes_legacy_database_backup(app_dir):
    db.add_schedule("2026-08-15", "레거시 보존")
    backup_dir = app_dir / "backups"
    backup_dir.mkdir(exist_ok=True)
    legacy = backup_dir / "calendar_backup_20260814.db"
    with open(legacy, "wb") as legacy_file:
        legacy_file.write(b"legacy-sentinel")

    assert db.backup_database() is True

    with open(legacy, "rb") as legacy_file:
        assert legacy_file.read() == b"legacy-sentinel"


@pytest.mark.parametrize("operation", ("import", "reset"))
def test_destructive_operation_creates_non_rotating_recovery_bundle(
        app_dir, operation):
    db.add_schedule("2026-08-15", f"{operation} 전 보존")

    assert db.backup_before_operation(operation) is True

    bundles = list((app_dir / "backups").glob(
        f"calendar_before_{operation}_*.cnbak"
    ))
    assert len(bundles) == 1
    assert db.validate_backup_bundle(bundles[0])["schema_version"] == 17


def test_v35_startup_blocks_before_any_backup_when_health_fails(app_dir):
    import main as app_main

    db.add_schedule("2026-08-15", "시작 실패 때 보존할 일정")
    security.SALT_FILE.unlink()
    security._fernet_cache = None
    security._legacy_fernet_cache = None

    with pytest.raises(db.DataHealthError) as exc_info:
        app_main._initialize_database()

    assert exc_info.value.report.code == "salt_missing"
    assert not security.SALT_FILE.exists()
    assert not list((app_dir / "backups").glob("*.cnbak"))


def test_v35_first_start_preserves_existing_rows_ciphertext_and_salt(app_dir):
    import main as app_main

    schedule_id = db.add_schedule("2026-08-15", "v3.4 원문 보존")
    with db._connection(enable_wal=False, read_only=True) as conn:
        before_row = tuple(conn.execute(
            "SELECT id, date, content, created_at, color "
            "FROM schedules WHERE id = ?", (schedule_id,)
        ).fetchone())
    with open(security.SALT_FILE, "rb") as salt_file:
        before_salt = salt_file.read()

    app_main._initialize_database()
    app_main._initialize_database()

    with db._connection(enable_wal=False, read_only=True) as conn:
        after_row = tuple(conn.execute(
            "SELECT id, date, content, created_at, color "
            "FROM schedules WHERE id = ?", (schedule_id,)
        ).fetchone())
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
    with open(security.SALT_FILE, "rb") as salt_file:
        after_salt = salt_file.read()

    assert after_row == before_row
    assert after_salt == before_salt
    assert len(list((app_dir / "backups").glob(
        "calendar_pre_v35_*.cnbak"
    ))) == 1


def test_v35_repeated_start_preserves_all_v34_user_data_exactly(app_dir):
    import main as app_main

    db.add_schedule("2026-08-15", "v3.4 일정", "#4CC9F0")
    db.save_memo("2026-08-15", "v3.4 메모")
    note_id = db.create_sticky_note("memo", -240, 180, "#FFFA8E")
    db.update_sticky_note(
        note_id, content="\uf0c8 v3.4 할 일", width=333, height=444
    )
    db.create_dday_widget("v3.4 D-Day", "2027-02-01", 31, 42)
    focus_id = db.create_focus_widget("v3.4 집중", "50/10", 53, 64)
    db.create_focus_session(
        focus_id, "v3.4 집중 기록", "50/10", 50, 10,
        "2026-08-15 09:00:00", "2026-08-15 09:50:00",
        3000, True, 5, "없음",
    )
    db.update_shortcut(1, "v3.4 바로가기", "C:/ClimateNote/keep.exe")
    db.save_setting("v34_custom_setting", "사용자 설정 보존")

    tables = (
        "schedules", "memos", "sticky_notes", "dday_widgets",
        "focus_widgets", "focus_sessions", "shortcuts", "app_settings",
        "sqlite_sequence",
    )

    def _raw_snapshot():
        with db._connection(enable_wal=False, read_only=True) as conn:
            return {
                table: [
                    tuple(row)
                    for row in conn.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"  # noqa: S608
                    )
                ]
                for table in tables
            }

    before = _raw_snapshot()
    with open(security.SALT_FILE, "rb") as salt_file:
        before_salt = salt_file.read()

    app_main._initialize_database()
    app_main._initialize_database()

    assert _raw_snapshot() == before
    with open(security.SALT_FILE, "rb") as salt_file:
        assert salt_file.read() == before_salt
    assert db.inspect_startup_data_health().ok is True
