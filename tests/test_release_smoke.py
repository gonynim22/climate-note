"""EXE를 빌드하지 않고 경로 제한·프로세스 소유권·합성 데이터 도구 검증."""

from ctypes import wintypes as W
import copy
import os
import sqlite3
import subprocess
import sys
import time

import pytest

from tools import smoke_release as smoke
from tools import verify


def test_smoke_refuses_existing_root_dist_and_outside_paths(tmp_path):
    with pytest.raises(ValueError):
        smoke.validate_paths(verify.ROOT / "dist/old.exe", tmp_path)
    directory = verify.create_run_dir()
    with pytest.raises(ValueError):
        smoke.validate_paths(verify.ROOT / "dist/old.exe", directory)
    with pytest.raises(ValueError):
        smoke.data_env(verify.ROOT / "output/not-harness")


def test_smoke_accepts_only_this_run_binary():
    directory = verify.create_run_dir()
    (directory / "dist").mkdir()
    exe = directory / "dist/test.exe"
    with open(exe, "wb") as stream:
        stream.write(b"synthetic test only")
    assert smoke.validate_paths(exe, directory) == (exe, directory)


def test_job_kills_its_descendants_but_not_other_processes(tmp_path):
    pid_file = tmp_path / "child.pid"
    pid_temp = tmp_path / "child.pid.tmp"
    child_command = (
        "import os, subprocess, sys\n"
        "with subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']) as child:\n"
        f"    with open({str(pid_temp)!r}, 'w') as stream:\n"
        "        stream.write(str(child.pid))\n"
        # exists()가 참이면 PID 내용도 완전히 기록되어 있어야 한다.
        f"    os.replace({str(pid_temp)!r}, {str(pid_file)!r})\n"
        "    child.wait()\n"
    )
    command = [sys.executable, str(verify.ROOT / "tools/smoke_release.py"), "_launch",
               sys.executable, "-c", child_command]
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as unrelated:
        handle = None
        try:
            with smoke.managed_launch(command, os.environ.copy(), tmp_path / "process.log") as (job, launcher):
                deadline = time.monotonic() + 10
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert pid_file.exists()
                with open(pid_file) as stream:
                    child_pid = int(stream.read())
                assert job.contains(launcher.pid)
                assert job.contains(child_pid)
                assert not job.contains(unrelated.pid)
                kernel = job.kernel
                kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
                kernel.WaitForSingleObject.restype = W.DWORD
                handle = kernel.OpenProcess(0x00100000, False, child_pid)  # SYNCHRONIZE
                assert handle
            assert launcher.poll() is not None
            assert kernel.WaitForSingleObject(handle, 5000) == 0
            assert unrelated.poll() is None
        finally:
            if handle:
                kernel.CloseHandle(handle)
            unrelated.kill()
            unrelated.wait(timeout=10)


def test_assignment_failure_never_releases_launcher(tmp_path, monkeypatch):
    marker = tmp_path / "must-not-exist"
    command = [sys.executable, str(verify.ROOT / "tools/smoke_release.py"), "_launch",
               sys.executable, "-c", f"with open({str(marker)!r}, 'w') as stream:\n    stream.write('launched')"]

    def denied(_self, _pid):
        raise PermissionError("cannot own process")

    monkeypatch.setattr(smoke.ProcessJob, "assign", denied)
    with pytest.raises(PermissionError):
        with smoke.managed_launch(command, os.environ.copy(), tmp_path / "denied.log"):
            pytest.fail("must not launch without ownership")
    assert not marker.exists()


