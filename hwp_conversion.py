"""HWP → HWPX의 설치 확인·입출력 검증. Qt/DB와 사용자 한글 창에 접근하지 않는다."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree

MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024


class ConversionError(ValueError):
    """경로/본문을 노출하지 않고 화면에 표시할 수 있는 변환 실패."""


@dataclass(frozen=True)
class ConversionEnvironment:
    hwp: Path | None = None
    converter: Path | None = None

    @property
    def available(self):
        return self.hwp is not None and self.converter is not None

    @property
    def message(self):
        if self.hwp is None:
            return "한글이 설치된 PC에서 사용할 수 있습니다."
        if self.converter is None:
            return "한글을 확인했습니다. 한컴 HWPX 변환기를 별도로 설치해 주세요."
        return "한글 · HWPX 변환기 확인 완료"


def _executable(command):
    match = re.match(r'^\s*"?(.+?\.exe)(?:"|\s|,|$)', str(command), re.IGNORECASE)
    if match:
        path = Path(os.path.expandvars(match[1]))
        if path.is_absolute() and path.is_file():
            return path.resolve()
    return None


def detect_environment():
    """32/64비트 등록과 실제 실행 파일을 조회한다. 프로그램을 실행하지 않는다."""
    import winreg

    def read(root, key, name, view):
        try:
            with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as handle:
                return winreg.QueryValueEx(handle, name)[0]
        except OSError:
            return ""  # 해당 제품/레지스트리 보기 미등록은 미설치로 표시.

    hwp = converter = None
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        clsid = read(winreg.HKEY_CLASSES_ROOT, r"HWPFrame.HwpObject\CLSID", "", view)
        if clsid:
            candidate = _executable(read(winreg.HKEY_CLASSES_ROOT, fr"CLSID\{clsid}\LocalServer32", "", view))
            if candidate and candidate.name.lower() == "hwp.exe":
                hwp = candidate
        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                    names = [winreg.EnumKey(handle, i) for i in range(winreg.QueryInfoKey(handle)[0])]
            except OSError:
                continue  # 없는 Uninstall 보기는 다른 보기/표준 설치 경로로 확인.
            for name in names:
                entry = key + "\\" + name
                if "hwpx" in str(read(hive, entry, "DisplayName", view)).lower():
                    candidate = _executable(read(hive, entry, "DisplayIcon", view))
                    if candidate and candidate.name.lower() == "hwpxconverter.exe":
                        converter = candidate
    if converter is None:
        for variable in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(variable)
            if base:
                candidate = Path(base) / "HNC" / "HwpxConverter" / "HwpxConverter.exe"
                if candidate.is_file():
                    converter = candidate.resolve()
                    break
    return ConversionEnvironment(hwp, converter)


def validate_hwp_header(header):
    if len(header) != 256 or header[:32] != b"HWP Document File".ljust(32, b"\0") or header[35] != 5:
        raise ConversionError("지원하는 HWP 5 문서가 아닙니다.")
    flags = int.from_bytes(header[36:40], "little")
    if flags & (2 | (1 << 8)):
        raise ConversionError("암호가 설정된 문서는 지원하지 않습니다.")
    if flags & 4:
        raise ConversionError("배포용 문서는 지원하지 않습니다.")
    if flags & (16 | (1 << 10)):
        raise ConversionError("DRM 보호 문서는 지원하지 않습니다.")
    if flags & ((1 << 7) | (1 << 9)):
        raise ConversionError("전자 서명이 있는 문서는 지원하지 않습니다.")


def validate_hwp(path):
    import pythoncom
    import pywintypes

    pythoncom.CoInitialize()
    storage = stream = None
    try:
        storage = pythoncom.StgOpenStorage(str(path), None, 0x20, None, 0)  # READ / SHARE_DENY_WRITE
        stream = storage.OpenStream("FileHeader", None, 0x10, 0)
        validate_hwp_header(stream.Read(256))
    except pywintypes.com_error as exc:
        raise ConversionError("정상적인 HWP 5 문서를 읽을 수 없습니다. 파일 형식이나 보호 상태를 확인해 주세요.") from exc
    finally:
        stream = storage = None  # 파일 핸들을 먼저 반환한 뒤 COM을 해제.
        pythoncom.CoUninitialize()


def validate_hwpx(path):
    """크기 제한 안에서 CRC·형식·필수 XML을 검사한다. 압축을 풀지 않는다."""
    required = {"mimetype", "version.xml", "Contents/content.hpf", "Contents/header.xml", "Contents/section0.xml"}
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) != len(names) or not required <= names or sum(e.file_size for e in entries) > MAX_EXPANDED_BYTES:
                raise ConversionError("변환 결과의 HWPX 구성 또는 크기를 확인할 수 없습니다.")
            if archive.getinfo("mimetype").file_size > 128 or archive.read("mimetype").strip() != b"application/hwp+zip":
                raise ConversionError("변환 결과가 HWPX 형식이 아닙니다.")
            for entry in entries:
                if entry.filename.endswith((".xml", ".hpf")):
                    if entry.file_size > MAX_XML_BYTES:
                        raise ConversionError("변환 결과의 XML이 지원 크기를 초과했습니다.")
                    data = archive.read(entry)
                    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                        raise ConversionError("지원하지 않는 XML 선언이 포함되어 있습니다.")
                    root = ElementTree.fromstring(data)
                    expected = {
                        "Contents/header.xml": "head",
                        "Contents/section0.xml": "sec",
                        "Contents/content.hpf": "package",
                        "version.xml": "HCFVersion",
                    }.get(entry.filename)
                    if expected and root.tag.rsplit("}", 1)[-1] != expected:
                        raise ConversionError("변환 결과의 필수 XML 구조가 올바르지 않습니다.")
            if archive.testzip() is not None:
                raise ConversionError("변환 결과가 손상되었습니다.")
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, RuntimeError, KeyError) as exc:
        raise ConversionError("변환 결과를 정상적인 HWPX로 확인할 수 없습니다.") from exc


def publish_result(staged, directory, source_name):
    """Windows rename은 기존 대상을 교체하지 않는다. 경합도 동일하게 처리한다."""
    if os.name != "nt":
        raise ConversionError("Windows에서만 변환할 수 있습니다.")
    stem = Path(source_name).stem
    for number in range(10000):
        suffix = f" ({number})" if number else ""
        target = Path(directory) / f"{stem}{suffix}.hwpx"
        try:
            os.rename(staged, target)
            return target
        except FileExistsError:
            continue  # 원본과 기존 결과를 보존하고 다음 빈 이름을 시도.
    raise ConversionError("같은 이름의 파일이 너무 많습니다. 다른 저장 폴더를 선택해 주세요.")
