# 화면 글자 따기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면 영역을 고르면 PC 안의 소형 OCR 모델이 한국어를 읽고, 표는 칸을 유지해 복사하는 다섯 번째 미니앱을 폴더 하나와 등록 한 줄로 걷어낼 수 있게 만든다.

**Architecture:**
- 순수 Python인 `layout`(줄·표 재구성)과 numpy+onnxruntime인 `engine`(PP-OCR 추론)을 Qt와 분리한다.
- Qt 쪽 `capture`(화면 멈춤·선택)와 `window`(도구 창)가 이 둘을 쓴다.
- 메인 창에는 "선택형 미니앱" 공용 연결부를 한 번만 넣고, 앱은 `optional_mini_apps.py` 등록부로만 연결한다.

**Tech Stack:** Python 3.13, PySide6 6.11.2, onnxruntime 1.30.0(CPU), numpy 2.2.6, PaddleOCR ONNX 모델(PP-OCRv3 mobile det, korean PP-OCRv5 mobile rec), pytest-qt, PyInstaller 6.19.

**Spec:** [`docs/superpowers/specs/2026-10-08-screen-text-capture-design.md`](../specs/2026-10-08-screen-text-capture-design.md)

## Global Constraints

- DB v17·Export v2·salt·암호화 키 유도·기존 설정 키·바로가기 6슬롯을 바꾸지 않는다. **새 설정 키, DB 테이블, 컬럼을 만들지 않는다.**
- 런타임은 오프라인 전용이다. 네트워크를 쓰지 않고 `onnxruntime.disable_telemetry_events()`를 호출한다.
- Qt 6.11.2 유지. lock에는 `onnxruntime==1.30.0`, `flatbuffers==25.12.19`, `protobuf==7.36.2`만 추가한다(numpy 2.2.6은 이미 있음). 세 패키지와 numpy는 2026-10-08 로컬 OSV-Scanner 2.5.1에서 지적 0건이다.
- `screen_text`를 import하는 곳은 `optional_mini_apps.py`, `build.spec`, `tests/test_screen_text_*.py`와 `screen_text/` 내부뿐이다.
- 기존 미니앱 4개(`ui_unit_converter.py`, `ui_date_time_calculator.py`, `ui_money_notation.py`, `ui_document_converter.py`)의 코드는 바꾸지 않는다. `ui_main.py`에는 기존 줄 옆에 공용 연결부 줄만 더한다.
- 리소스 경로는 `app_paths.resource_root()`로 만든다. `Path(__file__).parent`로 리소스 경로를 조립하지 않는다.
- QSS 글꼴 크기는 정수 px만 쓴다.
- 찍은 화면은 메모리에만 두고 임시 파일을 만들지 않는다. 로그에는 오류 종류만 남기고 글자·이미지는 남기지 않는다.
- `bare except` 금지. `except Exception`은 작업 스레드 경계에서만, 로깅과 함께 쓴다(`docs/CODING_STANDARDS.md` 4절).
- 파일은 `with open(...)`으로 연다. 이 기능은 DB에 접근하지 않는다.
- 테스트는 합성 데이터만 쓴다. 실사용 AppData·DB·salt·실제 문서를 쓰지 않는다.
- 테스트 프로필(quick/data/full)은 Git Bash에서 실행해도 된다. **release와 일반 빌드는 PowerShell에서만** 실행한다.
- 커밋 메시지는 한국어 `feat:`/`test:`/`docs:`/`build:` 접두어를 쓰고, 끝에 아래 줄을 붙인다.
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- 커밋은 해당 작업 파일만 명시해서 add한다(`git add -A` 금지). 저장소에 원래 있던 미커밋 변경(`AGENTS.md`, `docs/RELEASE_HISTORY.md`, 미추적 `docs/work/*` 5개)은 Task 8 전까지 건드리지 않는다.

## Review Focus

1. **로컬·KVM·혼합 DPI 환경의 보조 모니터 선택**: 배율 1.25/1.5 화면에서 고른 영역이 실제 픽셀 기준으로 정확히 잘려야 한다. → Task 6 `test_drag_selection_crops_physical_pixels_on_scaled_screen`, `test_crop_physical_rounds_fractional_ratio_and_clips`, `test_drag_past_screen_edge_is_clipped_to_that_screen`
2. **인식 중 잠금·트레이·초기화**: 늦게 끝난 인식 결과가 잠긴 창이나 새 화면에 나타나면 안 된다. → Task 7 `test_cancel_during_recognition_discards_late_result`, `test_hide_owned_popups_stops_pending_capture`
3. **아주 큰 선택(4K 전체 화면 등)**: 멈추지 않고 끝나며 상자 좌표는 원본 기준이어야 한다. → Task 3 `test_large_image_is_downscaled_and_mapped_back`
4. **인식 글자에 `<`, `&`, 탭, 줄바꿈이 섞임**: HTML 표가 깨지거나 탭 구분 칸이 밀리면 안 된다. → Task 2 `test_html_escapes_markup_and_tsv_flattens_tabs_and_newlines`
5. **모델 파일 손상·누락(EXE 내부 포함)**: 엔진이 이상한 모델을 실행하지 않고, 창은 안내 후 버튼을 막아야 한다. → Task 3 `test_engine_refuses_tampered_models`, Task 7 `test_model_error_disables_capture_button`

---

### Task 1: 작업 기록, 의존성, 모델 번들

**Files:**
- Create: `docs/work/2026-10-08-screen-text-capture.md`
- Create: `.gitattributes`
- Create: `screen_text/__init__.py` (이번 작업에서는 docstring만)
- Create: `screen_text/models/det.onnx`, `screen_text/models/rec.onnx`, `screen_text/models/dict.txt`, `screen_text/models/MANIFEST.json`, `screen_text/models/LICENSE`
- Modify: `requirements.txt`, `requirements-lock.txt`, `tools/verify.py:22-25`, `tests/test_packaging.py:108-119`
- Test: `tests/test_screen_text_engine.py` (처음 만듦)

**Interfaces:**
- Produces: `screen_text/models/MANIFEST.json` 형식 `{"format": 1, "source", "revision", "license", "files": [{"role": "det"|"rec"|"dict", "name", "model", "url", "size", "sha256"}]}`. 모델 파일 3개. Task 3이 이 형식을 읽는다.

- [ ] **Step 1: 작업 기록을 만든다**

`docs/work/2026-10-08-screen-text-capture.md`:

```markdown
# 작업 기록: 화면 글자 따기 미니앱

작성일: 2026-10-08 / 상태: 진행 중

## 목표와 범위

- 목표: 공모전(행정업무 효율화)용 다섯 번째 미니앱. 화면 영역의 한국어를 PC 안 소형 모델로 읽고 표는 칸을 유지해 복사한다. 폴더 하나와 등록 한 줄로 걷어낼 수 있다.
- 변경 대상: `screen_text/`, `optional_mini_apps.py`, `ui_mini_apps.py`, `ui_main.py`(공용 연결부), `build.spec`, 의존성·라이선스·문서, `app_info.py`(v3.9).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·바로가기 6슬롯 유지. 결과·화면은 메모리 전용.
- 제외 범위: 전역 단축키, 파일 끌어놓기, 스티키 보내기, PDF, 기울기 보정, push·Release 게시.
- 시작 시 사용자 변경: `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 5개를 보존한다. 시작 HEAD는 계획 커밋.

## 완료 조건

- [ ] 설계 문서의 화면 흐름·인식·표 재구성·수명 처리·걷어내기 절차 구현
- [ ] `quick --tests` 각 단계, 125/150% 합성 배율, `release` 1회
- [ ] 업무 PC 수동 확인(캡처 차단, 한글 표 붙여넣기, 혼합 DPI, 실측)

## 결정과 진행

- 2026-10-08: 설계 승인, 계획 작성. 개발 PC 시제품에서 13px 한국어 문장·표를 거의 정확히 읽음(마침표 뒤 공백 누락), 폭 정렬 묶음으로 인식 약 0.2~0.35초. 같은 이미지에서 Windows 내장 OCR은 줄 누락·오인식.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| | 미실행 | | |

## 미해결과 인계

