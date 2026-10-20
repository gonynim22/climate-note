# tests/test_fetch_data.py - 공휴일/음력 데이터 검증 헬퍼 테스트
import fetch_data
import http.client
import holidays
import io
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import urllib.response

import pytest


@pytest.fixture(autouse=True)
def _offline_api(monkeypatch):
    """실제 키·네트워크를 쓰지 않는다. 키가 필요한 시험은 가짜 값을 직접 넣는다."""
    monkeypatch.setattr(fetch_data, "API_KEY", "")

    def no_network(*_args, **_kwargs):
        pytest.fail("시험이 실제 API를 부르려 했습니다")

    monkeypatch.setattr(fetch_data._OPENER, "open", no_network)


def test_default_fixture_blocks_real_key_and_network(monkeypatch):
    assert fetch_data.API_KEY == ""
    monkeypatch.setattr(fetch_data, "API_KEY", "synthetic-key-7")
    with pytest.raises(pytest.fail.Exception):
        fetch_data.fetch_holidays(2026, 1)


def test_verify_passes_on_current_data():
    """현재 번들 데이터(공휴일 ~2027, 음력 ~2050)는 검증 통과."""
    ok, msg = fetch_data.verify_holiday_data(holidays)
    assert ok, msg


def test_verify_fails_on_deficient_data():
    """범위/건수가 부족한 데이터는 검증 실패."""
    class Stub:
        KOREAN_HOLIDAYS = {"2025-01-01": "x"}
        LUNAR_MAPPING = {"2025-01-01": "12.1"}
    ok, msg = fetch_data.verify_holiday_data(Stub)
    assert not ok


@pytest.mark.parametrize("scheme", ["file", "http", "ftp"])
def test_api_opener_rejects_non_https_even_with_https_proxy(tmp_path, monkeypatch, scheme):
    source = tmp_path / "synthetic.txt"
    source.write_text("synthetic only", encoding="utf-8")
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {
        "http": "https://proxy.invalid:443", "file": "https://proxy.invalid:443",
        "ftp": "https://proxy.invalid:443", "https": "http://proxy.invalid:8080",
        "no": "bypass.invalid",
    })
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)

    def unexpected_network(*args):
        pytest.fail("비HTTPS 요청이 네트워크 처리기에 도달함")

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", unexpected_network)
    opener = fetch_data._https_only_opener()
    url = source.as_uri() if scheme == "file" else f"{scheme}://calendar-probe.invalid/"
    with pytest.raises(urllib.error.URLError):
        opener.open(url, timeout=1)
    assert source.read_text(encoding="utf-8") == "synthetic only"


def test_https_opener_preserves_https_proxy(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://proxy.invalid:8080"})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    seen = []

    def transport(handler, request):
        seen.append((request.type, request.host, request._tunnel_host))
        response = urllib.response.addinfourl(io.BytesIO(b"ok"), {}, request.full_url, 200)
        response.msg = "OK"
        return response

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", transport)
    with fetch_data._https_only_opener().open("https://calendar-probe.invalid/", timeout=1) as response:
        assert response.read() == b"ok"
    assert seen == [("https", "proxy.invalid:8080", "calendar-probe.invalid")]


def api_xml(items="", code="00", total=None):
    total = items.count("<item>") if total is None else total
    return (f"<response><header><resultCode>{code}</resultCode><resultMsg>MSG</resultMsg></header>"
            f"<body><items>{items}</items><numOfRows>50</numOfRows><pageNo>1</pageNo>"
            f"<totalCount>{total}</totalCount></body></response>")


KEY_ERROR = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
             "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
             "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")

BOTH = pytest.mark.parametrize("fetch", [fetch_data.fetch_holidays, fetch_data.fetch_lunar_month])


def hol_item(loc="20260101", name="1월1일", flag="Y"):
    return (f"<item><locdate>{loc}</locdate>" + (f"<dateName>{name}</dateName>" if name is not None else "")
            + f"<isHoliday>{flag}</isHoliday></item>")


def lun_item(y="2026", m="01", d="01", lm="11", ld="13"):
    parts = [("solYear", y), ("solMonth", m), ("solDay", d), ("lunMonth", lm), ("lunDay", ld)]
    return "<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in parts if v is not None) + "</item>"


