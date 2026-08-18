# 설정 창 레이아웃 재설계 설계

- 작성일: 2026-06-11
- 대상 앱: 기후노트 (MyDesktopCalendar) v3.0 (UI 개선, 기능 불변)
- 스키마: 변경 없음 (DB·설정 키 그대로)

## 1. 배경 / 문제

현재 설정 창(`ui_settings.py`, 800×560 무스크롤 2열)은 `_make_card()` 카드들을
좌/우 칼럼에 평면적으로 쌓는 구조다. 사용자가 비주얼 검토에서 다음 3가지를 거슬리는
점으로 직접 골랐다.

- **② 우측 컨트롤 정렬선이 들쭉날쭉** — 스위치·콤보·슬라이더·버튼·PIN 입력의 폭이 제각각이라 오른쪽 가장자리가 정렬되지 않는다.
- **④ 섹션이 두 칼럼에 흩어져 시선 흐름이 끊김** — 어느 칼럼부터 봐야 할지 모호하고 그룹 경계가 약하다.
- **⑤ 제목 위계가 약함** — 섹션 제목(`StrongBodyLabel`)과 카드 제목(`SubtitleLabel`)의 크기가 비슷해 그룹 구분이 잘 안 보인다.

## 2. 목표

- 위 ②·④·⑤를 해결하도록 **배치/정렬/위계만** 재구성한다.
- **기능은 100% 동일**하게 유지한다 — 설정 항목·핸들러·콜백 시그니처·저장 키·동작 모두 그대로.
- 창은 **800×560 고정·무스크롤**을 유지한다(`ScrollArea` 도입 금지).
- 부수 요청: **캘린더 크기** 컨트롤을 콤보 드롭다운 → **일러스트 선택 picker**로 교체(저장값·동작 동일).

## 3. 사용자 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| 개편 범위 | **배치 전면 재구성**. 창 고정크기·무스크롤은 유지, 섹션→열 매핑/정렬 규칙은 새로 짠다 |
| 레이아웃 방식 | **Approach C — 섹션 패널(카드 박스) 2열**. 각 섹션을 테두리 패널로 감싸 그룹을 또렷이 |
| 캘린더 크기 컨트롤 | 콤보 → **일러스트 picker**. 동일 크기 **모니터** 3개 안에서 **파란 앱**이 차지하는 **면적**만 기본/중간/크게로 다름 |
| picker 그림 톤 | 단순화. 모니터(화면) 고정 + 모서리에 놓인 파란 앱 블록(남색 머리띠 + 파란 본체)의 면적만 변화 |
| 기능 | 추가/삭제 없음. 전 항목 보존 |

## 4. 접근법 결정

**레이아웃: 채택 = Approach C (섹션 패널 2열).**
- 패널 경계가 그룹을 시각적으로 분리 → ④(흐름)·⑤(위계)에 가장 강하다.
- 패널 헤더(남색·굵게·옅은 바탕 바)로 섹션/행 위계가 명확히 분리된다.
- 기각: **A(균형 2열 스택)** 는 변화가 작아 ④ 해결이 약함. **B(풀폭 섹션 밴드)** 도 좋은 후보였으나, 사용자가 "윈도우 설정 앱" 느낌의 또렷한 그룹 박스(C)를 선호.

**캘린더 크기: 채택 = 모니터 고정 + 앱 면적 picker.**
- "캘린더 크기"의 사용자 멘탈모델은 "내 모니터에서 앱이 얼마나 큰 공간을 쓰나"이다. 모니터를 고정하고 앱 면적만 키우면 그 비교가 직관적으로 보인다.
- 기각안: (1) 달력 그리드가 커지는 그림 — 모니터 대비 점유 면적이 안 보임. (2) 콤보 유지 — 부수 요청과 어긋남.

## 5. 상세 설계 — `ui_settings.py`

`SettingsWindow._build_ui()` 의 골격(제목 / 2열 `content_grid` / 하단 `bottom_row`)과
모든 컨트롤 **생성 코드·핸들러는 재사용**한다. 바뀌는 것은 **컨트롤을 담는 컨테이너**
(`_make_card`/`_section_header` → 패널/행 헬퍼)와 **캘린더 크기 위젯**뿐이다.

