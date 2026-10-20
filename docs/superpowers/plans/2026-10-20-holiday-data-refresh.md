# 공휴일 데이터 최신화와 만료 안내 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** release마다 공휴일을 API 최신 값으로 맞추고, API 오류·일부 누락이 저장되거나 EXE로 나가지 않게 하며, 데이터 만료 때 직원에게 개발자 메일을 안내한다.

**Architecture:** 받기·검사·이름 합치기·연도 선택·파일 쓰기·비교는 모두 `fetch_data.py` 한 곳에 둔다(수동 실행과 release가 같은 코드). `tools/verify.py`는 release 맨 앞(입력 스냅샷 전)에서 `fetch_data.refresh_holidays()`를 불러 결과를 보고서와 종료 코드로 바꾼다. 앱 쪽은 Qt 없는 `holiday_notice.py`가 문구를 만들고 `main.py`가 InfoBar로 띄운다.

**Tech Stack:** Python 3.13, PySide6/qfluentwidgets, pytest/pytest-qt, defusedxml, python-dotenv(이미 의존성).

**Spec:** `docs/superpowers/specs/2026-10-20-holiday-data-refresh-design.md` (구현자는 계획과 함께 반드시 읽는다)

## Global Constraints

- 앱 런타임 코드에 네트워크 호출을 추가하지 않는다.
- 공휴일 날짜는 API 값만 쓴다. 계산·추정 금지. 검증은 이름 존재 여부만 본다.
- DB v18, Export v3, salt, 설정 키, 바로가기 6슬롯, Qt/lock(`requirements-lock.txt`)을 바꾸지 않는다. 새 의존성을 추가하지 않는다.
- 앱 표시 버전(`app_info.APP_VERSION`)을 바꾸지 않는다.
- 작업 트리의 다른 미추적 파일(`docs/work/`의 기록, `motion/` 등)을 건드리지 않는다.
- 모든 자동 시험은 네트워크·API 키 없이 가짜 응답으로 돈다.
- `LUNAR_API_KEY`는 공휴일 단계에서만 쓰고, pytest·빌드·격리 EXE에 넘기는 환경 변수에 넣지 않는다. 키는 화면 출력·로그·`result.json`·`summary.md`·예외 메시지에 남기지 않는다.
- `except/pass`·`bare except` 금지, 파일은 `with open`(`docs/CODING_STANDARDS.md`).
- 주석·docstring·메시지는 한국어, 주변 코드처럼 짧게.
- release·빌드는 PowerShell에서 실행한다. 이 계획의 자동 검사는 Git Bash에서도 된다.
- 핵심 공휴일 이름 8개: `1월1일`, `삼일절`, `광복절`, `개천절`, `한글날`, `기독탄신일`, `설날`, `추석`.
- 같은 날 이름 구분자: `·` (가운뎃점 U+00B7).

## Review Focus

1. 프록시·게이트웨이가 XML 대신 HTML 오류 페이지를 돌려준다 → 실패로 멈추고 `holidays.py`는 그대로 (Task 1 `test_html_gateway_page_is_failure`).
2. 공휴일 이름에 따옴표·역슬래시·줄바꿈이 들어온다 → 생성 파일이 깨지지 않고 같은 값으로 다시 읽힌다 (Task 3 `test_render_escapes_names_round_trip`).
3. 교체 직전 디스크·권한 오류 → 원본 유지, 임시 파일이 남지 않는다 (Task 3 `test_write_keeps_original_when_replace_fails`).
4. 프로젝트 루트가 아닌 폴더에서 실행 → 루트 `.env`의 키를 찾고 `os.environ`을 바꾸지 않는다 (Task 1 `test_load_api_key_reads_root_env_without_touching_environ`).
5. API가 이미 있는 연도를 통째로 안 준다 → 조용히 지우지 않고 실패 (Task 2 `test_select_fails_when_existing_year_loses_core_or_disappears`).

---

### Task 1: API 응답 검사와 실패 예외

**Files:**
- Modify: `fetch_data.py` (머리 ~ `fetch_lunar_month`, 1–65행)
- Test: `tests/test_fetch_data.py`

**Interfaces:**
- Produces:
  - `ROOT: Path` (= `Path(__file__).resolve().parent`)
  - `class FetchError(Exception)`: `__init__(self, message: str, *, environment: bool)`, 속성 `environment: bool` (True = 키·네트워크·서비스 문제, 하네스 종료 코드 2 / False = 응답 내용 문제, 종료 코드 1)
  - `load_api_key(env_path: Path = ROOT / ".env") -> str`
  - `API_KEY: str = load_api_key()` (모듈 전역 유지, 기존 시험이 monkeypatch함)
  - `fetch_holidays(year: int, month: int) -> list[dict]` → `[{"date": "YYYY-MM-DD", "name": str}]`, `isHoliday == "Y"`만, 실패 시 `FetchError`
  - `fetch_lunar_month(year: int, month: int) -> list[dict]` → `[{"date": "YYYY-MM-DD", "lunar": "M.D"}]`, 실패 시 `FetchError`

- [ ] **Step 1: 시험 도우미와 실패하는 시험 작성**

`tests/test_fetch_data.py`에 응답 생성 도우미를 두고 기존 XML 시험 3개(`test_api_requests_use_fixed_https_service_url`, `test_fetch_holidays_parses_api_xml`, `test_fetch_lunar_parses_api_xml`)를 이 도우미로 바꾼다.

