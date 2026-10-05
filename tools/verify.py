"""Windows 개발 검증: doctor / quick / data / full / release.

앱을 import하지 않고 환경을 검사한다. 모든 실행 증거는 output/harness에
보존하며 테스트 실패·중단·검사 중 소스 변경을 성공으로 보고하지 않는다.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import tempfile
import time
import uuid
from defusedxml import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DIRECT_DEPENDENCIES = (
    "PySide6", "PySide6-Fluent-Widgets", "cryptography", "python-dotenv",
    "pytest", "pytest-qt", "pytest-timeout", "PyInstaller", "pywin32", "defusedxml",
)
QUICK_TESTS = (
    "tests/test_app_paths.py", "tests/test_startup_path.py",
    "tests/test_fetch_data.py", "tests/test_verify.py",
    "tests/test_release_smoke.py",
    "tests/test_database.py::TestMigration::test_fresh_install_is_v17",
    "tests/test_data_safety.py::test_health_gate_missing_salt_fails_without_creating_replacement",
    "tests/test_ui.py::test_schedule_right_click_menu_edits_and_deletes",
    "tests/test_ui.py::test_prepare_for_quit_blocks_when_sticky_save_fails",
)
DATA_TESTS = tuple(f"tests/test_{name}.py" for name in (
    "database", "security", "data_safety", "edge_cases", "stress",
    "startup_path", "ui", "ui_sticky", "ui_sticky_panel", "ui_data_lifecycle", "widget_limits",
))
MANUAL_CHECKS = (
    "정상 종료 직전 스티키 저장 및 실제 설정/휴지통 동작",
    "Win+D 직후 Explorer/브라우저 전환",
    "음수 좌표/혼합 DPI/KVM 전환",
    "특정 PC 멈춤 재현", "Defender 검사", "라이선스/SBOM/서명 후속 과제",
)


class VerificationFailure(ValueError):
    """실행 환경 오류가 아닌 산출물 검증 실패 (종료 코드 1)."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def inside(path, parent):
    """출력 루트 자체 또는 심볼릭 링크로 밖을 가리키는 대상은 거부한다."""
    resolved, boundary = Path(path).resolve(), Path(parent).resolve()
    if resolved == boundary or not resolved.is_relative_to(boundary):
        raise ValueError(f"허용된 하위 경로가 아닙니다: {path}")
    return resolved


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path, text):
    path = Path(path)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            pending = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()  # 이 호출이 생성한 임시 파일만 정리한다.


def write_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def create_run_dir(root=ROOT):
    output = inside(Path(root) / "output" / "harness", root)
    output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:10]
    directory = inside(output / run_id, output)
    directory.mkdir()
    return directory


def isolated_env(run_dir):
    directory = inside(run_dir, ROOT / "output" / "harness")
    appdata = inside(directory / "appdata", directory)
    appdata.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        LOCALAPPDATA=str(appdata), CLIMATENOTE_TEST_APPDATA=str(appdata),
        CLIMATENOTE_SKIP_STARTUP_REFRESH="1", PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
    )
    # 외부 pytest 옵션으로 선택된 검사/보고서/격리 경로가 바뀌지 않게 한다.
    env.pop("PYTEST_ADDOPTS", None)
    return env


def doctor(root=ROOT):
    result = {"python": sys.version, "executable": sys.executable,
              "platform": platform.platform(), "dependencies": {}, "errors": []}
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13):
        result["errors"].append("검증 환경은 Windows / Python 3.13입니다.")
    with open(Path(root) / "requirements-lock.txt", encoding="utf-8") as stream:
        pinned = {
            name.split("[", 1)[0].lower(): version
            for line in stream if "==" in line and not line.lstrip().startswith("#")
            for name, version in [line.strip().split("==", 1)]
        }
    for name in DIRECT_DEPENDENCIES:
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = None
        expected = pinned.get(name.lower())
        result["dependencies"][name] = {"expected": expected, "actual": actual}
        if expected is None or actual != expected:
            result["errors"].append(f"{name}: 설치={actual}, lock={expected}")
    for name in ("pytest.ini", "tests/conftest.py", "main.py", "security.py",
                 "database.py", "app_info.py", "build.spec", "holidays.py"):
        if not (Path(root) / name).is_file():
            result["errors"].append(f"필수 파일 없음: {name}")
    return result


