"""번들 리소스 루트 경로 해석 (소스 실행 / PyInstaller 공용).

폰트·아이콘·SVG·이미지처럼 `build.spec` datas로 묶여 배포되는 파일의
최상위 경로를 한 곳에서 결정한다. 호출하는 모듈이 어느 디렉터리에 있든
같은 값을 돌려주므로, 모듈을 옮겨도 리소스 경로가 깨지지 않는다.

이 모듈이 경로의 기준점(anchor)이다. `app_paths.py`를 하위 폴더로 옮기면
`_SOURCE_ROOT`의 `parents` 단계를 그만큼 올려야 한다. 리소스 경로를
`Path(__file__).parent`로 직접 만드는 코드를 다시 늘리지 않는다.
"""

from pathlib import Path
import sys

# 소스 실행 기준 프로젝트 루트. 이 파일이 루트의 src/에 있다는 전제다(v4.5a).
_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """번들 리소스가 놓이는 최상위 경로.

    PyInstaller one-file 실행에서는 datas가 풀리는 `sys._MEIPASS`이고,
    소스 실행에서는 프로젝트 루트다.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return _SOURCE_ROOT
