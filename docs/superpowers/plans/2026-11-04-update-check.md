# 새 버전 알림(인터넷 접속을 켠 PC만) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설정에서 '인터넷 접속'을 켠 PC만 GitLab 공개 Release에서 최신 버전 번호를 받아, 새 버전이 있으면 알림 한 번·빨간 점·앱 업데이트 창 강조로 알린다.

**Architecture:** 판정·네트워크는 Qt·DB 없는 `src/update_check.py`, 예약·스레드는 `src/ui_update_check.py`의 `UpdateCheckController`, 화면(점·알림·강조)은 기존 `src/ui_update.py`에 둔다. 메인 창은 컨트롤러의 `latestChanged` 신호만 받아 표시를 맞춘다. 요청은 데몬 스레드 하나에서 돌고, GUI는 결과 큐를 폴링한다(`ui_sticky_links`와 같은 방식).

**Tech Stack:** Python 3.13, PySide6, qfluentwidgets, urllib(전용 `OpenerDirector`), pytest-qt

**Spec:** [`docs/superpowers/specs/2026-11-04-update-check-design.md`](../specs/2026-11-04-update-check-design.md) — 화면 수치는 §5, 시안은 Claude Design 캔버스 '새 버전 알림' 쪽

**브랜치:** `feature/update-check`(main의 8adb285에서 분기). push는 이 계획 범위가 아니다.

## Global Constraints

- 데이터: 새 키 `internet_access_enabled`(`"1"`/`"0"`)만 추가하고 마이그레이션에 넣지 않는다. DB v19·Export v4·salt·암호문·기존 키는 그대로다.
- 키가 없거나 `"1"`이 아니면 꺼짐이다. 꺼진 PC에서는 요청이 한 번도 나가지 않는다.
- 주소(고정): `https://gitlab.aigov.go.kr/api/v4/projects/647/releases?per_page=1&order_by=released_at&sort=desc`
- 요청: GET, 헤더는 `Accept: application/json`과 `User-Agent: ClimateNote-UpdateCheck`만, 시간 제한 10초, 응답은 최대 256KiB(`256 * 1024`). `tag_name` 외 필드는 `upcoming_release`만 읽는다.
- opener: `OpenerDirector`에 ProxyHandler(https만)·UnknownHandler·HTTPSHandler(`ssl.create_default_context()`)·HTTPDefaultErrorHandler·HTTPErrorProcessor만 넣는다. 리디렉션 처리기 금지.
- Semgrep 대응: `OpenerDirector()` 생성과 `.open()` 호출은 `fetch_data.py`처럼 **다른 함수**에 둔다. `urlopen` 호출·`http.client` 연결·`nosemgrep` 금지. 주석에도 `urlopen(` 문자열을 쓰지 않는다(`tests/test_security_scan_rules.py`가 문자열로 찾는다).
- 실패는 화면에 보이지 않는다. 로그는 `logging.getLogger("app_error").error()`로 분류만 남긴다(이 로거는 `main.py`에서 ERROR 수준이라 `.warning()`은 버려진다). 주소·프록시 값은 로그에 넣지 않는다.
- 내려받기는 브라우저로 `ui_update.GITLAB_LATEST_URL`을 여는 것뿐이다. 브라우저 열기는 스위치와 무관하다.
- 색: 빨간 점 `#F04438`, 강조 `#2563EB`/`#1D4ED8`, 연한 파랑 `#DFE8FD`, 제목 `#0F1E36`, 본문 `#1F2A3D`, 보조 `#5B6678`, 머리줄 기본 `#01295F`(코드에서는 `ui_main.NAVY`).
- 움직임은 `ui_holiday_decor.motion_allowed()`가 True일 때만이고 초당 30회 이하다.
- 잠금 중에는 알림을 띄우지 않고, 잠금 화면 위에 점·알림이 보이지 않는다.
- 설정창은 800×560 무스크롤이다(`layout().minimumSize().height() ≤ 560`).
- 알림은 앱 실행당 한 번이다. 확인 시각·발견 버전·표시 여부는 메모리 전용이다.
- 앱 코드: 새 모듈은 `src/`에 두고 `import update_check`처럼 이름으로 import한다(`src.` 접두 금지). QSS 글꼴은 정수 px. `bare except`와 이유 없는 `except/pass` 금지.
- 배포 EXE에 버전을 바꾸는 옵션·환경 변수를 두지 않는다. 개발 도구는 `tools/`에만 둔다.
- 테스트는 실제 네트워크를 쓰지 않고 합성 데이터(`app_dir`)만 쓴다. `release`는 PowerShell에서만 실행한다.

## Review Focus

- **비정상 응답·환경**: 깊게 중첩된 JSON(`[` 20만 개), 수천 자리 숫자 태그, 유니코드 숫자, 프록시 주소 오타 → 예외가 스레드 밖으로 나가지 않고 실패나 '새 버전 없음'이 된다. (Task 1)
- **저장 실패한 스위치**: '끄기' 저장이 실패했는데 화면만 꺼지면 요청이 계속 나간다 → 스위치를 되돌려 알리고, 요청 직전에 키를 다시 읽는다. (Task 2·3)
- **열린 설정창에서 초기화**: 창이 열린 채 초기화하면 스위치가 켜짐으로 남는다 → 꺼짐으로 맞춘다. (Task 2)
- **오래 켜 둔 앱의 상태 변화**: 망이 끊겨도 점은 남고, 더 새 버전이면 꼬리표만 바뀌고(알림 재표시 없음), Release가 내려가면 점이 사라지고, 빠른 끔·켬에도 요청 스레드는 하나다. (Task 3·5)
- **좁은 창과 긴 태그**: 사이드바 없는 기본 크기(안내창 340px)에서 `v4.10a` → 타일 안내·꼬리표·알림 제목이 잘리지 않는다. (Task 5·6)

---

## 파일 지도

| 파일 | 책임 |
|---|---|
| `src/update_check.py` (새) | 태그 해석·비교, 응답 해석, HTTPS 전용 opener, 요청 1회. Qt·DB 없음 |
| `src/ui_update_check.py` (새) | `UpdateCheckController`: 키 읽기, 예약, 작업 스레드, 결과 반영 |
| `src/ui_update.py` | `UpdateDot`(②③), `UpdateToast`(①), 안내창 강조(④) |
| `src/ui_main.py` | 컨트롤러 소유, 표시 연결, 잠금·트레이·종료·초기화 연결 |
| `src/ui_settings.py`, `src/database.py` | ⑤ 스위치 줄, 키 상수와 Export 제외 |
| `build.spec` | `http`·`email`을 제외 목록에서 뺀다 |
| `tools/dev_update_check_preview.py` (새), `tools/smoke_release.py` | 개발 미리보기, EXE 확인 시나리오 |

---

### Task 1: 판정·네트워크 모듈과 EXE 포함

**Files:**
- Create: `src/update_check.py`, `tests/test_update_check.py`, `docs/work/2026-11-04-update-check.md`
- Modify: `build.spec`(excludes), `tests/test_packaging.py`

