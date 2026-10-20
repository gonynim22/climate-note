# tests/test_fetch_data.py - 공휴일/음력 데이터 검증 헬퍼 테스트
import fetch_data
import http.client
import holidays
import io
import os
import urllib.error
import urllib.parse
import urllib.request
import urllib.response

import pytest


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
    (fetch_data.fetch_lunar_month, lun_item(ld="x")),
    (fetch_data.fetch_lunar_month, lun_item(m=None)),
])
def test_missing_or_bad_fields_are_data_failures(monkeypatch, fetch, item):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: api_xml(item))
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


def year_of(data, y):
    return {k: v for k, v in data.items() if k.startswith(f"{y}-")}


def test_merge_holiday_names_keeps_api_order_and_dedupes():
    entries = [{"date": "2025-05-05", "name": "어린이날"}, {"date": "2025-05-05", "name": "부처님오신날"},
               {"date": "2025-05-05", "name": "어린이날"}, {"date": "2025-05-06", "name": "대체공휴일"}]
    assert fetch_data.merge_holiday_names(entries) == {
        "2025-05-05": "어린이날·부처님오신날", "2025-05-06": "대체공휴일"}


def test_missing_core_names_accepts_merged_names():
    y27 = year_of(holidays.KOREAN_HOLIDAYS, 2027)
    assert fetch_data.missing_core_names(y27, 2027) == []
    renamed = {**y27, "2027-03-01": "삼일절·임시공휴일"}
    assert fetch_data.missing_core_names(renamed, 2027) == []
    deleted = {k: v for k, v in y27.items() if k != "2027-03-01"}
    assert fetch_data.missing_core_names(deleted, 2027) == ["삼일절"]


def test_verify_requires_core_names_every_year():
    class Stub:
        KOREAN_HOLIDAYS = {k: v for k, v in holidays.KOREAN_HOLIDAYS.items() if k != "2026-10-09"}
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
        return [{"date": k, "name": v} for k, v in year_of(holidays.KOREAN_HOLIDAYS, year).items()
                if k.startswith(prefix)]

    monkeypatch.setattr(fetch_data, "fetch_holidays", fake)
    monkeypatch.setattr(fetch_data, "_pause", lambda: None)


def test_fetch_holiday_years_requests_twelve_months_and_skips_empty_years(monkeypatch):
    calls = []
    fake_fetch_for(monkeypatch, calls)
    result = fetch_data.fetch_holiday_years([2027, 2040])
    assert set(result) == {2027}
    assert len(calls) == 24
    assert result[2027] == year_of(holidays.KOREAN_HOLIDAYS, 2027)


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


def test_select_excludes_incomplete_new_year():
    kh = holidays.KOREAN_HOLIDAYS
    fetched = {y: year_of(kh, y) for y in (2025, 2026, 2027)}
    fetched[2028] = {"2028-04-12": "국회의원선거일"}
    merged, excluded = fetch_data.select_holiday_years(fetched, {2025, 2026, 2027})
    assert not any(k.startswith("2028-") for k in merged)
    assert excluded == [2028]
    assert merged == kh


@pytest.mark.parametrize("case", ["missing", "lost_chuseok"])
def test_select_fails_when_existing_year_loses_core_or_disappears(case):
    kh = holidays.KOREAN_HOLIDAYS
    fetched = {y: year_of(kh, y) for y in (2025, 2026, 2027)}
    if case == "missing":
        del fetched[2026]
    else:
        fetched[2026] = {k: v for k, v in fetched[2026].items() if "추석" not in v}
    with pytest.raises(fetch_data.FetchError) as exc:
        fetch_data.select_holiday_years(fetched, {2025, 2026, 2027})
    assert exc.value.environment is False
    assert "2026" in str(exc.value)


# ── 파일 쓰기·비교·갱신 진입점 ──
from pathlib import Path


def _current_by_year():
    years = {}
    for date, name in holidays.KOREAN_HOLIDAYS.items():
        years.setdefault(int(date[:4]), {})[date] = name
    return years


def _synthetic_2028():
    return {d.replace("2027-", "2028-", 1): n
            for d, n in holidays.KOREAN_HOLIDAYS.items() if d.startswith("2027-")}


def _copy_module(tmp_path):
    target = tmp_path / "holidays.py"
    target.write_bytes(Path(holidays.__file__).read_bytes())
    return target


def _leftovers(tmp_path):
    return [p.name for p in tmp_path.iterdir() if p.name != "holidays.py"]


def test_render_reproduces_current_module_exactly():
    text = fetch_data.render_holidays_module(holidays.KOREAN_HOLIDAYS, holidays.LUNAR_MAPPING)
    assert text == Path(holidays.__file__).read_text(encoding="utf-8")


def test_render_escapes_names_round_trip(tmp_path):
    hol = dict(holidays.KOREAN_HOLIDAYS)
    hol["2027-12-25"] = 'a"b\c\nd'
    path = tmp_path / "holidays.py"
    path.write_text(fetch_data.render_holidays_module(hol, holidays.LUNAR_MAPPING), encoding="utf-8")
    got_hol, got_lunar = fetch_data.read_holidays_module(path)
    assert got_hol == hol
    assert got_lunar == holidays.LUNAR_MAPPING