def git_output(*args, root=ROOT):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        encoding="utf-8", errors="replace", shell=False,
    ).stdout


def source_snapshot(root=ROOT):
    root = Path(root).resolve()
    paths = git_output("ls-files", "--cached", "--others", "--exclude-standard",
                       "-z", root=root).split("\0")
    hashes = {}
    for name in sorted(set(paths)):
        if not name:
            continue
        parts = Path(name).parts
        allowed_tree = len(parts) == 1 or parts[0] in {
            "tools", "tests", "docs", "resources", "fonts", "icon", "licenses",
        }
        if not allowed_tree or (len(parts) == 1 and name.startswith(".")):
            continue
        # 진행 노트·계획 수정은 실행 결과에 대한 기록이므로 소스 입력에서 제외.
        if name.replace("\\", "/").startswith(("docs/work/", "docs/superpowers/")):
            continue
        if Path(name).suffix.lower() not in {
            ".py", ".md", ".txt", ".ini", ".spec", ".svg", ".png", ".ico", ".ttf",
        }:
            continue
        path = inside(root / name, root)
        hashes[name.replace("\\", "/")] = file_hash(path) if path.is_file() else None
    return {"head": git_output("rev-parse", "HEAD", root=root).strip(),
            "dirty": bool(git_output("status", "--porcelain", root=root).strip()),
            "files": hashes}


def validate_targets(targets, root=ROOT):
    normalized = []
    for target in targets:
        filename, *node = target.split("::")
        if not filename or filename.startswith("-") or Path(filename).is_absolute():
            raise ValueError(f"잘못된 테스트 대상: {target}")
        path = inside(Path(root) / filename, Path(root) / "tests")
        if not path.is_file() or path.suffix != ".py":
            raise ValueError(f"테스트 파일 없음: {target}")
        normalized.append("::".join([path.relative_to(root).as_posix(), *node]))
    return list(dict.fromkeys(normalized))


def pytest_command(profile, extra, run_dir):
    targets = (list(QUICK_TESTS) + list(extra) if profile == "quick"
               else list(DATA_TESTS) if profile == "data" else ["tests"])
    if profile in {"quick", "data"}:
        targets = validate_targets(targets)
    return [sys.executable, "-m", "pytest", *targets, "-q", "--timeout=120",
            "--basetemp", str(run_dir / "pytest-tmp"),
            "-o", f"cache_dir={run_dir / 'pytest-cache'}",
            "--junitxml", str(run_dir / "pytest.xml")]


def run_step(name, command, run_dir, env, *, timeout=1800, report=None):
    if __package__:
        from .smoke_release import managed_launch
    else:
        from smoke_release import managed_launch
    step = {"name": name, "command": command, "status": "running",
            "started_at": utc_now(), "log": f"{name}.log"}
    if report is not None:
        report["steps"].append(step)
        save_report(run_dir, report)
    started = time.monotonic()
    process = None
    print(f"[{name}] 시작 — {run_dir / step['log']}", flush=True)
    launcher = [sys.executable, str(ROOT / "tools/smoke_release.py"), "_launch", *command]
    try:
        with managed_launch(launcher, env, run_dir / step["log"]) as (_, process):
            step["returncode"] = process.wait(timeout=timeout)
            step["status"] = "passed" if process.returncode == 0 else "failed"
    except KeyboardInterrupt:
        step["status"] = "interrupted"
        raise
    finally:
        if step["status"] == "running":
            step["status"] = "failed"
        if process is not None:
            step["returncode"] = process.returncode
        step["seconds"] = round(time.monotonic() - started, 3)
        step["finished_at"] = utc_now()
    print(f"[{name}] {step['status']} ({step['seconds']}초)", flush=True)
    return step


def junit_result(path):
    with open(path, "rb") as stream:
        tree = ET.parse(stream)
    cases = list(tree.iter("testcase"))
    counts = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    for case in cases:
        for tag, key in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            if case.find(tag) is not None:
                counts[key] += 1
    counts["passed"] = counts["tests"] - sum(counts[k] for k in ("failures", "errors", "skipped"))
    return counts


