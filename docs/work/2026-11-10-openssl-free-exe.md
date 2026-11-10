# 작업 기록: EXE에서 Python용 OpenSSL 빼기

작성일: 2026-11-10 / 상태: 구현 완료. 최종 검토 수정(`11a85ea`) 뒤의 release·교대 실행·실제 TLS 재확인이 남았다(아래 '최종 검토 뒤'). 수동 확인과 push 대기

## 목표와 범위

- 목표: 배포 EXE에서 Python용 OpenSSL 네 파일(`libcrypto-3.dll`·`libssl-3.dll`·`_ssl.pyd`·`_hashlib.pyd`)과 Qt의 OpenSSL 연결 플러그인(`qopensslbackend.dll`)을 빼고, 새 버전 확인의 통신을 Windows 내장 WinHTTP로 바꾼다. 기관 바이너리 검사의 보완 요청에 대한 조치다(검사 원본은 저장소 밖).
- 변경 대상: `src/update_check.py`, 새 `src/winhttp_get.py`, `build.spec`, `build_app.py`, `tools/verify.py`, `tools/smoke_release.py`, 새 `tools/run_without_openssl.py`·`tools/exe_handoff_check.py`, 관련 테스트, 라이선스 고지, 지침 문서.
- 데이터 영향: 없음. `src/database.py`·`src/security.py`는 고치지 않았다. DB v19·Export v4·salt·설정 키 그대로. OpenSSL이 빠지면 `hashlib.sha256`을 Python 내장 구현이 맡으므로, 열쇠 재료와 백업 해시가 같은 값인지 아래 증거로 확인했다.
- 제외 범위: 빌드 Python 버전 교체, `cryptography` 안의 OpenSSL(4.0.1), 새 버전 알림의 화면·예약·설정 키, 프록시 인증·PAC 지원, 소스로만 도는 개발 도구의 `ssl` 사용.
- 시작 시 사용자 변경: 다른 세션의 `docs/SCREEN_TEXT.md` 미커밋 변경이 있었다. 건드리지 않았다.

설계: [EXE에서 Python용 OpenSSL 빼기 설계](../superpowers/specs/2026-11-10-openssl-free-exe-design.md) / 계획: [구현 계획](../superpowers/plans/2026-11-10-openssl-free-exe.md)

## 완료 조건

- [x] 구현할 동작과 유지할 계약: EXE에 다섯 파일이 없다. 새 버전 확인은 고정 주소 GET 한 번·헤더 2개·10초·256KiB·리디렉션 없음·실패는 화면에 안 보임을 유지한다. 인증서 검증을 느슨하게 하지 않는다.
- [x] 데이터 동등성: 고정 값 테스트, OpenSSL을 막은 프로세스의 데이터 검사, `release`의 기존·업그레이드 시나리오, v4.8 EXE와 교대 실행.
- [x] 관련 자동 검사: `data`, PowerShell `release`(전체 pytest 포함, EXE의 OpenSSL 파일·버전 표시 확인 포함).
- [ ] 필요한 수동 확인: 인터넷이 되는 PC에서 `인터넷 접속`을 켠 실제 알림(새 버전이 있을 때), 기존 데이터로 새 EXE 첫 실행. 프록시를 쓰는 망에서의 동작.

## 결정과 진행

