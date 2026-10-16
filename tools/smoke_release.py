"""하네스가 새로 빌드한 EXE를 합성 데이터로 검증한다.

Windows Job Object에 대기 중인 launcher를 먼저 넣은 뒤 EXE 실행을 허용한다.
Job handle이 닫히면 그 launcher와 자식 EXE만 종료된다. 앱 모듈 import는
격리된 데이터 작업 subprocess 안에서만 수행한다.
"""

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

if __package__:
    from .verify import ROOT, file_hash, inside, read_json, write_json
else:
    from verify import ROOT, file_hash, inside, read_json, write_json


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", W.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD),
                ("SchedulingClass", W.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits),
                ("IoInfo", ctypes.c_ulonglong * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class ProcessJob:
    """이 객체가 소유한 handle과 프로세스에만 native 작업을 수행한다."""

    def __init__(self):
        self.handle = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "CreateJobObjectW": ([ctypes.c_void_p, W.LPCWSTR], W.HANDLE),
            "SetInformationJobObject": ([W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD], W.BOOL),
            "AssignProcessToJobObject": ([W.HANDLE, W.HANDLE], W.BOOL),
            "IsProcessInJob": ([W.HANDLE, W.HANDLE, ctypes.POINTER(W.BOOL)], W.BOOL),
            "OpenProcess": ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            "CloseHandle": ([W.HANDLE], W.BOOL),
        }
        for name, (args, result) in declarations.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        process = self.kernel.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(process)

    def contains(self, pid):
        process = self.kernel.OpenProcess(0x1000, False, pid)
        if not process:
            return False  # 이미 종료됐거나 조회할 수 없는 다른 창은 대상에서 제외.
        try:
            found = W.BOOL()
            return bool(self.kernel.IsProcessInJob(process, self.handle, ctypes.byref(found)) and found.value)
        finally:
            self.kernel.CloseHandle(process)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def managed_launch(command, env, log_path):
    """자식이 stdin GO를 기다리는 프로토콜. 할당 실패 시 실행하지 않는다."""
    job = ProcessJob()
    process = None
    try:
        with open(log_path, "wb") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                       stdout=log, stderr=subprocess.STDOUT, shell=False)
            job.assign(process.pid)
            process.stdin.write(b"GO\n")
            process.stdin.flush()
            process.stdin.close()
            yield job, process
    finally:
        try:
            job.close()  # 할당된 launcher와 모든 후손의 handle 소유권 범위만 정리.
        finally:
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()  # GO 전 실패하면 EOF로 launcher가 종료된다.
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()  # 할당 실패 시에도 우리가 만든 launcher 하나만 대상.
                    process.wait(timeout=10)


def windows_in_job(job):
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    declarations = {
        "EnumWindows": ([callback_type, W.LPARAM], W.BOOL),
        "GetWindowThreadProcessId": ([W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD),
        "IsWindowVisible": ([W.HWND], W.BOOL),
        "GetWindowTextW": ([W.HWND, W.LPWSTR, ctypes.c_int], ctypes.c_int),
        "GetWindowRect": ([W.HWND, ctypes.POINTER(W.RECT)], W.BOOL),
        "SendMessageTimeoutW": ([W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT,
                                 W.UINT, ctypes.POINTER(ctypes.c_size_t)], ctypes.c_size_t),
    }
    for name, (args, result) in declarations.items():
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    windows = []

    @callback_type
    def visit(hwnd, _):
        pid = W.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if job.contains(pid.value) and user.IsWindowVisible(hwnd):
            title, rect, reply = ctypes.create_unicode_buffer(512), W.RECT(), ctypes.c_size_t()
            user.GetWindowTextW(hwnd, title, len(title))
            user.GetWindowRect(hwnd, ctypes.byref(rect))
            responding = bool(user.SendMessageTimeoutW(hwnd, 0, 0, 0, 2, 300, ctypes.byref(reply)))
            windows.append({"hwnd": int(hwnd), "pid": pid.value, "title": title.value,
                            "width": rect.right - rect.left, "height": rect.bottom - rect.top,
                            "responding": responding})
        return True

    if not user.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return windows


def accept_first_run_setup(job, window):
    """이번 검사 Job의 실제 최초 설정창에만 Enter를 보낸다 (제품 우회 없음)."""
    current = next((w for w in windows_in_job(job) if w["hwnd"] == window["hwnd"]
                    and w["pid"] == window["pid"]
                    and w["title"] == "기후노트 — 처음 설정" and w["responding"]), None)
    if current is None:
        raise ValueError("소유한 최초 설정창을 확인하지 못했습니다.")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.PostMessageW.restype = W.BOOL
    for message in (0x0100, 0x0101):  # WM_KEYDOWN / WM_KEYUP, VK_RETURN
        if not user.PostMessageW(current["hwnd"], message, 0x0D, 0):
            raise ctypes.WinError(ctypes.get_last_error())


def validate_paths(exe, run_dir):
    boundary = inside(ROOT / "output" / "harness", ROOT)
    directory = inside(run_dir, boundary)
    if not directory.is_dir():
        raise ValueError("하네스 실행 폴더가 없습니다.")
    binary = inside(exe, directory / "dist")
    if binary.suffix.lower() != ".exe" or not binary.is_file():
        raise ValueError("이번 실행의 dist 하위 EXE만 검사할 수 있습니다.")
    return binary, directory


def data_env(data_root):
    boundary = inside(ROOT / "output" / "harness", ROOT)
    directory = inside(data_root, boundary)
    env = os.environ.copy()
    env.update(LOCALAPPDATA=str(directory), CLIMATENOTE_SKIP_STARTUP_REFRESH="1",
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.pop("CLIMATENOTE_TEST_APPDATA", None)
    return env


def data_step(action, data_root, result_path):
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "_data", action,
         str(data_root), str(result_path)], cwd=ROOT, env=data_env(data_root),
        timeout=30, capture_output=True, encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"합성 데이터 {action} 실패 ({completed.returncode}): {completed.stderr}")
    return read_json(result_path)