```python
def api_xml(items="", code="00", total=None):
    total = items.count("<item>") if total is None else total
    return (f"<response><header><resultCode>{code}</resultCode><resultMsg>MSG</resultMsg></header>"
            f"<body><items>{items}</items><numOfRows>50</numOfRows><pageNo>1</pageNo>"
            f"<totalCount>{total}</totalCount></body></response>")

KEY_ERROR = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
             "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
             "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
```

새 시험(두 받기 함수 `fetch_holidays`, `fetch_lunar_month`에 parametrize):
- `test_fetch_rejects_unsafe_or_malformed_xml` (기존 시험 수정): `pytest.raises(fetch_data.FetchError)`이고 `exc.environment is False`.
- `test_error_result_code_is_environment_failure`: `api_xml(code="22")`, `KEY_ERROR` → `FetchError`, `environment is True`, 메시지에 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 또는 결과 코드가 들어간다.
- `test_nodata_and_empty_responses_are_not_failures`: `api_xml(code="03")`, `api_xml(total=0)` → `[]`.
- `test_short_page_is_data_failure`: 항목 1개 + `total=3` → `FetchError`, `environment is False`.
- `test_missing_or_bad_fields_are_data_failures`: 공휴일 `dateName` 없음, `locdate` `"2026011"`, `isHoliday` `"X"`; 음력 `lunDay` `"x"`, `solMonth` 없음 → `FetchError`, `environment is False`.
- `test_network_errors_are_environment_failures_without_key`: `fetch_data.API_KEY = "synthetic-key-7"`, `_OPENER.open`이 `urllib.error.URLError("boom")`, `urllib.error.HTTPError("https://x/?serviceKey=synthetic-key-7", 500, "err", {}, None)`, `TimeoutError()`을 던짐 → `FetchError`, `environment is True`, `"synthetic-key-7" not in str(exc)`.
- `test_missing_key_is_environment_failure`: `API_KEY = ""` → `FetchError`, `environment is True`, `_OPENER.open` 호출 0회.
- `test_html_gateway_page_is_failure`: `"<html><body>Proxy error</body></html>"`, `"<html><body>"` → `FetchError` (종류 무관).
- `test_load_api_key_reads_root_env_without_touching_environ(tmp_path, monkeypatch)`: `tmp_path/".env"`에 `LUNAR_API_KEY=abc` → `monkeypatch.delenv("LUNAR_API_KEY", raising=False)` 후 `load_api_key(tmp_path / ".env") == "abc"`이고 `"LUNAR_API_KEY" not in os.environ`. `monkeypatch.setenv("LUNAR_API_KEY", "env")`이면 `"env"`. 파일이 없으면 `""`.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_data.py -q`
Expected: FAIL (`FetchError`, `load_api_key` 없음; 기존 함수는 `[]`를 돌려줌)

- [ ] **Step 3: 구현**

- 모듈 머리의 `load_dotenv()` 호출을 없애고 `load_api_key()`로 바꾼다: `os.environ.get("LUNAR_API_KEY")`가 있으면 그것, 없으면 `dotenv.dotenv_values(env_path).get("LUNAR_API_KEY") or ""`. `os.environ`을 바꾸지 않는다.
- `_api_get`: `API_KEY`가 비면 요청 전에 `FetchError("LUNAR_API_KEY가 없습니다 (.env 확인)", environment=True)`. `URLError`(HTTPError 포함)·`TimeoutError`·`OSError`는 `FetchError(environment=True)`로 바꾸되, 메시지는 서비스·연·월과 예외 형식 이름만 쓴다(URL·키·원래 예외 문자열 금지). `raise ... from None`으로 원 예외 체인에 URL이 붙지 않게 한다.
- 응답 해석 공통 함수 `_response_items(xml_text: str, label: str) -> list` 하나로:
  - `ET.ParseError`/`DefusedXmlException` → `FetchError(environment=False)`
  - `header/resultCode`가 `"03"` → `[]`
  - `"00"`이 아니거나 없음 → `FetchError(environment=True)`, 메시지에 결과 코드와 `resultMsg`/`returnAuthMsg`(있으면)
  - `body/totalCount`가 숫자가 아니면 `FetchError(environment=False)`, `body/items/item` 수가 그보다 적으면 `FetchError(environment=False)`
- 필드 검사: 공휴일 `locdate` `\d{8}`, `dateName` 비어 있지 않음, `isHoliday` `Y`/`N`. 음력 `solYear` `\d{4}`, `solMonth`/`solDay` `\d{2}`, `lunMonth`/`lunDay` 정수. 어긋나면 `FetchError(environment=False)`.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_data.py -q`
Expected: PASS (기존 opener 시험 포함)

- [ ] **Step 5: 커밋**

```bash
git add fetch_data.py tests/test_fetch_data.py
git commit -m "fix: 공휴일 API 응답 검사와 받기 실패 예외"
```

---

### Task 2: 이름 합치기·연도 선택·검증 강화

**Files:**
- Modify: `fetch_data.py` (`verify_holiday_data` 주변)
- Test: `tests/test_fetch_data.py`

