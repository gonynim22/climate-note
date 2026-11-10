# EXE에서 Python용 OpenSSL 빼기(새 버전 확인을 Windows 내장 통신으로) 설계

- 날짜: 2026-11-10
- 대상: v4.9(개발 중). DB v19·Export v4 그대로
- 상태: 사용자 승인 대기(검토 반영 2026-11-10: Qt OpenSSL 플러그인 제외, 고지 파일 목록, '요청 한 번'의 범위)
- 관련: [새 버전 알림 설계](2026-11-04-update-check-design.md)(8절 네트워크 계약을 이 문서가 바꾼다)

## 1. 의도와 이유

2026-11-10 기관의 바이너리 검사가 배포 EXE(v4.8)에 든 구성요소 **OpenSSL 3.0.16**의 공개 취약점(CVE)을 지적했고 보완을 요청했다. 앱 코드에서 나온 지적은 없다. 검사 원본은 기관 내부 자료라 저장소 밖에 둔다.

이 OpenSSL은 앱이 고른 것이 아니라 빌드에 쓰는 Python이 딸려 넣는 부품이다. 버전을 올려서 맞추는 길은 계속 따라가야 하고(3절 '확인한 사실'), 앱이 이 부품을 쓰는 곳은 새 버전 확인의 HTTPS 한 곳뿐이다. 그래서 **부품 자체를 EXE에서 빼고**, 새 버전 확인은 Windows에 들어 있는 통신 기능으로 바꾼다.

사용자가 말한 조건 두 가지가 이 설계의 맨 위에 있다.

1. **사용자의 DB는 절대 바뀌면 안 된다.** 일정이 꼬이거나 사라지는 것이 최악이다.
2. 새 버전 알림은 거의 베타이고 쓰는 사람이 드물다. 고쳐도 된다.

## 2. 목표 · 비목표 · 반목표

### 목표

- G1. 배포 EXE에 Python용 OpenSSL 네 파일(`libcrypto-3.dll`, `libssl-3.dll`, `_ssl.pyd`, `_hashlib.pyd`)과 Qt의 OpenSSL 연결 플러그인(`PySide6/plugins/tls/qopensslbackend.dll`)이 없다. `release`가 이번 EXE에서 직접 확인한다. 이 문서에서 '다섯 파일'은 이 다섯을 가리킨다.
- G2. 새 버전 확인은 사용자가 보기에 지금과 같게 돈다(스위치, 시점, 알림, 실패는 화면에 안 보임). 통신만 Windows 내장 기능(WinHTTP)이 맡는다.
- G3. 누가 나중에 OpenSSL에 기대는 코드를 넣으면 EXE를 만들기 전에 테스트가 막는다.
- G4. OpenSSL이 없는 EXE가 기존 사용자 데이터를 지금과 똑같이 읽고 쓴다는 증거를 남긴다(8절).

### 비목표

- 빌드 Python 버전 교체(3.13.5 그대로). Python 자체의 보안 수정 반영은 별도 후속 후보로만 적는다.
- `cryptography` 안에 정적으로 든 OpenSSL(4.0.1). 일정·메모 암호화가 쓰므로 뺄 수 없고 이번 검사에도 잡히지 않았다. 손대지 않는다.
- 새 버전 알림의 화면·예약·설정 키·문구 변경.
- 프록시 인증, 자동 구성 스크립트(PAC) 지원 추가. 지금도 지원하지 않는다.
- 소스로만 도는 개발 도구(`fetch_data.py`, `tools/`)의 `ssl` 사용. EXE에 들어가지 않으므로 그대로 둔다.
- Qt의 나머지 TLS 플러그인(`qschannelbackend.dll`·`qcertonlybackend.dll`)과 `Qt6Network.dll`. OpenSSL 표시가 없고 qfluentwidgets가 QtNetwork를 요구하므로 그대로 둔다.

### 반목표(기술적으로 돌아가도 실패로 본다)

