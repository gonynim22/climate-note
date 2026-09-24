# 작업 기록: 날짜·시간 계산기 스크롤 제거

작성일: 2026-09-24 / 상태: 완료 (별도 native 메뉴 관측·수동 확인은 아래 보존)

## 목표와 범위

- 목표: A안의 네 모드에서 입력·결과·복사·최근 기록을 스크롤 없이 사용한다.
- 변경 대상: 날짜·시간 계산기 UI, 관련 UI 회귀, UI/계산 계약과 AGENTS.md.
- 데이터 영향: 없음. 계산 엔진·DB v17·Export v2·salt·설정 키·바로가기·메모리 최근 12개와 합산 최대 24개를 유지한다. 버전은 v3.8b를 유지한다.
- 시작 시 사용자 변경: .gitignore, AGENTS.md, docs/RELEASE_HISTORY.md와 미추적 기존 작업 기록 4개. 이번 수정에 섞거나 덮어쓰지 않는다.

## 완료 조건

- [x] 일반 모드와 날짜 포함/날짜만/기간·근무 구간 합산 입력이 스크롤 없이 보인다.
- [x] 합산은 한 항목씩 이전/다음으로 전환하되 전체 행 계산·추가/삭제·종류 전환·최근 복원·오류 표시를 보존한다.
- [x] 기본/좁은 화면 및 125/150% 합성 배율에서 입력·결과·동작 버튼의 실제 배치를 확인한다.
- [x] 관련 회귀와 새 EXE 검증 결과를 기록한다.

## 결정과 진행

- 2026-09-24: 사용자 피드백에 따라 기존 입력 폼 스크롤 계약을 변경한다. 날짜 입력을 두 열로 정리하고 합산은 한 항목씩 표시한다. 단순히 스크롤바를 숨겨 입력을 가리는 방식은 사용하지 않는다.
- 기존 Qt probe에서 기본 시간 차이의 현재 폼 최소 높이는 160px인데 스크롤 본문은 306px, 스크롤 범위는 67px였다. 숨긴 모드의 높이와 세로 날짜 배치가 입력 공간을 과도하게 차지했다. QScrollArea를 제거하고 날짜 2열·합산 단일 항목 탐색으로 변경했다.
- 420×500의 압축 레이아웃에서 이전 최소 높이가 native 창에 남는 것을 확인했다. 화면 변경 시 안쪽 레이아웃부터 현재 최소 크기를 반영한 뒤 창 크기를 보정한다. 기본 크기로 복원할 때 입력·기록·합산 선택 위치는 그대로 유지한다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `quick --tests tests/test_ui_date_time_calculator.py tests/test_date_time_integration.py tests/test_ui_mini_apps.py` | 통과: 173개 | [20260924-233022-c54af91567](../../output/harness/20260924-233022-c54af91567/summary.md) | 현재 수정, 13개 UI 상태×3개 논리 작업 영역 및 실제 입력/합산/수명/기존 데이터 보존 |
| 같은 명령, `QT_SCALE_FACTOR=1.25` | 통과: 173개 | [20260924-233132-211d1d79f1](../../output/harness/20260924-233132-211d1d79f1/summary.md) | 별도 프로세스 합성 배율 |
| 같은 명령, `QT_SCALE_FACTOR=1.5` | 통과: 173개 | [20260924-233251-84b98ceb65](../../output/harness/20260924-233251-84b98ceb65/summary.md) | 별도 프로세스 합성 배율, 날짜 포함 420×500 PNG 확인 |
| 좁고 긴 작업 영역 Qt probe | 통과: 8개 상태의 배치 확인 | `output/harness/20260924-date-time-no-scroll/narrow/` | 420×900, 네 모드의 정상/오류. 하네스 테스트 수에 합산하지 않음 |
| 최초 `release` | 실패: 1개, 통과: 1,279개 | [20260924-233349-abdf216e2c](../../output/harness/20260924-233349-abdf216e2c/summary.md) | 기존 환산기 `reset_prepare` 검사의 창 열기에서 입력 포커스 5초 시간 초과. 빌드/EXE 실행은 도달하지 않음 |
| 환산기 `quick --tests tests/test_ui_unit_converter.py` | 실패: 1개, 통과: 112개 | [20260924-233820-f25b767731](../../output/harness/20260924-233820-f25b767731/summary.md) | 노출 대기 추가 뒤 원래 포커스 검사는 통과. 별도 기체 콤보 `[True-gas]`에서 초기 정상 표시 후 보호 시간 대기 중 메뉴가 닫힌 1건. 즉시 표시/효과 억제 단언은 통과 |
| 최종 `release` | 통과: 1,280개·새 EXE·격리 실행 3개 | [20260924-234234-5118aac61a](../../output/harness/20260924-234234-5118aac61a/summary.md) | 현재 코드/테스트, 오류·skip 0. 이전 실패 기록은 별도 보존 |

## 산출물

- 경로: `D:\04_Project\GC\MyDesktopCalendar\dist\기후노트_v3.8b.exe`
- 크기: 59,023,827 bytes
- SHA-256: `182C34BC719CCC01CEFA93269AF0501C84F995ADBCBC09BB0C8394D6BAE90EA2`
- Windows 숫자 버전: 3.8.2.0. 실제 번들의 9개 Python 모듈과 Qt 6.11.2 DLL 3개·이미지/SVG 3개를 현재 소스/venv와 대조했다. `bundle-verification.json`과 `dist-placement.json`은 최종 release 폴더에 보존한다.
- 이전 EXE: 배치 시 동일 이름의 dist 파일 없음. 최초 v3.8b release의 output/harness/20260924-181520-66630977c0/dist/ 산출물은 그대로 유지.
- 표준 경로 배치: True. 직접 EXE 미니앱 클릭은 수행하지 않았으며 소스 Qt 렌더·번들 코드 대조·격리 시작 3개 시나리오를 구분한다.


## 미해결과 인계

- 실제 회사 혼합 DPI/KVM·Win+D·EXE 정상 종료 수동 확인은 별도다.
- 전체 회귀에서 환산기 창 열기 helper가 native 노출을 기다리지 않고 부모와 공유될 수 있는 active 상태만 확인하는 것을 발견했다. 날짜·시간 통합 검사와 같은 `qWaitForWindowExposed` 선행 대기를 추가했다. 제품 환산기 코드/계산은 변경하지 않았다. 수정된 입력으로 위 최종 release를 통과했다.
- 별도 합성 `UnitConverterWindow`의 기체 콤보 반복 진단에서 최종 15회 중 3회가 클릭 직후 정상 표시 후 닫혔다. 2회는 본창 WindowDeactivate와 동반, 1회는 본창 활성 상태를 유지해 원인을 단정하지 않는다. 날짜·시간 창은 생성하지 않은 독립 진단이며 관련 환산기 제품 코드는 이번에 바꾸지 않았다. 증거: `output/harness/20260924-date-time-no-scroll/gas-popup-events-234119/events.json`. 초기 로그는 팝업 소유 판정 누락이 있어 최종 로그와 구분한다. 이후 새 ID의 전체 release는 통과했지만 간헐적 native 메뉴 닫힘은 별도 미해결 관측으로 유지한다.
- 정본: [날짜·시간 계약](../DATE_TIME_CALCULATION.md), [UI 계약](../UI_PATTERNS.md), [검증](../TESTING.md), [AGENTS.md](../../AGENTS.md).
- 새 EXE 빌드/배치 완료. 이번 변경만 로컬 커밋하며 정확한 커밋은 Git 이력과 최종 release 폴더의 `commit-verification.json`에 기록한다. GitLab push/Release 게시 없음.
