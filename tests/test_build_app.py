"""일반 빌드가 검증하지 않은 Qt 환경으로 EXE를 만들지 않도록 한다."""

from pathlib import Path
import subprocess
import sys

import pytest

import build_app
from tools import verify


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package,actual", [
    ("PySide6", "6.10.2"),
    ("PyInstaller", None),
])
def test_build_rejects_drift_or_missing_tool_without_building_or_installing(
    monkeypatch, capsys, package, actual
):
    installed_version = verify.metadata.version

    def version(name):
        if name == package:
            if actual is None:
                raise verify.metadata.PackageNotFoundError(name)
            return actual
        return installed_version(name)

    commands = []
    monkeypatch.setattr(verify.metadata, "version", version)
    monkeypatch.setattr(build_app.subprocess, "check_call", commands.append)

    assert build_app.build() == 2
    assert commands == []  # PyInstaller 실행과 자동 pip 설치 모두 금지한다.
    output = capsys.readouterr().out
    assert package in output
    assert "lock=" in output


def test_build_uses_verified_interpreter_and_discards_old_analysis(monkeypatch):
    commands = []
    monkeypatch.setattr(build_app.subprocess, "check_call", commands.append)

    assert build_app.build() == 0  # 실제 doctor가 현재 환경과 lock을 대조한다.
    assert commands == [[
        sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        str(ROOT / "build.spec"),
    ]]


@pytest.mark.parametrize("failure,expected", [
    (subprocess.CalledProcessError(7, "PyInstaller"), 1),
    (OSError("synthetic launch failure"), 2),
])
def test_build_failure_returns_nonzero(monkeypatch, failure, expected):
    def fail(_command):
        raise failure

    monkeypatch.setattr(build_app.subprocess, "check_call", fail)
    assert build_app.build() == expected


def test_batch_rejects_missing_project_venv_from_another_directory(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    batch = project / "build.bat"
    with open(ROOT / "build.bat", "rb") as source:
        content = source.read()
    with open(batch, "wb") as destination:
        destination.write(content)

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(batch)], cwd=tmp_path,
        capture_output=True, check=False,
    )

    assert result.returncode == 2
    assert b".venv\\Scripts\\python.exe is missing" in result.stdout