### 5.1 신규 헬퍼: 패널과 행

`_make_card()` / `_section_header()` 를 다음 두 헬퍼로 대체(또는 추가)한다.

```python
def _make_panel(self, title: str) -> tuple:
    """섹션 패널: 헤더(StrongBodyLabel) + 내부 행 레이아웃(body) 반환"""
    panel = CardWidget(self)
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
    header = StrongBodyLabel(title, panel)          # ← 섹션명을 그대로 담는다(기존 테스트 호환)
    header.setObjectName("panelHeader")
    header.setStyleSheet(
        "#panelHeader{font-size:12px;font-weight:800;color:#01295F;"
        "background:#EDF1F6;border-bottom:1px solid #D7DDE5;padding:6px 10px;}")
    v.addWidget(header)
    body = QVBoxLayout(); body.setContentsMargins(10, 2, 10, 6); body.setSpacing(0)
    v.addLayout(body)
    return panel, body

def _add_row(self, body, label: str, control) -> QWidget:
    """라벨-좌 / 컨트롤-우(고정폭 우측 레일). control 은 위젯 또는 컨테이너 위젯."""
    row = QWidget(self)
    h = QHBoxLayout(row); h.setContentsMargins(0, 6, 0, 6); h.setSpacing(8)
    lbl = BodyLabel(label, row); lbl.setStyleSheet("font-size:12px;font-weight:600;")
    h.addWidget(lbl, 1)
    h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
    body.addWidget(row)
    return row
```

- **② 정렬 해결**: 라벨은 stretch=1로 늘고, 컨트롤은 우측 정렬된다. 각 패널의
  행 컨트롤 컨테이너는 **공통 최소폭**(예: `setMinimumWidth(150)`)을 가져 오른쪽
  정렬선이 통일된다. 복합 컨트롤(콤보+그리드, 슬라이더+%, PIN+버튼 등)은 기존처럼
  작은 컨테이너 `QWidget`로 묶어 `control` 인자로 넘긴다(기존 sub-layout 그대로 이식).
- **⑤ 위계 해결**: 섹션 = 패널 헤더 바, 행 라벨은 12px 일반. 헤더는 `StrongBodyLabel`
  유지(섹션명 텍스트 포함)이므로 기존 `test_settings_has_five_section_headers` 가
  변경 없이 통과한다.
- 행 사이 옅은 점선 구분선이 필요하면 행 하단 1px 보더로 추가(선택). 폰트는 정수 px만.

### 5.2 섹션 패널 매핑 (④ 흐름)

`content_grid` 의 좌/우 칼럼 `QVBoxLayout`에 패널을 쌓는다. 항목/순서는 현재와 동일.

| 좌열 | 우열 |
|---|---|
| **화면 표시**: 모니터 및 위치 · 전체 투명도 · **캘린더 크기(picker)** · 음력 및 공휴일 | **데이터**: 내보내기 · 가져오기 · 저장 경로 |
| **위젯·도구**: 바로가기 · AI 법령검색 | **보안**: 개인정보 잠금 · 데이터 초기화 |
| (stretch) | **시스템**: 자동 실행 · 앱 글꼴 |

하단 전폭 바(`라이선스` / 크레딧 / `앱 종료`)는 현재 코드 그대로 둔다.

### 5.3 신규 위젯: `CalendarSizePicker`

`ui_settings.py` 내에 위젯 클래스로 정의(유일 소비자와 co-locate). 외부 이미지 없이
중첩 `QFrame` + QSS 로 그린다(서드파티·플랫폼 리소스 회피, 정수 px).
(`PySide6.QtCore` import 에 `Signal` 추가, `QFrame` 사용을 위해 `QtWidgets` import 보강 필요.)

```python
class CalendarSizePicker(QWidget):
    scaleChanged = Signal(str)
    _SCREEN = (46, 30)                                   # 모니터(화면) 고정 크기
    _SCALES = [("compact", "기본", (16, 10)),            # (값, 캡션, 앱 블록 크기)
               ("medium",  "중간", (26, 16)),
               ("large",   "크게", (36, 22))]

    def __init__(self, current: str, parent=None): ...    # 3개 _ScaleOption 생성, current 선택
    def select(self, value: str) -> None: ...             # 하이라이트 갱신 + scaleChanged.emit(value)
    def current_scale(self) -> str: ...
```

