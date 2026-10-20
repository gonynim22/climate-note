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
