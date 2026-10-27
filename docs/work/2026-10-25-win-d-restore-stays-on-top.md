# 작업 기록: Win+D로 되돌린 뒤 캘린더가 다른 창 위에 남음

작성일: 2026-10-25 / 상태: 완료(커밋 전)

## 목표와 범위

- 목표: '바탕화면 보기'(Win+D·작업 표시줄 버튼)를 다시 눌러 창들을 되돌렸을 때 캘린더가 탐색기 등 일반 창 위에 남아(다른 창을 누를 때까지) 그 창들을 가리는 문제를 고친다. v4.4a 때부터 남은 후속이며 사용자가 실화면에서 다시 확인했다("겹친 탐색기가 가려짐").
- 변경 대상: `show_desktop_guard.ShowDesktopKeeper`의 REORDER 처리, `tests/test_show_desktop_guard.py`, Win+D 계약 문서(AGENTS·UI 계약·아키텍처).
- 데이터 영향: 없음. DB v18·Export v3·salt·설정 키·버전 표시·의존성을 바꾸지 않는다.
- 제외 범위: 버전 올림·빌드(v4.5에서). 영구 topmost·WorkerW 재부모화는 계속 금지.
- 시작 시 사용자 변경: 사용자 아이콘 작업 미커밋 변경(다른 모델이 같은 폴더에서 진행 중), 앞선 [아이콘 클릭 수정](2026-10-25-desktop-icon-click-flicker.md) 미커밋 변경. 사용자 결정으로 v4.5 마무리 때 한꺼번에 커밋한다.

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 바탕화면 보기 뒤 셸이 바탕화면을 다시 맨 아래로 내리면 캘린더도 바탕화면 바로 위로 따라 내려간다. Win+D 보호(pulse)·바탕화면 클릭 무 pulse·다른 '바탕화면 고정' 앱과 서로 밀어내는 반복이 생기지 않게 한 번만 따라간다.
- [x] 관련 자동 검사: `tools/verify.py quick --tests tests/test_show_desktop_guard.py tests/test_ui_keep_desktop.py`
- [x] 필요한 수동 확인: 실화면 기록으로 바탕화면 활성 상태 Win+D 되돌림, '바탕화면 보기' 버튼 되돌림, 탐색기 활성 상태 Win+D 되돌림(지금도 정상), 아이콘·빈 바탕화면 클릭 회귀.

## 결정과 진행

- 2026-10-25 재현 기록(`output/harness/20261025-desktop-icon-click-fixed/traces/2-fixed-icon-click.log`, 아이콘 클릭 수정 소스 앱, 합성 데이터)에서 되돌림 6회를 비교했다.
  - 정상 2회(탐색기가 활성일 때 Win+D, 164.79·167.06초): 되돌리면 탐색기가 다시 활성화되고(FOREGROUND) 앱이 고정한다. 셸이 되살린 창들을 그 위에 올리고 바탕화면을 맨 아래로 내려 캘린더는 탐색기·터미널 아래(`cov=(CabinetWClass, CASCADIA…)`)다. 커서를 바탕화면에 둔 180.05·181.48초도 같다.
  - 문제 2회(바탕화면이 이미 활성일 때 Win+D, 45.25·53.22초): 되돌릴 때 활성화되는 앱이 없다. 셸은 창들을 아직 위에 있는 바탕화면 **아래**에 되살린 뒤(45.27초 `DESK idx=32 normal_below=5`) 바탕화면만 맨 아래로 내린다(45.30초 루트 데스크톱 REORDER, `DESK idx=569 normal_above=5`). 바탕화면 보기 동안 올라온 바탕화면 바로 위에 고정돼 있던 캘린더는 그대로 모든 창 위에 남는다(`gap=539 cov=()`, 47.40초 사용자가 누를 때까지).
  - 문제 2회('바탕화면 보기' 버튼으로 되돌림, 57.34·65.86초): 버튼을 누를 때 작업 표시줄이 활성화돼 앱이 고정하지만, 그 순간 바탕화면이 아직 위에 있어 그 바로 위(맨 위)로 고정된다. 뒤이어 바탕화면이 내려가면 같은 상태가 된다(57.51초 `gap=539 cov=()`).
