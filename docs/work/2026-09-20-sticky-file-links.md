# 작업 기록: 스티키 로컬 파일 링크 구현

작성일: 2026-09-20 / 상태: 구현·소스 검증 완료 (본 기록을 기능 커밋에 포함)

후속 사용자 요청에 따른 새 EXE 빌드·격리 검증·dist 배치는 [v3.7b 빌드 기록](2026-09-20-v3.7b-build.md)에 남긴다. 아래의 빌드 미실행 표기는 최초 구현 커밋 당시의 범위다.

## 목표와 범위

- 목표: [합의한 계획](2026-09-20-sticky-file-links-plan.md)의 파일 연결·재연결·주의 표시를 두 스티키 보기에서 제공한다.
- 변경 대상: 링크 공용 로직/편집기, 두 스티키 툴바, UI 수명 취소, Export 저장 게이트, 관련 검사와 정본 문서·AGENTS.md.
- 데이터 영향: 기존 HTML anchor와 암호화 저장 경로만 사용. DB v17·Export v2·salt·키 유도·설정·기존 메모 자동변환 없음.
- 제외 범위: EXE 빌드/게시·push·기존 보안 보류 과제. 후속 사용자 요청에 따라 소스 버전을 v3.7b로 갱신한다.
- 시작 사용자 변경: `.gitignore`, `AGENTS.md`, `README.md`, `app_info.py`, `docs/ARCHITECTURE.md`, `docs/RELEASE_HISTORY.md`, `docs/UI_PATTERNS.md`, `tests/test_ui.py` 및 미추적 9/11 보안·버전 기록, 9/17 문서 기록, 9/20 링크 계획. 보존하고 이번 기능과 무관한 변경은 커밋에서 제외한다.

## 완료 조건

- [x] 기존 본문·서식·체크박스 보존 및 링크 HTML/암호화/백업 왕복.
- [x] 파란 밑줄·화면 전용 경고, 합성 PC 이동 재연결, 두 보기 편집.
- [x] 파일 검사 비동기 처리와 잠금/숨김/폐기/실패 시 취소.
- [x] 현재 소스 full 검사와 문서·AGENTS.md 갱신.
- [x] 기능 커밋에 소스·버전·정본 문서·이 검증 기록 포함.

## 결정과 진행

- 2026-09-20: 구현·AGENTS.md 갱신·커밋을 사용자에게 승인받았다. karpathy-guidelines의 최소 변경 원칙을 적용한다.
- 먼저 QTextDocument의 href·기존 색/밑줄/굵기 왕복을 앱 구현 없이 검증한다.
- Qt anchor는 HTML 재로드 시 밑줄을 자동 추가한다. 최초 proof의 실패를 근거로 원래 밑줄 enum `u`와 개별 연결 ID `id`를 href에 추가했다. `path/origin/id/u` 모두 Qt 왕복을 통과했고 링크 해제 시 기존 색·굵기·이탤릭·밑줄을 보존한다. 일반 Qt 문서의 구형 저장 경로 호환을 검사했으며 구형 EXE 재편집은 별도 미확인이다.
- `sticky_file_links.py`는 표현/로컬 경로 검사, `ui_sticky_links.py`는 공용 편집·표시·파일창·worker 큐를 맡는다. `_TodoTextEdit`의 체크박스 처리와 기존 저장 함수는 유지한다. 링크 없는 문서에 파일 조회/주기 타이머를 추가하지 않는다.
- 최대 4개 daemon worker, 3초 GUI 대기 한도, 10초 상태 캐시를 사용한다. 열기 전 재검사하며 대상/문서 revision/편집기 세대가 달라지면 적용하지 않는다. 네트워크로 연결되는 정션까지 따라가지 않도록 재분석 지점도 제외했다. 클라우드 자리표시자는 로컬 일반 파일로 내려받아 연결해야 한다.
- 두 툴바 연결·한 Undo 드롭·끝 문자 anchor 비상속·주의 여백 표시를 구현했다. 경고는 마지막 표시 줄 오른쪽 18px 여백에 그려 본문과 겹치지 않는다. 100/125/150% 합성 캡처를 직접 확인했다.
- 설정 Export는 기존 `_prepare_data_change()`로 최신 일정/스티키를 먼저 저장한다. compact/large 모두 저장 실패 시 기존 출력 파일과 편집 원본을 유지하며 파일 선택도 시작하지 않는다.
- 후속 요청에 따라 `app_info.py`를 `v3.7b` / `2026. 9. 20.`로 갱신했다. 같은 메타데이터에서 `기후노트_v3.7b.exe` / Windows `3.7.2.0`을 생성한다. 버전·빌드 메타데이터 검사도 최종 full에 포함한다.
- 최종 전체 검사에서 717개가 통과했다. 앱/테스트 소스는 이 실행 뒤 변경하지 않는다. 아래 문서/스테이징 확인은 결과와 링크만 검증한다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 | 유의사항 |
|---|---|---|---|
| doctor | 통과 | [20260920-115653-37a708e5c6](../../output/harness/20260920-115653-37a708e5c6/summary.md) | 앱 import 없음 |
| Qt 저장 proof 초기 검사 | 실패 → 설계 보완 | [20260920-115801-1a23006031](../../output/harness/20260920-115801-1a23006031/summary.md) | Qt 기본 밑줄 자동 추가 발견, `u` 보존으로 해결 |
| 링크·기존 스티키 관련 quick | 통과, 139개 | [20260920-120522-541284e6a4](../../output/harness/20260920-120522-541284e6a4/summary.md) | 중간 입력의 개발 검사 |
| 저장/수명 추가 quick | 실패 1개, 통과 123개 | [20260920-120809-4126c63c2f](../../output/harness/20260920-120809-4126c63c2f/summary.md) | 테스트의 QTest 마우스 인수 수정 |
| full 첫 실행 | 실패 1개, 통과 716개 | [20260920-121129-e536396c5e](../../output/harness/20260920-121129-e536396c5e/summary.md) | 실제 컨텍스트 메뉴 enum 참조 수정 |
| 합성 125%/150% 배율 | 각각 통과, 59개 | [125%](../../output/harness/20260920-121209-a77aaf2538/summary.md), [150%](../../output/harness/20260920-121301-f0a281a893/summary.md) | 좁은 폭·줄바꿈·스크롤·경고 여백. 이후 수정은 메뉴 enum 참조 한 곳이며 표시 코드는 동일 |
| Qt 재연결 파일창 보충 검사 | 통과 | [20260920-121356-sticky-dialog-review](../../output/harness/20260920-121356-sticky-dialog-review/summary.md) | 합성 파일/PC, 실제 Qt picker 취소·선택 signal·표시 문구 보존; 외부 프로그램 실행 0회 |
| 최종 full | **통과, 717개** | [20260920-121422-4a466f014b](../../output/harness/20260920-121422-4a466f014b/summary.md), [result.json](../../output/harness/20260920-121422-4a466f014b/result.json) | 현재 앱/테스트 입력, 0 failures/errors/skips. 기존 SciPy 사용 경고 1개 |
| 문서 링크·스테이징 검토 | 통과 | [20260920-121953-sticky-commit-review](../../output/harness/20260920-121953-sticky-commit-review/summary.md) | 로컬 링크 대상·커밋 포함 여부·앱/테스트 입력 동일·diff 검사. 최종 커밋 전 동일 검사 재실행 |

