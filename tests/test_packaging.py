"""배포 패키지 메타데이터·의존성·고지 파일 회귀 테스트."""

import ast
import sys
from importlib.metadata import distribution
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyInstaller.utils.win32.versioninfo import VSVersionInfo

from app_info import (
    APP_AUTHOR,
    APP_DISPLAY_NAME,
    APP_VERSION,
    app_exe_name,
)
from build_app import _windows_version_parts, without_openssl


ROOT = Path(__file__).resolve().parents[1]


def _execute_spec():
    captured = {}

    def analysis(*_args, **_kwargs):
        return SimpleNamespace(
            pure=[],
            zipped_data=[],
            scripts=[],
            binaries=[],
            zipfiles=[],
            datas=[],
        )

    def pyz(*_args, **_kwargs):
        return object()

    def exe(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    namespace = {
        "SPECPATH": str(ROOT),
        "Analysis": analysis,
        "PYZ": pyz,
        "EXE": exe,
    }
    spec_path = ROOT / "build.spec"
    with open(spec_path, encoding="utf-8") as f:
        spec_source = f.read()
    exec(
        compile(spec_source, str(spec_path), "exec"),
        namespace,
    )
    return captured


def _version_strings(version_info):
    values = {}
    for child in version_info.kids:
        if getattr(child, "name", "") != "StringFileInfo":
            continue
        for table in child.kids:
            values.update({item.name: item.val for item in table.kids})
    return values


def test_build_spec_embeds_app_info_version_metadata():
    captured = _execute_spec()
    kwargs = captured["kwargs"]
    version_info = kwargs["version"]

    assert isinstance(version_info, VSVersionInfo)
    # 버전 변환 규칙은 build_app이 단일 출처다. 테스트가 규칙을 다시 구현하면
    # v3.6a 같은 접미사 표기에서 둘이 어긋난다.
    parts = _windows_version_parts(APP_VERSION)
    version_text = ".".join(str(part) for part in parts)
    strings = _version_strings(version_info)

    assert strings["FileVersion"] == version_text
    assert strings["ProductVersion"] == version_text
    assert strings["ProductName"] == APP_DISPLAY_NAME
    assert strings["CompanyName"] == APP_AUTHOR
    assert strings["OriginalFilename"] == app_exe_name()
    assert kwargs["name"] == app_exe_name().removesuffix(".exe")
    assert kwargs["codesign_identity"] is None


def test_requirements_lock_matches_verified_direct_dependencies():
    with open(ROOT / "requirements.txt", encoding="utf-8") as f:
        requirements = {
            line.strip().lower()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        }
    assert "pyinstaller" in requirements

    with open(ROOT / "requirements-lock.txt", encoding="utf-8") as f:
        lock_lines = [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]
    assert lock_lines
    assert all("==" in line for line in lock_lines)

    direct_names = {
        "PySide6",
        "PySide6-Fluent-Widgets",
        "cryptography",
        "python-dotenv",
        "pytest",
        "pytest-qt",
        "pytest-timeout",
        "PyInstaller",
        "pywin32",
        "defusedxml",
        "onnxruntime",
    }
    pinned = {}
    for line in lock_lines:
        name, version = line.split(";", 1)[0].strip().split("==", 1)
        pinned[name.split("[", 1)[0].lower()] = version

    for name in direct_names:
        assert pinned[name.lower()] == distribution(name).version


def test_pywin32_lines_carry_windows_only_marker():
    # GitLab push 보안 검사의 OSV-Scanner는 Linux에서 deps.dev로 하위 의존성을 푼다.
    # 2026-11-09 deps.dev가 pywin32의 의존성 자료를 모든 버전에서 주지 않아(404) 검사가
    # 종료 코드 127로 끝나고 push가 거절됐다. 이 표시가 있으면 pywin32==311은 그대로
    # 취약점 대조에 들어가고 해석만 건너뛴다. pip freeze로 lock을 다시 만들면 표시가 빠진다.
    from packaging.requirements import Requirement

    for file_name in ("requirements.txt", "requirements-lock.txt"):
        with open(ROOT / file_name, encoding="utf-8") as f:
            lines = [line.strip() for line in f
                     if line.strip() and not line.lstrip().startswith("#")]
        pywin32 = [line for line in lines if Requirement(line).name.lower() == "pywin32"]
        assert len(pywin32) == 1, file_name
        requirement = Requirement(pywin32[0])
        assert str(requirement.marker) == 'sys_platform == "win32"', file_name
        assert requirement.marker.evaluate(), file_name


def test_bundled_third_party_license_texts_and_notices_exist():
    licenses = ROOT / "licenses"
    expected_markers = {
        "Pretendard-LICENSE.txt": (
            "SIL OPEN FONT LICENSE",
            "Reserved Font Name Pretendard",
        ),
        "Font-Awesome-Free-LICENSE.txt": (
            "Font Awesome Free License",
            "SIL OPEN FONT LICENSE",
        ),
        "QFluentWidgets-LICENSE.txt": (
            "GNU GENERAL PUBLIC LICENSE",
            "Version 3",
        ),
        "LGPL-3.0.txt": (
            "GNU LESSER GENERAL PUBLIC LICENSE",
            "Version 3",
        ),
        "cryptography-LICENSE.APACHE.txt": (
            "Apache License",
            "Version 2.0",
        ),
        "cryptography-LICENSE.BSD.txt": (
            "Redistribution and use in source and binary forms",
            "THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS",
        ),
    }
    for filename, markers in expected_markers.items():
        with open(licenses / filename, encoding="utf-8") as f:
            text = f.read()
        assert all(marker in text for marker in markers)

    import json
    entries = json.loads((licenses / "components.json").read_text(encoding="utf-8"))
    for entry in entries:
        assert entry["files"], entry["id"]
        for filename in entry["files"]:
            assert (ROOT / filename).is_file(), filename
    assert {"app", "qt", "fluent", "hancom", "cffi", "python", "pywin32"} <= {
        entry["id"] for entry in entries
    }
    captured = _spec_analysis(ROOT)
    assert ("LICENSE", ".") in captured["datas"]
    assert ("licenses", "licenses") in captured["datas"]


def test_windows_version_parts_maps_letter_suffix_to_patch_position():
    """v3.6a 같은 문자 접미사는 다음 숫자 자리로 옮겨 버전이 증가해야 한다.

    접미사를 버리면 v3.6과 v3.6a의 Windows 파일 버전이 같아져 속성 창에서
    구분되지 않고 버전 비교로 업데이트를 판단할 수 없다.
    """
    assert _windows_version_parts("v3.6") == (3, 6, 0, 0)
    assert _windows_version_parts("v3.6a") == (3, 6, 1, 0)
    assert _windows_version_parts("v3.6b") == (3, 6, 2, 0)
    assert _windows_version_parts("v3.1a") == (3, 1, 1, 0)
    assert _windows_version_parts("v3.6.2a") == (3, 6, 2, 1)
    assert _windows_version_parts("v3.8") == (3, 8, 0, 0)
    assert _windows_version_parts("v3.8a") == (3, 8, 1, 0)
    assert _windows_version_parts("v3.8b") == (3, 8, 2, 0)
    assert _windows_version_parts("v3.8c") == (3, 8, 3, 0)
    assert _windows_version_parts("v3.8d") == (3, 8, 4, 0)
    assert _windows_version_parts("v3.8e") == (3, 8, 5, 0)
    assert _windows_version_parts("v3.9") == (3, 9, 0, 0)
    assert _windows_version_parts("v3.9a") == (3, 9, 1, 0)
    assert _windows_version_parts("v4.0") == (4, 0, 0, 0)
    assert _windows_version_parts("v4.0a") == (4, 0, 1, 0)
    assert _windows_version_parts("v4.1") == (4, 1, 0, 0)
    assert _windows_version_parts("v4.2") == (4, 2, 0, 0)
    assert _windows_version_parts("v4.3") == (4, 3, 0, 0)
    assert _windows_version_parts("v4.4") == (4, 4, 0, 0)
    assert _windows_version_parts("v4.4a") == (4, 4, 1, 0)
    assert _windows_version_parts("v4.4b") == (4, 4, 2, 0)
    assert _windows_version_parts("v4.5") == (4, 5, 0, 0)
    assert _windows_version_parts("v4.5a") == (4, 5, 1, 0)
    assert _windows_version_parts("v4.6") == (4, 6, 0, 0)
    assert _windows_version_parts("v4.7") == (4, 7, 0, 0)
    assert _windows_version_parts("v4.8") == (4, 8, 0, 0)
    assert _windows_version_parts("v4.9") == (4, 9, 0, 0)

    # 접미사가 붙은 버전은 붙지 않은 같은 base보다 커야 한다.
    assert _windows_version_parts("v3.6a") > _windows_version_parts("v3.6")
    assert _windows_version_parts("v3.6b") > _windows_version_parts("v3.6a")


def test_windows_version_parts_rejects_malformed_versions():
    for bad in ("v3.6ab", "v3.6.", "abc", "v3.6.1.2a", ""):
        with pytest.raises(ValueError):
            _windows_version_parts(bad)


def _spec_analysis(spec_dir, binaries=()):
    """build.spec을 가짜 Analysis·EXE로 실행한다. Analysis 인자와 EXE가 받은 위치 인자(exe_args)를 돌려준다."""
    captured = {}

    def analysis(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pure=[], zipped_data=[], scripts=[], binaries=list(binaries), zipfiles=[], datas=[])

    def exe(*args, **kwargs):
        captured["exe_args"] = args
        return object()

    namespace = {"SPECPATH": str(spec_dir), "Analysis": analysis, "PYZ": lambda *a, **k: object(),
                 "EXE": exe}
    saved_path = sys.path[:]  # build.spec이 sys.path 앞에 spec 폴더를 끼워 넣으므로 되돌린다
    try:
        with open(ROOT / "build.spec", encoding="utf-8") as f:
            exec(compile(f.read(), str(ROOT / "build.spec"), "exec"), namespace)
    finally:
        sys.path[:] = saved_path
    return captured


def test_build_spec_keeps_modules_update_check_needs(tmp_path):
    # urllib.request(프록시 읽기)는 http.client·email을, winhttp_get은 ctypes를 쓴다.
    # 제외하면 빌드는 성공하고 EXE만 시작하지 못한다.
    assert not {"http", "email", "urllib", "socket", "ctypes"} & set(_spec_analysis(tmp_path)["excludes"])


def test_build_spec_excludes_python_openssl_modules(tmp_path):
    # 배포 EXE에는 Python용 OpenSSL이 없다(검사 지적 조치). _ssl·_hashlib가 libssl·libcrypto를 끌고 들어온다.
    assert {"ssl", "_ssl", "_hashlib"} <= set(_spec_analysis(tmp_path)["excludes"])


def test_without_openssl_drops_only_the_five_files():
    keep = [("PySide6\plugins\tls\qschannelbackend.dll", "a", "BINARY"), ("python313.dll", "b", "BINARY"),
            ("cryptography\hazmat\bindings\_rust.pyd", "c", "EXTENSION")]
    drop = [("PySide6\plugins\tls\qopensslbackend.dll", "d", "BINARY"), ("LIBCRYPTO-3.DLL", "e", "BINARY"),
            ("libssl-3.dll", "f", "BINARY"), ("_ssl.pyd", "g", "EXTENSION"), ("lib/_hashlib.pyd", "h", "EXTENSION")]
    assert without_openssl(keep[:1] + drop + keep[1:]) == keep


def test_build_spec_filters_openssl_binaries_before_packing(tmp_path):
    # qopensslbackend.dll은 모듈이 아니라 PySide6 훅이 모으는 플러그인이라 excludes로는 빠지지 않는다.
    binaries = [("python313.dll", "b", "BINARY"), ("PySide6\plugins\tls\qopensslbackend.dll", "d", "BINARY")]
    assert _spec_analysis(tmp_path, binaries=binaries)["exe_args"][2] == binaries[:1]


def test_app_code_avoids_openssl_only_hashlib_calls():
    # OpenSSL이 없는 EXE에는 hashlib.pbkdf2_hmac·scrypt가 없고 hashlib.new는 일부 이름만 된다.
    # 소스 실행·pytest에서는 되고 EXE에서만 깨지므로 여기서 막는다. sha256 같은 이름 함수는 내장 구현이 맡는다.
    banned = {"pbkdf2_hmac", "scrypt", "new"}
    found = []
    for folder in ("src", "screen_text"):
        for path in sorted((ROOT / folder).glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Attribute) and node.attr in banned
                        and isinstance(node.value, ast.Name) and node.value.id == "hashlib"):
                    found.append(f"{path.name}:{node.lineno} hashlib.{node.attr}")
                elif isinstance(node, ast.ImportFrom) and node.module == "hashlib":
                    found.extend(f"{path.name}:{node.lineno} from hashlib import {alias.name}"
                                 for alias in node.names if alias.name in banned)
    assert not found, found


