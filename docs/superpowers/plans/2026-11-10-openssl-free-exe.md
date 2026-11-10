# EXE에서 Python용 OpenSSL 빼기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 배포 EXE에서 Python용 OpenSSL(네 파일)과 Qt의 OpenSSL 연결 플러그인을 빼고, 새 버전 확인의 통신을 Windows 내장 WinHTTP로 바꾼다. 사용자 DB는 한 글자도 달라지지 않는다.

**Architecture:** `update_check.py`(판정·분류·프록시 결정)가 새 얇은 층 `winhttp_get.py`(ctypes로 WinHTTP GET 한 번)를 부른다. `build.spec`이 `ssl`·`_ssl`·`_hashlib`를 빼고 `build_app.without_openssl`이 다섯 파일을 묶음에서 거른다. `release`의 `openssl_check`가 이번 EXE에서 파일과 버전 표시를 직접 확인하고, 데이터 검사는 OpenSSL을 막은 프로세스에서 한 번 더 돈다.

**Tech Stack:** Python 3.13.5, ctypes + `winhttp.dll`, PyInstaller(onefile), pytest·pytest-qt, 프로젝트 하네스 `tools/verify.py`.

**Spec:** [docs/superpowers/specs/2026-11-10-openssl-free-exe-design.md](../specs/2026-11-10-openssl-free-exe-design.md) — 실행하는 사람은 이 계획과 함께 읽는다.

## Global Constraints

- `src/database.py`, `src/security.py`는 **한 줄도 고치지 않는다.** 고쳐야만 풀리는 문제가 나오면 멈추고 사용자에게 알린다(설계 11절).
- 설계 11절의 중단 조건 셋 중 하나라도 생기면 구현을 멈춘다. 대안은 Python 3.13.16 교체다.
- 테스트·EXE 검증은 합성 데이터 폴더에서만 한다. 실사용 AppData·DB·salt, 실행 중인 앱을 건드리지 않는다.
- 인증서 검증을 끄거나 느슨하게 하는 코드를 넣지 않는다. TLS는 1.2 이상만.
- 앱이 보내는 요청: 고정 주소 GET 한 번, 헤더 `Accept: application/json`과 User-Agent `ClimateNote-UpdateCheck`, 10초, 256KiB, 리디렉션·쿠키·자동 인증 없음.
- 실패 분류 이름은 `timeout`·`connection`·`http-<코드>`·`format`·`worker` 그대로. 어떤 예외도 `check_latest()` 밖으로 나가지 않는다.
- 설정 키·DB 버전(v19)·Export(v4)·화면·문구·예약(`ui_update_check.py`)을 바꾸지 않는다.
- 새 앱 모듈은 `src/`에 두고 `import winhttp_get`처럼 이름으로 import한다.
- Python 명령은 `.\.venv\Scripts\python.exe`만 쓴다. `release`와 빌드는 PowerShell에서 돌린다.
- 커밋은 사용자가 허락한 경우에만 한다. `git add`는 파일을 지정한다(다른 세션의 `docs/SCREEN_TEXT.md` 변경을 섞지 않는다). push는 하지 않는다.
- 공개 저장소다. 문서·커밋·주석에 검사 결과의 상세(건수, 개별 CVE, 도구, 담당자)를 적지 않는다.

## Review Focus

설계가 암시하지만 놓치기 쉬운 다섯 가지. 각 줄의 테스트는 괄호 안 작업에 들어 있다.

1. 업무망 프록시가 인증을 요구해 407을 돌려준다 → 화면 반응 없이 `http-407`로 분류된다(작업 3·4).
2. Windows 인터넷 설정의 프록시 값이 `호스트:포트`만 있거나, 스킴·끝 슬래시가 붙거나, 사용자 정보가 들어 있다 → 앞의 셋은 같은 `호스트:포트`로 읽고 사용자 정보는 요청 없이 `connection`이다(작업 4).
3. 서버가 본문을 조금씩 끝없이 흘려보낸다 → 전체 시간 상한에서 `timeout`으로 끝난다(작업 3).
4. Windows 사용자 이름이 한글이다 → 열쇠 재료 값이 OpenSSL이 있을 때 적어 둔 값과 같다(작업 1).
5. `winhttp.dll`을 열지 못한다 → 예외가 새지 않고 `connection`이다(작업 3·4).

## File Structure

| 파일 | 역할 |
|---|---|
| `src/winhttp_get.py` (새로) | WinHTTP로 HTTPS GET 한 번. 앱의 다른 것을 모른다 |
| `src/update_check.py` | `ssl`·opener 제거, `proxy_for`, `check_latest(fetch=None)` |
| `build_app.py` | `OPENSSL_FILE_NAMES`, `without_openssl()` |
| `build.spec` | excludes 3개, `a.binaries` 거르기 |
| `tools/run_without_openssl.py` (새로) | `_ssl`·`_hashlib`를 막고 pytest를 띄운다 |
| `tools/verify.py` | `DATA_TESTS`, `no_openssl_command`, `find_openssl_banners`, `openssl_check`, 보고서 |
| `tools/smoke_release.py` | 근거 문장, `UPDATE_CHECK_LIVE_SECONDS` |
| `tools/exe_handoff_check.py` (새로) | 옛 EXE → 새 EXE → 옛 EXE 교대 실행 증거 |
| `tests/test_openssl_free.py` (새로) | 열쇠 재료·백업 해시 고정 값, 막힘 확인 |
| `tests/test_winhttp_get.py` (새로) | 통신 층 |
| `tests/test_update_check.py`, `test_ui_update_check.py`, `test_ui_update_main.py`, `test_packaging.py`, `test_verify.py`, `test_ui_licenses.py` | 바뀐 계약 |
| `licenses/*`, `AGENTS.md`, `docs/*.md`, `docs/work/2026-11-10-openssl-free-exe.md` | 고지·지침·작업 기록 |

---

### Task 1: 데이터 고정 값과 OpenSSL을 막는 실행기

아무것도 바꾸기 전에 안전망부터 만든다.

**Files:**
- Create: `docs/work/2026-11-10-openssl-free-exe.md` (`docs/templates/WORK_NOTE.md` 양식. 목표·완료 조건은 설계 2·8·9절에서 옮긴다)
- Create: `tests/test_openssl_free.py`
- Create: `tools/run_without_openssl.py`