**Interfaces:**
- Consumes: `FetchError`, `fetch_holidays` (Task 1)
- Produces:
  - `CORE_HOLIDAY_NAMES: tuple[str, ...]` (Global Constraints의 8개, 그 순서)
  - `HOLIDAY_YEARS: range = range(2025, 2051)`
  - `merge_holiday_names(entries: Iterable[dict]) -> dict[str, str]`
  - `missing_core_names(holidays: Mapping[str, str], year: int) -> list[str]` (빠진 핵심 이름, `CORE_HOLIDAY_NAMES` 순서)
  - `verify_holiday_data(hol) -> tuple[bool, str]` (기존 조건 + 모든 연도 핵심 이름)
  - `fetch_holiday_years(years: Iterable[int]) -> dict[int, dict[str, str]]` (연도별 12개월, 0건 연도는 키 없음, 실패 시 `FetchError` 그대로)
  - `select_holiday_years(fetched: Mapping[int, Mapping[str, str]], existing_years: Iterable[int]) -> tuple[dict[str, str], list[int]]` (합친 공휴일, 제외한 새 연도 오름차순)
  - `_pause() -> None` (요청 사이 0.1초, 시험에서 바꿔 끼움)

- [ ] **Step 1: 실패하는 시험 작성**

시험용 "완전한 해"는 현재 데이터에서 잘라 쓴다: `def year_of(data, y): return {k: v for k, v in data.items() if k.startswith(f"{y}-")}` (`holidays.KOREAN_HOLIDAYS`).

- `test_merge_holiday_names_keeps_api_order_and_dedupes`:
  입력 `[{"date": "2025-05-05", "name": "어린이날"}, {"date": "2025-05-05", "name": "부처님오신날"}, {"date": "2025-05-05", "name": "어린이날"}, {"date": "2025-05-06", "name": "대체공휴일"}]`
  → `{"2025-05-05": "어린이날·부처님오신날", "2025-05-06": "대체공휴일"}`
- `test_missing_core_names_accepts_merged_names`: 2027년 자료에서 `"2027-10-09"`를 `"한글날·임시공휴일"`로 바꿔도 `[]`; `"2027-10-09"`를 지우면 `["한글날"]`.
- `test_verify_requires_core_names_every_year`: 현재 자료에서 `"2026-08-15"`만 뺀 Stub → `ok is False`, 메시지에 `"2026"`과 `"광복절"`. 기존 `test_verify_passes_on_current_data`는 그대로 통과해야 한다.
- `test_fetch_holiday_years_requests_twelve_months_and_skips_empty_years`: `fetch_holidays`를 가짜로(2027은 `year_of(...,2027)`의 날짜·이름을 월별로 돌려줌, 2040은 늘 `[]`), `_pause`는 아무것도 안 함 → 결과 키 `{2027}`, 호출 24회, `result[2027] == year_of(holidays.KOREAN_HOLIDAYS, 2027)`.
- `test_fetch_holiday_years_stops_on_first_failure`: 3월에 `FetchError("x", environment=False)` → 같은 예외가 나오고 4월 이후는 호출되지 않는다.
- `test_select_excludes_incomplete_new_year`: `fetched = {2025: y25, 2026: y26, 2027: y27, 2028: {"2028-04-12": "국회의원선거일"}}`, `existing_years={2025, 2026, 2027}` → 결과에 `2028-` 키 없음, 제외 `[2028]`.
- `test_select_fails_when_existing_year_loses_core_or_disappears`: (a) `fetched`에 2026 없음, (b) 2026에서 추석 3일을 뺌 → 둘 다 `FetchError`, `environment is False`, 메시지에 `"2026"`.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_data.py -q`
Expected: FAIL (새 이름 없음, `verify_holiday_data`가 핵심 이름을 보지 않음)

- [ ] **Step 3: 구현**

- `merge_holiday_names`: 날짜별로 처음 본 순서대로 이름을 모으고 같은 이름은 한 번만, `"·".join`.
- `missing_core_names`: 그 해 이름들 중 어느 하나에 핵심 이름이 부분 문자열로 들어 있으면 있음으로 본다(날짜는 보지 않음).
- `verify_holiday_data`: 기존 세 조건 뒤에 `KOREAN_HOLIDAYS`의 연도마다 `missing_core_names` 검사, 실패 메시지 `f"{year}년 핵심 공휴일 누락: {', '.join(missing)}"`.
- `fetch_holiday_years`: 연도마다 1~12월 `fetch_holidays`를 모아 `merge_holiday_names`, 매 요청 뒤 `_pause()`.
- `select_holiday_years`: `existing_years ∪ fetched 연도`를 차례로 보며, 핵심 이름이 모자란 연도가 기존 연도면 `FetchError(f"{year}년 공휴일이 불완전합니다 (누락: …)", environment=False)`, 새 연도면 제외 목록에 넣는다(기존 연도가 `fetched`에 아예 없으면 8개 모두 누락으로 본다).

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_data.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add fetch_data.py tests/test_fetch_data.py
git commit -m "feat: 같은 날 공휴일 이름 합치기와 핵심 공휴일 연도 검증"
```

---

### Task 3: 안전한 파일 쓰기·비교·갱신 진입점

**Files:**
- Modify: `fetch_data.py` (`main()` 전체 교체, 끝의 `if __name__`)
- Test: `tests/test_fetch_data.py`