- 사용자 DB·salt·백업·설정 값이 바뀌거나, 기존 암호문을 읽지 못하게 된다.
- `src/database.py`, `src/security.py`를 이 작업에서 고친다. 두 파일은 한 줄도 바꾸지 않는다.
- 인증서 검증을 끄거나 느슨하게 한다(검증 무시 플래그, 오래된 TLS 허용).
- `인터넷 접속`이 꺼진 PC에서 요청이 나간다.
- 확인 실패가 화면에 보인다.
- 빌드는 성공하고 EXE에서만 깨지는 변경이 검증 없이 들어간다.

## 3. 확인한 사실(2026-11-10)

| 사실 | 근거 |
|---|---|
| EXE의 OpenSSL 3.0.16은 빌드 Python 3.13.5의 `DLLs\libcrypto-3.dll`·`libssl-3.dll`이고 `_ssl.pyd`·`_hashlib.pyd`가 끌고 들어온다. Git Bash mingw64 혼입이 아니다 | `build/build/Analysis-00.toc`의 원본 경로, DLL 파일 버전 3.0.16 |
| 앱 코드의 `ssl` 사용은 `src/update_check.py` 한 곳(13행 import, 78행 `ssl.create_default_context()`) | `src/`·`screen_text/` 검색 |
| 앱 코드의 `hashlib` 사용은 `sha256`뿐: `database.py` 2342·2352행(백업 manifest), `security.py` 75·83·93행(PC 고유값·파일 링크 표식), `screen_text/engine.py` 90행(모델 MANIFEST) | 같은 검색 |
| `security.py` 75·93행의 해시는 암호화 열쇠의 재료다. 값이 달라지면 기존 암호문을 읽지 못한다 | `_get_hardware_id`·`_get_legacy_hardware_id` → `_derive_fernet_key` |
| `hmac`은 `compare_digest`만 쓴다(`security.py` 239·247행) | 같은 검색 |
| 열쇠 파생(PBKDF2)과 Fernet은 `cryptography` 50.0.0이 맡고 그 안의 OpenSSL 4.0.1을 쓴다. Python용 OpenSSL과 무관하다 | `backend.openssl_version_text()` |
| `_ssl`·`_hashlib`를 막은 프로세스에서 `hashlib.sha256`·`hmac.new`·`compare_digest`·`secrets`·`uuid`·`random`·Fernet 왕복이 모두 같은 값으로 돈다. `hashlib.pbkdf2_hmac`·`hashlib.scrypt`는 사라진다 | 차단 실험(소스 환경) |
| 같은 실험에서 SHA-256 속도는 2,020 → 325 MiB/s(64MiB 32 → 197ms) | 같은 실험 |
| 앱이 쓰는 라이브러리 15개(qfluentwidgets, qframelesswindow, onnxruntime, PySide6, shiboken6, PIL, pywin32 3개, numpy, defusedxml, cryptography, darkdetect, flatbuffers, protobuf)의 `.py`에 `import ssl`·`_hashlib`·`pbkdf2_hmac`·`scrypt`·`hashlib.new(`가 없다 | 정적 검색 0건(실제 EXE 확인은 9절) |
| OpenSSL 3.0은 2026-09-07 지원이 끝났다. Windows 설치본이 있는 마지막 Python 3.13은 3.13.16(OpenSSL 3.5.9)이고, 2026-11-10에 3.5.10에서 고치는 CVE가 새로 발표됐다 | python.org 릴리스 노트, OpenSSL 취약점 목록 |
| `release`의 기존·업그레이드 시나리오는 소스 Python(OpenSSL이 있는 hashlib)이 만든 합성 데이터를 EXE가 열고, 끝난 뒤 소스 Python이 데이터 불변·백업 검증을 다시 본다 | `tools/smoke_release.py`의 `seed`·`inspect`·`_check_existing`·`_check_upgrade` |
| 라이선스 고지에 OpenSSL 3.0.16 표기가 있다. `components.json`의 `openssl` 항목은 `3.0.16 / 4.0.1` 합본이다 | `licenses/components.json` 239·243·248행, `licenses/NATIVE-NOTICE.txt` 8·12행, `licenses/ORIGINS.json` 64·68~69행, `licenses/OpenSSL-3.0.16-AUTHORS.txt` |
| EXE에 들어가는 바이너리 중 OpenSSL 버전 표시가 든 파일은 넷이다: `libcrypto-3.dll`(`OpenSSL 3.0.16 11 Feb 2025`, ASCII), `_hashlib.pyd`(`OpenSSL 3.0.0`, ASCII), `qopensslbackend.dll`(`OpenSSL 3.5.4 30 Sep 2025`, **UTF-16**), `cryptography`의 `_rust.pyd`(`OpenSSL 4.0.1 9 Jun 2026`, ASCII). ASCII로만 찾으면 Qt 플러그인을 놓친다 | venv·Python `DLLs`의 dll·pyd를 두 인코딩으로 검색 |
| `qopensslbackend.dll`은 v4.8 EXE에도 들어 있었고 1차 검사의 구성요소 목록에는 `openssl-3.0.16` 하나만 나왔다. 도구가 무엇으로 식별하는지는 알 수 없다 | v4.8 빌드 TOC, 검사 결과(저장소 밖) |
| 앱 코드와 qfluentwidgets의 `.py`는 QtNetwork·QSsl을 쓰지 않는다. Qt는 TLS 플러그인을 처음 쓸 때 불러온다 | 정적 검색 0건 |
| 설정 화면의 안내 문구는 "켜면 하루 한 번 GitLab 공개 저장소에서 새 버전이 있는지만 확인합니다. 일정·메모는 보내지 않습니다. 업무망 PC는 꺼 두세요."다 | `src/ui_settings.py` 861행 |

