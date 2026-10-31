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
