# 작업 기록: v4.2 일정 세부 설정 카드 리디자인

작성일: 2026-10-18 / 상태: 소스 구현·UI 검증 완료, 승인된 빌드·커밋·push 진행 중

## 목표와 범위

- 목표: [확정 설계](../superpowers/specs/2026-10-18-schedule-options-card-redesign-design.md)의 A 구성 + Azure 색표를 Qt 세부 카드에 구현하고 표시 버전을 v4.2로 갱신한다.
- 변경 대상: `ui_schedule_options.py`의 카드·작은 달력, `schedule_rules.py`의 표시 도우미 두 개, 관련 테스트, `app_info.py`, UI 계약·릴리스 기록.
- 데이터 영향: 없음. DB v18·Export v3·설정 키·salt·저장값·기존 규칙을 유지한다.
- 제외 범위: 시계 버튼·알약 줄·목록·알림 카드의 디자인, GitLab Release 게시(사용자가 수행).
- 후속 승인 범위: AGENTS.md 갱신, 커밋, EXE 빌드·검증·dist 배치, `git push origin main`.
- 시작 시 사용자 변경: 추적 파일 변경 없음. 설계 문서와 기존 `docs/work/` 미추적 문서 8개(9/11 보안·버전 기록, 9/17 릴리스 기록, 9/24 환산기 시안, 10/4 최초 설정, 10/9 디자인 기록 2개, 10/11 컴퓨터 사용 기록)를 보존한다.

## 완료 조건

- [x] 320px 카드, Azure 머리띠·세그먼트·아이콘, 알림 설명, 짧은 기간 문구·줄바꿈, 연결된 달력 띠 구현.
- [x] 즉시 반영·시간 검증·키보드·팝업 수명·여러 날/반복 배타·365일 상한 유지.
- [x] 설계의 관련 quick 검사를 100/125/150% 합성 배율에서 통과.
- [x] 세 상태 렌더를 기준 시안과 대조하고 차이를 설명.
- [x] UI 계약과 v4.2 메타데이터 갱신, 수동 확인 결과를 확인함/미확인으로 구분.
- [ ] 승인 후속: AGENTS 기록·커밋 → PowerShell release 전체 검사/빌드/격리 EXE 검증 → dist 배치 → 결과 기록·커밋 → main push.

## 결정과 진행

- 2026-10-18: AGENTS.md, UI·아키텍처·검증·릴리스 지침과 확정 설계를 확인했다. 로컬 기준 HTML 및 기존 카드 캡처 스크립트가 있다. 앱은 오프라인 PySide6/Qt UI, Qt·DB 없는 `schedule_rules` 규칙, 암호화 SQLite 저장 계층으로 분리되어 있으며 이번 변경은 표시 계층에 한정한다.
- 2026-10-18: `app_info.py`를 v4.2 / 2026. 10. 18.로 갱신한다. 설계 §11.7에 따라 커밋·push·EXE 빌드·Release는 별도 승인 전 수행하지 않는다.
- 2026-10-18: 머리띠·선택 바·아이콘·반복 끝 줄을 재배치했다. 시각 알림 설명은 보고 있는 발생일을 기준으로 계산하고, 기간 끝날은 실제 글자 폭에 따라 같은 줄/다음 줄에 둔다. 기간 버튼의 평문 `text()`·클릭 동작을 유지하며 날짜/일수의 색만 나누어 그린다.
- 2026-10-18: 작은 달력을 `QFrame`으로 그려 배경/테두리를 적용하고, 시작일의 선택 불가 상태와 띠 표시를 함께 유지했다. 분수 배율에서 픽셀 경계는 안티앨리어싱되므로 연결 여부는 실제 칸 경계로, 채움색은 안쪽 픽셀로 검사한다.
- 2026-10-18: 시계 버튼·알약 줄·위치 함수·기존 아이콘/말줄임 부품과 `schedule_rules.py`의 기존 모든 함수/클래스를 HEAD와 AST 대조하여 무변경을 확인했다. 순수 함수는 `alarm_caption`·`period_short_caption`만 추가했다.
- 2026-10-18: 최종 100/125/150% quick 각 323개 통과. 접근성·동일 폭·카드 높이·긴 기간 줄바꿈·색/달력 띠·Tab/Enter/Space·머리띠 동작과 기존 저장/수명 회귀를 포함한다. `git diff --check` 및 변경 문서 링크 확인도 통과했다.

영구 UI 계약은 [UI_PATTERNS.md](../UI_PATTERNS.md)에 반영한다.