## 4. 지켜야 할 기존 계약

`AGENTS.md`의 새 버전 알림(v4.7) 문단과 [새 버전 알림 설계](2026-11-04-update-check-design.md)에서 그대로 남는 것:

- 유일한 쓰기는 `internet_access_enabled` 한 키. 확인 시각·발견 버전·알림 표시는 메모리 전용.
- 꺼진 PC에서는 요청이 한 번도 나가지 않고, 요청 직전에도 키를 다시 읽는다(`ui_update_check.py`, 바꾸지 않는다).
- 앱이 보내는 요청은 고정 주소 GET 한 번, 앱이 정하는 헤더는 `Accept`와 고정 User-Agent뿐, 10초, 256KiB, 리디렉션을 따르지 않음(Windows가 인증서 확인을 위해 스스로 하는 통신은 6절 9번).
- 실패는 화면에 보이지 않고 `app_error`에 분류만 남는다. 분류 이름 `timeout`·`connection`·`http-<코드>`·`format`·`worker`를 그대로 쓴다.
- 판정·요청 모듈에는 Qt·DB가 없다. 예약·작업 스레드는 `ui_update_check.py`, 화면은 `ui_update.py`.
- 배포 EXE에 버전·주소를 바꾸는 옵션이나 환경 변수를 두지 않는다. 개발 미리보기는 `tools/dev_update_check_preview.py`만 쓴다.
- 앱 코드가 import하는 모듈은 `build.spec`의 excludes에 넣지 않는다(`tests/test_packaging.py`).
- 테스트·EXE 검증은 실행별 합성 데이터 폴더에서만 한다. 실사용 AppData·DB·salt를 쓰지 않는다.
- `release`와 빌드는 PowerShell에서 돌린다.

## 5. 사용자가 정한 것

- EXE에서 OpenSSL을 빼는 길(B안)로 간다. 기한은 넉넉하다.
- 사용자의 DB는 절대 바뀌면 안 된다.
- 새 버전 알림은 베타로 보고 고쳐도 된다.

## 6. 내가 정한 것(사용자 확인 대상)

