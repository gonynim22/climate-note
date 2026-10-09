# 작업 기록: Windows 다크 모드 깨짐과 잠금 화면 투명 수정

작성일: 2026-10-10 / 상태: 로컬 구현·검증 완료, main 병합(`d516a57`, fast-forward). 버전·빌드·push는 사용자 승인 대기

## 목표와 범위

- 목표: 2026-10-09 디자인 점검의 1번·2번 오류를 고친다. (1) Windows 다크 모드에서 흰 바탕 위 흰 글자, 입력칸·버튼·닫기 아이콘이 사라짐. (2) 잠금 화면이 배경을 칠하지 않아 잠긴 상태에서도 달력·일정이 보임.
- 변경 대상: `main.py`, `ui_main.py`(`LockOverlay`), `tests/test_app_theme.py`(신규), `tests/test_ui_data_lifecycle.py`, `docs/UI_PATTERNS.md`, `docs/TESTING.md`, `AGENTS.md`(기록 관리).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·PIN 확인·저장 경로를 바꾸지 않는다. 테마는 저장하는 값이 아니라 실행 때마다 적용한다. 검사는 임시 폴더 합성 데이터만 쓴다.
- 제외 범위: 다크 모드 지원(다크 색 설계), 버전 변경(v3.9a 유지)·빌드·push, 점검 3번 이후 항목.
- 시작 시 사용자 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 7개를 커밋하지 않고 보존한다. `AGENTS.md`는 `HEAD` 내용에 이번 한 줄만 더한 사본을 인덱스에 올린다.

## 완료 조건

- [x] Windows가 다크여도 Qt 색 구성표와 qfluentwidgets 테마를 둘 다 밝게 고정한다. 실행 중 Windows 테마를 다시 읽거나 따라가지 않는다(60초 레지스트리 폴링 삭제).
- [x] 잠금 화면이 불투명 `#1e1e2e` 배경으로 기본·크게 모드의 창 전체(머리줄·사이드바·달력·일정)를 덮는다. PIN 확인·위젯 숨김·해제 복원은 그대로.
- [x] 관련 자동 검사: 다크 흉내 후 6개 창이 처음부터 밝은 화면과 같은지(픽셀), 잠금 화면 픽셀(기본·크게), 100/125/150% quick, full.
- [ ] 필요한 수동 확인: 실제 Windows 다크 설정에서 EXE 실행, 실행 중 Windows 테마를 바꿔도 밝게 유지되는지.

## 결정과 진행

