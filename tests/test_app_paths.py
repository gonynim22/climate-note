"""번들 리소스 경로 해석 회귀 테스트.

`resource_root()`는 소스 실행과 PyInstaller one-file 실행 양쪽에서
같은 리소스를 가리켜야 한다. frozen 분기는 실제 EXE에서만 실행되므로
여기서 `sys.frozen`/`sys._MEIPASS`를 흉내 내어 계약을 고정한다.
"""

from pathlib import Path

import pytest

import app_fonts
import app_paths
import fluent_icons
import ui_focus
from app_paths import resource_root


ROOT = Path(__file__).resolve().parents[1]


def test_resource_root_is_project_root_when_running_from_source():
    assert resource_root() == ROOT


def test_resource_root_follows_meipass_when_frozen(monkeypatch, tmp_path):
    """번들 실행에서는 datas가 풀린 _MEIPASS를 가리켜야 한다."""
    monkeypatch.setattr(app_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_paths.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_root() == tmp_path


def test_resource_root_ignores_meipass_without_frozen_flag(monkeypatch, tmp_path):
    """frozen이 아니면 _MEIPASS가 남아 있어도 소스 루트를 쓴다."""
    monkeypatch.delattr(app_paths.sys, "frozen", raising=False)
    monkeypatch.setattr(app_paths.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_root() == ROOT


@pytest.mark.parametrize(
    "resolved, relative",
    [
        (lambda: app_fonts.FONT_DIR, "fonts"),
        (lambda: ui_focus._IMAGE_DIR, "resources/images"),
        (lambda: ui_focus.TOMATO_IMAGE_PATH, "resources/images/tomato.png"),
        (lambda: ui_focus.TOMATO_MINI_IMAGE_PATH, "resources/images/tomato_mini.png"),
        (lambda: fluent_icons.fluent_icon_path("settings"),
         "resources/fluent_icons/settings.svg"),
    ],
)
def test_bundled_resource_paths_resolve_under_resource_root(resolved, relative):
    """모든 번들 리소스 경로가 resource_root() 아래에서 실제로 존재해야 한다."""
    path = resolved()
    assert path == ROOT.joinpath(*relative.split("/"))
    assert path.exists()


def test_tray_icon_file_exists_under_resource_root():
    """main._make_tray_icon이 참조하는 아이콘이 실제로 번들에 있어야 한다."""
    assert (resource_root() / "icon" / "icon_fixed_32.ico").exists()


def test_build_spec_bundles_every_resource_root_subdirectory():
    """resource_root() 아래에서 참조하는 디렉터리는 build.spec datas에 있어야 한다."""
    with open(ROOT / "build.spec", encoding="utf-8") as f:
        spec_source = f.read()

    for folder in ("icon", "fonts", "resources", "licenses"):
        assert f"('{folder}', '{folder}')" in spec_source


def test_modules_do_not_rebuild_resource_paths_from_dunder_file():
    """리소스 경로를 __file__ 기준으로 다시 만드는 코드가 늘어나지 않아야 한다.

    번들 모듈의 __file__ 은 .py 파일이 번들 루트에 있을 때만 _MEIPASS와
    일치한다. 모듈을 하위 폴더로 옮기면 소스와 테스트는 통과하면서 EXE에서만
    리소스를 잃으므로, 기준점은 app_paths 한 곳으로 유지한다.
    """
    bundled_dirs = ("fonts", "icon", "resources", "licenses")
    offenders = []

    for module in ("main.py", "app_fonts.py", "fluent_icons.py", "ui_focus.py"):
        with open(ROOT / module, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if "__file__" not in line:
                    continue
                if any(f'"{folder}"' in line or f"'{folder}'" in line
                       for folder in bundled_dirs):
                    offenders.append(f"{module}:{lineno}")

    assert not offenders, (
        "리소스 경로는 app_paths.resource_root()를 사용한다: " + ", ".join(offenders)
    )
