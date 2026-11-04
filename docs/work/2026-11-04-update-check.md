# 작업 기록: 새 버전 알림(인터넷 접속을 켠 PC만)

작성일: 2026-11-04 / 상태: 구현 완료, 수동 확인 대기

## 목표와 범위

- 목표: 설정에서 '인터넷 접속'을 켠 PC만 GitLab 공개 Release에서 최신 버전 번호를 받아, 새 버전이면 알림 한 번·빨간 점·앱 업데이트 창 강조로 알린다.
- 변경 대상: `src/update_check.py`(새), `src/ui_update_check.py`(새), `src/ui_update.py`, `src/ui_main.py`, `src/ui_settings.py`, `src/database.py`, `build.spec`, `tools/`, 정본 문서.
- 데이터 영향: 설정 키 `internet_access_enabled` 하나 추가(마이그레이션 없음, Export 제외). DB v19·Export v4·salt·암호문·기존 키 불변.
- 제외 범위: 버전 번호 올리기, 배포 EXE 빌드, Release 게시, push.
- 시작 시 사용자 변경: 추적 안 되는 `docs/work/*`(17개)와 `motion/`. 건드리지 않는다.

## 완료 조건

- [x] 설계 [§11 자동 검증](../superpowers/specs/2026-11-04-update-check-design.md) 전부 통과, 꺼진 PC는 요청 0회
- [x] `release`(전체 pytest·EXE 빌드·smoke 6개) 통과, EXE는 `output/harness/` 안에만
- [x] `--live-update-check`로 실제 EXE의 TLS 확인
- [x] 필요한 수동 확인: 설계 §11 수동 항목을 인계에 남김

## 결정과 진행

- 2026-11-04: [구현 계획](../superpowers/plans/2026-11-04-update-check.md)을 Native로 실행, 브랜치 `feature/update-check`.
- 계획 작성 때 코드에서 확인해 설계에 반영: `build.spec`이 `http`·`email`을 빼고 있어 EXE에 `urllib.request`가 없었다. 메뉴 아이콘 칸이 14px이라 시안의 11px 점은 아이콘에 그릴 수 없다(viewport 자식 위젯으로 얹음). `app_error` 로거는 ERROR 수준이다.
- 계획과 달리 정한 것: 왼쪽 열 '화면 위치' 줄은 2×2 격자라 원래 60px이므로 36px 단언은 오른쪽 열만 한다. 알림에 `closed` 신호를 더했다. 긴 태그(`v4.10a`)는 알림 제목만 13px로 줄인다. 강조 타일 여백은 `(8, 22, 8, 16)`이다(Qt 레이아웃은 테두리를 빼지 않아 계획의 위아래 보정이 1px 어긋남을 만들었다. 그린 화면 대조로 발견).
- EXE 크기: 94,681,579바이트(직전 v4.6 94,410,051바이트보다 약 0.27MB 증가, `http`·`email` 포함분). OpenSSL DLL 출처는 Python `DLLs`로 검증 환경 안이다.
- 전체 검토(Opus 5.5, Fable 5.1은 크레딧 소진으로 실패)에서 Critical 0, Important 2. 두 건 모두 재현 테스트 RED→GREEN으로 고쳤다(`70bd183`).
  - 잠금: `MaskDialogBase`는 메인 창의 자식 위젯이라 `activeModalWidget()`으로 잡히지 않아 안내창이 잠금 덮개 위에 남고 PIN을 넣을 수 없었다. `_lock`이 직접 닫는다.
  - 스위치: 저장과 읽기가 함께 실패하면 되돌리는 코드의 DB 읽기에서 예외가 나 신호가 막힌 채 굳었다. 실패 경로는 DB를 읽지 않고 `QSignalBlocker`를 쓴다. 초기화 뒤에도 읽지 않고 꺼짐으로 둔다.
- 재실행 `release`(`20261104-223632-f4b1cd4450`)는 `test_shortcut_icon_is_smaller_and_delete_shows_on_hover` 1개로 실패했다. `8adb285`에서도 재현되는 기존 문제다. 화면 가운데 뜨는 시험 창의 바로가기 칸 안에 실제 커서(986, 443)가 있으면 합성 Leave 뒤 진짜 Enter가 들어온다. 시험 창을 `WA_DontShowOnScreen`으로 고쳤다(`e2c33a9`).
- 미룬 Minor 7건: 일시적 DB 읽기 실패 뒤 확인 중단, 안내창이 열린 동안 발견한 알림 소진, 초기화 일부 실패 때 스위치 어긋남, 10초 제한이 소켓 작업 기준, 물결이 카드 전체 재그림(창이 열린 동안 한 코어 11~15%), 시험의 단발 타이머 발사, 설계 문서 표기.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `quick`(기준선) | 통과 | `20261104-213354-2912b0b1c2` | 726d76f |
| `release`(전체 pytest 3,564개·빌드·smoke 6개) | 통과 | `20261105-004300-46c005886f` | e2c33a9, 공휴일 최신, BINARY 환경 밖 0개, `dist/` 변경 0개, 시험 EXE SHA `C0735B7A…` |
| smoke `update_check`(닫힌 포트) | 통과 | 위 실행 `smoke/update_check/` | 69초 만에 `새 버전 확인 실패: connection` 기록. EXE에서 확인이 돈다는 근거 |
| `--live-update-check`(인터넷 PC, 실제 EXE) | 통과 | 위 실행 `smoke/update_check_live/` | 75초 동안 실패 기록 없음(`error.log` 0바이트). TLS까지 성공했다는 근거 |
| `release`(이전 시도) | 실패 | `20261104-223632-f4b1cd4450` | 70bd183, 3,564개 중 1개 실패, 빌드 전 중단. 위 결정 참고. 그 전 `20261104-215726-28abaf2c44`(27f99d3)는 통과했지만 이후 코드가 바뀌어 근거로 쓰지 않는다 |
| 화면 대조(①②③④⑤) | 통과 | `output/design/update-guide-20261104/check_compact_*.png` | 기본 크기만 그림. 설정창 레이아웃 최소 높이 551px |

현재 입력에 대한 실제 결과만 기입한다.

## 미해결과 인계

- 남은 문제 / 수동 확인: `tools/dev_update_check_preview.py --latest v4.7`로 ①~④를 중간·크게·공휴일 테마·Windows 애니메이션 끔에서 보기. 업무망 PC(또는 망 차단)에서 스위치 켬 → 아무 표시·오류 창 없음·조작 지연 없음. 스위치 꺼짐에서 요청 없음(방화벽·프록시 기록으로 확인 가능하면). 실제 새 버전 알림은 다음 Release가 나와야 실기로 볼 수 있다.
- 변경한 정본 문서: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/CODING_STANDARDS.md`, `docs/UI_PATTERNS.md`, `docs/TESTING.md`.
- 다음 행동: 사용자 결정(병합·버전 번호·Release). 위 Minor 7건은 사용자가 고를 일이다. 서버 보안 검사(Semgrep)는 로컬에 없어 push 때 처음 돈다. `fetch_data.py`와 같은 구조로 맞췄다.
- 배포·커밋·push 여부: 브랜치 `feature/update-check`에 커밋. push·버전 올리기·EXE 배포는 수행하지 않음.