- 2026-10-10 원인 1: 창 바탕은 QSS로 흰색·남색이 고정돼 있는데 `main.py`가 시작 때와 60초마다 레지스트리 `AppsUseLightTheme`을 읽어 qfluentwidgets 테마만 다크로 바꿨다. 또 Qt 6.11의 windows11 스타일은 Windows가 다크면 기본 팔레트도 어둡게 바꾼다. 탐침에서 `styleHints().setColorScheme(Dark)`이면 입력칸 바탕 `#2d2d2d`·글자 흰색, `Light`이면 `#ffffff`·검정으로 바뀌었다. 실제 Qt까지 다크인 캡처는 점검 때(Fluent만 다크)보다 더 많이 깨졌다(설정 행 이름, 스티키 글자, 검색·휴지통·D-Day 창 바탕).
- 사용자 알림: 예전에 다크 모드를 고치려다 실패한 적이 있다. git 이력은 v3.3 이전이 합쳐져 있어 근거를 찾지 못했다. 그래서 반쪽 수정을 실제로 측정했다(임시 시험, 커밋하지 않음). 다크 흉내 후 처음부터 밝은 화면과의 픽셀 차이: Fluent만 고정하면 설정 65.9%·D-Day 만들기 83.8%·휴지통 31.8%·검색 28.1%, Qt만 고정하면 D-Day 17.5%·검색 4.9%·휴지통 1.6%·설정 1.1%, 둘 다 고정하면 6개 창 모두 0%. 예전 실패는 한쪽만 고정했기 때문일 가능성이 크다(추정).
- 결정(사용자 승인 2026-10-09): 다크 모드를 지원하지 않고 밝게 고정한다. 헤더 남색·달력 흰색이 고정된 지금 디자인, 최초 크기 선택 창의 "항상 밝게" 결정과 같은 방향이다. `main._apply_light_theme(app)`이 창을 만들기 전에 Qt 색 구성표 → `Theme.LIGHT` → 강조색 `#2563EB` 순으로 적용한다. Qt 색 구성표를 명시해 두면 Qt는 이후 Windows 테마 변경보다 이 값을 우선한다.
- 원인 2: `LockOverlay`는 QWidget 하위 클래스인데 `WA_StyledBackground`가 없어 `#lockOverlay` QSS 배경을 칠하지 않았다. 흰 '잠겨 있음'·'잠금 해제' 글자는 흰 바탕에 묻혔다. 기존 잠금 시험은 표시 여부만 봐서 놓쳤다. 속성 한 줄로 고쳤다.
- 잠금 해제 버튼: 배경이 보이자 글자에 붙은 사각 테두리가 드러나 `padding: 6px 20px`·`border-radius: 6px`·테두리 흰색 70%로 다듬었다(사용자 계획 범위 안의 잠금 화면 정리).
- 버리는 캡처 스크립트가 끝의 `os._exit`에서 가끔 접근 위반으로 끝났다. 이번 수정 경로를 쓰지 않는 밝은 모드(compact)에서도 같은 줄에서 재현돼 스크립트 쪽 문제로 판단했다. 캡처는 모두 저장됐다.
- 전/후 캡처는 `output/design/design-audit-20261009/design-audit.html`의 "1·2번 수정 결과" 절에 넣었다(gitignore 대상).

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_app_theme.py` (RED, 구현 전) | 실패(의도) | 하네스 실행 ID 없음 (pytest 직접 실행) | 3개 실패: `main._apply_light_theme` 없음, `AppsUseLightTheme` 읽기 남음 |
| `pytest tests/test_ui_data_lifecycle.py -k lock_overlay_paints` (RED) | 실패(의도) | 하네스 실행 ID 없음 | compact `#13386a`(머리줄 남색 비침), large `#ffffff` ≠ `#1e1e2e` |
| 반쪽 수정 민감도(임시 시험, 커밋 안 함) | 측정 | 하네스 실행 ID 없음 | 위 "사용자 알림"의 비율. 이 측정으로 기준을 0.1% 미만으로 정했다 |
| `pytest tests/test_app_theme.py tests/test_ui_data_lifecycle.py tests/test_first_run.py` | 통과 | 하네스 실행 ID 없음 | 88개 |
| `verify.py quick` (100%) | 통과 | `20261010-001241-6a622200a0` | 기본 69개 |
| `verify.py quick --tests tests/test_app_theme.py tests/test_ui_data_lifecycle.py tests/test_first_run.py` 100/125/150% | 통과 | `20261010-001301-d569f09428` / `20261010-001344-0f750434f2` / `20261010-001426-8074844ae5` | 각 157개. 125/150%는 Git Bash `QT_SCALE_FACTOR` |
| `verify.py full` | 통과 | `20261010-001520-a5f256d488` | 1,821개(실패·오류·건너뜀 0), 모든 코드 수정 뒤 실행 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 Windows 다크 설정에서 EXE 실행과, 실행 중 Windows 테마 전환 뒤에도 밝게 유지되는지(자동 검사는 Qt 색 구성표 요청으로만 흉내 낸다). 고대비 모드는 Qt가 색 구성표 요청을 따르지 않으며 이번 범위 밖이다.
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md)(Theme·전역 블루 액센트·Privacy Lock), [테스트 문서](../TESTING.md).
- 다음 행동: 2026-10-10 사용자 지시로 `main`에 fast-forward 병합하고 브랜치를 지웠다(사용자 미커밋 `AGENTS.md` 4줄 보존을 위해 작업 폴더를 건드리지 않는 `update-ref` 방식). 버전(예: v3.9b)·PowerShell release 빌드·push는 별도 승인. 디자인 점검 다음 항목은 3번(집중 위젯 목표 잘림), 진행 상황은 `output/design/design-audit-20261009/design-audit.html` 위쪽 "진행 상황"에 있다.
- 배포·커밋·push 여부: `main` 커밋·병합까지. 빌드·push는 하지 않음.
