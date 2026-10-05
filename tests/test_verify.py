"""개발 하네스의 실패 전파·격리·증거 기록 계약. 전체 검사 재귀 호출 없음."""

import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from tools import verify


def test_junit_entity_rejection_preserves_report(tmp_path):
    from defusedxml import DefusedXmlException
    path = tmp_path / "pytest.xml"
    source = ('<!DOCTYPE testsuite [<!ENTITY a "synthetic">]>'
              '<testsuite><testcase name="&a;"/></testsuite>')
    path.write_text(source, encoding="utf-8")
    with pytest.raises(DefusedXmlException):
        verify.junit_result(path)
    assert path.read_text(encoding="utf-8") == source


@pytest.fixture
def runner(tmp_path, monkeypatch):
    directory = tmp_path / "run"
    directory.mkdir()
    monkeypatch.setattr(verify, "create_run_dir", lambda: directory)
    monkeypatch.setattr(verify, "isolated_env", lambda _: os.environ.copy())
    monkeypatch.setattr(verify, "doctor", lambda: {"errors": []})
    monkeypatch.setattr(verify, "source_snapshot", lambda: {"head": "test", "files": {"a.py": "abc"}})
    return directory


def mini_pytest(tmp_path, code):
    test = tmp_path / "test_mini.py"
    config = tmp_path / "pytest.ini"
    verify.atomic_text(test, code)
    verify.atomic_text(config, "[pytest]\n")
    return lambda _profile, _extra, run: [
        sys.executable, "-m", "pytest", "-c", str(config), str(test), "-q",
        "--junitxml", str(run / "pytest.xml"), "--basetemp", str(run / "tmp"),
        "-o", f"cache_dir={run / 'cache'}",
    ]


@pytest.mark.parametrize("source,expected", [
    ("def test_ok():\n    assert True\n", 0),
    ("def test_bad():\n    assert False\n", 1),
    ("raise ValueError('collection failed')\n", 2),
    ("# no tests\n", 2),
    ("import pytest\n@pytest.mark.skip(reason='not run')\ndef test_skip():\n    pass\n", 2),
])
def test_real_subprocess_results_are_not_false_green(runner, tmp_path, monkeypatch, source, expected):
    monkeypatch.setattr(verify, "pytest_command", mini_pytest(tmp_path, source))
    assert verify.execute("full") == expected
    report = verify.read_json(runner / "result.json")
    assert report["exit_code"] == expected
    assert report["status"] == ("passed" if expected == 0 else "failed")
    assert report["steps"][0]["command"][0] == sys.executable
    assert (runner / "pytest.log").is_file()
    assert report["release_decision"] == "not_evaluated"
    assert set(report["manual_checks"].values()) == {"pending"}


def test_release_does_not_build_after_failed_tests(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "pytest_command", mini_pytest(tmp_path, "def test_bad():\n    assert False\n"))
    assert verify.execute("release") == 1
    assert [s["name"] for s in verify.read_json(runner / "result.json")["steps"]] == ["pytest"]


def test_doctor_mismatch_stops_before_subprocess(runner, monkeypatch):
    monkeypatch.setattr(verify, "doctor", lambda: {"errors": ["dependency drift"]})
    assert verify.execute("full") == 2
    report = verify.read_json(runner / "result.json")
    assert report["steps"] == []
    assert "dependency drift" in report["error"]


@pytest.mark.parametrize("installed", [None, "0.0.0"])
def test_doctor_detects_dependency_problem_without_importing_it(monkeypatch, installed):
    original = verify.metadata.version

    def version(name):
        if name == "cryptography":
            if installed is None:
                raise verify.metadata.PackageNotFoundError(name)
            return installed
        return original(name)

    monkeypatch.setattr(verify.metadata, "version", version)
    report = verify.doctor()
    assert report["dependencies"]["cryptography"]["actual"] == installed
    assert any("cryptography" in error for error in report["errors"])