- 2026-10-18 후속 요청: 사용자가 AGENTS.md 업데이트·커밋·빌드·push를 명시적으로 승인했다. GitLab Release는 사용자가 게시한다. 이전의 별도 승인 대기 상태는 이 요청으로 해소되었다. 원격 main을 fetch하여 시작 HEAD와 동일함을 확인했다. 기존 미추적 문서 8개와 이전 v4.1 EXE는 보존하고 이번 작업 파일만 커밋한다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 초기 quick 100% | 실패 | [20261018-001747-aadbfdc8cb](../../output/harness/20261018-001747-aadbfdc8cb/summary.md) | 290 통과·1 실패: 이전 시작일 role=end 기대값. 설계대로 start로 변경 |
| 중간 quick 100% | 통과(중간 입력) | [20261018-002231-c5164432a7](../../output/harness/20261018-002231-c5164432a7/summary.md) | 323개. 이후 픽셀 검사 수정으로 최종 근거는 아래 100% 재검사 |
| 초기 quick 125% | 실패 | [20261018-002336-c0c591ddf0](../../output/harness/20261018-002336-c0c591ddf0/summary.md) | 322 통과·1 실패: 띠 경계의 안티앨리어싱 색을 단색과 비교. 간격 검사는 유지하고 색 표본만 안쪽으로 이동 |
| 최종 quick 125% | 통과 | [20261018-002501-673bd7602b](../../output/harness/20261018-002501-673bd7602b/summary.md) · [result.json](../../output/harness/20261018-002501-673bd7602b/result.json) | 323 통과·실패/오류/skip 0 |
| 최종 quick 150% | 통과 | [20261018-002605-dc4923bb2b](../../output/harness/20261018-002605-dc4923bb2b/summary.md) · [result.json](../../output/harness/20261018-002605-dc4923bb2b/result.json) | 323 통과·실패/오류/skip 0 |
| 최종 quick 100% | 통과 | [20261018-002705-b0a612685e](../../output/harness/20261018-002705-b0a612685e/summary.md) · [result.json](../../output/harness/20261018-002705-b0a612685e/result.json) | 323 통과·실패/오류/skip 0 |
| 기준 시안 대조, 200% 카드 PNG | 통과 | [비교 HTML](../../output/design/schedule-options-redesign-20261017/after/comparison.html) | 기존 `capture_current.py`를 복사한 `capture_after.py`로 생성. 기존 `current/` 보존 |
| 메인 3크기·팝업 위치 합성 렌더 | 통과 | [20261018-002808-schedule-card-visual](../../output/harness/20261018-002808-schedule-card-visual/summary.md) · [result.json](../../output/harness/20261018-002808-schedule-card-visual/result.json) | 실제 MainCalendarWindow / 실행별 AppData / native foreground hook 비활성. 기본 위·중간/크게 아래, 카드 화면 경계 안에 표시 |
| data / full 별도 실행 | 미실행 | | 후속 release가 전체 pytest를 포함하므로 중복 실행하지 않음 |
| 승인 후 release / EXE 빌드 | 미실행 | | PowerShell에서 전체 검사·새 빌드·합성 4개 시나리오 실행 예정 |

최종 명령(PowerShell, `QT_SCALE_FACTOR`를 `1`·`1.25`·`1.5`로 각각 설정):

```powershell
$env:QT_SCALE_FACTOR="1"
.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_ui_schedule_options.py tests/test_schedule_rules.py tests/test_ui_schedule_input.py tests/test_ui_schedule_list.py tests/test_ui_schedule_emoji.py tests/test_packaging.py
```

세 최종 검사의 기준 HEAD는 `53239e2f38d77dd5b3c0656178e594f7fd544bec` + 이 작업의 미커밋 변경이다. 실행 전후 `inputs_before.files == inputs_after.files`이고 세 실행의 입력 목록도 같다. 그 목록을 정렬·공백 없는 JSON으로 직렬화한 SHA-256은 `658d4997cdf06101188ce7942d20e2bf332a4cc40822480b9923be017676610b`이며 파일별 해시는 각 `result.json`에 있다. 공통 경고 1건은 기존 qfluentwidgets의 SciPy deprecated import다.

### 화면 대조 및 수동 확인

- 기준: `UI-Final.dc.html`의 확정 Azure 시안, 기존 `preview-uicolors.png` 마지막 세 상태.
- 실제 카드(200% 합성 렌더, 논리 px): 기본 **320×232**, 시각/알림/매주 **320×287**, 여러 날 **320×441**. 목표 222/274/442에서 +10/+13/−1px이며 모두 허용치 ±15px 안이다.
- 설명된 차이: Qt의 테두리/레이아웃 및 글꼴 측정에 따른 높이 차이, 기존 벡터 아이콘 모양과 실제 달력의 요일/공휴일 색은 유지한다. 실제 앱 캡처에는 기존 `focus_first()` 규칙에 따른 파란 포커스 테두리가 있다. 머리띠·색 단계·순서·들여쓰기·짧은 문구·기간 띠는 시안과 대조했다.
- [기본 화면](../../output/harness/20261018-002808-schedule-card-visual/compact-with-card.png) · [중간 화면](../../output/harness/20261018-002808-schedule-card-visual/medium-with-card.png) · [크게 화면](../../output/harness/20261018-002808-schedule-card-visual/large-with-card.png)

| 항목 | 결과 | 확인 범위/제한 |
|---|---|---|
| 소스 앱 기본·중간·크게와 카드 위/아래 위치 | 확인함(합성 데이터 렌더) | 세 실제 MainCalendarWindow PNG 대조. 자동 경계 검사 포함 |
| 키보드 Tab/Enter/Space/Esc, 시간 입력·선택·달력·머리띠 닫기 | 자동 검사 통과 / 수동 미확인 | 실제 포커스된 위젯에 키 입력. 사람의 실기 조작으로 확인하지 않음 |
| Win11 넓은 DWM 테두리 없음 | 미확인 | 기존 `remove_dwm_border` 호출/창 플래그 무변경. QWidget.grab은 DWM 프레임을 찍지 않음 |
| 실제 혼합 DPI·KVM·Win+D | 미확인 | 합성 배율 및 PNG가 실기 검사를 대신하지 않음 |
| EXE 최종 화면·정상 종료·배포 | 미확인 | 이번 작업에서 EXE를 만들거나 실행하지 않음 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 자동 검사 실패 없음. 위 실기 수동 항목은 미확인.
- 변경한 정본 문서: UI_PATTERNS.md, RELEASE_HISTORY.md. README_detail.md의 현재 소스 버전·빌드 이름 및 v4.1 EXE 증거와의 구분도 반영.
- 다음 행동: 승인된 EXE 빌드·검증·배치 후 결과를 기록하고 main에 push.
- 배포·커밋·push 여부: 진행 중. GitLab Release는 사용자 담당.