def pytest_exit(code, counts):
    if code in {2, 3, 4, 5} or not counts or counts["tests"] == 0:
        return 2
    if code != 0 or counts["failures"] or counts["errors"]:
        return 1
    if not counts["passed"]:
        return 2
    return 0


def save_report(run_dir, report):
    lines = ["# 기후노트 검증 결과", "",
             f"- 실행: `{run_dir.name}`", f"- 프로필: `{report['profile']}`",
             f"- 상태: `{report['status']}`", f"- 종료 코드: `{report.get('exit_code', 'pending')}`"]
    if "tests" in report:
        lines.append(f"- 테스트: `{json.dumps(report['tests'])}`")
    if report.get("error"):
        lines.append(f"- 오류: {report['error']}")
    lines += ["", "## 실행 단계", "", "| 단계 | 결과 | 실제 종료 코드 | 로그 |",
              "|---|---|---|---|"]
    for step in report["steps"]:
        lines.append(f"| {step['name']} | {step['status']} | {step.get('returncode', '')} | [{step['log']}]({step['log']}) |")
    lines += ["", "## 수동 확인", "", "자동 검증 결과는 배포 승인이나 아래 항목의 통과를 의미하지 않습니다.", ""]
    lines.extend(f"- [ ] {item}" for item in MANUAL_CHECKS)
    lines += ["", "상세 환경·명령·입력 해시·EXE 결과는 [result.json](result.json)에 있습니다.", ""]
    # summary 실패도 성공 JSON을 남기지 않도록 summary를 먼저 게시한다.
    atomic_text(run_dir / "summary.md", "\n".join(lines))
    try:
        write_json(run_dir / "result.json", report)
    except OSError:
        # 최종 JSON 게시 실패 때 앞서 작성한 summary도 통과처럼 남기지 않는다.
        atomic_text(run_dir / "summary.md", (
            "# 기후노트 검증 결과\n\n"
            "상태: `failed` / 종료 코드: `2`\n\n"
            "result.json 기록에 실패하여 결과를 확정하지 못했습니다. "
            "이 실행은 통과 근거로 사용할 수 없습니다.\n"
        ))
        raise


def artifact_metadata(exe, env):
    if not exe.is_file() or exe.stat().st_size == 0:
        raise VerificationFailure("이번 빌드의 EXE가 없습니다.")
    command = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        # pwsh에서 Python을 거치면 PSModulePath가 Windows PowerShell로 상속된다.
        # 다른 PowerShell 버전의 Security 모듈을 잘못 자동 로드하지 않게 한다.
        "Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security') -ErrorAction Stop; "
        "$f=Get-Item -LiteralPath $env:CLIMATENOTE_VERIFY_EXE; "
        "$s=Get-AuthenticodeSignature -LiteralPath $f.FullName; "
        "[pscustomobject]@{file_version=$f.VersionInfo.FileVersion; "
        "product_version=$f.VersionInfo.ProductVersion; "
        "original_filename=$f.VersionInfo.OriginalFilename; "
        "signature_status=[string]$s.Status} | ConvertTo-Json -Compress"
    )
    meta = json.loads(subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**env, "CLIMATENOTE_VERIFY_EXE": str(exe)}, cwd=ROOT,
        capture_output=True, encoding="utf-8", check=True, timeout=60,
    ).stdout)
    if not meta.get("signature_status"):
        raise VerificationFailure("EXE 서명 상태를 확인하지 못했습니다.")
    meta.update(path=str(exe), size=exe.stat().st_size, sha256=file_hash(exe))
    info = runpy.run_path(str(ROOT / "app_info.py"))
    # build_app와 동일한 버전 변환 함수를 쓰되 앱 초기화는 실행하지 않는다.
    sys.path.insert(0, str(ROOT))
    try:
        from build_app import _windows_version_parts
        expected = ".".join(map(str, _windows_version_parts(info["APP_VERSION"])))
    finally:
        sys.path.pop(0)
    if (meta["file_version"] != expected or meta["product_version"] != expected
            or meta["original_filename"] != info["app_exe_name"]()):
        raise VerificationFailure("EXE 버전 정보가 현재 app_info와 다릅니다.")
    return meta