**Interfaces:**
- Consumes: 없음
- Produces (`update_check`):
  - 상수 `RELEASES_URL`, `USER_AGENT`, `TIMEOUT_SECONDS = 10`, `MAX_RESPONSE_BYTES = 256 * 1024`
  - `@dataclass(frozen=True) class CheckResult: latest_tag: str | None = None; failure: str | None = None` — `failure`가 None이면 응답을 정상으로 읽었다는 뜻이고, 이때 `latest_tag`가 None이면 '판단할 Release 없음'이다.
  - `parse_version(tag: object) -> tuple[int, int, str] | None`
  - `is_newer(tag: object, current: object) -> bool`
  - `read_result(body: bytes) -> CheckResult`
  - `https_only_opener() -> urllib.request.OpenerDirector`
  - `check_latest(opener=None) -> CheckResult` — 분류값 `"timeout"`, `"connection"`, `"http-<코드>"`, `"format"`

- [ ] **Step 1: 작업 기록 시작**

`docs/templates/WORK_NOTE.md`를 `docs/work/2026-11-04-update-check.md`로 복사해 목표·완료 조건을 적는다. '시작 시 사용자 변경'에 추적 안 되는 `docs/work/*`(17개)와 `motion/`을 적고 건드리지 않는다.

- [ ] **Step 2: 실패하는 테스트 작성** (`tests/test_update_check.py`)

```python
OK_BODY = json.dumps([{"tag_name": "v4.7", "upcoming_release": False}]).encode()

@pytest.mark.parametrize(("older", "newer"), [
    ("v4.6", "v4.7"), ("v4.6", "v4.6a"), ("v4.5a", "v4.6"), ("v4.9", "v4.10"), ("v4.6a", "v4.6b")])
def test_is_newer_orders_versions(older, newer):
    assert is_newer(newer, older) and not is_newer(older, newer) and not is_newer(older, older)

@pytest.mark.parametrize("bad", ["", "4.6", "v4", "v4.6.1", "v4.6A", "v4.6ab", "V4.6", "v4.6\n",
                                 "v٤.٦", "v" + "9" * 5000 + ".1", None, 46, ["v4.6"]])
def test_malformed_tag_is_never_newer(bad):
    assert parse_version(bad) is None
    assert not is_newer(bad, "v4.6") and not is_newer("v4.7", bad)

def test_reads_latest_tag():
    assert read_result(OK_BODY) == CheckResult(latest_tag="v4.7")

def test_empty_list_and_upcoming_are_not_failures():
    assert read_result(b"[]") == CheckResult()
    assert read_result(json.dumps([{"tag_name": "v9.9", "upcoming_release": True}]).encode()) == CheckResult()

@pytest.mark.parametrize("body", [b"", b"{", b"{}", b"null", b"[1]", b"[{}]", b'[{"tag_name": 5}]',
                                  b'[{"tag_name": "latest"}]', b"\xff\xfe\x00", b"[" * 200_000])
def test_bad_body_is_format_failure(body):
    assert read_result(body) == CheckResult(failure="format")
```

`check_latest`는 `open(request, timeout)`을 기록하고 `io.BytesIO(body)`를 돌려주거나 지정한 예외를 던지는 `FakeOpener(body=b"", error=None)`로 검사한다. `_http_error(code)`는 `HTTPError(RELEASES_URL, code, "x", {}, io.BytesIO())`다.

```python
def test_request_carries_only_fixed_headers():
    opener = FakeOpener(OK_BODY)
    assert check_latest(opener) == CheckResult(latest_tag="v4.7")
    request, timeout = opener.requests[0]
    assert request.full_url == RELEASES_URL and request.get_method() == "GET" and request.data is None
    assert dict(request.header_items()) == {"Accept": "application/json", "User-agent": "ClimateNote-UpdateCheck"}
    assert timeout == 10

def test_response_size_limit():
    limit = 256 * 1024
    assert check_latest(FakeOpener(OK_BODY + b" " * (limit - len(OK_BODY)))) == CheckResult(latest_tag="v4.7")
    assert check_latest(FakeOpener(OK_BODY + b" " * (limit + 1 - len(OK_BODY)))) == CheckResult(failure="format")

@pytest.mark.parametrize(("error", "failure"), [
    (_http_error(302), "http-302"), (_http_error(404), "http-404"), (_http_error(503), "http-503"),
    (TimeoutError(), "timeout"), (URLError(TimeoutError()), "timeout"), (URLError("refused"), "connection"),
    (ssl.SSLCertVerificationError("x"), "connection"), (http.client.RemoteDisconnected("x"), "connection"),
    (http.client.IncompleteRead(b""), "connection"), (ValueError("proxy URL with no authority"), "connection")])
def test_every_failure_is_classified_not_raised(error, failure):
    assert check_latest(FakeOpener(error=error)) == CheckResult(failure=failure)
```

opener는 `tests/test_fetch_data.py:73`처럼 `HTTPSHandler.https_open`을 가짜로 바꿔 실제 처리기 경로를 태운다.

- `test_opener_has_no_redirect_and_only_https_proxy`: `getproxies`가 https·http 프록시를 돌려줘도 `set(opener.handle_open) == {"https", "unknown"}`이고 `HTTPRedirectHandler` 인스턴스가 없다.
- `test_redirect_is_not_followed`: 가짜 전송이 `Location`을 단 302를 돌려줄 때 `check_latest() == CheckResult(failure="http-302")`이고 전송 호출이 `[RELEASES_URL]` 한 번뿐이다.
- `test_module_has_no_qt_or_db`: 소스에 `PySide6`, `import database`가 없다.

`tests/test_packaging.py`에 추가:

```python
def test_build_spec_keeps_modules_update_check_needs(tmp_path):
    # urllib.request는 http.client·email을 쓴다. 제외하면 빌드는 성공하고 EXE만 시작하지 못한다.
    assert not {"http", "email", "urllib", "ssl", "socket"} & set(_spec_analysis(tmp_path)["excludes"])
```

- [ ] **Step 3: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_update_check.py tests/test_packaging.py::test_build_spec_keeps_modules_update_check_needs -q`
Expected: `ModuleNotFoundError: No module named 'update_check'`로 수집 실패, packaging 테스트는 `{'http', 'email'}`로 실패

- [ ] **Step 4: `src/update_check.py` 구현, `build.spec`의 `'email'`·`'http'` 제거**

- 태그는 `re.fullmatch(r"v([0-9]{1,4})\.([0-9]{1,4})([a-z]?)", tag)`로만 받는다. `str`이 아니면 None. 자릿수 제한은 `int()`의 긴 숫자 `ValueError`를 막기 위해서다.
- `read_result`는 `json.loads`의 `(ValueError, RecursionError)`를 `format`으로 돌린다. `upcoming_release`를 `tag_name` 검사보다 먼저 본다.
- `check_latest`의 `except` 순서: `HTTPError`(닫은 뒤 `http-<코드>`, 자원 해제 규칙) → `URLError`(`reason`이 `TimeoutError`면 `timeout`, 아니면 `connection`) → `TimeoutError` → `(OSError, http.client.HTTPException, ValueError)`는 `connection`. opener 생성도 `try` 안에 둔다(인증서 저장소·프록시 오류). 본문은 `response.read(MAX_RESPONSE_BYTES + 1)`로 읽는다.
- `urllib.request`·`ssl`은 **모듈 맨 위에서** import한다. 지연 import하면 EXE에서 모듈이 빠져도 '조용한 실패'로 묻힌다. `ui_main`이 이 모듈을 시작 때 불러야 빠진 모듈이 EXE 시작 실패로 드러난다.
- `fetch_data.py`는 고치지 않는다(EXE에 들어가지 않고 `src`를 경로에 넣지 않는다).

- [ ] **Step 5: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_update_check.py tests/test_packaging.py tests/test_security_scan_rules.py -q`
Expected: 모두 통과

