# 스티키 노트 Todo 체크박스 기능 설계

- 작성일: 2026-04-19
- 대상 파일: `ui_sticky.py` (주), `tests/test_ui_sticky.py` (신규 또는 확장)
- 원칙: 기존 사용자 데이터·DB 스키마 불변, 기존 HTML 저장 포맷 유지

## 1. 목적

스티키 노트에 "할 일" 개념을 도입한다. 사용자는 헤더 툴바의 체크박스 버튼으로 todo 줄을 생성하고, 인라인 체크박스(☐/☑)를 클릭해 완료 상태를 토글한다. 완료된 todo는 dim 색 + 취소선으로 표시되어 시각적으로 구분된다.

기존 "취소선(S)" 버튼은 제거된다. 완료 표시는 체크박스 토글로 충분히 대체되며, 자유 취소선이 더는 별도 버튼으로 필요하지 않다는 판단이다.

## 2. UI 변경

### 2.1 헤더 툴바

- `ui_sticky.py:228-235`의 `strike_btn` 블록 삭제 (선언·스타일·시그널 연결 모두).
- 같은 위치에 `todo_btn` 추가:
  - 라벨: `☐` 유니코드 문자 (인라인 체크박스와 시각적 일관성).
  - 툴팁: "할 일 추가".
  - 스타일: 기존 `_fmt_style` 재사용. 단 `setCheckable(False)` — 토글 버튼이 아님.
  - 시그널: `clicked.connect(self._insert_todo)`.
- `_update_format_buttons()` (`ui_sticky.py:361-365`)에서 `strike_btn.setChecked(...)` 라인 제거.

### 2.2 제거 대상

- 메서드 `_toggle_strikethrough()` (`ui_sticky.py:339-342`).
- 멤버 `self.strike_btn` 및 관련 임포트·참조 (전체 검색 후 정리).

기존 노트 HTML에 이미 저장된 취소선 서식은 문서 문자열에 남아있으므로 **표시는 그대로 유지**된다(데이터 보존 원칙). 새로 만드는 도구만 사라진다.

## 3. 데이터 모델

- DB 스키마·컬럼·암호화 경로 **변경 없음**.
- Todo 상태는 본문 HTML 내부의 유니코드 문자 + 서식으로만 표현:
  - 미완료 줄: `<p>☐ 텍스트</p>`
  - 완료 줄: `<p><span style="color:#888888">☑ </span><span style="color:#888888;text-decoration:line-through">텍스트</span></p>` (대략적 표현; Qt가 생성하는 실제 HTML은 다를 수 있음)
- `QTextEdit.toHtml()` / `setHtml()` 왕복으로 상태가 보존되어야 함. § 7 테스트에서 검증.

## 4. 상호작용 규칙

### 4.1 Todo 삽입 (`_insert_todo`)

- 현재 커서의 블록(paragraph) 텍스트가 비어있는가 확인.
- 비어있으면: 현재 위치에 `"☐ "` 삽입.
- 비어있지 않으면: `QTextCursor.insertBlock()`으로 새 블록 생성 후 `"☐ "` 삽입.
- 삽입 직전 `QTextCharFormat`을 초기화(취소선/dim 없는 기본 서식)하여 커서가 "깨끗한" 상태로 시작.
- 자동 저장 타이머는 기존 `textChanged` 시그널이 트리거함.

### 4.2 체크박스 토글 (`_toggle_todo_at`)

진입점: `self.text_edit`에 커스텀 서브클래스를 쓰거나 `text_edit.viewport().installEventFilter(self)`로 마우스 클릭 가로채기.

1. 왼쪽 싱글 클릭 발생 시 `cursorForPosition(event.pos())`로 문서 상 위치 계산.
2. 그 위치의 한 글자(`document.characterAt(pos)`)가 `☐` 또는 `☑`인지 확인.
3. 맞으면 이벤트 소비(`return True`)하고 해당 위치 토글 수행.
4. 토글 로직:
   - `☐` → `☑`: 문자 자체를 `☑`로 교체. 그 줄(블록) 범위 전체를 선택해 `QColor("#888888")`로 foreground 설정. 체크박스 이후(공백 포함 뒤 전체)만 추가로 `setFontStrikeOut(True)`.
   - `☑` → `☐`: 문자 자체를 `☐`로 교체. 그 줄 전체 foreground를 `QColor("#000000")`로, strikeout `False`.

### 4.3 Enter 키 동작 (`keyPressEvent` 오버라이드)

- `QTextEdit` 서브클래스 또는 `eventFilter`로 처리.
- Enter(Qt.Key_Return, Qt.Key_Enter) 처리 순서:
  1. 현재 블록 텍스트 `line` 조회.
  2. `line.startswith("☐ ")` 또는 `line.startswith("☑ ")`:
     - 체크박스 뒤 텍스트가 **비어있음**(줄이 정확히 `"☐ "` 또는 `"☑ "`): 현재 블록의 체크박스 부분을 지우고 기본 서식으로 복귀. Enter 자체는 소비(줄바꿈 발생 안 함).
     - 체크박스 뒤 텍스트가 **있음**: 기본 처리로 블록 분리 후, 새 블록 맨 앞에 `"☐ "` 삽입, char format 초기화.
  3. 그 외 일반 줄: 기본 처리.