def execute(profile, extra=()):
    run_dir = create_run_dir()
    report = {"format_version": 1, "profile": profile, "status": "running",
              "started_at": utc_now(), "steps": [],
              "manual_checks": {item: "pending" for item in MANUAL_CHECKS},
              "release_decision": "not_evaluated"}
    code = 2
    print(f"결과 폴더: {run_dir}", flush=True)
    try:
        save_report(run_dir, report)
        env = isolated_env(run_dir)
        report["environment"] = doctor()
        report["inputs_before"] = source_snapshot()
        if report["environment"]["errors"]:
            raise ValueError("; ".join(report["environment"]["errors"]))
        code = 0
        if profile != "doctor":
            step = run_step("pytest", pytest_command(profile, extra, run_dir), run_dir, env, report=report)
            report["tests"] = junit_result(run_dir / "pytest.xml")
            code = pytest_exit(step["returncode"], report["tests"])
            save_report(run_dir, report)
        if code == 0 and profile == "release":
            command = [sys.executable, "-m", "PyInstaller", "--noconfirm",
                       "--distpath", str(run_dir / "dist"), "--workpath",
                       str(run_dir / "build"), "build.spec"]
            step = run_step("build", command, run_dir, env, report=report)
            code = 0 if step["returncode"] == 0 else 1
            save_report(run_dir, report)
            if code == 0:
                info = runpy.run_path(str(ROOT / "app_info.py"))
                exe = run_dir / "dist" / info["app_exe_name"]()
                report["artifact"] = artifact_metadata(exe, env)
                report["build_toc"] = {
                    p.relative_to(run_dir).as_posix(): file_hash(p)
                    for p in sorted((run_dir / "build").rglob("*.toc"))
                }
                if not report["build_toc"]:
                    raise VerificationFailure("이번 빌드의 TOC가 없습니다.")
                print("격리된 EXE 창이 잠시 표시됩니다. 검사 후 전용 프로세스를 정리합니다.", flush=True)
                step = run_step("smoke", [sys.executable, str(ROOT / "tools/smoke_release.py"),
                                         "--exe", str(exe), "--run-dir", str(run_dir)],
                                run_dir, env, timeout=300, report=report)
                code = 0 if step["returncode"] == 0 else 1
                smoke_path = run_dir / "smoke.json"
                if smoke_path.exists():
                    report["smoke"] = read_json(smoke_path)
                if report.get("smoke", {}).get("status") != "passed":
                    code = 1
        report["inputs_after"] = source_snapshot()
        if report["inputs_before"] != report["inputs_after"]:
            code = 1
            report["error"] = "inputs_changed: 검사 중 소스/작업 트리 상태가 바뀌었습니다."
    except KeyboardInterrupt:
        code = 130
        report["error"] = "사용자가 검사를 중단했습니다."
    except VerificationFailure as exc:
        code = 1
        report["error"] = str(exc)
    except (OSError, ValueError, subprocess.SubprocessError, ET.ParseError) as exc:
        code = 2
        report["error"] = f"{type(exc).__name__}: {exc}"
    report.update(exit_code=code, finished_at=utc_now(),
                  status="passed" if code == 0 else "interrupted" if code == 130 else "failed")
    try:
        save_report(run_dir, report)
    except OSError as exc:
        print(f"결과 기록 실패: {exc}", file=sys.stderr)
        return 2
    print(f"{report['status']}: {run_dir / 'summary.md'}", flush=True)
    if report.get("error"):
        print(report["error"], file=sys.stderr)
    return code


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("doctor", "quick", "data", "full", "release"))
    parser.add_argument("--tests", nargs="+", default=[], help="quick에 관련 테스트 추가")
    args = parser.parse_args(argv)
    if args.tests and args.profile != "quick":
        parser.error("--tests는 quick에서만 사용할 수 있습니다.")
    try:
        return execute(args.profile, args.tests)
    except (OSError, ValueError) as exc:
        print(f"검증 실행을 시작하지 못했습니다: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