**Interfaces:**
- Consumes: Task 1·2의 모든 이름
- Produces:
  - `HOLIDAYS_PATH: Path = ROOT / "holidays.py"`
  - `render_holidays_module(holidays: Mapping[str, str], lunar: Mapping[str, str]) -> str`
  - `read_holidays_module(path: Path) -> tuple[dict[str, str], dict[str, str]]` (`runpy.run_path`로 `KOREAN_HOLIDAYS`, `LUNAR_MAPPING`)
  - `write_holidays_module(path: Path, holidays: Mapping[str, str], lunar: Mapping[str, str], backup_dir: Path) -> Path` (백업 파일 경로를 돌려줌)
  - `@dataclass(frozen=True) class HolidayDiff`: `added: dict[str, str]`, `removed: dict[str, str]`, `renamed: dict[str, tuple[str, str]]` (날짜 → (이전, 새))
  - `diff_holidays(old: Mapping[str, str], new: Mapping[str, str]) -> HolidayDiff`
  - `@dataclass(frozen=True) class RefreshResult`: `status: str` (`"up_to_date"` | `"updated"` | `"blocked"`), `diff: HolidayDiff`, `excluded_years: list[int]`, `checked_at: str` (현지 시각 ISO, 초 단위), `years: tuple[int, int]` (받은 범위 처음·끝), `backup: Path | None`
  - `refresh_holidays(path: Path = HOLIDAYS_PATH, backup_dir: Path | None = None, years: Iterable[int] = HOLIDAY_YEARS) -> RefreshResult` (공휴일만 받음, 음력은 기존 값 유지)
  - `fetch_lunar_years(years: Iterable[int]) -> dict[str, str]`
  - `main() -> int` (수동 전체 재생성, 성공 0 / 실패 1)

- [ ] **Step 1: 실패하는 시험 작성**

- `test_render_reproduces_current_module_exactly`: `render_holidays_module(holidays.KOREAN_HOLIDAYS, holidays.LUNAR_MAPPING) == Path(holidays.__file__).read_text(encoding="utf-8")` (형식 불변의 정본 시험. 설계 단계에서 같은 형식의 렌더가 현재 파일과 완전히 같음을 확인함).
- `test_render_escapes_names_round_trip`: 현재 자료에 `"2027-12-25": 'a"b\\c\nd'`를 넣어 렌더 → 임시 파일 → `read_holidays_module` 결과가 입력과 같다.
- `test_write_replaces_after_verify_and_backs_up(tmp_path)`: 현재 `holidays.py`를 `tmp_path/"holidays.py"`로 복사, 새 자료 = 현재 + 2027 자료를 연도만 2028로 바꾼 합성 해 → 반환 백업 파일 내용 == 옛 파일 내용, 새 파일을 읽으면 2028 포함·`LUNAR_MAPPING` 동일, `tmp_path`에 `.tmp` 파일 없음.
- `test_write_keeps_original_when_verify_fails`: 2026 광복절을 뺀 자료 → `FetchError(environment=False)`, 원본 바이트 동일, 백업·임시 파일 없음.
- `test_write_keeps_original_when_replace_fails`: `monkeypatch.setattr(fetch_data.os, "replace", 실패)` → `OSError`, 원본 바이트 동일, 임시 파일 없음.
- `test_diff_holidays_classifies_added_removed_renamed`: old `{"a": "1", "b": "2", "c": "3"}`, new `{"a": "1", "b": "X", "d": "4"}` → added `{"d": "4"}`, removed `{"c": "3"}`, renamed `{"b": ("2", "X")}`.
- `test_refresh_statuses` (parametrize, `fetch_holiday_years`를 가짜로, 대상은 `tmp_path` 사본):
  - 같은 자료 → `"up_to_date"`, 파일 바이트 동일, `backup is None`
  - 2028 합성 완전한 해 추가 → `"updated"`, 파일에 2028, 음력 동일, 백업이 `backup_dir` 안에 있음
  - `"2026-10-05"` 삭제 → `"blocked"`, 파일 바이트 동일, `diff.removed == {"2026-10-05": "대체공휴일(개천절)"}`
  - `"2025-05-05"`를 `"어린이날·부처님오신날"`로 → `"blocked"`, `diff.renamed`에 그 날짜