def test_api_requests_use_fixed_https_service_url(monkeypatch):
    seen = []

    def fake_open(url, timeout):
        seen.append((urllib.parse.urlsplit(url), timeout))
        return io.BytesIO(api_xml().encode("utf-8"))

    monkeypatch.setattr(fetch_data, "API_KEY", "synthetic +& key")
    monkeypatch.setattr(fetch_data._OPENER, "open", fake_open)
    assert fetch_data.fetch_holidays(2026, 1) == []
    assert fetch_data.fetch_lunar_month(2026, 1) == []
    assert [(url.scheme, url.netloc, url.path, timeout) for url, timeout in seen] == [
        ("https", "apis.data.go.kr", "/B090041/openapi/service/SpcdeInfoService/getRestDeInfo", 10),
        ("https", "apis.data.go.kr", "/B090041/openapi/service/LrsrCldInfoService/getLunCalInfo", 10),
    ]
    for url, _timeout in seen:
        assert urllib.parse.parse_qs(url.query) == {
            "serviceKey": ["synthetic +& key"], "solYear": ["2026"], "solMonth": ["01"], "numOfRows": ["50"],
        }


def test_fetch_holidays_parses_api_xml(monkeypatch):
    xml = api_xml(hol_item() + hol_item("20260102", "평일", "N"))
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    assert fetch_data.fetch_holidays(2026, 1) == [{"date": "2026-01-01", "name": "1월1일"}]


def test_fetch_lunar_parses_api_xml(monkeypatch):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: api_xml(lun_item()))
    assert fetch_data.fetch_lunar_month(2026, 1) == [{"date": "2026-01-01", "lunar": "11.13"}]


@BOTH
@pytest.mark.parametrize("xml", [
    '<!DOCTYPE response [<!ENTITY a "01">]><response><header><resultCode>00</resultCode></header>'
    '<body><totalCount>1</totalCount><items><item>'
    '<locdate>20260101</locdate><dateName>test</dateName><isHoliday>Y</isHoliday>'
    '<solYear>2026</solYear><solMonth>&a;</solMonth><solDay>01</solDay>'
    '<lunMonth>&a;</lunMonth><lunDay>01</lunDay></item></items></body></response>',
    '<response><body>',
])
def test_fetch_rejects_unsafe_or_malformed_xml(monkeypatch, fetch, xml):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is False


@BOTH
@pytest.mark.parametrize("xml", [api_xml(code="22"), KEY_ERROR])
def test_error_result_code_is_environment_failure(monkeypatch, fetch, xml):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is True
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(exc.value) or "22" in str(exc.value)


@BOTH
@pytest.mark.parametrize("xml", [api_xml(code="03"), api_xml(total=0)])
def test_nodata_and_empty_responses_are_not_failures(monkeypatch, fetch, xml):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    assert fetch(2026, 1) == []


@BOTH
def test_short_page_is_data_failure(monkeypatch, fetch):
    xml = api_xml(hol_item() + lun_item(), total=3)
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is False


@pytest.mark.parametrize("fetch, item", [
    (fetch_data.fetch_holidays, hol_item(name=None)),
    (fetch_data.fetch_holidays, hol_item(loc="2026011")),
    (fetch_data.fetch_holidays, hol_item(flag="X")),
    (fetch_data.fetch_holidays, hol_item(loc="２０２６０１０１")),  # 전각 숫자
    (fetch_data.fetch_lunar_month, lun_item(ld="x")),
    (fetch_data.fetch_lunar_month, lun_item(m=None)),
    (fetch_data.fetch_lunar_month, lun_item(ld="١٣")),  # 아랍 숫자
])
def test_missing_or_bad_fields_are_data_failures(monkeypatch, fetch, item):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: api_xml(item))
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is False


@BOTH
@pytest.mark.parametrize("total", ["²", "１"])
def test_non_ascii_total_count_is_data_failure(monkeypatch, fetch, total):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: api_xml(total=total))
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is False