1. **통신은 WinHTTP를 `ctypes`로 직접 부른다.** Windows에 늘 들어 있고 인증서 검증을 Windows가 맡는다. 견준 길: Qt 통신(QtNetwork)은 '판정·요청 모듈에 Qt 없음' 계약과 작업 스레드 구조를 함께 바꿔야 해서 뺐고, `curl.exe` 같은 외부 프로그램 실행은 업무 PC에서 막힐 수 있고 프로세스 실행이 늘어 뺐다.
2. **프록시는 지금 읽는 방식 그대로 읽어서 WinHTTP에 넘긴다.** `urllib.request.getproxies()`의 `https` 항목과 `proxy_bypass()`를 그대로 쓰고(환경 변수 → Windows 인터넷 설정 순), 프록시가 있으면 지정 프록시로, 없거나 예외 대상이면 직접 연결한다. WinHTTP의 자동 프록시 탐지는 쓰지 않는다(지금 동작과 달라진다). 프록시 주소에 사용자 정보(`user:pass@`)가 있으면 요청하지 않고 `connection`으로 분류한다(지금은 urllib이 인증 헤더를 붙여 줬다. 베타 기능의 드문 경우라 지원을 줄인다).
3. **TLS는 1.2 이상만 허용한다.** 지금의 `ssl.create_default_context()`와 같은 하한이다. TLS 1.3 지정이 거부되는 Windows에서는 1.2만으로 다시 지정한다.
4. **Python 버전은 그대로 둔다.** OpenSSL을 빼면 Python이 어떤 OpenSSL을 달고 오는지는 EXE와 무관해진다.
5. **라이선스 고지에서 OpenSSL 3.0.16 부분을 걷어낸다.** 빠진 부품을 고지에 남기지 않는다. `cryptography` 쪽 4.0.1 고지는 그대로 둔다(`components.json`의 `openssl` 항목은 지우지 않고 4.0.1만 남게 고친다). 걷어내는 근거는 이번 빌드의 TOC다.
6. **Qt의 `qopensslbackend.dll`도 EXE에서 뺀다.** OpenSSL 본체가 아니라 OpenSSL을 찾아 쓰는 연결 조각이지만 안에 `OpenSSL 3.5.4` 표시가 들어 있다(3절). 검사 도구가 글자 표시로 식별한다면 OpenSSL 코드가 없어도 다시 지적될 수 있다. OpenSSL DLL이 빠진 EXE에서 이 플러그인은 어차피 일을 하지 못하고, 앱과 qfluentwidgets는 Qt의 TLS를 쓰지 않는다. 그 뒤 `release`가 EXE 안 모든 바이너리에서 OpenSSL 버전 표시를 ASCII와 UTF-16 두 가지로 찾아 기록하고, `cryptography`의 `_rust.pyd` 밖에서 나오면 실패로 본다.
7. **공개 저장소에 올라가는 문서에는 검사 결과의 상세(건수, 개별 CVE, 도구, 담당자)를 적지 않는다.** 원본은 저장소 밖에 있다.
8. **중단 조건을 둔다(11절).** 데이터 동등성 확인이 하나라도 어긋나면 이 길을 멈춘다.
9. **'요청 한 번'은 앱이 보내는 요청을 뜻한다.** 지금의 Python `ssl`은 PC에 저장된 인증서만으로 검증한다. Windows는 인증서 사슬이 불완전하거나 최상위 인증서가 PC에 없으면 검증을 위해 인증기관·Microsoft 서버에 스스로 접속할 수 있다. 이것은 검증을 느슨하게 하지 않고는 끌 수 없으므로 Windows의 동작으로 문서에 밝히고 계약 위반으로 보지 않는다. `인터넷 접속`을 켠 PC에서 확인을 할 때만 생긴다. 인증서 폐기 확인은 지금도 하지 않으며 새로 켜지 않는다. 설정 화면 문구는 그대로 둔다.

## 7. 설계

### 7.1 구성

```
ui_update_check.py  (예약·작업 스레드, 바꾸지 않음)
        │  update_check.check_latest()
        ▼
update_check.py     (판정·응답 해석·실패 분류·프록시 결정. Qt·DB·ssl 없음)
        │  고정 주소, 헤더 2개, 10초, 256KiB+1, 프록시
        ▼
<WinHTTP 모듈>      (새 파일. HTTPS GET 한 번만 아는 얇은 층. 앱의 다른 것을 모른다)
        │  ctypes
        ▼
winhttp.dll         (Windows 내장. TLS·인증서 검증)
```