- `test_refresh_reports_excluded_new_year`: 2028에 선거일 하나만 → `"up_to_date"`, `excluded_years == [2028]`.
- `test_refresh_always_refetches_existing_years`: `years=range(2028, 2030)`으로 불러도 가짜 `fetch_holiday_years`가 받은 연도에 2025·2026·2027이 들어 있다.
- `test_main_returns_one_and_keeps_file_on_failure`: `HOLIDAYS_PATH`를 `tmp_path` 사본으로, `API_KEY="k"`, `fetch_lunar_years`가 `FetchError` → `main() == 1`, 파일 바이트 동일.
- `test_main_missing_key_returns_one`: `API_KEY=""` → `main() == 1`, 받기 함수 호출 0회.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_data.py -q`
Expected: FAIL (새 이름 없음)

- [ ] **Step 3: 구현**

- `render_holidays_module`: 현재 `main()`이 쓰는 형식 그대로(머리 주석 2줄, `from datetime import date`, 연도 주석이 있는 두 dict, 함수 4개 블록). 키와 값은 `json.dumps(..., ensure_ascii=False)`로 따옴표를 붙여 특수 문자를 안전하게 쓴다(평범한 이름은 지금과 같은 결과).
- `write_holidays_module`: 같은 폴더에 텍스트 모드(`newline` 기본, Windows 줄바꿈 유지)로 임시 파일 작성 → `read_holidays_module`로 다시 읽어 입력과 같은지 + `verify_holiday_data(SimpleNamespace(...))` 통과 확인 → 실패 시 `FetchError(environment=False)` → `backup_dir`를 만들고 기존 파일을 `backup_dir / "holidays.py"`로 복사 → `os.replace`. 어떤 경로로 끝나든 이 호출이 만든 임시 파일은 지운다(`tools/verify.py`의 `atomic_text`와 같은 `try/finally` 방식).
- `refresh_holidays`: 현재 파일 읽기 → `years ∪ 기존 연도`로 `fetch_holiday_years` → `select_holiday_years(..., existing_years=기존 연도)` → `diff_holidays` → 삭제·변경이 있으면 `"blocked"`(쓰지 않음), 추가만 있으면 `write_holidays_module(..., 기존 음력, backup_dir)` 후 `"updated"`, 아니면 `"up_to_date"`. `backup_dir`가 None인데 써야 하면 `ROOT/"output"/"holiday-refresh"/<YYYYMMDD-HHMMSS>`.
- `main()`: 키 없으면 안내 출력 후 1. 음력 `fetch_lunar_years(HOLIDAY_YEARS)` → 공휴일 `fetch_holiday_years(HOLIDAY_YEARS ∪ 기존 연도)` → `select_holiday_years` → `diff_holidays`를 사람이 읽게 출력(추가·삭제·변경·제외 연도) → `write_holidays_module(HOLIDAYS_PATH, ..., ROOT/"output"/"holiday-refresh"/<시각>)` → 0. `FetchError`는 메시지를 출력하고 1. 이 경로가 release가 막은 삭제·변경을 받아들이는 공식 경로다.
- 파일 끝: `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fetch_data.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add fetch_data.py tests/test_fetch_data.py
git commit -m "feat: 공휴일 데이터 검증 후 교체·백업과 갱신 진입점"
```

---

### Task 4: release 맨 앞의 공휴일 최신화 단계

**Files:**
- Modify: `tools/verify.py` (`isolated_env` 113–125행, `save_report` 269–296행, `execute` 337–388행, 새 함수 2개)
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `fetch_data.refresh_holidays`, `RefreshResult`, `HolidayDiff`, `FetchError` (Task 1·3)
- Produces:
  - `_fetch_data_module() -> ModuleType` (ROOT를 `sys.path`에 잠시 넣고 `fetch_data`를 가져온다. `artifact_metadata`의 `build_app` 가져오기와 같은 방식. 모듈 import 시점에는 가져오지 않는다)
  - `refresh_holidays_step(run_dir: Path, report: dict) -> None` (`report["holidays"]`를 채우고, 막힘·실패면 예외)
  - `report["holidays"]` 형식: `{"status": "up_to_date"|"updated"|"blocked"|"failed", "checked_at": str, "years": [첫, 끝], "added": {날짜: 이름}, "removed": {날짜: 이름}, "renamed": {날짜: [이전, 새]}, "excluded_years": [int], "backup": str|None}`; 실패면 `{"status": "failed", "error": str}`

- [ ] **Step 1: 실패하는 시험 작성**

- 기존 `runner` fixture에 `monkeypatch.setattr(verify, "refresh_holidays_step", lambda run_dir, report: None)`를 더해 기존 release 시험이 네트워크를 타지 않게 한다. 모듈 머리에 `REAL_HOLIDAY_STEP = verify.refresh_holidays_step`를 보관한다.
- 도우미 `use_fake_fetch(monkeypatch, *, result=None, error=None)`: `verify.refresh_holidays_step`를 `REAL_HOLIDAY_STEP`로 되돌리고, `verify._fetch_data_module`이 `SimpleNamespace(refresh_holidays=가짜, FetchError=fetch_data.FetchError)`를 돌려주게 한다. `result`는 `fetch_data.RefreshResult`로 만든다.
- `test_release_refreshes_holidays_before_input_snapshot`: 공휴일 단계와 `source_snapshot` 호출 순서를 기록 → `["holidays", "snapshot", ...]`로 시작.
- `test_non_release_profiles_skip_holiday_refresh`: 공휴일 단계가 `AssertionError`를 던지게 하고 `mini_pytest` 통과 코드로 `execute("full") == 0`.
- `test_release_stops_when_holidays_blocked`: `status="blocked"`, renamed `{"2025-05-05": ("부처님오신날", "어린이날·부처님오신날")}` → `execute("release") == 1`, `steps == []`, `result.json`의 `holidays.status == "blocked"`, `renamed == {"2025-05-05": ["부처님오신날", "어린이날·부처님오신날"]}`, `"fetch_data.py" in error`, `summary.md`에 `"2025-05-05"`.
- `test_release_holiday_fetch_failure_exit_codes` (parametrize `environment`: True→2, False→1): `FetchError("받기 실패", environment=...)` → 종료 코드, `holidays.status == "failed"`, `steps == []`.
- `test_release_continues_after_holiday_update`: `status="updated"`, added `{"2028-01-01": "1월1일"}`, `run_step`은 `test_release_artifact_failure_has_exit_one`의 가짜를 재사용 → `[s["name"] for s in steps][0] == "pytest"`, `holidays.added == {"2028-01-01": "1월1일"}`, `summary.md`에 `"2028-01-01"`.
- `test_isolated_env_drops_api_key(tmp_path, monkeypatch)`: `monkeypatch.setattr(verify, "ROOT", tmp_path)`, `monkeypatch.setenv("LUNAR_API_KEY", "synthetic-key-7")`, `run = verify.create_run_dir(root=tmp_path)` → `"LUNAR_API_KEY" not in verify.isolated_env(run)`.
- 기존 `test_tool_import_has_no_app_side_effects`가 계속 통과해야 한다(`fetch_data`를 import 시점에 가져오지 않음).

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_verify.py -q`
Expected: FAIL (`refresh_holidays_step` 없음)

