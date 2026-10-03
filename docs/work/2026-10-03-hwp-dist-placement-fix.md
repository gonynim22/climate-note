# 작업 기록: HWP 미니앱 EXE 표준 경로 배치

작성일: 2026-10-03 / 상태: 완료

## 목표와 범위

- 사용자 제보: v3.8d에서 네 번째 미니앱이 보이지 않는다.
- 현재 `dist/기후노트_v3.8d.exe`가 HWP 기능 추가 전 파일임을 SHA-256으로 확인했다. 전에 안내한 `dist/verified-20261003-022445-258b2dde7f/`는 현재 없으며 삭제 경위는 확인하지 않았다.
- release 원본은 `output/harness/20261003-022445-258b2dde7f/dist/`에 남아 있다. 포함 코드/아이콘/Qt 및 현재 소스와 대조한 뒤 기존 EXE를 별도 보관하고 표준 dist 경로에 배치한다.
- 소스·버전·DB·salt·설정·의존성은 변경하지 않는다. 실사용 AppData와 실행 중 앱을 검사/종료하지 않는다. 현재 프로세스 경로 목록은 읽기만 했다.
- 시작 사용자 변경: AGENTS.md 4줄, RELEASE_HISTORY.md 16줄과 기존 작업 기록 4개. 보존하고 이번 커밋에서 제외한다.

## 완료 조건

- [x] 표준 EXE의 구형 해시 및 새 EXE의 네 번째 타일 포함 확인
- [x] 이전 EXE 백업·표준 경로 교체·복사 전후 해시 확인
- [x] README/AGENTS/기존 구현 기록의 최신 경로 정정·문서 링크 확인

## 검증 증거

- 실행 ID: `20261003-093718-hwp-dist-placement`.
- 결과: [summary.md](../../output/harness/20261003-093718-hwp-dist-placement/summary.md), [result.json](../../output/harness/20261003-093718-hwp-dist-placement/result.json).
- 기존 release 검사 수를 이번 신규 검사 수로 세지 않는다. 바이트가 같은 검증 완료 산출물의 배치 문제이므로 재빌드/전체 테스트는 중복하지 않는다.

## 미해결과 인계

- 실제 사용자 실행 경로/다른 PC에 복사한 EXE는 확인하지 않았다. 표준 dist 경로의 최신 파일을 제공한다.
- 기존 한글 버전/회사 DRM/서식 수동 대조/배포 보류는 [구현 기록](2026-10-03-hwp-document-converter.md)을 따른다.
- README/AGENTS/기존 구현 기록의 최신 EXE 경로를 표준 dist로 정정한다. 원격 push/게시 없음. 문서만 후속 커밋하며 EXE는 Git 대상이 아니다.

## 최종 배치

- 현재 실행 파일: [기후노트_v3.8d.exe](../../dist/기후노트_v3.8d.exe), 58,698,300 bytes.
- SHA-256: `655DCA366EF32A3751288336F733373DC21069C030B80B73566D6CA4582B53DC`.
- 구형 파일: [백업 EXE](../../output/harness/20261003-093718-hwp-dist-placement/previous/기후노트_v3.8d.exe), 해시 `3FED5C3BD5C3650DC64D4EFB0EDE41F3E068FB04185515A1ACF8C04317336957`.
- 기존 파일에는 문서 변환 모듈이 없었으며 새 파일은 모듈 11개(주머니/진입점 포함)·SVG·Qt DLL 4개가 현재 소스/venv와 일치한다. 전체 runtime 입력은 기존 release와 동일하다.
