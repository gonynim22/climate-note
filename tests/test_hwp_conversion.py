"""문서 원본/동명 결과 보존과 엔진 경계. 모든 파일은 합성 임시 데이터."""
import hashlib
from pathlib import Path
import subprocess
import zipfile

import pytest

import hwp_conversion as conversion
import hwp_conversion_worker as worker


def test_defused_xml_rejection_becomes_conversion_error(tmp_path, monkeypatch):
    from defusedxml import DefusedXmlException
    output = make_hwpx(tmp_path / "result.hwpx")
    original = output.read_bytes()
    conversion.validate_hwpx(output)

    def reject(data):
        raise DefusedXmlException("blocked")

    monkeypatch.setattr(conversion.ElementTree, "fromstring", reject)
    with pytest.raises(conversion.ConversionError):
        conversion.validate_hwpx(output)
    assert output.read_bytes() == original


def test_utf16_hwpx_entity_rejection_preserves_files(tmp_path):
    section = ('<?xml version="1.0" encoding="UTF-16"?>'
               '<!DOCTYPE sec [<!ENTITY a "synthetic">]><sec>&a;</sec>').encode("utf-16")
    output = make_hwpx(tmp_path / "result.hwpx", section=section)
    source = make_hwp(tmp_path / "source.hwp")
    existing = make_hwpx(tmp_path / "source.hwpx")
    originals = {path: path.read_bytes() for path in (output, source, existing)}
    with pytest.raises(conversion.ConversionError):
        conversion.validate_hwpx(output)
    assert {path: path.read_bytes() for path in originals} == originals


def test_valid_utf16_hwpx_remains_read_only(tmp_path):
    section = '<?xml version="1.0" encoding="UTF-16"?><sec>합성 문서</sec>'.encode("utf-16")
    output = make_hwpx(tmp_path / "result.hwpx", section=section)
    original = output.read_bytes()
    conversion.validate_hwpx(output)
    assert output.read_bytes() == original


def header(flags=1):
    data = bytearray(256)
    data[:32] = b"HWP Document File".ljust(32, b"\0")
    data[32:36] = bytes([0, 0, 0, 5])
    data[36:40] = flags.to_bytes(4, "little")
    return bytes(data)


def make_hwp(path, flags=1):
    import pythoncom
    pythoncom.CoInitialize()
    storage = stream = None
    try:
        storage = pythoncom.StgCreateDocfile(str(path), 0x1000 | 0x10 | 2, 0)
        stream = storage.CreateStream("FileHeader", 0x1000 | 0x10 | 2, 0, 0)
        stream.Write(header(flags))
        stream.Commit(0)
        storage.Commit(0)
    finally:
        stream = storage = None
        pythoncom.CoUninitialize()
    return path


def make_hwpx(path, *, mime=b"application/hwp+zip", section="<sec>합성 문서</sec>".encode(), omit=None):
    contents = {"mimetype": mime, "version.xml": b"<HCFVersion/>", "Contents/header.xml": b"<head/>",
                "Contents/content.hpf": b"<package/>", "Contents/section0.xml": section}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            if name != omit:
                archive.writestr(name, data)
    return path


@pytest.mark.parametrize("flags,message", [(2, "암호"), (4, "배포"), (16, "DRM"),
                                         (256, "암호"), (1024, "DRM"), (128, "서명"), (512, "서명")])
