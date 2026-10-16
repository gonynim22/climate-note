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
    assert before["version"] == 18
    assert before["integrity"] == ["ok"]
    assert len(before["ids"]["schedules"]) == 3
    assert len(before["ids"]["sticky_notes"]) == 2
    assert len(before["ids"]["focus_sessions"]) == 1
    protected = smoke.protected_hashes(data_root)
    with pytest.raises(RuntimeError, match="seed"):
        smoke.data_step("seed", data_root, directory / "again.json")
    assert smoke.protected_hashes(data_root) == protected
    corrupt = smoke.data_step("corrupt", data_root, directory / "corrupt.json")
    assert corrupt["code"] != "ok"
    assert smoke.protected_hashes(data_root)["calendar.db"] == protected["calendar.db"]


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


def test_upgrade_tooling_detects_kept_values_and_snapshot():
    directory = verify.create_run_dir()
    data_root = directory / "legacy"
    data_root.mkdir()
    before = smoke.data_step("seed_v17", data_root, directory / "seed_v17.json")
    assert before["version"] == 17
    conn = sqlite3.connect(data_root / "MyDesktopCalendar" / "calendar.db")
    try:
        assert [r[1] for r in conn.execute("PRAGMA table_info(schedules)")] == [
            "id", "date", "content", "created_at", "color"]
        # 위젯·집중 표에도 합성 행이 있어야 해시가 손상을 잡는다.
        for table in ("dday_widgets", "focus_widgets", "focus_sessions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
    finally:
        conn.close()
    # 마이그레이션 전에는 DB 버전이 최신이 아니라서 거절된다.
    with pytest.raises(RuntimeError, match="DB 버전이 최신이 아닙니다"):
        smoke.data_step("inspect_upgrade", data_root, directory / "too-early.json")

    smoke.data_step("upgrade_source", data_root, directory / "upgrade.json")
    after = smoke.data_step("inspect_upgrade", data_root, directory / "after.json")
    assert after["version"] == 18
    assert after["tables"] == before["tables"]
    assert after["pre_snapshot"]["tables"] == before["tables"]
    assert after["pre_snapshot"]["version"] == 17
    assert after["salt_sha256"] == before["salt_sha256"]
    assert after["integrity"] == ["ok"]
    assert after["error_log_bytes"] == 0
    smoke._check_upgrade(before, after)


def test_upgrade_check_rejects_changed_values_snapshot_salt_and_health():
    seeded = {"tables": {"schedules": "a" * 64, "memos": "b" * 64}, "version": 17,
              "salt_sha256": "c" * 64}
    good = {"tables": dict(seeded["tables"]), "version": 18,
            "pre_snapshot": {"tables": dict(seeded["tables"]), "version": 17},
            "salt_sha256": seeded["salt_sha256"], "integrity": ["ok"], "error_log_bytes": 0}
    smoke._check_upgrade(seeded, good)

    def tampered(change):
        after = copy.deepcopy(good)
        change(after)
        return after

    cases = (
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


def test_original_columns_snapshot_refuses_paths_outside_harness(tmp_path):
    outside = tmp_path / "calendar.db"
    outside.write_bytes(b"")
    with pytest.raises(ValueError):
        smoke._original_columns_snapshot(outside)