- Shift+Enter는 기본 처리(줄바꿈 only; QTextEdit 기본 동작).

## 5. 시각적 처리 규칙

| 대상 | 취소선 | 색상 |
|---|---|---|
| `☑` 문자 | X | `#888888` |
| 공백 / 텍스트 | O | `#888888` |
| `☐` 문자 (미완료) | X | 기본색 `#000000` |
| 미완료 텍스트 | X | 기본색 `#000000` |

- 언체크 시 그 줄 전체를 `#000000` / strikeout=False로 되돌린다.
- **알려진 한계**: 사용자가 체크 전에 커스텀 텍스트 색(예: 파랑)을 적용해 둔 줄이라도, 체크→언체크 사이클 후에는 기본색으로 돌아간다. QTextCharFormat 사용자 정의 프로퍼티는 HTML 왕복 시 손실되므로 원본 색 완벽 복원은 비용 대비 효용이 낮다고 판단. 사용자는 필요 시 텍스트 색 버튼으로 재적용 가능.

## 6. 엣지 케이스 정책

- Backspace로 `☐`/`☑` 삭제 시 보호하지 않음 → 일반 줄로 자연 전환.
- 체크된 줄 내에서 추가 입력 시 dim·취소선 자연 상속(`mergeCurrentCharFormat` 기반).
- `☐`/`☑`를 붙여넣기한 경우: 토글 로직은 위치 기반이므로 정상 동작.
- 기존 v2.4 이전 노트 로드: 체크박스 문자가 없으므로 동작에 영향 없음. 기존 취소선 서식은 그대로 렌더.
- 블록 내에 줄바꿈(soft wrap)이 있어도 블록 단위로 서식이 적용되므로 문제없음. 단, 사용자가 Shift+Enter로 블록 내 개행을 만든 경우 **한 블록 = 한 todo**로 간주되어 전체에 서식 적용됨.

## 7. 테스트

`tests/test_ui_sticky.py` (존재하지 않으면 신규)에 pytest-qt(`qtbot`) 기반 추가:

- `test_todo_insert_on_empty_line`: 빈 블록에서 `todo_btn` 클릭 → 블록이 `"☐ "`가 됨.
- `test_todo_insert_on_nonempty_line`: "Hello"가 있는 줄에서 클릭 → 새 블록 생성 후 `"☐ "` 삽입, 기존 "Hello"는 보존.
- `test_todo_toggle_to_checked`: `☐` 위치 클릭 시뮬레이션 → 문자가 `☑`로 바뀌고 그 줄 foreground=`#888888`, 텍스트 부분 strikeout=True.
- `test_todo_toggle_to_unchecked`: `☑` 클릭 → `☐` 복귀, foreground=`#000000`, strikeout=False.
- `test_enter_on_todo_with_text_continues`: `"☐ 우유"` 끝에서 Enter → 새 블록이 `"☐ "`로 시작.
- `test_enter_on_empty_todo_exits`: `"☐ "` 상태에서 Enter → 블록이 빈 일반 줄이 됨.
- `test_html_roundtrip_preserves_state`: 체크·미체크 todo를 섞은 노트를 `toHtml()` → 새 `QTextEdit.setHtml()` 왕복 후 모든 문자·서식 보존 확인. **(사용자 데이터 보존 원칙 검증 — 필수)**
- `test_strike_button_removed`: 창에 `strike_btn` 속성이 존재하지 않음 확인(리그레션 방지).

## 8. 구현 범위 외

- 키보드 단축키로 토글하는 기능(브레인스토밍에서 제외됨).
- 완료된 todo 자동 숨김·정렬·통계.
- 체크 전 원래 텍스트 색 완벽 복원.
- Todo를 DB의 별도 구조로 분리 저장(현 스키마 유지가 데이터 보존 원칙에 부합).

## 9. 위험 및 완화

| 위험 | 완화 |
|---|---|
| QTextEdit HTML 왕복으로 체크 상태 서식 손실 | § 7 `test_html_roundtrip_preserves_state`로 검증 후 진행 |
| 마우스 클릭 위치 판정 오차(체크박스 바로 옆 클릭) | `cursorForPosition` + 해당 위치 글자가 정확히 `☐`/`☑`일 때만 토글. 옆 클릭은 일반 커서 이동 |
| Enter 동작이 IME(한글 조합 중)과 충돌 | 조합 중 Enter는 Qt가 먼저 처리하므로 `keyPressEvent`에는 조합 확정 후 Enter만 도달. 필요 시 `event.isAccepted()` 점검 추가 |
| 기존 노트에 우연히 `☐`/`☑` 문자가 있을 경우 | 그 문자도 토글 동작에 반응하게 됨. 사실상 해가 없고 오히려 자연스러움 (기존에 수동으로 쓴 체크박스도 동작) |