def test_seed_is_isolated_and_cannot_overwrite_existing_dataset():
    directory = verify.create_run_dir()
    data_root = directory / "synthetic"
    data_root.mkdir()
    before = smoke.data_step("seed", data_root, directory / "seed.json")
    assert before["version"] == 19
    assert before["integrity"] == ["ok"]
    assert len(before["ids"]["schedules"]) == 7  # 색 3개 + 세부 설정 3개 + 수정 회차
    assert len(before["ids"]["sticky_notes"]) == 2
    assert len(before["ids"]["focus_sessions"]) == 1
    protected = smoke.protected_hashes(data_root)
    with pytest.raises(RuntimeError, match="seed"):
        smoke.data_step("seed", data_root, directory / "again.json")
    assert smoke.protected_hashes(data_root) == protected
    corrupt = smoke.data_step("corrupt", data_root, directory / "corrupt.json")
    assert corrupt["code"] != "ok"
    assert smoke.protected_hashes(data_root)["calendar.db"] == protected["calendar.db"]


def test_existing_seed_has_time_alarm_period_and_repeat_schedules():
    """기존 데이터 시나리오가 v4.1 세부 설정 값의 불변까지 확인하게 한다(교차검증 F2)."""
    directory = verify.create_run_dir()
    data_root = directory / "synthetic"
    data_root.mkdir()
    before = smoke.data_step("seed", data_root, directory / "seed.json")
    smoke._check_seed_options(before)
    options = [row[1:] for row in before["schedule_options"]]
    assert any(start and alarm is not None for start, _, _, _, _, alarm in options)
    assert any(end for _, end, _, _, _, _ in options)
    assert any(rule and until and skip for _, _, rule, until, skip, _ in options)


def test_seed_option_check_rejects_missing_kinds():
    full = {"schedule_options": [
        [1, "", "", "", "", "", None],
        [2, "09:30", "", "", "", "", 10],
        [3, "", "2026-01-03", "", "", "", None],
        [4, "", "", "weekly", "2026-03-01", "2026-01-08", None],
    ], "schedule_links": [[5, 4, "2026-01-15"]]}
    smoke._check_seed_options(full)
    for removed in (1, 2, 3):
        partial = {**full, "schedule_options": [r for i, r in enumerate(full["schedule_options"]) if i != removed]}
        with pytest.raises(ValueError, match="세부 설정"):
            smoke._check_seed_options(partial)
    with pytest.raises(ValueError, match="수정 회차"):
        smoke._check_seed_options({**full, "schedule_links": []})


def test_existing_check_rejects_changed_schedule_options():
    seeded = {"raw_hashes": {"schedules": "a"}, "logical_hashes": {"schedules": "b"},
              "ids": {"schedules": [1]}, "salt_sha256": "c",
              "schedule_options": [[1, "09:30", "", "", "", "", 10]], "schedule_links": [[1, None, ""]]}
    after = copy.deepcopy(seeded)
    after["backups"] = {"calendar_pre_v35_x.cnbak": "v4.4b"}
    smoke._check_existing(seeded, after)
    after["schedule_options"] = [[1, "09:30", "", "", "", "", None]]
    with pytest.raises(ValueError, match="schedule_options"):
        smoke._check_existing(seeded, after)
    del after["backups"]["calendar_pre_v35_x.cnbak"]
    after["schedule_options"] = seeded["schedule_options"]
    with pytest.raises(ValueError, match="보호 백업"):
        smoke._check_existing(seeded, after)


