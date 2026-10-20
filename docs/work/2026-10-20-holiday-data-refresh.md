# 작업 기록: 공휴일 데이터 최신화·만료 안내

작성일: 2026-10-20 / 상태: 구현·첫 실제 갱신 완료 (만료 안내 실제 화면 확인·release 남음)

## 목표와 범위

- 목표: `release`가 시작할 때 공휴일을 API로 다시 받아 추가는 자동 반영하고, 삭제·이름 변경은 멈춘다. 만료 안내에 개발자 메일을 넣는다.
- 변경 대상: `fetch_data.py`(키 읽기·오류 구분·같은 날 이름 `·` 합치기·검증 후 교체·`refresh_holidays`), `tools/verify.py`(release 공휴일 단계·`result.json`의 `holidays`), `date_time_calculator.py`·`ui_date_time_calculator.py`(범위 문구를 데이터에서), `app_info.py`(`APP_CONTACT_EMAIL`)·`holiday_notice.py`(만료 안내).
- 데이터 영향: `holidays.py`를 실제 API로 한 번 갱신(Task 8, 아래 결정과 진행). DB v18·Export v3·salt·설정 키·lock·`APP_VERSION` 유지.
- 제외 범위: 앱 런타임 네트워크 호출, 임의 계산·추정.
- 시작 시 사용자 변경: 다른 미추적 문서·`motion/`은 건드리지 않음.

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 추가 자동·삭제/변경 중단, 일부만 발표된 새 연도 제외, 키는 공휴일 단계에서만, 종료 코드 환경 2 / 데이터 1.
- [x] 관련 자동 검사: quick(관련 시험)·full 통과.
- [x] 첫 실제 API 실행(Task 8): 빈 연도 응답 형식 확인, 수동 갱신, 갱신 데이터로 quick 통과.
- [ ] 필요한 수동 확인: 만료 안내 실제 화면.

## 결정과 진행

- 2026-10-20: 설계 [spec](../superpowers/specs/2026-10-20-holiday-data-refresh-design.md), 계획 [plan](../superpowers/plans/2026-10-20-holiday-data-refresh.md).
- 2026-10-20: 같은 날 이름은 API 순서대로 중복 없이 `·`로 합친다. 핵심 이름 8개(1월1일·삼일절·광복절·개천절·한글날·기독탄신일·설날·추석)를 연도별로 검증한다.
- 2026-10-20: 쓰기는 임시 파일 → 재검증 → 백업 → `os.replace`. 수동 `python fetch_data.py`가 삭제·변경을 받아들이는 공식 경로다.
- 2026-10-20: 만료 안내는 줄바꿈을 4~5줄로 나눴다(두 줄 문구가 380px 창에서 429px 막대가 됨). 문구·시점은 설계대로.
- 2026-10-20: 버전 표시 변경 없음 — 미배포 v4.4에 포함.
- 2026-10-21: 최종 검토 수정 — `test_fetch_data.py`를 고정 시험 공휴일로 바꿔 첫 실제 갱신(2025-05-05 이름 합치기)·새 연도 추가 뒤에도 통과하게 함(마지막 연도가 늘어난 파일의 갱신 상태 시험 추가), 시험 기본값은 키 비움·네트워크 차단. 음력은 0건인 달을 실패로 보고 수동 실행이 음력 추가·삭제·변경 건수를 출력. 읽을 수 없는 기존 `holidays.py`(손상·병합 충돌)는 데이터 실패(종료 코드 1), `totalCount`·필드 숫자는 ASCII만. release·수동 실행 시작 때 진행 안내 한 줄, `summary.md`에 "공휴일 최신 확인" 표기. release 시험 보강(최신 확인·삭제만·실제 받기 경로의 키 없음/네트워크 오류에서 키 미기록·손상 파일). `AGENTS.md` 키 사용 범위, `ARCHITECTURE.md`·`DATE_TIME_CALCULATION.md` 고정 연도 표기 정정.
- 2026-10-21: Task 8 첫 실제 갱신(사용자 승인). 빈 연도(2040-01) 응답은 `00 NORMAL SERVICE.`·`totalCount` 0·항목 0건으로 "자료 없음" 처리와 맞음. 1차 `python fetch_data.py`는 공휴일 2035-07 요청 `TimeoutError`로 쓰기 전에 멈춤(`holidays.py` 변경 없음 확인). 2차 실행 성공. 변경: 2025-05-05 `부처님오신날` → `어린이날·부처님오신날`, 2027 추가 2건(`2027-05-03 대체공휴일(노동절)`, `2027-07-19 대체공휴일(제헌절)`), 2028년 18건 추가(제외 연도 없음), 음력 추가·삭제·변경 0건. 공휴일 83건·음력 9496건, 범위 2025–2028. 만료 안내는 이제 2028년 12월부터 나온다. 백업 `output/holiday-refresh/20261021-084259/holidays.py`.
- 2026-10-21: EXE에 함께 들어가는 `licenses/DATA-SOURCES.txt`의 "공휴일: 2025~2027년"을 고정 연도 없는 문장으로 바꿨다(release마다 범위가 늘어나므로).

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `verify.py quick --tests tests/test_holiday_notice.py tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py tests/test_date_time_integration.py` | 통과 (340/340) | `20261020-235505-2b6adcdaa4` (`output/harness/<run-id>/summary.md`) | 커밋 a13dc98 + 문서 변경, 네트워크 없음 |
| `verify.py full` (1차) | 실패 (2976/2977) | `20261020-235551-42da331b1f` | `test_file_conversion_runner.py::test_real_batch_worker_outputs_and_isolation`만 실패(변환 작업 비정상 종료). 이 브랜치 변경과 무관한 파일 변환 작업자 시험 |
| `verify.py quick --tests tests/test_file_conversion_runner.py::test_real_batch_worker_outputs_and_isolation` | 통과 (132/132) | `20261021-000242-c7e57eae44` | quick 기본 목록에 이 시험 하나를 더한 실행(단독 실행 아님). 이 시험은 통과 |
| `verify.py full` (재실행) | 통과 (2977/2977, 실패 0) | `20261021-000304-aee883b960` | 같은 입력 재실행. 위 시험은 부하 시 간헐 실패 가능성 있음 |
| (최종 검토 수정) `verify.py quick --tests tests/test_fetch_data.py tests/test_verify.py tests/test_holiday_notice.py tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py` | 통과 (352/352) | `20261021-004119-38770393c9` | 커밋 63afdbf, 네트워크·키 없음 |
| (최종 검토 수정) `verify.py full` | 통과 (3006/3006, 실패 0) | `20261021-004157-13fc7f0b23` | 커밋 63afdbf. 새 시험 29개 포함(2977 → 3006) |
| (최종 검토 수정) 데이터 상태 시뮬레이션: `holidays.py` 사본 3종에서 `tests/test_fetch_data.py` | 통과 (각 89/89) | 하네스 밖 임시 폴더(저장소 밖) | 사본: 현재 그대로 / 2025-05-05 "어린이날·부처님오신날" / 그 위에 2028년 추가. 수정 전 시험은 같은 사본에서 1건·4건 실패. 같은 두 사본을 `holidays` 모듈로 올려 공휴일 관련 6개 시험 파일도 각 341/341 통과. 실제 `holidays.py`는 바꾸지 않음 |

