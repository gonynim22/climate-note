# 작업 기록: 미니앱 공용 창 틀(디자인 점검 5번, B안)

작성일: 2026-10-10 / 상태: 로컬 구현·검증 완료(full `20261010-064315-f4a1aaa0b6`), main 병합(`481d644`, fast-forward). 버전·빌드·push는 사용자 승인 대기

## 목표와 범위

- 목표: 미니앱 5개 창을 어두운 제목줄(+같은 색 왼쪽 메뉴) 공용 틀 하나로 맞춘다. [설계](../superpowers/specs/2026-10-10-mini-app-frame-design.md), [계획](../superpowers/plans/2026-10-10-mini-app-frame.md).
- 사용자 결정(2026-10-10): 시안 B(어두운 메뉴). 고른 메뉴의 왼쪽 막대(띠)는 없이 지금처럼 선택 바탕만. 계획서 작성 뒤 검토 없이 바로 구현. 시안은 `output/design/miniapp-frame-20261010/frame-concepts.html`.
- 변경 대상: 새 `ui_mini_app_frame.py`, `ui_unit_converter.py`, `ui_date_time_calculator.py`, `ui_money_notation.py`, `ui_document_converter.py`, `screen_text/window.py`, `main.py`(체크 색 `Accent`), 새 `tests/test_ui_mini_app_frame.py`, `tests/test_app_theme.py`, `docs/UI_PATTERNS.md`·`docs/ARCHITECTURE.md`·`docs/TESTING.md`·`AGENTS.md`.
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·미니앱 메모리 기록·창 수명 불변. 검사는 임시 폴더 합성 데이터만 쓴다.
- 제외 범위: 메뉴·본문 안 배치, 8번(날짜·시간 체크박스 모양), 20·21번, 주머니, 버전 변경·빌드·push.
- 시작 시 사용자 변경: `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 7개는 보존한다.

## 완료 조건

- [x] 다섯 창 모두 표면 맨 위 전체 폭에 `MiniAppTitleBar`(48px, `#23252B`, 아이콘·이름·닫기). 메뉴 앱은 메뉴도 `#23252B`, 메뉴 없는 앱은 본문 `#FDFDFB`.
- [x] 제목줄 끌기로 창 이동(화면 안 유지), 닫기 버튼 Enter·클릭·Esc로 닫힘.
- [x] 문서 변환의 보라 값 제거(버튼·표 머리·진행 막대·제목·환경 문구), 체크 색 `Accent` `#2563EB`.
- [x] 기존 크기·무스크롤·경계·좁은 화면·수명 시험 통과, 100/125/150% quick, full.
- [ ] 필요한 수동 확인: 실제 EXE에서 다섯 창 열기·끌기·닫기, 실제 125/150% 화면에서 제목줄 아이콘 선명도.

## 결정과 진행 (실행 원장)

