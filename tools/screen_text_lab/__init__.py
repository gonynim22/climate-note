"""수동 실행 전용 OCR 진단. import만으로 자료·모델·앱을 읽지 않는다."""

import sys
from pathlib import Path

# 앱 모듈은 src/에 있다(v4.5a). screen_text가 app_paths 등을 import하므로, 부모·작업
# 프로세스와 `python -m tools.screen_text_lab.<모듈>` 직접 실행이 모두 먼저 읽는 이
# 패키지에서 경로만 넣는다. 앱 모듈 자체는 import하지 않는다.
_SRC_DIR = str(Path(__file__).resolve().parents[2] / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
