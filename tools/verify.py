"""Windows 개발 검증: doctor / quick / data / full / release.

앱을 import하지 않고 환경을 검사한다. 모든 실행 증거는 output/harness에
보존하며 테스트 실패·중단·검사 중 소스 변경을 성공으로 보고하지 않는다.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import runpy
import subprocess
import sys
import tempfile
import time
import uuid
from defusedxml import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE_DIR = "src"  # 앱 모듈 위치(B안). ROOT 기준 상대 경로로 두어 ROOT monkeypatch를 따른다.
DIRECT_DEPENDENCIES = (
    "PySide6", "PySide6-Fluent-Widgets", "cryptography", "python-dotenv",
    "pytest", "pytest-qt", "pytest-timeout", "PyInstaller", "pywin32", "defusedxml",
    "onnxruntime",
)
QUICK_TESTS = (
    "tests/test_app_paths.py", "tests/test_startup_path.py",
    "tests/test_fetch_data.py", "tests/test_verify.py",
    "tests/test_release_smoke.py",
    "tests/test_database.py::TestMigration::test_fresh_install_is_current_version",
    "tests/test_data_safety.py::test_health_gate_missing_salt_fails_without_creating_replacement",
    "tests/test_ui.py::test_schedule_right_click_menu_edits_and_deletes",
    "tests/test_ui.py::test_prepare_for_quit_blocks_when_sticky_save_fails",
)
DATA_TESTS = tuple(f"tests/test_{name}.py" for name in (
    "schedule_rules", "schedule_storage",
    "database", "security", "data_safety", "edge_cases", "stress",
    "startup_path", "ui", "ui_sticky", "ui_sticky_panel", "ui_data_lifecycle", "widget_limits",
    "openssl_free", "crypto_compat",
))
MANUAL_CHECKS = (
    "정상 종료 직전 스티키 저장 및 실제 설정/휴지통 동작",
    "Win+D 직후 Explorer/브라우저 전환",
    "음수 좌표/혼합 DPI/KVM 전환",
    "특정 PC 멈춤 재현", "Defender 검사", "라이선스/SBOM/서명 후속 과제",
    "일정 알림 실제 시각·절전 복귀·PIN 잠금·Win+D·다중 모니터 카드 위치·알림음",
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
    # API 키는 공휴일 단계에서만 쓰고 pytest·빌드·EXE에는 넘기지 않는다.
    env.pop("LUNAR_API_KEY", None)
    return env


def doctor(root=ROOT):
    result = {"python": sys.version, "executable": sys.executable,
              "platform": platform.platform(), "dependencies": {}, "errors": []}
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13):
        result["errors"].append("검증 환경은 Windows / Python 3.13입니다.")
    # 환경 표시(pywin32 줄의 '; sys_platform == "win32"')는 버전이 아니므로 버린다.
    with open(Path(root) / "requirements-lock.txt", encoding="utf-8") as stream:
        pinned = {
            name.split("[", 1)[0].lower(): version.strip()
            for line in stream if "==" in line and not line.lstrip().startswith("#")
            for name, version in [line.split(";", 1)[0].strip().split("==", 1)]
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
    for name in ("pytest.ini", "tests/conftest.py", "main.py", f"{APP_SOURCE_DIR}/security.py",
                 f"{APP_SOURCE_DIR}/database.py", f"{APP_SOURCE_DIR}/app_info.py", "build.spec",
                 f"{APP_SOURCE_DIR}/holidays.py"):
        if not (Path(root) / name).is_file():
            result["errors"].append(f"필수 파일 없음: {name}")
    return result


def git_output(*args, root=ROOT):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        encoding="utf-8", errors="replace", shell=False,
    ).stdout


# 진행 노트·계획(실행 결과 기록), 홍보 영상 작업, 출력·비공개 자료는 소스 입력이 아니다.
# 나머지는 종류와 폴더를 가리지 않고 모두 입력이다(OCR 모델·fixture·고지 JSON 누락 재발 방지).
NON_INPUT_PREFIXES = ("docs/work/", "docs/superpowers/", "motion/", "output/", "security/")


def source_snapshot(root=ROOT):
    root = Path(root).resolve()
    paths = git_output("ls-files", "--cached", "--others", "--exclude-standard",
                       "-z", root=root).split("\0")
    hashes = {}
    for name in sorted(set(paths)):
        posix = name.replace("\\", "/")
        if not posix or posix.startswith(NON_INPUT_PREFIXES):
            continue
        if "/" not in posix and posix.startswith("."):
            continue  # 루트의 .env·.gitignore 등
        path = inside(root / name, root)
        hashes[posix] = file_hash(path) if path.is_file() else None
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


def no_openssl_command(run_dir):
    """데이터 검사를 Python용 OpenSSL을 막은 프로세스에서 한 번 더 돌린다.

    배포 EXE에는 OpenSSL이 없어 hashlib·hmac을 내장 구현이 맡는다. 열쇠 재료·백업 해시가
    그 상태에서도 같은 값인지 data·release가 매번 확인한다.
    """
    return [sys.executable, str(ROOT / "tools/run_without_openssl.py"),
            *validate_targets(list(DATA_TESTS)), "-q", "--timeout=120",
            "--basetemp", str(run_dir / "pytest-tmp-no-openssl"),
            "-o", f"cache_dir={run_dir / 'pytest-cache-no-openssl'}",
            "--junitxml", str(run_dir / "pytest-no-openssl.xml")]


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


def holiday_change_lines(holidays):
    lines = [f"- 추가 {d}: {n}" for d, n in holidays.get("added", {}).items()]
    lines += [f"- 삭제 {d}: {n}" for d, n in holidays.get("removed", {}).items()]
    lines += [f"- 변경 {d}: {old} -> {new}" for d, (old, new) in holidays.get("renamed", {}).items()]
    if holidays.get("excluded_years"):
        lines.append(f"- 제외 연도: {', '.join(map(str, holidays['excluded_years']))}")
    return lines


HOLIDAY_STATUS_TEXT = {
    "up_to_date": "공휴일 최신 확인", "updated": "공휴일 갱신됨",
    "blocked": "기존 날짜 삭제·변경으로 중단", "failed": "공휴일 받기 실패",
}


def holiday_lines(holidays):
    status = holidays["status"]
    lines = [f"- 상태: {HOLIDAY_STATUS_TEXT.get(status, status)} (`{status}`)"]
    if holidays.get("error"):
        lines.append(f"- 실패: {holidays['error']}")
    if holidays.get("checked_at"):
        lines.append(f"- 조회 시각: {holidays['checked_at']}")
    if holidays.get("years"):
        lines.append(f"- 받은 범위: {holidays['years'][0]}~{holidays['years'][1]}년")
    lines += holiday_change_lines(holidays)
    if holidays.get("backup"):
        lines.append(f"- 백업: `{holidays['backup']}`")
    return lines


def save_report(run_dir, report):
    lines = ["# 기후노트 검증 결과", "",
             f"- 실행: `{run_dir.name}`", f"- 프로필: `{report['profile']}`",
             f"- 상태: `{report['status']}`", f"- 종료 코드: `{report.get('exit_code', 'pending')}`"]
    if "tests" in report:
        lines.append(f"- 테스트: `{json.dumps(report['tests'])}`")
    if "tests_no_openssl" in report:
        lines.append(f"- OpenSSL 없는 데이터 검사: `{json.dumps(report['tests_no_openssl'])}`")
    if report.get("error"):
        lines.append(f"- 오류: {report['error']}")
    if "holidays" in report:
        lines += ["", "## 공휴일 데이터", ""]
        lines += holiday_lines(report["holidays"])
    if "bundle" in report:
        bundle = report["bundle"]
        lines += ["", "## EXE 구성", "",
                  f"- BINARY {bundle['binary_entries']}개, 검증 환경 밖 {len(bundle['outside_environment'])}개",
                  f"- Qt DLL {len(bundle['qt_dlls'])}개: 검증 환경 원본과 바이트 동일"]
        if "app_modules" in bundle:
            lines.append(f"- src/ 앱 모듈 {bundle['app_modules']['expected']}개: 모두 EXE PYZ에 포함")
        if "openssl" in bundle:
            openssl = bundle["openssl"]
            shown = ", ".join(f"{Path(item['name']).name}({', '.join(item['found'])})"
                              for item in openssl["banners"]) or "없음"
            lines.append(f"- OpenSSL: Python용·Qt 연결 파일 없음, 버전 표시 {shown}뿐 "
                         f"(dll·pyd {openssl['scanned']}개 확인, 묶기 전에 거른 파일 {len(openssl['filtered'])}개, "
                         f"UPX 압축 {len(openssl['upx_packed'])}개)")
    if report.get("root_dist"):
        lines += ["", "## 기존 dist 보존", ""]
        for observation in report["root_dist"]:
            lines.append(f"- {observation['stage']}: 파일 {len(observation['files'])}개, "
                         f"소실/변경 {len(observation['changed'])}개")
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
    info = runpy.run_path(str(ROOT / APP_SOURCE_DIR / "app_info.py"))
    # build_app와 동일한 버전 변환 함수를 쓰되 앱 초기화는 실행하지 않는다.
    sys.path[:0] = [str(ROOT), str(ROOT / APP_SOURCE_DIR)]
    try:
        from build_app import _windows_version_parts
        expected = ".".join(map(str, _windows_version_parts(info["APP_VERSION"])))
    finally:
        del sys.path[:2]
    if (meta["file_version"] != expected or meta["product_version"] != expected
            or meta["original_filename"] != info["app_exe_name"]()):
        raise VerificationFailure("EXE 버전 정보가 현재 app_info와 다릅니다.")
    return meta


# System32에서 받는 BINARY는 Python이 쓰는 VC 런타임뿐이다.
VC_RUNTIME_PREFIXES = ("vcruntime140", "msvcp140")


def _binary_entries(value):
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and value[-1] == "BINARY" and isinstance(value[0], str):
            yield value
        else:
            for item in value:
                yield from _binary_entries(item)


def _embedded_reader(exe):
    # PyInstaller는 release 단계에서만 가져온다.
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    names = {name.replace("\\", "/"): name for name in archive.toc}
    return lambda name: archive.extract(names[name.replace("\\", "/")])


def bundle_check(toc_path, exe):
    """빌드 TOC의 BINARY 출처와 EXE 안 Qt DLL이 이 검증 환경의 원본인지 확인한다.

    Git Bash PATH의 mingw OpenSSL DLL이 섞인 적이 있다(2026-09-28). 직전 EXE와의
    바이트 동일은 Qt 업그레이드를 막으므로 통과 조건으로 쓰지 않는다.
    """
    with open(toc_path, encoding="utf-8") as stream:
        entries = list(_binary_entries(ast.literal_eval(stream.read())))
    if not entries:
        raise VerificationFailure("이번 빌드 TOC에 BINARY 항목이 없습니다.")
    venv, base = Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()
    system = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32").resolve()
    outside = []
    for name, source, _ in entries:
        path = Path(source).resolve()
        if not (path.is_relative_to(venv) or path.is_relative_to(base) or (
                path.parent == system and path.name.lower().startswith(VC_RUNTIME_PREFIXES))):
            outside.append([name, source])
    if outside:
        raise VerificationFailure(f"검증 환경 밖 BINARY 포함: {outside}")
    read = _embedded_reader(exe)
    qt = []
    for name, source, _ in entries:
        posix = name.replace("\\", "/")
        if not (Path(posix).name.startswith("Qt6") and posix.lower().endswith(".dll")):
            continue
        embedded = read(name)
        with open(source, "rb") as stream:
            if embedded != stream.read():
                raise VerificationFailure(f"EXE의 {posix}가 검증 환경 원본과 다릅니다.")
        qt.append({"name": posix, "sha256": hashlib.sha256(embedded).hexdigest()})
    if not qt:
        raise VerificationFailure("EXE에서 Qt DLL을 찾지 못했습니다.")
    return {"binary_entries": len(entries), "outside_environment": outside, "qt_dlls": qt}


# 배포 EXE에 있으면 안 되는 OpenSSL 파일(파일 이름 기준). build_app.OPENSSL_FILE_NAMES보다 넓게 본다:
# Git Bash의 libcrypto-3-x64.dll처럼 다른 경로로 섞여 든 것도 잡는다.
OPENSSL_FILE = re.compile(
    r"(?i)^(?:(?:libcrypto|libssl)[-\w.]*\.dll|_ssl\.[-\w.]*pyd|_hashlib\.[-\w.]*pyd|qopensslbackend\.dll)$")
# OpenSSL 버전 표시를 가져도 되는 파일: 본문 암호화를 맡는 cryptography의 정적 사본뿐이다.
OPENSSL_BANNER_ALLOWED = ("cryptography/hazmat/bindings/_rust.pyd",)
_BANNER_ASCII = re.compile(rb"OpenSSL \d+\.\d+\.\d+[a-z]*")
# Qt 플러그인은 같은 표시를 UTF-16으로 갖는다(ASCII로만 찾으면 놓친다).
_BANNER_WIDE = re.compile(
    rb"O\x00p\x00e\x00n\x00S\x00S\x00L\x00 \x00(?:\d\x00)+\.\x00(?:\d\x00)+\.\x00(?:\d\x00)+(?:[a-z]\x00)*")


def find_openssl_banners(data):
    """바이너리 안의 'OpenSSL 3.0.16' 같은 버전 표시를 ASCII와 UTF-16LE로 찾아 정렬해 돌려준다."""
    found = {match.group().decode("ascii") for match in _BANNER_ASCII.finditer(data)}
    found.update(match.group().decode("utf-16-le") for match in _BANNER_WIDE.finditer(data))
    return sorted(found)


def _toc_names(value):
    """TOC의 (이름, 원본, 종류) 항목 이름. BINARY뿐 아니라 EXTENSION 등 모든 종류를 본다."""
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and all(isinstance(item, str) for item in value):
            yield value[0]
        else:
            for item in value:
                yield from _toc_names(item)


def _embedded_archive(exe):
    # PyInstaller는 release 단계에서만 가져온다.
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    return list(archive.toc), archive.extract


def openssl_check(toc_path, exe):
    """이번 EXE에 Python용 OpenSSL·Qt OpenSSL 연결 플러그인이 없고 버전 표시가 허용 파일에만 있는지 확인한다.

    2026-11-10 바이너리 검사가 EXE의 OpenSSL을 지적했다. build.spec이 빼도 다른 경로로 다시
    섞이면 빌드는 성공하므로, EXE 안 파일을 직접 본다. Analysis TOC는 build.spec이 a.binaries를 거르기
    전 목록이라 판정에 쓰지 않고, 거기에만 있던 파일을 '묶기 전에 걸러짐(filtered)'으로 기록한다.
    """
    def openssl_files(names):
        return sorted({name.replace("\\", "/") for name in names
                       if OPENSSL_FILE.match(name.replace("\\", "/").rsplit("/", 1)[-1])})

    with open(toc_path, encoding="utf-8") as stream:
        analysed = openssl_files(_toc_names(ast.literal_eval(stream.read())))
    names, read = _embedded_archive(exe)
    files = openssl_files(names)
    if files:
        raise VerificationFailure(f"EXE에 OpenSSL 파일 포함: {files}")
    banners, packed, scanned = [], [], 0
    for name in names:
        posix = name.replace("\\", "/")
        if not posix.lower().endswith((".dll", ".pyd")):
            continue
        data = read(name)
        scanned += 1
        if b"UPX!" in data[:4096]:
            packed.append(posix)  # 압축된 파일은 안의 글자를 볼 수 없다
        found = find_openssl_banners(data)
        if found:
            banners.append({"name": posix, "found": found})
    if packed:
        raise VerificationFailure(f"UPX로 압축돼 OpenSSL 버전 표시를 확인할 수 없는 파일: {packed}")
    unexpected = [item for item in banners if not item["name"].endswith(OPENSSL_BANNER_ALLOWED)]
    if unexpected:
        raise VerificationFailure(f"허용하지 않은 OpenSSL 버전 표시: {unexpected}")
    return {"files": files, "filtered": analysed, "scanned": scanned, "banners": banners, "upx_packed": packed}


def _pyz_module_names(exe):
    # PyInstaller는 release 단계에서만 가져온다.
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(exe))
    pyz = [name for name, entry in archive.toc.items() if entry[-1] == "z"]
    if len(pyz) != 1:
        raise VerificationFailure("EXE에서 PYZ 묶음을 하나로 찾지 못했습니다.")
    return set(archive.open_embedded_archive(pyz[0]).toc)


def app_module_check(exe, root=ROOT):
    """추적 중인 src/ 앱 모듈이 모두 EXE의 PYZ에 들어갔는지 확인한다.

    build.spec이 src/를 검색 경로에 넣지 못해도 빌드는 성공으로 끝나고, 경고 파일에는
    빠진 모듈 일부만 남는다(2026-10-31 실측). 빠진 모듈은 EXE를 켤 때에야 오류 창으로
    드러나므로 이번 EXE의 PYZ 목록을 직접 대조한다.
    """
    expected = sorted(Path(name).stem for name in
                      git_output("ls-files", "--", f"{APP_SOURCE_DIR}/*.py", root=root).splitlines())
    if not expected:
        raise VerificationFailure("추적 중인 src/ 앱 모듈을 찾지 못했습니다.")
    missing = sorted(set(expected) - _pyz_module_names(exe))
    if missing:
        raise VerificationFailure(f"EXE에 없는 앱 모듈: {missing}")
    return {"expected": len(expected), "missing": missing}


def _fetch_data_module():
    # 모듈 import 때는 가져오지 않고 release 단계에서만 가져온다.
    sys.path.insert(0, str(ROOT))
    try:
        import fetch_data
    finally:
        sys.path.pop(0)
    return fetch_data


def refresh_holidays_step(run_dir, report):
    fd = _fetch_data_module()
    print("공휴일 데이터를 API에서 확인하는 중... (1~3분)", flush=True)
    try:
        result = fd.refresh_holidays(ROOT / APP_SOURCE_DIR / "holidays.py", backup_dir=run_dir / "holidays-backup")
    except fd.FetchError as exc:
        report["holidays"] = {"status": "failed", "error": str(exc)}
        print(f"공휴일: 받기 실패 ({exc})", flush=True)
        if exc.environment:
            raise ValueError(f"공휴일 데이터 받기 실패: {exc}") from exc
        raise VerificationFailure(f"공휴일 데이터 받기 실패: {exc}") from exc
    diff = result.diff
    report["holidays"] = {
        "status": result.status, "checked_at": result.checked_at,
        "years": list(result.years), "added": dict(diff.added),
        "removed": dict(diff.removed),
        "renamed": {d: list(pair) for d, pair in diff.renamed.items()},
        "excluded_years": list(result.excluded_years),
        "backup": result.backup.relative_to(run_dir).as_posix() if result.backup else None,
    }
    if result.status == "blocked":
        print("공휴일: 기존 날짜 삭제·변경 발견", flush=True)
        print(chr(10).join(holiday_change_lines(report["holidays"])), flush=True)
        raise VerificationFailure(
            "공휴일 기존 날짜가 삭제·변경되었습니다. 목록을 확인한 뒤 "
            "`python fetch_data.py`를 실행하고 다시 release 하세요.")
    if result.status == "updated":
        print(f"공휴일: {len(diff.added)}건 추가", flush=True)
    else:
        print("공휴일: 최신 확인", flush=True)
    changes = holiday_change_lines(report["holidays"])
    if changes:
        print(chr(10).join(changes), flush=True)


def root_dist_snapshot():
    """기존 루트 dist 파일을 읽기만 한다. release 출력은 실행별 폴더에 둔다."""
    folder = inside(ROOT / "dist", ROOT)
    if not folder.exists():
        return {}
    return {path.name: {"bytes": path.stat().st_size, "sha256": file_hash(inside(path, folder))}
            for path in sorted(folder.iterdir()) if path.is_file()}


def record_root_dist(report, stage):
    files = root_dist_snapshot()
    observations = report.setdefault("root_dist", [])
    baseline = observations[0]["files"] if observations else files
    changed = [name for name, value in baseline.items() if files.get(name) != value]
    observations.append({"stage": stage, "at": utc_now(), "files": files, "changed": changed})
    if changed:
        raise VerificationFailure(f"{stage}: 기존 dist 파일 소실/변경 발견: {', '.join(changed)}")


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
        if report["environment"]["errors"]:
            raise ValueError("; ".join(report["environment"]["errors"]))
        if profile == "release":
            record_root_dist(report, "before_holidays")
            # 스냅샷 전에 끝나야 inputs_after 비교와 충돌하지 않는다. 뒤 단계가 실패해도 되돌리지 않는다.
            refresh_holidays_step(run_dir, report)
            record_root_dist(report, "after_holidays")
            save_report(run_dir, report)
        report["inputs_before"] = source_snapshot()
        code = 0
        if profile != "doctor":
            step = run_step("pytest", pytest_command(profile, extra, run_dir), run_dir, env, report=report)
            report["tests"] = junit_result(run_dir / "pytest.xml")
            code = pytest_exit(step["returncode"], report["tests"])
            if code == 0 and profile in {"data", "release"}:
                step = run_step("pytest-no-openssl", no_openssl_command(run_dir), run_dir, env, report=report)
                report["tests_no_openssl"] = junit_result(run_dir / "pytest-no-openssl.xml")
                code = pytest_exit(step["returncode"], report["tests_no_openssl"])
            if profile == "release":
                record_root_dist(report, "after_pytest")
            save_report(run_dir, report)
        if code == 0 and profile == "release":
            command = [sys.executable, "-m", "PyInstaller", "--noconfirm",
                       "--distpath", str(run_dir / "dist"), "--workpath",
                       str(run_dir / "build"), "build.spec"]
            step = run_step("build", command, run_dir, env, report=report)
            record_root_dist(report, "after_build")
            code = 0 if step["returncode"] == 0 else 1
            save_report(run_dir, report)
            if code == 0:
                info = runpy.run_path(str(ROOT / APP_SOURCE_DIR / "app_info.py"))
                exe = run_dir / "dist" / info["app_exe_name"]()
                report["artifact"] = artifact_metadata(exe, env)
                report["build_toc"] = {
                    p.relative_to(run_dir).as_posix(): file_hash(p)
                    for p in sorted((run_dir / "build").rglob("*.toc"))
                }
                if not report["build_toc"]:
                    raise VerificationFailure("이번 빌드의 TOC가 없습니다.")
                analysis = sorted((run_dir / "build").rglob("Analysis-00.toc"))
                if len(analysis) != 1:
                    raise VerificationFailure("이번 빌드의 Analysis TOC를 하나로 찾지 못했습니다.")
                report["bundle"] = bundle_check(analysis[0], exe)
                report["bundle"]["app_modules"] = app_module_check(exe)
                report["bundle"]["openssl"] = openssl_check(analysis[0], exe)
                save_report(run_dir, report)
                print("격리된 EXE 창이 잠시 표시됩니다. 검사 후 전용 프로세스를 정리합니다.", flush=True)
                step = run_step("smoke", [sys.executable, str(ROOT / "tools/smoke_release.py"),
                                         "--exe", str(exe), "--run-dir", str(run_dir)],
                                run_dir, env, timeout=300, report=report)
                code = 0 if step["returncode"] == 0 else 1
                record_root_dist(report, "after_smoke")
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
