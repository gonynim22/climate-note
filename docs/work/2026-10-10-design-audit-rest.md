# 작업 기록: 디자인 점검 나머지(11·15~21번)

작성일: 2026-10-10 / 상태: 로컬 구현·검증 완료(full `20261010-215843-746e05d46b`), main 병합(`5cc0745`, fast-forward). 버전 v3.9a 유지, 빌드·push 안 함

## 목표와 범위

- 목표: 디자인 점검 11·15·16·17·18·19·20·21번(12번 제외, 사용자 지시 2026-10-10). [계획](../superpowers/plans/2026-10-10-design-audit-rest.md).
- 사용자 결정: 11 켜짐 표시는 작은 점, 17 날짜는 직접 입력 + 달력 버튼, 21 자주 안 쓰는 버튼은 필요할 때만 보이기, 18 폴더 버튼은 그대로.
- 변경 대상: `ui_main.py`(이동 버튼, 날짜 칸, 요일 머리줄), `ui_dday_panel.py`, `ui_sticky.py`, `ui_dday.py`, `ui_focus.py`, `ui_settings.py`, `ui_mini_apps.py`, `ui_date_time_calculator.py`, `ui_document_converter.py`; 새 시험 `tests/test_ui_calendar_cells.py`·`test_ui_right_column.py`·`test_ui_create_dialogs.py`·`test_ui_settings_data.py`·`test_ui_mini_app_spacing.py`, 보강 `tests/test_ui_calendar_move.py`·`test_ui_mini_apps.py`·`test_ui_document_converter.py`·`test_ui.py`; `docs/UI_PATTERNS.md`·`docs/DOCUMENT_CONVERSION.md`·`docs/TESTING.md`.
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·D-Day/집중 저장 경로·문서 변환 계약 불변. 합성 데이터만 쓴다.
- 시작 시 사용자/다른 작업 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md`, 다른 작업(화면 글자 따기 진단 도구)의 `docs/SCREEN_TEXT.md`·`docs/SCREEN_TEXT_LAB.md`·`docs/TESTING.md` 일부·`tools/screen_text_lab/`·`tests/test_screen_text_lab*.py`·작업 기록들은 건드리지 않는다. `docs/TESTING.md`는 같은 파일에 서로 다른 문단을 더해 두 쪽 모두 남아 있음을 확인했다.

## 완료 조건

- [x] 11: 이동 켜짐 = 채움 없이 흰 화살표 + 아래 4px 점(`#93C5FD`), 꺼짐 = 옅은 화살표 + 사선.
- [x] 15: 중간·크게에서 숫자 왼쪽 위(26×26), 오늘 남색 원, 고른 날 2px 테두리, 요일 12/13px 왼쪽 정렬. 기본 크기는 그대로.
- [x] 16: D-Day 이름 11px, 추가 칸 한 줄, 배경 색상 버튼 팔레트 아이콘.
- [x] 17: 창 안 제목, D-day 미리보기, 한국어·일요일 시작 달력 버튼, 버튼 위 여백(집중 창도 같은 틀).
- [x] 18: PIN 칸 110px·`PIN 4자리`, 저장 경로 한 줄(폴더 이름 남기는 말줄임) + 폴더 버튼 유지.
- [x] 19: 주머니 이름 첫 줄 높이 맞춤.
- [x] 20: 날짜·시간 입력·안내를 위로 붙이고 남는 높이는 결과 쪽으로.
- [x] 21: 빈 목록 끌어 놓기 안내, 상태별 버튼 표시.
- [x] full 하네스 통과(다른 작업 종료 후 재실행).
- [ ] 실제 EXE 확인.

## 결정과 진행

