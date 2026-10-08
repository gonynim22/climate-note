"""배포 패키지 메타데이터·의존성·고지 파일 회귀 테스트."""

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
from build_app import _windows_version_parts


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
        name, version = line.split("==", 1)
        pinned[name.split("[", 1)[0].lower()] = version

    for name in direct_names:
        assert pinned[name.lower()] == distribution(name).version


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

    with open(licenses / "THIRD_PARTY_NOTICES.txt", encoding="utf-8") as f:
        notices = f.read()
    for marker in (
        "Pretendard 1.3.9",
        "Font Awesome Free 6.7.2",
        "PySide6-Fluent-Widgets 1.11.1",
        "PySide6 6.11.2",
        "cryptography 50.0.0",
        "pysidesix-frameless-window 0.8.0",
        "Pretendard-LICENSE.txt",
        "Font-Awesome-Free-LICENSE.txt",
        "QFluentWidgets-LICENSE.txt",
        "LGPL-3.0.txt",
        "cryptography-LICENSE.APACHE.txt",
        "cryptography-LICENSE.BSD.txt",
    ):
        assert marker in notices


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

    # 접미사가 붙은 버전은 붙지 않은 같은 base보다 커야 한다.
    assert _windows_version_parts("v3.6a") > _windows_version_parts("v3.6")
    assert _windows_version_parts("v3.6b") > _windows_version_parts("v3.6a")


def test_windows_version_parts_rejects_malformed_versions():
    for bad in ("v3.6ab", "v3.6.", "abc", "v3.6.1.2a", ""):
        with pytest.raises(ValueError):
            _windows_version_parts(bad)