- [ ] **Step 6: Commit**

```bash
git add src/update_check.py tests/test_update_check.py tests/test_packaging.py build.spec docs/work/2026-11-04-update-check.md
git commit -m "feat: 새 버전 확인 판정·요청 모듈과 EXE 포함"
```

---

### Task 2: 설정 키와 ⑤ 인터넷 접속 줄

**Files:**
- Modify: `src/database.py:54-56`, `src/ui_settings.py`(`__init__`, `_add_row`, 시스템 묶음, `_on_reset`), `tests/test_database.py`(`:1532` 옆), `tests/test_ui_settings_holiday_theme.py:1-5,86-92`
- Create: `tests/test_ui_settings_internet_access.py`

**Interfaces:**
- Consumes: 없음
- Produces: `db.SETTING_INTERNET_ACCESS = "internet_access_enabled"`, `SettingsWindow(..., on_internet_access_changed=None)`, 위젯 `SettingsWindow.internet_switch`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_database.py`의 내보내기 묶음에 추가(`data` 프로필이 이 파일을 돈다):

```python
def test_internet_access_stays_on_this_pc(self, app_dir):
    assert db.get_setting(db.SETTING_INTERNET_ACCESS, "missing") == "missing"  # 마이그레이션에 넣지 않는다
    db.save_setting(db.SETTING_INTERNET_ACCESS, "1")
    exported = json.loads(db.export_all_data())
    assert db.SETTING_INTERNET_ACCESS not in exported["settings"]
    db.save_setting(db.SETTING_INTERNET_ACCESS, "0")
    exported["settings"][db.SETTING_INTERNET_ACCESS] = "1"  # 손으로 고친 파일이어도 받지 않는다
    db.import_all_data(json.dumps(exported))
    assert db.get_setting(db.SETTING_INTERNET_ACCESS, "") == "0"
```

`tests/test_ui_settings_internet_access.py`(`_window`·`_columns`는 `test_ui_settings_holiday_theme.py`와 같은 도우미):

- `test_row_sits_between_keep_desktop_and_font`: 시스템 묶음 줄 이름이 `["자동 실행", "바탕화면 고정", "인터넷 접속", "앱 글꼴"]`.
- `test_switch_off_by_default_and_for_garbage`: 키 없음·`"yes"`는 꺼짐, `"1"`은 켜짐.
- `test_tooltip_says_what_is_sent`: 툴팁이 §5⑤ 문구 그대로.
- `test_toggle_saves_key_audits_and_calls_back`: 켜고 끄면 저장값이 `[("internet_access_enabled", "1"), ("internet_access_enabled", "0")]`, `security.audit` 호출이 `"인터넷 접속 켬"`·`"인터넷 접속 끔"`, 콜백 2회.
- `test_failed_save_restores_switch_and_skips_callback`: 끄기에서 `db.save_setting`이 `sqlite3.OperationalError`를 던지면 스위치는 다시 켜짐, 콜백 0회, 저장 재시도 없음(호출 1회), 감사 로그에 끔 없음.
- `test_reset_with_open_window_turns_switch_off`: 키를 켠 채 `tests/test_ui_data_lifecycle.py:148`과 같은 방식으로 `_on_reset()` 실행 → `internet_switch.isChecked()`가 False, 키 없음, 끔 감사 로그 없음.

`tests/test_ui_settings_holiday_theme.py`의 `test_left_rows_36_right_rows_40`을 `test_both_columns_rows_36`으로 바꿔 `left_heights == right_heights == {36}`을 단언하고 파일 머리말의 '오른쪽 열은 그대로 40px'을 고친다. `test_layout_fits_without_compression`·배율 검사는 그대로 둔다(새 줄을 넣은 뒤 이 검사가 §3의 높이 계약을 증명한다).

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_settings_internet_access.py tests/test_ui_settings_holiday_theme.py tests/test_database.py -q`
Expected: 새 테스트와 `test_both_columns_rows_36`만 `AttributeError`(`SETTING_INTERNET_ACCESS`, `internet_switch`) 또는 `{40} != {36}`으로 실패

- [ ] **Step 3: 구현**

- `database.py`: 상수 추가, `EXPORT_EXCLUDED_SETTINGS`에 포함.
- `_add_row`의 `row_height` 기본값을 36으로 바꾸고 docstring을 '양쪽 열 모두 36'으로 고친다.
- 스위치 줄은 `self._add_row(sys_body, "인터넷 접속", self.internet_switch)`로 `keep_desktop_switch` 줄과 `font_combo` 사이에 넣는다. 툴팁은 `setToolTip`.
- `_on_internet_access_toggled(checked: bool)`: `db.save_setting` → 실패(`sqlite3.Error`)면 `_sync_internet_switch()`, `audit("인터넷 접속 설정", f"실패: {type(e).__name__}")`, `InfoBar.error(title="설정 오류", content="인터넷 접속 설정을 저장하지 못했습니다.", ...)` 후 return → 성공이면 `audit("인터넷 접속 켬" 또는 "인터넷 접속 끔")` → 콜백.
- `_sync_internet_switch() -> None`: `blockSignals`로 감싸 DB 값대로 `setChecked`. `setChecked(not checked)`로 되돌리면 처리기가 다시 돌아 저장을 재시도하므로 쓰지 않는다.
- `_on_reset`: `reset_succeeded.emit()` 앞에서 `_sync_internet_switch()`.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_settings_internet_access.py tests/test_ui_settings_holiday_theme.py tests/test_ui_settings_data.py tests/test_database.py -q`
Expected: 모두 통과. `test_layout_fits_at_scale_factors`(125·150%) 포함.

- [ ] **Step 5: Commit**

```bash
git add src/database.py src/ui_settings.py tests/test_database.py tests/test_ui_settings_internet_access.py tests/test_ui_settings_holiday_theme.py
git commit -m "feat: 설정 시스템 묶음에 인터넷 접속 스위치(기본 꺼짐, 내보내기 제외)"
```

---

### Task 3: 확인 예약과 작업 스레드

**Files:**
- Create: `src/ui_update_check.py`, `tests/test_ui_update_check.py`

**Interfaces:**
- Consumes: `update_check.check_latest`, `update_check.is_newer`, `CheckResult`; `db.SETTING_INTERNET_ACCESS`
- Produces (`ui_update_check`):
  - 상수 `FIRST_CHECK_DELAY_MS = 60_000`, `AFTER_SWITCH_DELAY_MS = 5_000`, `RETRY_DELAY_MS = 3_600_000`, `CHECK_INTERVAL_MS = 86_400_000`, `POLL_INTERVAL_MS = 200`
  - `class UpdateCheckController(QObject)`: `__init__(self, parent=None, current_version: str = APP_VERSION)`, `latestChanged = Signal(object)`(태그 또는 None), 읽기 속성 `latest -> str | None`
  - `start() -> None`: 창이 뜬 뒤 한 번. 켜져 있으면 60초 예약
  - `apply_setting() -> None`: 스위치 변경·가져오기·초기화 뒤. 꺼졌으면 취소+표시 지움, 켜졌는데 쉬고 있었으면 5초 예약, 이미 돌고 있으면 그대로
  - `stop() -> None`: 예약·폴링 취소, 결과 큐 버림(표시는 건드리지 않음). 종료용
  - 테스트·화면 연결용 `_set_latest(tag: str | None)`, 타이머 `_timer`(단발)·`_poll`, 스레드 `_worker`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_ui_update_check.py`)