- 원인: 셸이 바탕화면을 **올릴 때**는 pulse·REORDER 덮임 확인으로 따라 올라가지만, **내릴 때**는 따라 내려가는 처리가 없다. 바탕화면을 내리는 순간 루트 데스크톱 REORDER는 앱에도 오지만 처리기는 "바탕화면이 덮었나"만 보고, 바탕화면이 활성이 아니면(버튼 경우) 그마저 보지 않는다.
- 결정: `ShowDesktopKeeper`에 `_desktop_raised`(바탕화면 보기로 바탕화면이 올라왔고 따라 내려갈 차례)를 두고 `_start_topmost_pulse()`에서 켠다(활성화 알림 pulse·REORDER 덮임 pulse 모두). 루트 데스크톱 REORDER에서 pulse 중이 아니고 기존 덮임 pulse에 해당하지 않으면, `_desktop_raised`일 때 `_above_other_windows()`(바탕화면 호스트에서 `GW_HWNDPREV`로 올라가며 보이는 감시 창을 모두 만나기 전에 보이고 최소화되지 않은 다른 창을 만나는지, 1만 회 제한)를 보고 참이면 플래그를 끄고 `_pin_to_desktop_layer()`(실패 시 `_demote_all`)를 한 번 한다. 바탕화면이 활성인지는 보지 않는다(버튼 경우는 작업 표시줄이 활성). `set_enabled`·`shutdown`은 플래그를 끈다.
  - 한 번만 따라가는 이유: 매 REORDER마다 감시 창 아래의 창을 밀어내면 같은 방식으로 바탕화면 바로 위를 차지하려는 다른 앱과 서로 밀어내며 끝없이 반복할 수 있다. 되돌림 한 번에 한 번이면 충분하다(실측에서 바탕화면을 내린 뒤 창 순서 변화 없음).
  - 버린 안: 최소화 해제(`EVENT_SYSTEM_MINIMIZEEND`) 뒤 타이머로 재고정 — hook이 하나 더 늘고 바탕화면이 내려가는 시점(MINEND 뒤 약 25~30ms)과 맞추려면 지연을 짐작해야 하며 그동안 캘린더가 위에 보인다. 모든 REORDER에서 상시 강제 — 위의 서로 밀어내기 위험.
