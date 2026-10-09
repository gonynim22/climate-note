# 작업 기록: 집중 목표 잘림과 휴지통 색상 칸 수정

작성일: 2026-10-10 / 상태: 로컬 구현·검증 완료(full `20261010-003503-fbdda3f7ad`), 커밋 전. 버전·빌드·push는 사용자 승인 대기

## 목표와 범위

- 목표: 2026-10-09 디자인 점검의 3번·4번 오류를 고친다. (3) 집중 위젯 목표 "보고서 초안 작성"이 "보고서 초안 작"에서 잘림. (4) 스티키 노트 휴지통의 '색상' 칸이 비어 보임.
- 변경 대상: `ui_focus.py`(`FocusGoalLabel` 추가, 플로팅 위젯 목표), `ui_focus_panel.py`(large 미니 카드 목표), `ui_trash.py`(색상 칸 delegate), `tests/test_ui_focus.py`, `tests/test_ui_focus_panel.py`, `tests/test_ui_trash.py`, `docs/UI_PATTERNS.md`, `docs/TESTING.md`, `AGENTS.md`(기록 관리).
- 데이터 영향: 없음. 화면 표시만 바뀐다. 저장된 목표(최대 60자)·스티키 색·DB v17·Export v2·salt·설정 키를 바꾸지 않는다. 검사는 임시 폴더 합성 데이터만 쓴다.
- 제외 범위: 점검 9번(검색·휴지통 창 모양 통일), 집중 위젯 크기·배치 변경, 버전 변경(v3.9a 유지)·빌드·push.
- 시작 시 사용자 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 7개는 건드리지 않고 보존한다.

## 완료 조건

- [x] 긴 목표는 칸 폭에 맞게 `…`로 줄이고(앞 빈칸 없음), 줄였을 때만 전체 목표를 툴팁으로 보여 준다. 짧은 목표는 그대로·툴팁 없음. 기본/자세히 보기 모두 글자칸이 토마토·닫기 버튼 앞에서 끝난다.
- [x] large 미니 카드도 같은 칸을 써서 긴 목표가 카드 최소 폭을 늘리지 않는다.
- [x] 휴지통 '색상' 칸 가운데에 노트 색 원을 그린다. 선택한 줄에서도 보인다.
- [x] 관련 자동 검사: 100/125/150% quick, full.
- [ ] 필요한 수동 확인: 실제 EXE에서 집중 위젯 목표 툴팁, 휴지통 색 원 보기.

## 결정과 진행

- 2026-10-10 원인 3: `goal_label`은 일반 QLabel이라 목표 전체 폭을 최소 폭으로 잡는다. 위젯은 241px 고정이고 글자칸 몫은 기본 보기에서 약 85px(링 46·토마토 38·닫기 24·간격·여백 제외)이라, 레이아웃이 칸을 최소 폭보다 좁게 눌러 끝이 말줄임 없이 잘렸다. 실측에서 칸 오른쪽 끝은 토마토 왼쪽 앞이었다(보고서의 "토마토에 가려짐"은 실제로는 칸 끝 잘림).
- 같은 원인 확인: large 미니 카드(`FocusMiniCard`)는 긴 목표 때 최소 폭이 163→680px로 늘었다. 실제 large 메인에서 오른쪽 열이 300→471px로 넓어져 달력이 좁아졌다. 같은 목표 표시라 함께 고쳤다.
- 결정: `ui_focus.FocusGoalLabel`(가로 `QSizePolicy.Ignored`, 크기·글꼴 변경 때 다시 말줄임)을 두 곳에서 쓴다. 기존 `goal_label.setText()` 호출은 그대로 둔다. 툴팁은 줄였을 때만 둔다. Qt `elidedText`가 단어 사이에서 자르면 "보고서 초안 …"이 되어 앞 빈칸을 뗀다. 위젯 크기(241×78/126)와 배치는 바꾸지 않았다.
- 원인 4: 표 QSS의 `QTableWidget::item` 규칙이 있으면 스타일시트가 칸 그리기를 맡아 `setBackground()`(BackgroundRole)를 무시한다. 측정: 칸 가운데가 비선택 `#ffffff`, 선택 `#ebeced`.
- 결정: 0열 전용 `_ColorDotDelegate`가 기본 칸(선택 바탕 포함)을 그린 뒤 가운데에 14px 원을 그린다. 노랑 `#FFFA8E`·민트 `#D0FFF1`처럼 연한 색도 흰 바탕에서 보이게 `darker(130)` 1px 테두리를 둔다. 색은 `Qt.UserRole + 1`에 두고 무시되던 `setBackground()`는 지웠다. 행 식별 `Qt.UserRole`(note_id)은 그대로다.
- 전/후 캡처: 같은 합성 장면을 수정 전(`git show HEAD` 사본을 `sys.path` 앞에 둔 실행)과 수정 후 코드로 찍어 `output/design/design-audit-20261009/img/fix34/`에 두고 보고서 "3·4번 수정 결과" 절에 넣었다(gitignore 대상). 캡처 스크립트는 세션 scratchpad의 버리는 파일이다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_ui_focus.py tests/test_ui_focus_panel.py tests/test_ui_trash.py` (RED, 구현 전) | 실패(의도) | 하네스 실행 ID 없음 (pytest 직접 실행) | 5개 실패: 목표 말줄임 없음(기본·자세히), 미니 카드 최소 폭 680 > 163, 색상 칸 가운데 `#ffffff`/`#ebeced` |
| 같은 명령 (RED, 앞 빈칸) | 실패(의도) | 하네스 실행 ID 없음 | 기본 보기에서 `'보고서 초안 '` + `…` |
| 같은 명령 (GREEN) | 통과 | 하네스 실행 ID 없음 | 29개 |
| `verify.py quick --tests tests/test_ui_focus.py tests/test_ui_focus_panel.py tests/test_ui_trash.py tests/test_ui.py tests/test_ui_data_lifecycle.py tests/test_ui_sticky_panel.py` 100/125/150% | 통과(이전 입력) | `20261010-003021-31ade3d052` / `20261010-003109-aedcfb05d2` / `20261010-003157-966906b7bd` | 각 277개. 이후 쓰지 않는 `full_text()`를 지워 아래에서 다시 실행했다 |
| `verify.py full` (첫 실행) | 중단 | `20261010-003255-234aac5722` | 위 정리를 위해 직접 멈춤. summary가 `running`으로 남음, 통과 근거 아님 |
| `verify.py full` | 통과 | `20261010-003503-fbdda3f7ad` | 1,827개(실패·오류·건너뜀 0, 기존 1,821 + 새 시험 6), 모든 코드 수정 뒤 실행 |
| 같은 quick 125/150% (최종 코드) | 통과 | `20261010-003916-83a401ecda` / `20261010-004004-dccb4ac755` | 각 277개, Git Bash `QT_SCALE_FACTOR` |

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 EXE에서 목표 툴팁과 휴지통 색 원 확인. 기본 보기의 글자칸은 약 85px라 목표 대부분이 줄어 보인다(전체는 툴팁·자세히 보기). 더 보여 주려면 위젯 폭·토마토 배치를 바꾸는 디자인 결정이 필요하다.
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md)(Focus Mode Widgets 목표 말줄임, 스티키 삭제 정책의 휴지통 색상 칸), [테스트 문서](../TESTING.md).
- 다음 행동: 커밋·병합은 사용자 지시 후. 디자인 점검 다음 추천은 6·7번(영문 표기, 선택 색) → 5번.
- 배포·커밋·push 여부: 수행하지 않음.