```python
@pytest.fixture
def server(app_dir, monkeypatch):
    """check_latest를 바꾼다. answers를 차례로 돌려주고, gate를 걸면 그동안 응답을 붙잡는다."""
    state = SimpleNamespace(answers=[CheckResult(latest_tag="v4.7")], calls=0, gate=None)
    def fake(opener=None):
        state.calls += 1
        if state.gate is not None:
            state.gate.wait(5)
        return state.answers.pop(0) if len(state.answers) > 1 else state.answers[0]
    monkeypatch.setattr(update_check, "check_latest", fake)
    return state

def _fire(qtbot, controller, server):
    """예약 시각이 된 것처럼 하고 결과 반영까지 기다린다."""
    before = server.calls
    controller._timer.timeout.emit()
    qtbot.waitUntil(lambda: server.calls == before + 1 and not controller._poll.isActive())
```

컨트롤러는 `UpdateCheckController(current_version="v4.6")`로 만든다.

| 테스트 | 단언 |
|---|---|
| `test_off_means_no_request_at_all` | `update_check.https_only_opener`를 호출되면 실패하는 함수로 바꾸고, 진짜 `check_latest`로 키 없음·`"yes"`에서 `start()`·`apply_setting()`·`_timer.timeout.emit()` → 타이머 비활성, 호출 0회 |
| `test_key_is_read_again_just_before_request` | 켠 뒤 `start()`, `apply_setting()` 없이 키를 `"0"`으로 바꾸고 emit → `calls == 0`, 타이머 비활성, `latest` None |
| `test_unreadable_key_counts_as_off` | `db.get_setting`이 `sqlite3.Error` → `start()` 뒤 타이머 비활성 |
| `test_start_waits_a_minute_then_a_day` | `interval()` 60_000 → `_fire` 뒤 86_400_000, 활성 |
| `test_turning_on_checks_after_five_seconds` | 키 켬 + `apply_setting()` → 5_000 |
| `test_failure_retries_once_then_waits_a_day` | 실패 답 3개: 3_600_000 → 86_400_000 → 3_600_000, `caplog`(ERROR)에 `새 버전 확인 실패: timeout` |
| `test_newer_tag_is_reported_once` | v4.7 두 번 → 신호 1회, `latest == "v4.7"` |
| `test_failure_and_empty_answer_keep_known_latest` | v4.7 뒤 실패·`CheckResult()` → `latest == "v4.7"`, 신호 추가 없음 |
| `test_even_newer_tag_replaces_latest` | v4.7 뒤 v4.8 → 신호 `["v4.7", "v4.8"]` |
| `test_withdrawn_release_clears_latest` | v4.7 뒤 v4.6 → 신호 `["v4.7", None]` |
| `test_turning_off_drops_late_result_and_clears` | `gate` 걸고 emit, 키 끔 + `apply_setting()`, `gate.set()`, `qtbot.wait(POLL_INTERVAL_MS * 2)` → `latest` None, 타이머 비활성 |
| `test_quick_off_on_keeps_one_worker` | `gate` 걸고 emit, 끔·켬, 5초 예약 emit → `calls == 1`, `interval()` 5_000. `gate.set()`, `_worker`가 끝나길 기다린 뒤 다시 emit → `calls == 2` |
| `test_stop_drops_late_result` | `gate` 걸고 emit, `stop()`, `gate.set()` → `latest` None, 타이머 비활성 |
| `test_dead_worker_counts_as_failure` | 가짜가 `RuntimeError` → 폴링이 멈추고 3_600_000 예약 (`@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")`) |
| `test_controller_only_reads_the_key` | 소스의 `db.` 사용이 `get_setting`·`SETTING_INTERNET_ACCESS`뿐(정규식) |

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update_check.py -q`
Expected: `ModuleNotFoundError: No module named 'ui_update_check'`

- [ ] **Step 3: `src/ui_update_check.py` 구현**

- 작업 함수는 모듈 수준 `_run_check(results: Queue) -> None`이고 위젯을 잡지 않는다. `update_check.check_latest()`를 **호출 시점에 찾는다**(`from` import 금지. 테스트·미리보기가 바꿔 끼운다).
- 요청마다 `Queue(maxsize=1)`을 새로 만든다. `stop()`은 `self._results = None`으로 버리고 폴링을 멈춘다. 버린 큐의 결과는 아무도 읽지 않으므로 설계 §8의 세대 번호 역할을 한다.
- 예약이 울리면: 앞선 스레드가 살아 있으면 새로 시작하지 않고 5초 뒤로 → 키를 다시 읽어 꺼졌으면 `apply_setting()` → `Thread(target=_run_check, args=(queue,), daemon=True)` 시작 + 폴링 시작.
- 폴링 순서가 중요하다. 스레드가 넣고 끝나는 사이를 놓치지 않게 **먼저** `alive = worker.is_alive()`를 읽고 `get_nowait()` 한다. `Empty`이면서 `not alive`면 `CheckResult(failure="worker")`로 처리한다.
- 결과 처리:

```python
if result.failure is not None:
    _logger.error("새 버전 확인 실패: %s", result.failure)
    self._timer.start(CHECK_INTERVAL_MS if self._retried else RETRY_DELAY_MS)
    self._retried = not self._retried
    return
self._retried = False
self._timer.start(CHECK_INTERVAL_MS)
if result.latest_tag is not None:
    self._set_latest(result.latest_tag if update_check.is_newer(result.latest_tag, self._current) else None)
```

재시도까지 실패하면 그때부터 24시간 뒤를 다음 정기 확인으로 삼는다.
- 키 읽기는 `db.get_setting(db.SETTING_INTERNET_ACCESS, "0") == "1"`이고 `sqlite3.Error`는 로그 후 꺼짐으로 본다.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update_check.py -q`
Expected: 모두 통과

- [ ] **Step 5: Commit**

```bash
git add src/ui_update_check.py tests/test_ui_update_check.py
git commit -m "feat: 새 버전 확인 예약과 작업 스레드"
```

---

### Task 4: ②③ 빨간 점과 메인 창 연결

**Files:**
- Modify: `src/ui_update.py`, `src/ui_main.py`, `tests/test_ui.py:606`
- Create: `tests/test_ui_update_main.py`