- Ruling 17: 계획대로 qfluentwidgets 달력을 먼저 확인했더니 요일이 영어(Mo Tu…)이고 월요일 시작이라 앱 달력·한국어 원칙과 맞지 않았다 — Qt `QCalendarWidget`(한국어 로캘, 일요일 시작, 일·토 색)을 팝업으로 쓴다 — 틀리면 달력 모양이 Fluent와 조금 다를 뿐 기능은 같다.
- Ruling 18: 단순 가운데 말줄임은 마지막 폴더 이름까지 잘라("…ktopCalendar") 어느 폴더인지 안 보였다 — 드라이브와 마지막 폴더 이름을 남기고 가운데만 줄인다(`C:\…\MyDesktopCalendar`, 안 들어가면 기본 가운데 말줄임) — 틀리면 경로 앞부분 대신 끝부분이 보일 뿐이다. 한글 글꼴에서 `\`는 `₩`로 보인다(Windows 탐색기와 같음).
- Ruling 19: 처음 쓴 시험은 아이콘 위치를 쟀는데 아이콘은 원래 맞았고 어긋난 것은 이름 첫 줄(한 줄 이름이 두 줄 칸 가운데)이었다 — 시험을 이름 첫 줄 높이로 고친 뒤 RED(8px 차이)를 확인하고 고쳤다. 125/150%에서 아이콘 맨 아랫줄을 글자로 세지 않게 검사 시작점을 아이콘 아래 4px로 둔다.
- Ruling 20: 줄 사이 간격 시험은 처음에 통과했는데, 늘어난 것은 줄 사이가 아니라 줄 자체(휴게 공제 줄 29→63px)였다 — 줄·안내 높이가 제 크기를 넘지 않는지로 고쳐 RED 확인. 가로줄 안의 작은 라벨(합산 '1/3')은 같은 줄 버튼 높이에 맞춰지는 정상 동작이라 검사에서 뺐다.
- Ruling 21: 기존 좁은 화면 시험이 숨긴 버튼의 기본 크기(640×480)까지 검사해 실패했다 — 실패·완료 항목이 있어 버튼이 모두 보이는 상태로 바꿔 보이는 버튼만 잰다. 이 상태에서 420/480×500 화면에 창이 520/540px로 커지는 문제가 드러났는데, HEAD 코드에서도 같은 순서면 520px이었다(5번 48px 제목줄 + 바깥 레이아웃만 갱신하는 `fit_to_screen`). 높이 560 미만에서 제목줄 40px·위아래 여백 축소, 안쪽 레이아웃부터 갱신(날짜·시간 창과 같은 방식), 버튼 표시가 바뀌면 다시 맞추도록 고쳤다.
- Ruling 15: 기존 `test_calendar_day_button_selected_style_is_scoped_to_cell`은 중간·크게 칸의 고른 날을 옅은 채움으로 기대했다 — 테두리(`border: 2px solid #01295F`)로 바꾸고 칩 영역에 새지 않는지는 그대로 본다. 125%에서는 테두리가 1px 아래에 그려져 픽셀 검사를 y=1에서 한다.
- 150%에서 `test_sidebar_pocket_geometry_and_render[large]`가 한 번 주머니가 바로 닫혀 실패했으나 같은 배율로 두 번 다시 돌려 모두 통과했다(창 활성화 타이밍, 이번 변경과 무관해 보임).
- 다른 작업과의 겹침: 이 작업 중 화면 글자 따기 진단 도구 작업이 같은 저장소에서 계속 파일을 만들고 고쳐(`tools/screen_text_lab/`, `tests/test_screen_text_lab*.py`, `docs/SCREEN_TEXT_LAB.md`, `docs/TESTING.md`) 하네스가 두 번 `inputs_changed`로 실패 처리했다. 바뀐 파일은 모두 그 작업의 것이고 시험 결과는 모두 통과였다.
- 전/후 캡처: `output/design/design-audit-20261009/img/fixrest/`(수정 전 = 브랜치 시작 `2b17cee` 사본).

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 항목별 RED → GREEN (pytest 직접) | 통과 | 하네스 실행 ID 없음 | 11: 16개, 15: 16개, 16: 37개, 17: 28개, 18: 39개, 19: 74개, 20·21: 48개 |
| `verify.py quick --tests` 16개 파일 100/125/150% (1차) | 실패 | `20261010-212708-4e551ab87c` / `-212831-5a9b697226` / `-212954-8fd2b937dc` | 위 Ruling 15·19의 시험 수정 전, 150% 주머니 1회 |
| 같은 quick (2차) 100% / 150% | 통과 | `20261010-213232-da741521a0` / `20261010-213538-a35586945e` | 각 440개 |
| 같은 quick (2차) 125% | 실패(inputs_changed) | `20261010-213407-0488fe1515` | 440개 모두 통과, 실행 중 다른 작업의 파일 변경 |
| `verify.py full` | 실패(inputs_changed) | `20261010-213908-4cd1a1a373` | 1,934개 모두 통과(다른 작업 시험 포함), 실행 중 `docs/SCREEN_TEXT_LAB.md`·`docs/TESTING.md`·`tests/test_screen_text_lab*.py`·`tools/screen_text_lab/review_ui.py` 변경 |
| 같은 quick 125% (다른 작업 종료 후) | 통과 | `20261010-214944-9650fe71b2` | 440개 |
| `verify.py full` (재실행) | 실패 | `20261010-215112-eb1dd6a25a` | 1,947개 중 4개: 이모지 팝업·환산기 드롭다운이 열리자마자 닫힘, 바로가기 메뉴 하위 프로세스 30초 초과 — 모두 포커스 관련이며 이번 변경 영역 밖. 같은 4개(파라미터 포함 33개)를 두 번 다시 돌려 모두 통과 |
| `verify.py full` (재실행 2) | 통과 | `20261010-215843-746e05d46b` | 1,947개(실패·오류·건너뜀 0, 다른 작업 시험 포함), 모든 코드 수정 뒤 실행 |
| PowerShell `verify.py release` (main `8d34088`) | 통과 | `20261010-220459-0bd4f897c6` | 1,947개 시험·빌드·격리 EXE 3개, mingw 혼입 없음, Qt는 프로젝트 `.venv`, 다른 작업의 `tools/screen_text_lab` 미포함. `dist/기후노트_v3.9a.exe` 배치: 94,031,363 bytes, SHA-256 `FED6E7D270A261458710D35C476B966B08B15E54751BDFFDDCFE35A8FDF344C7`. 이전 EXE(`D4A0668B…`, 1~10·13·14번)는 `output/harness/20261010-092310-8c6a27c6db/dist/`에 있다 |