- 시험(먼저 실패 확인): `test_show_desktop_restore_follows_desktop_back_down`(바탕화면 활성 상태 되돌림 + 한 번 따라간 뒤 다른 창이 사이에 들어와도 다시 밀지 않음), `test_show_desktop_button_restore_follows_desktop_back_down`(작업 표시줄 활성화 후 바탕화면이 내려감) 둘 다 수정 전 `assert _is_above(other, widget)`에서 실패했다. `test_reorder_without_show_desktop_leaves_windows_below_alone`(pulse가 없었으면 재고정 없음)은 수정 전후 통과.
- 실화면 기록(`output/harness/20261025-win-d-restore/traces/2-fixed-restore.log`, 수정 소스 앱, 합성 데이터 사본, large·두 번째 모니터, 탐색기·터미널을 위에 겹침): 바탕화면 활성 상태 Win+D 되돌림 3회(10.76·13.63·15.73초)는 캘린더가 창들 위에 남은 시간이 5.7ms·0(샘플 없음)·6.1ms 뒤 `cov=(CASCADIA…, CabinetWClass)`로 돌아갔다(수정 전 다른 창을 누를 때까지, 이전 기록에서 약 2.1초 이상). '바탕화면 보기' 버튼 되돌림 2회(24.61·27.13초)는 위에 남은 샘플조차 없었다. 탐색기 활성 상태 Win+D 2회(32.66·37.30초)는 pulse·되돌림 모두 정상이다. 아이콘 클릭 1회(40.38초, `down=[]`)·빈 바탕화면 클릭 2회(8.90·34.63초, `down=[L]`)는 pulse가 없었다. 앱 오류 로그 0바이트. 첫 기록 `1-fixed-restore.log`(15분)는 조작 없이 끝나 증거로 쓰지 않는다.
- 관찰(이번 변경과 무관): 9.99초 `gap=-567 top=0` 한 샘플(8ms 이하) 뒤 pulse(`top=1`)가 됐다. 바탕화면이 활성일 때 Win+D는 바탕화면이 먼저 올라온 뒤 REORDER로 pulse하는 v4.4b 경로라 반응 시간이 있고, 덮임 확인을 먼저 하는 순서는 이번에 바꾸지 않았다. 화면 한 장(16.7ms)보다 짧다. 45.56초 12.8ms는 사용자가 캘린더를 직접 눌렀을 때의 기존 동작(활성화 직후 데스크톱 레이어로 재고정)이다.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다. 단순 문구 수정에는 별도 작업 기록을 요구하지 않는다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_show_desktop_guard.py -k "restore_follows or leaves_windows_below"` (수정 전) | 실패 2·통과 1 | 직접 실행 | 두 되돌림 시험이 `assert _is_above(other, widget)`(373·407행)에서 실패 |
| `pytest tests/test_show_desktop_guard.py` (수정 후) | 통과 37개 | 직접 실행 | |
| `tools/verify.py quick --tests tests/test_show_desktop_guard.py tests/test_ui_keep_desktop.py` | 통과 213개 | `20261025-023405-7b1711a6b5` / [summary.md](../../output/harness/20261025-023405-7b1711a6b5/summary.md), [result.json](../../output/harness/20261025-023405-7b1711a6b5/result.json) | 실패·오류·skip 0. 검사 뒤에는 문서(AGENTS·UI 계약·아키텍처·검증·이 기록)만 고쳤다 |
| 실화면 기록 | 확인 | `output/harness/20261025-win-d-restore/traces/2-fixed-restore.log` | 위 '결정과 진행' 참고. 합성 데이터 소스 앱, `zwatch4.py` 읽기 전용 |
| full·release·EXE | 미실행 | | v4.5 최신화 단계에서 실행 |

현재 입력에 대한 실제 결과만 기입한다. 이전 버전의 테스트 수를 현재 통과로 복사하지 않는다.
`output/harness/<run-id>/summary.md` 및 `result.json`을 연결한다.
로그는 gitignore 대상이므로 다른 개발자가 재현하려면 명령·커밋·검사 입력 해시도 확인한다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 EXE, 업무 PC 등 다른 Windows 빌드, 다른 '바탕화면 고정' 앱과 함께 쓸 때, 터치패드 바탕화면 보기, 혼합 DPI·KVM. 바탕화면이 활성일 때 Win+D의 REORDER pulse 반응 시간(8ms 이하 한 번 관찰)은 v4.4b 경로 그대로다.
- 변경한 정본 문서: [개발 지침](../../AGENTS.md) Win+D 보호 줄, [UI 계약](../UI_PATTERNS.md) 바탕화면 고정, [아키텍처](../ARCHITECTURE.md) `show_desktop_guard.py` 줄, [검증](../TESTING.md) v3.4 수동 릴리스 게이트에 되돌림 확인 한 줄. RELEASE_HISTORY·AGENTS 기록 관리는 v4.5 최신화 때 함께 적는다.
- 다음 행동: v4.5 최신화(버전·기록·full·PowerShell release·EXE 확인) 때 이 수정을 포함한다.
- 배포·커밋·push 여부: 수행하지 않음. 사용자 결정으로 v4.5 마무리 때 아이콘 변경·[아이콘 클릭 수정](2026-10-25-desktop-icon-click-flicker.md)과 한꺼번에 커밋한다.