- 2026-11-10: 원인 확인. EXE의 OpenSSL 3.0.16은 빌드 Python 3.13.5의 `DLLs`에서 오고 `_ssl.pyd`·`_hashlib.pyd`가 끌고 들어온다(`build/build/Analysis-00.toc`). 앱의 `ssl` 사용은 `update_check.py` 한 곳, `hashlib`은 `sha256`뿐이다.
- 2026-11-10: 사용자 결정. 버전을 올리는 길 대신 부품을 빼는 길로 간다. 사용자 DB는 절대 바뀌면 안 되고, 새 버전 알림은 베타로 보고 고쳐도 된다.
- 2026-11-10: 설계 검토에서 `qopensslbackend.dll`에 `OpenSSL 3.5.4` 표시가 UTF-16으로 들어 있음을 확인해 함께 빼기로 했다.
- 작업 1: 열쇠 재료·백업 해시 고정 값 테스트(`tests/test_openssl_free.py`, 한글 사용자 이름 포함)와 OpenSSL을 막는 실행기(`tools/run_without_openssl.py`). 기대값은 OpenSSL 3.0.16이 있는 환경에서 뽑았다.
- 작업 2: `data`·`release`가 `DATA_TESTS`를 OpenSSL을 막은 프로세스로 한 번 더 돌린다(`pytest-no-openssl`). 첫 실제 실행은 앱이 아직 `ssl`을 import해 수집 오류 3건으로 실패했다. 하네스가 OpenSSL 의존을 실제로 잡는다는 근거다.
- 작업 3: `src/winhttp_get.py`. `ctypes`로 WinHTTP를 불러 HTTPS GET 한 번. TLS 1.2 이상(1.3 지정이 거절되면 1.2만), 리디렉션·쿠키·자동 인증 끔, 단계별 10초와 전체 상한 30초, 본문 상한. 로컬 서버 시험으로 자체 서명 인증서 거부(요청을 보내지 않음), 프록시 경유(평문은 절대 URL, HTTPS는 CONNECT), 프록시의 407이 상태로 돌아옴을 고정했다.
  - 실측: WinHTTP는 루프백 대상(127.0.0.1)에 지정 프록시를 쓰지 않고 직접 연결한다. 프록시 시험은 `proxy-target.invalid`를 대상으로 한다. 닫힌 프록시는 오류 12029(시간 초과 아님)라 `connection`으로 분류된다.
  - 상수의 뜻과 적용 핸들은 Microsoft 문서 [Option flags](https://learn.microsoft.com/windows/win32/winhttp/option-flags)로 대조했다(DISABLE_FEATURE는 요청 핸들, SECURE_PROTOCOLS는 세션 핸들). 값은 Windows SDK `winhttp.h` 기준이고 동작은 테스트가 고정한다.
  - 사전 확인: 새 통신 층으로 앱의 고정 주소를 한 번 읽어 200·5,243바이트·최신 `v4.8`·0.25초.
- 작업 4: `update_check.py`에서 `ssl`·opener를 없애고 `proxy_for`·`check_latest(fetch=None)`로 바꿨다. 실패 분류 이름은 그대로다. 막는 실행기가 `sys.path[0]=tools/`로 떠서 루트의 `main`·`screen_text`를 못 찾던 결함을 고쳤다(`python -m pytest`처럼 프로젝트 루트를 넣는다).
- 작업 5: `build.spec` excludes에 `ssl`·`_ssl`·`_hashlib`, `build_app.without_openssl`로 다섯 파일을 묶음에서 거른다. 앱 코드의 `hashlib.pbkdf2_hmac`·`scrypt`·`new` 사용을 `test_packaging.py`가 막는다.
- 작업 6: `verify.openssl_check`. EXE 안 파일 이름과 모든 dll·pyd의 OpenSSL 버전 표시(ASCII·UTF-16)를 본다. 표시는 `cryptography`의 `_rust.pyd`에만 허용한다.
  - 첫 release는 이 검사에서 잘못 실패했다. Analysis TOC는 `build.spec`이 묶음을 거르기 전 목록이라 `qopensslbackend.dll`이 남는데 그것을 실패로 봤다. 판정을 EXE 안 파일로 바꾸고 TOC에만 있던 파일은 `filtered`로 기록한다(설계 7.4 정정).
- 작업 7: 라이선스 고지에서 OpenSSL 3.0.16 표기와 `OpenSSL-3.0.16-AUTHORS.txt`를 걷어냈다. `cryptography` 쪽 4.0.1과 Python 자체의 고지는 그대로다.
- 작업 8: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/CODING_STANDARDS.md`, `docs/TESTING.md`, 새 버전 알림 설계 8절.
- 작업 9: `tools/exe_handoff_check.py`와 아래 실제 EXE 증거.
- 구현 중 배운 것: Bash 도구의 heredoc은 이중 역슬래시를 하나로 줄인다. 역슬래시가 든 코드는 편집 도구로만 쓴다(한 번 `verify.py`에 NUL 바이트가 들어가 미커밋 편집을 되돌리고 다시 넣었다).

이 파일은 진행 기록이다. 영구 지침은 `AGENTS.md`가 지정한 정본 문서에 반영하고
여기에 그 링크를 남긴다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `verify.py data` | 통과 | `20261110-195134-0b08f19d5a` | 보통 실행 643 통과·1 건너뜀, OpenSSL을 막은 실행 643 통과·1 건너뜀. 커밋 `59782fc` 직전 작업 트리 |
| `verify.py quick --tests`(새 버전 확인·통신 층) | 통과 | `20261110-194804-d98b278fa0` | 작업 4 |
| `verify.py release` (PowerShell) 1차 | 실패 | `20261110-200441-57d3cf0530` | pytest 전체·OpenSSL 없는 검사·빌드는 통과, `openssl_check`가 거르기 전 목록을 실패로 봄(검사 결함, EXE는 깨끗) |
| `verify.py release` (PowerShell) 2차 | 통과 | `20261110-202000-7537eea7ba` | 커밋 `ca1c8e1`. 공휴일 최신 확인, pytest 4,447개(4,446 통과·1 건너뜀), OpenSSL 없는 데이터 검사 643 통과, 빌드, EXE 구성, 격리 실행 7개 장면 |
| v4.8 EXE 교대 실행 | 통과 | `20261110-203548-24e462fa78` (`handoff.json`) | v4.8(`0FD5D135…796AD8`) → 새 EXE → v4.8, 매번 데이터 불변·건강 검사·오류 로그 없음. 준비 시간 4.97·5.01·5.17초 |
| 교대 실행 도구 자체 점검 | 통과 | `20261110-200350-257b5ffa4f` | v4.8 EXE만 세 번 |
| 실제 TLS(`--live-update-check`) | 통과 | `20261110-202000-7537eea7ba/smoke/update_check_live` | 105초 동안 실패 기록 없음(이 PC, 프록시 없음) |

release 2차의 EXE(개발 중간 빌드, 배포 EXE 아님): `기후노트_v4.9.exe` 92,492,388 bytes, SHA-256 `78AA1C9630777F06805280B809FA0EEABB0BF219F8EEA776D8502D3DE263AE0E`.

- EXE 구성: BINARY 62개(v4.8은 64개), 검증 환경 밖 0개, Qt DLL 15개 원본과 동일, 앱 모듈 59개, OpenSSL 파일 0개, 버전 표시는 `_rust.pyd`(OpenSSL 4.0.1)뿐(dll·pyd 105개 확인), 묶기 전에 거른 파일 1개(`qopensslbackend.dll`), PYZ에 `ssl` 없음.
- 크기: v4.8 94,876,233 → 92,492,388 bytes(−2,383,845).
- 새 버전 확인 장면: 닫힌 프록시에서 `새 버전 확인 실패: connection` 기록(프록시 읽기와 WinHTTP 통신 층이 EXE에서 돈다).
- 격리 실행 시간(초, 직전 release `20261110-163232-57989df8e8` → 이번): 신규 6.9 → 6.9, 기존 8.2 → 7.5, 차단 7.7 → 6.8, v17 7.2 → 6.2, v18 7.1 → 6.6, 새 버전 확인 68.6 → 68.2, 글자 따기 15.3 → 15.0.
- SHA-256이 느려진 영향(보통 → OpenSSL 막음, 중앙값): 모델 5개 15.2MiB 해시 16.6 → 49.5ms, 5MiB 파일 4.4 → 15.9ms, 50MiB 파일 44.4 → 155.0ms. 체감할 크기가 아니다.

현재 입력에 대한 실제 결과만 기입한다.

### 최종 검토 뒤(2026-11-10 밤)

별도 검토자(새 컨텍스트)가 전체 변경을 읽었다. Critical 없음, `database.py`·`security.py` 무변경과 데이터 안전 성립을 확인받았다. 고친 것(`11a85ea`, 각각 실패하는 테스트를 먼저 썼다):

- 요청 전체 상한이 응답 머리줄 단계에서 지켜지지 않았다(머리줄을 0.3초마다 1바이트씩 흘리는 서버에서 서버가 끊을 때까지 150초, 검토자 재현). 상한 시각에 감시 타이머가 요청 핸들을 닫는다.
- `winhttp.dll`을 이름만으로 불러 EXE 폴더를 System32보다 먼저 찾았다. System32에서만 불러온다.
- `OSError`·`ValueError` 밖의 예외가 `check_latest()` 밖으로 나갈 수 있었다. `connection`으로 분류하고 종류 이름만 기록한다.
- release의 새 버전 확인 장면이 닫힌 포트의 `connection`을 기대해, `winhttp.dll`을 못 여는 고장과 구별하지 못했다. 터널 요청에 407로 답하는 로컬 프록시로 바꿔 `http-407` 기록과 프록시가 받은 터널 요청으로 판정한다.
- `test_crypto_compat.py`(과거 암호문을 읽는 고정 벡터)를 OpenSSL을 막은 데이터 검사에 넣었다(설계 8절).
- `.gitattributes`에 남은 지운 고지 파일 줄을 뺐다.

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 유의사항 |
|---|---|---|---|
| 수정 관련 pytest 묶음(통신 층·새 버전 확인·하네스·고지·smoke) | 통과 | 직접 실행 | 230 통과·1 건너뜀, 92 통과 |
| 고친 통신 층으로 실제 확인 한 번 | 통과 | 직접 실행 | 200, 최신 `v4.8`, 0.25초 |
| `verify.py release` (PowerShell) 3차 | **미실행(중단)** | `20261110-210726-809b40c1fd` | 시스템 메모리 부족으로 하네스 밖에서 중단됐다. 명령의 실패가 아니다. 결과 없음 |
| v4.8 EXE 교대 실행(수정 뒤 EXE) | 미실행 | | release 3차 뒤에 한다 |
| 실제 TLS(`--live-update-check`, 수정 뒤 EXE) | 미실행 | | release 3차 뒤에 한다 |

위 표의 release 2차·교대 실행·실제 TLS 증거는 수정 전 커밋(`ca1c8e1`)의 것이다. `11a85ea`가 `src/winhttp_get.py`·`src/update_check.py`·`tools/`를 바꿨으므로 현재 코드의 통과 근거로 쓰지 않는다. 데이터 쪽 코드는 바뀌지 않았다.

미룬 작은 지적(검토자 Minor, 고치지 않음): 프록시 값의 드문 모양(socks 스킴 등) 거부, `without_openssl`의 `-x64` 변형 이름, UPX 압축 파일을 실패로 볼지, 테스트의 포트 9 고정, 1ms 미만 시간 제한, 헤더 길이 계산, 실행기 종료 코드 3의 원인 문구, 정적 테스트 둘, 교대 실행 도구 설명 한 줄.

## 미해결과 인계

- 남은 문제 / 수동 확인:
  - 인터넷이 되는 PC에서 `인터넷 접속`을 켠 실제 알림(지금은 최신 Release가 v4.8이라 v4.9 EXE에는 알림이 뜨지 않는다. 개발 미리보기 `tools/dev_update_check_preview.py`로 화면은 볼 수 있다).
  - 프록시를 쓰는 망에서의 동작. 인증을 요구하는 프록시는 `http-407`, 사용자 정보가 든 프록시 주소는 `connection`으로 남고 화면에는 보이지 않는다.
  - Windows가 인증서 확인을 위해 스스로 하는 통신이 막힌 망에서는 `connection`·`timeout`이 남을 수 있다.
  - 재검사 도구의 판정은 돌려 봐야 안다. `cryptography` 안의 OpenSSL이 새로 지적되면 `cryptography` 버전 올리기(lock 갱신·전체 재검증·EXE 재빌드)로 대응한다.
- 변경한 정본 문서: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/CODING_STANDARDS.md`, `docs/TESTING.md`, `docs/superpowers/specs/2026-11-04-update-check-design.md`, `docs/RELEASE_HISTORY.md`.
- 다음 행동: (1) PowerShell `release`를 다시 돌린다 → (2) 그 EXE로 `tools/exe_handoff_check.py --old dist\기후노트_v4.8.exe --new <실행 폴더>\dist\기후노트_v4.9.exe` → (3) `tools/smoke_release.py --exe … --run-dir … --live-update-check` → (4) 이 표와 릴리스 이력의 중간 빌드 값을 새 결과로 고친다. 그 뒤 v4.9를 마무리할 때 최종 `release`로 배포 EXE를 만들고 재검사에 낸다.
- 배포·커밋·push 여부: 작업별 로컬 커밋. push는 하지 않았다(사용자 승인 필요).