**Interfaces:**
- Produces: `tools/run_without_openssl.py <pytest 인자...>` — 어떤 것보다 먼저 `sys.modules["_ssl"] = None`, `sys.modules["_hashlib"] = None`, `os.environ["CLIMATENOTE_NO_OPENSSL"] = "1"`을 두고, 막힘을 확인한 뒤 `pytest.main(sys.argv[1:])`의 종료 코드로 끝난다. 막힘이 적용되지 않았으면 메시지를 stderr에 쓰고 종료 코드 3.

- [ ] **Step 1: 테스트를 쓴다**

```python
GUID = "00000000-1111-2222-3333-444444444444"
NODE = 0x112233445566
# (hardware_id, file_link_origin, legacy_hardware_id) — 2026-11-10 OpenSSL 3.0.16이 있는 환경에서 뽑은 값. 고치지 않는다.
VECTORS = {
    "harness-user": ("7dc650290c0532016a31ed99221d240780f68c6f63a0d69819396a6527bef122",
                     "ce5c1d958955efa62d4355ae0bfb45643c059988471c9b23634fc7b249e08204",
                     "e2ceb572c0de8aa64a1c351a7a3a9772f1d99be6d60d7a952a222c760c7b429f"),
    "홍길동": ("e272fbdcf9540e51e0db27be4c045821cbce4c2e4eae9fade70c22f81aa7c4fc",
               "f9e387933d51b28d46154ee1b35114b4a734364e9ed90c6b73e8fd446d8eff13",
               "0ef15c3856686fb0011a43943124312427bdebabfda6007ddea029cd7a2871a7"),
}


@pytest.mark.parametrize("user", VECTORS)
def test_key_material_matches_values_recorded_with_openssl(monkeypatch, user):
    monkeypatch.setattr(security, "_get_machine_guid", lambda: GUID)
    monkeypatch.setattr(security.uuid, "getnode", lambda: NODE)
    monkeypatch.setenv("USERNAME", user)
    assert (security._get_hardware_id(), security.file_link_origin(),
            security._get_legacy_hardware_id()) == VECTORS[user]


def test_backup_digests_match_values_recorded_with_openssl(tmp_path):
    assert db._bytes_sha256("기후노트 climate-note 2026".encode("utf-8")) == \
        "15dd49ec0a725cf5fe10f114eda32ea8d6ebfe511fb6c5d8150a3b474e3c4286"
    path = tmp_path / "payload.bin"
    path.write_bytes(bytes(range(256)) * 4096 * 3 + b"tail!")
    assert db._file_size_and_sha256(path) == (
        3145733, "9d7fb3c88cbab2d4739c50f9f811e879b3cdc7823aaf496096f14fa61a7a0945")


def test_openssl_is_really_blocked_in_the_no_openssl_run():
    if os.environ.get("CLIMATENOTE_NO_OPENSSL") != "1":
        pytest.skip("OpenSSL을 막은 실행에서만 본다")
    assert "openssl" not in hashlib.sha256.__name__ and not hasattr(hashlib, "pbkdf2_hmac")
    with pytest.raises(ImportError):
        import ssl  # noqa: F401


def test_runner_blocks_openssl_before_pytest_starts(tmp_path):
    if os.environ.get("CLIMATENOTE_NO_OPENSSL") == "1":
        pytest.skip("막은 실행 안에서 다시 띄우지 않는다")
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools/run_without_openssl.py"), "tests/test_openssl_free.py", "-q",
         "-p", "no:cacheprovider", "--basetemp", str(tmp_path / "inner")],
        cwd=ROOT, capture_output=True, encoding="utf-8", timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "4 passed, 1 skipped" in done.stdout
```

- [ ] **Step 2: 돌려서 실패를 확인한다**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_openssl_free.py -q`
Expected: 고정 값 3개 통과, 막힘 확인 1개 skip, `test_runner_blocks_openssl_before_pytest_starts`만 실패(실행기 파일 없음). 고정 값이 실패하면 **멈춘다**(지금 코드의 값과 계획의 값이 다르다는 뜻).

- [ ] **Step 3: `tools/run_without_openssl.py`를 쓴다**

막기 → 환경 변수 → `import hashlib`로 `"openssl" not in hashlib.sha256.__name__` 확인(아니면 종료 코드 3) → `import pytest` → `sys.exit(pytest.main(sys.argv[1:]))`. 막기 전에는 `sys`·`os`만 import한다(`hashlib`이 먼저 불리면 막을 수 없다).

- [ ] **Step 4: 통과를 확인한다**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_openssl_free.py -q` → `4 passed, 1 skipped`

- [ ] **Step 5: 작업 기록을 만들고 커밋한다**

```
git add tests/test_openssl_free.py tools/run_without_openssl.py docs/work/2026-11-10-openssl-free-exe.md docs/superpowers/specs/2026-11-10-openssl-free-exe-design.md docs/superpowers/plans/2026-11-10-openssl-free-exe.md
git commit -m "test: 열쇠 재료·백업 해시 고정 값과 OpenSSL을 막는 테스트 실행기"
```

### Task 2: 하네스가 데이터 검사를 OpenSSL 없이 한 번 더 돌린다

**Files:**
- Modify: `tools/verify.py` (`DATA_TESTS` 41행, `pytest_command` 아래, `save_report` 304행 근처, `execute` 554~559행)
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: Task 1의 `tools/run_without_openssl.py`
- Produces: `verify.no_openssl_command(run_dir) -> list[str]`, 보고서 키 `tests_no_openssl`, 단계 이름 `pytest-no-openssl`

- [ ] **Step 1: 테스트를 쓴다** (`execute`를 시험하는 기존 테스트의 가짜 `run_step` 방식을 그대로 따른다)

```python
def test_data_tests_include_openssl_free_vectors():
    assert "tests/test_openssl_free.py" in verify.DATA_TESTS


def test_no_openssl_command_runs_data_tests_through_the_blocking_runner(tmp_path):
    command = verify.no_openssl_command(tmp_path)
    assert command[:2] == [sys.executable, str(verify.ROOT / "tools/run_without_openssl.py")]
    assert all(test in command for test in verify.DATA_TESTS)
    assert str(tmp_path / "pytest-no-openssl.xml") in command and "--timeout=120" in command
    assert str(tmp_path / "pytest-tmp-no-openssl") in command  # 첫 pytest 단계와 임시 폴더를 나눠 쓴다
```