**Interfaces:**
- Consumes: `UpdateCheckController`(Task 3), `show_update_guide`
- Produces:
  - `ui_update.DOT_COLOR = "#F04438"`, `class UpdateDot(QWidget)`: `__init__(self, parent, *, diameter: int, ring_color: str, ring: int = 2)`, `set_ring_color(color: str) -> None`, `ring_color() -> str`. 크기는 `diameter + 2 * ring`, 마우스 입력 통과.
  - `MainCalendarWindow._update_check`, `_update_dot`, `_on_update_latest_changed(latest: str | None) -> None`
  - `show_update_guide(parent, latest: str | None = None) -> None`(이 Task에서는 인자만 받고 쓰지 않는다. 강조는 Task 6)

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_ui_update_main.py`)

```python
def _make(qtbot, **settings):
    db.save_setting(db.SETTING_KEEP_ON_SHOW_DESKTOP, "0")
    for key, value in settings.items():
        db.save_setting(key, value)
    win = MainCalendarWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win

@pytest.fixture(autouse=True)
def no_network(app_dir, monkeypatch):  # 키를 켠 테스트의 예약이 울려도 나가지 않게 한다
    monkeypatch.setattr(update_check, "check_latest", lambda opener=None: CheckResult())
```

- `test_no_new_version_no_dots`: `_update_dot`가 보이지 않고 `win._build_more_menu().findChildren(UpdateDot) == []`.
- `test_more_button_dot_position_and_colors`: `win._update_check._set_latest("v4.7")` → 보임, 부모가 `_more_btn`, `geometry() == QRect(18, 2, 12, 12)`, `WA_TransparentForMouseEvents`, 픽셀 (6, 6) `#F04438`·(1, 6) `#01295F`.
- `test_dot_disappears_with_latest`: `_set_latest(None)` → 숨김.
- `test_dot_ring_follows_holiday_header`: `current_match`를 2026-12-25 판정으로 바꾸고 `win._holiday_theme.refresh()` → `ring_color() == match.theme.header`. None으로 되돌리면 `NAVY`.
- `test_menu_dot_sits_on_update_icon`: 메뉴의 `UpdateDot`이 하나, 부모가 `menu.view.viewport()`, 크기 11×11, 위치가 항목 `visualItemRect` 왼쪽 위 + (27, 3). 항목 문구·순서는 `["자동정렬", "앱 업데이트", "휴지통", "설정", "앱 최소화"]` 그대로.
- `test_update_guide_receives_latest`: 가짜 `ui_main.show_update_guide`로 메뉴 '앱 업데이트' 실행 → `calls == [(win, "v4.7")]`.
- `test_lock_overlay_covers_dot`: `_lock()` 뒤 점의 화면 좌표에서 `win.container.childAt(...)`가 `lock_overlay`이거나 그 자식.
- `test_import_keeps_and_reset_clears`: 키 켬·`_set_latest("v4.7")` → `win._on_import_complete()` 뒤 그대로. `db.reset_database()` + `win._on_factory_reset()` 뒤 `latest` None, 점 숨김.

`tests/test_ui.py:606`의 가짜를 `lambda parent=None, latest=None: calls.append(parent)`로 바꾼다.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update_main.py -q`
Expected: `ImportError`(`UpdateDot`)

- [ ] **Step 3: 구현**

- `MainCalendarWindow.__init__`: `_build_ui()` 앞에서 컨트롤러 생성, `_holiday_theme.refresh()` 앞에서 `latestChanged` 연결, `QTimer.singleShot(0, self, self._update_check.start)`.
- `_build_ui`의 `_more_btn` 바로 뒤: `self._update_dot = UpdateDot(self._more_btn, diameter=8, ring_color=NAVY)`, `move(18, 2)`, `hide()`.
- `_apply_holiday_theme`: `self._update_dot.set_ring_color(theme.header if theme is not None else NAVY)`.
- `_build_more_menu` 끝: `latest`가 있으면 `action.property("item")`로 항목을 찾아 `UpdateDot(menu.view.viewport(), diameter=7, ring_color="#FFFFFF")`을 `visualItemRect(item).topLeft() + MENU_DOT_OFFSET`(`QPoint(27, 3)`)에 놓고 `show()`. 메뉴 아이콘 칸이 14px이라 아이콘에 그리면 시안처럼 걸치지 못한다(`QIcon`을 바꾸지 않는다).
- `_on_update_guide`: `show_update_guide(self, self._update_check.latest)`.
- `_on_settings`: `on_internet_access_changed=self._update_check.apply_setting`.
- `_on_import_complete`: `self._update_check.apply_setting()`. 초기화도 이 함수를 지나므로 한 곳이면 된다.
- `prepare_for_quit`의 `_schedule_alarm_scheduler.stop(persist=True)` 옆: `self._update_check.stop()`.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update_main.py tests/test_ui_update.py tests/test_ui.py -q`
Expected: 모두 통과

- [ ] **Step 5: Commit**

```bash
git add src/ui_update.py src/ui_main.py tests/test_ui_update_main.py tests/test_ui.py
git commit -m "feat: 새 버전이 있으면 더보기 단추와 메뉴에 빨간 점"
```

---

### Task 5: ① 처음 발견 알림

**Files:**
- Modify: `src/ui_update.py`, `src/ui_main.py`, `tests/test_ui_update_main.py`

**Interfaces:**
- Consumes: `UpdateCheckController.latest`, `MainCalendarWindow._on_update_latest_changed`(Task 4)
- Produces:
  - `ui_update.open_latest_release_page() -> None`(`UpdateGuideDialog.open_gitlab`도 이것을 쓴다)
  - 상수 `TOAST_WIDTH = 348`, `TOAST_GAP = 8`, `TOAST_DURATION_MS = 10_000`
  - `class UpdateToast(QFrame)`: `__init__(self, parent, *, anchor: QWidget, header: QWidget, latest: str, current: str = APP_VERSION)`, 위젯 `get_button`·`close_button`·`title_label`·`sub_label`, 타이머 `_timer`, `reposition() -> None`. 닫히면 삭제된다(`WA_DeleteOnClose`).
  - `MainCalendarWindow._update_toast`, `_update_toast_shown`, `_maybe_show_update_toast()`, `_close_update_toast()`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_ui_update_main.py`)

`opened` 픽스처는 `tests/test_ui_update.py`와 같게 `ui_update.QDesktopServices`를 바꾼다.

- `test_toast_position_default_size`: 사이드바 켬(`SETTING_SHOW_SIDEBAR="1"`) → `container` 기준 `(x, y) == (96, 112)`, 폭 348. 사이드바 끔 → `x == 16`. 법령검색 끔(`SETTING_SHOW_LAW_SEARCH="0"`) → `y == 60`.
- `test_toast_stays_centered_after_scale_change`: 표시 중 `medium`으로 전환 → 가운데가 `right_content` 가운데, 위가 머리줄 아래 + 8.
- `test_toast_content`: 제목 `"새 버전 v4.7이 나왔습니다"`, 보조 `f"지금 쓰는 버전 {APP_VERSION}"`, 받기 높이 32, `close_button.accessibleName() == "알림 닫기"`.
- `test_long_tag_fits_toast`: `"v4.10a"`, 사이드바 끔 → 제목 라벨 폭 ≥ `sizeHint().width()`, 받기·닫기 오른쪽 끝 ≤ 348.
- `test_get_button_opens_page_and_closes`: `opened == [GITLAB_LATEST_URL]`, 알림 닫힘.
- `test_close_button_does_not_open_browser`, `test_toast_closes_after_ten_seconds`: `_timer.interval() == 10_000`, `timeout.emit()` 뒤 닫힘.
- `test_toast_once_per_run`: v4.7 표시·닫기 → v4.8 → `_update_toast is None`, 점은 보임, `latest == "v4.8"`.
- `test_hidden_then_shown`: `_minimize_to_tray()` 중 `_set_latest` → 없음. `toggle_visibility()` 뒤 `qtbot.waitUntil`로 표시.
- `test_locked_then_unlocked`: `_lock()` 중 → 없음. `_unlock()` 뒤 표시.
- `test_locked_and_hidden_waits_for_both`: 잠금+트레이 → `toggle_visibility()`만으로는 없음, `_unlock()` 뒤 표시.
- `test_lock_closes_visible_toast_without_repeat`, `test_tray_closes_visible_toast`.
- `test_turning_off_closes_toast`: 키 끔 + `apply_setting()` → 알림 닫힘, 점 숨김.
- `test_quit_stops_everything`: `prepare_for_quit()`가 True → `_timer` 비활성, 알림 닫힘.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update_main.py -q`
Expected: `ImportError`(`UpdateToast`)로 수집 실패

