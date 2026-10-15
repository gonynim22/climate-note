# 작업 기록: 백업 검증 임시 파일(-wal/-shm) 누적 수정

작성일: 2026-10-15 / 상태: 구현·검증·로컬 배치 완료 — 커밋·push·Release 게시는 별도 승인 대기

## 목표와 범위

- 목표: 백업 검증용 임시 DB의 `-wal`/`-shm`이 데이터 폴더에 무제한으로 쌓이는 문제를 막고, 이미 배포된 PC에 쌓인 파일을 업데이트 첫 실행 때 자동으로 정리한다.
- 변경 대상: `database.py`(임시 DB 정리·시작 시 잔여 파일 정리), `main.py`(시작 순서에 정리 호출), `tests/test_data_safety.py`, `app_info.py`(v4.0a), 관련 정본 문서.
- 데이터 영향: DB v17·Export v2·salt·백업 묶음 형식·설정 키 변경 없음. 지우는 파일은 이름이 `.backup-validate-*.db-wal|-shm`(데이터 폴더)·`.auto-snapshot-*.db-wal|-shm`(`backups\`)인 임시 짝 파일뿐이다.
- 제외 범위: 비정상 종료로 남은 임시 `.db` 본체 정리, 다른 결함(R6 등), 기능 추가.
- 시작 시 사용자 변경: `AGENTS.md`·`docs/RELEASE_HISTORY.md` 수정(9월 기록), `docs/work/` 미추적 8개, `test.png`. 모두 보존하고 이번 커밋에 섞지 않는다.

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 백업·보호백업·검증 뒤 임시 짝 파일 0개. 시작 시 잔여 짝 파일 정리. `calendar.db`·`calendar.db-wal/-shm`·`.cnbak`·`.salt`·0바이트가 아닌 `-wal`·짝 `.db`가 남은 묶음은 보존. 정리 실패는 경고 로그만 남기고 시작 계속.
- [x] 관련 자동 검사: `tools/verify.py data`, PowerShell `tools/verify.py release`
- [ ] 필요한 수동 확인: 실제 배포 PC의 첫 실행 정리(사용자 확인)

## 결정과 진행

- 2026-10-15: 합성 데이터에서 재현. `backup_database()` 1회 후 3쌍 잔존, 하루 2회 시작 가정 10일에 `.cnbak` 5개 유지·짝 파일 230개(3.7MB). 앱 시작 1회당 약 14개·224KB(백업 5개가 찬 뒤).
- 원인: WAL 원본에서 `Connection.backup()`으로 만든 사본이 WAL 머리값 `(2, 2)`를 물려받는다. 이 사본을 `mode=ro`로 열면 SQLite가 `-shm`(32KB)·`-wal`(0B)을 만들고, 읽기 전용 연결은 닫을 때 지우지 못한다. 정리 코드는 `.db`만 지운다(`validate_backup_bundle`, `_create_auto_backup_bundle`). 일반 연결로 열면 남지 않음을 따로 확인했다.
- 연결을 닫은 직후 Windows에서 두 짝 파일을 바로 지울 수 있음을 3회 반복 확인했다.
- 결정(사용자 승인): 임시 DB를 지울 때 짝 파일도 함께 지우고, 시작 시 이름 패턴이 정확히 맞는 잔여 짝 파일만 정리한다. `-wal`은 0바이트일 때만 지운다. 버전 v4.0a.
- 구현: `database._remove_temp_db()`가 임시 DB와 짝 파일을 함께 지운다(`validate_backup_bundle`, `_create_auto_backup_bundle`). `database.cleanup_stale_backup_sidecars()`를 `main._initialize_database()`의 시작 백업 뒤에 호출한다. 새 설정 키 없이 매 시작 실행한다(검색 2회).
- TDD: `tests/test_data_safety.py`에 4개 추가. 구현 전 실패 확인(백업 경로 후 짝 파일 24개 잔존, 정리 함수 없음, 시작 경로 미연결) 후 통과.
- 업그레이드 실기: 합성 데이터에서 구 `dist/기후노트_v4.0.exe`(SHA-256 `71179E64…`)를 2회 실행하자 임시 짝 파일 10→16개, 새 v4.0a EXE 1회 실행 후 0개, 다시 실행해도 0개. 정상 `calendar.db-wal/-shm`은 각 실행 직후 존재하지 않아 이 실기에서 보존 동작은 관찰하지 못했다(보존은 단위 테스트로 확인). 결과 `output/harness/20261015-230755-sidecar-upgrade/upgrade.json`.
- 별도 관찰(이번 수정과 무관, 미수정): 같은 실기에서 열린 스티키 크기가 300×400→306×396으로 저장됐다(내용·위치·ID 불변). 대조 실행에서 구 v4.0 EXE 단독 1회 실행도 같은 변화를 보여 기존 동작이다(`output/harness/*-sticky-control-old`·`-new`). 기존 smoke는 창 준비 직후 종료해 이 변화를 관찰하지 않는다. 데이터 손실은 아니며 별도 과제로 남긴다.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다. 단순 문구 수정에는 별도 작업 기록을 요구하지 않는다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_data_safety.py` (구현 전) | 실패 4건(예상) | 로컬 실행 | 새 테스트가 결함을 재현함을 확인 |
| `tools/verify.py data` | 통과 458개 | `output/harness/20261015-225855-ce489c3a94/summary.md` | v4.0a 소스·문서 갱신 후 |
| PowerShell `tools/verify.py release` | 통과 2,456개·build·smoke 3개 | `output/harness/20261015-230046-b64efa2b55/summary.md` | 입력 전후 동일, mingw 혼입 없음, `4.0.1.0`, `NotSigned`, 94,041,766 bytes, SHA-256 `2750798C847F0610F7D885366A398B9498E5252D91689344DBEBA05C15BE8A36` |
| 구 v4.0 → 새 v4.0a EXE 업그레이드 실기 | 정리 통과(짝 파일 16→0→0), 스크립트 판정은 스티키 크기 변화로 failed | `output/harness/20261015-230755-sidecar-upgrade/upgrade.json` | 스티키 크기 변화는 구 EXE 단독 대조에서도 동일(기존 동작) |

검증 뒤에는 README_detail·AGENTS.md·이 기록의 결과 문구만 갱신했다. 코드·테스트·빌드 입력은 release 입력과 같다.

현재 입력에 대한 실제 결과만 기입한다. 이전 버전의 테스트 수를 현재 통과로 복사하지 않는다.
`output/harness/<run-id>/summary.md` 및 `result.json`을 연결한다.
로그는 gitignore 대상이므로 다른 개발자가 재현하려면 명령·커밋·검사 입력 해시도 확인한다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 배포 PC에서 새 EXE 첫 실행 후 짝 파일 정리 확인. 스티키 크기 300×400→306×396 저장(기존 동작) 원인 조사. 기존 수동 검사·라이선스/SBOM/서명 보류 유지.
- 변경한 정본 문서: [아키텍처](../ARCHITECTURE.md) 자동백업 묶음 항목, [릴리스 이력](../RELEASE_HISTORY.md) v4.0a 항목과 기존 보류 항목의 수정 표시, `AGENTS.md` 기록 관리·후속 과제 줄, `README_detail.md`.
- 다음 행동: 사용자 승인 시 커밋(시작 시 있던 9월 미커밋 변경 제외)·`main` 병합·`git push origin main`·GitLab Release 게시.
- 배포·커밋·push 여부: `dist/기후노트_v4.0a.exe` 로컬 배치만 수행(기존 `dist/기후노트_v4.0.exe` 유지). 커밋·push·Release 게시는 수행하지 않음.
