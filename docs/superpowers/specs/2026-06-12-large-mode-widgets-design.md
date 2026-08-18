# 설계 문서 — '크게' 모드 위젯 통합 & 개수 제한

- 날짜: 2026-06-12
- 대상 버전: v3.1 → v3.2 (예정)
- 앱: 기후노트(`MyDesktopCalendar`)
- 진행: Codex (이 문서를 입력으로 구현 계획 수립)

## 1. 배경 / 문제

현재 동작:

1. **위젯 개수 제한이 불완전**하다.
   - 집중 모드: 생성은 1개로 제한(`ui_main.py:_on_new_focus_widget`)되고, 로드 시 초과분을 `is_open=0`으로 정리하지만(`_load_open_focus_widgets`) **(a) 가장 오래된(첫 번째) 위젯을 남기고, (b) 사용자에게 아무 안내가 없다.**
   - D-Day: 생성 상한이 **10개**(`_on_new_dday_widget`)이고, 로드 시 개수 제한이 **전혀 없다**(`_load_open_dday_widgets`).
2. **'크게'(large) 모드의 우측 사이드바에 일부 위젯만 들어간다.**
   - large 진입 시 플로팅 스티키 노트는 숨기고 우측 컬럼의 `StickySidePanel` 미니 카드로 대체한다(`_apply_sticky_side_panel`).
   - 그러나 **D-Day·집중 모드 위젯은 여전히 플로팅 상태로 남아** 사이드바에 통합되지 않는다.
3. **스티키 미니 패널의 기능이 플로팅 창보다 빈약하다.**
   - `StickyMiniCard`는 `_TodoTextEdit`를 써서 체크박스 클릭 토글은 되지만, **굵게·할 일 삽입·텍스트/배경 색상 툴바와 삭제(X) 기능이 없다.**

## 2. 목표 / 비목표

### 목표
- 집중 모드 위젯 **최대 1개**, D-Day 위젯 **최대 5개**로 제한.
- 구버전 DB에 상한 초과 위젯이 있으면, 새 빌드 첫 실행 시 **가장 최근(마지막) N개만 남기고** 나머지를 정리하고 **모달 경고창**으로 안내.
- 'large' 모드 우측 사이드바에 **일정 · D-Day · 집중 모드 · 스티키 노트**를 모두 수용. 스티키가 메인, D-Day·집중은 미니 표시.
- 스티키 미니 패널을 플로팅 창과 **기능 동기화**: 공통 서식 툴바(굵게·할 일·텍스트 색상·배경 색상) + 카드별 삭제(X).

### 비목표 (이번 범위 아님)
- D-Day / 집중 모드 휴지통(soft-delete) 도입. (스티키만 휴지통 유지)
- 위젯 데이터 스키마 변경(컬럼 추가/삭제 없음).
- 일정/메모 위젯의 미니화 변경(일정 패널은 기존 동작 유지).
- 색상 팔레트·집중 모드 모드명 등 기존 UI 규약 변경.

## 3. 핵심 제약 (반드시 준수)

`AGENTS.md` 규약을 그대로 따른다.

- **데이터 보존**: 초과 위젯은 **삭제 금지**, `is_open=0`으로 보존(복구 가능 상태). 스키마 변경 없음.
- **DB 접근**: 반드시 `database.py`의 `_connection()` 컨텍스트 매니저. 직접 `sqlite3.connect()` 금지.
- **암호화**: `goal`(집중), `name`(D-Day), 스티키 `content`는 기존 암호화 경로 유지.
- **예외 처리**: `bare except:` 금지(0024), `except + pass` 단독 금지(0023). 예외는 타입별 세분화 + 로깅.
- **리소스**: Qt 다이얼로그/팝업은 사용 후 `deleteLater()`. 파일은 `with open`.
- **폰트**: 체크박스 아이콘은 Font Awesome 고정(`_FA_FAMILY`). QSS `font-size`는 정수 px.
- **QSS 스코프**: bare 규칙 금지, `#objectName`/타입 선택자로 스코프(컨텍스트 메뉴 전파 방지).

## 4. 기능 1 — 위젯 개수 제한 + 업그레이드 정리

### 4.1 상한
| 위젯 | 상한 | 비고 |
|---|---|---|
| 집중 모드 | 1 | 기존 1 유지 |
| D-Day | 5 | 기존 10 → 5 |

### 4.2 신규 함수 `database.py`

