# 작업 기록: 일정 이모지 하단 잘림

작성일: 2026-09-10 / 상태: 소스 수정·검증·로컬 커밋 완료 / GitLab 보안 검사로 push 차단

## 목표와 범위

- 목표: 일정 이모지의 하단 잘림을 재현하고 표시 영역을 수정한다.
- 변경 대상: `ui_main.py`, `tests/test_ui_schedule_emoji.py`, `docs/UI_PATTERNS.md`, `AGENTS.md`.
- 데이터 영향: 표시 수정만 수행한다. DB v17·본문 Unicode·암호화·설정·salt와 저장 경로를 유지한다.
- 제외 범위: EXE 빌드·게시, 실제 사용자 데이터 및 실행 중 앱 검사.
- 시작 시 사용자 변경: `.gitignore` 수정이 있으며 그대로 보존한다.

## 완료 조건

- [x] 잘리는 위치와 원인을 합성 UI에서 확인하고 이모지 전체가 표시되도록 수정한다.
- [x] 기존 선택·키보드·포커스·저장 동작과 달력 크기 계약을 유지한다.
- [x] 관련 `quick --tests` 검사 및 합성 PNG 확인을 수행한다.
- [x] 실제 환경·혼합 DPI 수동 확인과 EXE 미실행 범위를 구분한다.

## 결정과 진행