@BOTH
@pytest.mark.parametrize("error", [
    urllib.error.URLError("boom"),
    urllib.error.HTTPError("https://x/?serviceKey=synthetic-key-7", 500, "err", {}, None),
    TimeoutError(),
    http.client.IncompleteRead(b""),
])
def test_network_errors_are_environment_failures_without_key(monkeypatch, fetch, error):
    def fake_open(url, timeout):
        raise error

    monkeypatch.setattr(fetch_data, "API_KEY", "synthetic-key-7")
    monkeypatch.setattr(fetch_data._OPENER, "open", fake_open)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is True
    assert "synthetic-key-7" not in str(exc.value)
    assert exc.value.__cause__ is None


@BOTH
def test_missing_key_is_environment_failure(monkeypatch, fetch):
    calls = []
    monkeypatch.setattr(fetch_data, "API_KEY", "")
    monkeypatch.setattr(fetch_data._OPENER, "open", lambda *a, **k: calls.append(a))
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch(2026, 1)
    assert exc.value.environment is True
    assert calls == []


@BOTH
@pytest.mark.parametrize("xml", ["<html><body>Proxy error</body></html>", "<html><body>"])
def test_html_gateway_page_is_failure(monkeypatch, fetch, xml):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    with pytest.raises(fetch_data.FetchError):
        fetch(2026, 1)