```text
def enforce_widget_limits() -> dict[str, int]:
    """is_open=1 위젯을 상한 이내로 정리. 최신(id 큰) N개만 남기고
    나머지는 is_open=0 (데이터 보존). 멱등. 정리된 개수를 반환."""
    # 반환 예: {"focus": 2, "dday": 3}  (정리된 초과분 개수)
```

규칙:
- 집중: `SELECT id FROM focus_widgets WHERE is_open=1 ORDER BY id DESC` → 첫 1개 유지, 나머지 `UPDATE ... SET is_open=0`.
- D-Day: 동일 패턴, 첫 5개 유지.
- 단일 `_connection()` 트랜잭션 내 처리, `commit()` 1회.
- 아무것도 정리하지 않으면 `{"focus": 0, "dday": 0}` 반환.
- `sqlite3.Error`는 상위로 전파(호출부에서 로깅). 함수 내부 silent pass 금지.

추가로 `get_open_dday_widgets()` / `get_open_focus_widgets()` 쿼리에 **`ORDER BY id`** 명시(결정적 로드 순서; "최신 유지"와 정합).

### 4.3 호출 위치 & 경고 (`ui_main.py`)

- `MainCalendarWindow.__init__`에서 위젯 로드(`_load_open_dday_widgets`/`_load_open_focus_widgets`) **이전**에 `result = db.enforce_widget_limits()` 호출(예외는 `_logger.error`로 로깅 후 빈 결과로 처리).
- `result["focus"] > 0 or result["dday"] > 0`이면, 메인 창 `show()` 이후 `QTimer.singleShot`으로 **모달 경고창** 표시.
  - 구현: `qfluentwidgets`의 `Dialog`(또는 `MessageBox`) 사용, `setWindowModality(Qt.ApplicationModal)`, 사용 후 `deleteLater()`.
  - 문구 예: "이전 버전에서 만든 위젯이 많아 일부를 정리했습니다.\n집중 모드는 1개, D-Day는 최신 5개만 남기고 나머지는 닫았습니다(데이터는 보존)."
  - 정리된 개수가 0인 종류는 문구에서 제외(둘 다 0이면 경고 자체를 띄우지 않음).
- 멱등성 덕분에 정리 후 재실행에서는 초과분이 없어 경고가 다시 뜨지 않음 → 사실상 업그레이드 직후 1회만 노출.

### 4.4 기존 로직 정리

- `_load_open_focus_widgets`의 `if idx >= 1: db.update_focus_widget(..., is_open=0)` 임시 정리 블록 **제거**(enforce가 최신 유지로 대체). 이후 로드는 단순히 열린 위젯을 표시.

### 4.5 생성 제한 카운트 버그픽스

`_on_new_focus_widget` / `_on_new_dday_widget`의 `open_count`가 현재 `w.isVisible()` 기반이라, large 패널 모드(위젯 숨김)에서는 0으로 세어 **제한이 우회**된다.

- 카운트를 **DB의 `is_open=1` 개수** 기준으로 변경:
  - `len(db.get_open_focus_widgets())` 또는 등록 딕셔너리(`self._focus_windows`) 길이 등 **표시 모드와 무관한 값** 사용.
- 집중 `>= 1`, D-Day `>= 5`일 때 `InfoBar.warning`(문구의 "10개"를 "5개"로 수정).

## 5. 기능 2 — 'large' 모드 사이드바 통합

### 5.1 레이아웃 (선택안 A: 세로 스택)

우측 컬럼(`_expanded_row`, QVBoxLayout)을 다음 순서로 구성:

```
일정(schedule_panel)   stretch 2
D-Day 미니 패널        stretch 2 (또는 콘텐츠 기반 고정+최대)
집중 미니 패널/카드     stretch 1
스티키 미니 패널        stretch 6  ← 메인(가장 큼)
```

- 정확한 stretch는 구현 시 시각 균형에 맞춰 조정하되 **스티키가 우세**해야 한다.
- D-Day는 최대 5개라 **세로 컴팩트 리스트**(필요 시 자체 스크롤). 집중은 1개 고정.
- 모서리 라운딩: 현재 `schedule_panel`/`StickySidePanel`이 우상단/우하단 모서리를 처리하는 방식과 동일하게, **맨 위 패널은 상단 모서리, 맨 아래(스티키) 패널은 우하단 모서리만** 라운드. 중간 패널은 각지게 두어 사이로 배경이 새지 않게 한다.
- `medium` 모드는 현재처럼 미니 패널 미적용(플로팅 유지). **large 전용**.