- 2026-09-10: `AGENTS.md`, `docs/UI_PATTERNS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`를 확인했다. 이모지는 본문 접두 문자열이며 선택 버튼은 26×26/20px, 선택창은 36×36/22px, 날짜 칩은 medium 16px/large 22px 높이로 표시한다. 합성 화면에서 글리프 잘림을 조사한다.
- 2026-09-10 재현: 독립 선택 버튼·팝업을 확대해도 표시 픽셀이 같아 글꼴 크기 변경은 하지 않았다. 실제 일정 행을 렌더하자 `QListWidget::item`의 상하 padding 6px가 행의 sizeHint 28px에서 차감되어 행은 22px, 내부 편집기는 18px였다. 여기에 26px 이모지 버튼이 들어가 하단이 잘렸다. 편집기를 숨긴 상태에서 sizeHint를 계산하는 순서도 높이 부족의 원인이었다. 새 회귀 검사는 compact/medium/large 모두 같은 원인으로 실패했다.
- 2026-09-10 수정: 목록 padding 3px를 행 레이아웃 여백(기존 4/2/4/2 → 7/5/7/5)에 포함하고 목록 자체 padding은 0으로 바꿨다. 편집기를 표시한 후 sizeHint를 다시 계산한다. 합성 수정 전·후 PNG에서 이모지 버튼과 입력창 하단이 온전히 표시되는 것을 확인했다. 영구 계약은 [UI 계약](../UI_PATTERNS.md)의 일정 행 높이에 반영했다.
- 2026-09-10 검증 완료: 관련 UI 237개 통과 후 125%·150% 배율에서 각각 63개 검사를 통과했다. 세 배율의 compact/medium/large 인라인 행 PNG에서 버튼·입력창 하단을 확인했다. 125% 최초 실행은 샌드박스 접근 오류로 실패하여 승인 후 별도 실행 ID로 재검사했으며 실패 기록도 보존한다. 검증 후 소스·테스트는 변경하지 않았다.
- 2026-09-10 커밋·push 요청: `AGENTS.md`에 행 높이 보존 계약과 이 기록의 링크를 추가했다. 이번 후속 변경은 문서에 한정하며, 세 통과 보고서에 기록된 모든 Python 소스·테스트 및 `UI_PATTERNS.md` 해시가 현재 파일과 같음을 확인했다. 두 문서의 로컬 링크 36개와 기존 AGENTS 지침 보존, `git diff --check`를 확인했다. 지침 문서 추가를 이유로 기존 하네스 보고서를 새로 실행한 결과로 바꾸지는 않는다. 원격보다 앞선 v3.7·일정 이모지 커밋 2개와 이번 수정을 `origin main`에 함께 반영하는 범위다. 기존 `.gitignore` 수정은 커밋에서 제외한다.
- 2026-09-10 push 실패: `git push origin main`은 서버 pre-receive 보안 검사에서 거부되었다. Semgrep은 `fetch_data.py:11`·`tools/verify.py:21`의 XML 파서, `fetch_data.py:23,36`의 동적 urllib 사용을 지적했고 검사기 오류 1건도 보고했다. OSV-Scanner는 Pygments 2.19.2·cryptography 46.0.4 등 잠금 의존성에서 취약점 항목을 보고했다(출력 예시 5건 + 생략 54건이며 독립 검증한 취약점 수는 아님). Gitleaks·Trivy·Syft는 PASS였다. `fetch_data.py`는 기존 원격과 동일했다. 원격 `refs/heads/main`은 `aa383a1fe16e736afe1b656a69169bad2412863b`로 유지됨을 확인했다. 거부 사실만 작업 기록에 추가하며 소스·검사·의존성은 변경하지 않는다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 수정 전 `quick --tests tests/test_ui_schedule_emoji.py::test_display_search_and_popup_geometry` | 통과 | `20260910-015626-bf8061c3a5` / [summary.md](../../output/harness/20260910-015626-bf8061c3a5/summary.md) | 60 passed. 기존 표시 검사만으로 인라인 버튼 잘림을 발견하지 못했다. 현재 수정의 통과 근거로 사용하지 않음. |
| 수정 전 `quick --tests tests/test_ui_schedule_emoji.py::test_inline_emoji_button_fits_row_before_and_after_edit` | 실패(재현 성공) | `20260910-020233-c4915152fa` / [summary.md](../../output/harness/20260910-020233-c4915152fa/summary.md) | 3 failed / 57 passed. 3모드 모두 18px 편집 영역이 26px 버튼을 포함하지 못함. |
| 수정 후 `quick --tests tests/test_ui_schedule_emoji.py tests/test_ui.py` | 통과 | `20260910-020313-9277261a47` / [summary.md](../../output/harness/20260910-020313-9277261a47/summary.md), [result.json](../../output/harness/20260910-020313-9277261a47/result.json) | 237 passed / 0 failed / 0 skipped. 기존 SciPy deprecation warning 1건. |
| `QT_SCALE_FACTOR=1.25` + `quick --tests tests/test_ui_schedule_emoji.py::test_inline_emoji_button_fits_row_before_and_after_edit tests/test_ui_schedule_emoji.py::test_display_search_and_popup_geometry` | 실패(환경) | `20260910-020443-89a7265135` / [summary.md](../../output/harness/20260910-020443-89a7265135/summary.md) | 29 passed / 34 setup errors. 샌드박스의 pytest-tmp 접근 거부(WinError 5). 이후 승인 후 새 실행 ID로 재검사. |
| 위 125% 명령 재실행 | 통과 | `20260910-064329-c1af0c1c64` / [summary.md](../../output/harness/20260910-064329-c1af0c1c64/summary.md), [result.json](../../output/harness/20260910-064329-c1af0c1c64/result.json) | 63 passed / 0 failed / 0 skipped. 세 모드 편집 행 PNG 확인. |
| 위 명령의 `QT_SCALE_FACTOR=1.5` 실행 | 통과 | `20260910-201608-cd94d6fe0f` / [summary.md](../../output/harness/20260910-201608-cd94d6fe0f/summary.md), [result.json](../../output/harness/20260910-201608-cd94d6fe0f/result.json) | 63 passed / 0 failed / 0 skipped. 세 모드 편집 행 PNG 확인. |
| 합성 UI PNG 확인 | 통과 | [수정 전](../../output/harness/20260910-020233-c4915152fa/schedule-emoji-inline-compact.png), [수정 후](../../output/harness/20260910-020313-9277261a47/schedule-emoji-inline-compact.png) | 실제 사용자 화면은 캡처하지 않음. 이모지 버튼 하단 및 입력창 확인. |
| 실제 한글 IME·혼합 DPI/KVM·EXE | 미실행 | | 별도 수동 확인 범위 |
| `git push origin main` / `git ls-remote origin refs/heads/main` | 실패(서버 보안 검사) / 원격 미반영 확인 | pre-receive: `SECURITY SCAN REJECTED`, 종료 코드 1 | Semgrep·OSV-Scanner FAIL. 원격 main은 `aa383a1` 유지. 자동 하네스 통과와 GitLab 게시 결과를 구분. |

## 미해결과 인계

- 남은 문제 / 수동 확인: GitLab 보안 지적·검사기 오류의 상세 확인과 조치가 필요하다. 의존성 업그레이드는 AGENTS의 lock 갱신·전체 재검증·EXE 재빌드·검증 스냅샷 갱신 계약에 따라 별도 범위로 수행한다. 실제 사용자 환경·물리 혼합 DPI/KVM과 EXE는 미실행. 사용자가 별도 위치를 지정하지 않아 합성 화면에서 재현한 일정 인라인 편집 하단 잘림을 수정했다.
- 정본 문서: [개발 지침](../../AGENTS.md), [UI 계약](../UI_PATTERNS.md), [검증](../TESTING.md).
- 커밋·push 상태: 소스와 지침·검사·이 기록은 로컬 커밋으로 보존한다. push는 서버 보안 검사로 차단되었고 원격 미반영이다. 커밋 식별자는 `git log -1 -- docs/work/2026-09-10-schedule-emoji-clipping.md`로 확인한다. 기존 `.gitignore` 수정은 커밋에서 제외했다.
- EXE 빌드·배포: 수행하지 않음.
