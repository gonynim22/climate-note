# 작업 기록: 바탕화면 아이콘 클릭 시 캘린더가 잠깐 앞으로 나옴

작성일: 2026-10-25 / 상태: 완료(커밋 전)

## 목표와 범위

- 목표: 캘린더 위에 탐색기·브라우저를 띄워 둔 채 바탕화면 **아이콘**을 누르면 캘린더가 0.35초 맨 앞으로 나왔다가 들어가는 문제(사용자 v4.4b 제보)를 고친다.
- 변경 대상: `show_desktop_guard._is_desktop_click`, `tests/test_show_desktop_guard.py`, Win+D 계약 문서(AGENTS·UI 계약·아키텍처).
- 데이터 영향: 없음. DB v18·Export v3·salt·설정 키·버전 표시·의존성을 바꾸지 않는다.
- 제외 범위: Win+D를 다시 눌러 되돌릴 때 캘린더가 다른 창 위에 남는 문제(별도 후속), 버전 올림·빌드(v4.5에서).
- 시작 시 사용자 변경: 사용자가 만든 앱 아이콘 미커밋 변경(SVG·ICO·`tools/generate_app_icons.py`·`icon/app.png` 삭제·AGENTS/ARCHITECTURE 아이콘 줄)과 기존 미추적 기록·`motion/`. 건드리지 않는다.

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 바탕화면 아이콘 클릭(버튼을 뗀 뒤 알림)도 클릭으로 보고 pulse하지 않는다. Win+D(Win 키 눌림)·'바탕화면 보기' 버튼(커서가 작업 표시줄)은 지금처럼 pulse한다. 판정 실패 시 pulse 유지, 영구 topmost·재부모화 금지 유지.
- [x] 관련 자동 검사: `tools/verify.py quick --tests tests/test_show_desktop_guard.py tests/test_ui_keep_desktop.py`
- [x] 필요한 수동 확인: 실화면 기록으로 아이콘 클릭·빈 바탕화면 클릭·Win+D(커서가 캘린더 위/빈 바탕화면 위)·바탕화면 클릭 뒤 Win+D·'바탕화면 보기' 버튼. 터치패드 세 손가락 바탕화면 보기는 기록에 없음(아래 미해결).

## 결정과 진행