### 5.2 미니 패널 신설

`StickySidePanel`(`ui_sticky_panel.py`)을 템플릿으로 동일 패턴 적용.

- **D-Day**: 신규 `ui_dday_panel.py`
  - `DDayMiniCard(QWidget)`: 색상 스트립/배경 + 이름 + D-카운트 텍스트. 더블클릭 → `DDayCreateDialog` 재사용(편집), 색상 변경 지원(`_ColorGridPopup`). 1분 주기 카운트다운 갱신은 패널 단위 타이머 1개로 일괄 처리(개별 타이머 남발 회피).
  - `DDaySidePanel(QWidget)`: 제목 "D-Day" + 카드 리스트. `reload()`는 `db.get_open_dday_widgets()`로 재구성. `save_all()` 불필요(D-Day는 즉시 저장 모델).
- **집중**: 신규 미니 카드(별도 `ui_focus_panel.py` 또는 `ui_focus.py` 내 클래스).
  - 표시: 진행 링(또는 막대) + 목표 + `NN%` + 남은 시간 `MM:SS`.
  - **라이브 타이머**(결정사항): 플로팅 집중창(`FocusWidgetWindow`)을 **파괴하지 않고 숨긴 채 유지**하여 내부 `FocusTimer`가 계속 tick하고 완료/휴식/회고 다이얼로그를 그대로 소유한다. 미니 카드는 매초(또는 그 창의 신호) 그 모델을 **미러링**하고, 클릭 시 일시정지/재개를 **플로팅 창에 위임**한다.
  - 따라서 집중은 다른 위젯과 달리 "숨김+미러"이며, 미니 카드는 표시·입력 위임만 담당(타이머 상태의 단일 출처는 플로팅 창의 `FocusTimer`).

### 5.3 패널 진입/이탈 통합 (`ui_main.py`)

- 신규 `_apply_dday_side_panel(large: bool)` / `_apply_focus_side_panel(large: bool)`를 `_apply_sticky_side_panel`과 같은 구조로 작성하고, `_apply_calendar_scale`에서 `scale == "large"`로 함께 호출.
- 진입(large) 시:
  - D-Day: 플로팅 창 `hide()`(데이터 즉시 저장 모델이라 별도 save 불필요), 미니 패널 `reload()`.
  - 집중: 플로팅 창을 **숨김 유지**(타이머 계속 동작), 미니 카드 미러링 시작.
  - 상태 플래그 `self._dday_in_panel_mode` / `self._focus_in_panel_mode` 도입(스티키의 `_sticky_in_panel_mode`와 동일 패턴).
- 이탈(비-large) 시:
  - 미니 패널 분리/`hide()`/`setParent(None)`.
  - D-Day 플로팅 재표시(`isVisible` 조건은 메인 창 표시 여부 따름).
  - 집중 플로팅 재표시(이미 살아 있으므로 `show()`만).
  - DB 최신값 반영이 필요한 경우(D-Day 편집 등) 플로팅에 재로드.
- 자동정렬(`_on_arrange_sticky_notes`)·투명도 broadcast·화면 변경 reload는 기존처럼 `isVisible()` 필터를 쓰므로, 패널 모드에서 숨겨진 위젯은 자연히 제외된다(스티키와 동일). 단, **집중은 숨겨도 살아 있으므로** 정렬 대상에서 빠지는지 확인(현재 `isVisible()` 필터로 제외됨 — 의도대로).

### 5.4 패널 모드 중 신규 생성

`_on_new_dday_widget` / `_on_new_focus_widget`에서, 생성 후 패널 모드면 스티키 생성부(`ui_main.py:1862` 인근)처럼:
- 플로팅 창을 `hide()`(집중은 숨김 유지),
- 해당 미니 패널 `reload()`.

## 6. 기능 3 — 스티키 미니 패널 기능 동기화

### 6.1 공용 서식 추출 (DRY)

현재 `StickyNoteWindow` 내부에 갇힌 서식 로직을 **재사용 가능한 형태로 추출**한다. 위치는 `ui_sticky.py`(또는 신규 `sticky_format.py`).