def test_rejects_protected_hwp_without_touching_original(tmp_path, flags, message):
    path = make_hwp(tmp_path / "보호.hwp", flags)
    original = path.read_bytes()
    with pytest.raises(conversion.ConversionError, match=message):
        conversion.validate_hwp(path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("data", [b"", b"HWP", b"other".ljust(256, b"\0"), header()[:35] + b"\x03" + header()[36:]])
def test_rejects_wrong_header(data):
    with pytest.raises(conversion.ConversionError):
        conversion.validate_hwp_header(data)


def test_actual_compound_storage_header_is_read_only(tmp_path):
    path = make_hwp(tmp_path / "정상 헤더.HWP")
    before = path.read_bytes()
    conversion.validate_hwp(path)
    assert path.read_bytes() == before
    path.unlink()  # COM 스트림/스토리지가 잠금을 남기지 않는다.


@pytest.mark.parametrize("options", [
    {"mime": b"application/zip"}, {"omit": "Contents/section0.xml"},
    {"section": b"<sec>"}, {"section": b"<unrelated/>"},
    {"section": b'<!DOCTYPE sec [<!ENTITY test "value">]><sec>&test;</sec>'},
])
def test_invalid_output_is_not_treated_as_conversion(tmp_path, options):
    output = make_hwpx(tmp_path / "broken.hwpx", **options)
    with pytest.raises(conversion.ConversionError):
        conversion.validate_hwpx(output)


def test_output_limits_and_crc(tmp_path, monkeypatch):
    output = make_hwpx(tmp_path / "large.hwpx")
    monkeypatch.setattr(conversion, "MAX_EXPANDED_BYTES", 8)
    with pytest.raises(conversion.ConversionError):
        conversion.validate_hwpx(output)


def test_publish_never_replaces_existing_results_or_source(tmp_path):
    original = tmp_path / "원본.hwp"
    original.write_bytes(b"original")
    for name in ("원본.hwpx", "원본 (1).hwpx"):
        (tmp_path / name).write_bytes(b"existing")
    staged = make_hwpx(tmp_path / "stage.hwpx")
    conversion.validate_hwpx(staged)
    data = staged.read_bytes()
    result = conversion.publish_result(staged, tmp_path, original.name)
    assert result.name == "원본 (2).hwpx" and result.read_bytes() == data
    assert original.read_bytes() == b"original"
    assert (tmp_path / "원본.hwpx").read_bytes() == (tmp_path / "원본 (1).hwpx").read_bytes() == b"existing"


def test_installed_converter_alone_does_not_enable_hwp(tmp_path, monkeypatch):
    import winreg
    def missing(*args):
        raise FileNotFoundError()
    monkeypatch.setattr(winreg, "OpenKey", missing)
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    monkeypatch.delenv("ProgramFiles", raising=False)
    engine = tmp_path / "HNC/HwpxConverter/HwpxConverter.exe"
    engine.parent.mkdir(parents=True)
    engine.touch()
    environment = conversion.detect_environment()
    assert environment.converter == engine and environment.hwp is None
    assert not environment.available and "한글" in environment.message


def test_executable_detection_handles_quoted_paths_and_arguments(tmp_path):
    hwp = tmp_path / "한글 설치" / "hwp.exe"
    hwp.parent.mkdir()
    hwp.touch()
    assert conversion._executable(f'"{hwp}" -Automation') == hwp
    assert conversion._executable(f'{hwp} -Automation') == hwp
    assert conversion._executable('hwp.exe') is None
    assert conversion._executable(str(tmp_path / 'missing.exe')) is None


def test_worker_copies_original_and_checks_engine_output(tmp_path, monkeypatch):
    source = make_hwp(tmp_path / "한글 공백.hwp")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    stage = tmp_path / "work"
    stage.mkdir()
    monkeypatch.setattr(worker, "detect_environment", lambda: conversion.ConversionEnvironment(Path("hwp.exe"), Path("HwpxConverter.exe")))
    def engine(command, **options):
        assert Path(command[1]) != source
        assert Path(command[1]).read_bytes() == source.read_bytes()
        assert options["shell"] is False and options["timeout"] == 90
        assert Path(options["env"]["LOCALAPPDATA"]).is_relative_to(stage)
        make_hwpx(Path(command[2]))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(worker.subprocess, "run", engine)
    worker.convert_to_stage(source, stage)
    conversion.validate_hwpx(stage / "result.hwpx")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert not (tmp_path / "한글 공백.hwpx").exists()  # 최종 확정은 부모만 수행.


def test_worker_rejects_protection_before_starting_engine(tmp_path, monkeypatch):
    source = make_hwp(tmp_path / "protected.hwp", 2)
    stage = tmp_path / "work"
    stage.mkdir()
    monkeypatch.setattr(worker, "detect_environment", lambda: conversion.ConversionEnvironment(source, source))
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **kw: pytest.fail("보호 문서에서 엔진 호출"))
    with pytest.raises(conversion.ConversionError, match="암호"):
        worker.convert_to_stage(source, stage)


def test_worker_rejects_oversize_input(tmp_path, monkeypatch):
    source = make_hwp(tmp_path / "large.hwp")
    stage = tmp_path / "work"
    stage.mkdir()
    monkeypatch.setattr(worker, "MAX_SOURCE_BYTES", 16)
    monkeypatch.setattr(worker, "detect_environment", lambda: conversion.ConversionEnvironment(source, source))
    with pytest.raises(conversion.ConversionError, match="100 MB"):
        worker.convert_to_stage(source, stage)


def test_frozen_external_engine_restores_dll_path_even_on_failure(tmp_path, monkeypatch):
    import ctypes
    import os
    from types import SimpleNamespace
    bundle = str(tmp_path / "bundle")
    calls = []
    def get_directory(size, buffer):
        if buffer is not None:
            buffer.value = bundle
        return len(bundle)
    def set_directory(value):
        calls.append(value)
        return True
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: SimpleNamespace(GetDllDirectoryW=get_directory, SetDllDirectoryW=set_directory))
    monkeypatch.setattr(worker.sys, "frozen", True, raising=False)
    monkeypatch.setattr(worker.sys, "_MEIPASS", bundle, raising=False)
    env = {"PATH": os.pathsep.join([bundle, bundle + os.sep + "PySide6", str(tmp_path / "system")])}
    with pytest.raises(RuntimeError):
        with worker.external_engine_environment(env) as clean:
            assert clean["PATH"] == str(tmp_path / "system")
            raise RuntimeError("engine failure")
    assert calls == [None, bundle]
    assert bundle in env["PATH"]
