# 작업 기록: 바탕화면 클릭 시 캘린더 깜빡임

작성일: 2026-10-24 / 상태: 완료 — v4.4a(Windows 4.4.1.0) release 통과·루트 `dist/` 배치, 이 기록 커밋 뒤 `git push origin main`. GitLab Release 게시는 사용자

v4.4는 2026-10-21 GitLab Release로 이미 게시됐으므로(SHA-256 `BEEB3C4D…`) 이 수정은 새 표시 버전 v4.4a로 빌드한다.

## 목표와 범위

- 목표: 다른 창이 캘린더 위에 있을 때 바탕화면을 누르면 그 창이 잠깐 사라졌다가 다시 나타나는 현상(사용자 제보)을 없앤다. Win+D 보호는 그대로 유지한다.
- 변경 대상: `show_desktop_guard.py`, `tests/test_show_desktop_guard.py`, 정본 문서 3곳(`AGENTS.md`, `docs/UI_PATTERNS.md`, `docs/ARCHITECTURE.md`)
- 데이터 영향: 없음(DB v18·Export v3·salt·설정 키 그대로, `keep_on_show_desktop` 의미 동일)
- 제외 범위: 아래 '미해결' 2건(Win+D 되돌린 뒤 캘린더가 위에 남음, 바탕화면이 이미 활성일 때 Win+D)
- 시작 시 사용자 변경: `docs/work/` 미추적 기록 7개와 `motion/`은 손대지 않음

## 완료 조건

- [x] 바탕화면 클릭(왼쪽·오른쪽)에서 topmost pulse 없음, 위를 덮던 일반 창은 그대로 위
- [x] Win+D·'바탕화면 보기' 버튼에서는 기존처럼 350ms pulse, 캘린더가 가려지는 순간 없음
- [x] 관련 자동 검사 통과
- [x] 실제 화면(이 PC, Windows 11 26300) 기록으로 확인

## 결정과 진행

