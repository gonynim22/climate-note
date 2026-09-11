# 작업 기록: 캘린더 요일 열 너비 수정

작성일: 2026-09-11 / 상태: 구현·검증·로컬 커밋 완료, 원격 보안 검사로 push 차단

## 목표와 범위

- 목표: 세로 화면 large 보기의 요일 열 축소와 월 이동에 따른 너비 변화를 수정한다.
- 변경 대상: `ui_main.py`, 관련 UI 회귀 테스트, `AGENTS.md`와 UI 계약·검증 기록.
- 데이터 영향: 표시 레이아웃만 수정한다. 앱 v3.7·DB v17·Export v2·암호화·salt·저장 경로·기존 설정 키와 저장값을 유지한다.
- 시작 시 사용자 변경: `.gitignore` 수정은 보존하고 이번 커밋에서 제외한다. 직전 조사에서 추가한 진단 코드·작업 기록은 이번 수정과 함께 보존한다.
- 승인 범위: 수정, AGENTS.md 업데이트, 커밋, `https://gitlab.aigov.go.kr/whrhkdrh/climate-note`로 push. EXE는 로컬 재빌드·격리 검증하고 git에 넣지 않는다.

## 완료 조건

- [x] 실제 배치된 7열이 일정 분포·추가·월 왕복·화면 왕복에 영향받지 않고 요일 제목과 정렬된다.
- [x] 좁은 칩의 말줄임, 전체 본문 툴팁, large/medium/compact 동작을 검증한다.
- [x] 기존 합성 데이터·salt·schema 보존과 신규 EXE 실행을 검증한다.
- [x] AGENTS.md/UI 계약 갱신, 관련 파일만 로컬 커밋.
- [ ] 명시적 `main` push와 원격 커밋 확인: 서버 pre-receive 보안 검사 거부로 미반영.

## 결정과 진행

- 원인과 대조 실험: [이전 조사](2026-09-11-large-calendar-column-width-investigation.md).
- 2026-09-11: 진단으로 확인한 최소 변경은 일정 칩의 가로 sizeHint를 레이아웃 입력에서 제외하고 날짜/요일 제목 그리드 7열에 동일한 stretch를 설정하는 것이다. 실제 칩 말줄임 갱신도 회귀 검사한다.
- 원격 fetch 시 로컬 main에 기존 v3.7 후속 커밋 4개가 있고 원격만의 커밋은 없다. 이번 수정 커밋과 함께 main을 정상 fast-forward push한다. archive 브랜치는 사용하지 않는다.
- 수정은 `ui_main.py` 5줄 추가로 끝났다. 일정 칩에 가로 `Ignored`를 적용하고 날짜/요일 제목 7열에 stretch=1을 준다. DB 관련 모듈·앱 버전·의존성은 수정하지 않는다.
- 회귀 검사에서는 실제 자식 셀을 QWidget 안에 배치한다. Windows top-level 창의 최소 프레임 폭이 68px 칩 축소 실험에 개입하지 않게 하며, 요청 폭과 실제 셀 폭이 같은지도 확인한다.
- 영구 계약을 [AGENTS.md](../../AGENTS.md), [UI 계약](../UI_PATTERNS.md), [아키텍처](../ARCHITECTURE.md), [검증](../TESTING.md)에 반영했다.
- `release`가 전체 pytest 663건·EXE 빌드·3개 smoke 시나리오 모두 통과했다. 기존 합성 데이터의 schedules/memos/sticky_notes/dday_widgets/focus_widgets/focus_sessions/shortcuts/app_settings 8개 테이블 raw/복호화 해시·ID와 salt 해시가 실행 전후 같았다. EXE smoke의 기존 데이터 시나리오는 compact이며, large에서의 암호문·메모·설정·salt·Export 보존은 신규 소스 회귀 검사로 별도 확인했다.
- 검증 뒤 README의 최신 로컬 빌드 해시/기록 링크와 RELEASE_HISTORY의 이번 결과를 갱신했다. 해당 문서 수정은 런타임 코드·리소스·빌드 설정을 바꾸지 않는다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `quick --tests tests/test_ui_calendar_columns.py`, 수정 전 | 실패: 6건 / 통과: 59건 | [20260911-210405-1ffe3960d3](../../output/harness/20260911-210405-1ffe3960d3/summary.md) | large 3개 크기·medium 열 너비 4건과 칩 축소 2건 실패. 칩 검사는 이후 top-level 최소 폭 영향을 제거하도록 자식 위젯으로 보완 |
| 같은 quick, 수정 후 | 통과: 65건 | [20260911-210510-0fb3ac854d](../../output/harness/20260911-210510-0fb3ac854d/summary.md) | 신규 8건 포함. 기본 배율 native Qt. 최종 지침 문구 추가 전 검사이며 최종 입력은 release로 검증 |
| `python diagnostics/calendar_columns_probe.py --width 864 --height 1536`, 수정 후 현행 코드 | 증상 해소 관측, exit 0 | [20260911-210651-columns-5d11777b](../../output/harness/20260911-210651-columns-5d11777b/summary.md) | 첫 표시·금토 추가·월 왕복·화면 왕복에서 58/59px 유지. offscreen PNG 직접 확인: 제목과 날짜 정렬, 금·토의 일정 텍스트 표시 |
| `.\.venv\Scripts\python.exe tools/verify.py release` | 통과: pytest 663건, build, smoke 3개 | [20260911-210624-06a98aabf3](../../output/harness/20260911-210624-06a98aabf3/summary.md) | 입력 해시 불변. 신규 schema 17/32바이트 salt/유효 백업, 기존 데이터 보존, 손상 salt 원본 보존 |
| `QT_SCALE_FACTOR=1.25` + `quick --tests tests/test_ui_calendar_columns.py tests/test_ui_screen_change.py` | 통과: 69건 | [20260911-210950-319411a3a8](../../output/harness/20260911-210950-319411a3a8/summary.md) | native Qt + 합성 배율/모니터, 실제 혼합 DPI 전환 아님 |
| `QT_SCALE_FACTOR=1.5` + 같은 quick | 통과: 69건 | [20260911-211139-04faec35fb](../../output/harness/20260911-211139-04faec35fb/summary.md) | README/릴리스 결과 기록 갱신 후 입력. 검사 중 입력 불변 |
| 문서 링크·diff·release 입력 대조 | 통과 | 로컬 검토 | 수정 문서의 로컬 링크 존재, `git diff --check`, 런타임/테스트/DB/암호화/버전/빌드/lock 해시가 release 검사 입력과 일치 |