- `_ScaleOption(QFrame)`: 세로 [ `_Monitor` , 캡션 `BodyLabel` ]. 클릭 시 부모 `select(value)`.
  선택된 옵션은 `setProperty("selected", True)` + `style().polish()` 로 파란 테두리/배경.
- `_Monitor(QFrame)`: 고정 `_SCREEN` 크기, 옅은 화면 배경 + 테두리. 자식 **앱 블록**
  `QFrame`을 우측 하단(2px 인셋, 실제 기본 위치와 동일한 모서리)에 `setGeometry`로 배치.
  앱 블록 스타일 = 파란 본체 + 상단 남색 머리띠:
  `background:#2566B8; border-top:3px solid #01295F; border-radius:2px;`
- 3옵션 가로 배치. 모니터는 모두 같은 크기, 앱 블록 면적만 다름 → "점유 면적" 직관 전달.
- 전체 폭 ≈ 3×(옵션 ~60px) ≈ 180px 로 우측 레일에 들어가고, 행 높이만 ~16px 늘어
  무스크롤(800×560)을 유지한다(구현 시 실측 확인).

### 5.4 `SettingsWindow` 배선 변경

- 기존 `scale_combo` 생성/연결 블록(현 252–265행) 제거, 다음으로 대체:
  ```python
  self.scale_picker = CalendarSizePicker(
      db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE), self)
  self.scale_picker.scaleChanged.connect(self._on_scale_changed)
  ```
  그리고 `화면 표시` 패널의 "캘린더 크기" 행 `control` 로 `self.scale_picker` 를 넘긴다.
- `_on_scale_changed` 시그니처를 **index → scale: str** 로 변경(동작 동일):
  ```python
  def _on_scale_changed(self, scale: str):
      if not scale:
          return
      db.save_setting(db.SETTING_CALENDAR_SCALE, scale)
      if self.on_scale_changed:
          self.on_scale_changed()
  ```

### 5.5 기능 불변 보장 (핸들러·콜백 매핑)

| 항목 | 위젯 | 핸들러 | 변경 |
|---|---|---|---|
| 모니터 및 위치 | `monitor_combo` + `_position_btns`(4) | `_on_monitor_changed`/`_on_position_changed` | 컨테이너만 이동 |
| 전체 투명도 | `opacity_slider`(+`opacity_value_label`) | `_on_opacity_changed` | 이동 |
| **캘린더 크기** | ~~`scale_combo`~~ → **`scale_picker`** | `_on_scale_changed`(index→str) | **위젯·시그니처 교체, 동작 동일** |
| 음력 및 공휴일 | `lunar_switch` | `_on_lunar_toggled` | 이동 |
| 바로가기 | `sidebar_switch` | `_on_sidebar_toggled` | 이동 |
| AI 법령검색 | `law_search_switch` | `_on_law_search_toggled` | 이동 |
| 내보내기 | `export_pin`+버튼 | `_on_export` | 이동 |
| 가져오기 | `import_pin`+버튼 | `_on_import` | 이동 |
| 저장 경로 | `open_data_folder_btn` | `_on_open_data_folder` | 이동 |
| 개인정보 잠금 | `privacy_switch`+`pin_container`(`privacy_pin_edit`) | `_on_privacy_lock_toggled`/`_on_save_privacy_pin` | 이동 |
| 데이터 초기화 | `factory_reset_btn`(빨강) | `_on_reset` | 이동(색/아이콘 규칙 유지) |
| 자동 실행 | `startup_switch` | `_on_startup_toggled` | 이동 |
| 앱 글꼴 | `font_combo` | `_on_font_changed` | 이동 |
| 라이선스 / 앱 종료 | 하단 바 / `quit_app_btn`(검정) | `_on_license`/`_on_quit` | 그대로 |

> 모든 위젯의 `setObjectName`/속성 이름은 그대로 유지한다(테스트·QSS 규칙 의존).

