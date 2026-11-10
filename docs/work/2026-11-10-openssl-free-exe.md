# 작업 기록: EXE에서 Python용 OpenSSL 빼기

작성일: 2026-11-10 / 상태: 진행 중

## 목표와 범위

- 목표: 배포 EXE에서 Python용 OpenSSL 네 파일(`libcrypto-3.dll`·`libssl-3.dll`·`_ssl.pyd`·`_hashlib.pyd`)과 Qt의 OpenSSL 연결 플러그인(`qopensslbackend.dll`)을 빼고, 새 버전 확인의 통신을 Windows 내장 WinHTTP로 바꾼다. 기관 바이너리 검사의 보완 요청에 대한 조치다(검사 원본은 저장소 밖).
- 변경 대상: `src/update_check.py`, 새 `src/winhttp_get.py`, `build.spec`, `build_app.py`, `tools/verify.py`, `tools/smoke_release.py`, 새 `tools/run_without_openssl.py`·`tools/exe_handoff_check.py`, 관련 테스트, 라이선스 고지, 지침 문서.
- 데이터 영향: 없음이 목표다. `src/database.py`·`src/security.py`는 고치지 않는다. DB v19·Export v4·salt·설정 키 그대로. OpenSSL이 빠지면 `hashlib.sha256`을 Python 내장 구현이 맡으므로, 열쇠 재료와 백업 해시가 같은 값인지 아래 완료 조건으로 확인한다.
- 제외 범위: 빌드 Python 버전 교체, `cryptography` 안의 OpenSSL, 새 버전 알림의 화면·예약·설정 키, 프록시 인증·PAC 지원, 소스로만 도는 개발 도구의 `ssl` 사용.
- 시작 시 사용자 변경: 다른 세션의 `docs/SCREEN_TEXT.md` 미커밋 변경이 있다. 건드리지 않는다.

설계: [EXE에서 Python용 OpenSSL 빼기 설계](../superpowers/specs/2026-11-10-openssl-free-exe-design.md) / 계획: [구현 계획](../superpowers/plans/2026-11-10-openssl-free-exe.md)

## 완료 조건

- [ ] 구현할 동작과 유지할 계약: EXE에 다섯 파일이 없다. 새 버전 확인은 고정 주소 GET 한 번·헤더 2개·10초·256KiB·리디렉션 없음·실패는 화면에 안 보임을 유지한다. 인증서 검증을 느슨하게 하지 않는다.
- [ ] 데이터 동등성: 고정 값 테스트(`tests/test_openssl_free.py`), OpenSSL을 막은 프로세스의 데이터 검사, `release`의 기존·업그레이드 시나리오, v4.8 EXE와 교대 실행.
- [ ] 관련 자동 검사: `data`, `full`, PowerShell `release`(EXE의 OpenSSL 파일·버전 표시 확인 포함).
- [ ] 필요한 수동 확인: 인터넷이 되는 PC에서 `인터넷 접속`을 켠 실제 알림, 기존 데이터로 새 EXE 첫 실행.

## 결정과 진행

- 2026-11-10: 원인 확인. EXE의 OpenSSL 3.0.16은 빌드 Python 3.13.5의 `DLLs`에서 오고 `_ssl.pyd`·`_hashlib.pyd`가 끌고 들어온다(`build/build/Analysis-00.toc`). 앱의 `ssl` 사용은 `update_check.py` 한 곳, `hashlib`은 `sha256`뿐이다.
- 2026-11-10: 사용자 결정. 버전을 올리는 길 대신 부품을 빼는 길로 간다. 사용자 DB는 절대 바뀌면 안 되고, 새 버전 알림은 베타로 보고 고쳐도 된다.
- 2026-11-10: 설계 검토에서 `qopensslbackend.dll`에 `OpenSSL 3.5.4` 표시가 UTF-16으로 들어 있음을 확인해 함께 빼기로 했다.
- 2026-11-10: 작업 1. 열쇠 재료·백업 해시 고정 값 테스트와 OpenSSL을 막는 실행기를 만들었다. 기대값은 OpenSSL 3.0.16이 있는 환경에서 뽑았고, 보통 실행과 막은 실행 모두 `4 passed, 1 skipped`.

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `pytest tests/test_openssl_free.py` (보통·막은 실행) | 통과 | 직접 실행 | 작업 1 시점 |
| `verify.py data` | 미실행 | | |
| `verify.py full` | 미실행 | | |
| `verify.py release` | 미실행 | | |
| v4.8 EXE 교대 실행 | 미실행 | | |
| 실제 TLS(`--live-update-check`) | 미실행 | | |

현재 입력에 대한 실제 결과만 기입한다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 완료 조건의 수동 확인 둘.
- 변경한 정본 문서: 아직 없음(작업 8).
- 다음 행동: 계획의 작업 2부터.
- 배포·커밋·push 여부: 작업별 로컬 커밋, push는 하지 않음.