## 12번 추가(2026-10-10)

- 사용자 지시 "12도 진행하자 바로 깔끔하게 그냥". 기본 크기 칸의 개수 숫자는 네모(그날의 서로 다른 색마다 하나, 최대 3개)로 다 보이지 못한 일정 수만 `+N`으로 보인다. 보고서 예시('4개 이상일 때 +2')는 네모가 색마다 하나라는 점을 반영해 '네모로 못 보인 수'로 정했다(같은 색 3개면 네모 1개 + `+2`).
- 기존 시험 3곳(`test_calendar_cell_shows_total_count`, 모드 전환 시험의 개수, `test_cell_count_updates_live_on_add_and_delete`)을 새 규칙으로 갱신했다. 새 시험 `tests/test_ui_calendar_count.py`(RED: `'1' == ''` 등 → GREEN).
- 재검증(다른 작업 종료 뒤): full `20261010-222843-c45e15a9e1` 1,965개 통과(실패·오류·건너뜀 0, 다른 작업 시험 포함). 직전 full `20261010-221750-f45cf54238`은 1,954개 통과였으나 동시 수정으로 inputs_changed였다.
- PowerShell `verify.py release`(main `8dc7b5e`) `20261010-223326-b5230277c5` 통과: 1,965개 시험·빌드·격리 EXE 3개, mingw 혼입 없음, Qt는 프로젝트 `.venv`, `tools/screen_text_lab` 미포함. `dist/기후노트_v3.9a.exe` 배치: 94,031,011 bytes, SHA-256 `C72606C198D25F913198272F75970013C1FEB52FA50F4475440DDBFE0178A223`. 이전 EXE(`FED6E7D2…`, 12번 외 전부)는 `output/harness/20261010-220459-0bd4f897c6/dist/`에 있다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 EXE 화면 확인(Windows 다크 설정·125/150% 포함).
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md), [문서 변환](../DOCUMENT_CONVERSION.md), [테스트](../TESTING.md).
- 다음 행동: 2026-10-10 사용자 확인(다른 작업 종료) 뒤 재검증하고 `feat/design-audit-rest`에 커밋(`5cc0745`), `main`에 fast-forward 병합 후 브랜치를 지웠다. 사용자·다른 작업의 미커밋 변경(`AGENTS.md` 4줄, `docs/RELEASE_HISTORY.md`, `docs/SCREEN_TEXT.md`, `docs/TESTING.md`의 진단 도구 절, `tools/screen_text_lab/` 등)은 커밋하지 않고 보존했다. 병합된 main으로 release 빌드를 통과해 `dist/`에 배치했다(디자인 점검 12번 외 전부 포함). 12번은 `1cfab2b`로 병합한 뒤 다시 release 빌드해 `dist/`를 바꿨다(21항목 전부 포함).
- 배포·커밋·push 여부: `main` 커밋·병합까지. push는 하지 않음.
