# 작업 기록: push 보안 검사(OSV)의 pywin32 해석 실패 대응

작성일: 2026-11-09 / 상태: 구현·검증 끝, push 전

## 목표와 범위

- 목표: GitLab push 보안 검사의 OSV-Scanner가 외부 DB(deps.dev) 때문에 종료 코드 127로 끝나 push가 막힌 것을, 검사 범위를 줄이지 않고 푼다.
- 변경 대상: `requirements.txt`·`requirements-lock.txt`의 pywin32 줄, `tools/verify.py` `doctor()`의 lock 해석, `tests/test_packaging.py`·`tests/test_verify.py`, 정본 문서 `AGENTS.md`·`docs/TESTING.md`.
- 데이터 영향: 없음. 앱 코드·DB·설정·Export·EXE는 바꾸지 않는다.
- 제외 범위: 의존성 버전 변경, EXE 재빌드(Windows에서 설치되는 패키지가 같다), 검사 규칙 제외·우회.
- 시작 시 사용자 변경: `docs/SCREEN_TEXT.md`에 사용자가 일부러 커밋하지 않은 두 줄이 있어 그대로 둔다. 추적하지 않는 옛 `docs/work/*`·`motion/`은 원래 있던 것이다.

## 완료 조건

- [x] pywin32 줄에 `; sys_platform == "win32"`만 붙이고 버전은 그대로 둔다. Windows에서 `pip install -r requirements-lock.txt`가 설치하는 것은 같다.
- [x] `doctor()`와 lock 시험이 표시 뒤를 버전으로 읽지 않는다. 표시가 빠지면 시험이 실패한다.
- [ ] `full` 통과, 로컬 OSV 종료 코드 0, GitLab 보안 검사 통과 뒤 GitHub push.
- [x] 필요한 수동 확인: 없음.

## 결정과 진행

- 2026-11-09 밤: 낫표 작업 커밋의 push가 두 번 OSV FAIL(취약 목록 빈 채)로 거절됐다([기록](2026-11-09-screen-text-nakpyo-double.md)). 다시 보니 deps.dev가 pywin32의 의존성 자료를 306~312 모든 버전에서 404로 줬다(`/v3alpha/systems/pypi/packages/pywin32/versions/<버전>:requirements`). 같은 API에서 PySide6·cryptography·onnxruntime·PyInstaller는 200이었고, pywin32는 312가 새 기본 버전이다. 로컬 osv-scanner 2.5.1도 `pywin32[Concrete:311.0.0]: not found`로 종료 코드 127이었다.
- 사본 시험: `git archive main`을 풀어 서버처럼 저장소 전체를 `scan source -r --all-packages`로 보니 그대로는 127, 두 파일 pywin32 줄에 표시를 붙이면 0이었다. 표시를 붙여도 lock의 `pywin32==311`·`pywin32-ctypes==0.2.3`과 `requirements.txt`의 `pywin32`는 검사 목록에 남아 취약점 대조에 든다(0건). 건너뛰는 것은 deps.dev 의존성 해석뿐이고 pywin32는 하위 의존성이 없다.
- 사용자 결정: 처음에는 기다렸다 같은 커밋을 다시 push하기로 했다가, 위 근거를 듣고 표시를 붙여 push하기로 했다.
- 구현(TDD): `test_doctor_reads_lock_line_with_environment_marker`(표시가 붙은 lock에서 `311`만 읽기)와 `test_pywin32_lines_carry_windows_only_marker`(두 파일의 표시, `packaging`으로 PEP 508 해석·Windows에서 참)를 먼저 넣어 실패를 본 뒤 고쳤다.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`의 환경 드리프트 항목과 [검증](../TESTING.md)의 개발 하네스 절에 있다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 새 시험 2개(고치기 전) | 실패(의도) | 직접 pytest | `doctor`가 버전을 `311; sys_platform == "win32"`로 읽음, 파일에 표시 없음 |
| `tests/test_packaging.py`·`tests/test_verify.py` | 통과 63개 | 직접 pytest | 고친 뒤 |
| `pip install --dry-run --no-index -r requirements-lock.txt` | 통과 | 출력 | `pywin32==311` 이미 충족, 설치할 것 없음 |
| `tools/verify.py doctor` | 통과 | `output/harness/20261109-222937-524cba8950` | |
| 로컬 OSV(`--lockfile "requirements.txt:<파일>"`, 두 파일 각각) | 종료 코드 0 | 출력 | No issues found |
| `full` | 통과 4,338개 | `output/harness/20261109-223207-a951944731` | 위 변경을 모두 넣은 작업 트리(9분 2초) |

## 미해결과 인계

- 남은 문제: 없음. deps.dev가 고쳐진 뒤에도 표시는 맞는 표기라 그대로 두어도 된다(지울지는 그때 정한다).
- 변경한 정본 문서: `AGENTS.md` 환경 드리프트 항목, [검증](../TESTING.md) 개발 하네스 절.
- 다음 행동: `full` 뒤 커밋, GitLab push(보안 검사) 성공 뒤 GitHub push, 결과 기록.
- 배포·커밋·push 여부: 사용자 승인으로 커밋·push(GitLab → GitHub, 커밋 지정).
