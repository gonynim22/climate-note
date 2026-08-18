# 바탕화면 유지 (Win+D 면역) — 설계

- 날짜: 2026-07-01
- 상태: 승인됨 (구현 계획 대기)
- 앱: 기후노트 (MyDesktopCalendar) v3.1
- 관련 파일: `ui_main.py`, `main.py`, `database.py`, `ui_settings.py`, `ui_sticky.py`, `ui_dday.py`, `ui_focus.py`

## 1. 배경 / 동기

Windows에서 **Win+D**(또는 작업표시줄 오른쪽 끝 '바탕화면 보기' 버튼)를 누르면 셸(explorer.exe)이 모든 최상위 창을 최소화한다. 기후노트도 여기에 걸려 함께 내려간다. 사용자는 Win+D로 바탕화면을 볼 때 기후노트(및 부속 위젯)는 **그대로 남기를** 원한다.

### 폐기된 대안 — WorkerW/Progman 재부모화

`ui_main.py:879`에 `(바탕화면 고정 모드 기능 제거됨)` 주석이 있다. 과거에 창을 바탕화면 레이어(WorkerW/Progman)의 자식으로 편입시키는 방식이 구현됐다가 **"자꾸 사라지거나 불안정"**한 이유로 제거됐다(사용자 확인). 이는 Qt가 top-level 스타일을 재강제하며 `SetParent`를 되돌리는 고전적 실패로, 이 앱의 반투명(`WA_TranslucentBackground`)·전체 투명도(`setWindowOpacity`)·Win+L 잠금 감지(`winId()` 등록, `ui_main.py:922`)와도 충돌한다. **따라서 재부모화 방식은 채택하지 않는다.**

## 2. 목표 / 비목표

### 목표
- Win+D / Win+M(모두 최소화) 시 **메인 달력 창 + 모든 플로팅 위젯(스티키·D-Day·집중)** 이 내려가지 않고 화면에 유지된다.
- 설정에서 켜고 끌 수 있으며 **기본값은 ON**, 변경은 **실시간 반영**(재시작 불필요).
- 기존 외관·기능(반투명, 둥근 모서리, 전체 투명도, 드래그, 멀티모니터 배치, Win+L 개인정보 잠금, 트레이, Boss Key) **무손상**.

### 비목표 (YAGNI)
- WorkerW/Progman 재부모화 (불안정 이력).
- `WM_WINDOWPOSCHANGING` 네이티브 거부(=깜빡임 완전 제거) — v1 제외. 깜빡임이 거슬리면 후속 개선으로 검토.
- 설정/휴지통/검색 다이얼로그 및 집중 격려 말풍선(3초 소멸)은 가드 대상에서 제외(일시적 창).

## 3. 핵심 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 방식 | **②a: 최소화 감지 → 즉시 복원** | 순수 Qt 이벤트, 재부모화 없음 → 안정성 최우선(불안정 이력 감안) |
| 감지 | `QEvent.WindowStateChange` + `WindowMinimized` | 이 창들은 사용자용 최소화 수단이 없어(최소화 버튼 없음, Boss Key/트레이는 `hide()`) 최소화 = Win+D/Win+M뿐 → 오탐 0 |
| 깜빡임 | 허용 (잠깐 내려갔다 복원) | 안정 우선. 무깜빡임 필요 시 ②b 후속 |
| 범위 | 메인 + 모든 플로팅 위젯 | 사용자 선택 |
| 토글 | 설정 토글, 기본 ON, 실시간 | 안전 스위치 + 앱 설정 규칙 부합 |

## 4. 아키텍처 · 컴포넌트

### 새 단위: `show_desktop_guard.py`
단일 책임 = "감시 중인 창이 최소화되면 되돌린다".

```python
class ShowDesktopKeeper(QObject):
    def __init__(self, enabled: bool = True, parent=None): ...
    def guard(self, widget: QWidget) -> None      # widget.installEventFilter(self)
    def set_enabled(self, on: bool) -> None        # 실시간 on/off
    def eventFilter(self, obj, event) -> bool:     # 감지만; return False (소비 안 함)
        # enabled && WindowStateChange && obj.isWindow() && (windowState & Minimized)
        #   -> QTimer.singleShot(0, lambda: self._restore(obj))
    @staticmethod
    def _restore(widget: QWidget) -> None:         # 최소화 비트 제거 후 show()
```