def test_write_replaces_after_verify_and_backs_up(tmp_path):
    target = _copy_module(tmp_path)
    old_bytes = target.read_bytes()
    new_hol = {**holidays.KOREAN_HOLIDAYS, **_synthetic_2028()}
    backup = fetch_data.write_holidays_module(target, new_hol, holidays.LUNAR_MAPPING, tmp_path / "bak")
    assert backup.read_bytes() == old_bytes
    got_hol, got_lunar = fetch_data.read_holidays_module(target)
    assert got_hol == new_hol and any(d.startswith("2028-") for d in got_hol)
    assert got_lunar == holidays.LUNAR_MAPPING
    assert not list(tmp_path.glob("*.tmp"))
    assert sorted(_leftovers(tmp_path)) == ["bak"]


def test_write_keeps_original_when_verify_fails(tmp_path):
    target = _copy_module(tmp_path)
    old_bytes = target.read_bytes()
    bad = {d: n for d, n in holidays.KOREAN_HOLIDAYS.items() if d != "2026-10-09"}
    with pytest.raises(fetch_data.FetchError) as info:
        fetch_data.write_holidays_module(target, bad, holidays.LUNAR_MAPPING, tmp_path / "bak")
    assert info.value.environment is False
    assert target.read_bytes() == old_bytes
    assert _leftovers(tmp_path) == []


def test_write_keeps_original_when_replace_fails(tmp_path, monkeypatch):
    target = _copy_module(tmp_path)
    old_bytes = target.read_bytes()

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(fetch_data.os, "replace", failing_replace)
    new_hol = {**holidays.KOREAN_HOLIDAYS, **_synthetic_2028()}
    with pytest.raises(OSError):
        fetch_data.write_holidays_module(target, new_hol, holidays.LUNAR_MAPPING, tmp_path / "bak")
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


def _modified(change):
    by_year = {y: dict(v) for y, v in _current_by_year().items()}
    change(by_year)
    return by_year


@pytest.mark.parametrize("case", ["same", "added", "removed", "renamed"])
def test_refresh_statuses(tmp_path, monkeypatch, case):
    target = _copy_module(tmp_path)
    old_bytes = target.read_bytes()
    backup_dir = tmp_path / "bak"

    def change(by_year):
        if case == "added":
            by_year[2028] = _synthetic_2028()
        elif case == "removed":
            del by_year[2026]["2026-10-05"]
        elif case == "renamed":
            by_year[2025]["2025-05-05"] = "어린이날·부처님오신날"

    _fake_fetch(monkeypatch, _modified(change))
    result = fetch_data.refresh_holidays(target, backup_dir=backup_dir)
    if case == "same":
        assert result.status == "up_to_date"
        assert target.read_bytes() == old_bytes and result.backup is None
    elif case == "added":
        assert result.status == "updated"
        got_hol, got_lunar = fetch_data.read_holidays_module(target)
        assert any(d.startswith("2028-") for d in got_hol)
        assert got_lunar == holidays.LUNAR_MAPPING
        assert result.backup.parent == backup_dir and result.backup.exists()
        assert result.years == (2025, 2028)
    elif case == "removed":
        assert result.status == "blocked"
        assert target.read_bytes() == old_bytes
        assert result.diff.removed == {"2026-10-05": "대체공휴일(개천절)"}
    else:
        assert result.status == "blocked"
        assert target.read_bytes() == old_bytes
        assert "2025-05-05" in result.diff.renamed
    assert result.checked_at[:2] == "20" and "T" in result.checked_at


def test_refresh_reports_excluded_new_year(tmp_path, monkeypatch):
    target = _copy_module(tmp_path)
    old_bytes = target.read_bytes()
    _fake_fetch(monkeypatch, _modified(lambda b: b.__setitem__(2028, {"2028-06-03": "선거일"})))
    result = fetch_data.refresh_holidays(target, backup_dir=tmp_path / "bak")
    assert result.status == "up_to_date"
    assert result.excluded_years == [2028]
    assert target.read_bytes() == old_bytes


def test_refresh_always_refetches_existing_years(tmp_path, monkeypatch):
    target = _copy_module(tmp_path)
    seen = []
    _fake_fetch(monkeypatch, _current_by_year(), seen)
    fetch_data.refresh_holidays(target, backup_dir=tmp_path / "bak", years=range(2028, 2030))
    assert {2025, 2026, 2027} <= set(seen[0])


def test_main_returns_one_and_keeps_file_on_failure(tmp_path, monkeypatch, capsys):
    target = _copy_module(tmp_path)
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
    target = _copy_module(tmp_path)
    monkeypatch.setattr(fetch_data, "HOLIDAYS_PATH", target)
    monkeypatch.setattr(fetch_data, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_data, "API_KEY", "")
    calls = []
    monkeypatch.setattr(fetch_data, "fetch_lunar_years", lambda y: calls.append(y))
    monkeypatch.setattr(fetch_data, "fetch_holiday_years", lambda y: calls.append(y))
    assert fetch_data.main() == 1
    assert calls == []
