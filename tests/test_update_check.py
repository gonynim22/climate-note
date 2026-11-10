"""새 버전 확인의 판정·요청: 실제 네트워크 없이 가짜 통신 층으로 검사한다."""
import json
import urllib.request
from pathlib import Path

import pytest

import update_check
from update_check import RELEASES_URL, CheckResult, check_latest, is_newer, parse_version, proxy_for, read_result
from winhttp_get import Response, WinHttpError

OK_BODY = json.dumps([{"tag_name": "v4.7", "upcoming_release": False}]).encode()


class FakeFetch:
    """winhttp_get.https_get 자리. 호출 인자를 기록하고 정해 둔 응답을 돌려주거나 예외를 낸다."""

    def __init__(self, outcome=None):
        self.outcome, self.calls = outcome, []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture
def direct(monkeypatch):
    """프록시 없는 PC."""
    monkeypatch.setattr(update_check, "proxy_for", lambda host: None)


@pytest.mark.parametrize(("older", "newer"), [
    ("v4.6", "v4.7"), ("v4.6", "v4.6a"), ("v4.5a", "v4.6"), ("v4.9", "v4.10"), ("v4.6a", "v4.6b")])
def test_is_newer_orders_versions(older, newer):
    assert is_newer(newer, older) and not is_newer(older, newer) and not is_newer(older, older)


@pytest.mark.parametrize("bad", ["", "4.6", "v4", "v4.6.1", "v4.6A", "v4.6ab", "V4.6", "v4.6\n",
                                 "v٤.٦", pytest.param("v" + "9" * 5000 + ".1", id="long-digits"),
                                 None, 46, ["v4.6"]])
def test_malformed_tag_is_never_newer(bad):
    assert parse_version(bad) is None
    assert not is_newer(bad, "v4.6") and not is_newer("v4.7", bad)


def test_reads_latest_tag():
    assert read_result(OK_BODY) == CheckResult(latest_tag="v4.7")


def test_empty_list_and_upcoming_are_not_failures():
    assert read_result(b"[]") == CheckResult()
    assert read_result(json.dumps([{"tag_name": "v9.9", "upcoming_release": True}]).encode()) == CheckResult()


@pytest.mark.parametrize("body", [b"", b"{", b"{}", b"null", b"[1]", b"[{}]", b'[{"tag_name": 5}]',
                                  b'[{"tag_name": "latest"}]', b"\xff\xfe\x00",
                                  pytest.param(b"[" * 200_000, id="deep-nesting")])
def test_bad_body_is_format_failure(body):
    assert read_result(body) == CheckResult(failure="format")


def test_request_carries_only_fixed_values(direct):
    fetch = FakeFetch(Response(200, OK_BODY))
    assert check_latest(fetch) == CheckResult(latest_tag="v4.7")
    assert fetch.calls == [((RELEASES_URL,), dict(
        headers={"Accept": "application/json"}, user_agent="ClimateNote-UpdateCheck",
        timeout_seconds=10, max_bytes=256 * 1024 + 1, proxy=None))]


def test_proxy_of_the_fixed_host_is_passed_to_the_transport(monkeypatch):
    hosts = []
    monkeypatch.setattr(update_check, "proxy_for", lambda host: hosts.append(host) or "p.invalid:8080")
    fetch = FakeFetch(Response(200, OK_BODY))
    assert check_latest(fetch) == CheckResult(latest_tag="v4.7")
    assert hosts == ["gitlab.aigov.go.kr"] and fetch.calls[0][1]["proxy"] == "p.invalid:8080"


def test_response_size_limit(direct):
    limit = 256 * 1024
    assert check_latest(FakeFetch(Response(200, OK_BODY + b" " * (limit - len(OK_BODY))))) == \
        CheckResult(latest_tag="v4.7")
    assert check_latest(FakeFetch(Response(200, OK_BODY + b" " * (limit + 1 - len(OK_BODY))))) == \
        CheckResult(failure="format")


@pytest.mark.parametrize(("outcome", "failure"), [
    (Response(302, b""), "http-302"), (Response(404, b""), "http-404"),
    (Response(407, b""), "http-407"), (Response(503, b""), "http-503"),
    (Response(199, OK_BODY), "http-199"), (Response(300, OK_BODY), "http-300"),
    (Response(204, b""), "format"),
    (WinHttpError(12002, timed_out=True), "timeout"), (TimeoutError(), "timeout"),
    (WinHttpError(12029), "connection"), (WinHttpError(12175), "connection"),
    (OSError("winhttp.dll"), "connection"), (ValueError("bad"), "connection")])
def test_every_outcome_is_classified_not_raised(direct, outcome, failure):
    assert check_latest(FakeFetch(outcome)) == CheckResult(failure=failure)


def test_default_transport_is_looked_up_at_call_time(direct, monkeypatch):
    fetch = FakeFetch(Response(200, OK_BODY))
    monkeypatch.setattr(update_check.winhttp_get, "https_get", fetch)
    assert check_latest() == CheckResult(latest_tag="v4.7")
    assert len(fetch.calls) == 1


@pytest.mark.parametrize(("proxies", "bypass", "expected"), [
    ({}, False, None), ({"http": "http://p.invalid:8080"}, False, None),
    ({"https": "http://p.invalid:8080"}, False, "p.invalid:8080"),
    ({"https": "p.invalid:8080"}, False, "p.invalid:8080"),
    ({"https": "https://p.invalid:8080/"}, False, "p.invalid:8080"),
    ({"https": "http://p.invalid"}, False, "p.invalid"),
    ({"https": "http://p.invalid:8080"}, True, None)])
def test_proxy_is_read_the_way_urllib_reads_it(monkeypatch, proxies, bypass, expected):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: proxies)
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: bypass)
    assert proxy_for("gitlab.aigov.go.kr") == expected


@pytest.mark.parametrize("address", ["http://user:pw@p.invalid:8080", "http://user@p.invalid:8080",
                                     "http://:8080", "http://", "http://p.invalid:port"])
def test_unusable_proxy_address_is_refused(monkeypatch, address):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": address})
    monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
    with pytest.raises(ValueError):
        proxy_for("gitlab.aigov.go.kr")


def test_refused_proxy_means_connection_failure_without_a_request(monkeypatch):
    def refused(host):
        raise ValueError("프록시 주소에 사용자 정보가 있음")

    monkeypatch.setattr(update_check, "proxy_for", refused)
    fetch = FakeFetch(Response(200, OK_BODY))
    assert check_latest(fetch) == CheckResult(failure="connection")
    assert fetch.calls == []


def test_module_has_no_qt_db_or_openssl():
    source = Path(update_check.__file__).read_text(encoding="utf-8")
    for forbidden in ("PySide6", "import database", "import ssl", "http.client", "OpenerDirector"):
        assert forbidden not in source
