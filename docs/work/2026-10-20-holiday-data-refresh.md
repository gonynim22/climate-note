# 작업 기록: 공휴일 데이터 최신화·만료 안내

작성일: 2026-10-20 / 상태: 진행 중 (Task 8 첫 실제 API 갱신 대기)

## 목표와 범위

- 목표: `release`가 시작할 때 공휴일을 API로 다시 받아 추가는 자동 반영하고, 삭제·이름 변경은 멈춘다. 만료 안내에 개발자 메일을 넣는다.
- 변경 대상: `fetch_data.py`(키 읽기·오류 구분·같은 날 이름 `·` 합치기·검증 후 교체·`refresh_holidays`), `tools/verify.py`(release 공휴일 단계·`result.json`의 `holidays`), `date_time_calculator.py`·`ui_date_time_calculator.py`(범위 문구를 데이터에서), `app_info.py`(`APP_CONTACT_EMAIL`)·`holiday_notice.py`(만료 안내).
- 데이터 영향: 없음(`holidays.py`는 이번 작업에서 바꾸지 않음). DB v18·Export v3·salt·설정 키·lock·`APP_VERSION` 유지.
- 제외 범위: 앱 런타임 네트워크 호출, 임의 계산·추정, 첫 실제 API 갱신(Task 8).
- 시작 시 사용자 변경: 다른 미추적 문서·`motion/`은 건드리지 않음.

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 추가 자동·삭제/변경 중단, 일부만 발표된 새 연도 제외, 키는 공휴일 단계에서만, 종료 코드 환경 2 / 데이터 1.
- [x] 관련 자동 검사: quick(관련 시험)·full 통과.
- [ ] 필요한 수동 확인: 첫 실제 API 실행(Task 8)과 만료 안내 실제 화면.

## 결정과 진행

- 2026-10-20: 설계 [spec](../superpowers/specs/2026-10-20-holiday-data-refresh-design.md), 계획 [plan](../superpowers/plans/2026-10-20-holiday-data-refresh.md).
- 2026-10-20: 같은 날 이름은 API 순서대로 중복 없이 `·`로 합친다. 핵심 이름 8개(1월1일·삼일절·광복절·개천절·한글날·기독탄신일·설날·추석)를 연도별로 검증한다.
- 2026-10-20: 쓰기는 임시 파일 → 재검증 → 백업 → `os.replace`. 수동 `python fetch_data.py`가 삭제·변경을 받아들이는 공식 경로다.
- 2026-10-20: 만료 안내는 줄바꿈을 4~5줄로 나눴다(두 줄 문구가 380px 창에서 429px 막대가 됨). 문구·시점은 설계대로.
- 2026-10-20: 버전 표시 변경 없음 — 미배포 v4.4에 포함.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `verify.py quick --tests tests/test_holiday_notice.py tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py tests/test_date_time_integration.py` | 통과 (340/340) | `20261020-235505-2b6adcdaa4` (`output/harness/<run-id>/summary.md`) | 커밋 a13dc98 + 문서 변경, 네트워크 없음 |
| `verify.py full` (1차) | 실패 (2976/2977) | `20261020-235551-42da331b1f` | `test_file_conversion_runner.py::test_real_batch_worker_outputs_and_isolation`만 실패(변환 작업 비정상 종료). 이 브랜치 변경과 무관한 파일 변환 작업자 시험 |
| `verify.py quick --tests ...::test_real_batch_worker_outputs_and_isolation` | 통과 (단독) | `20261021-000242-c7e57eae44` | 단독 재실행은 통과 |
| `verify.py full` (재실행) | 통과 (2977/2977, 실패 0) | `20261021-000304-aee883b960` | 같은 입력 재실행. 위 시험은 부하 시 간헐 실패 가능성 있음 |

현재 입력에 대한 실제 결과만 기입한다. `release`는 실제 API·빌드를 쓰므로 실행하지 않았다.

## 미해결과 인계

- 남은 문제 / 수동 확인: Task 8 — 이 PC에서 첫 실제 API 실행(빈 연도 응답 형식 확인, `python fetch_data.py` 실행, 예상: 2025-05-05 이름에 어린이날 포함, `holidays.py` 커밋). 사용자 승인 필요. `test_real_batch_worker_outputs_and_isolation`의 full 중 1회 간헐 실패(별도 조사 필요).
- 변경한 정본 문서: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/DATE_TIME_CALCULATION.md`
- 다음 행동: Task 8 승인 후 실행, 이후 v4.4와 함께 release.
- 배포·커밋·push 여부: 커밋만 수행, push·release 수행하지 않음