추출 대상:
- 헬퍼 함수: `toggle_bold(text_edit, on: bool)`, `insert_todo(text_edit)`, `apply_text_color(text_edit, hex)`, `bold_state(text_edit) -> bool`.
- 위젯: `_TextColorButton`(이미 독립적), 버튼 공통 스타일 상수(`_fmt_style`).
- 재사용 가능한 **`StickyFormatToolbar(QWidget)`**: 굵게/할 일/텍스트 색상(/배경 색상) 버튼을 담고, "현재 대상 `QTextEdit`"를 콜백/세터로 받아 동작.

리팩터링 원칙: **동작 변화 없이** 추출만 한다. `StickyNoteWindow`는 추출된 헬퍼/툴바를 사용하도록 내부만 교체(외부 동작·외형 동일). 기존 체크박스/Enter/dim+취소선 규약(`_TodoTextEdit`)은 그대로.

### 6.2 공통 편집 툴바 (`StickySidePanel` 헤더)

- 패널 상단 제목("스티키 노트") 옆/아래에 **공통 `StickyFormatToolbar` 1개** 배치: **굵게 / 할 일 / 텍스트 색상 / 배경 색상**.
- 동작 대상 = **현재 포커스된 `StickyMiniCard`**.
  - 각 `StickyMiniCard`가 자신의 `text_edit` 포커스-인 시 패널에 알림(예: 카드에 `focused = Signal(object)` 추가, `_TodoTextEdit.focusInEvent` 오버라이드 또는 이벤트 필터). 패널은 `_active_card`를 갱신.
  - 툴바 버튼은 `setFocusPolicy(Qt.NoFocus)`로 두어 클릭해도 카드 텍스트의 선택/커서가 유지되게 한다.
  - 굵게 버튼 체크 상태는 활성 카드의 `cursorPositionChanged`에 맞춰 `bold_state()`로 동기화.
  - 활성 카드가 없으면 툴바는 비활성(`setEnabled(False)`) 또는 무동작.
- **배경 색상**: 활성 카드(노트)의 `color`를 변경 → `db.update_sticky_note(note_id, color=...)` + 카드 외형 갱신(헤더 스트립·테두리). 플로팅과 동일한 `STICKY_COLORS`/`STICKY_HEADER_COLORS` 사용.

### 6.3 카드별 삭제(X) 버튼

- 각 `StickyMiniCard`에 작은 X 버튼(우상단, `TransparentToolButton(FIF.CLOSE)` 등). 색상 스트립 영역과 겹치지 않게 배치.
- 클릭 → 확인 다이얼로그(플로팅과 동일 톤: "이 노트를 휴지통으로 이동하시겠습니까?") → `db.trash_sticky_note(note_id)`(휴지통 soft-delete, 기존 정책).
- 패널은 상위로 **`note_trashed = Signal(int)`** 방출 → `MainCalendarWindow`가 수신해:
  - `self._sticky_windows`에서 해당 플로팅 창 정리(`close()`/`deleteLater()`/pop) — 모드 이탈 시 부활 방지.
  - 패널 `reload()`.
- 확인 다이얼로그는 사용 후 `deleteLater()`.

### 6.4 양방향 동기화

- 미니 카드 편집(텍스트·서식·체크·색상)은 기존 2초 디바운스 `_auto_save`로 DB 저장.
- 모드 이탈 시 `save_all()` 후 `_restore_floating_sticky_content()`가 플로팅 창 본문을 DB 최신값으로 재로드(기존 메커니즘) → 플로팅에 반영.
- 신규 노트 생성·삭제도 패널 reload로 즉시 반영(기존 흐름 유지).

## 7. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `database.py` | `enforce_widget_limits()` 신설, `get_open_dday_widgets`/`get_open_focus_widgets`에 `ORDER BY id` |
| `ui_main.py` | enforce 호출+모달 경고, 생성 카운트 버그픽스(isVisible→DB), D-Day/집중 미니 패널 진입·이탈·생성 통합, `note_trashed` 수신 |
| `ui_sticky.py` | 서식 헬퍼/툴바 추출(동작 무변경), `StickyNoteWindow` 내부 교체 |
| `ui_sticky_panel.py` | 공통 서식 툴바, 카드 포커스 추적, 카드별 X(휴지통), `note_trashed` 시그널, 배경색 변경 |
| `ui_dday_panel.py` (신규) | `DDayMiniCard`/`DDaySidePanel` |
| 집중 미니 (`ui_focus_panel.py` 신규 또는 `ui_focus.py`) | 라이브 미러 미니 카드 |
| `AGENTS.md` | 모듈맵/제약 갱신(아래 9장) |

