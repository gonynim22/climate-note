# 작업 기록: 앱 사용 문제점 점검

작성일: 2026-09-08 / 상태: 점검 완료 — 결함 수정 미착수

## 목표와 범위

- 목표: 현재 소스에서 실제 사용에 영향을 주는 결함을 찾고 합성 데이터로 재현한다.
- 변경 대상: 이 작업 기록과 실행별 진단 산출물. 제품 코드는 수정하지 않는다.
- 데이터 영향: 실제 AppData·DB·salt 및 기존 실행 앱에 접근하지 않는다. 검증은 격리 데이터만 사용한다.
- 제외 범위: 결함 수정, EXE 빌드·배포, 실사용 데이터 검사, 기존 보류 과제의 근거 없는 완료 판정.
- 시작 시 사용자 변경: `.gitignore`, `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `docs/UI_PATTERNS.md`, `tests/conftest.py` 수정; `docs/RELEASE_HISTORY.md`, `docs/templates/`, `tests/test_release_smoke.py`, `tests/test_verify.py`, `tools/` 미추적. 모두 보존한다.

## 완료 조건

- [x] 저장·백업·가져오기·초기화·위젯·잠금 경로의 실제 코드 확인
- [x] 현재 입력의 전체 하네스 검사 결과 기록
- [x] 주요 의심 항목의 합성 데이터 재현과 코드 위치 확보
- [x] 확정 문제와 미검증 범위를 구분한 결과 보고

## 결정과 진행

- 2026-09-08: AGENTS.md와 아키텍처·UI·보안·검증 계약을 기준으로 점검 시작. `karpathy-guidelines` 적용. 현재 변경은 보존하며 수정 대신 재현 증거를 수집한다.
- 전체 하네스 572건 통과. 기존 테스트가 정상 동작을 검사하는 범위와 이번 사용 시나리오의 빈틈을 구분한다.
- 진단 코드는 `output/harness/20260908-usage-review-probes*/`에만 생성했다. 기존 tests/와 제품 코드는 수정하지 않았다.
- 첫 진단 실행은 Win32 대체 함수의 `hwnd` 키워드 누락으로 가져오기 관련 4건이 진단 오류였으므로 해당 실패를 제품 결함 근거로 쓰지 않는다. 별도 r2에서 대체 함수를 수정한 뒤 재실행했다.
- 최종 r3는 초기화 후 실제 Qt 저장/집중 타이머를 기다리고, 실제 `.enc` 복호화→보호백업→가져오기→콜백 경로도 추가했다. 12건 모두 정상 기대값을 위반하는 AssertionError로 실패했다. 이 12건은 아래 7개 문제의 재현 증거이며, 일반 전체 테스트가 12건 실패했다는 뜻은 아니다.
- 기준 HEAD: `aa383a1fe16e736afe1b656a69169bad2412863b` + 시작 시 미커밋 변경. full과 r3의 제품 입력 스냅샷이 동일하고 각 실행 전후 해시도 불변임을 확인했다.

## 확인한 문제

우선순위 P1은 데이터 손실·잠금 노출 때문에 먼저 수정할 항목, P2는 기능 오류, P3은 제한·일관성 문제다. 아래 결과는 합성 데이터와 offscreen Qt에서 확인했으며 실제 사용자의 데이터가 이미 손상되었다는 의미는 아니다.

### R1 / P1 — 가져오기 후 기존 위젯을 중복 생성하여 저장한 메모가 덮어써짐

- 위치: `ui_main.py:3059` `_on_import_complete`, `ui_main.py:2468` `_load_open_sticky_notes`, `ui_main.py:2852` `_load_open_focus_widgets`; 저장 경로 `ui_main.py:3114`.
- 재현: 메모가 열린 상태에서 일정이 들어 있는 유효한 `.enc`를 가져온다. 기존 메모와 같은 DB ID의 플로팅 창이 추가로 생성되고 기존 창도 살아 있다. 겹친 창을 이동해 기존 창에 내용을 쓰고 저장한 뒤 정상 종료 저장을 수행하면 새로 생성된 창의 이전 본문이 DB를 덮는다.
- 관측: 같은 ID의 표시 중 편집창 2개. 기존 창에서 `edited in duplicate after encrypted import`를 저장한 뒤 `prepare_for_quit()`를 호출하자 DB 본문이 `saved before import`로 돌아갔다. 실제 설정창의 `.enc` 가져오기 경로에서도 동일했다.
- 부수 영향: 실행 중 집중 타이머도 새 인스턴스로 바뀌며 등록된 타이머 상태가 `running`에서 `idle`로 바뀐다. 기존 인스턴스는 바탕화면 가드의 참조 때문에 남을 수 있다. 이 문제는 같은 백업을 반복 가져올 때 DB 항목이 추가되는 기존 병합 정책과 별개다.
- 방향: 기존 ID의 인스턴스를 재사용하며 새 항목만 추가하고, 교체가 필요한 경우 현재 원본 저장과 타이머 정리를 완료한 후 교체한다. 집중 진행 상태를 유지해야 한다.
- 진단: `test_import_keeps_one_live_window_per_existing_note`, `test_import_does_not_allow_old_copy_to_lose_a_saved_edit`, `test_import_preserves_running_focus_timer`, `test_encrypted_import_ui_reproduces_stale_editor_overwrite`.

### R2 / P1 — 초기화 후에도 이전 위젯의 저장 타이머가 살아 있음

- 위치: `ui_main.py:3042` `_on_factory_reset`, `database.py:2239` `reset_database`; `ui_sticky.py:650`, `ui_focus.py:400`.
- 원인: 초기화 콜백은 플로팅 창에 `close()`만 호출하고 딕셔너리를 비운다. Qt 위젯은 close만으로 삭제되지 않으며, 가드의 강한 참조와 자식 타이머가 남는다. 새 DB에서는 ID가 다시 시작한다.
- 재현 A: 메모 편집의 2초 저장 타이머가 대기 중일 때 초기화하고 바로 새 메모를 작성·저장한다. 이전 메모와 새 메모의 ID가 같아지면 이전 타이머가 새 메모 본문을 덮는다. 실제 Qt 타이머를 2.3초 기다려 `new note after reset`이 `pre-reset pending text`로 바뀌는 것을 확인했다.
- 재현 B: 집중 세션 실행 중 초기화한 뒤 이전 세션의 완료 시점으로 시험용 시계를 이동한다. 실제 Qt tick을 기다리면 비어 있던 새 DB에 초기화 전 목표를 포함한 집중 기록이 다시 들어온다. 휴식 확인 팝업은 진단에서 생략했으며 기록 저장 자체는 실제 코드다.
- 방향: 초기화 전 최신 원본 저장·보호백업을 확정하고 모든 이전 편집기/타이머를 정지·폐기한다. DB/salt 전환 이후에는 이전 객체의 콜백이 쓰기를 수행할 수 없어야 한다.
- 진단: `test_factory_reset_stops_old_focus_timer`, `test_factory_reset_cancels_pending_sticky_save_before_id_reuse`.

### R3 / P1 — PIN 잠금이 트레이 복원과 이미 열린 검색창에 적용되지 않음

- 위치: `ui_main.py:3097` `toggle_visibility`, `ui_main.py:3414` `_lock`.
- 재현 A: 잠금을 걸어 스티키가 숨겨진 상태에서 트레이의 숨기기/보이기를 수행한다. `_is_locked`는 True인데 스티키가 다시 표시되고 편집 가능 상태다. 복원 함수가 잠금 여부를 검사하지 않는다.
- 재현 B: 일정 검색 결과 창을 열어 둔 채 잠근다. 메인 오버레이와 별개인 검색창은 여전히 표시되고 결과를 읽거나 검색할 수 있다.
- 방향: 잠금 상태에서 모든 재표시 경로를 차단하고 보조 창의 수명·표시·입력도 잠금 정책에 포함한다. 실제 Windows 세션 잠금은 이번 시험에서 작동시키지 않았으며 앱 내부 잠금 함수를 직접 호출했다.
- 진단: `test_lock_stays_effective_after_tray_hide_show`, `test_lock_hides_existing_search_results`.

### R4 / P2 — 편집 직후 내보내기 파일에 최신 스티키 내용이 빠짐

- 위치: `ui_settings.py:917` `_on_export`.
- 재현: 설정창을 열어 둔 상태에서 스티키를 편집하고 2초 자동저장 전에 내보내기를 수행한다. 내보내기는 편집기 저장 없이 DB를 먼저 읽어 파일 선택창을 연다.
- 관측: 생성된 `.enc`를 실제 복호화했을 때 `latest pending export text` 대신 이전 `saved before import`가 있었다. 파일 선택창에서 기다려도 이미 만든 snapshot은 갱신되지 않는다. 원본 DB의 이후 자동저장과는 별개로 내보내기 파일만 이전 내용이다.
- 방향: 현재 모드의 최신 스티키를 강제 저장한 후 Export snapshot을 만들고 저장 실패 시 내보내기를 보류한다.
- 진단: `test_export_contains_latest_pending_sticky_text`.

### R5 / P2 — 크게 모드에서 가져온 스티키가 미니 패널에 나타나지 않음

- 위치: `ui_main.py:2530` `_apply_sticky_side_panel`, `ui_main.py:3059` `_on_import_complete`.
- 재현: 이미 large 모드인 상태에서 스티키를 가져온다. 같은 large 모드 재적용은 기존 카드 목록을 재조회하지 않고, 새 플로팅 창은 숨긴다.
- 관측: 열린 메모 DB 행은 2개인데 미니 패널은 기존 카드 1개만 표시했다. DB 데이터 자체는 존재한다.
- 방향: 가져오기 성공 후 현재 패널의 대기 편집을 보존하면서 카드 목록을 새 DB 상태에 맞춘다.
- 진단: `test_large_import_refreshes_sticky_panel`.

### R6 / P2 — 집중 중 X로 종료하면 회고·세션 기록이 남지 않음

- 위치: `ui_focus.py:729` `_on_close`; 연결되지 않은 종료/회고 처리 `ui_focus.py:668` `_finish_session`.
- 재현: 집중을 시작하고 시험용 시계를 10분 진행한 뒤 실제 닫기 버튼의 click 시그널을 실행한다.
- 관측: 위젯만 삭제되고 `focus_sessions`가 빈 목록으로 남았다. 수동 종료에서 회고를 여는 코드는 존재하지만 닫기 경로가 호출하지 않는다. 자동 완료와 수동 종료의 동작이 다르며 UI 계약의 수동 종료 기록을 충족하지 않는다.
- 방향: 사용자가 세션을 끝내는 경로에서 완료 여부와 경과 시간을 확정하고 회고/저장 성공 후 위젯을 정리한다.
- 진단: `test_manual_focus_close_records_elapsed_session`.

### R7 / P3 — 크게 모드에서는 스티키 최대 10개 제한이 작동하지 않음

- 위치: `ui_main.py:2432` `_on_new_sticky_note`.
- 재현: large 모드에서 새 스티키를 11번 생성한다.
- 관측: 실제 열린 메모 11개가 생성된다. 제한 계산이 등록 개수가 아닌 플로팅 창의 `isVisible()`을 사용하여 large에서는 항상 0으로 계산된다. 이 값으로 색과 위치도 계산하므로 모두 같은 초기 색/좌표가 선택된다.
- 방향: D-Day/집중 위젯과 마찬가지로 등록된 유효 위젯 수를 기준으로 제한한다.
- 진단: `test_large_sticky_creation_respects_ten_note_limit`.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `.venv/Scripts/python.exe tools/verify.py full` | 통과 — 572 passed, 0 failed/error/skipped | `20260908-231941-6322355dea` / [summary.md](../../output/harness/20260908-231941-6322355dea/summary.md) | 현재 작업 트리, 합성 데이터. 117.80초. SciPy import deprecation 경고 1건 |
| 초기 진단 | 실패 — 제품 기대 위반과 진단 스텁 오류 혼재, 최종 증거로 사용하지 않음 | `20260908-usage-review-probes` / [summary.md](../../output/harness/20260908-usage-review-probes/summary.md) | Win32 대체 함수 키워드 오류를 r2에서 수정 |
| 진단 r2 | 실패 — 11개 정상 기대값 위반 재현 | `20260908-usage-review-probes-r2` / [summary.md](../../output/harness/20260908-usage-review-probes-r2/summary.md) | 실제 AppData 미접근, offscreen Qt |
| `.venv/Scripts/python.exe -X utf8 output/harness/20260908-usage-review-probes-r3/run_probes.py` | 실패 — 12개 정상 기대값 위반 재현, 진단 예외 없음 | `20260908-usage-review-probes-r3` / [summary.md](../../output/harness/20260908-usage-review-probes-r3/summary.md), [result.json](../../output/harness/20260908-usage-review-probes-r3/result.json), [재현 코드](../../output/harness/20260908-usage-review-probes-r3/test_usage_probes.py) | 실제 Qt 타이머 대기·합성 `.enc` 포함. full과 동일 제품 입력. 재현 코드 SHA-256 `e905880b241fdebe8ab43d5ce80ea3d060e5cf72630044b85add2c87ab4f64e2` |

## 미해결과 인계

- 남은 문제 / 수동 확인: R1~R7 모두 미수정. 실제 Win+D, 혼합 DPI/KVM, 특정 PC 설정/휴지통 멈춤, Defender·EXE·성능은 이번 추가 진단 범위 밖이다. 기존 WAL/SHM 누적과 라이선스·SBOM·서명 보류도 해결 처리하지 않았다.
- 변경한 정본 문서: 없음.
- 다음 행동: R1/R2 데이터 쓰기·객체 수명과 R3 잠금 범위를 먼저 수정하고 정식 회귀 테스트에 편입한다. 저장 관련 수정은 `data`, 기능 마무리는 해당 지침에 따라 검증한다.
- 배포·커밋·push 여부: 수행하지 않음.