`execute` 시험 셋: `data`와 `release`는 `pytest` 뒤에 `pytest-no-openssl` 단계가 돌고 `report["tests_no_openssl"]`이 생긴다 / `quick`·`full`은 돌지 않는다 / 이 단계가 실패하면 종료 코드가 0이 아니고 `release`는 빌드로 넘어가지 않는다.

- [ ] **Step 2: 실패를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_verify.py -q`

- [ ] **Step 3: 구현한다**

`DATA_TESTS`에 `"openssl_free"`를 더한다. `no_openssl_command`는 `pytest_command`와 같은 옵션에 파일 이름만 `pytest-tmp-no-openssl`·`pytest-cache-no-openssl`·`pytest-no-openssl.xml`로 바꾼다. `execute`는 첫 pytest가 0으로 끝난 `data`·`release`에서만 이 단계를 돌리고 `pytest_exit`로 코드를 정한다. `save_report`는 `- OpenSSL 없는 데이터 검사: <junit 결과>` 한 줄을 더한다.

- [ ] **Step 4: 단위 시험 통과를 확인한다** — 같은 명령, 전부 통과

- [ ] **Step 5: 실제 `data` 프로필을 돌린다**

Run: `.\.venv\Scripts\python.exe tools/verify.py data`
Expected: `passed`, `summary.md`에 두 pytest 단계 모두 passed. `pytest-no-openssl`만 실패하면 원인을 가른다: 테스트 코드가 OpenSSL 전용 기능을 쓴 것이면 그 테스트만 고친다. 앱 코드가 원인이고 `database.py`·`security.py`를 고쳐야 하면 **멈춘다**. 실행 ID를 작업 기록에 적는다.

- [ ] **Step 6: 커밋** — `git add tools/verify.py tests/test_verify.py docs/work/2026-11-10-openssl-free-exe.md` / `feat: data·release 하네스가 OpenSSL을 막은 프로세스로 데이터 검사를 한 번 더 실행`

### Task 3: WinHTTP 통신 층

**Files:**
- Create: `src/winhttp_get.py`
- Test: `tests/test_winhttp_get.py`

**Interfaces:**
- Produces:

```python
TOTAL_TIMEOUT_FACTOR = 3                     # 요청 하나의 전체 상한 = timeout_seconds × 3

class WinHttpError(OSError):                 # .code: int(GetLastError), .timed_out: bool
    def __init__(self, code: int, *, timed_out: bool = False): ...

@dataclass(frozen=True)
class Response:
    status: int
    body: bytes                              # 많아야 max_bytes 바이트

def https_get(url: str, *, headers: dict[str, str], user_agent: str, timeout_seconds: float,
              max_bytes: int, proxy: str | None = None) -> Response
def _get(host: str, port: int, path: str, *, secure: bool, headers: dict[str, str], user_agent: str,
         timeout_seconds: float, max_bytes: int, proxy: str | None) -> Response
def _library()                               # 인자·반환 형식을 선언한 ctypes.WinDLL("winhttp", use_last_error=True). 못 열면 OSError
def _set_dword_option(handle, option: int, value: int) -> bool
def _set_tls_floor(session, set_option=_set_dword_option) -> None
def _close_handle(handle) -> None
```

- [ ] **Step 1: 테스트를 쓴다**

시험용 서버는 `http.server.ThreadingHTTPServer(("127.0.0.1", 0), …)`를 스레드로 띄우고 받은 `(경로, 헤더)`를 기록한다. 경로: `/ok`(200, `b"x" * 5000`), `/redirect`(302, `Location: /ok`), `/cookie`(200, `Set-Cookie: a=b`), `/407`(407), `/slow`(3초 뒤 200), `/drip`(200 뒤 0.3초마다 1바이트를 10초 동안). 공통 인자 `ARGS = dict(headers={"Accept": "application/json"}, user_agent="ClimateNote-UpdateCheck", timeout_seconds=5, max_bytes=10_000, proxy=None)`.

| 테스트 | 단언 |
|---|---|
| `test_reads_status_and_body_up_to_limit` | `/ok`: `status == 200`, `len(body) == 5000`. `max_bytes=1000`이면 `len(body) == 1000` |
| `test_sends_only_fixed_headers` | 서버가 받은 헤더 이름(소문자) ⊆ `{"host", "accept", "user-agent", "connection"}`, `accept == "application/json"`, `user-agent == "ClimateNote-UpdateCheck"` |
| `test_redirect_is_returned_not_followed` | `/redirect`: `status == 302`, 서버가 받은 경로 `== ["/redirect"]` |
| `test_cookies_are_not_stored_or_sent` | `/cookie`를 두 번: 둘째 요청 헤더에 `cookie` 없음 |
| `test_proxy_auth_required_is_just_a_status` | `/407`: `status == 407`, 서버 요청 1번 |
| `test_slow_server_times_out` | `/slow`, `timeout_seconds=1`: `WinHttpError`, `timed_out is True` |
| `test_dripping_body_hits_total_deadline` | `/drip`, `timeout_seconds=1`: `WinHttpError`, `timed_out is True`, 걸린 시간 6초 미만 |
| `test_closed_port_is_connection_error` | 닫힌 포트: `WinHttpError`, `timed_out is False` |
| `test_closed_proxy_is_connection_error` | `proxy="127.0.0.1:9"`: `WinHttpError`, `timed_out is False`, 서버 요청 0번 |
| `test_self_signed_https_server_is_rejected` | 시험 중에 `cryptography.x509`로 만든 자체 서명 인증서의 로컬 HTTPS 서버에 `https_get(f"https://127.0.0.1:{port}/ok", **ARGS)`: `WinHttpError`, `timed_out is False`, 서버가 받은 요청 0번 |
| `test_public_function_refuses_anything_but_https` | `https_get("http://127.0.0.1/", **ARGS)`와 `"ftp://x/"`, `"//x/"`: `ValueError`, 통신 없음(`_get`을 '불리면 실패'로 바꿔 둔다) |
| `test_header_with_line_break_is_refused` | `headers={"Accept": "a\r\nX: y"}`: `ValueError` |
| `test_handles_are_closed_on_success_and_failure` | `_close_handle`을 세는 래퍼로 바꿔: 성공 3번, 닫힌 포트 실패 3번 |
| `test_tls_floor_tries_1_3_then_falls_back_to_1_2_only` | 첫 호출을 거절하는 가짜 `set_option`: 넘어온 값 `== [0x2800, 0x0800]` |
| `test_missing_dll_is_oserror` | `_library`가 `OSError`를 내면 `_get`도 `OSError` |
| `test_source_never_relaxes_certificate_checks` | 모듈 소스에 `SECURITY_FLAG`, `OPTION_SECURITY_FLAGS`, `REVOCATION`, `PySide6`, `import database`, `import ssl`이 없다 |

- [ ] **Step 2: 실패를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_winhttp_get.py -q` → 모듈 없음