def test_smoke_failure_and_interruption_are_recorded(tmp_path, monkeypatch):
    exe = tmp_path / "test.exe"
    with open(exe, "wb") as stream:
        stream.write(b"synthetic")
    monkeypatch.setattr(smoke, "validate_paths", lambda *_: (exe, tmp_path))

    def failed(*_args):
        raise ValueError("unexpected data change")

    monkeypatch.setattr(smoke, "scenario", failed)
    assert smoke.main(["--exe", str(exe), "--run-dir", str(tmp_path)]) == 1
    assert verify.read_json(tmp_path / "smoke.json")["status"] == "failed"

    def interrupted(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(smoke, "scenario", interrupted)
    assert smoke.main(["--exe", str(exe), "--run-dir", str(tmp_path)]) == 130
    assert verify.read_json(tmp_path / "smoke.json")["status"] == "interrupted"


@pytest.mark.parametrize("version", [17, 18])
def test_upgrade_tooling_detects_kept_values_and_snapshot(version):
    directory = verify.create_run_dir()
    data_root = directory / "legacy"
    data_root.mkdir()
    before = smoke.data_step(f"seed_v{version}", data_root, directory / "seed.json")
    assert before["version"] == version
    conn = sqlite3.connect(data_root / "MyDesktopCalendar" / "calendar.db")
    try:
        assert [r[1] for r in conn.execute("PRAGMA table_info(schedules)")] == [
            "id", "date", "content", "created_at", "color", *(smoke.V18_COLUMNS if version == 18 else ())]
        # 위젯·집중 표에도 합성 행이 있어야 해시가 손상을 잡는다.
        for table in ("dday_widgets", "focus_widgets", "focus_sessions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
    finally:
        conn.close()
    # 마이그레이션 전에는 DB 버전이 최신이 아니라서 거절된다.
    inspect = "inspect_upgrade_v18" if version == 18 else "inspect_upgrade"
    with pytest.raises(RuntimeError, match="DB 버전이 최신이 아닙니다"):
        smoke.data_step(inspect, data_root, directory / "too-early.json")

    smoke.data_step("upgrade_source", data_root, directory / "upgrade.json")
    after = smoke.data_step(inspect, data_root, directory / "after.json")
    assert after["version"] == 19
    assert after["privacy_pin_upgraded"] is True
    assert after["tables"] == before["tables"]
    assert after["pre_snapshot"]["tables"] == before["tables"]
    assert after["pre_snapshot"]["version"] == version
    assert after["salt_sha256"] == before["salt_sha256"]
    assert after["integrity"] == ["ok"]
    assert after["error_log_bytes"] == 0
    smoke._check_upgrade(before, after)


def test_upgrade_check_rejects_changed_values_snapshot_salt_and_health():
    seeded = {"tables": {"schedules": "a" * 64, "memos": "b" * 64}, "version": 17,
              "salt_sha256": "c" * 64}
    good = {"tables": dict(seeded["tables"]), "version": 18,
            "pre_snapshot": {"tables": dict(seeded["tables"]), "version": 17},
            "salt_sha256": seeded["salt_sha256"], "integrity": ["ok"], "error_log_bytes": 0,
            "privacy_pin_upgraded": True}
    smoke._check_upgrade(seeded, good)

    def tampered(change):
        after = copy.deepcopy(good)
        change(after)
        return after

    cases = (
        (lambda a: a.update(privacy_pin_upgraded=False), "PIN"),
        (lambda a: a["tables"].update(memos="0" * 64), "기존 값을 바꿨습니다"),
        (lambda a: a["pre_snapshot"]["tables"].update(schedules="0" * 64), "스냅샷이 원본과 다릅니다"),
        (lambda a: a["pre_snapshot"].update(version=16), "스냅샷이 원본과 다릅니다"),
        (lambda a: a.update(salt_sha256="0" * 64), "salt를 바꿨습니다"),
        (lambda a: a.update(integrity=["row 1 missing from index"]), "무결성"),
        (lambda a: a.update(error_log_bytes=12), "오류 로그"),
    )
    for change, reason in cases:
        with pytest.raises(ValueError, match=reason):
            smoke._check_upgrade(seeded, tampered(change))


def test_original_columns_snapshot_refuses_paths_outside_harness():
    # tmp_path는 verify.py 실행에서 output/harness 아래(--basetemp)라 '밖' 예시가 될 수 없다.
    # 경계 검사는 파일을 열기 전에 하므로 만들지 않은 저장소 루트 경로로 확인한다.
    outside = verify.ROOT / "calendar.db"
    assert not outside.exists()
    with pytest.raises(ValueError, match="허용된 하위 경로가 아닙니다"):
        smoke._original_columns_snapshot(outside)
    with pytest.raises(ValueError, match="허용된 하위 경로가 아닙니다"):
        smoke._original_columns_snapshot(verify.ROOT / "output" / "harness")
