# 작업 기록: 미니앱 버튼과 빈 주머니

작성일: 2026-09-20 / 상태: 구현·커밋·빌드·격리 검증 완료

## 목표와 범위

- 승인된 [계획](2026-09-20-mini-app-pocket-plan.md)의 사이드바 미니앱 버튼과 빈 주머니를 구현한다. 단위 환산기는 후속 명세로 분리한다.
- UI/테스트/정본 문서와 AGENTS.md만 변경한다. DB v17·Export v2·salt·암호화·바로가기 6개 ID/이름/경로·기존 설정·의존성·v3.7b를 유지한다.
- 기존 사용자 변경(.gitignore, AGENTS.md, RELEASE_HISTORY와 미추적 기록 3개)은 output/implementation/mini-app-pocket에 초기 사본/diff를 남기고 커밋에서 제외한다.
- 사용자가 구현 → AGENTS 갱신 → 커밋 → 빌드를 요청했다. push/게시 제외.
- 추가 요청으로 `.gitignore`에 `/desgn_claude/`를 추가하고 AGENTS.md에 프로젝트 탐색/검색/분석 제외를 명시한다. 폴더 내부는 읽지 않았고, Git 추적 항목 없음과 ignore 규칙 적용만 확인한다.

## 완료 조건

- [x] 최상단 미니앱 버튼·기존 바로가기 6개·짧은 화면 스크롤과 세 크기/배율 렌더.
- [x] 주머니 열기/닫기/재클릭/키보드/화면 경계/잠금·트레이·보기 전환 수명.
- [x] 진행 중 일정 저장 실패 보류·초안 보존·기존 DB/설정/salt 불변.
- [x] 관련 검사·정본 문서/AGENTS 갱신·기능 커밋.
- [x] release 전체 검사/새 EXE 3개 격리 시나리오·코드/Qt 대조·기존 EXE 보호 후 dist 배치.

## 결정과 진행

- 제품 코드를 읽고 기존 ShortcutSlot ID 연결과 팝업/편집 저장 계약을 확인했다. 구현은 별도 DB 없이 UI로만 추가했다.
- 미니앱 64×48px/주머니 300×220px, 바로가기 64×64px·6슬롯·ID 유지. 기본 높이에서 전체 표시, 500px에서는 목록 스크롤로 마지막 슬롯 접근을 확인했다.
- 100/125/150% 합성 Qt 렌더에서 버튼/한글/팝업/6개 슬롯 배치를 확인했다. 반복 열기/닫기 전후 전체 DB dump·Export·기존 바로가기·salt가 동일하고 저장 실패 시 편집을 보존했다.

## 검증 증거

| 범위 | 상태 | 실행 ID / 결과 | 유의사항 |
|---|---|---|---|
| 관련 quick | 통과: 314개 | [20260920-230148-f9aa42d17c](../../output/harness/20260920-230148-f9aa42d17c/summary.md) | 새 주머니·기존 바로가기/일정/잠금/이동/화면 회귀 포함 |
| 125% 합성 배율 | 통과: 79개 | [20260920-230427-827d3fd1d0](../../output/harness/20260920-230427-827d3fd1d0/summary.md) | QT_SCALE_FACTOR=1.25, 주머니 전체 검사 |
| 150% 합성 배율 | 통과: 79개 | [20260920-230515-2cdbfcae87](../../output/harness/20260920-230515-2cdbfcae87/summary.md) | QT_SCALE_FACTOR=1.5, 동일 대상 |
| 포커스 준비 보강 후 quick | 통과: 140개 | [20260920-231015-bbabe65bb5](../../output/harness/20260920-231015-bbabe65bb5/summary.md) | 이모지 전체·미니앱 전체와 기본 회귀 |
| 실제 native 표시/활성화 대기 후 quick | 통과: 141개 | [20260920-231508-c78ec670be](../../output/harness/20260920-231508-c78ec670be/summary.md) | 이모지/미니앱 전체, QWindow 바깥 클릭 추가 |
| release | 통과: 798개·새 EXE·3개 격리 시나리오 | [20260920-231715-72ee145267](../../output/harness/20260920-231715-72ee145267/summary.md) | 소스 커밋 `bb95ccc`, 검사 전후 입력 불변 |
| 최초 release | 실패: 796 통과 / 1 실패 | [20260920-230650-4f34cbbfc1](../../output/harness/20260920-230650-4f34cbbfc1/summary.md) | 기존 이모지 선택 검사의 포커스 복원 대기 timeout. 빌드/EXE 단계 미실행 |
| 두 번째 release | 실패: 796 통과 / 1 실패 | [20260920-231108-eab917d899](../../output/harness/20260920-231108-eab917d899/summary.md) | 다른 이모지(📊)에서 같은 포커스 timeout. 메인 활성 확인만으로 부족, 빌드/EXE 단계 미실행 |
| 실제 혼합 DPI/KVM/Win+D/IME·정상 종료·Defender | 미실행 | | 자동 검사와 구분 |

