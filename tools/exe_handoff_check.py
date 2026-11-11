"""옛 EXE → 새 EXE → 옛 EXE를 같은 합성 데이터로 번갈아 띄워, 서로의 데이터를 그대로 읽는지 본다.

배포 EXE의 구성(예: Python용 OpenSSL 유무)이 바뀌어도 암호화 열쇠가 같아 기존 데이터를 읽고 바꾸지 않는지 확인하는
증거 도구다. EXE를 띄울 때마다 본 창과 일일 백업이 준비되는지 보고, 닫은 뒤 원문·복호화 해시·ID·세부 설정·일정 연결·
salt를 처음 만든 합성 데이터와 대조하며 보호 백업이 있는지 본다.
열쇠가 달라지면 시작 전 건강 검사가 '데이터 보호를 위해 실행을 중단했습니다' 창을 띄우고, 이 도구는 실패한다.
실사용 AppData는 쓰지 않는다. 새 하네스 실행 폴더에 두 EXE를 복사하고 합성 데이터를 한 번 만든다.

    .\\.venv\\Scripts\\python.exe tools/exe_handoff_check.py --old dist\\기후노트_v4.8.exe --new <release 실행 폴더>\\dist\\기후노트_v4.9.exe
"""

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

if __package__:
    from . import smoke_release as smoke
    from .verify import create_run_dir, file_hash, write_json
else:
    import smoke_release as smoke
    from verify import create_run_dir, file_hash, write_json

BLOCKED_TITLE = "데이터 보호를 위해 실행을 중단했습니다"
SETUP_TITLE = "기후노트 — 처음 설정"
READY_SECONDS = 60
SETTLE_SECONDS = 3  # 본 창이 뜬 뒤에도 더 지켜본다(뒤늦은 차단·종료)
ORDER = ("old", "new", "old")


def run_once(exe, data_root, log_path):
    """EXE를 띄워 본 창과 일일 백업이 준비될 때까지 기다린 뒤 닫는다. 걸린 시간을 돌려준다."""
    command = [sys.executable, str(Path(smoke.__file__).resolve()), "_launch", str(exe)]
    backups = data_root / "MyDesktopCalendar" / "backups"
    started = time.monotonic()
    with smoke.managed_launch(command, smoke.data_env(data_root), log_path) as (job, process):
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"창 준비 전 EXE 종료 ({process.returncode})")
            windows = [w for w in smoke.windows_in_job(job) if w["responding"]]
            titles = {w["title"] for w in windows}
            if BLOCKED_TITLE in titles:
                raise RuntimeError("기존 합성 데이터로 시작이 차단됐습니다(열쇠·데이터 불일치).")
            if SETUP_TITLE in titles:
                raise RuntimeError("기존 합성 데이터인데 최초 설정이 표시됐습니다.")
            main_window = any(w["width"] >= 350 and w["height"] >= 450
                              and w["title"] not in (BLOCKED_TITLE, SETUP_TITLE, smoke.UPGRADE_NOTICE_TITLE)
                              for w in windows)
            if main_window and any(backups.glob("calendar_auto_*.cnbak")):
                break
            if time.monotonic() - started > READY_SECONDS:
                raise TimeoutError(f"창/백업 준비 시간 초과. 관측 창={sorted(titles)}")
            time.sleep(0.2)
        ready = round(time.monotonic() - started, 3)
        time.sleep(SETTLE_SECONDS)
        if process.poll() is not None:
            raise RuntimeError(f"창이 뜬 뒤 EXE 종료 ({process.returncode})")
        if BLOCKED_TITLE in {w["title"] for w in smoke.windows_in_job(job)}:
            raise RuntimeError("창이 뜬 뒤 시작 차단 창이 표시됐습니다.")
    return ready


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", required=True, help="이전 배포 EXE")
    parser.add_argument("--new", required=True, help="이번에 만든 EXE")
    args = parser.parse_args(argv)
    run_dir = create_run_dir()
    print(f"결과 폴더: {run_dir}", flush=True)
    report = {"status": "running", "order": list(ORDER), "exes": {}, "steps": []}
    code = 1
    try:
        exes = {}
        for label, given in (("old", args.old), ("new", args.new)):
            source = Path(given).resolve()
            if not source.is_file():
                raise ValueError(f"EXE가 없습니다: {source}")
            target = run_dir / "dist" / label / source.name
            target.parent.mkdir(parents=True)
            shutil.copy2(source, target)
            exes[label], _ = smoke.validate_paths(target, run_dir)
            report["exes"][label] = {"source": str(source), "sha256": file_hash(target), "bytes": target.stat().st_size}
        folder = run_dir / "handoff"
        data_root = folder / "appdata"
        data_root.mkdir(parents=True)
        seeded = smoke.data_step("seed", data_root, folder / "before.json")
        smoke._check_seed_options(seeded)
        for index, label in enumerate(ORDER, 1):
            print(f"[handoff] {index}/{len(ORDER)} {label}", flush=True)
            step = {"order": index, "exe": label, "status": "running"}
            report["steps"].append(step)
            step["ready_seconds"] = run_once(exes[label], data_root, folder / f"{index}-{label}.log")
            after = smoke.data_step("inspect", data_root, folder / f"{index}-{label}-after.json")
            smoke._check_existing(seeded, after)  # 값·세부 설정·salt가 seed와 같고 보호 백업이 있다
            step["status"] = "passed"
        report["status"] = "passed"
        code = 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        if report["steps"] and report["steps"][-1]["status"] == "running":
            report["steps"][-1]["status"] = "failed"
        print(report["error"], file=sys.stderr)
    write_json(run_dir / "handoff.json", report)
    print(json.dumps({"status": report["status"], "run": run_dir.name}, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