- `update_check.py`에서 `import ssl`, `https_only_opener()`, urllib opener 사용을 없앤다. `urllib.request`는 프록시를 읽는 두 함수(`getproxies`, `proxy_bypass`) 때문에 남긴다. 그래서 `http`·`email`을 excludes에 넣지 않는 기존 규칙도 그대로다.
- `check_latest()`는 테스트가 통신 층을 바꿔 끼울 수 있는 인자를 계속 받는다(지금의 `opener` 자리). `ui_update_check._run_check`와 개발 미리보기가 `update_check.check_latest`를 부를 때 찾는 구조는 유지한다.
- 새 모듈과 `update_check.py`의 import는 지금처럼 모듈 맨 위에 둔다(EXE에서 모듈이 빠지면 시작 때 드러나야 한다). `winhttp.dll`을 여는 것은 요청할 때 하고, 열지 못하면 `connection`이다.

### 7.2 WinHTTP 모듈이 지키는 것

- 받는 것: `https://` 주소 하나, 헤더, User-Agent, 시간 제한, 읽기 상한, 프록시(없음 또는 `호스트:포트`). 돌려주는 것: 상태 코드와 본문(상한+1 바이트까지). 실패는 종류를 알 수 있는 예외 하나.
- 공개 함수는 `https`가 아닌 주소를 거부한다.
- 요청 한 번에 한 번만 보낸다. 리디렉션·쿠키·자동 인증을 끈다. 클라이언트 인증서를 보내지 않는다.
- 인증서 검증은 WinHTTP 기본값 그대로다. 검증을 건너뛰는 보안 플래그를 어떤 경우에도 지정하지 않는다(테스트로 고정). 폐기 확인 옵션은 켜지 않는다(6절 9번).
- 이름 풀이·연결·보내기·받기 각각 10초. 본문을 읽는 반복이 전체 시간 상한 없이 이어지지 않게 한다. (최종 검토 뒤 보강: 응답 머리줄을 조금씩 흘리는 서버는 받기 호출 하나를 붙잡으므로, 상한 시각에 감시 타이머가 요청 핸들을 닫아 요청 전체에 상한을 건다. `winhttp.dll`은 System32에서만 불러온다.)
- 연 핸들은 실패 경로를 포함해 모두 닫는다.
- 64비트에서 핸들·포인터가 잘리지 않게 `ctypes` 함수마다 인자·반환 형식을 선언한다(`tools/smoke_release.py`의 `ProcessJob`이 같은 방식이다). 상수 값은 Microsoft 문서(`winhttp.h`)로 확인하고 출처를 주석에 남긴다.
- Qt·DB·설정·로그를 모른다. 작업 스레드에서 불린다.

### 7.3 실패 분류

| 상황 | 분류 |
|---|---|
| 상태 코드가 2xx가 아님(3xx 포함) | `http-<코드>` |
| WinHTTP 시간 초과, 전체 시간 상한 초과 | `timeout` |
| 이름 풀이·연결·TLS·인증서·연결 끊김·프록시 주소 오류·`winhttp.dll` 열기 실패, 그 밖의 통신 층 예외 | `connection` |
| 본문이 256KiB를 넘거나 형식이 다름 | `format` |
| 작업 스레드가 결과 없이 끝남 | `worker`(`ui_update_check.py`, 그대로) |

어떤 예외도 `check_latest()` 밖으로 나가지 않는다.

### 7.4 빌드