- 실행 방식: 사용자 지시에 따라 계획 검토 없이 이 세션에서 직접 실행(서브에이전트 없음). 원장은 `.superpowers/sdd` 대신 이 작업 기록에 둔다(AGENTS.md가 작업 기록을 요구).
- Task 1: 공용 제목줄 모듈과 다섯 창 공통 시험 — RED(모듈 없음, `Accent` `#009faa`) → GREEN. 창 시험은 Task 2~5 뒤 통과.
- Task 2: 날짜·시간·금액 — 머리줄(52/40px)을 제목줄(48/40px)로. 관련 시험 126개 통과.
- Task 3: 문서 변환 — 표면 = 제목줄 + 내용(여백 18·12·18·16), 보라 값 제거. 28개 통과.
- Task 4: 화면 글자 따기 — 표면 = 제목줄 + 내용(여백 18·10·18·16), 바탕 `#FDFDFB`, 쓰지 않게 된 `QFrame` import 제거. 99개 통과. `screen_text`는 `ui_mini_app_frame`·`app_paths`만 가져다 쓰고 핵심 모듈은 `screen_text`를 가져오지 않는다(걷어내기 절차 불변).
- Task 5: 단위 환산기 — 표면 = 제목줄 + (분류 메뉴 | 본문). 메뉴 맨 위 "▪ 단위 환산" 삭제, 본문 머리줄은 분류 이름만(44→36px). 250개 통과.
- Ruling: 계획의 공통 시험이 `show_near`로 창을 여는데 단위 환산기에는 없다 — 시험 도우미가 `ui_main._open_unit_converter`와 같이 위치 지정 → `fit_to_screen` → `show`로 연다 — 틀리면 환산기 열기 경로 차이를 시험이 놓칠 수 있음(실제 경로와 같은 순서라 위험 낮음).
- Ruling: 150% 합성 배율(낮은 논리 화면)에서 끌기 시험의 아래 이동 20px이 `fit_to_screen`으로 되돌려졌다 — 앱이 창을 화면 안에 지키는 정상 동작이므로 기대 y를 `min(시작+20, 화면 아래-창 높이)`로 하고 가로 이동과 화면 안 유지를 함께 단언 — 틀리면 세로 끌기 회귀가 화면이 낮을 때만 가려진다(가로 이동은 계속 검사).
- Ruling: 단위 환산기의 분류 이름은 더 이상 끌기 손잡이가 아니다(끌기는 제목줄) — 다른 네 창과 같은 규칙 — 분류 이름을 잡고 끌던 사용자는 제목줄을 잡아야 한다.
- Final review: 자체 검토(이 세션은 사용자 요청 없이 서브에이전트를 띄우지 않는다). 작성자 검토라 새 눈의 검토보다 약하다.
- Final: minor (deferred): 아이콘 경로 규칙이 `ui_mini_apps.mini_app_icon()`과 `ui_mini_app_frame.mini_app_icon_path()` 두 곳에 있다.
- Final: minor (deferred): 어두운 둥근 모서리 가장자리에 밝은 표면이 1px 비친다(기존 어두운 메뉴의 아래 왼쪽 모서리와 같은 현상, 100%에서 거의 보이지 않음).
- 전/후 캡처: `output/design/miniapp-frame-20261010/img/now_*.png`(수정 전), `after_*.png`(수정 후), 같은 합성 데이터.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_ui_mini_app_frame.py tests/test_app_theme.py` (RED, 구현 전) | 실패(의도) | 하네스 실행 ID 없음 | `ModuleNotFoundError: ui_mini_app_frame`, `Accent` `#009faa` |
| 창별 시험(Task 2~5) | 통과 | 하네스 실행 ID 없음 | 126 / 28 / 99 / 250개 |
| `verify.py quick --tests` 공통 틀·테마·미니앱 10개 파일, 150% | 실패 → 시험 수정 | `20261010-063750-eb2a0fa342` | 끌기 시험 5개: 낮은 논리 화면의 y 보정(위 Ruling) |
| 같은 quick 100/125/150% | 통과 | `20261010-063924-8304fb1ff1` / `20261010-064037-28eb614694` / `20261010-064153-fb652adf43` | 각 420개, Git Bash `QT_SCALE_FACTOR` |
| `verify.py full` | 통과 | `20261010-064315-f4a1aaa0b6` | 1,847개(실패·오류·건너뜀 0, 기존 1,831 + 새 16), 모든 코드 수정 뒤 실행 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 EXE 확인, 8번(날짜·시간 체크박스 모양 — 체크 색은 이제 파랑), 위 deferred minor 2건.
- 변경한 정본 문서: [UI 계약](../UI_PATTERNS.md)(미니앱 공용 창 틀, 문서 변환 색), [아키텍처](../ARCHITECTURE.md)(모듈 표), [테스트](../TESTING.md), `AGENTS.md`(금액 도우미 줄의 창 틀 문구, 기록 관리).
- 다음 행동: 2026-10-10 사용자 지시로 `feat/mini-app-frame`에 커밋(`481d644`)하고 `main`에 fast-forward 병합한 뒤 브랜치를 지웠다. 사용자 미커밋 `AGENTS.md` 4줄·`docs/RELEASE_HISTORY.md`는 커밋하지 않고 보존했다. 버전·PowerShell release 빌드·push는 별도 승인. 디자인 점검 다음은 8·9번.
- 배포·커밋·push 여부: `main` 커밋·병합까지. 빌드·push는 하지 않음.