최종 명령: `.\.venv\Scripts\python.exe tools/verify.py full`.
배율 명령: `QT_SCALE_FACTOR=1.25` 또는 `1.5` 환경에서 `quick --tests tests/test_ui_sticky_file_links.py::test_no_selection_add_and_warning_capture tests/test_ui_sticky_file_links.py::test_minimum_width_gutter_wrap_and_scroll`.

검사 불변식: 기존 합성 8개 테이블 raw·ID·salt 표시 전후 불변, 기존 체크 표식/구형 평문·HTML/서식 유지, 링크 암호화 `.enc`·Import·보호 `.cnbak`·휴지통 왕복, PC B의 같은 경로 실행 차단, 선택 연결만 재지정, 경고/조회가 textChanged·Undo·dirty를 만들지 않음, 숨김/잠금/폐기 뒤 대기 연결·파일 열기 취소. 기존 구형 Export/백업/초기화 ID 재사용 검사는 최종 full의 기존 회귀와 함께 통과했다.

## 미해결과 인계

- 실제 한글 IME·탐색기 드롭·기본 프로그램·Win+D·혼합 DPI/KVM은 자동 합성 검사와 구분한다.
- 실제 구형 EXE의 링크 재편집, PC 두 대의 실제 이동, 접근권한/장치 지연의 실기 재현도 미확인이다. 자동 검사는 합성 PC 표식·로컬 임시 파일·지연 주입·외부 실행 가로채기를 사용했다.
- 기존 보안 회신·설정/휴지통 특정 PC 멈춤·WAL/SHM·라이선스/SBOM/서명 과제 유지.
- 정본 반영: [UI 계약](../UI_PATTERNS.md), [데이터 계약](../ARCHITECTURE.md), [검증](../TESTING.md), [릴리스 이력](../RELEASE_HISTORY.md), [AGENTS.md](../../AGENTS.md), [README](../../README.md).
- 커밋에는 이번 구현/버전/문서와 README의 관련 버전 안내를 포함한다. 기존 `.gitignore`, 별도 AGENTS/릴리스 이력의 보안·과거 기록 변경과 9/11·9/17 미추적 기록은 스테이징하지 않고 보존한다.
- 커밋 제목: `feat: add sticky file links and bump version to v3.7b`. 자기 참조 해시 대신 이 파일의 Git 이력으로 커밋을 확인한다. 새 EXE 빌드·기존 dist 교체·push·배포 미실행.
