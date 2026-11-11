# build_app.py - PyInstaller 빌드 자동화 스크립트
from pathlib import Path
import subprocess
import sys
import os

# 앱 모듈은 src/에 있다(B안). build.spec·verify가 import해도 app_info를 찾게 한다.
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from app_info import APP_AUTHOR, APP_DISPLAY_NAME, APP_VERSION, app_exe_name

# 배포 EXE에 넣지 않는 OpenSSL 파일(2026-11-10 검사 지적 조치). 앞의 넷은 Python용 OpenSSL과 그것을 끌고
# 들어오는 확장 모듈이고, 다음은 Qt가 OpenSSL을 찾아 쓰는 연결 플러그인이다(안에 OpenSSL 버전 표시가 있다).
# 마지막 둘은 Git Bash에서 빌드하면 PATH의 mingw64 OpenSSL이 섞여 드는 이름이다(2026-09-28).
# 새 버전 확인은 winhttp_get(WinHTTP), 해시는 Python 내장 구현, 본문 암호화는 cryptography가 맡는다.
OPENSSL_FILE_NAMES = frozenset({
    "libcrypto-3.dll", "libssl-3.dll", "_ssl.pyd", "_hashlib.pyd", "qopensslbackend.dll",
    "libcrypto-3-x64.dll", "libssl-3-x64.dll",
})


def without_openssl(entries):
    """PyInstaller 묶음 목록(이름, 원본, 종류)에서 OPENSSL_FILE_NAMES의 파일만 뺀다. 순서는 유지한다.

    qopensslbackend.dll은 모듈이 아니라 PySide6 훅이 모으는 플러그인이라 build.spec의 excludes로는 빠지지 않는다.
    """
    return [entry for entry in entries
            if entry[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in OPENSSL_FILE_NAMES]


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


def build() -> int:
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    exe_name = app_exe_name()
    print(f"빌드를 시작합니다... ({APP_DISPLAY_NAME} {APP_VERSION})")
    
    # 일반 빌드에도 하네스와 같은 lock 검사를 적용한다. 전역 Python의
    # 구형 Qt로 빌드하면 소스에서 해결한 컬러 이모지 잘림이 EXE에 재발한다.
    from tools.verify import doctor

    try:
        environment = doctor(script_dir)
    except (OSError, ValueError) as e:
        print(f"빌드 환경 확인 실패: {e}")
        return 2
    if environment["errors"]:
        print(f"빌드 환경 확인 실패 (Python: {sys.executable})")
        for error in environment["errors"]:
            print(f"  - {error}")
        print("프로젝트 .venv의 Python 3.13과 requirements-lock.txt를 확인하세요.")
        return 2

    # 이전 인터프리터로 만든 분석 결과와 바이너리 캐시를 재사용하지 않는다.
    spec_path = script_dir / "build.spec"
    try:
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec_path)
        ])
        print("\n" + "="*40)
        print("빌드가 성공적으로 완료되었습니다!")
        print(f"출력 파일: dist/{exe_name}")
        print("="*40)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n빌드 중 오류가 발생했습니다: {e}")
        return 1
    except OSError as e:
        print(f"\n빌드 환경 오류: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(build())
