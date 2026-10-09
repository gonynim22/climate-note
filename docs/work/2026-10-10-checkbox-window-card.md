# 작업 기록: 미니앱 체크박스와 검색·휴지통 흰 카드, v3.9a 재빌드

작성일: 2026-10-10 / 상태: 로컬 구현·검증·release 빌드 완료(`20261010-074959-b539017280`), `dist/` 배치. 커밋 전. 버전 v3.9a 유지, push 안 함

## 목표와 범위

- 목표: 2026-10-09 디자인 점검의 8번(날짜·시간 계산기만 Windows 기본 체크박스)과 9번(검색·휴지통 창이 다른 앱처럼 보임)을 고치고, 1~9번이 들어간 EXE를 빌드한다. 사용자 지시(2026-10-10): "8,9도 바로 진행해줘. 그리고 빌드."
- 변경 대상: `ui_mini_app_frame.py`(`MiniAppCheckBox`), `ui_date_time_calculator.py`·`ui_document_converter.py`(체크박스 교체), 새 `ui_window_card.py`, `ui_search.py`, `ui_trash.py`, `tests/test_ui_mini_app_frame.py`, 새 `tests/test_ui_window_card.py`, `docs/UI_PATTERNS.md`·`docs/ARCHITECTURE.md`·`docs/TESTING.md`·`AGENTS.md`(기록 관리).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·검색/휴지통 동작 불변. 검사는 합성 데이터만 쓴다.
- 제외 범위: 메인 정돈(10~16번)·세부(17~21번), 검색 결과의 📝 메모 배지, 버전 변경·push·GitLab Release 게시.
- 시작 시 사용자 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 7개는 보존한다.

## 완료 조건

- [x] 8번: 미니앱 체크박스는 18px 둥근 상자, 체크하면 `#2563EB` 바탕에 흰 체크 선.
- [x] 9번: 검색·휴지통 창이 설정 카드와 같은 흰 카드·파랑 선 아이콘 제목, 앱 색 표, 빈 상태 안내.
- [x] 100/125/150% quick, release(전체 시험·빌드·격리 EXE 3개), TOC 대조, `dist/` 배치.
- [ ] 필요한 수동 확인: 새 EXE로 날짜·시간 체크, 검색·휴지통 창 열기. 실제 Windows 다크 설정·125/150% 화면 확인(1·2번부터 남은 항목).

## 결정과 진행

- 2026-10-10 원인 8: 7번 수정 뒤 Qt 체크박스도 앱 파랑으로 칠해졌지만, windows11 스타일은 파랑 위에 어두운 체크를 그려 대비가 낮다(측정 캡처). 앱 안 다른 체크는 Fluent 모양(흰 체크)이다.
- 결정 8: `MiniAppCheckBox`가 상자는 자체 QSS(16px 안쪽 + 1px 테두리 = 18px, 모서리 4px)로 칠하고, 체크 선은 `paintEvent`에서 흰 1.8px 선으로 직접 그린다. 그림 파일(SVG)을 QSS `image:`로 쓰면 EXE의 이미지 형식 플러그인에 기대게 돼 피했다. qfluentwidgets `CheckBox`는 자체 14px 글꼴 QSS가 창의 12px보다 우선해 좁은 화면 무스크롤 배치를 흔들 수 있어 쓰지 않았다.
- Ruling: 계획한 시험의 상자 크기 16px은 QSS 박스 모델상 테두리를 뺀 크기였다 — 실제 18px(Fluent 체크박스와 같은 크기)을 기대값으로 고쳤다 — 틀리면 상자가 2px 크다는 것뿐.
- 결정 9: 공용 `ui_window_card.WindowCard`(흰 바탕, `#D7DAE2` 테두리, 모서리 11px, 머리줄 `#F6F6F6`·파랑 FluentIcon 17px·굵은 14px 제목, 본문 `body`, `empty_label()`)와 `TABLE_QSS`를 두 창이 쓴다. 노션풍 색(`#37352f` 등)을 지웠다. 검색 창은 이전에 일부러 둔 격자선(`setShowGrid(True)`)을 유지하고 색만 옅게 했다. 검색 처음·결과 없음에는 표를 숨기고 안내 문구를 보인다.
- 빌드: 버전 지시가 없어 v3.9a를 유지했다. 이전 `dist/기후노트_v3.9a.exe`(SHA-256 `3C80DBB0…`)는 `output/harness/20261009-183942-21246a4373/dist/`에 같은 해시로 이미 있어, 확인 뒤 루트 `dist/`를 새 EXE로 바꿨다. 같은 이름이므로 해시로 구분한다.
- 캡처: `output/design/design-audit-20261009/img/fix89/`(수정 전 = main `8466052` 사본, 수정 후), 보고서 "8·9번 수정 결과" 절.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_ui_window_card.py tests/test_ui_mini_app_frame.py` (RED) | 실패(의도) | 하네스 실행 ID 없음 | `ui_window_card` 없음, `MiniAppCheckBox` 없음 |
| 같은 + 관련 창 시험 (GREEN) | 통과 | 하네스 실행 ID 없음 | 8번 112개, 9번 137개 |
| `verify.py quick --tests` 8개 파일(카드·틀·휴지통·ui·테마·날짜·문서·수명) 100/125/150% | 통과 | `20261010-074632-ccc2881938` / `20261010-074736-11f3606228` / `20261010-074842-7817b7de17` | 각 356개, Git Bash `QT_SCALE_FACTOR` |
| PowerShell `verify.py release` | 통과 | `20261010-074959-b539017280` | 1,854개 시험·빌드 63초·격리 EXE 3개 시나리오. 작업 폴더 변경(dirty) 상태 기록 |
| TOC 대조 | 통과 | `.../build/build/Analysis-00.toc` | mingw64 원본 0건, Qt DLL은 프로젝트 `.venv` PySide6, `ui_mini_app_frame`·`ui_window_card` 포함 |
| `dist/` 배치 | 완료 | `dist/기후노트_v3.9a.exe` | 94,022,500 bytes, SHA-256 `B3AFC0DD6D593DCA406968395E8BF6967631BB725FEDCC9616C7AB14999945C3` |

## 미해결과 인계

- 남은 문제 / 수동 확인: 새 EXE의 실제 화면 확인, 실제 Windows 다크 설정·125/150% 화면. GitLab Release 게시·push는 별도.
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md)(보조 창 흰 카드, 미니앱 체크박스), [아키텍처](../ARCHITECTURE.md)(모듈 표), [테스트](../TESTING.md).
- 다음 행동: 커밋·병합은 사용자 지시 후. 디자인 점검 다음은 메인 정돈(10~16번).
- 배포·커밋·push 여부: 빌드·`dist/` 배치까지. 커밋·push·게시는 하지 않음.