- `build.spec` excludes에 `ssl`, `_ssl`, `_hashlib`를 더한다. 이유를 주석으로 남긴다.
- `a.binaries`에서 `qopensslbackend.dll`을 걸러 낸다. 이 파일은 모듈이 아니라 PySide6 훅이 모으는 플러그인이라 excludes로는 빠지지 않는다. 걸러 내는 코드는 PyInstaller 없이 시험할 수 있게 둔다(`_spec_analysis`가 `Analysis`를 가짜로 바꿔 spec을 실행하는 지금 방식에서 확인할 수 있어야 한다).
- 안전망: 다른 경로로 OpenSSL DLL이 끌려 들어와도 묶음에 넣지 않도록 같은 자리에서 나머지 네 파일 이름도 걸러 낸다(만드는 사람이 실제 빌드에서 필요 없다고 확인하면 네 파일 쪽은 생략할 수 있다. G1 확인은 어느 쪽이든 `release`가 한다).
- `tests/test_packaging.py`
  - `test_build_spec_keeps_modules_update_check_needs`: `ssl`을 '빼면 안 되는 목록'에서 내리고 `http`·`email`·`urllib`·`socket`은 남긴다.
  - 새 단언: excludes에 `ssl`·`_ssl`·`_hashlib`가 있다.
  - 기존 `test_build_spec_keeps_every_module_the_app_imports`가 앱 코드의 `import ssl`을 자동으로 막는다.
  - 새 단언: `src/`·`screen_text/`가 `hashlib.pbkdf2_hmac`·`hashlib.scrypt`·`hashlib.new(`를 쓰지 않는다(OpenSSL 없이는 없거나 일부만 된다).
- `tools/verify.py`의 `release` 묶음 검사(`bundle_check` 또는 그 옆)
  - EXE 안 파일 목록에 다섯 파일이 없다. (구현 중 정정, 2026-11-10: Analysis TOC는 `build.spec`이 `a.binaries`를 거르기 전 목록이라 `qopensslbackend.dll`이 남는다. 판정은 EXE 안 파일로 하고, TOC에만 있던 파일은 '묶기 전에 걸러짐'으로 보고서에 남긴다.)
  - EXE 안 모든 바이너리에서 OpenSSL 버전 표시(`OpenSSL <숫자>.<숫자>.<숫자>`)를 ASCII와 UTF-16LE 두 가지로 찾아 보고서에 남기고, `cryptography`의 `_rust.pyd` 밖에서 나오면 실패한다(UPX로 압축돼 글자를 볼 수 없는 파일이 있으면 그 사실을 보고서에 적는다). 이 검사 함수는 3절의 네 파일로 단위 시험한다(UTF-16 표시를 찾는지 포함).

### 7.5 문서·고지

- `AGENTS.md`: v4.7 문단의 요청 설명과 '명령' 절에 'EXE에는 Python용 OpenSSL이 없다(`ssl`·`pbkdf2_hmac` 등 사용 금지, 근거 테스트)'를 넣는다.
- `docs/ARCHITECTURE.md`: 모듈 표의 `update_check.py` 줄, 새 모듈 줄.
- `docs/CODING_STANDARDS.md`: 229행 근처 '새 버전 확인도 같은 opener 규칙' 문장을 새 통신 규칙으로 바꾼다. `fetch_data.py` 규칙은 그대로다.
- `docs/TESTING.md`: release 설명(새 버전 확인 시나리오의 근거 문장, 새 묶음 검사).
- [새 버전 알림 설계](2026-11-04-update-check-design.md) 8절에 이 문서로 가는 한 줄.
- 라이선스 고지(6절 5번): `licenses/components.json`의 `openssl` 항목(버전·출처·파일 목록에서 3.0.16만 뺀다), `licenses/NATIVE-NOTICE.txt` 8·12행, `licenses/ORIGINS.json` 64·68~69행(64행의 LICENSE 출처는 4.0.1 기준으로 고친다), `licenses/OpenSSL-3.0.16-AUTHORS.txt` 삭제, 이를 단언하는 테스트. Python 자체의 고지(`python` 항목)는 그대로다.
- 작업 기록 `docs/work/2026-11-10-openssl-free-exe.md`(양식 `docs/templates/WORK_NOTE.md`). 릴리스 이력은 v4.9를 마무리할 때 적는다.

## 8. 데이터 안전(가장 중요한 절)

이 작업은 DB 코드를 고치지 않는다. 다만 OpenSSL이 빠지면 `hashlib.sha256`을 Python 내장 구현이 맡게 되고, 그 계산이 암호화 열쇠의 재료와 백업 검증에 쓰인다. SHA-256은 표준이라 같은 값이 나와야 하지만, 어긋나면 사용자가 일정을 읽지 못하므로 아래를 모두 증거로 남긴다.