- 2026-10-24 원인 확인: 실행 중인 v4.4 EXE의 창 순서를 읽기 전용 감시 스크립트(WinEvent + 4ms 폴링)로 기록. 바탕화면 클릭도 `EVENT_SYSTEM_FOREGROUND(Progman)`를 내므로 `ShowDesktopKeeper`가 Win+D와 똑같이 350ms topmost pulse를 했다. 4회 모두 캘린더가 탐색기 위로 올라갔다가(`top=1`, 덮는 창 없음) 360ms 뒤 다시 뒤로 갔다. 고정 자체(평소 바탕화면 바로 위)는 정상이었다.
- 1차 수정(폐기): 알림 순간 바탕화면이 감시 창을 이미 덮었을 때만 pulse. 단위 검사는 통과했지만 실화면에서 Win+D 때 캘린더가 105~360ms 사라졌다가 나타났다(사용자 제보와 기록 일치). 셸은 바탕화면 활성화 알림 **뒤** 7~250ms에 바탕화면(Progman)을 올린다. 앞선 Win+D 기록에서 "바탕화면을 올리지 않는다"고 본 것은 감시 스크립트가 바탕화면 위치 변화를 기록하지 않은 탓이었다.
- 2차 수정(채택): 알림 순간 마우스 버튼(왼·오·가운데)이 눌려 있고 커서 아래 최상위 창이 셸 바탕화면이면 클릭으로 보고 pulse하지 않는다(`_is_desktop_click`). 판정 실패 시 pulse 유지, 클릭 경로도 settle에서 레이어 재고정. 실화면 기록: 클릭 순간은 매번 `down=[L]/[R] root=Progman`, Win+D는 `down=[Win]`, '바탕화면 보기' 버튼은 `root=Shell_TrayWnd`였다.
- 2026-10-24 빌드 준비: v4.4a 버전 반영 커밋 `5b2be74`. 첫 release를 시작한 뒤 push 전 로컬 OSV에서 `setuptools 83.0.0`(GHSA-xmj3-9gf7-h52w, Low, 84.1.0 해결) 1건이 나와 release를 멈췄다. 10-21 pillow처럼 서버 검사가 거절할 수 있어 EXE 미포함(`build.spec` 제외) setuptools만 84.1.0으로 올리고 lock을 갱신했다(로컬 OSV 0건, doctor `20261024-215613-20cc2ef8b4` 통과, pip freeze 전후 차이는 이 한 줄: `output/harness/20261024-desktop-click-manual/pip-freeze-*.txt`).
- 2026-10-24 release: `352b864` 기준 PowerShell release `20261024-215637-302c493969` 통과(공휴일 최신 확인·변경 없음, 3,014개, 빌드, 격리 실행 fresh·existing·blocked·upgrade). 새 EXE는 게시된 v4.4(`20261021-222221-cf9d0bd488`) 대비 포함 목록 331개·PYZ 모듈 540개가 같고(추가·삭제 없음) Qt DLL 15개, mingw/Git 바이너리·PIL·setuptools 없음. EXE 안 `show_desktop_guard`에 `_is_desktop_click`이 있고 폐기한 `_desktop_covers_any`는 없으며, `app_info`는 `v4.4a`/`2026. 10. 24.`, 파일 버전 4.4.1.0. 94,192,493 bytes(v4.4 대비 +372), SHA-256 `D4CC9E7D9E383EE37519FA26D5A9C3DB9A6D96F853FAD551A5E581A145A00BAC`, 루트 `dist/기후노트_v4.4a.exe`로 복사 후 해시 일치.
- 루트 `dist/`는 복사 전 비어 있었다(폴더 변경 시각 21:51). 하네스·테스트·`build.spec`은 루트 `dist/`를 쓰거나 지우지 않음을 확인했고 원인은 미확인이다. 게시된 v4.4 EXE는 `output/harness/20261021-222221-cf9d0bd488/dist/`에 남아 있다.
- 회귀 검사: 실제 z-order 대역 창으로 (1) 클릭 시 topmost 없음, (2) Win+D 알림 뒤 바탕화면이 올라와도 pulse로 위 유지, (3) 클릭으로 봤는데 바탕화면이 올라오면 settle에서 재고정을 검사한다. (1)은 원래 코드, (2)는 1차 수정 코드에서 실패하는 것을 먼저 확인했다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| release (PowerShell) | 통과 3,014개·빌드·격리 실행 4개 | `output/harness/20261024-215637-302c493969` | `352b864`(v4.4a·setuptools 84.1.0) 기준. 공휴일 최신 확인 |
| 새 EXE 번들 대조 | 통과 | 같은 실행 폴더 `v4.4a-bundle.json` | 게시된 v4.4 빌드와 포함 목록·모듈 동일, Qt DLL 15개, mingw·PIL·setuptools 없음, EXE 안 수정 코드·버전 확인 |
| 로컬 OSV (lock) | 0건 | — | setuptools 84.1.0 갱신 후. 갱신 전 1건(GHSA-xmj3-9gf7-h52w) |
| doctor | 통과 | `output/harness/20261024-215613-20cc2ef8b4` | setuptools 갱신 후 venv·lock 일치 |
| quick --tests (가드 관련 13개 파일) | 통과 636개 | `output/harness/20261024-214229-c260b66828` | 버전 반영 전 최종 수정 코드 기준 |
| 위와 같은 묶음 | 실패 1/636 | `output/harness/20261024-213913-2c146eed60` | `test_ui_schedule_emoji` 팝업 노출 대기 중 팝업 닫힘. 검사 중 사용자 화면 사용·테스트 앱 실행 중이었다. 아래 단독 재실행과 위 묶음 재실행에서 통과 |
| quick --tests tests/test_ui_schedule_emoji.py | 통과 221개 | `output/harness/20261024-214141-33baeb138f` | 위 실패 재확인 |
| quick --tests (1차 수정) | 통과 605개 | `output/harness/20261024-212604-c48907a9b2` | 폐기한 1차 수정 기준이라 현재 근거 아님 |
| 실화면 기록 | 확인 | `output/harness/20261024-desktop-click-manual/traces/` | 합성 데이터(`appdata/`, 하네스 seed)로 띄운 소스 앱. 1·2=원래 v4.4 EXE, 3=1차 수정 회귀, 4=최종(바탕화면 클릭 18회 topmost 0회, Win+D 2회·버튼 2회만 pulse, 가려짐 0회) |

## 미해결과 인계

- 남은 문제(이번 수정 전부터 있던 것, 범위 밖):
  1. Win+D를 다시 눌러(또는 '바탕화면 보기'를 다시 눌러) 창을 되돌리면 셸이 창 순서를 복원하면서 캘린더를 일반 창 **위**에 둔다. 다른 창을 한 번 누를 때까지 그대로다(기록 2·4에서 매번 재현).
  2. 바탕화면을 누른 직후(이미 바탕화면이 활성) Win+D를 누르면 활성 알림이 다시 오지 않아 pulse가 없고 캘린더가 바탕화면에 가려진다. 두 번째 Win+D까지 유지(기록 3, 43.5초).
- 수동 확인: 업무 PC 등 다른 Windows 빌드의 Win+D·바탕화면 클릭, 터치패드 '탭' 클릭(버튼 눌림 시간이 짧으면 클릭으로 못 보고 예전처럼 pulse할 수 있음)
- 변경한 정본 문서: [AGENTS.md](../../AGENTS.md), [UI 계약](../UI_PATTERNS.md), [아키텍처](../ARCHITECTURE.md)
- 다음 행동: GitLab Release에 `기후노트_v4.4a.exe` 게시(사용자), 위 남은 문제 2건 원인 조사
- 배포·커밋·push 여부: 커밋 `5b2be74`(수정·v4.4a)·`352b864`(setuptools)·이 기록 커밋, `git push origin main`. GitLab Release는 사용자