def _dataset_snapshot(db, security):
    tables = ("schedules", "memos", "sticky_notes", "dday_widgets", "focus_widgets",
              "focus_sessions", "shortcuts", "app_settings")
    with db._connection(read_only=True, enable_wal=False) as conn:
        rows = {name: [dict(row) for row in conn.execute(f"SELECT * FROM {name} ORDER BY 1")]
                for name in tables}  # table는 위 고정 allowlist에서만 선택.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    logical = json.loads(json.dumps(rows))
    for table, field in (("schedules", "content"), ("memos", "content"),
                         ("sticky_notes", "content"), ("dday_widgets", "name"),
                         ("focus_widgets", "goal"), ("focus_sessions", "goal")):
        for row in logical[table]:
            if row[field]:
                row[field] = security.decrypt(row[field])
    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {"version": version, "integrity": integrity,
            "raw_hashes": {name: digest(value) for name, value in rows.items()},
            "logical_hashes": {name: digest(value) for name, value in logical.items()},
            "ids": {name: [row.get("id", row.get("key")) for row in value] for name, value in rows.items()},
            "salt_sha256": file_hash(security.SALT_FILE)}


def _data_worker(action, data_root, result_path):
    boundary = inside(ROOT / "output" / "harness", ROOT)
    directory = inside(data_root, boundary)
    result_path = inside(result_path, directory.parent)
    os.environ["LOCALAPPDATA"] = str(directory)
    os.environ["CLIMATENOTE_SKIP_STARTUP_REFRESH"] = "1"
    sys.path.insert(0, str(ROOT))
    import database as db
    import security

    if action == "seed":
        if db.DB_FILE.exists():
            raise ValueError("새 합성 데이터 폴더만 초기화할 수 있습니다.")
        db.migrate()
        day = date.today().isoformat()
        for color, _ in db.SCHEDULE_COLORS:
            db.add_schedule(day, "하네스 합성 일정 " + color, color)
        db.save_memo(day, "하네스 합성 메모")
        opened = db.create_sticky_note()
        db.update_sticky_note(opened, content="하네스 열린 스티키")
        trashed = db.create_sticky_note()
        db.update_sticky_note(trashed, content="하네스 휴지통 스티키")
        db.trash_sticky_note(trashed)
        db.create_dday_widget("하네스 D-Day", "2027-01-01")
        focus = db.create_focus_widget("하네스 집중 목표")
        db.create_focus_session(focus, "하네스 집중 기록", "25/5", 25, 5,
                                day + " 09:00:00", day + " 09:25:00", 1500, True)
        db.update_shortcut(1, "하네스 폴더", str(directory))
        db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
        db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
        db.save_setting(db.SETTING_SHOW_SIDEBAR, "0")
        db.save_schedule_palette(("#FF9F68", "#80CFA9", "#B197FC"))
        result = _dataset_snapshot(db, security)
    elif action == "corrupt":
        # 시작 차단 때 이미 존재하던 정상 보호본도 불변인지 검사한다.
        db.backup_before_operation("import")
        # 합성 DB의 salt만 손상. 원본 사용자 데이터 입력 경로는 제공하지 않는다.
        with open(security.SALT_FILE, "wb") as stream:
            stream.write(b"x" * 32)
        # backup 검증이 채운 캐시를 비워 손상된 디스크 salt로 다시 검사한다.
        security._fernet_cache = None
        security._legacy_fernet_cache = None
        result = {"code": db.inspect_startup_data_health().code}
    elif action == "seed_v17":
        if db.DB_FILE.exists():
            raise ValueError("새 합성 데이터 폴더만 초기화할 수 있습니다.")
        db.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        day = date.today().isoformat()
        stamp = day + " 09:00:00"
        # _connection은 마이그레이션하지 않는다. v17 틀 그대로 user_version 17을 만든다.
        with db._connection(enable_wal=False) as conn:
            with open(V17_FIXTURE, encoding="utf-8") as fixture:
                conn.executescript(fixture.read())
            for color, _ in db.SCHEDULE_COLORS:
                conn.execute(
                    "INSERT INTO schedules (date, content, created_at, color) VALUES (?, ?, ?, ?)",
                    (day, security.encrypt("v17 합성 일정 " + color), stamp, color))
            conn.execute("INSERT INTO memos (date, content, updated_at) VALUES (?, ?, ?)",
                         (day, security.encrypt("v17 합성 메모"), stamp))
            # 닫힌 스티키로 둔다. 열린 스티키는 앱이 창 크기를 5mm 격자에 맞춰(300×400→306×396 등)
            # 저장하는 기존 동작이 있어, 실행 시간에 따라 값 비교가 흔들린다(v4.0부터 같은 동작).
            conn.execute("INSERT INTO sticky_notes (content, is_open) VALUES (?, 0)",
                         (security.encrypt("v17 스티키"),))
            # 나머지 세 표도 값이 있어야 해시가 손상을 잡는다. 같은 이유로 위젯은 닫힌 채로 둔다.
            conn.execute("INSERT INTO dday_widgets (name, target_date, is_open) VALUES (?, ?, 0)",
                         (security.encrypt("v17 D-Day"), "2027-01-01"))
            conn.execute(
                "INSERT INTO focus_widgets (goal, is_open, created_at) VALUES (?, 0, ?)",
                (security.encrypt("v17 집중 목표"), stamp))
            conn.execute(
                "INSERT INTO focus_sessions (widget_id, goal, started_at, ended_at, "
                "elapsed_seconds, completed, created_at) VALUES (1, ?, ?, ?, 1500, 1, ?)",
                (security.encrypt("v17 집중 기록"), stamp, day + " 09:25:00", stamp))
            conn.execute("PRAGMA user_version = 17")
            conn.commit()
        result = _original_columns_snapshot(db.DB_FILE)
        result["salt_sha256"] = file_hash(security.SALT_FILE)
    elif action == "upgrade_source":
        # EXE 없이 같은 시작 경로를 소스로 실행한다(검사 도구 자체 시험용).
        import main as app_main
        app_main._initialize_database()
        result = {"ok": True}
    elif action == "inspect_upgrade":
        health = db.inspect_startup_data_health()
        if not health.ok:
            raise ValueError(f"업그레이드 뒤 데이터 건강 검사 실패: {health.code}")
        result = _original_columns_snapshot(db.DB_FILE)
        if result["version"] != db.CURRENT_SCHEMA_VERSION:
            raise ValueError("업그레이드 뒤 DB 버전이 최신이 아닙니다.")
        with db._connection(read_only=True, enable_wal=False) as conn:
            result["integrity"] = [row[0] for row in conn.execute("PRAGMA integrity_check")]
            changed = conn.execute(
                "SELECT COUNT(*) FROM schedules WHERE start_time != '' OR end_date != '' "
                "OR repeat_rule != '' OR repeat_until != '' OR repeat_skip != '' "
                "OR alarm_before IS NOT NULL").fetchone()[0]
        if changed:
            raise ValueError("업그레이드 뒤 새 칸이 기본값이 아닙니다.")
        snapshot = db.APP_DIR / "backups" / "calendar_pre_v18_v17.db"
        if not snapshot.is_file():
            raise ValueError("마이그레이션 전 스냅샷이 없습니다.")
        result["pre_snapshot"] = _original_columns_snapshot(snapshot)
        result["salt_sha256"] = file_hash(security.SALT_FILE)
        log = db.APP_DIR / "error.log"
        result["error_log_bytes"] = log.stat().st_size if log.exists() else 0
    elif action == "inspect":
        health = db.inspect_startup_data_health()
        if not health.ok:
            raise ValueError(f"실행 후 데이터 건강 검사 실패: {health.code}")
        result = _dataset_snapshot(db, security)
        result["salt_bytes"] = security.SALT_FILE.stat().st_size
        result["calendar_scale"] = db.get_setting(db.SETTING_CALENDAR_SCALE)
        if result["salt_bytes"] != 32:
            raise ValueError("salt 크기가 32바이트가 아닙니다.")
        if result["version"] != db.CURRENT_SCHEMA_VERSION or result["integrity"] != ["ok"]:
            raise ValueError("DB 버전 또는 무결성 불일치")
        bundles = sorted((db.APP_DIR / "backups").glob("*.cnbak"))
        result["backups"] = {p.name: db.validate_backup_bundle(p)["app_version"] for p in bundles}
        if not any(p.name.startswith("calendar_auto_") for p in bundles):
            raise ValueError("검증 가능한 일일 백업이 없습니다.")
        log = db.APP_DIR / "error.log"
        result["error_log_bytes"] = log.stat().st_size if log.exists() else 0
        if result["error_log_bytes"]:
            raise ValueError("격리 실행 오류 로그가 비어 있지 않습니다.")
    else:
        raise ValueError(f"지원하지 않는 데이터 작업: {action}")
    write_json(result_path, result)


