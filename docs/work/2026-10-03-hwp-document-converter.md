# 작업 기록: HWP → HWPX 미니앱

작성일: 2026-10-03 / 상태: 구현·자동 검증·빌드 완료 (수동 호환성 확인 별도)

## 목표와 범위

- 네 번째 미니앱에 HWP → HWPX 일괄 변환을 구현한다. 한글 설치가 필수이며 XLS 등 다른 형식은 제외한다.
- 원본·기존 결과·DB v17·Export v2·salt·설정·바로가기 6슬롯을 보존한다. 목록/결과는 메모리 전용이다.
- [계획](2026-10-02-document-format-converter-plan.md)을 HWP 전용으로 확정했다. v3.8d를 유지하고 기존 EXE는 보존한다.
- 시작 변경: AGENTS.md 4줄, RELEASE_HISTORY.md 16줄 및 기존 미추적 기록 4개. 이번 커밋에 섞지 않는다.

## 결정과 진행

- 로컬 한글 2022의 32비트 COM 등록과 실제 hwp.exe, 공식 HwpxConverter.exe를 확인했다. 기존 실행 중인 한글 프로세스는 없었다.
- `output/harness/20261003-hwp-engine-probe`에서 설치 제품의 번들 예제를 시험 폴더로 복사하고, 공식 CLI를 Job에 격리해 입력/출력 인수로 실행했다. 약 2초 이내 종료 코드 0, 유효한 ZIP/XML HWPX 생성, 남은 창 없음. 실제 사용자 파일은 사용하지 않았다.
- 선택 엔진: **설치된 공식 HWPX 변환기 CLI**. 한글과 변환기를 각각 확인하며 변환기가 없으면 설치 필요를 안내한다. 엔진을 번들/자동 설치하지 않는다. COM으로 사용자의 한글 창을 제어하지 않는다.
- 원본을 작업 전용 폴더로 복사한 뒤 변환한다. HWP5 헤더와 보호 여부를 검사하며 구형/암호/배포용 문서는 지원하지 않는다. 결과 ZIP/XML을 확인한 뒤 부모 프로세스가 덮어쓰기 없이 확정한다.
- 작업 프로세스는 GO 요청 전 Windows Job에 넣고, 취소/숨김/폐기 시 그 Job만 종료한다. 작업 진입점은 DB/보안/트레이 import 전에 분기한다.
- 공통 창 틀 추출은 검토 후 보류: 이번 창은 단일 모드 파일 큐여서 기존 계산형 두 앱의 폼 구조와 다르다. 기존 세 앱을 변경하지 않고 같은 시각 규칙을 적용한다.
- 구현: 설치 확인/헤더·ZIP/XML 검사, 원본 사본 변환, Job 가입 후 요청, onefile 작업 분기, 파일 선택/드롭/중복 제거/최대 100개 큐/취소/실패 재시도/출력 폴더 열기를 연결했다. 기존 주머니의 네 번째 칸을 보라 SVG로 교체했다.
- 실패 수정: 첫 quick에서 QProcess 종료 신호의 객체 캡처/부모 정리 충돌로 Qt abort를 재현했다. 명시적 QObject 수신 슬롯과 완료 후 신호 연결 해제/부모 분리/지연 삭제로 수정했고 실제 자식·손자 프로세스 취소와 시작 직후 취소를 회귀 검사했다. 직접 검사에서 빈 DB의 salt를 존재한다고 가정한 테스트 7건도 합성 salt 초기화로 수정했다.
- 실제 제품 경로: `20261003-hwp-product-probe`는 UI → 작업 모드 → 실제 설치 CLI → 결과 검증/확정으로 번들 예제 사본 2개를 변환하고 합성 손상 파일 1개를 거부했다. 원본 SHA-256/기존 동명 결과 보존, 작업 임시 폴더 정리, 작업 모드의 앱 DB 미생성을 확인했다. `completed.png`를 직접 검토했다.
- 소형 화면 420×500/480×500와 기본 화면 캡처를 검토했다. 파일명 열의 가용 너비와 출력 폴더 안내를 정리했으며 관련 quick 167개가 통과했다. 작업 준비/COM 예외 처리, 보호 플래그, frozen DLL 검색 경로 정리까지 반영한 최종 quick 172개가 통과했다. 125%/150% 합성 배율은 각각 140개가 통과했다.

## 완료 조건

- [x] 파일 선택/드롭·중복 제거·일괄 변환·취소·재시도·결과 폴더 열기
- [x] 원본/동명 결과 보존·실패/시간 초과·보호 입력·출력 구조 검사
- [x] 미니앱 4개·잠금/숨김/초기화/종료·데이터 보존·합성 배율 검증
- [x] 실제 엔진/EXE 작업 모드 검증과 AGENTS/정본 문서 갱신·로컬 커밋·빌드

## 검증 증거