1. **고정 값 테스트.** 정해 둔 입력(가짜 MachineGuid·사용자 이름)에 대해 `security._get_hardware_id()`·`_get_legacy_hardware_id()`·`file_link_origin()`과 `database._bytes_sha256()`·`_file_size_and_sha256()`이 미리 적어 둔 값과 같다. 기대값은 지금(OpenSSL이 있는) 환경에서 뽑아 테스트에 상수로 적는다. 기존 `tests/test_crypto_compat.py`와 `tests/fixtures/crypto_compat_cryptography46.json`(열쇠 파생·기존 토큰 고정 벡터)은 고치지 않고 함께 돌린다.
2. **OpenSSL을 막은 프로세스에서 데이터 검사 전체.** 어떤 모듈보다 먼저 `_ssl`·`_hashlib`를 막고 시작한 Python에서 `data` 프로필이 도는 테스트 묶음과 1번 테스트가 통과한다. 막힌 상태가 실제로 적용됐는지(`hashlib.sha256`이 OpenSSL 구현이 아님) 같은 실행에서 단언한다. pytest가 먼저 `hashlib`을 불러오므로 conftest에서 막는 것으로는 늦다. 시작 방법은 만드는 사람이 정한다.
3. **실제 EXE에서 양방향.** `release`의 기존·v17 업그레이드·v18 업그레이드 시나리오가 그대로 통과한다. 이 시나리오는 OpenSSL이 있는 소스 Python이 암호화해 만든 합성 데이터를 새 EXE가 열고(열쇠가 다르면 시작 건강 검사가 멈춘다), 새 EXE가 만든 일일 백업(manifest의 SHA-256)을 소스 Python이 검증한다.
4. **v4.8 EXE와 교대 실행(일회성 증거).** 같은 합성 폴더를 v4.8 EXE(OpenSSL 있음) → 새 EXE → v4.8 EXE 순으로 열고, 매번 뒤에 데이터 불변·건강 검사·오류 로그 없음(3번과 같은 `inspect`)을 확인한다. 상시 시나리오로 넣을지는 만드는 사람이 정한다. 결과는 작업 기록에 남긴다.
5. **안전망은 이미 있다.** 열쇠가 달라지는 일이 생겨도 시작 전 건강 검사가 데이터를 바꾸지 않고 시작을 멈춘다(`release`의 차단 시나리오가 이것을 본다). 이 동작을 바꾸지 않는다.

## 9. 검증

- 통신 층 단위 시험(인터넷 불필요)
  - 로컬 서버로: 상태 코드 읽기, 본문 상한(딱 맞음/1바이트 넘음), 3xx를 따르지 않고 요청이 한 번뿐임, 보낸 헤더(앱이 정한 것은 `Accept`·User-Agent뿐, 쿠키를 다시 보내지 않음), 느린 서버의 `timeout`, 닫힌 포트의 `connection`, 닫힌 프록시의 `connection`, 실패 뒤 핸들 닫힘.
  - 로컬 HTTPS 서버(시험 중에 만든 자체 서명 인증서)에 대한 요청은 **거부**돼 `connection`이 된다(인증서 검증이 켜져 있다는 근거. 시험은 소스에서 돌므로 서버 쪽은 Python `ssl`을 써도 된다).
  - 평문 로컬 서버를 쓰는 시험을 위해 안쪽 함수에 시험용 통로를 둘 수 있다. 앱 경로에서 평문 요청이 나갈 수 없다는 것(공개 함수는 `https`만)을 테스트로 고정한다.