V18_COLUMNS = ("start_time", "end_date", "repeat_rule", "repeat_until", "repeat_skip", "alarm_before")
V17_FIXTURE = ROOT / "tests" / "fixtures" / "schema_v17.sql"


def _original_columns_snapshot(path):
    """모든 표의 v17 열 값 해시(v18 새 열 제외)와 user_version."""
    boundary = inside(ROOT / "output" / "harness", ROOT)
    resolved = inside(path, boundary)
    # 상위 프로세스(리허설)도 부르므로 database를 import하지 않고 직접 읽기 전용으로 연다.
    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        hashes = {}
        for table in tables:  # 표·열 이름은 sqlite_master·table_info에서만 온다.
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                       if row[1] not in V18_COLUMNS]
            rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid").fetchall()
            hashes[table] = hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()
    return {"tables": hashes, "version": version}


def _check_upgrade(seeded, after):
    """업그레이드 뒤 값·스냅샷·salt·무결성·오류 로그가 시작 전과 같은지 검사한다."""
    if after["tables"] != seeded["tables"]:
        raise ValueError("업그레이드가 기존 값을 바꿨습니다.")
    if after["pre_snapshot"] != {"tables": seeded["tables"], "version": 17}:
        raise ValueError("마이그레이션 전 스냅샷이 원본과 다릅니다.")
    if after["salt_sha256"] != seeded["salt_sha256"]:
        raise ValueError("업그레이드가 salt를 바꿨습니다.")
    if after["integrity"] != ["ok"]:
        raise ValueError("업그레이드 뒤 DB 무결성 검사가 통과하지 못했습니다.")
    if after["error_log_bytes"]:
        raise ValueError("업그레이드 뒤 오류 로그가 비어 있지 않습니다.")