- [ ] **Step 3: 구현**

- 모양은 시안 ① 그대로: 안쪽 여백 위 10·오른쪽 8·아래 10·왼쪽 12, 간격 10, 흰 바탕, 1px `#D7E3FB`, 둥근 12px, `QGraphicsDropShadowEffect`(blur 30, 오프셋 (0, 10), `QColor(1, 20, 48, 90)`). 왼쪽 32px 원(`#DFE8FD`) 안 18px 위쪽 화살표(`#1D4ED8`, 굵기 2.2). 받기: 높이 32, 좌우 여백 14, 둥근 8, `#2563EB`(hover `#1D4ED8`), 흰 12px Bold. ×: 32×32, 둥근 8, 투명(hover `#F1F4F9`), 14px(`#5B6678`, 굵기 2.4). 제목 14px Bold(`_font(14, Bold, display=True)`), 보조 11px.
- `ICONS`에 `"arrow_up"`(`M12 19V5`, `M6 11l6-6 6 6`), `"close"`(`M6 6l12 12`, `M18 6L6 18`)를 더한다.
- `reposition`: `x = anchor 왼쪽 + (anchor.width() - TOAST_WIDTH) // 2`, `y = header 아래 + TOAST_GAP`(모두 `parent` 좌표). `anchor`·`header`에 이벤트 필터를 걸어 Resize·Move 때 다시 부른다.
- `UpdateToast`의 부모는 `self.container`, `anchor=self.right_content`, `header=self._header_section`. `LockOverlay`와 같은 부모라 잠금 덮개가 위로 올라온다.
- `_maybe_show_update_toast`: `latest`가 없거나 이미 띄웠거나 `_is_locked`·`_hidden_to_tray`·`not isVisible()`이면 return. 부르는 곳은 `_on_update_latest_changed`, `_unlock` 끝, `showEvent`(`QTimer.singleShot(0, self, ...)`).
- `_close_update_toast`: `isValid` 확인 후 닫고 None. 부르는 곳은 `_lock`, `_minimize_to_tray`, `prepare_for_quit`, `_on_update_latest_changed(None)`. 끄고 다시 켜도 `_update_toast_shown`은 되돌리지 않는다(실행당 한 번).

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update_main.py tests/test_ui_update.py -q`
Expected: 모두 통과. `test_line_icons_render`가 새 아이콘까지 돈다.

- [ ] **Step 5: Commit**

```bash
git add src/ui_update.py src/ui_main.py tests/test_ui_update_main.py
git commit -m "feat: 새 버전을 처음 발견하면 캘린더 위에 알림 한 번"
```

---

### Task 6: ④ 앱 업데이트 창의 GitLab 타일 강조

**Files:**
- Modify: `src/ui_update.py`, `tests/test_ui_update.py`

**Interfaces:**
- Consumes: `motion_allowed`(`ui_holiday_decor`), `show_update_guide(parent, latest)`(Task 4)
- Produces:
  - `UpdateGuideDialog(parent, latest: str | None = None)`, 속성 `_motion_timer`, `_ripple`(`latest` 없으면 None), `here_badge`(없으면 None)
  - 순수 함수 `ripple_state(elapsed_ms: int) -> tuple[float, float]`(퍼짐 px, 불투명도), `arrow_offset(elapsed_ms: int) -> int`, 타이머 슬롯 `_tick() -> None`

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_ui_update.py`, `_open(qtbot, parent, latest=None)`로 바꾼다)

```python
def test_ripple_follows_design_keyframes():
    assert ripple_state(0) == (0.0, 0.55)
    assert ripple_state(560) == pytest.approx((10.5, 0.1375))  # 0.5 지점, ease-out(1-(1-p)²)
    assert ripple_state(1120) == (0.0, 0.0)  # 70%에서 끝나고 나머지는 쉰다
    assert ripple_state(1600) == ripple_state(0)

def test_arrow_rises_two_pixels_and_returns():
    assert (arrow_offset(0), arrow_offset(800), arrow_offset(1600)) == (0, 2, 0)
    assert {arrow_offset(t) for t in range(0, 1600, 33)} == {0, 1, 2}
```