| (Task 8) 빈 연도 응답 확인 `SpcdeInfoService` 2040-01 | `00` / `NORMAL SERVICE.` / `totalCount` 0 / 항목 0 | 화면 출력만(키·URL 미출력) | 실제 API |
| (Task 8) `python fetch_data.py` (1차) | 실패 (종료 코드 1) | 화면 출력 | 공휴일 2035-07 요청 `TimeoutError`. 쓰기 전 중단, `holidays.py` 변경 없음 |
| (Task 8) `python fetch_data.py` (2차) | 통과 (종료 코드 0) | 백업 `output/holiday-refresh/20261021-084259/holidays.py` | 공휴일 변경 21건(추가 20·변경 1), 음력 변경 0건 |
| (Task 8) `verify.py quick --tests tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py tests/test_holiday_notice.py tests/test_ui.py tests/test_fetch_data.py tests/test_verify.py` | 통과 (474/474) | `20261021-084318-a88a7ddd1a` | 갱신된 `holidays.py`(2025–2028). 계획 목록에 `test_fetch_data.py`·`test_verify.py`를 더해 실제 데이터 변경 뒤 시험 독립성 확인. 경고 1건은 qfluentwidgets의 scipy 경로 사용 경고 |
| (Task 8) `verify.py quick --tests tests/test_ui_licenses.py tests/test_packaging.py` | 통과 | `20261021-084516-24687a977e` | `licenses/DATA-SOURCES.txt` 문구 변경 뒤 |

현재 입력에 대한 실제 결과만 기입한다. `release`는 실제 API·빌드를 쓰므로 실행하지 않았다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 만료 안내 실제 화면. 요청 한 건의 시간 초과로 전체가 멈춤(Task 8 1차에서 실제로 발생) — release 공휴일 단계(약 312건)도 같아서 종료 코드 2로 멈출 수 있음, 다시 실행하면 됨(재시도 추가는 후속 검토). 핵심 이름에 5~7월 공휴일 없음(어린이날·현충일 추가는 후속 검토). `tests/test_file_conversion_runner.py::test_real_batch_worker_outputs_and_isolation`의 full 중 1회 간헐 실패(별도 조사 필요).
- 변경한 정본 문서: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/DATE_TIME_CALCULATION.md`
- 다음 행동: v4.4와 함께 release(공휴일 단계가 "최신 확인"으로 지나가는지 확인).
- 배포·커밋·push 여부: 커밋만 수행, push·release 수행하지 않음