def protected_hashes(data_root):
    """시작 차단 시 DB/salt/기존 백업이 그대로인지 확인한다."""
    folder = data_root / "MyDesktopCalendar"
    paths = [folder / "calendar.db", folder / ".salt"]
    paths.extend(sorted((folder / "backups").glob("*")))
    return {path.relative_to(folder).as_posix(): file_hash(path) for path in paths if path.is_file()}


def scenario(exe, run_dir, name):
    folder = run_dir / "smoke" / name
    folder.mkdir(parents=True)  # 기존 시나리오 폴더는 재사용하지 않는다.
    data_root = folder / "appdata"
    data_root.mkdir()
    before = None
    if name == "upgrade":
        before = data_step("seed_v17", data_root, folder / "before.json")
    elif name != "fresh":
        before = data_step("seed", data_root, folder / "before.json")
    if name == "blocked":
        data_step("corrupt", data_root, folder / "corrupt.json")
        before = protected_hashes(data_root)
    expected_error = "데이터 보호를 위해 실행을 중단했습니다"
    command = [sys.executable, str(Path(__file__).resolve()), "_launch", str(exe)]
    observed = []
    ready = False
    setup_seen = False
    with managed_launch(command, data_env(data_root), folder / "exe.log") as (job, process):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{name}: 창 준비 전 EXE 종료 ({process.returncode})")
            observed = windows_in_job(job)
            setup = [w for w in observed if w["title"] == "기후노트 — 처음 설정" and w["responding"]]
            if setup:
                if name != "fresh":
                    raise RuntimeError(f"{name}: 기존 데이터에 최초 설정이 표시됐습니다.")
                if not setup_seen:
                    app_dir = data_root / "MyDesktopCalendar"
                    if any((app_dir / p).exists() for p in ("calendar.db", ".salt", "backups")):
                        raise RuntimeError("최초 크기 선택 전에 DB/salt/백업이 생성됐습니다.")
                    accept_first_run_setup(job, setup[0])
                    setup_seen = True
            errors = [w for w in observed if w["title"] == expected_error and w["responding"]]
            app_windows = [w for w in observed if w["width"] >= 350 and w["height"] >= 450
                           and w["responding"] and w["title"] not in
                           (expected_error, "기후노트 — 처음 설정")]
            if name == "blocked":
                ready = bool(errors) and not app_windows
            else:
                if errors:
                    raise RuntimeError(f"{name}: 정상 데이터로 시작이 차단됐습니다.")
                ready = bool(app_windows) and any(
                    (data_root / "MyDesktopCalendar" / "backups").glob("calendar_auto_*.cnbak")
                )
            if ready:
                break
            time.sleep(0.2)
        if not ready:
            raise TimeoutError(f"{name}: 창/백업 준비 시간 초과. 관측 창={observed}")
    result = {"status": "passed", "windows": observed, "cleanup": "job_close_forced",
              "graceful_quit_verified": False, "first_run_setup_seen": setup_seen}
    if name == "blocked":
        after = protected_hashes(data_root)
        if before != after:
            raise ValueError("시작 차단 후 원본 DB/salt/백업이 변경됐습니다.")
        result["preserved"] = after
    else:
        if name == "upgrade":
            after = data_step("inspect_upgrade", data_root, folder / "after.json")
            _check_upgrade(before, after)
            result["data"] = after
            return result
        after = data_step("inspect", data_root, folder / "after.json")
        if name == "fresh" and (not setup_seen or after["calendar_scale"] != "compact"):
            raise ValueError("최초 설정 표시/선택한 크기 저장을 확인하지 못했습니다.")
        if before is not None:
            for key in ("raw_hashes", "logical_hashes", "ids", "salt_sha256"):
                if before[key] != after[key]:
                    raise ValueError(f"기존 합성 데이터 변경: {key}")
            if not any(name.startswith("calendar_pre_v35_") for name in after["backups"]):
                raise ValueError("기존 데이터 최초 보호 백업이 없습니다.")
        result["data"] = after
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    exe, directory = validate_paths(args.exe, args.run_dir)
    report = {"status": "running", "exe_sha256": file_hash(exe), "scenarios": {}}
    write_json(directory / "smoke.json", report)
    try:
        for name in ("fresh", "existing", "blocked", "upgrade"):
            print(f"[smoke] {name}", flush=True)
            report["scenarios"][name] = {"status": "running"}
            write_json(directory / "smoke.json", report)
            started = time.monotonic()
            report["scenarios"][name] = scenario(exe, directory, name)
            report["scenarios"][name]["seconds"] = round(time.monotonic() - started, 3)
            write_json(directory / "smoke.json", report)
        report["status"] = "passed"
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["scenarios"][name] = {"status": "failed", "error": report["error"]}
        print(report["error"], file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        report["error"] = "사용자가 EXE 검사를 중단했습니다."
        report["scenarios"][name] = {"status": "interrupted"}
        return 130
    finally:
        write_json(directory / "smoke.json", report)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_launch":
        if sys.stdin.buffer.readline() != b"GO\n":
            raise SystemExit(2)
        with subprocess.Popen(sys.argv[2:], cwd=ROOT, env=os.environ.copy(), shell=False) as child:
            raise SystemExit(child.wait())
    elif len(sys.argv) > 1 and sys.argv[1] == "_data":
        _data_worker(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        raise SystemExit(main())