- [ ] **Step 3: 구현한다**

`https_get`: `urllib.parse.urlsplit`로 나눠 스킴이 `https`가 아니거나 호스트가 없으면 `ValueError`, 포트 기본 443, 경로+쿼리를 넘겨 `_get(secure=True)`. `_get`의 순서: 헤더 검사(CR·LF 거부) → `WinHttpOpen`(프록시 없으면 NO_PROXY, 있으면 NAMED_PROXY) → `secure`면 `_set_tls_floor` → `WinHttpSetTimeouts`(네 값 모두 `timeout_seconds`) → `WinHttpConnect` → `WinHttpOpenRequest`("GET", `secure`면 SECURE 플래그) → DISABLE_FEATURE에 COOKIES|REDIRECTS|AUTHENTICATION → `WinHttpSendRequest` → `WinHttpReceiveResponse` → 상태 코드 조회 → `max_bytes`에 닿거나 0바이트가 올 때까지 `WinHttpReadData`. 보내기·받기·읽기마다 그 전에 전체 상한을 본다(넘으면 `WinHttpError(12002, timed_out=True)`). WinHTTP 호출 실패는 `WinHttpError(ctypes.get_last_error(), timed_out=<12002인지>)`. 핸들 셋은 `try/finally`에서 `_close_handle`로 닫는다.

상수(값은 Microsoft 문서의 `winhttp.h`와 대조하고 주석에 출처를 남긴다): `WINHTTP_ACCESS_TYPE_NO_PROXY 1`, `WINHTTP_ACCESS_TYPE_NAMED_PROXY 3`, `WINHTTP_FLAG_SECURE 0x00800000`, `WINHTTP_OPTION_DISABLE_FEATURE 63`(`COOKIES 1`, `REDIRECTS 2`, `AUTHENTICATION 4`), `WINHTTP_OPTION_SECURE_PROTOCOLS 84`(`TLS1_2 0x0800`, `TLS1_3 0x2000`), `WINHTTP_QUERY_STATUS_CODE 19 | WINHTTP_QUERY_FLAG_NUMBER 0x20000000`, `ERROR_WINHTTP_TIMEOUT 12002`. 함수마다 `argtypes`·`restype`를 선언한다(핸들은 `c_void_p`. `tools/smoke_release.py`의 `ProcessJob`이 같은 방식이다).

- [ ] **Step 4: 통과를 확인한다** — 같은 명령, 전부 통과. 대조한 문서 주소를 작업 기록에 적는다.

- [ ] **Step 5: 커밋** — `git add src/winhttp_get.py tests/test_winhttp_get.py` / `feat: WinHTTP로 HTTPS GET 한 번을 보내는 통신 층`

### Task 4: 새 버전 확인을 새 통신 층으로 옮긴다

**Files:**
- Modify: `src/update_check.py`
- Modify: `tools/dev_update_check_preview.py:70`, `tests/test_ui_update_check.py`(25·66·246행 근처), `tests/test_ui_update_main.py:22`
- Test: `tests/test_update_check.py`

**Interfaces:**
- Consumes: `winhttp_get.https_get`, `winhttp_get.Response`, `winhttp_get.WinHttpError`
- Produces: `update_check.proxy_for(host: str) -> str | None`(쓸 수 없는 주소면 `ValueError`), `update_check.check_latest(fetch=None) -> CheckResult`. `fetch`는 `https_get`과 같은 모양이고 `None`이면 **부를 때** `winhttp_get.https_get`을 찾는다. `https_only_opener`는 없어진다.

- [ ] **Step 1: `tests/test_update_check.py`를 고친다**

판정·`read_result` 시험은 그대로 둔다. `FakeOpener`를 `FakeFetch(response=None, error=None)`(호출 인자를 `calls`에 기록)로 바꾸고 `ssl`·`http.client`·`urllib.error` import를 없앤다.

```python
def test_request_carries_only_fixed_values(monkeypatch):
    monkeypatch.setattr(update_check, "proxy_for", lambda host: None)
    fetch = FakeFetch(Response(200, OK_BODY))
    assert check_latest(fetch) == CheckResult(latest_tag="v4.7")
    assert fetch.calls == [((RELEASES_URL,), dict(
        headers={"Accept": "application/json"}, user_agent="ClimateNote-UpdateCheck",
        timeout_seconds=10, max_bytes=256 * 1024 + 1, proxy=None))]


@pytest.mark.parametrize(("outcome", "failure"), [
    (Response(302, b""), "http-302"), (Response(404, b""), "http-404"),
    (Response(407, b""), "http-407"), (Response(503, b""), "http-503"),
    (Response(204, b""), "format"),
    (WinHttpError(12002, timed_out=True), "timeout"), (TimeoutError(), "timeout"),
    (WinHttpError(12029), "connection"), (WinHttpError(12175), "connection"),
    (OSError("winhttp.dll"), "connection"), (ValueError("bad"), "connection")])
def test_every_outcome_is_classified_not_raised(monkeypatch, outcome, failure): ...


@pytest.mark.parametrize(("proxies", "bypass", "expected"), [
    ({}, False, None), ({"http": "http://p.invalid:8080"}, False, None),
    ({"https": "http://p.invalid:8080"}, False, "p.invalid:8080"),
    ({"https": "p.invalid:8080"}, False, "p.invalid:8080"),
    ({"https": "https://p.invalid:8080/"}, False, "p.invalid:8080"),
    ({"https": "http://p.invalid"}, False, "p.invalid"),
    ({"https": "http://p.invalid:8080"}, True, None)])
def test_proxy_is_read_the_way_urllib_reads_it(monkeypatch, proxies, bypass, expected): ...
    # urllib.request.getproxies / proxy_bypass를 바꿔 끼우고 proxy_for("gitlab.aigov.go.kr") == expected


@pytest.mark.parametrize("address", ["http://user:pw@p.invalid:8080", "http://:8080", "http://"])
def test_unusable_proxy_address_is_refused(monkeypatch, address): ...   # proxy_for가 ValueError


def test_refused_proxy_means_connection_failure_without_a_request(monkeypatch): ...
    # proxy_for가 ValueError → check_latest(fetch) == CheckResult(failure="connection"), fetch.calls == []
```