설계 원칙:
- **재부모화·스타일 변경 없음.** 이벤트 관찰만 하므로 Qt와 싸우지 않는다.
- **복원은 `QTimer.singleShot(0, ...)`로 지연** — Windows가 최소화를 끝낸 뒤 다음 이벤트 루프 턴에 복원하여 재진입/경쟁을 피한다.
- `eventFilter`는 **`return False`**로 이벤트를 소비하지 않아 정상 처리 흐름을 방해하지 않는다.
- 필터 내부 예외는 로깅 후 삼켜 이벤트 루프를 보호한다(`0023_NOACTION`/`0024_NOCHKERR` 준수: 예외 타입 세분화 + 로깅).

### 통합 (`ui_main.py`) — 기존 투명도 브로드캐스트 패턴 미러링
- 메인 창이 `ShowDesktopKeeper` **1개**를 소유(부모=메인).
- 앱 시작 시 DB에서 설정을 읽어 `keeper.enabled` 초기화.
- **창 생성 지점에서 `keeper.guard(창)` 호출** — 투명도(`_apply_app_opacity`)를 적용하는 바로 그 지점과 동일:
  - 메인 창 자신
  - 스티키(`_sticky_windows`), D-Day(`_dday_windows`), 집중(`_focus_windows`) 생성 시
- 설정 토글 변경 시 `keeper.set_enabled(...)` 호출로 즉시 반영.

## 5. 데이터 흐름

```
[앱 시작] DB.get(keep_on_show_desktop) -> keeper.enabled
[창 생성] 메인/스티키/D-Day/집중 -> keeper.guard(창)   (투명도 적용과 동일 지점)
[Win+D]  창 최소화 -> eventFilter 감지 -> (enabled면) singleShot(0) -> _restore -> 창 복원
[설정 변경] 토글 -> DB 저장 + keeper.set_enabled(...) -> 즉시 반영
```

## 6. DB · 설정 (데이터 보존 규칙 준수)

- `database.py`
  - `SETTING_KEEP_ON_SHOW_DESKTOP = "keep_on_show_desktop"`
  - 기본값 `"1"`(ON) — 로드시 fallback 기본값 제공(기존 키 삭제 금지 규칙 준수).
- **마이그레이션 v15 → v16** (`migrate()`):
  - `INSERT OR IGNORE INTO app_settings (key, value) VALUES ('keep_on_show_desktop', '1');`
  - `user_version = 16`.
  - 멱등성 보장(`INSERT OR IGNORE`). **기존 데이터·설정 무손상.**
- **Export/Import**: `app_settings`는 이미 포함(단, `privacy_pin` 제외) → 이 키는 자동으로 백업/복원됨. 별도 코드 불필요.

## 7. 설정 UI (`ui_settings.py`)

- **[as-built]** **"시스템"** 섹션 패널(`_SettingsPanel`)에 `SwitchButton` 행 1개 추가. (기본안은 "화면 표시"였으나 이미 5행이라 오버플로 위험 → 아래 레이아웃 제약에 따라 "시스템"으로 배치. `_on_startup_toggled`(자동 실행)와 같은 OS 동작 성격에도 부합.)
- 라벨: **"바탕화면 유지"** (고정 라벨폭 116px에 맞춘 짧은 표기).
- `_add_row(라벨-좌 고정폭 / 컨트롤-우 + 1px 구분선)` 규칙 준수. 자동 실행 → 바탕화면 유지 → 앱 글꼴(마지막, `divider=False`) 순서.
- `SwitchButton`은 전역 블루(`setThemeColor #2563EB`) 자동 적용(텍스트 없는 단일 블루 토글). 성공 시 InfoBar 없음(조용한 토글, `_on_startup_toggled`와 동일 성격).
- 상태 변경 → DB 저장 + 메인의 `keeper.set_enabled(...)` 실시간 반영. `SettingsWindow`의 `on_keep_changed` 콜백 → 메인 `_on_keep_desktop_changed()` 경로(전체 투명도의 `on_opacity_changed`와 동일한 콜백 배선 방식).
- ⚠️ **레이아웃 제약(AGENTS.md)**: 설정창은 `ScrollArea` 없이 **800×560** 고정/최소 유지. **[사후 정정]** 구현 당시 코드가 스펙(560)과 달리 `resize(800, 520)`으로 잠복해 있었고, 이 행 추가(+41px)로 우측 컬럼 레이아웃 최소치가 546px이 되어 520을 초과 → 행이 세로 압축되며 고정높이(34px) 버튼이 구분선을 침범하는 **회귀가 발생**했다(자동 테스트로는 미검출, 실기기에서 발견). 코드를 스펙대로 560으로 올려 해결. 교훈: 무스크롤 고정 창에 행을 추가할 땐 `layout().minimumSize()`가 창 높이 이하인지 실측으로 확인할 것.