def test_tool_import_has_no_app_side_effects():
    command = [sys.executable, "-c", (
        "import sys; from tools import verify, smoke_release; "
        "assert not {'security', 'database', 'main'} & set(sys.modules)"
    )]
    subprocess.run(command, cwd=verify.ROOT, check=True, timeout=20, capture_output=True)


def test_input_change_fails_doctor(runner, monkeypatch):
    snapshots = iter(({"files": {"a.py": "old"}}, {"files": {"a.py": "new"}}))
    monkeypatch.setattr(verify, "source_snapshot", lambda: next(snapshots))
    assert verify.execute("doctor") == 1
    assert "inputs_changed" in verify.read_json(runner / "result.json")["error"]


def test_interruption_is_recorded(runner, monkeypatch):
    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(verify, "run_step", interrupted)
    assert verify.execute("full") == 130
    assert verify.read_json(runner / "result.json")["status"] == "interrupted"


def test_step_timeout_retains_command_and_failure(tmp_path):
    report = {"profile": "full", "status": "running", "steps": []}
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(subprocess.TimeoutExpired):
        verify.run_step("timeout", command, tmp_path, os.environ.copy(), timeout=0.1, report=report)
    assert report["steps"][0]["status"] == "failed"
    assert report["steps"][0]["command"] == command
    assert report["steps"][0]["returncode"] is not None


def test_report_write_failure_is_not_success(runner, monkeypatch):
    def denied(*_args):
        raise PermissionError("report is read-only")

    monkeypatch.setattr(verify, "save_report", denied)
    assert verify.execute("doctor") == 2


def test_final_json_failure_does_not_leave_passed_summary(runner, monkeypatch):
    original = verify.write_json

    def denied_final(path, report):
        if report["status"] == "passed":
            raise PermissionError("final result denied")
        original(path, report)

    monkeypatch.setattr(verify, "write_json", denied_final)
    assert verify.execute("doctor") == 2
    assert verify.read_json(runner / "result.json")["status"] == "running"
    with open(runner / "summary.md", encoding="utf-8") as stream:
        summary = stream.read()
    assert "`failed`" in summary
    assert "`passed`" not in summary


def test_release_artifact_failure_has_exit_one(runner, monkeypatch):
    def step(name, _command, directory, _env, **kwargs):
        record = {"name": name, "status": "passed", "returncode": 0, "log": f"{name}.log"}
        kwargs["report"]["steps"].append(record)
        if name == "pytest":
            verify.atomic_text(directory / "pytest.xml", "<testsuite><testcase name='ok'/></testsuite>")
        return record

    # 빌드 명령이 0이어도 이번 EXE가 없으면 산출물 실패다.
    monkeypatch.setattr(verify, "run_step", step)
    assert verify.execute("release") == 1
    assert "EXE" in verify.read_json(runner / "result.json")["error"]


def test_metadata_powershell_uses_its_own_security_module():
    # 이미 설치된 Python EXE로 실제 메타데이터 명령만 검사한다.
    # 기후노트가 아니므로 마지막 버전 비교에서 실패해야 한다.
    with pytest.raises(verify.VerificationFailure, match="버전"):
        verify.artifact_metadata(Path(sys.executable), os.environ.copy())


def test_atomic_report_failure_preserves_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    verify.write_json(target, {"status": "running"})

    def denied(*_args):
        raise PermissionError("replace denied")

    monkeypatch.setattr(verify.os, "replace", denied)
    with pytest.raises(PermissionError):
        verify.write_json(target, {"status": "passed"})
    assert verify.read_json(target) == {"status": "running"}
    assert list(tmp_path.iterdir()) == [target]


def test_runs_are_unique_and_previous_success_is_untouched(tmp_path):
    first, second = verify.create_run_dir(tmp_path), verify.create_run_dir(tmp_path)
    verify.write_json(first / "result.json", {"status": "passed"})
    verify.write_json(second / "result.json", {"status": "failed"})
    assert first != second
    assert verify.read_json(first / "result.json")["status"] == "passed"