크기 상한 시험(256KiB 딱 맞음은 정상, 1바이트 넘으면 `format`)과 '통신 층을 찾다가 난 예외도 `connection`' 시험은 새 가짜로 옮긴다. 소스 시험은 `PySide6`, `import database`, `import ssl`, `http.client`가 없음을 본다.

- [ ] **Step 2: 실패를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_update_check.py -q`

- [ ] **Step 3: `update_check.py`를 고친다**

`import http.client`·`import ssl`·`import urllib.error`와 `https_only_opener`를 없애고 `import winhttp_get`·`import urllib.parse`를 모듈 맨 위에 둔다(`urllib.request`는 남는다). `proxy_for`는 `urllib.request.getproxies().get("https")`가 없거나 `urllib.request.proxy_bypass(host)`면 `None`, 아니면 스킴이 없을 때 `//`를 붙여 `urlsplit`하고 사용자 정보가 있거나 호스트가 없으면 `ValueError`, 포트가 있으면 `호스트:포트` 없으면 호스트. `check_latest`는 `proxy_for`와 `fetch`를 한 `try` 안에서 부르고 `WinHttpError.timed_out`·`TimeoutError` → `timeout`, 나머지 `OSError`·`ValueError` → `connection`, 상태가 200~299가 아니면 `http-<코드>`, 본문이 `MAX_RESPONSE_BYTES`를 넘으면 `format`, 그 밖에는 `read_result`. 모듈 docstring의 'urllib.request·ssl은 일부러…' 문단을 새 구성으로 고친다(EXE에서 모듈이 빠지면 시작 때 드러나야 한다는 이유는 남긴다).

- [ ] **Step 4: 따라가는 곳을 고친다**

`tools/dev_update_check_preview.py:70`과 `tests/test_ui_update_main.py:22`의 `lambda opener=None`을 `lambda fetch=None`으로, `tests/test_ui_update_check.py`의 가짜 `fake(opener=None)`을 `fake(fetch=None)`으로 바꾼다. `test_off_means_no_request_at_all`은 `monkeypatch.setattr(update_check.winhttp_get, "https_get", forbidden)`(`forbidden(*args, **kwargs)`)으로 바꿔 꺼진 PC에서 통신 층이 불리지 않음을 계속 단언한다.

- [ ] **Step 5: 통과를 확인한다**

Run: `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_update_check.py tests/test_winhttp_get.py tests/test_ui_update_check.py tests/test_ui_update_main.py tests/test_source_layout.py`
Expected: `passed`. 실행 ID를 작업 기록에 적는다.

- [ ] **Step 6: 커밋** — 고친 파일 여섯 개를 지정 / `feat: 새 버전 확인의 통신을 WinHTTP로 교체(ssl 사용 제거)`

### Task 5: 빌드에서 OpenSSL을 뺀다

**Files:**
- Modify: `build_app.py`, `build.spec`(11행 import, 66행 excludes, 142행 뒤)
- Test: `tests/test_packaging.py`(242행 `_spec_analysis`, 260행)