## 6. 무스크롤·크기 적합성

- `ScrollArea` 도입 금지(`test_settings_has_no_scroll_area` 유지).
- 좌열 행 수(화면 표시 4 + 위젯·도구 2)와 우열(데이터 3 + 보안 2 + 시스템 2)은
  현재와 동일하며, 패널 헤더(~28px×5)와 picker 추가 높이(~16px)만 늘어난다.
  800×560 내에 들어가도록 패널 마진/행 패딩을 조정하고 **구현 후 실제 창에서 확인**한다.
- 폰트 크기는 QSS 정수 px만 사용.

## 7. 보안 코딩 규칙 준수 (행안부 CODEMIND 4.5)

- UI 전용 변경이라 데이터·암호화 경로는 건드리지 않는다(Export/Import/PIN 로직 그대로).
- 새 위젯에서 만드는 일회성 팝업이 있으면 `deleteLater()` (0026_RESLEAK). 본 설계에는
  picker가 팝업을 만들지 않음.
- 예외 처리 신설 없음. 기존 핸들러의 타입별 예외 처리 유지(0023/0024).

## 8. 테스트 (`tests/test_ui.py`)

UI 전용·비데이터 변경이므로 왕복 DB 테스트는 불필요. 다음만 갱신/추가한다.

- **갱신(필수)**: `test_settings_scale_combo_persists_and_calls_callback`
  → `test_settings_scale_picker_persists_and_calls_callback` 로:
  ```python
  win = SettingsWindow(on_scale_changed=lambda: received.append(True))
  assert win.scale_picker.current_scale() in ("compact", "medium", "large")
  win.scale_picker.select("medium")
  assert db.get_setting(db.SETTING_CALENDAR_SCALE) == "medium"
  assert received == [True]
  ```
  (선택: `[s[0] for s in CalendarSizePicker._SCALES] == ["compact","medium","large"]` 단언.)
- **추가**: `test_calendar_size_picker_highlight` — `select(v)` 후 `current_scale()==v`,
  선택된 옵션 1개만 `selected` 속성 True.
- **변경 없이 통과 유지(설계가 보장)**:
  - `test_settings_has_five_section_headers` — 패널 헤더를 `StrongBodyLabel`(섹션명)로 유지.
  - `test_settings_preserves_all_existing_controls` — 위젯 attr 이름·objectName 유지(`scale_combo`는 목록에 없음).
  - `test_settings_has_no_scroll_area` — `ScrollArea` 미도입.
  - 투명도/모니터/사이드바 등 나머지 `SettingsWindow` 테스트.
- 실행: `python -m pytest tests/test_ui.py -q` 전체 통과 확인.

## 9. 문서 갱신

- `AGENTS.md`
  - Module Map `ui_settings.py` 줄: "2열 보드 + 5개 섹션" → "**5개 섹션 패널** 2열", 캘린더 크기 = 일러스트 picker 반영.
  - Key Constraints "설정창 레이아웃": 패널 기반 표현으로 갱신(무스크롤·고정크기·5섹션은 유지).
- `docs/UI_PATTERNS.md` "Settings UI" 항목: 섹션 패널 + 우측 정렬 레일 + 캘린더 크기 picker 반영.

## 10. 영향 범위 요약

| 파일 | 변경 |
|---|---|
| `ui_settings.py` | `_make_panel`/`_add_row` 헬퍼, `_build_ui` 컨테이너 재구성, `CalendarSizePicker` 신규, `scale_combo`→`scale_picker`, `_on_scale_changed`(index→str) |
| `tests/test_ui.py` | scale picker 테스트 갱신 + 하이라이트 테스트 추가 |
| `AGENTS.md`, `docs/UI_PATTERNS.md` | 설정창 설명 갱신 |

## 11. 비목표 (YAGNI)

- 설정 항목 추가/삭제/이동(섹션 간 항목 재배치)은 하지 않는다 — 기능 불변.
- 창 크기 변경·스크롤 도입·좌측 내비 패러다임(검토했던 안)은 채택하지 않는다.
- 다른 창(메인/스티키/집중)의 디자인은 범위 외.
- DB 스키마·설정 키 변경 없음.