- 남은 문제 / 수동 확인: 업무 PC 확인 전부
- 변경한 정본 문서: (Task 8에서 기입)
- 다음 행동: Task 1부터 진행
- 배포·커밋·push 여부: 로컬 커밋만. push·Release 게시는 별도 승인
```

- [ ] **Step 2: 모델 파일이 줄바꿈 변환되지 않게 한다**

`core.autocrlf=true`라 `dict.txt`가 체크아웃 때 CRLF로 바뀌면 SHA-256이 달라진다. `.gitattributes`:

```
# 화면 글자 따기 모델은 바이트 그대로 둔다 (MANIFEST.json SHA-256 고정)
screen_text/models/* -text
```

- [ ] **Step 3: 실패하는 MANIFEST 검사를 쓴다**

`tests/test_screen_text_engine.py`:

```python
"""화면 글자 따기 인식 엔진: 번들 모델 무결성과 전후처리, 실제 모델 인식."""
import hashlib
import json
from pathlib import Path

from app_paths import resource_root

MODEL_DIR = resource_root() / "screen_text" / "models"


def test_manifest_matches_bundled_files():
    with open(MODEL_DIR / "MANIFEST.json", encoding="utf-8") as stream:
        manifest = json.load(stream)
    assert manifest["license"] == "Apache-2.0"
    assert {entry["role"] for entry in manifest["files"]} == {"det", "rec", "dict"}
    for entry in manifest["files"]:
        path = MODEL_DIR / entry["name"]
        with open(path, "rb") as stream:
            data = stream.read()
        assert len(data) == entry["size"], entry["name"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["name"]
    with open(MODEL_DIR / "LICENSE", encoding="utf-8") as stream:
        assert "Apache License" in stream.read()
```

- [ ] **Step 4: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_engine.py -v`
Expected: FAIL. `FileNotFoundError: ...screen_text\models\MANIFEST.json`

- [ ] **Step 5: 모델을 고정 리비전에서 받고 SHA-256을 확인한다**

Run (Git Bash, 프로젝트 루트):

```bash
mkdir -p screen_text/models
.venv/Scripts/python.exe - <<'EOF'
import hashlib, urllib.request
BASE = "https://huggingface.co/monkt/paddleocr-onnx/resolve/7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65/"
FILES = {
    "det.onnx": ("detection/v3/det.onnx", "ee40e80071ba3a320d4efda75f3e22047a7d049e9bf7bcaaf9daea23fc21b935"),
    "rec.onnx": ("languages/korean/rec.onnx", "322f140154c820fcb83c3d24cfe42c9ec70dd1a1834163306a7338136e4f1eaa"),
    "dict.txt": ("languages/korean/dict.txt", "a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7"),
}
for name, (path, expected) in FILES.items():
    data = urllib.request.urlopen(BASE + path, timeout=120).read()
    actual = hashlib.sha256(data).hexdigest()
    assert actual == expected, (name, actual)
    with open("screen_text/models/" + name, "wb") as stream:
        stream.write(data)
    print(name, len(data), actual)
EOF
cp licenses/cryptography-LICENSE.APACHE.txt screen_text/models/LICENSE
```

Expected: `det.onnx 2429873 ee40…`, `rec.onnx 13401252 322f…`, `dict.txt 47451 a880…`

- [ ] **Step 6: MANIFEST.json과 패키지 파일을 만든다**

`screen_text/models/MANIFEST.json`:

```json
{
  "format": 1,
  "source": "https://huggingface.co/monkt/paddleocr-onnx (PaddleOCR 모델의 ONNX 변환본)",
  "revision": "7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65",
  "license": "Apache-2.0",
  "files": [
    {"role": "det", "name": "det.onnx", "model": "PP-OCRv3_mobile_det",
     "url": "https://huggingface.co/monkt/paddleocr-onnx/resolve/7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65/detection/v3/det.onnx",
     "size": 2429873, "sha256": "ee40e80071ba3a320d4efda75f3e22047a7d049e9bf7bcaaf9daea23fc21b935"},
    {"role": "rec", "name": "rec.onnx", "model": "korean_PP-OCRv5_mobile_rec",
     "url": "https://huggingface.co/monkt/paddleocr-onnx/resolve/7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65/languages/korean/rec.onnx",
     "size": 13401252, "sha256": "322f140154c820fcb83c3d24cfe42c9ec70dd1a1834163306a7338136e4f1eaa"},
    {"role": "dict", "name": "dict.txt", "model": "ppocrv5_korean_dict",
     "url": "https://huggingface.co/monkt/paddleocr-onnx/resolve/7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65/languages/korean/dict.txt",
     "size": 47451, "sha256": "a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7"}
  ]
}
```

`screen_text/__init__.py`:

```python
"""화면 글자 따기 미니앱 (걷어낼 수 있는 선택형 앱). 계약은 docs/SCREEN_TEXT.md를 따른다."""
```

- [ ] **Step 7: 검사가 통과하는지 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_engine.py -v`
Expected: PASS 1개

- [ ] **Step 8: onnxruntime를 설치하고 lock을 갱신한다**

Run: `.venv/Scripts/python.exe -m pip install onnxruntime==1.30.0`
Run: `.venv/Scripts/python.exe -m pip show onnxruntime flatbuffers protobuf numpy | grep -E "^(Name|Version)"`
Expected: `onnxruntime 1.30.0`, `flatbuffers 25.12.19`, `protobuf 7.36.2`, `numpy 2.2.6`. 다르면 멈추고 실제 버전을 작업 기록에 적은 뒤 사용자에게 알린다.

`requirements.txt` 끝에 한 줄 추가:

```
onnxruntime
```

`requirements-lock.txt` 수정:
- 머리 주석 마지막 줄 뒤에 `# 2026-10-08 화면 글자 따기: onnxruntime 1.30.0(하위 flatbuffers·protobuf) 추가 (docs/work/2026-10-08-screen-text-capture.md).`를 넣는다.
- 첫 묶음 `defusedxml==0.7.1` 다음 줄에 `onnxruntime==1.30.0`를 넣는다.
- 둘째 묶음에 알파벳 순서로 `flatbuffers==25.12.19`(`darkdetect` 다음), `protobuf==7.36.2`(`pluggy` 다음)를 넣는다.

`tools/verify.py`의 `DIRECT_DEPENDENCIES` 끝에 `"onnxruntime"`을 더한다:

```python
DIRECT_DEPENDENCIES = (
    "PySide6", "PySide6-Fluent-Widgets", "cryptography", "python-dotenv",
    "pytest", "pytest-qt", "pytest-timeout", "PyInstaller", "pywin32", "defusedxml",
    "onnxruntime",
)
```

`tests/test_packaging.py`의 `direct_names` 집합에 `"onnxruntime",`을 더한다(`"defusedxml",` 다음 줄).

- [ ] **Step 9: 환경·패키징 검사를 돌린다**

Run: `.venv/Scripts/python.exe tools/verify.py doctor`
Expected: errors 없음
Run: `.venv/Scripts/python.exe tools/verify.py quick --tests tests/test_packaging.py tests/test_screen_text_engine.py`
Expected: 통과, 실패·오류·skip 0. 실행 ID를 작업 기록 표에 적는다.

- [ ] **Step 10: 커밋한다**

```bash
git add .gitattributes docs/work/2026-10-08-screen-text-capture.md screen_text/__init__.py screen_text/models requirements.txt requirements-lock.txt tools/verify.py tests/test_packaging.py tests/test_screen_text_engine.py
git commit -m "build: 화면 글자 따기 모델 번들과 onnxruntime 의존성 추가

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 줄·표 재구성 (`screen_text/layout.py`)

**Files:**
- Create: `screen_text/layout.py`
- Test: `tests/test_screen_text_layout.py`

**Interfaces:**
설계와 다른 점: 설계의 표 판단 규칙 "그 줄의 60% 이상이 2칸 이상"을 **"표에 들어가는 모든 줄이 2칸 이상"**으로 단순화한다(더 엄격). 문장 줄이 표에 섞이는 오판을 줄이려는 것이다. 한 칸만 있는 줄은 표를 끝낸다.

- Produces:
  - `TextBox(x: int, y: int, w: int, h: int, text: str, score: float)` (frozen dataclass, 원본 픽셀 좌표)
  - `Cell(text: str, unsure: bool = False)`, `TextLine(cells: list[Cell])`, `Table(rows: list[list[Cell]])`
  - `group_lines(boxes) -> list[list[TextBox]]`
  - `build_blocks(boxes) -> list[TextLine | Table]`
  - `rows_of(block) -> list[list[Cell]]`
  - `to_plain(blocks) -> str`, `to_tsv(blocks) -> str`, `to_html(blocks) -> str`
  - `unsure_count(blocks) -> int`, `has_table(blocks) -> bool`
  - 상수 `UNSURE_SCORE = 0.80`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_screen_text_layout.py`:

```python
"""화면 글자 따기 줄·표 재구성: 순수 Python 규칙만 검사한다."""
from screen_text.layout import (
    Cell, Table, TextBox, TextLine, build_blocks, group_lines, has_table, rows_of,
    to_html, to_plain, to_tsv, unsure_count,
)


def box(x, y, text, w=None, h=16, score=0.99):
    return TextBox(x, y, w if w is not None else 10 * len(text), h, text, score)


# 테두리 없는 표: 머리글 + 3행, '충북' 위반 칸은 '51'을 '5l'로 잘못 읽은 상태
TABLE_BOXES = [
    box(10, 10, "구분", w=30), box(120, 10, "점검 사업장", w=70), box(260, 10, "위반", w=30),
    box(12, 34, "대전", w=30), box(140, 34, "42", w=16), box(265, 34, "3", w=8),
    box(12, 58, "충북", w=30), box(140, 58, "5l", w=16, score=0.95), box(265, 58, "4", w=8),
    box(12, 82, "계", w=14), box(136, 82, "176", w=24), box(262, 82, "15", w=16),
]


def texts(rows):
    return [[cell.text for cell in row] for row in rows]


def test_group_lines_orders_rows_top_to_bottom_and_left_to_right():
    lines = group_lines(list(reversed(TABLE_BOXES)))
    assert [[b.text for b in line] for line in lines] == [
        ["구분", "점검 사업장", "위반"], ["대전", "42", "3"], ["충북", "5l", "4"], ["계", "176", "15"],
    ]


def test_group_lines_keeps_slightly_offset_boxes_on_one_line():
    assert len(group_lines([box(0, 10, "가"), box(50, 14, "나")])) == 1
    assert len(group_lines([box(0, 10, "가"), box(50, 30, "나")])) == 2


def test_borderless_aligned_rows_become_table():
    blocks = build_blocks(TABLE_BOXES)
    assert len(blocks) == 1 and isinstance(blocks[0], Table)
    assert texts(blocks[0].rows) == [
        ["구분", "점검 사업장", "위반"], ["대전", "42", "3"], ["충북", "5l", "4"], ["계", "176", "15"],
    ]


def test_numeric_column_lookalike_letter_is_marked_unsure_not_corrected():
    table = build_blocks(TABLE_BOXES)[0]
    assert table.rows[2][1].text == "5l"
    assert table.rows[2][1].unsure
    assert not table.rows[2][0].unsure
    assert unsure_count([table]) == 1


def test_low_score_box_is_unsure():
    blocks = build_blocks([box(0, 0, "점검", score=0.5)])
    assert isinstance(blocks[0], TextLine) and blocks[0].cells[0].unsure


def test_paragraph_line_spanning_columns_ends_table():
    boxes = TABLE_BOXES + [box(10, 106, "붙임", w=30), box(60, 106, "점검 결과 세부 내역 1부. 끝.", w=260)]
    blocks = build_blocks(boxes)
    assert isinstance(blocks[0], Table) and len(blocks[0].rows) == 4
    assert isinstance(blocks[1], TextLine)
    assert [c.text for c in blocks[1].cells] == ["붙임", "점검 결과 세부 내역 1부. 끝."]


def test_single_row_is_not_a_table():
    assert not has_table(build_blocks([box(0, 0, "구분", w=30), box(100, 0, "위반", w=30)]))


def test_missing_cell_stays_empty_in_its_column():
    boxes = TABLE_BOXES[:3] + [box(12, 34, "대전", w=30), box(265, 34, "3", w=8)]
    table = build_blocks(boxes)[0]
    assert texts(table.rows)[1] == ["대전", "", "3"]


def test_plain_tsv_and_html_outputs():
    shifted = [TextBox(b.x, b.y + 40, b.w, b.h, b.text, b.score) for b in TABLE_BOXES]
    blocks = build_blocks([box(0, 0, "제목", w=30)] + shifted)
    assert to_plain(blocks).splitlines()[:2] == ["제목", "구분 점검 사업장 위반"]
    assert to_tsv(blocks).splitlines()[:2] == ["제목", "구분\t점검 사업장\t위반"]
    html_text = to_html(blocks)
    assert "<p>제목</p>" in html_text
    assert html_text.count("<tr>") == 4
    assert "<td>점검 사업장</td>" in html_text


def test_html_escapes_markup_and_tsv_flattens_tabs_and_newlines():
    blocks = [Table([[Cell("a<b>&c"), Cell("x\ty\nz")], [Cell("1"), Cell("2")]])]
    assert "a&lt;b&gt;&amp;c" in to_html(blocks)
    assert to_tsv(blocks).splitlines()[0] == "a<b>&c\tx y z"


def test_rows_of_and_empty_input():
    line = TextLine([Cell("가")])
    assert rows_of(line) == [[Cell("가")]]
    assert build_blocks([]) == []
    assert to_plain([]) == "" and to_tsv([]) == "" and unsure_count([]) == 0
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_layout.py -v`
Expected: FAIL. `ModuleNotFoundError: No module named 'screen_text.layout'`

- [ ] **Step 3: 구현한다**

`screen_text/layout.py`:

```python
"""인식 상자를 줄·표로 재구성하고 불확실한 곳을 표시한다.

Qt·numpy를 쓰지 않는 순수 Python이다. 규칙은 docs/SCREEN_TEXT.md를 따른다.
글자를 자동으로 고치지 않고 불확실한 곳만 표시한다(추정 금지).
"""
from dataclasses import dataclass
import html
import re

UNSURE_SCORE = 0.80          # 이 값 미만의 인식 점수는 확인 필요 (Task 4 측정으로 확정)
LINE_OVERLAP = 0.5           # 세로 겹침이 작은 쪽 높이의 이 비율 이상이면 같은 줄
LOOKALIKE = frozenset("lIOoSB")
_NUMERIC = re.compile(r"[0-9.,%△▲▽+\-()]+")


@dataclass(frozen=True)
class TextBox:
    """원본 이미지 픽셀 좌표의 글자 상자와 인식 결과."""
    x: int
    y: int
    w: int
    h: int
    text: str
    score: float


@dataclass
class Cell:
    text: str
    unsure: bool = False


@dataclass
class TextLine:
    cells: list[Cell]


@dataclass
class Table:
    rows: list[list[Cell]]


def rows_of(block):
    """TextLine은 한 행, Table은 모든 행을 돌려준다."""
    return block.rows if isinstance(block, Table) else [block.cells]


def group_lines(boxes):
    """세로 위치로 줄을 묶고 줄 안은 왼쪽부터 정렬한다."""
    lines = []  # [상자 목록, 위, 아래]
    for item in sorted(boxes, key=lambda b: (b.y + b.h / 2, b.x)):
        if lines:
            members, top, bottom = lines[-1]
            overlap = min(bottom, item.y + item.h) - max(top, item.y)
            if overlap >= LINE_OVERLAP * min(bottom - top, item.h):
                members.append(item)
                lines[-1][1], lines[-1][2] = min(top, item.y), max(bottom, item.y + item.h)
                continue
        lines.append([[item], item.y, item.y + item.h])
    return [sorted(members, key=lambda b: b.x) for members, _, _ in lines]


def _merge_bands(intervals):
    """겹치는 x 구간을 합쳐 왼쪽부터 열 띠 목록을 만든다."""
    bands = []
    for start, end in sorted(intervals):
        if bands and start < bands[-1][1]:
            bands[-1] = (bands[-1][0], max(bands[-1][1], end))
        else:
            bands.append((start, end))
    return bands


def _intervals(line):
    return [(item.x, item.x + item.w) for item in line]


def _table_runs(lines):
    """표가 되는 연속 줄 구간 (시작, 끝, 열 띠). 2칸 이상인 줄 2개 이상이 같은 열에 맞아야 한다."""
    runs, index = [], 0
    while index < len(lines):
        if len(lines[index]) < 2:
            index += 1
            continue
        bands = _merge_bands(_intervals(lines[index]))
        end = index + 1
        while end < len(lines) and len(lines[end]) >= 2:
            merged = _merge_bands(bands + _intervals(lines[end]))
            if len(merged) < len(bands):  # 여러 칸을 가로지르는 줄은 일반 문장이다
                break
            bands, end = merged, end + 1
        if end - index >= 2 and len(bands) >= 2:
            runs.append((index, end, bands))
        index = end
    return runs


def _cell(items):
    text = " ".join(item.text for item in items).strip()
    return Cell(text, any(item.score < UNSURE_SCORE for item in items))


def _column_of(item, bands):
    center = item.x + item.w / 2
    for column, (start, end) in enumerate(bands):
        if start <= center < end:
            return column
    return min(range(len(bands)), key=lambda c: abs((bands[c][0] + bands[c][1]) / 2 - center))


def _table(lines, bands):
    rows = []
    for line in lines:
        slots = [[] for _ in bands]
        for item in line:
            slots[_column_of(item, bands)].append(item)
        rows.append([_cell(slot) for slot in slots])
    return Table(rows)


def _mark_lookalikes(table):
    """숫자가 절반 이상인 열에서 숫자와 닮은 영문자가 섞인 칸을 확인 필요로 표시한다."""
    for column in range(len(table.rows[0])):
        cells = [row[column] for row in table.rows if row[column].text]
        numeric = [cell for cell in cells if _NUMERIC.fullmatch(cell.text)]
        if not cells or len(numeric) * 2 < len(cells):
            continue
        for cell in cells:
            if any(ch.isdigit() for ch in cell.text) and LOOKALIKE & set(cell.text):
                cell.unsure = True


def build_blocks(boxes):
    """글자 상자를 위에서 아래로 TextLine·Table 블록 목록으로 만든다."""
    lines = group_lines(boxes)
    runs = {start: (end, bands) for start, end, bands in _table_runs(lines)}
    blocks, index = [], 0
    while index < len(lines):
        if index in runs:
            end, bands = runs[index]
            table = _table(lines[index:end], bands)
            _mark_lookalikes(table)
            blocks.append(table)
            index = end
        else:
            blocks.append(TextLine([_cell([item]) for item in lines[index]]))
            index += 1
    return blocks


def _clean(text):
    """탭·줄바꿈이 칸 경계를 깨지 않도록 공백 하나로 바꾼다."""
    return " ".join(text.split())


def _line_text(cells):
    return " ".join(_clean(cell.text) for cell in cells if cell.text)


def to_plain(blocks):
    return "\n".join(_line_text(row) for block in blocks for row in rows_of(block))


def to_tsv(blocks):
    lines = []
    for block in blocks:
        if isinstance(block, Table):
            lines.extend("\t".join(_clean(cell.text) for cell in row) for row in block.rows)
        else:
            lines.append(_line_text(block.cells))
    return "\n".join(lines)


def to_html(blocks):
    parts = []
    for block in blocks:
        if isinstance(block, Table):
            rows = "".join(
                "<tr>" + "".join(f"<td>{html.escape(_clean(cell.text))}</td>" for cell in row) + "</tr>"
                for row in block.rows
            )
            parts.append(f'<table border="1" cellspacing="0" cellpadding="2">{rows}</table>')
        else:
            parts.append(f"<p>{html.escape(_line_text(block.cells))}</p>")
    return "<html><body>" + "".join(parts) + "</body></html>"


def unsure_count(blocks):
    return sum(cell.unsure for block in blocks for row in rows_of(block) for cell in row)


def has_table(blocks):
    return any(isinstance(block, Table) for block in blocks)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_layout.py -v`
Expected: PASS 11개

- [ ] **Step 5: 커밋한다**

```bash
git add screen_text/layout.py tests/test_screen_text_layout.py
git commit -m "feat: 화면 글자 따기 줄·표 재구성과 불확실 표시

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 인식 엔진 (`screen_text/engine.py`)

**Files:**
- Create: `screen_text/engine.py`
- Modify: `tests/test_screen_text_engine.py` (Task 1 파일에 추가)

**Interfaces:**
- Consumes: `screen_text.layout.TextBox`, Task 1의 `MANIFEST.json`
- Produces:
  - `model_dir() -> Path`
  - `verify_models(directory=None) -> dict[str, Path]`: 키 `"det"`, `"rec"`, `"dict"`. 불일치하면 `ModelIntegrityError`
  - `load_charset(path) -> list[str]`: 11,945자 + 마지막 `" "`
  - `rgb_from_buffer(width, height, bytes_per_line, data) -> np.ndarray(H, W, 3) uint8`
  - `resize_bilinear(image, width, height) -> np.ndarray float32`
  - `label_components(mask) -> list[(x0, y0, x1, y1, runs)]`: 포함 좌표, `runs = [(y, x_start, x_end)]`
  - `expand_box(x0, y0, x1, y1, ratio=1.5) -> (fx0, fy0, fx1, fy1)`
  - `ctc_decode(probs, charset) -> (text, mean_confidence)`
  - `class OcrEngine(directory=None, threads=None)`, `.recognize(image, cancelled=lambda: False) -> list[TextBox]`
  - 예외 `ModelIntegrityError(RuntimeError)`, `RecognitionCancelled(Exception)`

- [ ] **Step 1: 실패하는 테스트를 추가한다**

`tests/test_screen_text_engine.py` 맨 위 import를 아래로 바꾸고, 기존 `test_manifest_matches_bundled_files` 아래에 테스트를 추가한다:

```python
"""화면 글자 따기 인식 엔진: 번들 모델 무결성과 전후처리, 실제 모델 인식."""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from app_paths import resource_root
from screen_text.engine import (
    ModelIntegrityError, OcrEngine, RecognitionCancelled, ctc_decode, expand_box,
    label_components, load_charset, model_dir, resize_bilinear, rgb_from_buffer, verify_models,
)

MODEL_DIR = resource_root() / "screen_text" / "models"
```

```python
def test_verify_models_returns_roles_and_rejects_changed_file(tmp_path):
    assert set(verify_models()) == {"det", "rec", "dict"}
    assert model_dir() == MODEL_DIR
    copy = tmp_path / "models"
    shutil.copytree(MODEL_DIR, copy)
    with open(copy / "dict.txt", "ab") as stream:
        stream.write(b"x")
    with pytest.raises(ModelIntegrityError):
        verify_models(copy)


def test_verify_models_rejects_missing_manifest(tmp_path):
    with pytest.raises(ModelIntegrityError):
        verify_models(tmp_path)


def test_load_charset_appends_space_as_last_class():
    chars = load_charset(MODEL_DIR / "dict.txt")
    assert len(chars) == 11946
    assert chars[0] == "\u1100" and chars[-1] == " "


def test_rgb_from_buffer_drops_row_padding():
    data = bytes([1, 2, 3, 4, 5, 6, 0, 0, 7, 8, 9, 10, 11, 12, 0, 0])  # 2×2, 줄당 8바이트
    image = rgb_from_buffer(2, 2, 8, data)
    assert image.shape == (2, 2, 3)
    assert image[1, 1].tolist() == [10, 11, 12]


def test_resize_bilinear_keeps_constant_color_up_and_down():
    image = np.full((7, 10, 3), 200, dtype=np.uint8)
    assert np.allclose(resize_bilinear(image, 25, 13), 200)
    big = np.full((400, 400, 3), 50, dtype=np.uint8)
    small = resize_bilinear(big, 100, 90)
    assert small.shape == (90, 100, 3) and np.allclose(small, 50)


def test_label_components_joins_diagonal_pixels_and_separates_blobs():
    mask = np.zeros((6, 8), dtype=bool)
    mask[0, 0] = mask[1, 1] = True          # 대각선은 같은 요소 (8연결)
    mask[3:5, 4:7] = True                   # 떨어진 사각형
    components = sorted((x0, y0, x1, y1) for x0, y0, x1, y1, _ in label_components(mask))
    assert components == [(0, 0, 1, 1), (4, 3, 6, 4)]


def test_expand_box_matches_db_distance():
    # 10×2 상자: 넓이 20, 둘레 24 → 20 × 1.5 / 24 = 1.25
    assert expand_box(0, 0, 9, 1) == pytest.approx((-1.25, -1.25, 11.25, 3.25))


def test_ctc_decode_collapses_repeats_and_blanks():
    charset = ["가", "나", " "]
    probs = np.zeros((6, 4), dtype=np.float32)
    for step, index in enumerate([1, 1, 0, 1, 2, 3]):
        probs[step, index] = 0.9
    text, score = ctc_decode(probs, charset)
    assert text == "가가나 "
    assert score == pytest.approx(0.9)


def render(lines, pixel_size, width=900):
    """Qt로 그린 합성 문서. '|'로 나눈 칸은 170px 간격의 열이 된다."""
    font = QFont("Malgun Gothic")
    font.setPixelSize(pixel_size)
    image = QImage(width, (pixel_size + 12) * len(lines) + 20, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    y = 10 + pixel_size
    for line in lines:
        for column, cell in enumerate(line.split("|")):
            painter.drawText(10 + column * 170, y, cell)
        y += pixel_size + 12
    painter.end()
    return rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))


@pytest.fixture(scope="module")
def ocr():
    return OcrEngine()


@pytest.mark.parametrize("pixel_size", [13, 16])
def test_reads_korean_sentence_and_table_cells(qapp, ocr, pixel_size):
    image = render(["환경 점검 결과 알림", "구분|점검 사업장|위반", "대전|42|3"], pixel_size)
    found = [item.text for item in ocr.recognize(image)]
    for expected in ("환경 점검 결과 알림", "구분", "점검 사업장", "위반", "대전", "42", "3"):
        assert expected in found, (expected, found)


def test_boxes_are_in_original_image_coordinates(qapp, ocr):
    image = render(["구분|점검 사업장|위반", "대전|42|3"], 16)
    height, width = image.shape[:2]
    boxes = ocr.recognize(image)
    assert boxes
    for item in boxes:
        assert 0 <= item.x and item.x + item.w <= width and 0 <= item.y and item.y + item.h <= height
    assert next(b for b in boxes if b.text == "대전").x < 170


def test_large_image_is_downscaled_and_mapped_back(qapp, ocr):
    font = QFont("Malgun Gothic")
    font.setPixelSize(80)
    image = QImage(5200, 400, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    painter.drawText(4000, 200, "환경 점검")
    painter.end()
    boxes = ocr.recognize(rgb_from_buffer(5200, 400, image.bytesPerLine(), bytes(image.constBits())))
    target = next(b for b in boxes if "환경" in b.text)
    assert 3900 < target.x < 4100


def test_blank_image_returns_no_boxes(ocr):
    assert ocr.recognize(np.full((100, 300, 3), 255, dtype=np.uint8)) == []


def test_cancel_raises_before_reading(qapp, ocr):
    image = render(["환경 점검 결과 알림"], 16)
    with pytest.raises(RecognitionCancelled):
        ocr.recognize(image, cancelled=lambda: True)


def test_engine_refuses_tampered_models(tmp_path):
    copy = tmp_path / "models"
    shutil.copytree(MODEL_DIR, copy)
    with open(copy / "rec.onnx", "r+b") as stream:
        stream.seek(-1, 2)
        last = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([last[0] ^ 0xFF]))
    with pytest.raises(ModelIntegrityError):
        OcrEngine(copy)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_engine.py -v`
Expected: FAIL. `ModuleNotFoundError: No module named 'screen_text.engine'`

- [ ] **Step 3: 구현한다**

`screen_text/engine.py`:

```python
"""PP-OCR 위치 모델과 한국어 인식 모델로 글자 상자를 읽는다.

Qt를 import하지 않는다. numpy와 onnxruntime만 쓰며, MANIFEST.json의 크기와
SHA-256을 확인한 번들 모델만 불러온다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from app_paths import resource_root
from screen_text.layout import TextBox

DET_LIMIT = 960            # 위치 모델 입력의 긴 변 상한
DET_THRESHOLD = 0.3        # 글자 확률 이진화 기준
BOX_THRESHOLD = 0.6        # 상자 평균 확률 하한
UNCLIP_RATIO = 1.5         # DB 방식 상자 확장 비율
MIN_BOX_AREA = 6           # 확률 맵에서 이보다 작은 요소는 잡음
REC_HEIGHT = 48            # 한국어 인식 모델 입력 높이 (모델 입력 [N, 3, 48, W])
REC_BATCH = 6              # 폭이 비슷한 상자끼리 묶는 개수
MAX_SIDE = 4000            # 입력 이미지 긴 변 상한 (넘으면 줄인다)
UPSCALE = 1.0              # 작은 글씨 확대 배율 (Task 4 측정으로 확정)
CHARSET_SIZE = 11945
DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class ModelIntegrityError(RuntimeError):
    """번들 모델이 없거나 MANIFEST와 다르다. 이 상태에서는 인식을 시작하지 않는다."""


class RecognitionCancelled(Exception):
    """사용자 동작이나 수명 처리로 인식이 취소됐다."""


def model_dir() -> Path:
    return resource_root() / "screen_text" / "models"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_models(directory=None):
    """MANIFEST의 크기·SHA-256과 일치하는 모델 경로를 역할별로 돌려준다."""
    directory = Path(directory) if directory is not None else model_dir()
    try:
        with open(directory / "MANIFEST.json", encoding="utf-8") as stream:
            manifest = json.load(stream)
        files = {}
        for entry in manifest["files"]:
            path = directory / entry["name"]
            if path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
                raise ModelIntegrityError(f"모델 파일 불일치: {entry['name']}")
            files[entry["role"]] = path
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ModelIntegrityError("인식 모델을 확인하지 못했습니다") from error
    if set(files) != {"det", "rec", "dict"}:
        raise ModelIntegrityError("인식 모델 구성이 맞지 않습니다")
    return files


def load_charset(path):
    """사전 한 줄이 한 글자다. 모델의 마지막 클래스는 공백이다."""
    with open(path, encoding="utf-8", newline="") as stream:
        chars = [line.rstrip("\r\n") for line in stream]
    if len(chars) != CHARSET_SIZE:
        raise ModelIntegrityError("인식 사전 크기가 맞지 않습니다")
    return chars + [" "]


def rgb_from_buffer(width, height, bytes_per_line, data):
    """줄 끝 여백이 있는 RGB888 버퍼를 (높이, 너비, 3) 배열로 바꾼다."""
    raw = np.frombuffer(data, dtype=np.uint8)[: height * bytes_per_line]
    return raw.reshape(height, bytes_per_line)[:, : width * 3].reshape(height, width, 3).copy()


def resize_bilinear(image, width, height):
    """numpy 이중선형 크기 변경. 크게 줄일 때는 정수 배 평균으로 먼저 줄인다."""
    source = image.astype(np.float32)
    src_h, src_w = source.shape[:2]
    if (width, height) == (src_w, src_h):
        return source
    factor = int(min(src_w / width, src_h / height))
    if factor >= 2:
        cut_h, cut_w = src_h // factor * factor, src_w // factor * factor
        source = source[:cut_h, :cut_w].reshape(cut_h // factor, factor, cut_w // factor, factor, -1).mean(axis=(1, 3))
        src_h, src_w = source.shape[:2]
    ys = np.clip((np.arange(height, dtype=np.float32) + 0.5) * (src_h / height) - 0.5, 0, src_h - 1)
    xs = np.clip((np.arange(width, dtype=np.float32) + 0.5) * (src_w / width) - 0.5, 0, src_w - 1)
    y0, x0 = np.floor(ys).astype(np.int32), np.floor(xs).astype(np.int32)
    y1, x1 = np.minimum(y0 + 1, src_h - 1), np.minimum(x0 + 1, src_w - 1)
    wy, wx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = source[y0][:, x0] * (1 - wx) + source[y0][:, x1] * wx
    bottom = source[y1][:, x0] * (1 - wx) + source[y1][:, x1] * wx
    return top * (1 - wy) + bottom * wy


def label_components(mask):
    """행 단위 run을 8연결로 묶는다. 반환: [(x0, y0, x1, y1, [(y, xs, xe), ...])] (포함 좌표)."""
    parent, runs, previous = [], [], []

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for y in range(mask.shape[0]):
        row = mask[y]
        if not row.any():
            previous = []
            continue
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
        current = []
        for start, end in zip(edges[0::2].tolist(), (edges[1::2] - 1).tolist()):
            run_id = len(runs)
            runs.append((y, start, end))
            parent.append(run_id)
            current.append(run_id)
            for other in previous:
                _, other_start, other_end = runs[other]
                if other_start <= end + 1 and other_end >= start - 1:
                    a, b = find(run_id), find(other)
                    if a != b:
                        parent[a] = b
        previous = current
    groups = {}
    for run_id, run in enumerate(runs):
        groups.setdefault(find(run_id), []).append(run)
    return [
        (min(r[1] for r in members), min(r[0] for r in members),
         max(r[2] for r in members), max(r[0] for r in members), members)
        for members in groups.values()
    ]


def expand_box(x0, y0, x1, y1, ratio=UNCLIP_RATIO):
    """포함 좌표 사각형을 DB 방식 거리만큼 넓힌 반열림 좌표를 돌려준다."""
    width, height = x1 - x0 + 1, y1 - y0 + 1
    distance = width * height * ratio / (2 * (width + height))
    return x0 - distance, y0 - distance, x1 + 1 + distance, y1 + 1 + distance


def ctc_decode(probs, charset):
    """(timestep, class) 확률에서 반복·blank(0)를 지운 글자와 평균 확신도."""
    indices = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    text, scores, previous = [], [], 0
    for step, index in enumerate(indices.tolist()):
        if index != 0 and index != previous:
            text.append(charset[index - 1])
            scores.append(float(confidence[step]))
        previous = index
    return "".join(text), (float(np.mean(scores)) if scores else 0.0)


class OcrEngine:
    """번들 모델 세션을 들고 RGB 배열의 글자 상자를 읽는다. 세션 생성은 무겁다."""

    def __init__(self, directory=None, threads=None):
        import onnxruntime as ort  # 처음 인식할 때만 불러온다

        files = verify_models(directory)
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads or min(4, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
        self._det = ort.InferenceSession(str(files["det"]), options, providers=providers)
        self._rec = ort.InferenceSession(str(files["rec"]), options, providers=providers)
        self._charset = load_charset(files["dict"])
        if self._rec.get_outputs()[0].shape[-1] != len(self._charset) + 1:
            raise ModelIntegrityError("인식 모델과 사전이 맞지 않습니다")

    def recognize(self, image, cancelled=lambda: False):
        """RGB 배열(H, W, 3)의 글자 상자를 원본 좌표로 돌려준다. 취소되면 RecognitionCancelled."""
        height, width = image.shape[:2]
        scale = min(UPSCALE, MAX_SIDE / max(width, height))
        work = image
        if scale != 1.0:
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            work = np.clip(resize_bilinear(image, *size), 0, 255).astype(np.uint8)
        boxes = self._detect(work)
        if cancelled():
            raise RecognitionCancelled
        results = self._read(work, boxes, cancelled)
        out = []
        for (x0, y0, x1, y1), (text, score) in zip(boxes, results):
            text = text.strip()
            if text:
                out.append(TextBox(round(x0 / scale), round(y0 / scale),
                                   max(1, round((x1 - x0) / scale)), max(1, round((y1 - y0) / scale)),
                                   text, score))
        return out

    def _detect(self, image):
        height, width = image.shape[:2]
        ratio = min(1.0, DET_LIMIT / max(height, width))
        new_h = max(32, int(round(height * ratio / 32)) * 32)
        new_w = max(32, int(round(width * ratio / 32)) * 32)
        tensor = resize_bilinear(image, new_w, new_h)[:, :, ::-1] / 255.0  # 모델은 BGR 순서로 학습됐다
        tensor = ((tensor - DET_MEAN) / DET_STD).transpose(2, 0, 1)[None].astype(np.float32)
        prob = self._det.run(None, {"x": tensor})[0][0, 0]
        scale_x, scale_y = width / new_w, height / new_h
        boxes = []
        for x0, y0, x1, y1, runs in label_components(prob > DET_THRESHOLD):
            if (x1 - x0 + 1) * (y1 - y0 + 1) < MIN_BOX_AREA:
                continue
            score = float(np.mean(np.concatenate([prob[y, a:b + 1] for y, a, b in runs])))
            if score < BOX_THRESHOLD:
                continue
            fx0, fy0, fx1, fy1 = expand_box(x0, y0, x1, y1)
            box = (max(0, int(fx0 * scale_x)), max(0, int(fy0 * scale_y)),
                   min(width, int(round(fx1 * scale_x))), min(height, int(round(fy1 * scale_y))))
            if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
                boxes.append(box)
        return boxes

    def _read(self, image, boxes, cancelled):
        crops = []
        for x0, y0, x1, y1 in boxes:
            crop = image[y0:y1, x0:x1]
            crop_width = max(8, int(np.ceil(REC_HEIGHT * crop.shape[1] / max(1, crop.shape[0]))))
            crops.append(resize_bilinear(crop, crop_width, REC_HEIGHT)[:, :, ::-1])
        results = [("", 0.0)] * len(crops)
        order = sorted(range(len(crops)), key=lambda i: crops[i].shape[1])
        for start in range(0, len(order), REC_BATCH):
            if cancelled():
                raise RecognitionCancelled
            ids = order[start:start + REC_BATCH]
            widest = max(crops[i].shape[1] for i in ids)
            batch = np.zeros((len(ids), 3, REC_HEIGHT, widest), dtype=np.float32)
            for slot, i in enumerate(ids):
                batch[slot, :, :, : crops[i].shape[1]] = ((crops[i] / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
            probs = self._rec.run(None, {"x": batch})[0]
            for slot, i in enumerate(ids):
                steps = max(1, int(np.ceil(probs.shape[1] * crops[i].shape[1] / widest)))
                results[i] = ctc_decode(probs[slot, :steps], self._charset)
        return results
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_engine.py -v`
Expected: PASS 16개. `test_reads_korean_sentence_and_table_cells`가 실패하면 실제 `found`를 작업 기록에 적고 멈춘다. 기준을 낮추지 않는다.

- [ ] **Step 5: 하네스로 기록하고 커밋한다**

Run: `.venv/Scripts/python.exe tools/verify.py quick --tests tests/test_screen_text_layout.py tests/test_screen_text_engine.py`
Expected: 통과. 실행 ID를 작업 기록에 적는다.

```bash
git add screen_text/engine.py tests/test_screen_text_engine.py docs/work/2026-10-08-screen-text-capture.md
git commit -m "feat: 화면 글자 따기 소형 OCR 엔진 (numpy·onnxruntime)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 측정 게이트 (첫날 실험, 진행 여부 결정)

실험 스크립트와 결과는 `output/` 아래에만 둔다(git 추적 안 함). 제품 코드는 Task 3 엔진을 그대로 import한다.

**Files:**
- Create: `output/spike-screen-text-20261008/make_samples.py`, `output/spike-screen-text-20261008/winocr.ps1`, `output/spike-screen-text-20261008/measure.py`, `output/spike-screen-text-20261008/report.md`
- Modify (결과에 따라): `screen_text/layout.py` `UNSURE_SCORE`, `screen_text/engine.py` `UPSCALE`, `docs/work/2026-10-08-screen-text-capture.md`

**Interfaces:**
- Consumes: `OcrEngine`, `rgb_from_buffer` (Task 3)
- Produces: `report.md`의 결정값 세 가지(UPSCALE, UNSURE_SCORE, 진행 여부)

- [ ] **Step 1: 표본 이미지 생성 스크립트를 쓴다**

`output/spike-screen-text-20261008/make_samples.py`:

```python
"""합성 표본 이미지와 정답 텍스트를 만든다 (실제 문서 사용 금지)."""
import json
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

HERE = Path(__file__).resolve().parent
SAMPLES = {
    "body": ["2. 위 호와 관련하여 3분기 점검 결과를 아래와 같이 알려드립니다.",
             "가. 대상: 폐수배출시설 176개소", "나. 기간: 2026. 7. 1. ~ 9. 30."],
    "ruled_table": ["구분|점검 사업장|위반|조치 완료", "대전|42|3|3", "세종|18|1|1", "충남|65|7|6", "계|176|15|14"],
    "plain_table": ["항목|BOD(mg/L)|SS(mg/L)", "1월|2.4|5.1", "2월|3.1|4.8"],
    "small": ["붙임 1. 점검 결과 세부 내역 1부.", "관련: 수질관리과-1234(2026. 7. 1.)"],
}
SIZES = {"100": 13, "125": 16, "150": 20, "small9pt": 12}


def render(lines, pixel_size, ruled):
    font = QFont("Malgun Gothic")
    font.setPixelSize(pixel_size)
    line_height = pixel_size + 14
    image = QImage(1000, line_height * len(lines) + 24, QImage.Format_RGB888)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    for row, line in enumerate(lines):
        top = 12 + row * line_height
        for column, cell in enumerate(line.split("|")):
            painter.drawText(16 + column * 200, top + pixel_size, cell)
            if ruled and "|" in line:
                painter.drawRect(8 + column * 200, top - 4, 200, line_height)
    painter.end()
    return image


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    truth = {}
    for name, lines in SAMPLES.items():
        for scale, size in SIZES.items():
            path = HERE / "samples" / f"{name}_{scale}.png"
            path.parent.mkdir(exist_ok=True)
            render(lines, size, name == "ruled_table").save(str(path))
            truth[path.name] = "\n".join(line.replace("|", " ") for line in lines)
    with open(HERE / "samples" / "truth.json", "w", encoding="utf-8") as stream:
        json.dump(truth, stream, ensure_ascii=False, indent=1)
    print(len(truth), "samples")
```

Run: `.venv/Scripts/python.exe output/spike-screen-text-20261008/make_samples.py`
Expected: `16 samples`

- [ ] **Step 2: Windows 내장 OCR 비교 스크립트를 쓴다**

`output/spike-screen-text-20261008/winocr.ps1` (Windows PowerShell 5.1 전용):

```powershell
param([string]$Path)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) { $t = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $Path).Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$stream.Dispose()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$result.Lines | ForEach-Object { $_.Text }
```

- [ ] **Step 3: 측정 스크립트를 쓴다**

`output/spike-screen-text-20261008/measure.py`:

```python
"""소형 모델과 Windows 내장 OCR의 글자 정확도·시간을 같은 표본으로 비교한다."""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402
from screen_text.engine import OcrEngine, rgb_from_buffer  # noqa: E402
from screen_text.layout import build_blocks, to_plain  # noqa: E402


def distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def accuracy(truth, text):
    t, h = "".join(truth.split()), "".join(text.split())  # 공백 차이는 따로 본다
    return max(0.0, 1 - distance(t, h) / max(1, len(t)))


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    with open(HERE / "samples" / "truth.json", encoding="utf-8") as stream:
        truth = json.load(stream)
    started = time.perf_counter()
    engine = OcrEngine()
    load_seconds = time.perf_counter() - started
    rows = []
    for name, expected in truth.items():
        image = QImage(str(HERE / "samples" / name)).convertToFormat(QImage.Format_RGB888)
        rgb = rgb_from_buffer(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits()))
        t0 = time.perf_counter()
        boxes = engine.recognize(rgb)
        seconds = time.perf_counter() - t0
        ours = to_plain(build_blocks(boxes))
        low = min((b.score for b in boxes), default=1.0)
        windows = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "winocr.ps1"),
             "-Path", str(HERE / "samples" / name)],
            capture_output=True, encoding="utf-8", errors="replace", shell=False, check=False,
        ).stdout
        rows.append((name, accuracy(expected, ours), accuracy(expected, windows), seconds, low, ours, windows))
    with open(HERE / "report.md", "w", encoding="utf-8") as stream:
        stream.write(f"# 화면 글자 따기 측정\n\n모델 로딩 {load_seconds:.2f}초\n\n")
        stream.write("| 표본 | 소형 모델 정확도 | Windows OCR 정확도 | 소형 모델 시간(초) | 최저 점수 |\n|---|---|---|---|---|\n")
        for name, ours, win, seconds, low, _, _ in rows:
            stream.write(f"| {name} | {ours:.3f} | {win:.3f} | {seconds:.2f} | {low:.2f} |\n")
        mean_ours = sum(r[1] for r in rows) / len(rows)
        mean_win = sum(r[2] for r in rows) / len(rows)
        stream.write(f"\n평균: 소형 모델 {mean_ours:.3f}, Windows OCR {mean_win:.3f}, 최대 시간 {max(r[3] for r in rows):.2f}초\n\n")
        for name, _, _, _, _, ours, win in rows:
            stream.write(f"## {name}\n\n소형 모델:\n```\n{ours}\n```\nWindows OCR:\n```\n{win}\n```\n\n")
    print(open(HERE / "report.md", encoding="utf-8").read().split("## ")[0])
```

- [ ] **Step 4: 측정을 실행한다**

Run: `.venv/Scripts/python.exe output/spike-screen-text-20261008/measure.py`
Expected: 표본 16개의 표와 평균이 출력되고 `report.md`가 생긴다.

- [ ] **Step 5: 결정값을 정하고 기록한다**

`report.md` 끝에 아래 "결정" 절을 실제 값으로 쓰고, 같은 내용을 작업 기록 "결정과 진행"에 옮긴다.
- **진행 기준**: 소형 모델 평균 정확도가 Windows OCR 평균 − 0.02 이상이고, 표본 최대 시간이 2.0초 이하
- **UPSCALE**
  - `small9pt` 표본 정확도가 `100` 표본보다 0.05 이상 낮으면 `screen_text/engine.py`의 `UPSCALE`을 2.0으로 바꾸고 Step 4를 다시 돌려 개선을 확인한다.
  - 그렇지 않으면 1.0을 유지한다.
- **UNSURE_SCORE**
  - 정답과 일치한 상자의 최저 점수보다 낮고, 오인식 상자의 점수보다 높은 값으로 정한다. 기본은 0.80이다.
  - 오인식 상자가 없으면 0.80을 유지한다.
- 값을 바꿨으면 Task 2·3 테스트를 다시 돌린다.
  Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_layout.py tests/test_screen_text_engine.py -q`

- [ ] **Step 6: 사용자에게 보고하고 진행 승인을 받는다 (게이트)**

평균 정확도 두 값, 최대 시간, 결정값, 기준 충족 여부를 3~5줄로 보고한다. **기준 미달이면 Task 5로 넘어가지 말고** 대안(큰 인식 모델, Windows 내장 OCR 전환)을 제시해 사용자 결정을 받는다.

- [ ] **Step 7: 바뀐 값만 커밋한다**

값이 바뀌었을 때만:

```bash
git add screen_text/engine.py screen_text/layout.py docs/work/2026-10-08-screen-text-capture.md
git commit -m "feat: 화면 글자 따기 측정 게이트 결과로 확대·불확실 기준 확정

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

값이 그대로면 작업 기록만 커밋한다(`docs: 화면 글자 따기 측정 게이트 기록`).

---

### Task 5: 선택형 미니앱 공용 연결부

**Files:**
- Create: `optional_mini_apps.py`
- Modify: `ui_mini_apps.py` (`MiniAppSpec`, `pocket_body_height`, `MiniAppsPocket.__init__`)
- Modify: `ui_main.py:415` (import), `:1219` (상태), `:1325-1328`, `:1564-1567`, `:3252`, `:3306`, `:3386`, `:3449`, `:3567-3570`, `:3659-3665`, `:3993-3994`, 그리고 `_discard_document_converter` 다음에 새 메서드
- Modify: `tests/test_ui_mini_apps.py:23-31` (기존 기대값 고정), `tests/test_ui_document_converter.py` (주머니 앱 개수 고정)
- Test: `tests/test_optional_mini_apps.py`

설계와 다른 점: 설계는 `MiniAppSpec`을 `optional_mini_apps.py`에 두었지만 **`ui_mini_apps.py`에 둔다.** 등록부가 `screen_text`를 import하고 `screen_text`가 다시 `MiniAppSpec`을 import하면 순환 import가 되기 때문이다. 등록부는 목록만 가진다.

**Interfaces:**
- Produces:
  - `ui_mini_apps.MiniAppSpec(app_id: str, title: str, accessible_name: str, description: str, icon_path: Path, create_window: Callable[[QWidget], QWidget])` (frozen dataclass)
  - `ui_mini_apps.pocket_body_height(app_count: int) -> int` (= `60 + 110 × min(3, max(2, ceil(n/2)))`)
  - `MiniAppsPocket(parent=None, optional_apps=())`, 신호 `optional_app_requested(str)`, 속성 `optional_cards: dict[str, MiniAppTile]`
  - `optional_mini_apps.OPTIONAL_MINI_APPS: tuple[MiniAppSpec, ...]` (이번 작업은 빈 튜플)
  - 선택형 앱 창 규약: `show_near(anchor, available)`, `hide_owned_popups()`, `cancel_work()`, `fit_to_screen(available=None)`, `shutdown()`. 그리고 QWidget의 `setEnabled`·`hide`·`deleteLater`
  - `MainCalendarWindow._optional_windows: dict[str, QWidget]`
  - `MainCalendarWindow._open_optional_mini_app(app_id)`, `_hide_optional_mini_apps()`, `_disable_optional_mini_apps()`, `_fit_optional_mini_apps()`, `_discard_optional_mini_apps()`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_optional_mini_apps.py`:

```python
"""선택형 미니앱 공용 연결부: 등록부·주머니 높이·메인 창 수명 지점 (가짜 앱 사용)."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from qfluentwidgets.common.font import fontFamilies, setFontFamilies
from shiboken6 import isValid

from app_fonts import apply_app_font
from app_paths import resource_root
import database as db
import optional_mini_apps
import ui_main
from ui_main import MainCalendarWindow
from ui_mini_apps import MiniAppSpec, pocket_body_height


class FakeOptionalWindow(QWidget):
    instances = []

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool)
        self.calls = []
        FakeOptionalWindow.instances.append(self)

    def show_near(self, anchor, available):
        self.calls.append("show_near")
        self.show()

    def hide_owned_popups(self):
        self.calls.append("hide_owned_popups")

    def cancel_work(self):
        self.calls.append("cancel_work")

    def fit_to_screen(self, available=None):
        self.calls.append("fit_to_screen")

    def shutdown(self):
        self.calls.append("shutdown")


FAKE = MiniAppSpec(
    app_id="fake", title="가짜\n앱", accessible_name="가짜 앱 실행", description="공용 연결부 검사용",
    icon_path=resource_root() / "resources" / "icons" / "mini_apps" / "upcoming.svg",
    create_window=FakeOptionalWindow,
)


@pytest.fixture(autouse=True)
def isolated(app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", (FAKE,))
    FakeOptionalWindow.instances.clear()
    yield
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


def window(qtbot):
    db.save_setting(db.SETTING_CALENDAR_SCALE, "compact")
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    win.activateWindow()
    assert QTest.qWaitForWindowExposed(win)
    return win


def open_pocket(qtbot, win):
    qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: win._mini_apps_popup is not None and win._mini_apps_popup.isVisible())
    return win._mini_apps_popup


def open_fake(qtbot, win):
    popup = open_pocket(qtbot, win)
    qtbot.mouseClick(popup.optional_cards["fake"], Qt.LeftButton)
    qtbot.waitUntil(lambda: "fake" in win._optional_windows)
    return win._optional_windows["fake"]


def test_pocket_body_height_by_app_count():
    assert [pocket_body_height(n) for n in (1, 4, 5, 6, 7, 9)] == [280, 280, 390, 390, 390, 390]


def test_pocket_appends_optional_tile_and_grows_to_three_rows(qtbot):
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    assert popup.card.size() == QSize(252, 390)
    assert popup.size() == QSize(300, 438)
    assert popup.apps_grid.count() == 5
    tile = popup.optional_cards["fake"]
    assert popup.apps_grid.itemAtPosition(2, 0).widget() is tile
    assert tile.text() == "가짜\n앱" and tile.accessibleName() == "가짜 앱 실행"
    assert not tile.icon().isNull()
    assert popup.count_label.text() == "5개"
    assert popup.apps_scroll.verticalScrollBar().maximum() == 0
    win._close_mini_apps()


def test_empty_registry_keeps_original_pocket(qtbot, monkeypatch):
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", ())
    win = window(qtbot)
    popup = open_pocket(qtbot, win)
    assert popup.card.size() == QSize(252, 280)
    assert popup.apps_grid.count() == 4 and popup.optional_cards == {}
    win._close_mini_apps()


def test_tile_opens_and_reuses_single_window(qtbot):
    win = window(qtbot)
    first = open_fake(qtbot, win)
    assert win._mini_apps_popup is None
    assert first.isVisible() and first.isEnabled()
    second = open_fake(qtbot, win)
    assert second is first and len(FakeOptionalWindow.instances) == 1
    assert first.calls.count("show_near") == 2


def test_locked_main_does_not_open_optional_app(qtbot):
    win = window(qtbot)
    win._lock()
    win._open_optional_mini_app("fake")
    assert win._optional_windows == {}
    win._unlock()


@pytest.mark.parametrize("action", ["lock", "tray", "sidebar", "scale", "reset_before"])
def test_hiding_lifecycle_cancels_and_hides(qtbot, action):
    win = window(qtbot)
    fake = open_fake(qtbot, win)
    fake.calls.clear()
    actions = {
        "lock": win._lock, "tray": win._minimize_to_tray,
        "sidebar": lambda: (db.save_setting(db.SETTING_SHOW_SIDEBAR, "0"), win._apply_sidebar_visibility()),
        # 크기 적용은 사이드바가 사라질 때만 미니앱을 숨긴다(기존 4개 앱과 같은 규칙).
        "scale": lambda: (db.save_setting(db.SETTING_SHOW_SIDEBAR, "0"), win._apply_calendar_scale()),
        "reset_before": win._discard_data_widgets,
    }
    actions[action]()
    assert fake.calls[:2] == ["cancel_work", "hide_owned_popups"]
    assert not fake.isVisible()
    assert fake.isEnabled() == (action != "lock")
    if action == "lock":
        win._unlock()


def test_screen_change_closes_popups_and_fits_without_cancelling(qtbot):
    win = window(qtbot)
    fake = open_fake(qtbot, win)
    fake.calls.clear()
    win._on_screen_changed()
    assert fake.calls == ["hide_owned_popups", "fit_to_screen"]


@pytest.mark.parametrize("route", ["quit", "reset_success"])
def test_quit_and_reset_success_shut_down_and_delete(qtbot, route):
    win = window(qtbot)
    fake = open_fake(qtbot, win)
    if route == "quit":
        assert win.prepare_for_quit()
    else:
        win._on_settings()
        win._settings_window.reset_succeeded.emit()
    assert "shutdown" in fake.calls
    assert win._optional_windows == {}
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not isValid(fake)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_optional_mini_apps.py -v`
Expected: FAIL. `ModuleNotFoundError: No module named 'optional_mini_apps'`

- [ ] **Step 3: 등록부를 만든다**

`optional_mini_apps.py`:

```python
"""걷어낼 수 있는 선택형 미니앱 등록부.

앱을 빼려면 그 앱의 폴더와 아래 등록 줄을 지운다(절차: docs/SCREEN_TEXT.md
"걷어내기"). 기존 미니앱 4개는 여기에 두지 않는다. 메인 창은 이 목록을
주머니 타일과 9개 수명 지점에 공용으로 연결한다.
"""

OPTIONAL_MINI_APPS = ()
```

- [ ] **Step 4: 주머니를 바꾼다**

`ui_mini_apps.py` import와 상수 부분:

```python
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
...
TILE_SLOTS = 4
MAX_VISIBLE_ROWS = 3


@dataclass(frozen=True)
class MiniAppSpec:
    """걷어낼 수 있는 선택형 미니앱 정보. 창은 show_near·hide_owned_popups·cancel_work·
    fit_to_screen·shutdown을 제공한다 (optional_mini_apps.py 참고)."""
    app_id: str
    title: str
    accessible_name: str
    description: str
    icon_path: Path
    create_window: Callable


def pocket_body_height(app_count: int) -> int:
    """머리 48 + 위 6 + 줄×100 + 사이×10 + 아래 14 + 테두리 2. 2줄 280, 3줄 390."""
    rows = min(MAX_VISIBLE_ROWS, max(2, math.ceil(app_count / 2)))
    return 60 + 110 * rows
```

`MiniAppsPocket`:
- 클래스 신호에 `optional_app_requested = Signal(str)`를 더한다.
- 생성자를 `def __init__(self, parent=None, optional_apps=()):`로 바꾼다.
- `self.resize(...)` 줄을 아래로 바꾼다.

```python
        self.optional_cards = {}
        self.resize(POCKET_WIDTH + 2 * SHADOW_MARGIN,
                    pocket_body_height(TILE_SLOTS + len(optional_apps)) + 2 * SHADOW_MARGIN)
```

`self.document_card.setAccessibleName("문서 형식 변환 실행")` 다음, 준비 중 칸 `for` 앞에 넣는다:

```python
        for spec in optional_apps:
            card = self.add_app(
                spec.title, spec.app_id, spec.description,
                lambda checked=False, app_id=spec.app_id: self.optional_app_requested.emit(app_id),
                icon=QIcon(str(spec.icon_path)),
            )
            card.setObjectName(f"optionalMiniApp_{spec.app_id}")
            card.setAccessibleName(spec.accessible_name)
            self.optional_cards[spec.app_id] = card
```

`tiles_layout.setContentsMargins(16, 6, 8, 14)` 위 주석의 `48+6+100+10+100+14+2=280`을 아래로 바꾼다.

```python
        # 높이 계산은 pocket_body_height()를 따른다(2줄 280, 3줄 390).
```

- [ ] **Step 5: 메인 창 공용 연결부를 넣는다**

`ui_main.py`:

1. import (`from ui_mini_apps import ...` 줄 바로 위):
```python
import optional_mini_apps
```
2. 상태 (`self._document_converter = None` 다음):
```python
        self._optional_windows = {}
```
3. `_apply_sidebar_visibility`와 `_apply_calendar_scale`의 `self._hide_document_converter()` 다음에 각각:
```python
            self._hide_optional_mini_apps()
```
4. `_on_settings`의 `reset_succeeded.connect(self._discard_document_converter)` 다음:
```python
            self._settings_window.reset_succeeded.connect(self._discard_optional_mini_apps)
```
5. `_discard_data_widgets`와 `_minimize_to_tray`의 `self._hide_document_converter()` 다음에 각각:
```python
        self._hide_optional_mini_apps()
```
6. `prepare_for_quit`의 `self._discard_document_converter()` 다음:
```python
            self._discard_optional_mini_apps()
```
7. `_on_screen_changed`의 `self._document_converter.fit_to_screen()` 블록 다음:
```python
        self._fit_optional_mini_apps()
```
8. `_toggle_mini_apps`에서 생성과 연결:
```python
        popup = MiniAppsPocket(self, optional_apps=optional_mini_apps.OPTIONAL_MINI_APPS)
        ...
        popup.document_converter_requested.connect(self._open_document_converter)
        popup.optional_app_requested.connect(self._open_optional_mini_app)
```
9. `_lock`의 `self._hide_document_converter()` 다음에 `self._hide_optional_mini_apps()`, `self._document_converter.setEnabled(False)` 블록 다음에:
```python
        self._disable_optional_mini_apps()
```
10. `_discard_document_converter` 메서드 바로 다음:

```python
    # ─── 선택형 미니앱 (optional_mini_apps 등록부, 걷어낼 수 있음) ───
    def _open_optional_mini_app(self, app_id: str) -> None:
        if not self._mini_apps_allowed() or not self._save_schedule_edit():
            return
        spec = next((s for s in optional_mini_apps.OPTIONAL_MINI_APPS if s.app_id == app_id), None)
        if spec is None:
            return
        self._close_mini_apps()
        self._close_schedule_emoji_popups()
        win = self._optional_windows.get(app_id)
        if win is None:
            win = spec.create_window(self)
            self._optional_windows[app_id] = win
        button = self.sidebar.mini_apps_button
        anchor = button.rect().translated(button.mapToGlobal(QPoint()))
        screen = QApplication.screenAt(anchor.center()) or self.screen()
        win.setEnabled(True)
        win.show_near(anchor, screen.availableGeometry())

    def _hide_optional_mini_apps(self) -> None:
        for win in self._optional_windows.values():
            win.cancel_work()
            win.hide_owned_popups()
            win.hide()

    def _disable_optional_mini_apps(self) -> None:
        for win in self._optional_windows.values():
            win.setEnabled(False)

    def _fit_optional_mini_apps(self) -> None:
        for win in self._optional_windows.values():
            win.hide_owned_popups()
            win.fit_to_screen()

    def _discard_optional_mini_apps(self) -> None:
        windows, self._optional_windows = self._optional_windows, {}
        for win in windows.values():
            win.shutdown()
            win.hide_owned_popups()
            win.hide()
            win.deleteLater()
```

- [ ] **Step 6: 기존 주머니 테스트가 등록 앱에 영향받지 않게 고정한다**

`tests/test_ui_mini_apps.py`의 `import ui_main` 다음 줄에 `import optional_mini_apps`를 넣는다. `isolated_ui` 픽스처의 `monkeypatch.setattr(ui_main.InfoBar, ...)` 다음 줄에 아래를 넣는다.

```python
    # 기존 4개 앱의 주머니 계약을 검사한다. 선택형 앱은 test_optional_mini_apps.py가 맡는다.
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", ())
```

`tests/test_ui_document_converter.py`
- 상단 `import ui_main` 다음 줄에 `import optional_mini_apps`를 넣는다.
- `test_main_lifecycle_owns_fourth_app_and_preserves_data(qtbot, action)`의 인자를 `(qtbot, action, monkeypatch)`로 바꾼다.
- 그 함수의 첫 줄에 아래를 넣는다(133행 `pocket.count_label.text() == "4개"`를 지키기 위함).

```python
    monkeypatch.setattr(optional_mini_apps, "OPTIONAL_MINI_APPS", ())
```

- [ ] **Step 7: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_optional_mini_apps.py -v`
Expected: PASS 13개
Run: `.venv/Scripts/python.exe tools/verify.py quick --tests tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py tests/test_ui_document_converter.py tests/test_ui_data_lifecycle.py tests/test_money_notation_integration.py tests/test_date_time_integration.py`
Expected: 통과. 실행 ID를 작업 기록에 적는다.

- [ ] **Step 8: 커밋한다**

```bash
git add optional_mini_apps.py ui_mini_apps.py ui_main.py tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py tests/test_ui_document_converter.py docs/work/2026-10-08-screen-text-capture.md
git commit -m "feat: 걷어낼 수 있는 선택형 미니앱 공용 연결부와 주머니 3줄 확장

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 화면 멈춤·영역 선택 (`screen_text/capture.py`)

**Files:**
- Create: `screen_text/capture.py`
- Test: `tests/test_screen_text_capture.py`

**Interfaces:**
- Produces:
  - `grab_screens() -> list[tuple[QRect, QPixmap]]` (논리 좌표 화면 영역, device pixel ratio가 있는 pixmap)
  - `is_blocked(image: QImage) -> bool`
  - `crop_physical(pixmap: QPixmap, rect: QRect) -> QImage` (Format_RGB888)
  - `CaptureOverlay(geometry, pixmap)`: 신호 `selected(QRect)`, `cancelled()`, 속성 `pixmap`
  - `ScreenCapture(parent=None, grab=grab_screens)`: 신호 `captured(QImage)`, `cancelled()`, `blocked()`, 메서드 `start()`, `cancel(notify=True)`, `is_active() -> bool`, 속성 `overlays: list[CaptureOverlay]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_screen_text_capture.py`:

```python
"""화면 글자 따기 화면 멈춤·영역 선택 (가짜 스크린샷만 사용, 실제 화면을 찍지 않는다)."""
import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from screen_text.capture import ScreenCapture, crop_physical, is_blocked


def fake_shot(geometry, ratio=1.0, fill="white"):
    """논리 (40, 20, 30×10) 위치에 검은 사각형이 있는 화면."""
    pixmap = QPixmap(round(geometry.width() * ratio), round(geometry.height() * ratio))
    pixmap.fill(QColor(fill))
    painter = QPainter(pixmap)
    painter.fillRect(QRect(round(40 * ratio), round(20 * ratio), round(30 * ratio), round(10 * ratio)), QColor("black"))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return geometry, pixmap


def drag(qtbot, overlay, start, end):
    qtbot.mousePress(overlay, Qt.LeftButton, pos=start)
    qtbot.mouseMove(overlay, end)
    qtbot.mouseRelease(overlay, Qt.LeftButton, pos=end)


def started(qtbot, shots):
    capture = ScreenCapture(grab=lambda: shots)
    got = {"captured": [], "cancelled": 0, "blocked": 0}
    capture.captured.connect(got["captured"].append)
    capture.cancelled.connect(lambda: got.__setitem__("cancelled", got["cancelled"] + 1))
    capture.blocked.connect(lambda: got.__setitem__("blocked", got["blocked"] + 1))
    capture.start()
    for overlay in capture.overlays:
        qtbot.waitExposed(overlay)
    return capture, got


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5])
def test_drag_selection_crops_physical_pixels_on_scaled_screen(qtbot, ratio):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300), ratio)])
    drag(qtbot, capture.overlays[0], QPoint(40, 20), QPoint(69, 29))
    image = got["captured"][0]
    assert image.size() == QSize(round(30 * ratio), round(10 * ratio))
    assert image.format() == QImage.Format_RGB888
    assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("black")
    assert not capture.is_active()


def test_drag_past_screen_edge_is_clipped_to_that_screen(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    drag(qtbot, capture.overlays[0], QPoint(390, 290), QPoint(500, 420))
    assert got["captured"][0].size() == QSize(10, 10)


def test_crop_physical_rounds_fractional_ratio_and_clips():
    _, pixmap = fake_shot(QRect(0, 0, 100, 80), 1.25)
    assert crop_physical(pixmap, QRect(10, 10, 9, 7)).size() == QSize(11, 9)
    # (112, 88, 62, 62)를 125×100 pixmap 경계로 자른다 (Python round는 .5를 짝수로)
    assert crop_physical(pixmap, QRect(90, 70, 50, 50)).size() == QSize(13, 12)


def test_second_screen_selection_uses_its_own_pixmap(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 200, 150), 1.0),
                                   fake_shot(QRect(0, 0, 200, 150), 1.5, fill="#DDDDDD")])
    assert len(capture.overlays) == 2
    drag(qtbot, capture.overlays[1], QPoint(0, 0), QPoint(19, 9))
    assert got["captured"][0].size() == QSize(30, 15)
    assert got["captured"][0].pixelColor(1, 1) == QColor("#DDDDDD")
    assert not capture.overlays


def test_small_drag_is_ignored_then_escape_cancels_and_discards(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    overlay = capture.overlays[0]
    drag(qtbot, overlay, QPoint(10, 10), QPoint(14, 13))
    assert got["captured"] == [] and capture.is_active()
    qtbot.keyClick(overlay, Qt.Key_Escape)
    assert got["cancelled"] == 1
    assert overlay.pixmap.isNull()
    assert not capture.is_active()


def test_right_click_cancels(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    qtbot.mouseClick(capture.overlays[0], Qt.RightButton, pos=QPoint(5, 5))
    assert got["cancelled"] == 1 and not capture.is_active()


def test_cancel_without_notify_and_twice_is_quiet(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300))])
    capture.cancel(notify=False)
    capture.cancel()
    assert got["cancelled"] == 0 and not capture.is_active()


def test_black_screen_is_blocked_without_overlay(qtbot):
    capture, got = started(qtbot, [fake_shot(QRect(0, 0, 400, 300), fill="black")])
    assert got["blocked"] == 1 and not capture.overlays


def test_is_blocked_threshold():
    image = QImage(100, 100, QImage.Format_RGB888)
    image.fill(QColor("black"))
    assert is_blocked(image)
    painter = QPainter(image)
    painter.fillRect(QRect(0, 0, 100, 5), QColor("white"))   # 표본의 약 5%가 밝다
    painter.end()
    assert not is_blocked(image)
    assert is_blocked(QImage())
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_capture.py -v`
Expected: FAIL. `ModuleNotFoundError: No module named 'screen_text.capture'`

- [ ] **Step 3: 구현한다**

`screen_text/capture.py`:

```python
"""화면을 멈춰 영역을 고르게 하고, 잘라낸 실제 픽셀 이미지를 넘긴다.

찍은 화면 전체는 선택하거나 취소하는 즉시 버린다. 임시 파일을 만들지 않는다.
보안 프로그램이 캡처를 막으면(거의 검은 화면) 안내만 하고 우회하지 않는다.
"""
from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

MIN_SELECTION = 8
BLOCKED_LUMA = 8
BLOCKED_RATIO = 0.98
SAMPLE_GRID = 64
DIM = QColor(6, 12, 22, 140)
ACCENT = QColor("#E8590C")


def grab_screens():
    """연결된 모든 화면을 (논리 좌표 영역, 실제 픽셀 pixmap)으로 찍는다."""
    return [(screen.geometry(), screen.grabWindow(0)) for screen in QGuiApplication.screens()]


def is_blocked(image):
    """격자 표본의 98% 이상이 거의 검은색이면 캡처가 막힌 것으로 본다."""
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return True
    dark = total = 0
    for gy in range(SAMPLE_GRID):
        y = min(image.height() - 1, gy * image.height() // SAMPLE_GRID)
        for gx in range(SAMPLE_GRID):
            x = min(image.width() - 1, gx * image.width() // SAMPLE_GRID)
            color = image.pixelColor(x, y)
            luma = (color.red() * 299 + color.green() * 587 + color.blue() * 114) // 1000
            dark += luma < BLOCKED_LUMA
            total += 1
    return dark >= BLOCKED_RATIO * total


def _physical(rect, ratio):
    return QRect(round(rect.x() * ratio), round(rect.y() * ratio),
                 round(rect.width() * ratio), round(rect.height() * ratio))


def crop_physical(pixmap, rect):
    """논리 좌표 선택을 pixmap의 device pixel ratio로 바꿔 실제 픽셀로 자른다."""
    physical = _physical(rect, pixmap.devicePixelRatio()).intersected(QRect(0, 0, pixmap.width(), pixmap.height()))
    return pixmap.copy(physical).toImage().convertToFormat(QImage.Format_RGB888)


class CaptureOverlay(QWidget):
    """한 화면을 덮는 멈춘 화면. 끌어서 사각형을 고른다(그 화면 안으로 제한)."""

    selected = Signal(QRect)
    cancelled = Signal()

    def __init__(self, geometry, pixmap):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("screenTextCaptureOverlay")
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.pixmap = pixmap
        self._origin = None
        self._current = QRect()
        self.setGeometry(geometry)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.fillRect(self.rect(), DIM)
        if not self._current.isEmpty():
            painter.drawPixmap(self._current, self.pixmap, _physical(self._current, self.pixmap.devicePixelRatio()))
            painter.setPen(QPen(ACCENT, 2))
            painter.drawRect(self._current.adjusted(0, 0, -1, -1))
            painter.drawText(self._current.topLeft() + QPoint(0, -6),
                             f"{self._current.width()} × {self._current.height()}")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._current = QRect(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._current = QRect(self._origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._origin is None:
            return
        self._origin = None
        rect = QRect(self._current)
        if rect.width() < MIN_SELECTION or rect.height() < MIN_SELECTION:
            self._current = QRect()
            self.update()
            return
        self.selected.emit(rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ScreenCapture(QObject):
    """모든 화면에 오버레이를 띄우고 한 곳의 선택 결과만 넘긴다."""

    captured = Signal(QImage)
    cancelled = Signal()
    blocked = Signal()

    def __init__(self, parent=None, grab=grab_screens):
        super().__init__(parent)
        self._grab = grab
        self.overlays = []

    def is_active(self):
        return bool(self.overlays)

    def start(self):
        self._close_overlays()
        shots = self._grab()
        if not shots or all(is_blocked(pixmap.toImage()) for _, pixmap in shots):
            self.blocked.emit()
            return
        for geometry, pixmap in shots:
            overlay = CaptureOverlay(geometry, pixmap)
            overlay.selected.connect(lambda rect, source=overlay: self._finish(source, rect))
            overlay.cancelled.connect(self.cancel)
            self.overlays.append(overlay)
            overlay.show()
        cursor = QCursor.pos()
        focus = next((o for o in self.overlays if o.geometry().contains(cursor)), self.overlays[0])
        focus.raise_()
        focus.activateWindow()
        focus.setFocus(Qt.OtherFocusReason)

    def cancel(self, notify=True):
        """오버레이를 닫고 찍은 화면을 버린다. 진행 중이었고 notify이면 cancelled를 보낸다."""
        if self._close_overlays() and notify:
            self.cancelled.emit()

    def _close_overlays(self):
        overlays, self.overlays = self.overlays, []
        for overlay in overlays:
            overlay.pixmap = QPixmap()
            overlay.hide()
            overlay.deleteLater()
        return bool(overlays)

    def _finish(self, overlay, rect):
        image = crop_physical(overlay.pixmap, rect)
        self._close_overlays()
        self.captured.emit(image)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_capture.py -v`
Expected: PASS 11개

- [ ] **Step 5: 커밋한다**

```bash
git add screen_text/capture.py tests/test_screen_text_capture.py
git commit -m "feat: 화면 글자 따기 화면 멈춤과 실제 픽셀 영역 선택

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 도구 창, 아이콘, 등록

**Files:**
- Create: `screen_text/window.py`, `screen_text/icon.svg`
- Modify: `screen_text/__init__.py` (APP 추가), `optional_mini_apps.py` (등록 줄)
- Test: `tests/test_screen_text_ui.py`

**Interfaces:**
- Consumes: `layout.build_blocks`·`to_plain`·`to_tsv`·`to_html`·`rows_of`·`has_table`·`Cell`·`Table`·`TextLine`, `capture.ScreenCapture`·`grab_screens`, `engine.OcrEngine`·`ModelIntegrityError`·`RecognitionCancelled`·`rgb_from_buffer`(작업 스레드에서 늦게 import), `ui_mini_apps.MiniAppSpec`
- Produces:
  - `ScreenTextWindow(parent=None, engine_factory=_default_engine, grab=grab_screens)`
  - 규약 메서드 5개 + `start_capture()`, `copy_result()`, `release_model()`
  - 페이지 속성 `intro_page`, `busy_page`, `result_page`, `stack`
  - 위젯 속성 `capture_button`, `cancel_button`, `copy_button`, `again_button`, `text_tab`, `table_tab`, `text_edit`, `table`, `status_label`, `message_label`, `first_load_label`, `preview`
  - `screen_text.APP: MiniAppSpec` (`app_id="screen_text"`)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_screen_text_ui.py`:

```python
"""화면 글자 따기 도구 창·등록·아이콘 (가짜 엔진·가짜 스크린샷, 실제 화면을 찍지 않는다)."""
import re
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from qfluentwidgets.common.font import fontFamilies, setFontFamilies

from app_fonts import apply_app_font
from app_paths import resource_root
import database as db
import optional_mini_apps
import ui_main
from screen_text import APP
from screen_text.engine import ModelIntegrityError, RecognitionCancelled
from screen_text.layout import TextBox
from screen_text.window import ScreenTextWindow

ROOT = Path(__file__).resolve().parents[1]
TABLE = [
    TextBox(10, 10, 30, 16, "구분", 0.99), TextBox(120, 10, 70, 16, "점검 사업장", 0.99), TextBox(260, 10, 30, 16, "위반", 0.99),
    TextBox(12, 34, 30, 16, "대전", 0.99), TextBox(140, 34, 16, 16, "42", 0.99), TextBox(265, 34, 8, 16, "3", 0.99),
    TextBox(12, 58, 30, 16, "충북", 0.99), TextBox(140, 58, 16, 16, "5l", 0.95), TextBox(265, 58, 8, 16, "4", 0.99),
]
SENTENCE = [TextBox(0, 0, 200, 16, "환경 점검 결과 알림", 0.99)]


class FakeEngine:
    def __init__(self, boxes=(), gate=None, error=None):
        self.boxes, self.gate, self.error, self.calls = list(boxes), gate, error, 0

    def recognize(self, rgb, cancelled):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(5)
        if cancelled():
            raise RecognitionCancelled
        if self.error is not None:
            raise self.error
        return list(self.boxes)


def shot(fill="white"):
    pixmap = QPixmap(400, 300)
    pixmap.fill(QColor(fill))
    return [(QRect(0, 0, 400, 300), pixmap)]


def image(width=120, height=40):
    picture = QImage(width, height, QImage.Format_RGB888)
    picture.fill(QColor("white"))
    return picture


@pytest.fixture
def make(qtbot):
    def factory(engine=None, grab=None):
        win = ScreenTextWindow(None, engine_factory=lambda: engine or FakeEngine(TABLE), grab=grab or shot)
        qtbot.addWidget(win)
        win.show_near(QRect(100, 100, 64, 48), QGuiApplication.primaryScreen().availableGeometry())
        qtbot.waitExposed(win)
        return win
    return factory


def recognized(qtbot, win, picture=None):
    win._on_captured(picture or image())
    qtbot.waitUntil(lambda: win.stack.currentWidget() is not win.busy_page, timeout=5000)


def test_intro_state_offline_note_and_focus(make):
    win = make()
    assert win.stack.currentWidget() is win.intro_page
    assert win.capture_button.isEnabled() and not win.message_label.isVisible()
    assert "인터넷 없이" in win.offline_label.text()
    assert win.size().width() <= 460 + 48


def test_capture_flow_shows_preview_table_tab_and_unsure(qtbot, make):
    win = make()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    assert not win.isVisible()
    overlay = win._capture.overlays[0]
    qtbot.waitExposed(overlay)
    qtbot.mousePress(overlay, Qt.LeftButton, pos=QPoint(10, 10))
    qtbot.mouseMove(overlay, QPoint(209, 109))
    qtbot.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(209, 109))
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page, timeout=5000)
    assert win.isVisible()
    assert 0 < win.preview.pixmap().height() <= 90
    assert win.table_tab.isVisible() and win.table_tab.isChecked()
    assert win.status_label.text() == "확인 필요 1곳"
    item = win.table.item(2, 1)
    assert item.text() == "5l" and item.background().color() == QColor("#FFE58A")


def test_text_only_result_hides_table_tab(qtbot, make):
    win = make(FakeEngine(SENTENCE))
    recognized(qtbot, win)
    assert not win.table_tab.isVisible() and win.text_tab.isChecked()
    assert win.text_edit.toPlainText() == "환경 점검 결과 알림"
    assert win.status_label.text() == "불확실한 곳 없음"


def test_copy_table_puts_tsv_and_html_on_clipboard(qtbot, make):
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    mime = QGuiApplication.clipboard().mimeData()
    assert mime.text().splitlines()[0] == "구분\t점검 사업장\t위반"
    assert "<td>점검 사업장</td>" in mime.html()
    assert win.status_label.text() == "복사했습니다"


def test_copy_text_tab_puts_edited_plain_text_only(qtbot, make):
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    win.text_edit.setPlainText("고친 글자")
    qtbot.mouseClick(win.copy_button, Qt.LeftButton)
    mime = QGuiApplication.clipboard().mimeData()
    assert mime.text() == "고친 글자" and not mime.hasHtml()


def test_editing_unsure_cell_clears_mark_and_refreshes_text_tab(qtbot, make):
    win = make()
    recognized(qtbot, win)
    win.table.item(2, 1).setText("51")
    assert win.status_label.text() == "확인 완료"
    assert win.table.item(2, 1).background().style() == Qt.NoBrush
    assert "충북 51 4" in win.text_edit.toPlainText()


def test_editing_unsure_token_in_text_tab_updates_count(qtbot, make):
    win = make()
    recognized(qtbot, win)
    qtbot.mouseClick(win.text_tab, Qt.LeftButton)
    assert win.status_label.text() == "확인 필요 1곳"
    assert len(win.text_edit.extraSelections()) == 1
    win.text_edit.setPlainText(win.text_edit.toPlainText().replace("5l", "51"))
    assert win.status_label.text() == "확인 완료"
    assert win.text_edit.extraSelections() == []


def test_cancel_during_recognition_discards_late_result(qtbot, make):
    gate = threading.Event()
    win = make(FakeEngine(TABLE, gate=gate))
    win._on_captured(image())
    assert win.stack.currentWidget() is win.busy_page
    qtbot.mouseClick(win.cancel_button, Qt.LeftButton)
    assert win.stack.currentWidget() is win.intro_page
    gate.set()
    qtbot.wait(300)
    assert win.stack.currentWidget() is win.intro_page and win._blocks == []


def test_first_recognition_shows_model_loading_note(qtbot, make):
    gate = threading.Event()
    win = make(FakeEngine(TABLE, gate=gate))
    win._on_captured(image())
    assert win.first_load_label.isVisible()
    gate.set()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page, timeout=5000)
    win._on_captured(image())
    assert not win.first_load_label.isVisible()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.result_page, timeout=5000)


def test_hide_owned_popups_stops_pending_capture(qtbot, make):
    win = make()
    win.start_capture()
    win.hide_owned_popups()
    qtbot.wait(350)
    assert not win._capture.is_active()


def test_lifecycle_hide_during_overlay_does_not_reopen_window(qtbot, make):
    win = make()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    win.cancel_work()
    win.hide_owned_popups()
    win.hide()
    qtbot.wait(100)
    assert not win.isVisible() and not win._capture.is_active()


def test_escape_on_overlay_brings_window_back(qtbot, make):
    win = make()
    win.start_capture()
    qtbot.waitUntil(lambda: win._capture.is_active(), timeout=2000)
    qtbot.keyClick(win._capture.overlays[0], Qt.Key_Escape)
    qtbot.waitUntil(win.isVisible)
    assert win.stack.currentWidget() is win.intro_page


def test_blocked_capture_shows_message(qtbot, make):
    win = make(grab=lambda: shot("black"))
    win.start_capture()
    qtbot.waitUntil(win.isVisible, timeout=2000)
    assert win.message_label.isVisible()
    assert win.message_label.text() == "보안 프로그램이 화면 캡처를 막아 글자를 딸 수 없습니다."


def test_empty_result_shows_message(qtbot, make):
    win = make(FakeEngine([]))
    recognized(qtbot, win)
    assert win.stack.currentWidget() is win.intro_page
    assert win.message_label.text() == "고른 영역에서 글자를 찾지 못했습니다."


def test_model_error_disables_capture_button(qtbot, make):
    win = make(FakeEngine(error=ModelIntegrityError("x")))
    recognized(qtbot, win)
    assert win.message_label.text() == "인식 모델을 확인하지 못했습니다."
    assert not win.capture_button.isEnabled()


def test_engine_failure_is_reported_without_text_in_log(qtbot, make, caplog):
    win = make(FakeEngine(error=ValueError("비밀 글자")))
    recognized(qtbot, win)
    assert win.message_label.text() == "글자를 읽지 못했습니다. 다시 시도해 주세요."
    assert "비밀 글자" not in caplog.text


def test_close_releases_model_but_keeps_result(qtbot, make):
    win = make()
    recognized(qtbot, win)
    assert win._engine is not None
    win.close()
    assert win._engine is None and win._blocks
    win.show_near(QRect(100, 100, 64, 48), QGuiApplication.primaryScreen().availableGeometry())
    assert win.stack.currentWidget() is win.result_page


def test_shutdown_clears_results_preview_and_model(qtbot, make):
    win = make()
    recognized(qtbot, win)
    win.shutdown()
    assert win._blocks == [] and win._engine is None
    assert win.preview.pixmap().isNull()
    assert win.stack.currentWidget() is win.intro_page


def test_app_spec_and_registry():
    assert APP.app_id == "screen_text"
    assert APP.title == "화면 글자\n따기" and APP.accessible_name == "화면 글자 따기 실행"
    assert APP.icon_path == resource_root() / "screen_text" / "icon.svg"
    assert APP in optional_mini_apps.OPTIONAL_MINI_APPS


def test_registered_tile_opens_window_and_lock_hides_it(qtbot, app_dir, qapp, monkeypatch):
    previous_font, previous_families = qapp.font(), fontFamilies()
    apply_app_font(db.DEFAULT_APP_FONT, qapp)
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    db.save_setting(db.SETTING_SHOW_SIDEBAR, "1")
    monkeypatch.setattr(ui_main.InfoBar, "error", lambda **kw: None)
    win = ui_main.MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    assert QTest.qWaitForWindowExposed(win)
    qtbot.mouseClick(win.sidebar.mini_apps_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: win._mini_apps_popup is not None and win._mini_apps_popup.isVisible())
    popup = win._mini_apps_popup
    assert popup.card.height() == 390
    qtbot.mouseClick(popup.optional_cards["screen_text"], Qt.LeftButton)
    qtbot.waitUntil(lambda: "screen_text" in win._optional_windows)
    tool = win._optional_windows["screen_text"]
    assert isinstance(tool, ScreenTextWindow) and tool.isVisible()
    win._lock()
    assert not tool.isVisible() and not tool.isEnabled()
    win._unlock()
    qapp.setFont(previous_font)
    setFontFamilies(previous_families, save=False)


@pytest.mark.parametrize("scale", [1, 1.25, 1.5])
def test_icon_follows_mini_app_icon_rules(qapp, scale):
    path = resource_root() / "screen_text" / "icon.svg"
    with open(path, encoding="utf-8") as stream:
        text = stream.read()
    for banned in ("<text", "<image", "<filter", "<mask", "<style", "https://", "xlink:href"):
        assert banned not in text
    size = round(48 * scale)
    picture = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    picture.fill(Qt.transparent)
    painter = QPainter(picture)
    QSvgRenderer(str(path)).render(painter, QRectF(0, 0, size, size))
    painter.end()

    def near(color, expected):
        target = QColor(expected)
        return abs(color.red() - target.red()) + abs(color.green() - target.green()) + abs(color.blue() - target.blue()) <= 90

    assert picture.pixelColor(0, 0).alpha() == 0
    assert near(picture.pixelColor(round(size * .16), round(size * .10)), "#FF9A4D")
    assert near(picture.pixelColor(round(size * .84), round(size * .90)), "#D9480F")
    inner = range(round(size * .2), round(size * .8))
    white = sum(1 for x in inner for y in inner
                if picture.pixelColor(x, y).alpha() == 255 and min(picture.pixelColor(x, y).getRgb()[:3]) >= 235)
    assert white >= size


def test_screen_text_is_imported_only_from_registry_build_spec_and_own_tests():
    pattern = re.compile(r"^\s*(from|import)\s+screen_text\b", re.M)
    candidates = list(ROOT.glob("*.py")) + list((ROOT / "tests").glob("*.py")) + list((ROOT / "tools").glob("*.py"))
    offenders = []
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        if relative == "optional_mini_apps.py" or relative.startswith("tests/test_screen_text_"):
            continue
        with open(path, encoding="utf-8") as stream:
            if pattern.search(stream.read()):
                offenders.append(relative)
    assert offenders == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_ui.py -v`
Expected: FAIL. `ImportError: cannot import name 'APP' from 'screen_text'`

- [ ] **Step 3: 아이콘을 만든다**

`screen_text/icon.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
  <defs>
    <linearGradient id="bg" x1="10" y1="2" x2="38" y2="46" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#FF9A4D"/>
      <stop offset="1" stop-color="#D9480F"/>
    </linearGradient>
  </defs>
  <rect width="48" height="48" rx="12.5" fill="url(#bg)"/>
  <rect x="0.5" y="0.5" width="47" height="47" rx="12" fill="none" stroke="#FFFFFF" stroke-opacity="0.22"/>
  <g transform="translate(9.6 9.6) scale(1.2)" fill="none" stroke="#FFFFFF" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3"/>
    <path d="M8 9h8M8 12.5h8M8 16h5"/>
  </g>
</svg>
```

- [ ] **Step 4: 도구 창을 구현한다**

`screen_text/window.py`:

```python
"""화면 글자 따기 도구 창. 결과·미리보기는 실행 중 메모리 전용이다.

계약은 docs/SCREEN_TEXT.md를 따른다. 인식 엔진(numpy·onnxruntime)은 처음
인식할 때 작업 스레드에서 불러오고, 사용자가 창을 닫으면 내린다.
"""
import logging
import threading

from PySide6.QtCore import QEvent, QMimeData, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from screen_text.capture import ScreenCapture, grab_screens
from screen_text.layout import Cell, Table, TextLine, build_blocks, has_table, rows_of, to_html, to_plain, to_tsv

_logger = logging.getLogger("app_error")
CONTENT_WIDTH, CONTENT_HEIGHT, SHADOW_MARGIN = 460, 560, 24
CAPTURE_DELAY_MS = 200
PREVIEW_HEIGHT = 90
UNSURE_BACKGROUND = QColor("#FFE58A")
INTRO_TEXT = "복사할 수 없는 이미지나 스캔 문서의 글자를 읽습니다.\n[영역 고르기]를 누른 뒤 화면에서 끌어서 고르세요."
OFFLINE_TEXT = "인터넷 없이 이 PC에서만 처리합니다. 결과는 저장하지 않습니다."
FIRST_LOAD_TEXT = "처음 한 번은 모델을 불러오느라 조금 더 걸립니다."
MESSAGES = {
    "blocked": "보안 프로그램이 화면 캡처를 막아 글자를 딸 수 없습니다.",
    "empty": "고른 영역에서 글자를 찾지 못했습니다.",
    "model": "인식 모델을 확인하지 못했습니다.",
    "failed": "글자를 읽지 못했습니다. 다시 시도해 주세요.",
}
STYLE = """
    QWidget { color:#253447; }
    QWidget#screenTextSurface { background:#FFFFFF; border-radius:16px; }
    QLabel#screenTextTitle { color:#172B4D; font-size:15px; font-weight:bold; }
    QLabel[muted="true"] { color:#677180; font-size:11px; }
    QLabel#screenTextMessage { background:#FFF4E5; color:#8A4B08; border-radius:8px; padding:8px 10px; }
    QLabel#screenTextPreview { background:#F5F7FA; border:1px solid #E1E6ED; border-radius:6px; }
    QLabel#screenTextStatus { background:#FFE58A; color:#5C4200; border-radius:10px; padding:2px 10px; font-size:11px; }
    QLabel#screenTextStatus[done="true"] { background:#EAF2FE; color:#1D4ED8; }
    QPushButton { background:#FFFFFF; border:1px solid #CDD5E0; border-radius:6px; padding:6px 12px; font-size:13px; }
    QPushButton:hover { background:#EDF3FB; border-color:#91AACA; }
    QPushButton:focus { border:1px solid #315C98; }
    QPushButton:disabled { color:#959CA6; background:#F3F4F6; }
    QPushButton[primary="true"] { background:#2563EB; border-color:#2563EB; color:#FFFFFF; font-weight:bold; }
    QPushButton[primary="true"]:disabled { background:#A9C1F2; border-color:#A9C1F2; }
    QPushButton[tab="true"] { background:transparent; border:0; color:#677180; padding:6px 14px; }
    QPushButton[tab="true"]:checked { background:#EAF2FE; color:#1D4ED8; font-weight:bold; }
    QPushButton#screenTextClose { background:transparent; border:0; color:#7A8699; font-size:19px; padding:0 8px; }
    QPlainTextEdit, QTableWidget { border:1px solid #DCE1E8; border-radius:6px; font-size:13px; }
"""


class _Bridge(QObject):
    """작업 스레드 결과를 GUI 스레드로 넘긴다(스레드 간 신호는 큐로 전달된다)."""

    finished = Signal(int, object)
    failed = Signal(int, str)


def _default_engine():
    from screen_text.engine import OcrEngine
    return OcrEngine()


def _image_buffer(image):
    image = image.convertToFormat(QImage.Format_RGB888)
    return image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits())


def _emit(signal, *args):
    """창이 이미 폐기된 뒤 작업 스레드가 끝나면 신호 대상이 없다. 결과를 버린다."""
    try:
        signal.emit(*args)
    except RuntimeError:
        _logger.debug("화면 글자 따기 창이 폐기된 뒤 결과를 버렸습니다")


def _set_property(widget, name, value):
    if widget.property(name) != value:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class ScreenTextWindow(QWidget):
    def __init__(self, parent=None, engine_factory=_default_engine, grab=grab_screens):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("screenText")
        self.setWindowTitle("화면 글자 따기 · 기후노트")
        self.setAccessibleName("화면 글자 따기")
        self.setAttribute(Qt.WA_TranslucentBackground)
        font = QFont(self.font())
        font.setPixelSize(13)
        self.setFont(font)
        self.setStyleSheet(STYLE)
        self._engine_factory = engine_factory
        self._engine = None
        self._engine_lock = threading.Lock()
        self._generation = 0
        self._cancel_event = None
        self._blocks = []
        self._table_rows = []
        self._unsure_tokens = []
        self._text_unsure_left = 0
        self._had_unsure = False
        self._text_dirty = False
        self._filling = False
        self._model_broken = False
        self._tab = "text"
        self._placed = False
        self._drag_origin = None
        self._bridge = _Bridge(self)
        self._bridge.finished.connect(self._on_finished)
        self._bridge.failed.connect(self._on_failed)
        self._capture = ScreenCapture(self, grab=grab)
        self._capture.captured.connect(self._on_captured)
        self._capture.cancelled.connect(self._reappear)
        self._capture.blocked.connect(self._on_blocked)
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.setInterval(CAPTURE_DELAY_MS)
        self._capture_timer.timeout.connect(self._begin_capture)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(1500)
        self._status_timer.timeout.connect(self._update_status)
        self._build()
        self._show_intro(None)
        self.fit_to_screen()

    # ── 화면 구성 ──
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        self.surface = QWidget(self)
        self.surface.setObjectName("screenTextSurface")
        self.surface.setAttribute(Qt.WA_StyledBackground)
        outer.addWidget(self.surface)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(24, 46, 76, 80))
        self.surface.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self.surface)
        layout.setContentsMargins(18, 0, 18, 16)
        layout.setSpacing(10)

        self.header = QFrame(self.surface)
        self.header.setFixedHeight(48)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("화면 글자 따기", self.header)
        self.title_label.setObjectName("screenTextTitle")
        header.addWidget(self.title_label)
        header.addStretch()
        self.close_button = QPushButton("×", self.header)
        self.close_button.setObjectName("screenTextClose")
        self.close_button.setAccessibleName("화면 글자 따기 닫기")
        self.close_button.setToolTip("닫기 (Esc)")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        self.header.installEventFilter(self)
        self.title_label.installEventFilter(self)
        layout.addWidget(self.header)

        self.stack = QStackedWidget(self.surface)
        layout.addWidget(self.stack, 1)

        self.intro_page = QWidget()
        intro = QVBoxLayout(self.intro_page)
        intro.setContentsMargins(0, 0, 0, 0)
        intro.setSpacing(12)
        guide = QLabel(INTRO_TEXT)
        guide.setWordWrap(True)
        intro.addWidget(guide)
        self.message_label = QLabel()
        self.message_label.setObjectName("screenTextMessage")
        self.message_label.setWordWrap(True)
        intro.addWidget(self.message_label)
        self.capture_button = QPushButton("영역 고르기")
        self.capture_button.setProperty("primary", True)
        self.capture_button.setFixedHeight(40)
        self.capture_button.clicked.connect(self.start_capture)
        intro.addWidget(self.capture_button)
        self.offline_label = QLabel(OFFLINE_TEXT)
        self.offline_label.setProperty("muted", True)
        self.offline_label.setWordWrap(True)
        intro.addWidget(self.offline_label)
        intro.addStretch()
        self.stack.addWidget(self.intro_page)

        self.busy_page = QWidget()
        busy = QVBoxLayout(self.busy_page)
        busy.setContentsMargins(0, 0, 0, 0)
        busy.addStretch()
        reading = QLabel("읽는 중…")
        reading.setAlignment(Qt.AlignCenter)
        reading.setStyleSheet("font-size:15px; font-weight:bold;")
        busy.addWidget(reading)
        self.first_load_label = QLabel(FIRST_LOAD_TEXT)
        self.first_load_label.setProperty("muted", True)
        self.first_load_label.setAlignment(Qt.AlignCenter)
        busy.addWidget(self.first_load_label)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.cancel_work)
        busy.addWidget(self.cancel_button, 0, Qt.AlignCenter)
        busy.addStretch()
        self.stack.addWidget(self.busy_page)

        self.result_page = QWidget()
        result = QVBoxLayout(self.result_page)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(8)
        self.preview = QLabel()
        self.preview.setObjectName("screenTextPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(PREVIEW_HEIGHT + 8)
        result.addWidget(self.preview)
        tabs = QHBoxLayout()
        self.text_tab = QPushButton("글자")
        self.table_tab = QPushButton("표 모양")
        group = QButtonGroup(self)
        for button, name in ((self.text_tab, "text"), (self.table_tab, "table")):
            button.setProperty("tab", True)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, tab=name: self._set_tab(tab))
            group.addButton(button)
            tabs.addWidget(button)
        tabs.addStretch()
        self.status_label = QLabel()
        self.status_label.setObjectName("screenTextStatus")
        tabs.addWidget(self.status_label)
        result.addLayout(tabs)
        self.result_stack = QStackedWidget()
        self.text_edit = QPlainTextEdit()
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.table = QTableWidget()
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.result_stack.addWidget(self.text_edit)
        self.result_stack.addWidget(self.table)
        result.addWidget(self.result_stack, 1)
        actions = QHBoxLayout()
        self.copy_button = QPushButton("복사")
        self.copy_button.setProperty("primary", True)
        self.copy_button.clicked.connect(self.copy_result)
        self.again_button = QPushButton("다시 고르기")
        self.again_button.clicked.connect(self.start_capture)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.again_button)
        actions.addStretch()
        result.addLayout(actions)
        note = QLabel(OFFLINE_TEXT)
        note.setProperty("muted", True)
        result.addWidget(note)
        self.stack.addWidget(self.result_page)
        for button in self.findChildren(QPushButton):
            button.installEventFilter(self)

    # ── 수명 규약 (ui_main 공용 연결부가 호출) ──
    def show_near(self, anchor, available):
        if not self._placed:
            self.move(anchor.right() + 12, anchor.top())
            self._placed = True
        self.fit_to_screen(available)
        self._reappear()

    def hide_owned_popups(self):
        """예약된 캡처와 화면 오버레이를 닫는다. 찍은 화면은 버린다."""
        self._capture_timer.stop()
        self._capture.cancel(notify=False)

    def cancel_work(self):
        """진행 중인 인식을 취소한다. 늦게 도착한 결과는 실행 번호로 버린다."""
        busy = self.stack.currentWidget() is self.busy_page
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_event = None
        self._generation += 1
        if busy:
            if self._blocks:
                self._show_result()
            else:
                self._show_intro(None)

    def fit_to_screen(self, available=None):
        if available is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
        margin = min(SHADOW_MARGIN, max(0, (available.width() - CONTENT_WIDTH) // 2),
                     max(0, (available.height() - CONTENT_HEIGHT) // 2))
        self.layout().setContentsMargins(margin, margin, margin, margin)
        shadow = self.surface.graphicsEffect()
        shadow.setBlurRadius(max(0, margin - 4))
        shadow.setOffset(0, min(4, margin))
        shadow.setEnabled(margin > 0)
        self.resize(min(CONTENT_WIDTH + 2 * margin, available.width()),
                    min(CONTENT_HEIGHT + 2 * margin, available.height()))
        self.move(max(available.left(), min(self.x(), available.right() + 1 - self.width())),
                  max(available.top(), min(self.y(), available.bottom() + 1 - self.height())))

    def release_model(self):
        with self._engine_lock:
            self._engine = None

    def shutdown(self):
        self.hide_owned_popups()
        self.cancel_work()
        self._blocks, self._table_rows, self._unsure_tokens = [], [], []
        self._had_unsure = False
        self.preview.clear()
        self._filling = True
        self.text_edit.clear()
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self._filling = False
        self.release_model()
        self._show_intro(None)

    # ── 사용자 동작 ──
    def start_capture(self):
        if not self.isEnabled() or self.stack.currentWidget() is self.busy_page:
            return
        self.hide()
        self._capture_timer.start()

    def copy_result(self):
        mime = QMimeData()
        if self._tab == "table":
            mime.setText(to_tsv(self._blocks))
            mime.setHtml(to_html(self._blocks))
        else:
            mime.setText(self.text_edit.toPlainText())
        QGuiApplication.clipboard().setMimeData(mime)
        self.status_label.setText("복사했습니다")
        _set_property(self.status_label, "done", True)
        self._status_timer.start()

    # ── 캡처와 인식 ──
    def _begin_capture(self):
        if self.isEnabled():
            self._capture.start()

    def _reappear(self):
        self.show()
        self.raise_()
        self.activateWindow()
        target = self.copy_button if self.stack.currentWidget() is self.result_page else self.capture_button
        target.setFocus(Qt.OtherFocusReason)

    def _on_blocked(self):
        self._show_intro("blocked")
        self._reappear()

    def _on_captured(self, image):
        pixmap = QPixmap.fromImage(image)
        if pixmap.height() > PREVIEW_HEIGHT:
            pixmap = pixmap.scaledToHeight(PREVIEW_HEIGHT, Qt.SmoothTransformation)
        if pixmap.width() > CONTENT_WIDTH - 40:
            pixmap = pixmap.scaledToWidth(CONTENT_WIDTH - 40, Qt.SmoothTransformation)
        self.preview.setPixmap(pixmap)
        self._generation += 1
        generation, event = self._generation, threading.Event()
        self._cancel_event = event
        self.first_load_label.setVisible(self._engine is None)
        self.stack.setCurrentWidget(self.busy_page)
        threading.Thread(target=self._work, args=(generation, _image_buffer(image), event),
                         name="screen-text-ocr", daemon=True).start()
        self._reappear()
        self.cancel_button.setFocus(Qt.OtherFocusReason)

    def _engine_for_work(self):
        with self._engine_lock:
            if self._engine is None:
                self._engine = self._engine_factory()
            return self._engine

    def _work(self, generation, buffer, event):
        """작업 스레드. Qt 위젯을 만지지 않고 신호로만 결과를 보낸다."""
        from screen_text.engine import ModelIntegrityError, RecognitionCancelled, rgb_from_buffer
        try:
            boxes = self._engine_for_work().recognize(rgb_from_buffer(*buffer), event.is_set)
        except RecognitionCancelled:
            return
        except ModelIntegrityError:
            _emit(self._bridge.failed, generation, "model")
            return
        except Exception as error:  # 작업 스레드 경계: 어떤 오류도 창을 '읽는 중'에 멈춰 두지 않는다
            _logger.error("화면 글자 인식 실패: %s", type(error).__name__)
            _emit(self._bridge.failed, generation, "failed")
            return
        _emit(self._bridge.finished, generation, boxes)

    def _on_finished(self, generation, boxes):
        if generation != self._generation:
            return
        self._cancel_event = None
        blocks = build_blocks(boxes)
        if not blocks:
            self._show_intro("empty")
            return
        self._blocks = blocks
        self._had_unsure = any(cell.unsure for block in blocks for row in rows_of(block) for cell in row)
        self._tab = "table" if has_table(blocks) else "text"
        self._fill_table()
        self._fill_text()
        self._show_result()

    def _on_failed(self, generation, kind):
        if generation != self._generation:
            return
        self._cancel_event = None
        self._show_intro(kind)

    # ── 결과 표시와 편집 ──
    def _show_intro(self, kind):
        self._model_broken = self._model_broken or kind == "model"
        self.message_label.setText(MESSAGES.get(kind, ""))
        self.message_label.setVisible(kind is not None)
        self.capture_button.setEnabled(not self._model_broken)
        self.stack.setCurrentWidget(self.intro_page)

    def _show_result(self):
        self.stack.setCurrentWidget(self.result_page)
        self.table_tab.setVisible(has_table(self._blocks))
        self._set_tab(self._tab)

    def _set_tab(self, name):
        self._tab = name
        self.text_tab.setChecked(name == "text")
        self.table_tab.setChecked(name == "table")
        self.result_stack.setCurrentWidget(self.text_edit if name == "text" else self.table)
        self._update_status()

    def _fill_text(self):
        self._filling = True
        self.text_edit.setPlainText(to_plain(self._blocks))
        self._filling = False
        self._text_dirty = False
        self._unsure_tokens = [cell.text for block in self._blocks for row in rows_of(block)
                               for cell in row if cell.unsure]
        self._highlight_text()

    def _fill_table(self):
        self._filling = True
        self._table_rows = []
        columns = max([len(block.rows[0]) for block in self._blocks if isinstance(block, Table)] + [1])
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(columns)
        for block in self._blocks:
            for row_index, row in enumerate(rows_of(block)):
                position = self.table.rowCount()
                self.table.insertRow(position)
                self._table_rows.append((block, row_index))
                if isinstance(block, TextLine):
                    item = QTableWidgetItem(" ".join(cell.text for cell in row if cell.text))
                    if any(cell.unsure for cell in row):
                        item.setBackground(UNSURE_BACKGROUND)
                    self.table.setItem(position, 0, item)
                    if columns > 1:
                        self.table.setSpan(position, 0, 1, columns)
                    continue
                for column, cell in enumerate(row):
                    item = QTableWidgetItem(cell.text)
                    if cell.unsure:
                        item.setBackground(UNSURE_BACKGROUND)
                    self.table.setItem(position, column, item)
        self.table.resizeColumnsToContents()
        self._filling = False

    def _on_table_item_changed(self, item):
        if self._filling:
            return
        block, row_index = self._table_rows[item.row()]
        text = item.text()
        if isinstance(block, TextLine):
            if text != " ".join(cell.text for cell in block.cells if cell.text):
                block.cells[:] = [Cell(text)]
        else:
            cell = block.rows[row_index][item.column()]
            if text != cell.text:
                cell.text, cell.unsure = text, False
        self._filling = True
        item.setData(Qt.BackgroundRole, None)
        self._filling = False
        if not self._text_dirty:
            self._fill_text()
        self._update_status()

    def _on_text_changed(self):
        if self._filling:
            return
        self._text_dirty = True
        self._highlight_text()
        self._update_status()

    def _highlight_text(self):
        """확인 필요 글자가 아직 그대로 남은 곳만 노랗게 표시한다."""
        document = self.text_edit.document()
        cursor = QTextCursor(document)
        selections = []
        for token in self._unsure_tokens:
            found = document.find(token, cursor)
            if found.isNull():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = found
            selection.format.setBackground(UNSURE_BACKGROUND)
            selections.append(selection)
            cursor = found
        self._text_unsure_left = len(selections)
        self.text_edit.setExtraSelections(selections)

    def _update_status(self):
        if self._tab == "text":
            left = self._text_unsure_left
        else:
            left = sum(cell.unsure for block in self._blocks for row in rows_of(block) for cell in row)
        if left:
            self.status_label.setText(f"확인 필요 {left}곳")
        else:
            self.status_label.setText("확인 완료" if self._had_unsure else "불확실한 곳 없음")
        _set_property(self.status_label, "done", not left)

    # ── 창 조작 ──
    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and isinstance(watched, QAbstractButton) and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                watched.click()
            return True
        if watched in (getattr(self, "header", None), getattr(self, "title_label", None)):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_origin = (event.globalPosition().toPoint(), self.pos())
                return True
            if event.type() == QEvent.MouseMove and self._drag_origin and event.buttons() & Qt.LeftButton:
                origin, position = self._drag_origin
                self.move(position + event.globalPosition().toPoint() - origin)
                return True
            if event.type() == QEvent.MouseButtonRelease and self._drag_origin:
                self._drag_origin = None
                self.fit_to_screen()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """사용자가 닫으면 작업을 멈추고 모델을 내린다. 결과는 다음 열기까지 유지한다."""
        self.hide_owned_popups()
        self.cancel_work()
        self.release_model()
        super().closeEvent(event)
```

- [ ] **Step 5: 앱 정보와 등록 줄을 넣는다**

`screen_text/__init__.py`:

```python
"""화면 글자 따기 미니앱 (걷어낼 수 있는 선택형 앱). 계약은 docs/SCREEN_TEXT.md를 따른다."""
from app_paths import resource_root
from ui_mini_apps import MiniAppSpec


def _create_window(parent):
    from screen_text.window import ScreenTextWindow  # 타일을 눌렀을 때만 창 모듈을 불러온다
    return ScreenTextWindow(parent)


APP = MiniAppSpec(
    app_id="screen_text",
    title="화면 글자\n따기",
    accessible_name="화면 글자 따기 실행",
    description="이미지·스캔 속 글자를 읽어 복사",
    icon_path=resource_root() / "screen_text" / "icon.svg",
    create_window=_create_window,
)
```

`optional_mini_apps.py`의 `OPTIONAL_MINI_APPS = ()`를 아래로 바꾼다.

```python
from screen_text import APP as SCREEN_TEXT_APP  # 화면 글자 따기 (걷어낼 때 이 줄을 지운다)

OPTIONAL_MINI_APPS = (SCREEN_TEXT_APP,)  # 걷어낼 때 () 로 되돌린다
```

- [ ] **Step 6: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_screen_text_ui.py -v`
Expected: PASS 24개

- [ ] **Step 7: 관련 검사와 합성 배율을 돌린다**

Run:

```bash
.venv/Scripts/python.exe tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_screen_text_layout.py tests/test_screen_text_engine.py tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py tests/test_mini_app_icons.py tests/test_app_paths.py
QT_SCALE_FACTOR=1.25 .venv/Scripts/python.exe tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_optional_mini_apps.py
QT_SCALE_FACTOR=1.5 .venv/Scripts/python.exe tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_optional_mini_apps.py
```

Expected: 세 실행 모두 통과. 실행 ID 3개를 작업 기록 표에 적는다.

- [ ] **Step 8: 커밋한다**

```bash
git add screen_text/__init__.py screen_text/window.py screen_text/icon.svg optional_mini_apps.py tests/test_screen_text_ui.py docs/work/2026-10-08-screen-text-capture.md
git commit -m "feat: 화면 글자 따기 도구 창과 다섯 번째 미니앱 등록

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 빌드, 라이선스, 문서, 버전 v3.9, release

**Files:**
- Modify: `build.spec`, `tests/test_packaging.py`, `app_info.py`, `tests/test_ui.py:592-598`
- Create: `screen_text/licenses/onnxruntime-LICENSE.txt`, `screen_text/licenses/onnxruntime-ThirdPartyNotices.txt`, `screen_text/licenses/numpy-LICENSE.txt`
- Modify: `licenses/THIRD_PARTY_NOTICES.txt`
- Create: `docs/SCREEN_TEXT.md`
- Modify: `AGENTS.md`, `README_detail.md`, `docs/ARCHITECTURE.md` (Module Map), `docs/TESTING.md`, `docs/work/2026-10-08-screen-text-capture.md`

**Interfaces:**
- Consumes: Task 1~7 전체
- Produces: `build.spec`의 `_SCREEN_TEXT` 분기(폴더 유무로 datas·hiddenimports·excludes 결정), 표시 버전 `v3.9`

- [ ] **Step 1: 실패하는 빌드 설정 테스트를 쓴다**

`tests/test_packaging.py` 끝에 추가:

```python
def _spec_analysis(spec_dir):
    captured = {}

    def analysis(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pure=[], zipped_data=[], scripts=[], binaries=[], zipfiles=[], datas=[])

    namespace = {"SPECPATH": str(spec_dir), "Analysis": analysis, "PYZ": lambda *a, **k: object(),
                 "EXE": lambda *a, **k: object()}
    with open(ROOT / "build.spec", encoding="utf-8") as f:
        exec(compile(f.read(), str(ROOT / "build.spec"), "exec"), namespace)
    return captured


def test_build_spec_bundles_screen_text_only_when_folder_exists(tmp_path):
    present = _spec_analysis(ROOT)
    assert ("screen_text/models", "screen_text/models") in present["datas"]
    assert ("screen_text/icon.svg", "screen_text") in present["datas"]
    assert ("screen_text/licenses", "screen_text/licenses") in present["datas"]
    assert "onnxruntime" in present["hiddenimports"]
    assert "numpy" not in present["excludes"]
    absent = _spec_analysis(tmp_path)  # 걷어낸 뒤: 폴더가 없으면 원래 빌드
    assert not any("screen_text" in source for source, _ in absent["datas"])
    assert "onnxruntime" not in absent["hiddenimports"]
    assert "numpy" in absent["excludes"]
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_packaging.py::test_build_spec_bundles_screen_text_only_when_folder_exists -v`
Expected: FAIL (`AssertionError` — datas에 모델 없음)

- [ ] **Step 2: build.spec에 폴더 감지를 넣는다**

`build.spec`의 `version_info = make_windows_version_info()` 다음에:

```python
# 화면 글자 따기(걷어낼 수 있는 선택형 미니앱): 폴더가 있을 때만 모델·onnxruntime·numpy를 넣는다.
_SCREEN_TEXT = (_SPEC_DIR / "screen_text").is_dir()
_SCREEN_TEXT_DATAS = [
    ('screen_text/models', 'screen_text/models'),
    ('screen_text/icon.svg', 'screen_text'),
    ('screen_text/licenses', 'screen_text/licenses'),
] if _SCREEN_TEXT else []
_SCREEN_TEXT_IMPORTS = ['onnxruntime', 'numpy'] if _SCREEN_TEXT else []
```

`Analysis(...)` 인자를 바꾼다:
- `datas=[...]` 리스트 닫는 괄호 뒤에 `+ _SCREEN_TEXT_DATAS`
- `hiddenimports=[...]` 리스트 닫는 괄호 뒤에 `+ _SCREEN_TEXT_IMPORTS`
- `excludes` 리스트의 `'numpy',` 줄을 지우고, 리스트 닫는 괄호 뒤에 `+ ([] if _SCREEN_TEXT else ['numpy'])`

- [ ] **Step 3: 라이선스 파일을 복사하고 고지를 쓴다**

```bash
mkdir -p screen_text/licenses
cp .venv/Lib/site-packages/onnxruntime/LICENSE screen_text/licenses/onnxruntime-LICENSE.txt
cp .venv/Lib/site-packages/onnxruntime/ThirdPartyNotices.txt screen_text/licenses/onnxruntime-ThirdPartyNotices.txt
cp .venv/Lib/site-packages/numpy-2.2.6.dist-info/LICENSE.txt screen_text/licenses/numpy-LICENSE.txt
```

`licenses/THIRD_PARTY_NOTICES.txt` 끝에 추가:

```
화면 글자 따기 (선택형 미니앱, screen_text/ 폴더와 함께 걷어낼 수 있음)
----------------------------------------------------------------------

PaddleOCR 모델 ONNX 변환본 (PP-OCRv3_mobile_det, korean_PP-OCRv5_mobile_rec)
  번들 파일: screen_text/models/det.onnx, rec.onnx, dict.txt
  라이선스 원문: screen_text/models/LICENSE (Apache License 2.0)
  출처·리비전·SHA-256: screen_text/models/MANIFEST.json

onnxruntime 1.30.0
  라이선스 원문: screen_text/licenses/onnxruntime-LICENSE.txt (MIT)
  제3자 고지: screen_text/licenses/onnxruntime-ThirdPartyNotices.txt

numpy 2.2.6
  라이선스 원문: screen_text/licenses/numpy-LICENSE.txt (BSD-3-Clause 및 번들 구성요소 고지)
```

Step 9의 Analysis TOC에서 `google/protobuf` 또는 `flatbuffers`가 실제로 포함됐으면, 그 패키지의 dist-info `LICENSE`를 `screen_text/licenses/`에 복사하고 같은 형식의 항목을 더한다. 포함되지 않았으면 작업 기록에 "미포함 확인"만 적는다.

`tests/test_packaging.py`의 `test_bundled_third_party_license_texts_and_notices_exist`는 바꾸지 않는다. 걷어낸 뒤에도 통과해야 하기 때문이다.

- [ ] **Step 4: 빌드 설정 테스트 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_packaging.py -v`
Expected: 모두 PASS

- [ ] **Step 5: 계약 문서를 쓴다**

`docs/SCREEN_TEXT.md`:

```markdown
# 화면 글자 따기 계약

다섯 번째 미니앱이며 **걷어낼 수 있는 선택형 앱**이다. 설계는 [설계 문서](superpowers/specs/2026-10-08-screen-text-capture-design.md), 구현·검증은 [작업 기록](work/2026-10-08-screen-text-capture.md)을 따른다.

## 동작
- 주머니 타일 → 도구 창 → [영역 고르기] → 화면이 멈추면 끌어서 선택(Esc·오른쪽 클릭 취소, 시작한 화면 안으로 제한) → 같은 창에 결과.
- 탭 [글자]/[표 모양]. 표가 감지되면 표 모양이 기본이다. 표 모양 복사는 탭 구분 글자와 HTML 표를 함께 넣고, 글자 복사는 일반 텍스트만 넣는다.
- 표 탭을 고치면 아직 손대지 않은 글자 탭이 다시 만들어진다. 글자 탭에서 고친 내용은 표 탭에 반영하지 않는다.
- 불확실한 곳(점수 미만, 숫자 열의 닮은 영문자)은 노랗게 표시만 하고 자동으로 고치지 않는다.
- 알려진 한계: 마침표 뒤 공백이 빠질 수 있다(예: `2026. 7. 1.` → `2026.7.1.`). 여러 줄 병합 셀은 첫 칸에만 들어간다. 많이 기울어진 스캔본은 지원하지 않는다.

## 엔진
- PP-OCRv3 mobile det + korean PP-OCRv5 mobile rec ONNX(Apache-2.0), onnxruntime CPU, numpy만 사용한다. 모델은 `screen_text/models/MANIFEST.json`의 크기·SHA-256이 맞을 때만 불러온다.
- 엔진은 처음 인식할 때 작업 스레드에서 불러오고, 사용자가 창을 닫거나 초기화·종료하면 내린다. 텔레메트리를 끈다. 네트워크를 쓰지 않는다.

## 데이터와 보안
- 찍은 화면 전체는 선택·취소 즉시 버린다. 잘라낸 영역과 결과는 메모리에만 두며 임시 파일을 만들지 않는다. 로그에는 오류 종류만 남긴다.
- DB v17·Export v2·salt·설정 키·바로가기 6슬롯을 바꾸지 않는다. 새 설정 키를 만들지 않는다.
- 캡처가 막히면(거의 검은 화면) 안내만 하고 우회하지 않는다.

## 수명 처리
- 공용 연결부(`optional_mini_apps.py` → `ui_main` 선택형 미니앱 메서드)를 따른다. 잠금: 취소·숨김·비활성(결과 유지). 트레이·사이드바·크기 변경·초기화 전: 취소·숨김. 화면 변경: 오버레이 닫기·화면 맞춤. 초기화 성공·종료: `shutdown()` 후 폐기.

## 걷어내기
1. `screen_text/` 폴더 삭제
2. `optional_mini_apps.py`의 등록 줄 삭제(`OPTIONAL_MINI_APPS = ()`)
3. `tests/test_screen_text_*.py` 삭제
4. `AGENTS.md`·`README_detail.md`·`docs/ARCHITECTURE.md`·`docs/TESTING.md`의 해당 항목, `licenses/THIRD_PARTY_NOTICES.txt`의 "화면 글자 따기" 절, `.gitattributes`의 모델 줄, 이 문서 삭제
5. (선택) `requirements.txt`·`requirements-lock.txt`·`tools/verify.py`·`tests/test_packaging.py`에서 onnxruntime·flatbuffers·protobuf 제거
6. `full` 검증 → 빌드 → EXE 크기 원복과 numpy 미포함 확인. `build.spec`은 폴더가 없으면 자동으로 원래 빌드가 된다.
```

- [ ] **Step 6: 정본 문서와 버전을 갱신한다**

1. `app_info.py`
   - `APP_VERSION = "v3.9"`
   - `APP_RELEASE_DATE`는 이 단계를 실행하는 날짜를 `"2026. 10. N."` 형식으로 넣는다.
   - 날짜 확인: `date +%Y-%m-%d`
2. `tests/test_ui.py`의 `test_settings_credit_uses_v38e_metadata`
   - 이름을 `test_settings_credit_uses_v39_metadata`로 바꾼다.
   - docstring의 `v3.8e`를 `v3.9`로 바꾼다.
   - 단언은 `assert APP_VERSION == "v3.9"`, `assert win.author_label.text().startswith(f"v3.9  ·  {APP_RELEASE_DATE}")`로 바꾼다(`from app_info import APP_RELEASE_DATE`가 없으면 추가).
3. `tests/test_packaging.py`의 버전 변환 테스트에 `assert _windows_version_parts("v3.9") == (3, 9, 0, 0)`을 더한다.
4. `AGENTS.md`
   - 이 작업 시작 전 원래 미커밋 변경은 그대로 둔다.
   - "반드시 보존할 계약" 목록의 미니앱 아이콘 규칙 앞에 아래 항목을 넣는다.
     > - 화면 글자 따기(v3.9)는 다섯 번째이자 첫 **선택형 미니앱**이다. `screen_text/` 폴더와 `optional_mini_apps.py` 등록 한 줄로만 연결되며 [걷어내기 절차](docs/SCREEN_TEXT.md)로 원래 빌드로 돌아간다. 소형 OCR 모델(Apache-2.0)과 onnxruntime 1.30.0을 PC 안에서만 쓰고, MANIFEST SHA-256 확인·텔레메트리 끔·캡처 이미지 메모리 전용·임시 파일 없음·차단 시 우회 금지를 유지한다. DB v17·Export v2·salt·설정 키·바로가기 6슬롯은 유지한다. 주머니는 앱 개수에 따라 2줄 280/3줄 390px이다. 아이콘은 예외적으로 `screen_text/icon.svg`(주황 `#FF9A4D→#D9480F`)다. 상세는 [계약](docs/SCREEN_TEXT.md)과 [작업 기록](docs/work/2026-10-08-screen-text-capture.md)을 따른다.
   - 아이콘 색 목록의 "예비: 주황"을 "사용 중: 주황(화면 글자 따기)"으로 바꾼다.
   - 미니앱 버튼 항목의 "4개를 제공하며"를 "4개와 선택형 화면 글자 따기를 제공하며"로 바꾼다.
5. `docs/ARCHITECTURE.md` Module Map 표에 두 행을 더한다.
   - `| optional_mini_apps.py | 걷어낼 수 있는 선택형 미니앱 등록부. 메인 창 공용 연결부와 주머니가 읽는다 |`
   - `| screen_text/ | 화면 글자 따기: layout(줄·표)·engine(PP-OCR ONNX)·capture(화면 멈춤)·window(도구 창). 계약은 docs/SCREEN_TEXT.md |`
6. `docs/TESTING.md`의 금액·숫자 표기 도우미 문단 다음에 한 문단을 넣는다.
   > 화면 글자 따기는 `tests/test_screen_text_layout.py`, `test_screen_text_engine.py`, `test_screen_text_capture.py`, `test_screen_text_ui.py`, `test_optional_mini_apps.py`를 함께 실행한다. 실제 화면을 찍지 않고 가짜 스크린샷과 Qt로 그린 합성 이미지만 쓴다. 125/150%는 `QT_SCALE_FACTOR` 합성 실행이며 실제 혼합 DPI/KVM·보안 프로그램 캡처 차단·한글 표 붙여넣기 확인을 대신하지 않는다.
7. `README_detail.md` 기능 목록의 미니앱 항목에 "화면 글자 따기(이미지·스캔 글자 인식, 표 모양 복사, PC 안 소형 AI 모델)"를 더한다.

- [ ] **Step 7: 전체 검사를 돌린다**

Run: `.venv/Scripts/python.exe tools/verify.py full`
Expected: 전체 pytest 통과, 실패·오류 0. 실행 ID와 테스트 수를 작업 기록에 적는다.

- [ ] **Step 8: 로컬 보안 검사를 돌린다**

Run:

```bash
output/harness/20260911-212909-security-6420ac33/bin/osv-scanner_windows_amd64.exe scan source -L requirements-lock.txt
```

Expected: `No issues found`. 지적이 있으면 멈추고 사용자에게 보고한다.

- [ ] **Step 9: release를 PowerShell에서 돌리고 EXE를 대조한다**

PowerShell(프로젝트 루트):

```powershell
.\.venv\Scripts\python.exe tools/verify.py release
```

Expected: 전체 pytest, 빌드, 격리 EXE 시나리오 3개 통과.

이어서 같은 실행 폴더(`output/harness/<run-id>/`)에서 확인해 작업 기록에 적는다.
- `build/build/Analysis-00.toc`
  - `screen_text\\models\\rec.onnx`, `onnxruntime\\capi\\onnxruntime.dll`, `numpy`가 있는지
  - `C:\\Program Files\\Git\\mingw64\\bin`의 DLL이 없는지
  - `google\\protobuf`·`flatbuffers` 포함 여부(Step 3의 고지 판단 근거)
- `dist/기후노트_v3.9.exe`의 크기와 SHA-256(`Get-FileHash -Algorithm SHA256`), v3.8e(59,049,343 bytes)와의 크기 차이
- 격리 데이터로 새 EXE 실행 → 주머니 → 화면 글자 따기 → 합성 이미지 영역 인식 1회(작업 기록에 결과 텍스트)

- [ ] **Step 10: 커밋한다**

```bash
git add build.spec tests/test_packaging.py tests/test_ui.py app_info.py screen_text/licenses licenses/THIRD_PARTY_NOTICES.txt docs/SCREEN_TEXT.md docs/ARCHITECTURE.md docs/TESTING.md README_detail.md docs/work/2026-10-08-screen-text-capture.md
git add -p AGENTS.md   # 이번 작업의 세 군데만 고른다. 원래 있던 미커밋 변경은 제외
git commit -m "build: 화면 글자 따기 빌드 분기·라이선스·문서와 v3.9

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`git add -p`로 원래 변경과 섞여 고르기 어려우면 AGENTS.md는 이 커밋에서 빼고 사용자에게 알린다.

---

### Task 9: 업무 PC 수동 확인과 공모전 실측

코드 작업은 없다. 사용자가 업무 PC에서 진행하고 결과를 작업 기록에 남긴다.

**Files:**
- Modify: `docs/work/2026-10-08-screen-text-capture.md`

- [ ] **Step 1: 사전 확인 두 가지**
  - `Win+Shift+S`로 화면 캡처가 되는지(보안 프로그램 차단 여부)
  - 보안 문서 뷰어 화면이 검게 찍히는지(검으면 차단 안내가 나와야 정상)

- [ ] **Step 2: 기능 확인**
  - Task 8의 `dist/기후노트_v3.9.exe`를 업무 PC에서 실행해 주머니 다섯 번째 타일이 3줄째에 보이는지 본다.
  - 스캔 공문 이미지의 본문과 표를 따서 [표 모양] 복사 → **한글**에 붙여넣기 → 표로 들어가는지 본다. 안 되면 `docs/SCREEN_TEXT.md`에 안내 문구를 추가할지 사용자와 정한다.
  - 같은 표를 **엑셀**에 붙여넣어 칸이 유지되는지 본다.
  - 혼합 DPI 모니터 또는 KVM 전환 뒤 보조 모니터에서 영역을 고르고, 잘린 위치가 맞는지 본다.
  - 잠금(Win+L) 직후 창과 오버레이가 사라지는지 본다.

- [ ] **Step 3: 공모전 실측 (실제 값만 기록)**
  - 표본: 이미지로 된 표 3개(행 10개 안팎)와 스캔 본문 3개. 실제 업무 문서는 PC 밖으로 내보내지 않는다.
  - 각 표본을 ① 직접 타이핑, ② 화면 글자 따기 + 확인·수정으로 옮기며 시간과 남은 오류 수를 잰다.
  - 가능하면 동료 몇 명이 같은 방법으로 잰다. 결과 표를 작업 기록에 적는다.

- [ ] **Step 4: 작업 기록을 마무리하고 커밋한다**

```bash
git add docs/work/2026-10-08-screen-text-capture.md
git commit -m "docs: 화면 글자 따기 업무 PC 확인과 실측 기록

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