- [ ] **Step 3: 구현**

- `isolated_env`: `env.pop("LUNAR_API_KEY", None)`.
- `refresh_holidays_step`: `fd = _fetch_data_module()` → `fd.refresh_holidays(ROOT / "holidays.py", backup_dir=run_dir / "holidays-backup")`.
  - 결과를 위 형식으로 `report["holidays"]`에 넣고(`backup`은 `run_dir` 기준 상대 경로), 화면에 한 줄 출력(`공휴일: 최신 확인` / `공휴일: N건 추가` / `공휴일: 기존 날짜 삭제·변경 발견`).
  - `"blocked"` → `VerificationFailure("공휴일 기존 날짜가 삭제·변경되었습니다. 목록을 확인한 뒤 `python fetch_data.py`를 실행하고 다시 release 하세요.")`
  - `fd.FetchError` → `report["holidays"] = {"status": "failed", "error": str(exc)}` 후, `exc.environment`면 `ValueError(...)`(종료 코드 2), 아니면 `VerificationFailure(...)`(종료 코드 1).
- `execute` 순서: `report["environment"] = doctor()` → 오류면 지금처럼 `ValueError` → `if profile == "release": refresh_holidays_step(run_dir, report); save_report(run_dir, report)` → `report["inputs_before"] = source_snapshot()` → 이하 동일.
- 뒤 단계(pytest·빌드·격리 실행)가 실패해도 갱신한 `holidays.py`를 되돌리지 않는다(설계 결정). 되돌리는 코드를 넣지 않는다.
- `save_report`: `report`에 `"holidays"`가 있으면 `## 공휴일 데이터` 블록(상태, 조회 시각, 받은 범위, 추가/삭제/변경 목록, 제외 연도, 백업, 실패 메시지)을 `## 실행 단계` 앞에 넣는다.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_verify.py tests/test_fetch_data.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add tools/verify.py tests/test_verify.py
git commit -m "feat: release 시작 때 공휴일 데이터 최신화 단계"
```

---

### Task 5: 날짜·시간 계산기의 공휴일 범위 표기를 데이터에서 가져오기

**Files:**
- Modify: `date_time_calculator.py:12-14`, `ui_date_time_calculator.py:13-17,347,348,588`
- Test: `tests/test_date_time_calculator.py:161-168`, `tests/test_ui_date_time_calculator.py:192-198`

**Interfaces:**
- Produces: `date_time_calculator.HOLIDAY_SPAN: str` (`f"{min(HOLIDAY_YEARS)}–{max(HOLIDAY_YEARS)}"`, en dash), `HOLIDAY_RANGE`는 `f"{HOLIDAY_SPAN}년"`으로 바꿔 값은 그대로.

- [ ] **Step 1: 시험을 데이터 기준으로 바꾸고 새 시험 추가**

- `test_missing_holiday_year_is_not_treated_as_zero_holidays`: 범위를 `FIRST, LAST = min(HOLIDAY_YEARS), max(HOLIDAY_YEARS)`로 만든다. 경우: `(date(FIRST-1, 12, 31), date(FIRST, 1, 2))`, `(date(LAST, 12, 31), date(LAST+1, 1, 1))`, `(date(LAST+1, 1, 1), date(LAST+1, 1, 2))`. `match=re.escape(HOLIDAY_RANGE)`.
- `test_ui_date_time_calculator.py` 192–198행: `2028`을 `LAST + 1`년의 1월 3일 이후 첫 월요일부터 금요일까지로 바꾼다(`start = date(LAST+1, 1, 3); start += timedelta((7 - start.weekday()) % 7)`), 오류 문구 검사는 `str(FIRST)`와 `str(LAST)`. `'4일'`·`'공휴일 미반영'` 검사는 그대로.
- 새 시험 `test_workday_holiday_notes_follow_data(qtbot, monkeypatch)`: `monkeypatch.setattr(ui_date_time_calculator, "HOLIDAY_RANGE", "2025–2028년")`, `HOLIDAY_SPAN`도 `"2025–2028"`으로 바꾼 뒤 창을 만들면 근무일 안내 문구가 `"공휴일 자료: 2025–2028년"`이고 툴팁에 `"2025–2028년"`이 들어 있으며, 공휴일 반영 계산 결과 주석에 `"공휴일 반영 (2025–2028)"`이 나온다(2026년 날짜로 계산).

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py -q`
Expected: 새 시험 FAIL (문구가 박혀 있음)

- [ ] **Step 3: 구현**