- `test_unknown_latest_keeps_b_design`: `latest` 없음 → `findChild(QLabel, "updateNewVersionPill") is None`, `here_badge is None`, 힌트 `"브라우저로 열기"`, `_pixel(gitlab, 1, h // 2) == GITLAB["bg"]`, 타이머 비활성.
- `test_new_version_row_and_tile`: `"v4.7"` → 꼬리표 `f"현재 {APP_VERSION}"` · `"새 v4.7"`(왼쪽→오른쪽 순서, 바탕 픽셀 `#1D4ED8`), 힌트 `"v4.7 받으러 가기"`, `_pixel(gitlab, 0, h // 2)`·`(1, h // 2)`가 `#1D4ED8`, 접근성 설명에 `여기서 받으세요`.
- `test_hover_and_focus_keep_two_pixel_border`: 타일에 포커스를 준 뒤에도 픽셀 (1, h // 2)가 `#1D4ED8`.
- `test_badge_straddles_top_edge`: 부모가 `dlg.widget`, 위 = 타일 위 − 12, 가운데 차이 1px 이내, 마우스 통과, 글자 `"여기서 받으세요"`, `dlg.widget.height() <= calendar.height()`. 뱃지 자리(`QPoint(w // 2, 3)`) 클릭 → `opened == [GITLAB_LATEST_URL]`.
- `test_motion_runs_only_on_visible_choice_page`: 표시 → 활성(간격 33 이상), 온나라 안내 → 비활성·뱃지 숨김, 돌아오기 → 활성, 닫기 → 비활성.
- `test_motion_off_keeps_border_and_badge`: `ui_update.motion_allowed`가 False → 타이머 비활성, `_ripple.isHidden()`, 뱃지 보임, 테두리 픽셀 `#1D4ED8`.
- `test_motion_stops_while_calendar_is_hidden`: `calendar.hide()` → 비활성, `calendar.show()` → 활성.
- `test_arrow_returns_home_when_motion_stops`: `dlg._tick()` 몇 번 뒤 멈추면 화살표 위치가 시작 위치.
- `test_long_tag_fits_narrow_dialog`: 부모 폭 380, `"v4.10a"` → 카드 폭 340, 힌트 라벨 폭 ≥ `sizeHint().width()`, 화살표 오른쪽 끝 ≤ 타일 폭, 새 꼬리표 오른쪽 끝 ≤ 카드 폭 − 20.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update.py -q`
Expected: `ImportError`(`ripple_state`)

- [ ] **Step 3: 구현**

- 순수 함수(§5④와 시안 키프레임): 주기 1600ms.

```python
def ripple_state(elapsed_ms):
    p = (elapsed_ms % 1600) / 1600 / 0.7
    if p >= 1:
        return 0.0, 0.0
    eased = 1 - (1 - p) ** 2
    return 14 * eased, 0.55 * (1 - eased)

def arrow_offset(elapsed_ms):
    return round(2 * math.sin(math.pi * (elapsed_ms % 1600) / 1600))
```

- 꼬리표 줄: `latest`가 있을 때만 `현재` 꼬리표 + 12px 오른쪽 화살표 아이콘(`ICONS["arrow_right"]`: `M5 12h14`, `M13 6l6 6-6 6`, `#5B6678`, 굵기 2.4) + `updateNewVersionPill`을 간격 6으로 가운데 정렬한다. 없으면 지금 코드 경로 그대로다.
- 타일: `UpdateTile.set_highlight(latest: str)` — 힌트 문구 교체, 여백을 `(11, 21, 11, 15)`로 줄여(테두리 2px 상쇄) 내용이 움직이지 않게, 동적 속성 `updateHighlight="true"` 후 `style().unpolish/polish`. `CARD_QSS` 뒤에 `[updateHighlight="true"]`의 기본·hover·pressed·focus 모두 `border: 2px solid #1D4ED8` 규칙을 둔다.
- 뱃지와 물결은 `self.widget`(카드)의 자식이다. `choice_page`의 자식으로 두면 페이지 가장자리에서 잘린다. 물결 위젯(`_TileRipple`)은 타일 사각형을 사방 14px 넓힌 크기이고 `lower()`로 `choice_page` 아래에 둔다. 카드 바탕은 카드 자신이 그리고 페이지는 투명이라 물결이 타일 둘레로 보이며, 타일이 위를 덮어 고리만 남는다. 칠하기는 `drawRoundedRect(타일 사각형을 spread만큼 넓힘, 14 + spread, 14 + spread)`, 색 `QColor(29, 78, 216)`에 불투명도.
- `_place_highlight()`: `gitlab_tile.mapTo(self.widget, QPoint(0, 0))` 기준으로 뱃지·물결을 놓는다. 타일에 이벤트 필터를 걸어 Resize·Move 때 다시 부른다.
- 움직임은 `_update_motion()` 한 곳에서 켜고 끈다. 조건: `latest` 있음 ∧ `motion_allowed()` ∧ `self.isVisible()` ∧ `choice_page` 표시 ∧ 부모 표시. 부르는 곳: `showEvent`, `hideEvent`, `show_choice`, `show_onnara_guide`, 부모의 Show·Hide 이벤트(필터). 타이머 간격 33ms, `QElapsedTimer`. 멈출 때 물결을 숨기고 화살표를 시작 위치로 돌린다. 화살표는 `hint_icon.move(시작 x + d, 시작 y - d)`로 움직인다.
- 잠금은 `_lock`의 `modal.reject()`가 창을 닫으므로 `hideEvent` 경로로 멈춘다. 온나라 타일·안내·닫기 동작은 바꾸지 않는다.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ui_update.py tests/test_ui_update_main.py -q`
Expected: 모두 통과

- [ ] **Step 5: Commit**

```bash
git add src/ui_update.py tests/test_ui_update.py
git commit -m "feat: 새 버전이 있으면 앱 업데이트 창의 GitLab 타일을 강조"
```

---

### Task 7: 개발 미리보기와 EXE 확인 시나리오

실패가 화면에 보이지 않는 기능이라, EXE에서 안 돌아도 아무도 모른다. 이 Task는 그 공백을 막는다. 앱에는 숨은 옵션을 넣지 않고 표준 프록시 환경 변수만 쓴다.

**Files:**
- Create: `tools/dev_update_check_preview.py`
- Modify: `tools/smoke_release.py`, `tests/test_source_layout.py`, `tests/test_release_smoke.py`

**Interfaces:**
- Consumes: `tools.dev_holiday_theme_preview.prepare_run`·`seed_synthetic_data`·`pin_theme_date`, `CheckResult`, `ui_update_check.FIRST_CHECK_DELAY_MS`, `db.SETTING_INTERNET_ACCESS`
- Produces:
  - `tools/dev_update_check_preview.py --latest v4.7 [--scale ...] [--date YYYY-MM-DD] [--reuse RUN_ID] [--check-only]`
  - `smoke_release.SCENARIOS`(튜플, `"update_check"` 포함), `update_check_scenario(exe, run_dir, *, live: bool = False) -> dict`, `_data` 동작 `enable_internet_access`, 옵션 `--live-update-check`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_source_layout.py`: `test_holiday_theme_preview_tool_stays_out_of_the_build`를 `@pytest.mark.parametrize("tool", ["dev_holiday_theme_preview", "dev_update_check_preview"])`로 넓히고, 합성 폴더 시험을 본떠 `test_update_check_preview_tool_uses_synthetic_appdata`(`--latest v4.7 --check-only`, 바깥 `LOCALAPPDATA`가 있어도 JSON의 `app_dir`이 `output/harness` 안, `latest == "v4.7"`)와 `test_update_check_preview_rejects_version_not_newer`(`--latest v0.1`이면 비영 종료)를 더한다.

`tests/test_release_smoke.py`:

- `test_update_check_scenario_runs_in_release`: `"update_check" in smoke.SCENARIOS`, 기존 5개 순서 유지.
- `test_enable_internet_access_writes_only_that_key`: `test_seed_is_isolated...`처럼 합성 폴더에서 seed 뒤 `enable_internet_access` → 키 `"1"`, 일정·메모 ID 그대로.
- `test_update_check_scenario_detects_missing_log`: `managed_launch`·`data_step`을 가짜로 바꾸고 `UPDATE_CHECK_WAIT_SECONDS`를 0으로 → `TimeoutError`.
- `test_live_scenario_fails_on_logged_failure`: `error.log`에 실패 줄이 있으면 `RuntimeError`.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_layout.py tests/test_release_smoke.py -q`
Expected: 새 테스트가 실패(`SCENARIOS` 없음, 도구 없음)

- [ ] **Step 3: 구현**

- 미리보기: `prepare_run` 뒤 `main.py`를 `runpy`로 가져온 다음(`dev_holiday_theme_preview.main`과 같은 순서) 격리를 확인하고, 키를 `"1"`로 저장, `update_check.check_latest = lambda opener=None: CheckResult(latest_tag=latest)`, `ui_update_check.FIRST_CHECK_DELAY_MS = 1000`을 넣고 `entry["main"]()`을 부른다. `--latest`는 `parse_version`이 받고 `APP_VERSION`보다 새로워야 한다. `--date`가 있으면 `pin_theme_date`로 테마 머리줄을 본다.
- 시나리오(`update_check_scenario`): 합성 폴더에서 `seed` → `enable_internet_access` → `managed_launch`로 EXE 실행. 기본은 환경에 `HTTPS_PROXY=http://127.0.0.1:9`를 넣고 `NO_PROXY`를 빼서(닫힌 포트라 인터넷 없이 연결 실패가 보장된다) `UPDATE_CHECK_WAIT_SECONDS = 90` 안에 `data_root/MyDesktopCalendar/error.log`에 `새 버전 확인 실패: connection`이 나타나는지 본다. `live=True`면 프록시를 건드리지 않고 `UPDATE_CHECK_LIVE_SECONDS = 75` 동안 실패 줄이 **없어야** 통과다. 첫 확인 60초 + 시간 제한 10초 안에 끝나므로, 앞의 시나리오와 함께 보면 TLS까지 성공했다는 근거가 된다. 프로세스 조기 종료는 실패다.
- `scenario()`는 `name == "update_check"`면 이 함수로 넘기고, `main()`의 목록은 `SCENARIOS`로 뺀다. `--live-update-check`는 `main()`에서 이 시나리오 하나만 돌리고 `smoke/update_check_live/result.json`에 결과를 남긴다.
- 시나리오는 약 70초 늘어난다(최근 기존 5개 합계 약 40초). `verify.py`의 `timeout=300` 안이라 고치지 않는다.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_layout.py tests/test_release_smoke.py -q`
Expected: 모두 통과

- [ ] **Step 5: 미리보기 도구 확인**

Run: `.\.venv\Scripts\python.exe tools/dev_update_check_preview.py --latest v4.7 --check-only`
Expected: `output/harness/<id>/appdata` 경로와 `"latest": "v4.7"`가 담긴 JSON 한 줄

- [ ] **Step 6: Commit**

```bash
git add tools/dev_update_check_preview.py tools/smoke_release.py tests/test_source_layout.py tests/test_release_smoke.py
git commit -m "test: 새 버전 알림 개발 미리보기와 EXE 확인 시나리오"
```

---

### Task 8: 문서와 최종 검증

**Files:**
- Modify: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/CODING_STANDARDS.md`, `docs/UI_PATTERNS.md`, `docs/TESTING.md`, `src/ui_update.py`(머리말), `docs/work/2026-11-04-update-check.md`

**Interfaces:**
- Consumes: Task 1~7 전체
- Produces: 없음

- [ ] **Step 1: 정본 문서 갱신**

- `AGENTS.md:72` → "런타임은 오프라인 전용이다(설정에서 인터넷 접속을 켠 경우는 제외). AI 법령검색·업데이트 안내의 브라우저 URL 열기는 스위치와 무관한 예외다." 공휴일 테마 단락의 '오른쪽 열 40px 유지'를 '양쪽 열 36px'로 고친다. '반드시 보존할 계약'에 새 버전 알림 항목을 추가한다(기본 꺼짐·요청 내용·실행당 한 번·저장 없음·`http`/`email` 제외 금지·미리보기 도구).
- `docs/ARCHITECTURE.md:142`, `:164`: `ui_update.py` 설명을 고치고 `update_check.py`·`ui_update_check.py` 행을 추가, 오프라인 줄에 예외를 적는다.
- `docs/CODING_STANDARDS.md:229`: 끝 문장 "앱 런타임은 오프라인 전용이다."를 같은 뜻으로 바꾸고, 앱의 새 버전 확인도 같은 opener 규칙을 따른다고 적는다.
- `docs/UI_PATTERNS.md`: `:69`·`:163`·`:188`(시스템 4행, 양쪽 열 36px, 실측 높이), `:126`(①~④).
- `docs/TESTING.md`: `:8` 뒤에 미리보기 도구, `:61`·`:182` 주변의 시나리오 수(6개)와 `--live-update-check`, `quick`·`data`·`full`이 네트워크를 쓰지 않는다는 문장 유지.
- `src/ui_update.py:7`: "이 창은 네트워크에 접속하지 않는다"로 고치고 머리말에 점·알림을 적는다.

- [ ] **Step 2: 지침 유실 확인**

Run: `git diff --stat -- AGENTS.md docs/` 후 `AGENTS.md` 변경이 위 세 곳뿐인지 `git diff -- AGENTS.md`로 본다.
Expected: 삭제 줄은 고친 두 문장뿐

- [ ] **Step 3: 전체 검증** (PowerShell)

Run: `.\.venv\Scripts\python.exe tools/verify.py release`
Expected: 종료 코드 0. `summary.md`에 전체 pytest 통과, smoke 6개 통과(`update_check` 포함), BINARY 출처가 검증 환경 안.

`release`는 전체 pytest를 1회 포함하므로 `quick`·`data`·`full`을 따로 돌리지 않는다. EXE는 `output/harness/<run-id>/dist/`에만 생기며 **`dist/`로 복사하지 않는다**(버전을 올리지 않았고, 배포는 이 계획 범위가 아니다). 공휴일 추가가 자동 반영되면 `holidays.py` 변경을 작업 기록에 적고 별도 커밋한다.

`.env` 키나 네트워크가 없어 `release`를 돌릴 수 없으면 `tools/verify.py full`을 돌리고, EXE 항목은 '미실행'으로 기록한 뒤 사용자에게 알린다.

- [ ] **Step 4: 실제 EXE의 TLS 확인** (PowerShell, 인터넷 PC)

Run: `.\.venv\Scripts\python.exe tools/smoke_release.py --exe "output\harness\<run-id>\dist\기후노트_v4.6.exe" --run-dir "output\harness\<run-id>" --live-update-check`
Expected: 종료 코드 0, `smoke/update_check_live/result.json`의 `status`가 `passed`

- [ ] **Step 5: 작업 기록 마무리와 Commit**

검증 증거 표에 실행 ID·결과를 적고, 남은 수동 확인을 '미해결과 인계'에 남긴다(설계 §11: `tools/dev_update_check_preview.py --latest v4.7`로 ①~④를 중간·크게·공휴일 테마·움직임 끔에서 보기, 업무망 PC, 스위치 꺼짐). 상태를 '구현 완료, 수동 확인 대기'로 바꾼다.

```bash
git add AGENTS.md docs/ARCHITECTURE.md docs/CODING_STANDARDS.md docs/UI_PATTERNS.md docs/TESTING.md src/ui_update.py docs/work/2026-11-04-update-check.md
git commit -m "docs: 새 버전 알림 계약과 오프라인 예외 반영"
```
