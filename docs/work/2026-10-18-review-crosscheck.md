# 작업 기록: 외부 모델 코드 점검 교차검증

작성일: 2026-10-18 / 상태: 완료(교차검증, 제품 수정 없음)

## 목표와 범위

- 목표: `tmp/2026-10-18-code-review-findings.md`의 33개 주장과 제안, 테스트 공백을 현재 `0554595` 코드·계약·격리 재현으로 판정한다.
- 변경 대상: 이 작업 기록, 별도 교차검증 보고서와 합성 재현 자료만 추가한다. 제품 수정은 하지 않는다.
- 데이터 영향: 실행별 `output/harness/` 합성 데이터만 사용한다. 실사용 AppData·DB·salt·실행 중 앱에는 접근하지 않는다.
- 제외 범위: 새 EXE 빌드/배포, 의존성 변경, 커밋/push, 실제 KVM/Win+L/한글 변환 환경 검사.
- 시작 시 사용자 변경: 추적 파일 수정 없음. 기존 untracked 작업 기록 9개, `motion/`, `tmp/` 보존.

## 완료 조건

- [x] 33개 항목을 확인/부분 확인/근거 부족 또는 정책 사항으로 구분하고 근거를 기록한다.
- [x] 주요 결함은 합성 입력으로 재현하며 실제 대용량 메모리 고갈·사용자 화면 캡처를 실행하지 않는다.
- [x] 관련 하네스 결과와 별도 재현 결과, 미실행 범위를 구분한다.
- [x] 사용자에게 우선순위와 잘못된 수정 제안을 설명하는 보고서를 작성한다.

## 결정과 진행

- 2026-10-18: 원문과 현재 HEAD가 같은 `0554595`임을 확인했다. 원문 요약 28건과 본문 33건의 집계 불일치를 발견했다. `karpathy-guidelines`와 `AGENTS.md`, 검증·보안·데이터/UI 계약을 기준으로 검토한다.
- 2026-10-18: 17개 핵심 지적 확인 / 9개 부분 확인 / 7개 결함 판정 보류·정정으로 분류했다. OCR 두 탭은 의도적 독립 편집이고, 구형 날짜 문자열 Import 허용도 기존 호환 계약이다. 추가로 large의 스티키 생성 개수 제한 우회 경로를 확인했다.
- 상세 결과와 수정 우선순위: [교차검증 보고서](../../tmp/2026-10-18-code-review-crosscheck.md).

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `quick --tests tests/test_schedule_rules.py tests/test_schedule_storage.py tests/test_ui_sticky_panel.py tests/test_ui_data_lifecycle.py tests/test_widget_limits.py tests/test_security.py tests/test_screen_text_ui.py tests/test_screen_text_engine.py tests/test_ui_unit_converter.py tests/test_money_notation.py tests/test_date_time_calculator.py` | 통과 664개 | `20261018-104254-e5d3074765` / [summary](../../output/harness/20261018-104254-e5d3074765/summary.md), [result](../../output/harness/20261018-104254-e5d3074765/result.json) | 기존 검사, 제품 수정 없음 |
| `python -X utf8 tmp/run_review_crosscheck.py` | 최종 통과 37개 | `20261018-104745-b85fd33ef8` / [summary](../../output/harness/20261018-104745-b85fd33ef8/summary.md), [result](../../output/harness/20261018-104745-b85fd33ef8/result.json) | 합성 데이터·offscreen Qt, 관찰 재현 성공이지 결함 수정 아님 |
| 재현 도구 초기·확장 실행 | 실패 기록 보존 | `20261018-104510-a5668f27f1`, `20261018-104532-23a8b07aa6`, `20261018-104655-fcd40e2bff` | 순서대로 가짜 위젯 teardown, offscreen clipboard 종료 오류, 원문 설정 조회 8회 가정 불일치(실제 4회). 보고서에 구분 |
| 실제 Win+L/KVM/혼합 DPI/OCR 대용량 추론/HWP 변환/EXE | 미실행 | 해당 없음 | 정적 경로·주입 재현과 실제 환경 장애를 구분 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 확인된 제품 문제는 미수정. 실제 환경 장애 빈도·성능은 별도 검증 필요.
- 변경한 정본 문서: 없음. 리뷰 결과는 구현 계약 변경이 아니다.
- 결과: [33개 항목 교차검증 보고서](../../tmp/2026-10-18-code-review-crosscheck.md).
- 다음 행동: 보고서의 우선순위와 호환성 제약을 기준으로 후속 수정 범위를 정한다.
- 배포·커밋·push 여부: 수행하지 않음.