## 8. 테스트 계획 (`tests/`, pytest-qt)

데이터 변경 기능이므로 왕복 검증 필수.

- `enforce_widget_limits`:
  - 집중 3개(is_open=1) → 실행 후 최신 id 1개만 is_open=1, 나머지 is_open=0(행 삭제 안 됨), 반환 `{"focus": 2, ...}`.
  - D-Day 7개 → 최신 5개 유지, 2개 닫힘, 반환 `{"dday": 2}`.
  - 상한 이하 → 변화 없음, `{0,0}`. **멱등**(연속 2회 호출 시 2회차 `{0,0}`).
  - 보존 검증: 닫힌 위젯의 `goal`/`name`/`target_date` 등 데이터 복호화 왕복 일치.
- 생성 제한: 패널 모드(위젯 숨김)에서도 집중 2개째/D-Day 6개째 생성이 차단되는지(카운트가 DB 기준인지).
- 스티키 미니 패널: 툴바 굵게/할 일 삽입/색상 적용 후 `toHtml()` 저장→재로드 시 서식 유지. X 삭제 시 `is_deleted=1`·`is_open=0`, 휴지통 목록에 등장, 플로팅 레지스트리에서 제거.
- large↔compact 전환 라운드트립: D-Day/집중/스티키가 플로팅↔미니로 오갈 때 데이터·표시 일관, 집중 세션 연속성(타이머 끊김 없음).
- 회귀: 기존 스티키/포커스/디데이 테스트 통과.

## 9. AGENTS.md 갱신 항목 (구현 후)

- 모듈맵: `ui_dday_panel.py`, 집중 미니 모듈 추가. `ui_sticky.py`에 서식 추출(`StickyFormatToolbar`) 명시. `ui_sticky_panel.py`에 공통 툴바/X 삭제/`note_trashed` 명시.
- 제약:
  - "집중 모드 위젯 제한"·"D-Day 위젯 제한(최대 5)" 갱신, `enforce_widget_limits` 멱등 정리 + 모달 경고 규약.
  - "확장 캘린더(large)" 항목: 우측 컬럼이 [일정·D-Day(미니)·집중(미니, 라이브)·스티키(메인)] 4구획임을 명시. 집중은 숨김+미러 방식.
  - 스티키 미니 패널 공통 서식 툴바·휴지통 X 동작 명시.
- `database.py`: `enforce_widget_limits()` 추가 기재.

## 10. 결정 기록 (Resolved)

| 항목 | 결정 |
|---|---|
| large 레이아웃 | A — 세로 스택(일정→D-Day→집중→스티키), 스티키 우세 |
| 집중 미니 | 라이브 타이머(숨긴 플로팅창 tick 유지 + 미니 미러) |
| D-Day 미니 | 편집 가능(더블클릭 편집 + 색상) |
| 업그레이드 경고 | 모달 경고창(차단형), 정리 개수>0일 때만 |
| 정리 기준 | 최신(id 큰) N개 유지, 나머지 `is_open=0` 보존 |
| 정리 트리거 | `enforce_widget_limits()` 멱등 함수, 시작 시 1회(스키마/`user_version` 변경 없음) |
| 스티키 툴바 | `StickySidePanel` 헤더에 공통 툴바 1개, 포커스된 카드에 적용 |
| 스티키 삭제 | 카드별 X → 휴지통(soft-delete), `note_trashed`로 플로팅 정리 |

## 11. 리스크 / 주의

- **집중 라이브 미러**가 가장 복잡. 숨긴 플로팅 창이 완료/휴식/회고 모달을 띄울 때, 부모가 숨겨진 상태에서 다이얼로그 위치/모달성 확인 필요(필요 시 부모를 메인 창으로 지정).
- 패널 진입/이탈 시 `setParent`/`removeWidget` 순서로 레이아웃 깜빡임 또는 배경 누수 가능 — 기존 `_apply_sticky_side_panel`의 재부착 순서 주의(일정→D-Day→집중→스티키 고정).
- 공통 툴바가 별도 위젯의 텍스트에 작용하므로 **포커스/선택 유지**(NoFocus)와 활성 카드 추적의 정확성이 관건.
- 카운트 버그픽스로 제한 동작이 바뀌므로 기존 사용자 흐름 회귀 테스트 필요.