- `update_check.py` 시험: 지금의 판정·분류 표를 새 통신 층 가짜로 다시 쓴다(고정 헤더, 크기 상한, 실패 분류, 통신 층 준비 실패, 프록시 선택, 사용자 정보가 든 프록시 거부, Qt·DB·`ssl` 없음).
- `tests/test_ui_update_main.py`·`test_source_layout.py`·개발 미리보기는 `check_latest`의 인자 이름 변경만 따라간다. `tests/test_ui_update_check.py`의 `test_off_means_no_request_at_all`은 없어지는 `https_only_opener` 대신 새 통신 층을 '불리면 실패'로 바꿔 끼워, 꺼진 PC에서 통신 층이 한 번도 불리지 않음을 계속 단언한다.
- Qt 플러그인을 뺀 영향: `release`의 모든 격리 실행 시나리오(신규·기존·차단·업그레이드 둘·새 버전 확인·글자 따기)가 그대로 통과한다.
- 하네스: 바꾼 파일에 맞춰 `quick --tests <관련 파일>`, 데이터 절 때문에 `data`, 실행기·격리를 건드리면 `full`, 마지막에 PowerShell에서 `release`. 실행 ID와 `summary.md`를 작업 기록에 남긴다.
- `release`의 `update_check` 시나리오: 닫힌 프록시(`HTTPS_PROXY=http://127.0.0.1:9`)를 준 EXE가 `새 버전 확인 실패: connection`을 남긴다(새 통신 층이 EXE에서 돈다는 근거). 문서의 근거 문장만 'http·ssl 모듈'에서 새 구성으로 고친다. (최종 검토 뒤 정정, 2026-11-10: `connection`은 `winhttp.dll`을 못 열어도 남으므로 근거가 약하다. 터널 요청에 407로 답하는 로컬 프록시를 주고 `http-407` 기록과 프록시가 받은 터널 요청으로 판정한다.)
- 인터넷 PC에서 `tools/smoke_release.py --live-update-check`: 75초 동안 실패 기록이 없다(실제 TLS와 인증서 검증이 성공한다는 근거).
- 재 볼 것: EXE 크기(직전 대비), 글자 따기 첫 실행의 모델 확인 시간과 일일 백업 시간(SHA-256이 느려진 영향), 시작 시간. 숫자를 작업 기록에 남긴다.
- 수동(사용자): 인터넷이 되는 PC에서 `인터넷 접속`을 켜고 새 버전 알림이 뜨는지, `error.log`에 무엇이 남는지(Windows의 인증서 확인이 막힌 망에서는 `connection`·`timeout`이 남을 수 있다). 기존 데이터로 새 EXE를 처음 켰을 때 일정·메모·스티키가 그대로인지.

## 10. 만드는 사람에게 맡기는 것

- 새 모듈의 이름과 함수 모양, 예외 이름, `check_latest`의 바꿔 끼우는 인자 이름.
- WinHTTP 호출 순서와 옵션 지정 방식(7.2의 결과를 지키는 한).
- 전체 시간 상한의 값(요청 하나가 10초 단위 몇 번을 넘겨 끝없이 이어지지 않는 선).
- OpenSSL을 막은 테스트 실행을 하네스의 어느 프로필에 어떻게 넣을지(8절 2번).
- v4.8 EXE 교대 실행을 일회성 스크립트로 할지 상시 시나리오로 할지(8절 4번).
- `a.binaries`에서 Python용 네 파일까지 거를지(7.4. `qopensslbackend.dll` 거르기는 필수다).

## 11. 중단 조건

아래 중 하나라도 생기면 구현을 멈추고 사용자에게 알린다. 이때 대안은 빌드 Python을 3.13.16으로 바꾸는 길(OpenSSL 3.5.9, 코드 수정 없음, 새 CVE가 나오면 다시 지적될 수 있음)이다.

- 8절 1~4번 중 하나라도 값이 다르거나 기존 데이터를 읽지 못한다.
- OpenSSL 없이는 돌지 않는 앱 기능이 EXE에서 발견되고, 그 기능을 고치려면 `database.py`·`security.py`를 건드려야 한다.
- WinHTTP로는 4절의 통신 계약(리디렉션 금지, 크기 상한, 인증서 검증)을 지킬 수 없다.

## 12. 끝난 뒤

- 재검사에는 v4.9 최종 EXE를 낸다. 최종 EXE는 v4.9를 마무리할 때 `release`로 만든다.
- 재검사 도구가 어떻게 판정할지는 돌려 봐야 안다. `cryptography` 안의 OpenSSL이 새로 지적되면 그쪽은 `cryptography` 버전 올리기(lock 갱신·전체 재검증·EXE 재빌드 한 묶음)로 대응한다.
- 소스코드 점검 결과가 오면 같은 v4.9 안에서 따로 다룬다.