| 범위 | 상태 | 실행 ID / 결과 |
|---|---|---|
| 공식 CLI 1차 시험 | 통과 | `20261003-hwp-engine-probe` (초기 조사, 최종 제품 검증 아님) |
| 최초 quick (Qt 종료 충돌) | 실패 | `20261003-015632-4ab17c0169` / [summary.md](../../output/harness/20261003-015632-4ab17c0169/summary.md) |
| 종료 수명 수정 후 quick | 통과 | `20261003-020019-c8085d6aec`, 158개 / [summary.md](../../output/harness/20261003-020019-c8085d6aec/summary.md) — 최종 UI/추가 수명 검사 전 |
| UI/초기화/실제 작업 수명 quick | 통과 | `20261003-020739-ba075568c9`, 167개 / [summary.md](../../output/harness/20261003-020739-ba075568c9/summary.md) |
| 실제 제품 UI/CLI | 통과 | `20261003-hwp-product-probe` / [summary.md](../../output/harness/20261003-hwp-product-probe/summary.md), [result.json](../../output/harness/20261003-hwp-product-probe/result.json) |
| 최종 quick | 통과 | `20261003-021340-038f73a006`, 172개 / [summary.md](../../output/harness/20261003-021340-038f73a006/summary.md) |
| 125% / 150% 합성 배율 | 통과 | 각각 140개 / [125% summary.md](../../output/harness/20261003-020959-0bc3453299/summary.md), [150% summary.md](../../output/harness/20261003-021021-618deb6a75/summary.md) |
| 첫 release | 실패 | `20261003-022033-b579664066`, 1,575개 통과/기존 설정창 신호 기대 1개 실패. 네 번째 앱 초기화 연결 기대값을 갱신하고 재검사한다. [summary.md](../../output/harness/20261003-022033-b579664066/summary.md) |
| 최종 release | 통과 | `20261003-022445-258b2dde7f`, **1,576개 테스트·새 빌드·격리 EXE 3개 시나리오** / [summary.md](../../output/harness/20261003-022445-258b2dde7f/summary.md) |
| 새 EXE 작업 모드/실제 CLI | 통과 | 예제 사본 2개 성공·손상 1개 거부·frozen 작업 취소 / [summary.md](../../output/harness/20261003-022445-258b2dde7f/frozen-hwp-probe-final/summary.md), [result.json](../../output/harness/20261003-022445-258b2dde7f/frozen-hwp-probe-final/result.json) |
| 포함 코드·Qt·SVG·배치 | 통과 | [bundle-verification.json](../../output/harness/20261003-022445-258b2dde7f/bundle-verification.json), [artifact-placement.json](../../output/harness/20261003-022445-258b2dde7f/artifact-placement.json) |

## 미해결과 인계

- 실제 회사 DRM·한글 버전별 호환성·수동 서식 대조는 별도 확인한다. 공식 변환기 연동/배포 조건은 기존 보류 항목으로 남긴다.
- 구현/계획/AGENTS 커밋: `f44af2a`. 기존 초기화 연결 테스트/문서 링크 후속: `3fb1623`. 이 커밋 기준 release가 통과했다. 이후 변경은 결과 기록 문서뿐이며 코드·테스트·빌드·리소스·lock은 그대로다. 원격 push/게시 없음.
- frozen 추가 시험의 첫 실행은 정상 변환 2개와 손상 거부를 통과했으나, 시험용 UI 감시 타이머가 다음 취소 루프를 조기 종료했다. `frozen-hwp-probe/result.json`에 실패를 남겼고, 제품 수정 없이 감시 타이머/자동 종료를 정리한 `frozen-hwp-probe-final`에서 모두 통과했다.
- 새 EXE의 본창을 직접 클릭한 전체 변환 흐름은 수동 미확인이다. 실제 소스 UI와 새 EXE 작업 모드·공식 CLI의 결합, 일반 EXE 시작/기존 데이터 보존/보호 종료 3개 시나리오는 자동 확인했다.

## 산출물과 최종 확인

- 빌드 입력 커밋: `3fb1623` (미커밋 사용자 문서 2개/기존 작업 기록 4개는 보존·커밋 제외). PowerShell release.
- 현재 EXE: [기후노트_v3.8d.exe](../../dist/기후노트_v3.8d.exe), **58,698,300 bytes**, Windows `3.8.4.0`.
- SHA-256: `655DCA366EF32A3751288336F733373DC21069C030B80B73566D6CA4582B53DC`.
- 새/연결 모듈 11개(작업 진입 main 포함), SVG, Qt 6.11.2 DLL 4개가 실제 번들과 현재 소스/venv에 일치한다. mingw/Git 바이너리 혼입 0건. 기존 v3.8d보다 625,861 bytes 증가했다.
- 최초 배치 당시 기존 `dist/기후노트_v3.8d.exe`와 이전 버전 EXE는 덮어쓰지 않았다. 기존 v3.8d 해시 `3FED5C3BD5C3650DC64D4EFB0EDE41F3E068FB04185515A1ACF8C04317336957` 보존을 배치 전후 확인했다.
- 최종 문서 링크/검증 입력 보존 확인: [summary.md](../../output/harness/20261003-022445-258b2dde7f/post-validation-summary.md), [result.json](../../output/harness/20261003-022445-258b2dde7f/post-validation.json).

## 표준 dist 경로 후속 정정 (2026-10-03)

- 네 번째 앱이 보이지 않는다는 제보 후 표준 dist가 기능 추가 전 파일임을 확인했다. 앞서 안내한 verified 폴더는 현재 없으며 삭제 경위는 확인하지 않았다.
- release 원본은 동일 해시로 남아 있어 현재 코드/리소스/Qt 대조 후 표준 dist에 배치했다. 구형 EXE는 별도 백업했다. 코드/빌드를 변경하지 않았으므로 이전 1,576개를 새 테스트 실행 수로 기록하지 않는다.
- 최신 배치·백업·검증·문서 경로는 [후속 기록](2026-10-03-hwp-dist-placement-fix.md)을 따른다.