def test_load_api_key_reads_root_env_without_touching_environ(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LUNAR_API_KEY=abc\n", encoding="utf-8")
    monkeypatch.delenv("LUNAR_API_KEY", raising=False)
    assert fetch_data.load_api_key(env_file) == "abc"
    assert "LUNAR_API_KEY" not in os.environ
    monkeypatch.setenv("LUNAR_API_KEY", "env")
    assert fetch_data.load_api_key(env_file) == "env"
    monkeypatch.delenv("LUNAR_API_KEY")
    assert fetch_data.load_api_key(tmp_path / "missing.env") == ""


# ── 시험용 고정 공휴일 ──
# 실제 holidays.py와 무관하게 고정한다. 첫 실제 갱신(같은 날 이름 합치기)이나
# 새 연도 추가 release 뒤에도 같은 결과가 나와야 하기 때문이다.
BASE_YEARS = (2025, 2026, 2027)
NEXT_YEAR = BASE_YEARS[-1] + 1
EXTENDED_YEARS = (*BASE_YEARS, NEXT_YEAR)
_SYNTHETIC_DAYS = {
    "01-01": "1월1일", "02-09": "설날", "02-10": "설날", "02-11": "설날", "03-01": "삼일절",
    "05-05": "어린이날", "05-15": "부처님오신날", "06-06": "현충일", "08-15": "광복절",
    "09-20": "추석", "09-21": "추석", "09-22": "추석", "10-03": "개천절",
    "10-05": "대체공휴일(개천절)", "10-09": "한글날", "12-25": "기독탄신일",
}


def synthetic_year(year):
    """핵심 이름 8개를 모두 갖춘 시험용 한 해 (날짜는 형식만 맞춘 가짜 값)."""
    return {f"{year}-{day}": name for day, name in _SYNTHETIC_DAYS.items()}


def synthetic_holidays(years=BASE_YEARS):
    return {date: name for year in years for date, name in synthetic_year(year).items()}


def test_merge_holiday_names_keeps_api_order_and_dedupes():
    entries = [{"date": "2025-05-05", "name": "어린이날"}, {"date": "2025-05-05", "name": "부처님오신날"},
               {"date": "2025-05-05", "name": "어린이날"}, {"date": "2025-05-06", "name": "대체공휴일"}]
    assert fetch_data.merge_holiday_names(entries) == {
        "2025-05-05": "어린이날·부처님오신날", "2025-05-06": "대체공휴일"}


def test_missing_core_names_accepts_merged_names():
    y27 = synthetic_year(2027)
    assert fetch_data.missing_core_names(y27, 2027) == []
    renamed = {**y27, "2027-03-01": "삼일절·임시공휴일"}
    assert fetch_data.missing_core_names(renamed, 2027) == []
    deleted = {k: v for k, v in y27.items() if k != "2027-03-01"}
    assert fetch_data.missing_core_names(deleted, 2027) == ["삼일절"]


def test_verify_requires_core_names_every_year():
    class Stub:
        KOREAN_HOLIDAYS = {k: v for k, v in synthetic_holidays().items() if k != "2026-10-09"}
        LUNAR_MAPPING = holidays.LUNAR_MAPPING
    ok, msg = fetch_data.verify_holiday_data(Stub)
    assert ok is False
    assert "2026" in msg and "한글날" in msg


def fake_fetch_for(monkeypatch, calls):
    def fake(year, month):
        calls.append((year, month))
        if year != 2027:
            return []
        prefix = f"{year}-{month:02d}-"
        return [{"date": k, "name": v} for k, v in synthetic_year(year).items() if k.startswith(prefix)]

    monkeypatch.setattr(fetch_data, "fetch_holidays", fake)
    monkeypatch.setattr(fetch_data, "_pause", lambda: None)


def test_fetch_holiday_years_requests_twelve_months_and_skips_empty_years(monkeypatch):
    calls = []
    fake_fetch_for(monkeypatch, calls)
    result = fetch_data.fetch_holiday_years([2027, 2040])
    assert set(result) == {2027}
    assert len(calls) == 24
    assert result[2027] == synthetic_year(2027)


def test_fetch_holiday_years_stops_on_first_failure(monkeypatch):
    calls = []

    def fake(year, month):
        calls.append((year, month))
        if month == 3:
            raise fetch_data.FetchError("x", environment=False)
        return []

    monkeypatch.setattr(fetch_data, "fetch_holidays", fake)
    monkeypatch.setattr(fetch_data, "_pause", lambda: None)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch_data.fetch_holiday_years([2027])
    assert exc.value.environment is False
    assert calls == [(2027, 1), (2027, 2), (2027, 3)]


@pytest.mark.parametrize("complete", [True, False])
def test_select_adds_complete_new_year_and_excludes_incomplete(complete):
    fetched = {y: synthetic_year(y) for y in BASE_YEARS}
    fetched[NEXT_YEAR] = synthetic_year(NEXT_YEAR) if complete else {f"{NEXT_YEAR}-04-12": "국회의원선거일"}
    merged, excluded = fetch_data.select_holiday_years(fetched, set(BASE_YEARS))
    if complete:  # 기존 연도와 핵심 이름을 갖춘 새 연도를 함께 고른다
        assert merged == synthetic_holidays(EXTENDED_YEARS)
        assert excluded == []
    else:
        assert merged == synthetic_holidays()
        assert excluded == [NEXT_YEAR]


@pytest.mark.parametrize("case", ["missing", "lost_chuseok"])
def test_select_fails_when_existing_year_loses_core_or_disappears(case):
    fetched = {y: synthetic_year(y) for y in BASE_YEARS}
    if case == "missing":
        del fetched[2026]
    else:
        fetched[2026] = {k: v for k, v in fetched[2026].items() if "추석" not in v}
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch_data.select_holiday_years(fetched, set(BASE_YEARS))
    assert exc.value.environment is False
    assert "2026" in str(exc.value)


def _lunar_months(empty_march=None):
    """달마다 음력 1건을 돌려주는 가짜 응답. empty_march를 주면 3월만 그 응답."""
    def fake_get(_service, year, month):
        if month == 3 and empty_march is not None:
            return empty_march
        return api_xml(lun_item(f"{year:04d}", f"{month:02d}"))
    return fake_get


@pytest.mark.parametrize("xml", [api_xml(code="03"), api_xml(total=0)], ids=["code03", "empty00"])
def test_lunar_years_fail_on_empty_month(monkeypatch, xml):
    monkeypatch.setattr(fetch_data, "_api_get", _lunar_months(empty_march=xml))
    monkeypatch.setattr(fetch_data, "_pause", lambda: None)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch_data.fetch_lunar_years([2026])
    assert exc.value.environment is False
    assert "2026-03" in str(exc.value)


def test_lunar_years_collect_every_month(monkeypatch):
    monkeypatch.setattr(fetch_data, "_api_get", _lunar_months())
    monkeypatch.setattr(fetch_data, "_pause", lambda: None)
    lunar = fetch_data.fetch_lunar_years([2026])
    assert len(lunar) == 12
    assert lunar["2026-03-01"] == "11.13"


# ── 파일 쓰기·비교·갱신 진입점 ──
from pathlib import Path


def _write_module(tmp_path, years=BASE_YEARS):
    """고정 시험 공휴일로 tmp_path/holidays.py를 만든다 (음력은 번들 값)."""
    target = tmp_path / "holidays.py"
    target.write_text(fetch_data.render_holidays_module(synthetic_holidays(years), holidays.LUNAR_MAPPING),
                      encoding="utf-8")
    return target


def _leftovers(tmp_path):
    return [p.name for p in tmp_path.iterdir() if p.name != "holidays.py"]


def test_render_reproduces_current_module_exactly():
    text = fetch_data.render_holidays_module(holidays.KOREAN_HOLIDAYS, holidays.LUNAR_MAPPING)
    assert text == Path(holidays.__file__).read_text(encoding="utf-8")


def test_render_escapes_names_round_trip(tmp_path):
    hol = synthetic_holidays()
    hol["2027-12-25"] = 'a"b\\c\nd'
    path = tmp_path / "holidays.py"
    path.write_text(fetch_data.render_holidays_module(hol, holidays.LUNAR_MAPPING), encoding="utf-8")
    got_hol, got_lunar = fetch_data.read_holidays_module(path)
    assert got_hol == hol
    assert got_lunar == holidays.LUNAR_MAPPING


def test_write_replaces_after_verify_and_backs_up(tmp_path):
    target = _write_module(tmp_path)
    old_bytes = target.read_bytes()
    new_hol = synthetic_holidays(EXTENDED_YEARS)
    backup = fetch_data.write_holidays_module(target, new_hol, holidays.LUNAR_MAPPING, tmp_path / "bak")
    assert backup.read_bytes() == old_bytes
    got_hol, got_lunar = fetch_data.read_holidays_module(target)
    assert got_hol == new_hol
    assert got_lunar == holidays.LUNAR_MAPPING
    assert not list(tmp_path.glob("*.tmp"))
    assert sorted(_leftovers(tmp_path)) == ["bak"]


def test_write_keeps_original_when_verify_fails(tmp_path):
    target = _write_module(tmp_path)
    old_bytes = target.read_bytes()
    bad = {d: n for d, n in synthetic_holidays().items() if d != "2026-10-09"}
    with pytest.raises(fetch_data.FetchError) as info:
        fetch_data.write_holidays_module(target, bad, holidays.LUNAR_MAPPING, tmp_path / "bak")
    assert info.value.environment is False
    assert target.read_bytes() == old_bytes
    assert _leftovers(tmp_path) == []


def test_write_keeps_original_when_replace_fails(tmp_path, monkeypatch):
    target = _write_module(tmp_path)
    old_bytes = target.read_bytes()

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(fetch_data.os, "replace", failing_replace)
    with pytest.raises(OSError):
        fetch_data.write_holidays_module(target, synthetic_holidays(EXTENDED_YEARS), holidays.LUNAR_MAPPING,
                                         tmp_path / "bak")
    assert target.read_bytes() == old_bytes
    assert not list(tmp_path.glob("*.tmp"))


def test_diff_holidays_classifies_added_removed_renamed():
    diff = fetch_data.diff_holidays({"a": "1", "b": "2", "c": "3"}, {"a": "1", "b": "X", "d": "4"})
    assert diff.added == {"d": "4"}
    assert diff.removed == {"c": "3"}
    assert diff.renamed == {"b": ("2", "X")}


def _fake_fetch(monkeypatch, by_year, seen=None):
    def fake(years):
        if seen is not None:
            seen.append(sorted(years))
        return by_year

    monkeypatch.setattr(fetch_data, "fetch_holiday_years", fake)


# extended: 마지막 연도가 하나 늘어난 파일(새 연도 추가 release 뒤)에서 다음 release를 흉내 낸다.
SPANS = pytest.mark.parametrize("years", [BASE_YEARS, EXTENDED_YEARS], ids=["base", "extended"])


@SPANS
@pytest.mark.parametrize("case", ["same", "added", "removed", "renamed"])
def test_refresh_statuses(tmp_path, monkeypatch, case, years):
    target = _write_module(tmp_path, years)
    old_bytes = target.read_bytes()
    old = synthetic_holidays(years)
    backup_dir = tmp_path / "bak"
    new_year = years[-1] + 1
    by_year = {y: synthetic_year(y) for y in years}
    if case == "added":
        by_year[new_year] = synthetic_year(new_year)
    elif case == "removed":
        del by_year[2026]["2026-10-05"]
    elif case == "renamed":
        by_year[2025]["2025-05-05"] = "어린이날·부처님오신날"

    _fake_fetch(monkeypatch, by_year)
    result = fetch_data.refresh_holidays(target, backup_dir=backup_dir)
    if case == "same":
        assert result.status == "up_to_date"
        assert target.read_bytes() == old_bytes and result.backup is None
        assert result.years == (years[0], years[-1])
    elif case == "added":
        assert result.status == "updated"
        assert result.diff.added == synthetic_year(new_year)
        got_hol, got_lunar = fetch_data.read_holidays_module(target)
        assert got_hol == {**old, **synthetic_year(new_year)}
        assert got_lunar == holidays.LUNAR_MAPPING
        assert result.backup.parent == backup_dir and result.backup.read_bytes() == old_bytes
        assert result.years == (years[0], new_year)
    elif case == "removed":
        assert result.status == "blocked"
        assert target.read_bytes() == old_bytes and result.backup is None
        assert result.diff.removed == {"2026-10-05": old["2026-10-05"]}
    else:
        assert result.status == "blocked"
        assert target.read_bytes() == old_bytes and result.backup is None
        assert result.diff.renamed == {"2025-05-05": (old["2025-05-05"], "어린이날·부처님오신날")}
    assert result.checked_at[:2] == "20" and "T" in result.checked_at


@SPANS
def test_refresh_reports_excluded_new_year(tmp_path, monkeypatch, years):
    target = _write_module(tmp_path, years)
    old_bytes = target.read_bytes()
    new_year = years[-1] + 1
    by_year = {y: synthetic_year(y) for y in years}
    by_year[new_year] = {f"{new_year}-06-03": "선거일"}
    _fake_fetch(monkeypatch, by_year)
    result = fetch_data.refresh_holidays(target, backup_dir=tmp_path / "bak")
    assert result.status == "up_to_date"
    assert result.excluded_years == [new_year]
    assert target.read_bytes() == old_bytes


def test_refresh_always_refetches_existing_years(tmp_path, monkeypatch):
    target = _write_module(tmp_path)
    seen = []
    _fake_fetch(monkeypatch, {y: synthetic_year(y) for y in BASE_YEARS}, seen)
    fetch_data.refresh_holidays(target, backup_dir=tmp_path / "bak", years=range(NEXT_YEAR, NEXT_YEAR + 2))
    assert set(BASE_YEARS) <= set(seen[0])


# 손상·손편집·병합 충돌로 읽을 수 없는 holidays.py와 그때의 예외 이름
CORRUPT_MODULES = [
    ("<<<<<<< HEAD\nKOREAN_HOLIDAYS = {}\n=======\nKOREAN_HOLIDAYS = {}\n>>>>>>> other\n", "SyntaxError"),
    ("LUNAR_MAPPING = {}\n", "KeyError"),
    ("KOREAN_HOLIDAYS = UNKNOWN\n", "NameError"),
    ("KOREAN_HOLIDAYS = 1\nLUNAR_MAPPING = {}\n", "TypeError"),
    ('KOREAN_HOLIDAYS = {"20x5-01-01": "1월1일"}\nLUNAR_MAPPING = {}\n', "ValueError"),
]
CORRUPT_IDS = [name for _text, name in CORRUPT_MODULES]


def _corrupt_module(tmp_path, text):
    target = tmp_path / "holidays.py"
    target.write_text(text, encoding="utf-8")
    return target


def _forbid_fetch(monkeypatch):
    def forbidden(years):
        raise AssertionError("읽지 못한 파일인데 받기를 시작함")

    monkeypatch.setattr(fetch_data, "fetch_holiday_years", forbidden)
    monkeypatch.setattr(fetch_data, "fetch_lunar_years", forbidden)


@pytest.mark.parametrize("text, error_name", CORRUPT_MODULES, ids=CORRUPT_IDS)
def test_refresh_corrupt_module_is_data_failure(tmp_path, monkeypatch, text, error_name):
    target = _corrupt_module(tmp_path, text)
    _forbid_fetch(monkeypatch)
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch_data.refresh_holidays(target, backup_dir=tmp_path / "bak")
    assert exc.value.environment is False
    assert error_name in str(exc.value)
    assert exc.value.__cause__ is None
    assert target.read_text(encoding="utf-8") == text
    assert _leftovers(tmp_path) == []


@pytest.mark.parametrize("text, error_name", CORRUPT_MODULES[:2], ids=CORRUPT_IDS[:2])
def test_main_corrupt_module_returns_one(tmp_path, monkeypatch, capsys, text, error_name):
    target = _corrupt_module(tmp_path, text)
    monkeypatch.setattr(fetch_data, "HOLIDAYS_PATH", target)
    monkeypatch.setattr(fetch_data, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_data, "API_KEY", "synthetic-key-7")
    _forbid_fetch(monkeypatch)
    assert fetch_data.main() == 1
    out = capsys.readouterr().out
    assert "ERROR" in out and error_name in out
    assert target.read_text(encoding="utf-8") == text
    assert not (tmp_path / "output").exists()


def test_main_accepts_rename_writes_backup_and_hides_key(tmp_path, monkeypatch, capsys):
    key = "synthetic-key-main"
    target = _write_module(tmp_path)
    old_bytes = target.read_bytes()
    monkeypatch.setattr(fetch_data, "HOLIDAYS_PATH", target)
    monkeypatch.setattr(fetch_data, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_data, "API_KEY", key)
    by_year = {y: synthetic_year(y) for y in BASE_YEARS}
    by_year[2025]["2025-05-05"] = "어린이날·부처님오신날"
    lunar = dict(holidays.LUNAR_MAPPING)
    lunar[min(lunar)] = "0.0"  # 시험용 음력 변경 1건
    monkeypatch.setattr(fetch_data, "fetch_lunar_years", lambda years: lunar)
    monkeypatch.setattr(fetch_data, "fetch_holiday_years", lambda years: by_year)
    assert fetch_data.main() == 0
    got_hol, got_lunar = fetch_data.read_holidays_module(target)
    assert got_hol["2025-05-05"] == "어린이날·부처님오신날"
    assert got_lunar == lunar
    backups = list((tmp_path / "output" / "holiday-refresh").glob("*/holidays.py"))
    assert len(backups) == 1 and backups[0].read_bytes() == old_bytes
    assert re.fullmatch(r"\d{8}-\d{6}", backups[0].parent.name)
    out = capsys.readouterr().out
    assert "API에서 받는 중" in out
    assert "변경 2025-05-05 어린이날 -> 어린이날·부처님오신날" in out
    assert "음력: 추가 0건, 삭제 0건, 변경 1건" in out
    assert key not in out


def test_main_returns_one_and_keeps_file_on_failure(tmp_path, monkeypatch, capsys):
    target = _write_module(tmp_path)
    old_bytes = target.read_bytes()
    monkeypatch.setattr(fetch_data, "HOLIDAYS_PATH", target)
    monkeypatch.setattr(fetch_data, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_data, "API_KEY", "k")

    def failing(years):
        raise fetch_data.FetchError("음력 요청 실패 (URLError)", environment=True)

    monkeypatch.setattr(fetch_data, "fetch_lunar_years", failing)
    assert fetch_data.main() == 1
    assert target.read_bytes() == old_bytes
    out = capsys.readouterr().out
    assert "http" not in out and "serviceKey" not in out
    assert not (tmp_path / "output").exists()


def test_main_missing_key_returns_one(tmp_path, monkeypatch):
    target = _write_module(tmp_path)
    monkeypatch.setattr(fetch_data, "HOLIDAYS_PATH", target)
    monkeypatch.setattr(fetch_data, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_data, "API_KEY", "")
    calls = []
    monkeypatch.setattr(fetch_data, "fetch_lunar_years", lambda y: calls.append(y))
    monkeypatch.setattr(fetch_data, "fetch_holiday_years", lambda y: calls.append(y))
    assert fetch_data.main() == 1
    assert calls == []
