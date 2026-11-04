# 작업 기록: 새 버전 알림(인터넷 접속을 켠 PC만)

작성일: 2026-11-04 / 상태: 진행 중

## 목표와 범위

- 목표: 설정에서 '인터넷 접속'을 켠 PC만 GitLab 공개 Release에서 최신 버전 번호를 받아, 새 버전이면 알림 한 번·빨간 점·앱 업데이트 창 강조로 알린다.
- 변경 대상: `src/update_check.py`(새), `src/ui_update_check.py`(새), `src/ui_update.py`, `src/ui_main.py`, `src/ui_settings.py`, `src/database.py`, `build.spec`, `tools/`, 정본 문서.
- 데이터 영향: 설정 키 `internet_access_enabled` 하나 추가(마이그레이션 없음, Export 제외). DB v19·Export v4·salt·암호문·기존 키 불변.
- 제외 범위: 버전 번호 올리기, 배포 EXE 빌드, Release 게시, push.
- 시작 시 사용자 변경: 추적 안 되는 `docs/work/*`(17개)와 `motion/`. 건드리지 않는다.

## 완료 조건

- [ ] 설계 [§11 자동 검증](../superpowers/specs/2026-11-04-update-check-design.md) 전부 통과, 꺼진 PC는 요청 0회
- [ ] `release`(전체 pytest·EXE 빌드·smoke 6개) 통과, EXE는 `output/harness/` 안에만
- [ ] `--live-update-check`로 실제 EXE의 TLS 확인
- [ ] 필요한 수동 확인: 설계 §11 수동 항목을 인계에 남김

## 결정과 진행

- 2026-11-04: [구현 계획](../superpowers/plans/2026-11-04-update-check.md)을 Native로 실행, 브랜치 `feature/update-check`.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `quick`(기준선) | 통과 | `20261104-213354-2912b0b1c2` | 726d76f |

현재 입력에 대한 실제 결과만 기입한다.

## 미해결과 인계

- 남은 문제 / 수동 확인:
- 변경한 정본 문서:
- 다음 행동:
- 배포·커밋·push 여부: 수행하지 않음 / 별도 승인 범위