## 새 EXE

- 파일: `dist/calendar-column-fix-20260911/기후노트_v3.7.exe` (이전 EXE 덮어쓰기 없음).
- 크기: 57,907,537 bytes / File·Product Version: 3.7.0.0 / Authenticode: NotSigned.
- SHA-256: `0A3A85C1E082A81CEFE742FE63BDE642427D0A389ACE11D4309277ACACB2F379`.
- release 산출물과 로컬 복사본의 해시가 일치한다. git에는 추가하지 않는다.

## 수동 배포 확인

| 항목 | 결과 | 근거/제한 |
|---|---|---|
| 합성 세로 화면의 열 너비·요일 정렬·금토 일정 표시 | 확인 | 소스 offscreen PNG 육안 확인 및 native Qt geometry 회귀 |
| 실제 회사 PC의 혼합 DPI·가로/세로·KVM | 미확인 | 합성 배율과 구분 |
| EXE 정상 종료 직전 저장·최종 설정/휴지통 동작 | 미확인 | source 저장 회귀는 통과, EXE smoke는 Job 강제 종료 |
| Win+D 뒤 Explorer/브라우저 전환 | 미확인 | 이번 수정 범위 밖 |
| Defender·라이선스·SBOM·Qt 고지·서명 | 미확인/보류 | 기존 보류 항목 유지 |
| GitLab Release EXE 게시 | 미실행 | 이번 원격 작업은 소스 main push |

## 미해결과 인계

- 실제 회사 PC의 혼합 DPI/KVM·최종 사용자 화면은 수동 미확인으로 구분한다.
- 수정 커밋: `ca0f617192d509b4062582571fee49e51e8e4793` (`fix: keep calendar weekday columns stable on portrait screens`). 기존 `.gitignore` 사용자 변경은 커밋하지 않았다.
- `git push origin main`을 실행했으나 GitLab의 pre-receive hook이 `SECURITY SCAN REJECTED`로 거부했다. 인증/권한 실패가 아닌 서버의 코드·의존성 보안 검사 실패다.
- 거부 후 `git ls-remote origin refs/heads/main`으로 원격이 기존 `aa383a1fe16e736afe1b656a69169bad2412863b`에 그대로 있음을 확인했다. 이번 수정과 로컬에 먼저 있던 v3.7 후속 4개 커밋은 원격에 반영되지 않았다.
- 서버 응답 요약: Gitleaks PASS / Semgrep FAIL / OSV-Scanner FAIL / Trivy PASS / Syft PASS. [push 거부 기록](../../output/harness/20260911-210624-06a98aabf3/push-rejection.txt).
- Semgrep: `fetch_data.py:11`, `tools/verify.py:21`의 `xml.etree.ElementTree` 사용에 ERROR; `fetch_data.py:23,36` 동적 urllib 호출에 WARNING; 검사기 오류 1건도 보고했다.
- OSV-Scanner: `Pygments 2.19.2`의 `PYSEC-2026-2987`, `GHSA-5239-wwwm-4pmq`; `cryptography 46.0.4`의 `PYSEC-2026-2141`, `PYSEC-2026-35`, `PYSEC-2026-3552`; 그 외 54건을 보고했다. 나머지 상세 목록/수정 버전은 서버 응답에 없다.
- 위 파일과 의존성은 이번 캘린더 수정 커밋에서 변경하지 않았다. origin/main과 비교해도 cryptography/Pygments 버전은 같으며, lock 차이는 이전 컬러 이모지 수정의 Qt 계열 4개 버전뿐이다. 이 사실이 서버 지적의 오탐을 의미하지는 않는다.
- 원격 반영을 마무리하려면 전체 보안 검사 보고서 및 검사기 오류 원인을 확인하고, 필요한 코드/의존성 보안 수정과 lock·전체 검사·EXE 재빌드를 한 묶음으로 검증해야 한다. 이번 조사에서 검사 예외나 bypass는 추가하지 않았다.