**Interfaces:**
- Produces: `build_app.OPENSSL_FILE_NAMES = frozenset({"libcrypto-3.dll", "libssl-3.dll", "_ssl.pyd", "_hashlib.pyd", "qopensslbackend.dll"})`, `build_app.without_openssl(entries: list[tuple]) -> list[tuple]`(항목 첫 칸의 파일 이름을 `\`·`/` 뒤에서 잘라 소문자로 비교해 다섯 파일만 뺀다. 순서 유지)

- [ ] **Step 1: 테스트를 쓴다**

```python
def test_build_spec_keeps_modules_update_check_needs(tmp_path):
    # urllib.request(프록시 읽기)는 http.client·email을, winhttp_get은 ctypes를 쓴다.
    assert not {"http", "email", "urllib", "socket", "ctypes"} & set(_spec_analysis(tmp_path)["excludes"])


def test_build_spec_excludes_python_openssl_modules(tmp_path):
    assert {"ssl", "_ssl", "_hashlib"} <= set(_spec_analysis(tmp_path)["excludes"])


def test_without_openssl_drops_only_the_five_files():
    keep = [("PySide6\\plugins\\tls\\qschannelbackend.dll", "a", "BINARY"), ("python313.dll", "b", "BINARY"),
            ("cryptography\\hazmat\\bindings\\_rust.pyd", "c", "EXTENSION")]
    drop = [("PySide6\\plugins\\tls\\qopensslbackend.dll", "d", "BINARY"), ("LIBCRYPTO-3.DLL", "e", "BINARY"),
            ("libssl-3.dll", "f", "BINARY"), ("_ssl.pyd", "g", "EXTENSION"), ("lib/_hashlib.pyd", "h", "EXTENSION")]
    assert without_openssl(keep[:1] + drop + keep[1:]) == keep


def test_build_spec_filters_openssl_binaries_before_packing(tmp_path):
    binaries = [("python313.dll", "b", "BINARY"), ("PySide6\\plugins\\tls\\qopensslbackend.dll", "d", "BINARY")]
    assert _spec_analysis(tmp_path, binaries=binaries)["exe_args"][2] == binaries[:1]


def test_app_code_avoids_openssl_only_hashlib_calls():
    # OpenSSL이 없는 EXE에는 pbkdf2_hmac·scrypt가 없고 hashlib.new는 일부 이름만 된다.
    ...  # src/*.py와 screen_text/*.py의 AST에서 hashlib.pbkdf2_hmac / .scrypt / .new 속성 접근과
         # `from hashlib import` 그 세 이름이 0건
```

`_spec_analysis(spec_dir, binaries=())`는 가짜 `Analysis`가 `binaries=list(binaries)`를 돌려주고 가짜 `EXE`가 받은 위치 인자를 `captured["exe_args"]`에 담도록 넓힌다.

- [ ] **Step 2: 실패를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_packaging.py -q`

- [ ] **Step 3: 구현한다**

`build.spec`: excludes에 `'ssl', '_ssl', '_hashlib'`를 넣고 주석으로 '배포 EXE에는 Python용 OpenSSL이 없다. 새 버전 확인은 winhttp_get(WinHTTP), 해시는 내장 구현' 이유를 남긴다. `Analysis(...)` 바로 뒤에 `a.binaries = without_openssl(a.binaries)`. 기존 `test_build_spec_keeps_every_module_the_app_imports`가 통과해야 한다(앱 코드에 `import ssl`이 남아 있으면 여기서 걸린다).

- [ ] **Step 4: 통과를 확인한다** — 같은 명령, 전부 통과

- [ ] **Step 5: 커밋** — `git add build_app.py build.spec tests/test_packaging.py` / `build: EXE에서 Python용 OpenSSL과 Qt OpenSSL 연결 플러그인 제외`

### Task 6: release가 이번 EXE에서 OpenSSL이 없음을 확인한다

**Files:**
- Modify: `tools/verify.py`(`bundle_check` 아래, `save_report` 311행 근처, `execute` 581행 근처), `tools/smoke_release.py`(32·36·547행 근처)
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `build_app.OPENSSL_FILE_NAMES`
- Produces:

```python
OPENSSL_FILE = re.compile(r"(?i)^(?:(?:libcrypto|libssl)[-\w.]*\.dll|_ssl\.[-\w.]*pyd|_hashlib\.[-\w.]*pyd|qopensslbackend\.dll)$")
OPENSSL_BANNER_ALLOWED = ("cryptography/hazmat/bindings/_rust.pyd",)
def find_openssl_banners(data: bytes) -> list[str]     # "OpenSSL 3.5.4"처럼 정렬·중복 제거. ASCII와 UTF-16LE 모두
def _embedded_archive(exe) -> tuple[list[str], Callable[[str], bytes]]   # EXE 안 파일 이름들과 읽는 함수
def openssl_check(toc_path, exe) -> dict   # {"files": [], "scanned": int, "banners": [{"name", "found"}], "upx_packed": [..]}
```

- [ ] **Step 1: 테스트를 쓴다**

| 테스트 | 단언 |
|---|---|
| `test_find_openssl_banners_reads_ascii_and_utf16` | `b"..OpenSSL 3.0.16 11 Feb 2025.."` → `["OpenSSL 3.0.16"]`, `"OpenSSL 3.5.4 30 Sep 2025".encode("utf-16-le")`가 든 바이트 → `["OpenSSL 3.5.4"]`, 둘 다 들면 정렬된 두 개, `b"OpenSSL backend"` → `[]` |
| `test_find_openssl_banners_on_installed_binaries` | venv의 `PySide6/plugins/tls/qopensslbackend.dll`과 `cryptography/hazmat/bindings/_rust.pyd`, 기본 Python의 `DLLs/libcrypto-3.dll`·`DLLs/_hashlib.pyd` 각각 결과가 비어 있지 않다(파일이 없으면 그 항목만 skip) |
| `test_build_filter_names_all_match_the_release_pattern` | `all(verify.OPENSSL_FILE.match(name) for name in build_app.OPENSSL_FILE_NAMES)`, `libcrypto-3-x64.dll`·`_ssl.cp313-win_amd64.pyd`도 맞고 `qschannelbackend.dll`·`_sqlite3.pyd`는 안 맞는다 |
| `test_openssl_check_accepts_exe_with_only_the_cryptography_copy` | TOC·EXE에 다섯 파일이 없고 `_rust.pyd`에만 표시 → `files == []`, `banners == [{"name": "cryptography/hazmat/bindings/_rust.pyd", "found": ["OpenSSL 4.0.1"]}]` |
| `test_openssl_check_rejects_openssl_file_in_toc` | TOC에 `("_ssl.pyd", …, "EXTENSION")` → `VerificationFailure`, 메시지에 `_ssl.pyd` |
| `test_openssl_check_rejects_openssl_file_inside_exe` | EXE 목록에 `PySide6\plugins\tls\qopensslbackend.dll` → `VerificationFailure` |
| `test_openssl_check_rejects_banner_outside_allowed_file` | 다른 dll에 UTF-16 표시 → `VerificationFailure`, 메시지에 파일 이름과 `OpenSSL 3.5.4` |

`_embedded_archive`는 기존 `_embedded_reader`처럼 `monkeypatch`로 바꿔 끼운다. `execute`·`save_report` 시험은 `app_modules`를 다루는 기존 시험 옆에 같은 방식으로: `release`가 `report["bundle"]["openssl"]`을 채우고 `summary.md`에 한 줄이 생긴다.

- [ ] **Step 2: 실패를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_verify.py -q`

- [ ] **Step 3: 구현한다**

`openssl_check`: TOC의 모든 종류(BINARY·EXTENSION 등) 항목과 EXE 안 파일 이름에서 파일 이름이 `OPENSSL_FILE`에 맞는 것을 모아 하나라도 있으면 `VerificationFailure("EXE에 OpenSSL 파일 포함: …")`. 이어서 EXE 안 `.dll`·`.pyd`를 모두 읽어 `find_openssl_banners`를 적용하고, 이름(슬래시로 통일)이 `OPENSSL_BANNER_ALLOWED`로 끝나지 않는데 표시가 있으면 `VerificationFailure("허용하지 않은 OpenSSL 버전 표시: …")`. 앞 4KiB 안에 `b"UPX!"`가 있는 파일 이름은 `upx_packed`에 적는다. `execute`는 `bundle_check` 바로 뒤에 `report["bundle"]["openssl"] = openssl_check(analysis[0], exe)`. `save_report`는 `- OpenSSL: Python용·Qt 연결 파일 없음, 버전 표시 <파일>(<표시>)뿐` 한 줄.

`tools/smoke_release.py`: 32행 근처 주석과 `update_check_scenario` docstring의 'http·ssl 모듈까지 EXE에서 돈다'를 'WinHTTP 통신 층까지 EXE에서 돈다'로 고치고, `UPDATE_CHECK_LIVE_SECONDS = 105`(첫 확인 60초 + 전체 상한 30초 + 마지막 읽기 10초 + 여유).

- [ ] **Step 4: 통과를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_verify.py tests/test_release_smoke.py -q`

- [ ] **Step 5: 커밋** — `git add tools/verify.py tools/smoke_release.py tests/test_verify.py` / `feat: release가 EXE의 OpenSSL 파일·버전 표시를 직접 확인`

### Task 7: 라이선스 고지에서 OpenSSL 3.0.16을 걷어낸다

**Files:**
- Modify: `licenses/components.json`(237~251행), `licenses/NATIVE-NOTICE.txt`(8~13행), `licenses/ORIGINS.json`(62~71행)
- Delete: `licenses/OpenSSL-3.0.16-AUTHORS.txt`
- Test: `tests/test_ui_licenses.py`

- [ ] **Step 1: 테스트를 쓴다**

```python
def test_openssl_notice_covers_only_the_copy_inside_cryptography():
    entries = {entry["id"]: entry for entry in json.loads((ROOT / "licenses/components.json").read_text(encoding="utf-8"))}
    assert entries["openssl"]["version"] == "4.0.1"
    assert entries["openssl"]["files"] == ["licenses/OpenSSL-LICENSE.txt", "licenses/OpenSSL-4.0.1-AUTHORS.txt"]
    assert entries["python"]["version"] == "3.13.5"  # Python 자체의 고지는 그대로다
    for name in ("components.json", "NATIVE-NOTICE.txt", "ORIGINS.json"):
        assert "3.0.16" not in (ROOT / "licenses" / name).read_text(encoding="utf-8")
    assert not (ROOT / "licenses/OpenSSL-3.0.16-AUTHORS.txt").exists()
```

- [ ] **Step 2: 실패를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_ui_licenses.py -q`

- [ ] **Step 3: 고친다**

- `components.json`의 `openssl`: `version` `"4.0.1"`, `description` `"cryptography 내부에 정적으로 포함된 구성입니다."`, `sources`는 4.0.1 주소 하나, `files`는 위 둘.
- `NATIVE-NOTICE.txt`: 8행과 12행을 지우고 10~11행을 `Copyright (c) The OpenSSL Project Authors. AUTHORS와 Apache-2.0 전문을 함께 제공합니다.`로 고친다.
- `ORIGINS.json`: `OpenSSL-3.0.16-AUTHORS.txt` 기록을 지우고 `OpenSSL-LICENSE.txt`의 `source`를 `https://raw.githubusercontent.com/openssl/openssl/openssl-4.0.1/LICENSE.txt`로 바꾼다(`sha256`은 그대로. 두 버전의 원문이 같다고 기록돼 있다).
- `git rm licenses/OpenSSL-3.0.16-AUTHORS.txt`

- [ ] **Step 4: 통과를 확인한다** — `.\.venv\Scripts\python.exe -m pytest tests/test_ui_licenses.py tests/test_packaging.py -q`

- [ ] **Step 5: 커밋** — 고친 파일 넷을 지정 / `docs: 라이선스 고지에서 EXE에 없는 OpenSSL 3.0.16 표기 제거`

### Task 8: 지침과 문서

**Files:**
- Modify: `AGENTS.md`, `docs/ARCHITECTURE.md`(143행 근처·모듈 표), `docs/CODING_STANDARDS.md`(229행), `docs/TESTING.md`(62·198행 근처), `docs/superpowers/specs/2026-11-04-update-check-design.md`(8절)

- [ ] **Step 1: `AGENTS.md`**

- '명령' 절, excludes 항목 뒤에 새 항목: 배포 EXE에는 Python용 OpenSSL이 없다(v4.9). `build.spec`이 `ssl`·`_ssl`·`_hashlib`를 빼고 `build_app.without_openssl`이 `qopensslbackend.dll`까지 다섯 파일을 거른다. 앱 코드에서 `ssl`과 `hashlib.pbkdf2_hmac`·`scrypt`·`new`를 쓰지 않는다(`hashlib.sha256`은 내장 구현이 같은 값을 낸다). `test_packaging.py`가 막고 `release`의 `openssl_check`가 EXE의 파일과 버전 표시(ASCII·UTF-16)를 확인하며, `cryptography`의 `_rust.pyd`만 표시를 가질 수 있다. `data`·`release`는 데이터 검사를 OpenSSL을 막은 프로세스(`tools/run_without_openssl.py`)로 한 번 더 돌린다. 설계 문서 링크.
- 새 버전 알림(v4.7) 문단의 요청 문장 뒤에: v4.9부터 통신은 `winhttp_get.py`가 Windows WinHTTP로 한다. '요청 한 번'은 앱이 보내는 요청이고 Windows가 인증서 확인을 위해 스스로 하는 통신은 별개다. 프록시는 `urllib.request.getproxies()`·`proxy_bypass()`로 읽고 주소의 사용자 정보는 지원하지 않는다.
- '현재 v4.9는…' 줄의 'v4.8·v4.9는 화면 글자 따기만 고쳐 설정 키도 늘지 않았다'를 v4.9가 새 버전 확인의 통신 층과 EXE 구성도 바꿨고 설정 키는 늘지 않았다는 내용으로 고친다.

- [ ] **Step 2: 나머지 문서**

- `docs/ARCHITECTURE.md`: `update_check.py` 줄을 '태그 해석·비교, 응답 해석, 프록시 결정, 고정 주소 요청 1회(통신은 `winhttp_get`)'로, 새 줄 `winhttp_get.py`('WinHTTP로 HTTPS GET 한 번. TLS 1.2 이상, 인증서 검증은 Windows, 리디렉션·쿠키·자동 인증 없음. Qt·DB 없음').
- `docs/CODING_STANDARDS.md` 229행: '그 경우의 새 버전 확인도 같은 opener 규칙을 따른다' 문장을 '새 버전 확인(`src/update_check.py`)은 `src/winhttp_get.py`의 `https_get`만 쓴다. 배포 EXE에는 `ssl`이 없으므로 앱 코드에서 `urllib`로 HTTPS를 열지 않는다'로 바꾼다. `fetch_data.py` 규칙은 그대로 둔다.
- `docs/TESTING.md`: `data`·`release` 설명에 `pytest-no-openssl` 단계, release 설명에 `openssl_check`, 198행의 근거 문장('http·ssl' → 'WinHTTP 통신 층'), `--live-update-check` 시간(105초), `tools/exe_handoff_check.py` 사용법 한 줄.
- 새 버전 알림 설계 8절 맨 위에 '통신 구현은 2026-11-10 설계로 바뀌었다' 한 줄과 링크.

- [ ] **Step 3: 링크와 사실을 확인한다** — 고친 문서의 상대 링크가 열리는지, 함수·파일 이름이 코드와 같은지 `Grep`으로 대조한다.

- [ ] **Step 4: 커밋** — 고친 문서 다섯을 지정 / `docs: OpenSSL 없는 EXE와 WinHTTP 통신 계약 반영`

### Task 9: 실제 EXE 증거

**Files:**
- Create: `tools/exe_handoff_check.py`
- Modify: `docs/work/2026-11-10-openssl-free-exe.md`

**Interfaces:**
- Consumes: `tools/smoke_release.py`의 `managed_launch`, `windows_in_job`, `data_env`, `data_step`, `_check_existing`, `validate_paths`; `tools/verify.py`의 `create_run_dir`, `file_hash`, `write_json`
- Produces: `.\.venv\Scripts\python.exe tools/exe_handoff_check.py --old <옛 EXE> --new <새 EXE>` — 새 하네스 실행 폴더를 만들고 두 EXE를 `<실행 폴더>/dist/old/`·`dist/new/`로 복사한 뒤, 합성 데이터를 한 번 `seed`하고 옛 → 새 → 옛 순으로 띄운다. 매번 본 창(폭 350·높이 450 이상, 응답함)이 뜨고 '데이터 보호를 위해 실행을 중단했습니다' 창이 없음을 본 뒤 3초 더 두고 닫고, `data_step("inspect", …)` 결과를 `_check_existing(seed 결과, 결과)`로 대조한다. `<실행 폴더>/handoff.json`에 EXE별 SHA-256·걸린 시간·상태를 남기고 종료 코드 0/1.

- [ ] **Step 1: 교대 실행 도구를 쓰고 도구 자체를 확인한다**

Run: `.\.venv\Scripts\python.exe tools/exe_handoff_check.py --old dist\기후노트_v4.8.exe --new dist\기후노트_v4.8.exe`
Expected: 종료 코드 0(같은 EXE 셋이면 반드시 통과해야 도구가 맞다). `dist\기후노트_v4.8.exe`의 SHA-256이 `docs/RELEASE_HISTORY.md`의 v4.8 값과 같은지 먼저 본다.

- [ ] **Step 2: 전체 검사** — `.\.venv\Scripts\python.exe tools/verify.py full` → `passed`

- [ ] **Step 3: PowerShell에서 release**

Run: `.\.venv\Scripts\python.exe tools/verify.py release`
Expected: `passed`. `summary.md`에서 확인할 것: `pytest`·`pytest-no-openssl`·`build`·`smoke` 모두 passed, 'OpenSSL: …' 줄의 버전 표시가 `_rust.pyd`뿐, 격리 실행 7개 시나리오(신규·기존·차단·v17·v18·새 버전 확인·글자 따기) 통과. 하나라도 실패하면 고치고 관련 검사를 다시 돌린다. 기존·업그레이드 시나리오가 '시작이 차단됐다'로 실패하면 **멈춘다**(열쇠가 달라졌다는 뜻이다).

- [ ] **Step 4: v4.8 EXE와 교대 실행**

Run: `.\.venv\Scripts\python.exe tools/exe_handoff_check.py --old dist\기후노트_v4.8.exe --new output\harness\<release 실행 ID>\dist\기후노트_v4.9.exe`
Expected: 종료 코드 0. 실패하면 **멈춘다**.

- [ ] **Step 5: 실제 TLS** (인터넷이 되는 이 PC에서)

Run: `.\.venv\Scripts\python.exe tools/smoke_release.py --exe output\harness\<release 실행 ID>\dist\기후노트_v4.9.exe --run-dir output\harness\<release 실행 ID> --live-update-check`
Expected: `{"status": "passed", "live": true, "log_line": ""}`. 실패 기록이 남으면 `error.log`의 분류를 작업 기록에 적고 원인을 가른다(이 PC의 망 문제인지 통신 층 문제인지).

- [ ] **Step 6: 숫자를 잰다**

- EXE 크기: v4.8 94,876,233바이트 대비.
- SHA-256이 느려진 영향: `screen_text/models`의 MANIFEST 확인에 드는 시간과 `database._file_size_and_sha256`(합성 DB 사본)의 시간을 보통 Python과 `tools/run_without_openssl.py` 방식으로 막은 Python에서 각각 잰다.
- 시작 시간: 이번 `smoke.json`의 시나리오별 `seconds`를 직전 release 실행 `20261110-163232-57989df8e8`과 견준다.

- [ ] **Step 7: 작업 기록을 채우고 커밋한다**

검증 증거 표에 실행 ID 넷(`data`, `full`, `release`, 교대 실행)과 실제 TLS 결과, Step 6의 숫자, 남은 수동 확인(인터넷 PC에서 스위치를 켠 실제 알림, 기존 데이터로 새 EXE 첫 실행)을 적는다. 릴리스 이력은 v4.9를 마무리할 때 적는다.

`git add tools/exe_handoff_check.py docs/work/2026-11-10-openssl-free-exe.md` / `test: v4.8 EXE와 OpenSSL 없는 EXE의 교대 실행 증거 도구와 검증 기록`
