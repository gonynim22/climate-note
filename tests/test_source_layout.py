"""앱 모듈 src/ 배치(v4.5a) 회귀 테스트.

앱 모듈은 패키지가 아닌 `src/` 폴더에 두고 `main.py`·`tests/conftest.py`·`build.spec`·
`build_app.py`가 그 폴더를 import 경로에 넣는다. 아래 위반은 소스 실행과 pytest를
통과하면서 EXE나 개발 도구에서만 드러나므로 여기서 고정한다.
근거: docs/work/2026-10-31-root-file-cleanup-risk.md (4장 G1·G2·G4·G5)
"""
import re
import subprocess
import sys
from pathlib import Path

import fetch_data
import holidays
import ui_settings

ROOT = Path(__file__).resolve().parents[1]
_SRC_IMPORT = re.compile(r"^\s*(from\s+src(\.|\s+import\b)|import\s+src\b)", re.M)


def _tracked(*patterns):
    names = subprocess.run(["git", "ls-files", "-z", "--", *patterns], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode("utf-8").split("\0")
    return [name for name in names if name]


def test_no_tracked_source_imports_app_modules_through_src_prefix():
    """`import src.database`는 `database`와 다른 모듈 객체가 되고, build.spec·build_app이
    `from src.app_info import`로 바뀌면 src가 검색 경로에 없어 앱 모듈이 빠진 EXE가 된다."""
    offenders = [name for name in _tracked("*.py", "build.spec")
                 if _SRC_IMPORT.search((ROOT / name).read_text(encoding="utf-8"))]
    assert offenders == []


def test_root_keeps_only_entry_scripts():
    """PyInstaller는 진입 스크립트 폴더(루트)를 src보다 먼저 찾는다. 루트에 같은 이름의
    사본이 생기면 소스·pytest는 src를, EXE만 루트 사본을 쓰므로 미추적 파일도 막는다."""
    assert sorted(path.name for path in ROOT.glob("*.py")) == ["build_app.py", "fetch_data.py", "main.py"]
    assert not (ROOT / "src" / "__init__.py").exists(), "src/는 패키지가 아니다"


def test_dunder_file_paths_stay_in_known_source_only_modules():
    """src/x.py의 __file__ 깊이는 EXE(_MEIPASS/x.py)와 다르다. __file__ 경로는 소스 실행
    전용 분기가 있는 두 곳만 허용하고, 리소스는 app_paths.resource_root()로 찾는다."""
    users = sorted(name for name in _tracked("src/*.py")
                   if "__file__" in (ROOT / name).read_text(encoding="utf-8"))
    assert users == ["src/app_paths.py", "src/ui_settings.py"]


def test_holiday_refresh_writes_the_module_the_app_imports():
    assert fetch_data.HOLIDAYS_PATH.resolve() == Path(holidays.__file__).resolve()
    assert fetch_data.HOLIDAYS_PATH.resolve() == ROOT / "src" / "holidays.py"


def test_source_startup_command_runs_root_main():
    python, script = ui_settings._get_startup_cmd().strip('"').split('" "')
    assert python == sys.executable
    assert Path(script).resolve() == ROOT / "main.py"


# ── 공휴일 테마 개발 미리보기 도구(v4.6)는 배포물에 들어가지 않고 합성 폴더에서만 돈다 ──

_PREVIEW_TOOL = "dev_holiday_theme_preview"


def test_holiday_theme_preview_tool_stays_out_of_the_build():
    """날짜를 바꾸는 개발 도구가 EXE에 섞이면 사용자 화면의 테마가 날짜 우회로 바뀐다."""
    assert (ROOT / "tools" / f"{_PREVIEW_TOOL}.py").is_file()
    for name in ("build.spec", "build_app.py"):
        assert _PREVIEW_TOOL not in (ROOT / name).read_text(encoding="utf-8"), name
    spec = (ROOT / "build.spec").read_text(encoding="utf-8")
    assert "('tools'" not in spec and '("tools"' not in spec
    assert "tools" not in spec.split("pathex=", 1)[1].split("\n", 1)[0], "tools/는 분석 경로가 아니다"
    # 앱 모듈은 도구를 import하지 않는다(앱에 날짜 고정 경로를 두지 않는다).
    assert [name for name in _tracked("src/*.py", "main.py")
            if _PREVIEW_TOOL in (ROOT / name).read_text(encoding="utf-8")] == []


def test_holiday_theme_preview_tool_uses_synthetic_appdata(tmp_path):
    """바깥 LOCALAPPDATA가 실제 AppData여도 도구는 output/harness 합성 폴더만 보고 날짜를 고정한다."""
    import json
    import os
    import shutil

    sentinel = tmp_path / "real-appdata"
    sentinel.mkdir()
    env = {**os.environ, "LOCALAPPDATA": str(sentinel), "PYTHONIOENCODING": "utf-8"}
    env.pop("CLIMATENOTE_TEST_APPDATA", None)
    done = subprocess.run([sys.executable, str(ROOT / "tools" / f"{_PREVIEW_TOOL}.py"),
                           "--date", "2026-12-25", "--check-only"],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout.strip().splitlines()[-1])
    run_dir = Path(report["run_dir"]).resolve()
    try:
        assert run_dir.parent == (ROOT / "output" / "harness").resolve()
        assert Path(report["app_dir"]).resolve() == run_dir / "appdata" / "MyDesktopCalendar"
        assert (report["theme"], report["in_holiday"]) == ("christmas", True)
        assert list(sentinel.iterdir()) == [], "바깥 LOCALAPPDATA에는 아무것도 만들지 않는다"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