`ui_date_time_calculator.py`의 세 문구를 `HOLIDAY_RANGE`·`HOLIDAY_SPAN`(모듈 전역으로 import)으로 만든다. 문구 모양은 `'공휴일 자료: {HOLIDAY_RANGE} · 범위 밖은 공휴일 제외를 끄고 계산'`, `'공휴일 자료: {HOLIDAY_RANGE}'`, `'공휴일 반영 ({HOLIDAY_SPAN})'`.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py tests/test_date_time_integration.py -q`
Expected: PASS (기존 배치 시험 포함)

- [ ] **Step 5: 커밋**

```bash
git add date_time_calculator.py ui_date_time_calculator.py tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py
git commit -m "fix: 날짜·시간 계산기 공휴일 범위 표기를 데이터에서 가져오기"
```

---

### Task 6: 만료 안내 문구와 개발자 메일

**Files:**
- Modify: `app_info.py:6`, `main.py:288-300`
- Create: `holiday_notice.py`
- Test: `tests/test_holiday_notice.py` (새 파일)

**Interfaces:**
- Produces:
  - `app_info.APP_CONTACT_EMAIL = "ggjo@korea.kr"`, `APP_AUTHOR = f"기후에너지환경부 보문산불주먹 ({APP_CONTACT_EMAIL})"`
  - `holiday_notice.HOLIDAY_NOTICE_TITLE = "공휴일 안내"`
  - `holiday_notice.holiday_expiry_notice(today: date, last_year: int, email: str) -> tuple[str, str] | None` (Qt 없음)

- [ ] **Step 1: 실패하는 시험 작성 (`tests/test_holiday_notice.py`)**

```python
from datetime import date
import pytest
from app_info import APP_AUTHOR, APP_CONTACT_EMAIL
from holiday_notice import HOLIDAY_NOTICE_TITLE, holiday_expiry_notice

FIRST = ("공휴일 정보는 2027년까지 들어 있습니다.\n"
         "새 버전을 받지 못했다면 개발자(ggjo@korea.kr)에게 메일로 알려 주세요.")
AFTER = ("2028년부터는 달력에 공휴일이 표시되지 않습니다.\n"
         "개발자(ggjo@korea.kr)에게 메일로 알려 주세요.")

@pytest.mark.parametrize("today,expected", [
    (date(2027, 11, 30), None),
    (date(2027, 12, 1), (HOLIDAY_NOTICE_TITLE, FIRST)),
    (date(2027, 12, 31), (HOLIDAY_NOTICE_TITLE, FIRST)),
    (date(2028, 1, 1), (HOLIDAY_NOTICE_TITLE, AFTER)),
    (date(2031, 6, 1), (HOLIDAY_NOTICE_TITLE, AFTER)),
])
def test_holiday_expiry_notice_by_date(today, expected):
    assert holiday_expiry_notice(today, 2027, "ggjo@korea.kr") == expected
```

- `test_contact_email_is_single_source`: `APP_CONTACT_EMAIL == "ggjo@korea.kr"`, `APP_AUTHOR == "기후에너지환경부 보문산불주먹 (ggjo@korea.kr)"`.
- `test_notice_fits_narrowest_main_window(qtbot)`: 폭 380, 높이 600의 부모 `QWidget`을 띄우고 `InfoBar.warning(title, content, parent=부모, position=InfoBarPosition.TOP, duration=-1)`를 두 문구 각각으로 만든 뒤 `qtbot.waitExposed` → `APP_CONTACT_EMAIL in bar.contentLabel.text()`(메일 주소 중간에 줄바꿈 없음), `bar.geometry().right() <= 부모.width()`, `bar.geometry().left() >= 0`.

- [ ] **Step 2: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_holiday_notice.py -q`
Expected: FAIL (`holiday_notice` 없음)

- [ ] **Step 3: 구현**

- `holiday_notice.py`: 위 시험의 두 문구를 그대로 만든다(`{Y}` = `last_year`, `{Y+1}` = `last_year + 1`). 조건은 기존 `main.py`와 같다: `today.year == last_year and today.month == 12` → 1단계, `today.year > last_year` → 2단계, 그 외 `None`. `last_year <= 0`이면 `None`.
- `app_info.py`: 상수 추가, `APP_AUTHOR`는 그 상수로 같은 문자열을 만든다.
- `main.py` 288–300행: `holiday_last_year()`·`APP_CONTACT_EMAIL`·`holiday_expiry_notice(date.today(), …)` 결과가 있으면 기존과 같은 `QTimer.singleShot(2000, …InfoBar.warning(title=…, content=…, parent=main_window, position=InfoBarPosition.TOP, duration=10000))`.
- 380px 시험이 실패하면(메일이 잘리거나 쪼개짐) 문구 뜻은 유지한 채 줄바꿈 위치만 조정하고, 시험의 기대 문구도 같이 맞춘다.

- [ ] **Step 4: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_holiday_notice.py tests/test_packaging.py -q`
Expected: PASS (`CompanyName` 불변 포함. 설정 화면 만든이 문구는 Task 7의 full에서 `tests/test_ui.py`로 확인)

- [ ] **Step 5: 커밋**

```bash
git add holiday_notice.py app_info.py main.py tests/test_holiday_notice.py
git commit -m "feat: 공휴일 만료 안내에 개발자 메일 추가"
```

---

### Task 7: 정본 문서·작업 기록 갱신과 전체 검증

**Files:**
- Modify: `AGENTS.md:93,109` (+ `## 기록 관리` 맨 위 항목), `docs/ARCHITECTURE.md:105-106,165`, `docs/TESTING.md:33` (+ release 설명 단락), `docs/DATE_TIME_CALCULATION.md:16`
- Create: `docs/work/2026-10-20-holiday-data-refresh.md` (`docs/templates/WORK_NOTE.md` 양식)

