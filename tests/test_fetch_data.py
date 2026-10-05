# tests/test_fetch_data.py - 공휴일/음력 데이터 검증 헬퍼 테스트
import fetch_data
import holidays
import io
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


def test_api_requests_use_fixed_https_service_url(monkeypatch):
    seen = []

    def fake_open(url, timeout):
        seen.append((urllib.parse.urlsplit(url), timeout))
        return io.BytesIO(b"<response><body><items/></body></response>")

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
    xml = ("<response><body><items>"
           "<item><locdate>20260101</locdate><dateName>1월1일</dateName><isHoliday>Y</isHoliday></item>"
           "<item><locdate>20260102</locdate><dateName>평일</dateName><isHoliday>N</isHoliday></item>"
           "</items></body></response>")
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    assert fetch_data.fetch_holidays(2026, 1) == [{"date": "2026-01-01", "name": "1월1일"}]


def test_fetch_lunar_parses_api_xml(monkeypatch):
    xml = ("<response><body><items><item><solYear>2026</solYear><solMonth>01</solMonth>"
           "<solDay>01</solDay><lunMonth>11</lunMonth><lunDay>13</lunDay>"
           "</item></items></body></response>")
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    assert fetch_data.fetch_lunar_month(2026, 1) == [{"date": "2026-01-01", "lunar": "11.13"}]


@pytest.mark.parametrize("fetch", [fetch_data.fetch_holidays, fetch_data.fetch_lunar_month])
@pytest.mark.parametrize("xml", [
    '<!DOCTYPE response [<!ENTITY a "01">]><response><body><items><item>'
    '<locdate>20260101</locdate><dateName>test</dateName><isHoliday>Y</isHoliday>'
    '<solYear>2026</solYear><solMonth>&a;</solMonth><solDay>01</solDay>'
    '<lunMonth>&a;</lunMonth><lunDay>01</lunDay></item></items></body></response>',
    '<response><body>',
])
def test_fetch_rejects_unsafe_or_malformed_xml(monkeypatch, fetch, xml):
    monkeypatch.setattr(fetch_data, "_api_get", lambda *args: xml)
    assert fetch(2026, 1) == []