@pytest.mark.parametrize("target", ["--collect-only", "../main.py", "main.py", "tests/missing.py", "C:/Windows/test.py"])
def test_extra_test_paths_cannot_escape(target):
    with pytest.raises(ValueError):
        verify.validate_targets([target])


def test_profiles_select_expected_scope(tmp_path):
    quick = verify.pytest_command("quick", ["tests/test_ui_sticky.py"], tmp_path)
    assert "tests/test_ui_sticky.py" in quick
    assert all(target in quick for target in verify.QUICK_TESTS)
    data = verify.pytest_command("data", [], tmp_path)
    assert all(target in data for target in verify.DATA_TESTS)
    assert "tests/test_ui.py" in data  # 저장/소유권 전환 회귀가 이 파일에도 있다.
    for profile in ("full", "release"):
        command = verify.pytest_command(profile, [], tmp_path)
        assert command.count("tests") == 1
        assert "tests/test_ui.py" not in command


def test_source_snapshot_includes_untracked_code_but_not_private_data(tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    verify.atomic_text(tmp_path / "tools/new.py", "# newly added code\n")
    verify.atomic_text(tmp_path / "main.py", "# app\n")

    def git(*args, **_kwargs):
        if args[0] == "ls-files":
            return "main.py\0tools/new.py\0.env\0security/private.md\0output/result.json\0docs/work/note.md\0"
        return "dirty" if args[0] == "status" else "abc"

    monkeypatch.setattr(verify, "git_output", git)
    report = verify.source_snapshot(tmp_path)
    assert set(report["files"]) == {"main.py", "tools/new.py"}
    assert report["dirty"]


def test_test_bootstrap_honors_run_path_before_app_import():
    directory = verify.create_run_dir()
    env = verify.isolated_env(directory)
    script = (
        "import runpy; runpy.run_path('tests/conftest.py'); import security, database; "
        "print('APPDIR=' + str(security.APP_DIR)); "
        "assert database.APP_DIR == security.APP_DIR"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=verify.ROOT, env=env,
                            check=True, timeout=20, capture_output=True, encoding="utf-8")
    assert f"APPDIR={directory / 'appdata' / 'MyDesktopCalendar'}" in result.stdout


def test_test_bootstrap_rejects_outside_before_creating_it(tmp_path):
    # 하네스로 실행하면 tmp_path 자체도 허용된 output/harness 안이다.
    outside = verify.ROOT / "output" / f"rejected-{uuid.uuid4().hex}"
    env = {**os.environ, "CLIMATENOTE_TEST_APPDATA": str(outside)}
    result = subprocess.run(
        [sys.executable, "-c", "import runpy; runpy.run_path('tests/conftest.py')"],
        cwd=verify.ROOT, env=env, timeout=20, capture_output=True,
    )
    assert result.returncode != 0
    assert not outside.exists()


def test_invalid_option_combination_exits_two():
    with pytest.raises(SystemExit) as exc:
        verify.main(["full", "--tests", "tests/test_ui.py"])
    assert exc.value.code == 2


def test_fixture_cleanup_disposes_only_new_app_windows(qapp, qtbot):
    from conftest import _dispose_test_windows
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QWidget
    from shiboken6 import isValid

    class AppWindow(QWidget):
        __module__ = "ui_fixture_probe"

    existing = AppWindow()
    qtbot.addWidget(existing)
    previous = set(qapp.topLevelWidgets())
    created = AppWindow()
    timer = QTimer(created)
    timer.start(500)
    helper = QWidget()
    qtbot.addWidget(helper)

    _dispose_test_windows(previous)

    assert isValid(existing)
    assert isValid(helper)
    assert not isValid(created)
    assert not isValid(timer)
