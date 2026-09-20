# 작업 기록: 미니앱 정사각형 타일·환산기 확대·환경 단위

작성일: 2026-09-21 / 상태: 진행 중

## 목표와 범위

- 목표: 미니앱 주머니를 정사각형 타일 격자로 바꾸고 환산기 가독성과 환경 분야 단위를 보완한다.
- 변경 대상: ui_mini_apps.py, ui_unit_converter.py, unit_converter.py, 관련 테스트·정본 문서.
- 데이터 영향: 메모리 전용 계산/레이아웃만 변경. DB v17·Export v2·salt·기존 설정 키·바로가기 6개 유지.
- 제외 범위: 밀도/분자량/온도/압력이 필요한 서로 다른 농도 기준 간 환산, 추정 건강영향/배출량, 외부 앱 로더.
- 시작 시 사용자 변경: .gitignore, AGENTS.md, docs/RELEASE_HISTORY.md 및 기존 미추적 작업 기록 3개. 보존하고 이번 커밋에서 제외한다. 원본 지침 사본은 output/mini-app-environment-baseline/에 보관.
- 시작 HEAD: e3f32e0. 버전은 v3.8 / 2026. 9. 21. / 3.8.0.0 유지.

## 완료 조건

- [x] 132×132 타일을 2열로 배치하는 정사각형 주머니, 항목 증가 시 세로 스크롤.
- [x] 환산기 기본 440×580, 글자/입력/선택 영역 확대, 작은 화면 보정 유지.
- [x] 기체 농도(몰분율), 질량비, 수질 농도, 유량 4분류 추가. 기준을 화면에서 구분.
- [x] 독립 환산 기준값·왕복·오류/경계·UI·기존 데이터 보존 검증.
- [ ] 100/125/150% 합성 렌더 검토, 새 EXE 빌드 및 격리 smoke.

## 결정과 진행

- ppm·ppb·ppt는 각각 10^-6/10^-9/10^-12로 명시하며 몰분율과 질량분율을 별도 분류로 둔다. NIST는 SI 표기에 µmol/mol·mg/kg 같은 명확한 비율 단위를 권장하므로 함께 제공한다.
- 수질 mg/L는 질량/부피 기준이며 ppm=mg/L로 고정하지 않는다. USGS의 농도 정의와 밀도 보정 설명을 확인했다. 유량은 실제 부피 기준이고 표준상태 유량을 추정하지 않는다.
- 영구 계약: [단위 정의](../UNIT_CONVERSION.md), [UI](../UI_PATTERNS.md), [검증](../TESTING.md), [아키텍처](../ARCHITECTURE.md).
- 4분류·31항목을 추가하여 합계 25분류·178항목. 몰/질량분율은 0~100%, 수질 농도/유량은 0 이상을 검증한다. 최근 기록은 같은 ppm 표기라도 분류별로 구분한다.
- 첫 UI 검사에서 메인의 300×220 덮어쓰기를 확인해 팝업 자체 크기를 사용하도록 변경했다. 후속 검사에서 실행 중 타일을 추가할 때 스크롤의 크기 갱신이 늦는 것을 확인해 grid 최소/최대 크기 계약과 타일 표시를 명시했다.
- 125/150% 실제 Qt 위젯 PNG를 열어 주머니/기체·수질 화면을 확인했다. 이 이미지는 소스 UI 렌더이며 EXE 화면 캡처는 아니다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 유의사항 |
|---|---|---|---|
| quick + 계산/UI/주머니, 100% | 실패: 4 실패·258 통과 | [20260921-023413-9a3c63ef9a](../../output/harness/20260921-023413-9a3c63ef9a/summary.md) | 메인의 구형 팝업 크기 고정, 수정 완료 |
| quick + 계산/UI/주머니, 125% | 실패: 1 실패·261 통과 | [20260921-023652-cb474cf841](../../output/harness/20260921-023652-cb474cf841/summary.md) | 추가 타일의 스크롤 갱신, 수정 완료 |
| quick + 계산/UI/주머니, 125% | 통과: 262개 | [20260921-023744-5da7081e12](../../output/harness/20260921-023744-5da7081e12/summary.md) | 모든 새 환산 기준값/경계·실제 입력·기존 DB dump/Export/salt 보존 |
| quick + 환산기 배치/환경 입력/작은 화면·주머니, 150% | 통과: 97개 | [20260921-023832-664df5c025](../../output/harness/20260921-023832-664df5c025/summary.md) | 실제 혼합 DPI와 구분 |
| release | 미실행 | | 기존 결과를 재사용하지 않음 |

재현: `QT_SCALE_FACTOR=1.25`의 별도 PowerShell 프로세스에서 `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_unit_converter.py tests/test_ui_unit_converter.py tests/test_ui_mini_apps.py`.
150%는 `QT_SCALE_FACTOR=1.5`로 `test_ui_unit_converter.py::test_render_categories_and_actual_geometry`, `::test_disconnected_screen_and_smaller_work_area_are_clamped`, `::test_environment_basis_input_and_recent_restore`, `test_ui_mini_apps.py`를 추가했다.

## 미해결과 인계

- 수동 확인: 실제 혼합 DPI/KVM·Win+D·회사 PC·새 EXE 직접 클릭/정상 종료는 자동 smoke와 별도.
- 배포·커밋·push: 기존 요청에 이어 로컬 커밋·빌드 예정. 원격 push/게시 없음.