- [ ] **Step 1: 문서 갱신**

- `AGENTS.md` 93·109행: "갱신은 `fetch_data.py`로만"을 유지하면서, release가 시작할 때 공휴일만 다시 받아 추가는 자동 반영·삭제/변경은 멈춤, 수동 `python fetch_data.py`가 삭제·변경을 받아들이는 경로, 일부만 발표된 새 연도는 제외, API 키는 release 공휴일 단계에서만이라는 점. `## 기록 관리` 맨 위에 2026-10-20 항목(버전 변경 없음, 작업 기록 링크).
- `docs/ARCHITECTURE.md`: 105–106행 모듈 설명(같은 날 이름 `·` 합치기, 검증 후 교체·백업, `refresh_holidays`), 165행 공휴일 데이터 규칙(갱신 절차를 코드가 수행함으로 정정, 만료 안내 문구·메일 정본 `app_info.APP_CONTACT_EMAIL`).
- `docs/TESTING.md`: release 행에 "공휴일 최신화(네트워크·`.env` 키 필요) → 전체 pytest → …", 멈추는 경우와 종료 코드(환경 2 / 데이터 1), quick·data·full은 네트워크 없음.
- `docs/DATE_TIME_CALCULATION.md` 16행: 범위 문구가 데이터를 따른다는 문장으로.
- 작업 기록: 목표·완료 조건·결정(설계 문서 링크)·검증 증거 표.

- [ ] **Step 2: 관련 quick 검사**

Run: `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_holiday_notice.py tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py tests/test_date_time_integration.py`
Expected: `passed: output\harness\<run-id>\summary.md` (quick 기본 목록에 `test_fetch_data.py`·`test_verify.py`가 이미 있음)

- [ ] **Step 3: 하네스 변경이 있으므로 full 검사**

Run: `.\.venv\Scripts\python.exe tools/verify.py full`
Expected: `passed`, 실패 0. 실행 ID와 테스트 수를 작업 기록 표에 적는다.

- [ ] **Step 4: 커밋**

```bash
git add AGENTS.md docs/ARCHITECTURE.md docs/TESTING.md docs/DATE_TIME_CALCULATION.md docs/work/2026-10-20-holiday-data-refresh.md docs/superpowers/specs/2026-10-20-holiday-data-refresh-design.md docs/superpowers/plans/2026-10-20-holiday-data-refresh.md
git commit -m "docs: 공휴일 데이터 최신화·만료 안내 계약과 작업 기록"
```

---

### Task 8: 실제 API로 한 번 갱신 (사용자 확인 후, 이 PC·PowerShell)

실제 키로 공공데이터포털을 부르고 추적 파일 `holidays.py`를 바꾸므로, 시작 전에 사용자에게 확인을 받는다. 서브에이전트가 아니라 진행자가 직접 한다.

**Files:**
- Modify: `holidays.py` (생성물), `docs/work/2026-10-20-holiday-data-refresh.md`

- [ ] **Step 1: 빈 연도의 실제 응답 형식 확인**

PowerShell에서 키·URL을 출력하지 않고 결과 코드·메시지·건수만 본다:

```powershell
.\.venv\Scripts\python.exe -c "import fetch_data as f; from defusedxml import ElementTree as ET; r = ET.fromstring(f._api_get('SpcdeInfoService/getRestDeInfo', 2040, 1)); print(r.findtext('header/resultCode'), r.findtext('header/resultMsg'), r.findtext('body/totalCount'))"
```

Expected: `00 NORMAL SERVICE. 0` 또는 `03 …`. 다른 값이면 멈추고 Task 1의 "자료 없음" 처리를 다시 본다. 결과를 작업 기록에 적는다.

- [ ] **Step 2: 수동 갱신**

Run: `.\.venv\Scripts\python.exe fetch_data.py`
Expected: 종료 코드 0. 출력의 변경 목록에 `2025-05-05` 이름 변경(`어린이날`이 합쳐짐)이 있고, 그 밖의 추가·삭제·변경은 사용자에게 보여 확인받는다. 백업이 `output\holiday-refresh\<시각>\holidays.py`에 있다.

- [ ] **Step 3: 갱신된 데이터로 검사**

Run: `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_date_time_calculator.py tests/test_ui_date_time_calculator.py tests/test_holiday_notice.py tests/test_ui.py`
Expected: `passed`

- [ ] **Step 4: 기록과 커밋**

작업 기록에 응답 형식, 변경 목록, 실행 ID를 남긴다.

```bash
git add holidays.py docs/work/2026-10-20-holiday-data-refresh.md
git commit -m "data: 공휴일 데이터 갱신 (같은 날 이름 합치기 반영)"
```

release(EXE 빌드)와 push는 이 계획 밖이다. 다음 버전 release 때 사용자가 PowerShell에서 실행하며, 그때 공휴일 단계가 "최신 확인"으로 지나가는지 본다.
