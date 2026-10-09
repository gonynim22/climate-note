# 작업 기록: 영문 표기 정리와 글자 선택 색 통일

작성일: 2026-10-10 / 상태: 로컬 구현·검증 완료(full `20261010-011043-406027ac51`), 커밋 전. 버전·빌드·push는 사용자 승인 대기

## 목표와 범위

- 목표: 2026-10-09 디자인 점검의 6번·7번을 고친다. (6) 날짜·시간 계산기 'CALCULATE', 금액 도우미 'NUMBER', 설정 'Factory Reset'만 영어. (7) 입력칸에서 글자를 선택하면 바탕이 청록이라 앱 파랑과 다름.
- 변경 대상: `main.py`(`_apply_light_theme` 선택 색), `ui_date_time_calculator.py`·`ui_money_notation.py`(왼쪽 메뉴 머리글), `ui_settings.py`(초기화 버튼 글자), `tests/test_app_theme.py`, `tests/test_ui.py`, `tests/test_ui_date_time_calculator.py`, `tests/test_ui_money_notation.py`, `docs/UI_PATTERNS.md`, `docs/MONEY_NOTATION.md`, `docs/TESTING.md`, `AGENTS.md`(기록 관리).
- 데이터 영향: 없음. 화면 문구와 실행 때 적용하는 팔레트만 바뀐다. DB v17·Export v2·salt·설정 키를 바꾸지 않는다. 검사는 임시 폴더 합성 데이터만 쓴다.
- 제외 범위: 점검 5번(미니앱 공용 창 틀). 왼쪽 메뉴 구조·크기는 5번에서 다시 다룬다. 감사 로그 문구 `전체 초기화(Factory Reset)`와 문서의 기능 이름 표기는 화면 문구가 아니라 그대로 둔다. 버전 변경(v3.9a 유지)·빌드·push.
- 시작 시 사용자 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 7개는 건드리지 않고 보존한다.

## 완료 조건

- [x] 날짜·시간 계산기 왼쪽 메뉴 머리글 `계산 종류`, 금액 도우미 `도구`, 설정 데이터 초기화 버튼 `초기화`. 크기·스타일·버튼 최소 폭(152px)은 유지.
- [x] 앱 팔레트의 글자 선택 색을 `#2563EB`/흰 글자로 고정한다. 나머지 팔레트 색은 밝은 시스템 팔레트를 따른다.
- [x] 관련 자동 검사: 100/125/150% quick, full.
- [ ] 필요한 수동 확인: 실제 EXE에서 일정 편집·미니앱·스티키 본문 선택 색, Windows 강조색이 파랑인 PC와 청록인 PC 비교.

## 결정과 진행

- 2026-10-10 원인 7: Qt 기본 `QLineEdit`(일정 편집 `ScheduleInlineEditor`, 날짜·시간·금액 입력)은 팔레트 `Highlight`를 선택 바탕으로 쓴다. windows11 스타일은 이 값을 Windows 강조색에서 가져온다. 측정 PC의 강조색은 청록(`AccentColor` → `#00B7C3`, Qt `Highlight` `#009faa`)이다. Fluent `LineEdit`은 자체 QSS로 `#2768f7`(테마색 계열)을 써서 이미 파랑이다. 그래서 선택 색이 PC마다 다르고 같은 앱 안에서도 입력칸 종류에 따라 달랐다.
- 결정 7: 보고서 제안은 "옅은 파랑 바탕"이었지만, 이미 진한 파랑+흰 글자를 쓰는 Fluent 입력칸과 한 가지 모양으로 맞추려고 `#2563EB`+흰 글자를 골랐다. 옅은 파랑으로 하면 Fluent 입력칸 QSS까지 바꿔야 한다. `_apply_light_theme()`에서 두 색만 지정한 빈 `QPalette`를 `app.setPalette()`로 적용한다. 탐침: 적용 뒤 Qt 색 구성표를 다크로 요청해도 `Highlight`는 `#2563eb`로 유지, `setPalette(QPalette())`로 시스템 값(`#009faa`)에 돌아온다. 시험은 이 방법으로 팔레트를 되돌려 다른 시험에 새지 않게 한다.
- 결정 6: 머리글을 없애면 메뉴 버튼 위치·무스크롤 배치가 바뀌므로 글자만 바꿨다. 날짜·시간은 메뉴가 계산 방식이라 `계산 종류`, 금액은 표기·읽기·환산이 섞여 `도구`(보고서 제안대로). 설정 버튼은 행 이름이 이미 `데이터 초기화`라 `초기화`.
- 캡처 주의: 이벤트 루프 없이 도는 캡처 스크립트에서 날짜를 다시 고르면 `deleteLater`된 옛 일정 줄 위젯이 남아 글자가 겹쳐 보였다(앱 문제 아님, 실제 앱은 이벤트 루프가 지운다). `sendPostedEvents(None, DeferredDelete)`로 처리한 뒤 다시 찍었다.
- 전/후 캡처는 수정 전(`git show HEAD` 사본) 코드와 수정 후 코드로 같은 합성 장면을 찍어 `output/design/design-audit-20261009/img/fix67/`과 보고서 "6·7번 수정 결과" 절에 넣었다(gitignore 대상).

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_app_theme.py tests/test_ui.py::test_settings_destructive_buttons_use_icon_design tests/test_ui_date_time_calculator.py::test_rail_header_is_korean tests/test_ui_money_notation.py::test_rail_header_is_korean` (RED, 구현 전) | 실패(의도) | 하네스 실행 ID 없음 (pytest 직접 실행) | 5개 실패: 선택 색 `#009faa`, 세 입력칸의 앱 파랑 선택 픽셀 0개, `Factory Reset`·`CALCULATE`·`NUMBER` |
| 같은 명령 (GREEN) | 통과 | 하네스 실행 ID 없음 | 8개 |
| `verify.py quick --tests tests/test_app_theme.py tests/test_ui.py tests/test_ui_date_time_calculator.py tests/test_ui_money_notation.py tests/test_ui_schedule_emoji.py tests/test_ui_mini_apps.py` 100/125/150% | 통과 | `20261010-010731-25429884da` / `20261010-010832-6d6d685544` / `20261010-010935-20202edfb3` | 각 408개. 125/150%는 Git Bash `QT_SCALE_FACTOR` |
| `verify.py full` | 통과 | `20261010-011043-406027ac51` | 1,831개(실패·오류·건너뜀 0, 기존 1,827 + 새 시험 4), 모든 코드 수정 뒤 실행 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 EXE에서 선택 색 확인. 목록·표 등 QSS로 선택 색을 따로 정하지 않은 곳도 이제 Windows 강조색 대신 앱 파랑을 쓴다(의도한 통일).
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md)(전역 블루 액센트의 글자 선택 색, 날짜·시간·금액 메뉴 머리글, 설정 위험 버튼 글자), [금액·숫자 표기 계약](../MONEY_NOTATION.md), [테스트 문서](../TESTING.md).
- 다음 행동: 커밋·병합은 사용자 지시 후. 디자인 점검 다음은 5번(미니앱 공용 창 틀, 시안 비교부터).
- 배포·커밋·push 여부: 수행하지 않음.