## 빌드·배치와 기록

- 기능·AGENTS/UI/아키텍처는 `21b1055`, 입력 검사 준비 보강은 `bb95ccc`로 커밋한 뒤 release를 실행했다. 검증 후 README/릴리스 이력/이 기록만 갱신하며 런타임·빌드 입력은 유지한다.
- 새 [기후노트_v3.7b.exe](../../dist/기후노트_v3.7b.exe): **57,951,181 bytes**, Windows **3.7.2.0**, SHA-256 **`460D0C42BF0CE4A329CB971C744AEAAEF2C2BE04A82594BF0589888099BFEDA4`**. 원본 검사 산출물과 dist 파일의 해시가 일치한다.
- 기존 EXE를 [dist/previous-v3.7b-20260920-231715-72ee145267/기후노트_v3.7b.exe](../../dist/previous-v3.7b-20260920-231715-72ee145267/기후노트_v3.7b.exe)에 먼저 보호 보관했다. 보관본 SHA-256은 **`E69D477E24B579BC68D7757183394AE5A5AB6197A786E78412A9893EF811F49D`**로 이전 이동 토글 빌드와 일치한다. 기존 실행 앱은 종료/검사 대상으로 삼지 않았다.
- [산출물 대조](../../output/harness/20260920-231715-72ee145267/artifact-check/result.json): 내부 `ui_main`/`ui_mini_apps`/`database`/`app_info`의 컴파일 코드가 현재 소스와 일치한다(파일명 메타데이터 정규화). `apps.svg` 바이트 일치, Qt6Core/Qt6Gui/Qt6Widgets **6.11.2.0**과 검증 venv의 바이트/SHA-256 일치를 확인했다.
- [기본 렌더](../../output/harness/20260920-231715-72ee145267/mini-apps-compact.png), [중간 렌더](../../output/harness/20260920-231715-72ee145267/mini-apps-medium.png), [크게 렌더](../../output/harness/20260920-231715-72ee145267/mini-apps-large.png)는 합성 데이터의 소스 Qt 위젯 렌더다. 실제 EXE는 신규 설치·기존 데이터 보존·손상 salt 시작 차단 3개 자동 시나리오를 통과했다.
- 기존 합성 데이터 8개 테이블의 raw/복호화 내용·ID·salt 보존을 확인했다. 실사용 AppData/DB/salt는 접근하지 않았다. 실제 혼합 DPI/KVM/Win+D/IME·정상 종료 수동 확인·Defender·서명 검사는 미실행이며 자동 통과와 구분한다.

## 미해결과 인계

- 최초 전체 검사에서 기존 `test_all_palette_choices_can_be_saved[🔥]`가 포커스 대기 timeout으로 실패했다. 테스트 helper가 Windows의 비동기 창 활성화 완료를 확인하지 않고 클릭하던 입력 준비를 `waitExposed`/`isActiveWindow` 대기로 보강했다. 앱 런타임 코드는 변경하지 않고 관련 검사와 release를 새 실행 ID로 다시 검증했다.
- 재발 후 pytest-qt 구현을 확인해 `qtbot.waitExposed()`가 컨텍스트 관리자라 단독 호출로는 기다리지 않음을 확인했다. 메인과 선택 팝업 모두 Qt의 `qWaitForWindowExposed`/`qWaitForWindowActive` 반환값을 검사하도록 고쳤다. 주머니 검사에도 같은 실제 표시/활성화 대기와 QWindow 경로의 바깥 클릭 검사를 적용했다.
- 단위 환산기 내용/실행 기능은 이번 범위에서 제외한다.
- 기존 보안 회신·라이선스/SBOM/서명 보류와 GitLab push/게시 미수행 상태를 유지한다.