- 2026-10-25 원인 재확인: `output/harness/20261025-desktop-icon-click/traces/1-icon-click.log`(v4.4b 소스, 합성 데이터)에서 아이콘 클릭 3회(0.87·19.10·25.51초)는 모두 바탕화면 활성화 알림이 마우스 버튼을 뗀 뒤 와서 `down=[]`, 커서 아래 최상위 창은 `Progman`이었고 바로 `top=1`(pulse, 덮는 창 없음)이 됐다. 빈 바탕화면 클릭 3회(23.10·24.21·26.70초)는 `down=[L]`이라 pulse가 없었다. 현재 `_is_desktop_click`이 "버튼 눌림"을 필수로 요구해 아이콘 클릭을 Win+D로 본다. v4.4a부터 있던 판정 빈틈이다.
- 구분 근거(이전 실화면 기록 전체의 바탕화면 활성화 알림): Win+D 5회(`20261024-desktop-click-manual/traces/4-click-check-final.log` 33.02·67.97초, `20261025-win-d-desktop-active/traces/1-desktop-active-win-d.log` 81.08초, `2-fixed-desktop-active-win-d.log` 48.94·52.27초)는 모두 `down=[Win]`이었고 그중 2회(33.02·81.08초)는 커서가 바탕화면 위였다. 그 전 기록 1~3은 키 상태를 남기지 않았다. 그래서 커서 위치만으로는 Win+D와 클릭을 가를 수 없다. '바탕화면 보기' 버튼 2회는 `down=[]`, 커서 아래 `Shell_TrayWnd`였다. 기존 시험 `test_desktop_click_needs_button_down_over_desktop`은 Win+D를 "키·버튼 없음 + 커서가 바탕화면"으로 흉내 내 실측과 달랐다.
- 결정: 알림 순간 Win 키(왼쪽·오른쪽)가 눌려 있지 않고 커서 아래 최상위 창이 셸 바탕화면이면 클릭으로 본다(마우스 버튼 눌림은 더 이상 필수가 아니다). 키·버튼 없이 바탕화면을 올리는 경로(터치패드 제스처, 자동 입력 도구가 Win 키를 곧바로 떼는 Win+D)는 클릭으로 잘못 볼 수 있지만, 바탕화면이 활성인 동안 바탕화면이 감시 창을 덮으면 v4.4b REORDER 확인이 같은 pulse를 하므로 보호가 사라지지 않는다. 이 되살림 경로를 시험으로 고정한다.
- 구현: `_is_desktop_click`이 Win 키(`VK_LWIN`·`VK_RWIN`)가 눌려 있으면 `False`, 아니면 커서 아래 최상위 창이 셸 바탕화면인지만 본다. 쓰지 않게 된 마우스 버튼 상수는 모듈에서 빼고 시험 파일로 옮겼다. 시험: 기존 `test_desktop_click_needs_button_down_over_desktop`을 실측대로 `test_desktop_click_is_mouse_activation_over_desktop`으로 바꿨다(아이콘 클릭=키·버튼 없음+바탕화면 → 클릭, Win+D=Win 키+바탕화면 → 아님, 버튼=작업 표시줄 → 아님). 수정 전 이 시험이 아이콘 클릭 단언에서 실패함을 확인했다. 클릭으로 본 뒤 settle 전에 바탕화면이 올라오면 REORDER에서 pulse하는 `test_show_desktop_taken_for_click_is_rescued_by_reorder`를 더했다(기존 안전망이라 수정 전에도 통과).
- 실화면 기록(`output/harness/20261025-desktop-icon-click-fixed/traces/2-fixed-icon-click.log`, 수정 소스 앱 `main.py`, 이전 기록의 합성 데이터 사본, large·두 번째 모니터, 탐색기·터미널을 위에 겹침): 바탕화면 활성화 알림 12회를 모두 분류대로 처리했다. 아이콘 클릭 4회(25.84·27.54·30.82·41.48초, `down=[]`·커서 아래 `Progman`)는 pulse 없이 탐색기·터미널 뒤에 그대로였다(`top=0`, `cov=(CabinetWClass, CASCADIA…)`). 빈 바탕화면 클릭 2회(38.19·50.14초, `down=[L]`) pulse 없음. 다른 창이 활성일 때 Win+D 4회는 모두 `down=[Win]`이었고 pulse로 남았다. 커서가 캘린더 위였던 2회(163.81·166.37초)와 **커서가 빈 바탕화면 위였던 2회**(179.14·180.91초, 이번 판정이 직접 가르는 경우)다. 바탕화면이 이미 활성일 때 Win+D 2회(44.64·50.47초, 알림 없음)는 REORDER 경로로 pulse했다. '바탕화면 보기' 버튼 2회(56.78·62.82초, 커서 아래 `Shell_TrayWnd`)도 pulse했다. 실제 가려짐(`gap<0`·`top=0`)은 0회, 앱 오류 로그 0바이트. 다른 점이 있으면 알려 달라고 했고 사용자는 이상을 알리지 않았다.
- `gap=-12 top=1` 3회(44.69·62.82·179.14초)는 pulse 시작 직후 첫 샘플에만 나타났고 5~8ms 뒤 `gap=19`로 정상이었다. 감시 스크립트는 창 목록을 훑는 도중 셸이 순서를 바꿔 바탕화면을 못 찾으면 `gap=-(순번)`으로 적는다. topmost 대역의 창은 일반 창인 바탕화면 아래에 있을 수 없으므로 실제 가려짐이 아닌 측정 흔적으로 판단했다(덮는 창도 없음).
- 첫 기록 `1-fixed-icon-click.log`(7분)는 조작 없이 끝나 증거로 쓰지 않는다.
- Win+D를 다시 눌러 되돌린 뒤 캘린더가 다른 창 위에 남는 기존 후속(바탕화면이 이미 활성이던 경우 `gap=539 cov=()`)은 이번 범위 밖이며 그대로 재현됐다.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다. 단순 문구 수정에는 별도 작업 기록을 요구하지 않는다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_show_desktop_guard.py -k "desktop_click_is_mouse_activation or taken_for_click"` (수정 전) | 실패 1·통과 1 | 직접 실행 | 새 판정 시험이 아이콘 클릭 단언(`assert False is True`)에서 실패, 되살림 시험은 통과 |
| `pytest tests/test_show_desktop_guard.py` (수정 후) | 통과 34개 | 직접 실행 | |
| `tools/verify.py quick --tests tests/test_show_desktop_guard.py tests/test_ui_keep_desktop.py` | 통과 210개 | `20261025-020525-a003126571` / [summary.md](../../output/harness/20261025-020525-a003126571/summary.md), [result.json](../../output/harness/20261025-020525-a003126571/result.json) | 실패·오류·skip 0. 검사 뒤에는 문서만 고쳤다(AGENTS·UI 계약·아키텍처·이 기록) |
| 실화면 기록 | 확인 | `output/harness/20261025-desktop-icon-click-fixed/traces/2-fixed-icon-click.log` | 위 '결정과 진행' 참고. 합성 데이터 소스 앱, `zwatch4.py` 읽기 전용 |
| full·release·EXE | 미실행 | | v4.5 최신화 단계에서 실행 |

현재 입력에 대한 실제 결과만 기입한다. 이전 버전의 테스트 수를 현재 통과로 복사하지 않는다.
`output/harness/<run-id>/summary.md` 및 `result.json`을 연결한다.
로그는 gitignore 대상이므로 다른 개발자가 재현하려면 명령·커밋·검사 입력 해시도 확인한다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 터치패드 세 손가락 바탕화면 보기·Win 키를 곧바로 떼는 자동 입력 Win+D(클릭으로 볼 수 있어 REORDER 되살림에 기댐, 시험으로만 확인), 터치패드 탭 클릭, 업무 PC 등 다른 Windows 빌드, 실제 EXE. Win+D 되돌림 시 캘린더가 위에 남는 문제는 별도 후속.
- 변경한 정본 문서: [개발 지침](../../AGENTS.md) Win+D 보호 줄, [UI 계약](../UI_PATTERNS.md) 바탕화면 고정, [아키텍처](../ARCHITECTURE.md) `show_desktop_guard.py` 줄. RELEASE_HISTORY·AGENTS 기록 관리는 v4.5 최신화 때 함께 적는다.
- 다음 행동: v4.5 최신화(버전·기록·full·PowerShell release·EXE 확인) 때 이 수정을 포함한다.
- 배포·커밋·push 여부: 수행하지 않음(브랜치 `fix/v4.4b-must-fixes`, 사용자 아이콘 작업 미커밋 변경과 같은 작업 폴더)
