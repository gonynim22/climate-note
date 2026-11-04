"""새 버전 확인의 판정·요청: 실제 네트워크 없이 가짜 opener와 가짜 전송으로 검사한다."""
import http.client
import io
import json
import ssl
import urllib.request
import urllib.response
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import update_check
from update_check import (
    RELEASES_URL, CheckResult, check_latest, https_only_opener, is_newer, parse_version, read_result,
)

OK_BODY = json.dumps([{"tag_name": "v4.7", "upcoming_release": False}]).encode()


class FakeOpener:
    def __init__(self, body=b"", error=None):
        self.body, self.error, self.requests = body, error, []

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.body)


def _http_error(code):
    return HTTPError(RELEASES_URL, code, "x", {}, io.BytesIO())


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


def test_opener_failure_is_classified_not_raised(monkeypatch):
    def broken():
        raise ssl.SSLError("인증서 저장소를 읽지 못함")

    monkeypatch.setattr(update_check, "https_only_opener", broken)
    assert check_latest() == CheckResult(failure="connection")


def test_opener_has_no_redirect_and_only_https_proxy(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies",
                        lambda: {"https": "http://proxy.invalid:8080", "http": "http://proxy.invalid:8080"})
    opener = https_only_opener()
    assert set(opener.handle_open) == {"https", "unknown"}
    assert not any(isinstance(handler, urllib.request.HTTPRedirectHandler) for handler in opener.handlers)


def test_redirect_is_not_followed(monkeypatch):
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    calls = []

    def transport(handler, request):
        calls.append(request.full_url)
        response = urllib.response.addinfourl(
            io.BytesIO(b""), {"Location": "https://other.invalid/"}, request.full_url, 302)
        response.msg = "Found"
        return response

    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", transport)
    assert check_latest() == CheckResult(failure="http-302")
    assert calls == [RELEASES_URL]


def test_module_has_no_qt_or_db():
    source = Path(update_check.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source and "import database" not in source