## 8. 엣지 케이스

| 상황 | 동작 | 근거 |
|---|---|---|
| Boss Key(Ctrl+Shift+H) / 트레이 / 닫기 | 복원 안 함 | 모두 `hide()`(최소화 아님) → `WindowStateChange` 미발생 |
| '크게'(large) 모드 | 메인 가드가 전부 커버 | 플로팅 위젯은 숨김(이벤트 미발생) + 내용은 메인에 임베드된 자식 위젯 |
| 새 위젯 생성 | 자동 보호 | 생성 지점에서 `guard()` 호출(투명도와 동일) |
| 토글 OFF | 가드 설치돼 있으나 no-op | ON 전환 시 즉시 작동. 설치/해제 대신 플래그 게이트 |
| 설정/휴지통/검색 다이얼로그 | 가드 안 함 | 일시적 창, 내려가도 무방(비목표) |
| 집중 격려 말풍선 | 가드 안 함 | 3초 소멸 일시 오버레이 |

## 9. 테스트 (`tests/`)

- **마이그레이션 왕복** (`test_database.py` 또는 신규):
  - 신규 DB → `user_version=16` + `keep_on_show_desktop = "1"`.
  - 기존 v15 DB → v16 멱등 마이그레이션, 다른 설정/데이터 무손상.
  - Export → Import 후 키 값 보존.
- **가드 동작** (pytest-qt, 신규 `test_show_desktop_guard.py`):
  - 창에 `ShowDesktopKeeper` 설치 후 `setWindowState(Qt.WindowMinimized)` 주입 → enabled면 최소화 비트 제거되어 복원, disabled면 최소화 유지.
  - `guard()`가 여러 창에 독립 적용됨.
- **설정 UI** (`test_ui.py` 계열):
  - 토글 존재 + `SwitchButton` 타입 + 저장/로드 반영.
- 기존 테스트 전부 통과 유지(`python -m pytest tests -q`).

## 10. 파일 변경 요약

| 파일 | 변경 |
|---|---|
| `show_desktop_guard.py` | **신규** — `ShowDesktopKeeper` |
| `database.py` | `SETTING_KEEP_ON_SHOW_DESKTOP` 상수 + v15→v16 마이그레이션 |
| `ui_main.py` | keeper 소유·초기화, 생성 지점 `guard()`, 설정 변경 live 반영 |
| `ui_settings.py` | "화면 표시" 섹션 토글 행 |
| `AGENTS.md` | 모듈맵(신규 파일)·Key Constraints·마이그레이션 v16 문서화 |
| `tests/` | 마이그레이션·가드·설정 UI 테스트 |

## 11. 검증 체크포인트 (실기기)

과거 유사 기능이 불안정으로 제거된 이력이 있으므로, 구현 후 **실제 Windows 11 기기에서 수동 검증** 필수(자동 테스트로는 Win+D 셸 동작을 완전 재현 불가):

1. Win+D → 메인 + 플로팅 위젯 모두 유지되는가.
2. 다시 Win+D → 다른 앱 복원과 충돌 없는가.
3. Win+M(모두 최소화)에도 유지되는가.
4. Boss Key / 트레이 숨김이 여전히 정상 작동하는가(가드가 방해 안 함).
5. 반투명·둥근 모서리·전체 투명도·드래그·멀티모니터·Win+L 잠금이 무손상인가.
6. 설정 토글 OFF → Win+D에 정상적으로 내려가는가(즉시 반영).
7. 깜빡임 정도가 수용 가능한가(아니면 ②b 후속 결정).

## 12. 참고 — 확인이 필요한 기술 전제

- `QEvent.WindowStateChange`가 `Qt.Tool | FramelessWindowHint` 반투명 창에 대해 Win+D 시 실제로 발생하는지 실기기에서 확인(설계의 대전제). 만약 일부 창에서 미발생 시 `nativeEvent`의 `WM_SIZE(SIZE_MINIMIZED)` 보조 감지를 추가.
- 이 항목은 구현 초기 스파이크로 먼저 확인 후 본 구현 진행 권장.