def _imported_top_modules(folder):
    """폴더의 .py 파일이 절대 import하는 최상위 모듈 이름."""
    names = set()
    for path in sorted(folder.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_build_spec_keeps_every_module_the_app_imports(tmp_path):
    # 속도 개선(2026-11-09)이 글자 따기 엔진에 concurrent.futures를 들였는데 build.spec이 concurrent를 빼서,
    # 빌드는 성공하고 EXE의 글자 따기만 '인식 모듈 불러오기 실패'가 됐다(release의 격리 실행이 잡았다)
    present_dir = tmp_path / "present"
    (present_dir / "screen_text").mkdir(parents=True)
    excludes = set(_spec_analysis(present_dir)["excludes"])
    used = _imported_top_modules(ROOT / "screen_text") | _imported_top_modules(ROOT / "src")
    assert not used & excludes, sorted(used & excludes)


def test_build_spec_bundles_screen_text_only_when_folder_exists(tmp_path):
    # 저장소의 screen_text/ 폴더에 기대지 않는다: 걷어낸 뒤에도 이 시험이 통과해야 한다.
    present_dir = tmp_path / "present"
    (present_dir / "screen_text").mkdir(parents=True)
    absent_dir = tmp_path / "absent"
    absent_dir.mkdir()
    present = _spec_analysis(present_dir)
    assert ("screen_text/models", "screen_text/models") in present["datas"]
    assert ("screen_text/icon.svg", "screen_text") in present["datas"]
    assert ("screen_text/licenses", "screen_text/licenses") in present["datas"]
    assert "onnxruntime" in present["hiddenimports"]
    assert "numpy" in present["hiddenimports"]
    assert "numpy" not in present["excludes"]
    assert "html" not in present["excludes"]  # layout.py·ui_text가 html.escape를 쓴다(제외하면 EXE에서 import 실패)
    absent = _spec_analysis(absent_dir)  # 걷어낸 뒤: 폴더가 없으면 원래 빌드
    assert not any("screen_text" in source for source, _ in absent["datas"])
    assert "onnxruntime" not in absent["hiddenimports"]
    assert "numpy" in absent["excludes"]
    assert "html" not in absent["excludes"]  # 걷어내도 src/ui_text.py가 html.escape를 쓴다
