# build_app.py - PyInstaller 빌드 자동화 스크립트
from pathlib import Path
import subprocess
import sys
import os

from app_info import APP_AUTHOR, APP_DISPLAY_NAME, APP_VERSION, app_exe_name


def _windows_version_parts(version: str) -> tuple[int, int, int, int]:
    """``v3.5``/``v3.6a`` 형식 앱 버전을 Windows 4-part 숫자 버전으로 변환한다.

    마지막 자리에 붙는 소문자 한 글자는 패치 표기이며 다음 자리 숫자로 옮긴다
    (``a``→1, ``b``→2 ...). ``v3.6``이 ``3.6.0.0``이므로 ``v3.6a``는
    ``3.6.1.0``이 되어 Windows 속성에서 두 산출물이 구분되고 버전도 증가한다.
    접미사를 그냥 버리면 두 파일이 같은 숫자 버전을 갖게 된다.
    """
    raw = version.strip().lstrip("vV")
    suffix = 0
    if raw and raw[-1].isalpha():
        letter = raw[-1].lower()
        if not ("a" <= letter <= "z"):
            raise ValueError(f"Windows 버전으로 변환할 수 없습니다: {version}")
        suffix = ord(letter) - ord("a") + 1
        raw = raw[:-1]

    raw_parts = raw.split(".")
    max_parts = 3 if suffix else 4
    if not 1 <= len(raw_parts) <= max_parts or any(
        not part.isdigit() for part in raw_parts
    ):
        raise ValueError(f"Windows 버전으로 변환할 수 없습니다: {version}")

    parts = tuple(int(part) for part in raw_parts)
    if suffix:
        # 접미사는 base 바로 다음 자리에 놓는다. major.minor 뒤면 세 번째 자리다.
        # v3.6a -> (3, 6, 1, 0),  v3.6.2a -> (3, 6, 2, 1)
        parts = parts + (0,) * max(0, 2 - len(parts)) + (suffix,)
    return parts + (0,) * (4 - len(parts))


def make_windows_version_info():
    """app_info를 단일 출처로 사용하는 PyInstaller Windows 버전 리소스."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version_parts = _windows_version_parts(APP_VERSION)
    version_text = ".".join(str(part) for part in version_parts)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=version_parts,
            prodvers=version_parts,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    "041204B0",
                    [
                        StringStruct("CompanyName", APP_AUTHOR),
                        StringStruct("FileDescription", APP_DISPLAY_NAME),
                        StringStruct("FileVersion", version_text),
                        StringStruct("InternalName", APP_DISPLAY_NAME),
                        StringStruct("OriginalFilename", app_exe_name()),
                        StringStruct("ProductName", APP_DISPLAY_NAME),
                        StringStruct("ProductVersion", version_text),
                    ],
                )
            ]),
            VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
        ],
    )


def build():
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    exe_name = app_exe_name()
    print(f"빌드를 시작합니다... ({APP_DISPLAY_NAME} {APP_VERSION})")
    
    # 1. PyInstaller 설치 확인
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller가 설치되어 있지 않습니다. 설치를 시도합니다...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. 빌드 실행 (build.spec 사용)
    spec_path = script_dir / "build.spec"
    if not os.path.exists(spec_path):
        print(f"오류: {spec_path} 파일을 찾을 수 없습니다.")
        return

    try:
        subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_path)])
        print("\n" + "="*40)
        print("빌드가 성공적으로 완료되었습니다!")
        print(f"출력 파일: dist/{exe_name}")
        print("="*40)
    except subprocess.CalledProcessError as e:
        print(f"\n빌드 중 오류가 발생했습니다: {e}")
    except (OSError, FileNotFoundError) as e:
        print(f"\n빌드 환경 오류: {e}")

if __name__ == "__main__":
    build()
