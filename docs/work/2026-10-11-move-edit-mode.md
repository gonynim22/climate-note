# 작업 기록: 캘린더 위치 편집(J안)·고른 날 회색 채움

작성일: 2026-10-11 / 상태: 로컬 구현·검증 완료(full `20261011-135224-98649525e6`), 브랜치 `feat/move-edit-mode`(main 병합 전). 버전 v3.9a 유지, 빌드·push 안 함

## 목표와 범위

- 목표: 디자인 점검 11·15번 재작업. 사용자가 이동 버튼 켜짐 점("무슨 의미인지 모르겠어")과 중간·크게 고른 날 테두리를 싫어함. [계획](../superpowers/plans/2026-10-11-move-edit-mode.md).
- 시안: 1차(A~F, 그림만 바꿈) 거절 → 조사 기반 2차(G~K) `output/design/move-button-20261011/move-button-concepts-2.html`에서 사용자가 **J안(편집 모드 + 완료)** 선택. 실제 380px 확정 시안과 점선 색 비교는 `output/design/move-button-20261011/j-final.html`.
- 사용자 결정(2026-10-11): "J가 괜찮은 것 같아", "네 방향이라기보다 '십자 화살표'가 나을 것 같아", 점선은 파랑 두 톤(노랑 비교 후), 기존 사용자도 고정으로 시작·다른 곳 클릭 자동 완료·고정 중 끌기 안내 "네 제안대로", 실행은 인라인 + 끝에 새 검토자.
- 변경 대상: `ui_main.py`(`CalendarMoveButton`, 새 `CalendarMoveDoneButton`·`CalendarMoveEditOverlay`, 편집 상태와 자동 종료, 고정 중 끌기 안내, 날짜 칸 고른 날 스타일), `database.py`(쓰지 않는 기본값 상수 삭제), 시험 `tests/test_ui_calendar_move.py`(전면 교체)·`test_ui_calendar_drag.py`·`test_ui_kvm_position.py`·`test_ui_calendar_cells.py`·`test_ui.py`, 문서 `docs/UI_PATTERNS.md`·`docs/ARCHITECTURE.md`·`docs/TESTING.md`·`README_detail.md`·`AGENTS.md`.
- 데이터 영향: 없음. DB v17·Export v2·salt 불변. 새 설정 키 없음. 예전 `calendar_move_enabled` 행은 읽지 않고 지우거나 새로 쓰지도 않는다(Export·Import에도 그대로). 위치 저장(`calendar_x/y`·`calendar_position_mode`·대상 화면)은 기존 끌기 저장 그대로.
- 동작 변화: 예전에는 기본이 "이동 허용"이라 머리줄을 바로 끌 수 있었다. 이제 모든 사용자가 고정 상태로 시작하고 십자 화살표를 눌러야 옮길 수 있다(사용자 승인).
- 시작 시 사용자/다른 작업 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md`, 다른 작업(화면 글자 따기 진단 도구)의 `docs/SCREEN_TEXT.md`·`docs/SCREEN_TEXT_LAB.md`·`docs/TESTING.md` 진단 절·`tests/test_screen_text_lab*.py`·`tools/screen_text_lab/`·미추적 `docs/work/*`. 모두 커밋하지 않고 보존했다(`AGENTS.md`·`docs/TESTING.md`는 HEAD 사본에 같은 치환만 한 blob으로 스테이지).

## 완료 조건

- [x] 평소 고정: 앱은 항상 고정으로 시작, 머리줄을 끌어도 움직이지 않음. 예전 설정 행(없음/"1"/"0") 보존.
- [x] 십자 화살표(흰 선 하나, 점·사선 없음, 체크 단추 아님) → 위치 편집 시작. 편집 중 검색·십자 화살표·⋮을 숨기고 오른쪽 104px 묶음 끝에 '완료'(52×32, 테두리 `#93C5FD`).
- [x] 편집 표시: 창 안쪽 2px 점선 두 톤(남색 머리줄 위 `#93C5FD`, 그 밖 `#2563EB`), 머리줄 아래 28px 안내 띠(`#EAF2FF`/`#1D4ED8`, 겹쳐 그림·마우스 통과).
- [x] 끝내기: '완료'·Esc·창 비활성·PIN 잠금·트레이 숨김·크기 변경·가져오기/초기화. 진행 중 끌기 취소. 모니터 변경은 편집 유지.
- [x] 키보드: Tab → Space/Enter로 시작하면 '완료'로 포커스, 끝내면 십자 화살표로 복귀. 마우스 클릭은 일정 입력 포커스 유지.
- [x] 고정 중 머리줄을 끌면 실행마다 한 번 InfoBar "캘린더 위치 고정 / 옮기려면 머리줄의 십자 화살표 단추를 누르세요."(세로 배치, 380px 안).
- [x] 중간·크게 고른 날: 칸 전체 연한 회색 `rgba(1,41,95,20)`, 테두리 없음, 오늘 남색 숫자 원 유지(오늘을 고르면 회색 칸 + 원).
- [x] 100/125/150% quick, full 하네스 통과.
- [ ] 새 검토자 검토(브랜치 전체).
- [ ] 실제 EXE 확인(편집 표시·Esc·다른 창 클릭 자동 완료, 다크 모드·125/150%).

## 결정과 진행

- 점선 색: 파랑 한 색 `#3B82F6`(대비 3.3~3.8), 노랑 한 색 `#FBBF24`(흰 칸 1.7), 노랑 두 톤 `#FBBF24`+`#D97706`(회색 열·안내 띠 2.9)과 비교해 파랑 두 톤(7.8/5.2/4.7/4.6)으로 결정. 노랑은 머리줄의 키보드 포커스 색과 겹친다.
- '완료' 자리: 380px 머리줄은 좌 104 + 가운데 148 + 우 104 = 356px로 남는 칸이 없어, 편집 중에는 검색·십자 화살표·⋮을 숨기고 같은 묶음에 '완료'만 둔다(2차 시안 J와 다른 점).
- 점선 위치: 창 바깥은 바탕화면이라 창 안쪽 가장자리에 그린다(2차 시안 J와 다른 점).
- Ruling(Task 5): `docs/ARCHITECTURE.md` 44·104행도 예전 이동 토글 설명이라 계획 목록 밖이지만 함께 고쳤다.
- Ruling(Task 5): `test_outline_color_follows_background`의 "흰 바탕 위에 연한 파랑 없음" 단언이 125/150%에서 실패했다. 진한 파랑 점선 가장자리가 흰 바탕과 반쯤 섞인 픽셀(약 146,177,245)을 허용치 24로 연한 파랑으로 오인했다. 허용치를 8로 좁히고, 연한 파랑으로 바꾼 돌연변이가 100/125/150% 모두에서 실패로 잡히는 것을 확인했다.
- `test_ui_calendar_move.py` 첫 창 활성화 대기에서 `Windows fatal exception: code 0x8001010d`(COM)가 1회 출력된다. main(`d56803a`)의 옛 시험에서도 같은 위치·같은 횟수로 재현되는 기존 환경 잡음이며 결과에 영향 없다.
- 다른 작업과의 겹침: 이 작업 중에도 화면 글자 따기 진단 작업이 같은 저장소에서 파일을 고쳤다(`tools/screen_text_lab/*.py`, `docs/TESTING.md` 진단 절, `docs/SCREEN_TEXT_LAB.md`). 150% quick 1회가 그 때문에 inputs_changed였고 다시 돌려 통과했다.
- 실제 그림 확인: 하네스 캡처 `calendar-move-edit-{compact,medium,large}.png`(아래 실행 폴더)를 `output/design/move-button-20261011/real/`에 복사해 확정 시안과 비교했다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| Task별 RED → GREEN (pytest 직접) | 통과 | 하네스 실행 ID 없음 | Task 1: 5개 RED → 134개 통과, Task 2: RED(AttributeError·창이 움직임) → 198개, Task 3: 7개 RED → 144개, Task 4: 7개 RED → 220개 |
| `verify.py quick --tests tests/test_ui_calendar_move.py` | 통과 | `20261011-133908-8e3e8813a6` | Task 3 중간 확인, 편집 중 캡처 3장 |
| `verify.py quick --tests` 6개 파일 100/125/150% (1차) | 100% 통과, 125·150% 실패 | `20261011-134423-6229412cca` / `-134519-ac69df9b73` / `-134615-0909ac443b` | 125·150% 각 1개: 위 Ruling(시험 허용치) |
| 같은 quick (2차) 100% / 125% | 통과 | `20261011-134836-5bc8795f9d` / `20261011-134929-66e2180038` | 각 297개 |
| 같은 quick (2차) 150% | 실패(inputs_changed) | `20261011-135023-bc5d7c9cfb` | 297개 모두 통과, 실행 중 다른 작업이 `docs/SCREEN_TEXT_LAB.md` 수정 |
| 같은 quick 150% (재실행) | 통과 | `20261011-135126-56ef9b0001` | 297개 |
| `verify.py full` | 통과 | `20261011-135224-98649525e6` | 2,124개(실패·오류·건너뜀 0, 다른 작업 시험 포함), 모든 코드 수정 뒤 실행. 캡처는 `output/design/move-button-20261011/real/`로 복사 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 EXE에서 편집 표시·Esc·다른 창 클릭 자동 완료, Windows 다크 설정·125/150%.
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md), [아키텍처](../ARCHITECTURE.md), [테스트](../TESTING.md), [자세한 설명](../../README_detail.md).
- 다음 행동: 새 검토자 검토 → 사용자 확인 뒤 main 병합·release 빌드(지시가 있을 때만).
- 배포·커밋·push 여부: 브랜치 `feat/move-edit-mode` 커밋까지. main 병합·빌드·push는 하지 않음.
