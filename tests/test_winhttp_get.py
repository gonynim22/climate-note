"""WinHTTP 통신 층: 로컬 서버로 '요청 한 번'의 계약을 본다(인터넷 불필요).

평문 로컬 서버는 안쪽 함수 _get(secure=False)로만 부른다. 앱 경로의 공개 함수 https_get은 https만 받는다.
"""
import ast
import datetime
import http.server
import socket
import ssl
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import winhttp_get
from winhttp_get import Response, WinHttpError

ARGS = dict(headers={"Accept": "application/json"}, user_agent="ClimateNote-UpdateCheck",
            timeout_seconds=5, max_bytes=10_000, proxy=None)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.server.seen.append((self.path, {name.lower(): value for name, value in self.headers.items()}))
        if self.path == "/ok":
            self._reply(200, b"x" * 5000)
        elif self.path == "/redirect":
            self._reply(302, b"", {"Location": "/ok"})
        elif self.path == "/cookie":
            self._reply(200, b"ok", {"Set-Cookie": "a=b"})
        elif self.path == "/407":
            self._reply(407, b"", {"Proxy-Authenticate": 'Basic realm="x"'})
        elif self.path == "/slow":
            time.sleep(3)
            self._reply(200, b"late")
        elif self.path == "/drip":
            self._drip()
        elif self.path == "/dripheaders":
            self._drip_headers()
        else:
            self._reply(404, b"")

    def do_CONNECT(self):
        # 프록시 역할: HTTPS 요청은 터널을 열어 달라는 CONNECT로 온다. 인증을 요구하는 업무망 프록시처럼 407로 답한다.
        self.server.seen.append(("CONNECT " + self.path, {name.lower(): value for name, value in self.headers.items()}))
        self._reply(407, b"", {"Proxy-Authenticate": 'Basic realm="x"'})

    def _reply(self, status, body, headers=None):
        try:
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # 시간 초과 시험에서는 클라이언트가 먼저 끊는다
        self.close_connection = True

    def _drip(self):
        try:
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            for _ in range(34):  # 0.3초마다 1바이트, 약 10초
                self.wfile.write(b"x")
                self.wfile.flush()
                time.sleep(0.3)
        except OSError:
            pass
        self.close_connection = True


    def _drip_headers(self):
        # 응답 머리줄을 0.3초마다 1바이트씩 약 24초 동안 보낸다. 받기 호출 하나가 끝나지 않는 서버다.
        try:
            for byte in b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nX-Pad: " + b"a" * 40:
                self.wfile.write(bytes([byte]))
                self.wfile.flush()
                time.sleep(0.3)
        except OSError:
            pass
        self.close_connection = True


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # 거부된 TLS 연결·끊긴 연결의 traceback을 시험 출력에 남기지 않는다


def _serve(wrap=None):
    httpd = _Server(("127.0.0.1", 0), _Handler)
    httpd.seen = []
    if wrap is not None:
        httpd.socket = wrap(httpd.socket)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


@pytest.fixture
def server():
    httpd = _serve()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _get(server, path, **changes):
    return winhttp_get._get("127.0.0.1", server.server_address[1], path, secure=False, **{**ARGS, **changes})


def _closed_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_reads_status_and_body_up_to_limit(server):
    assert _get(server, "/ok") == Response(200, b"x" * 5000)
    assert _get(server, "/ok", max_bytes=1000) == Response(200, b"x" * 1000)


def test_sends_only_fixed_headers(server):
    _get(server, "/ok")
    path, headers = server.seen[0]
    assert path == "/ok"
    assert set(headers) <= {"host", "accept", "user-agent", "connection"}
    assert headers["accept"] == "application/json" and headers["user-agent"] == "ClimateNote-UpdateCheck"


def test_redirect_is_returned_not_followed(server):
    assert _get(server, "/redirect").status == 302
    assert [path for path, _ in server.seen] == ["/redirect"]


def test_cookies_are_not_stored_or_sent(server):
    _get(server, "/cookie")
    _get(server, "/cookie")
    assert len(server.seen) == 2 and "cookie" not in server.seen[1][1]


def test_proxy_auth_required_is_just_a_status(server):
    assert _get(server, "/407").status == 407
    assert len(server.seen) == 1


def test_slow_server_times_out(server):
    with pytest.raises(WinHttpError) as caught:
        _get(server, "/slow", timeout_seconds=1)
    assert caught.value.timed_out is True


def test_dripping_body_hits_total_deadline(server):
    started = time.monotonic()
    with pytest.raises(WinHttpError) as caught:
        _get(server, "/drip", timeout_seconds=1)
    assert caught.value.timed_out is True
    assert time.monotonic() - started < 6


def test_dripping_headers_hit_total_deadline(server):
    # 전체 상한은 WinHTTP 호출 사이에서만 보면 지켜지지 않는다: 머리줄을 흘리는 서버는 받기 호출 하나를
    # 붙잡아 둔다(2026-11-10 검토에서 재현, 서버가 끊을 때까지 150초). 상한 시각에 요청을 끊어야 한다.
    started = time.monotonic()
    with pytest.raises(WinHttpError) as caught:
        _get(server, "/dripheaders", timeout_seconds=1)
    assert caught.value.timed_out is True
    assert time.monotonic() - started < 6


def test_closed_port_is_connection_error():
    with pytest.raises(WinHttpError) as caught:
        winhttp_get._get("127.0.0.1", _closed_port(), "/ok", secure=False, **ARGS)
    assert caught.value.timed_out is False and caught.value.code


# WinHTTP는 루프백 대상(127.0.0.1)에는 지정 프록시를 쓰지 않고 직접 연결한다(2026-11-10 실측).
# 프록시 시험은 다른 이름을 대상으로 한다. 이름 풀이는 프록시 몫이라 DNS 조회가 나가지 않는다.
PROXIED = "proxy-target.invalid"


def _as_proxy(server):
    return f"127.0.0.1:{server.server_address[1]}"


def test_closed_proxy_is_connection_error():
    closed = f"127.0.0.1:{_closed_port()}"  # 포트 9를 닫혔다고 가정하지 않는다(그 PC에서 열려 있을 수 있다)
    with pytest.raises(WinHttpError) as caught:
        winhttp_get._get(PROXIED, 80, "/ok", secure=False, **{**ARGS, "proxy": closed})
    assert caught.value.timed_out is False
    with pytest.raises(WinHttpError) as caught:  # release의 update_check 시나리오와 같은 모양
        winhttp_get.https_get(f"https://{PROXIED}/x", **{**ARGS, "proxy": closed})
    assert caught.value.timed_out is False


def test_plain_request_goes_through_the_named_proxy(server):
    winhttp_get._get(PROXIED, 80, "/ok", secure=False, **{**ARGS, "proxy": _as_proxy(server)})
    assert [path for path, _ in server.seen] == [f"http://{PROXIED}/ok"]


def test_https_request_asks_the_proxy_for_a_tunnel_and_reports_its_407(server):
    result = winhttp_get.https_get(f"https://{PROXIED}/x", **{**ARGS, "proxy": _as_proxy(server)})
    assert result.status == 407  # 인증을 요구하는 프록시: 자동 인증 없이 상태만 돌려준다
    assert [path for path, _ in server.seen] == [f"CONNECT {PROXIED}:443"]


def _self_signed(folder):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(now - datetime.timedelta(days=1))
                   .not_valid_after(now + datetime.timedelta(days=1))
                   .sign(key, hashes.SHA256()))
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    return cert_path, key_path


def test_self_signed_https_server_is_rejected(tmp_path):
    cert_path, key_path = _self_signed(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    httpd = _serve(lambda sock: context.wrap_socket(sock, server_side=True))
    try:
        with pytest.raises(WinHttpError) as caught:
            winhttp_get.https_get(f"https://127.0.0.1:{httpd.server_address[1]}/ok", **ARGS)
        assert caught.value.timed_out is False
        assert httpd.seen == []  # 인증서를 믿지 못하면 요청을 보내지 않는다
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "ftp://x.invalid/", "//x.invalid/", "https:///only-path"])
def test_public_function_refuses_anything_but_https(monkeypatch, url):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("https가 아닌 주소로 통신을 시작했다")

    monkeypatch.setattr(winhttp_get, "_get", forbidden)
    with pytest.raises(ValueError):
        winhttp_get.https_get(url, **ARGS)


@pytest.mark.parametrize(("url", "expected"), [
    ("https://example.invalid/api/v4/x?per_page=1&sort=desc", ("example.invalid", 443, "/api/v4/x?per_page=1&sort=desc")),
    ("https://example.invalid:8443", ("example.invalid", 8443, "/"))])
def test_public_function_always_asks_for_a_secure_request(monkeypatch, url, expected):
    calls = []

    def fake(host, port, path, **kwargs):
        calls.append(((host, port, path), kwargs))
        return Response(200, b"")

    monkeypatch.setattr(winhttp_get, "_get", fake)
    assert winhttp_get.https_get(url, **ARGS) == Response(200, b"")
    assert calls == [(expected, {"secure": True, **ARGS})]


@pytest.mark.parametrize("headers", [{"Accept": "a\r\nX-Injected: y"}, {"Bad\nName": "a"}, {"Na:me": "a"},
                                     # 헤더 길이는 글자 수로 넘긴다. ASCII가 아니면 UTF-16 길이와 어긋난다
                                     {"Accept": "é"}, {"Accept": "a😀"}, {"Accept": "a\x00b"}])
def test_header_with_unusable_characters_is_refused(server, headers):
    with pytest.raises(ValueError):
        _get(server, "/ok", headers=headers)
    assert server.seen == []


def test_sub_millisecond_timeout_stays_bounded(monkeypatch):
    # WinHTTP는 제한 시간 0을 '무한'으로 읽는다. 1ms 미만을 0으로 깎지 않는다.
    real = winhttp_get._library()
    timeouts = []

    class Spy:
        def __getattr__(self, name):
            return getattr(real, name)

        def WinHttpSetTimeouts(self, session, *values):
            timeouts.append(values)
            return real.WinHttpSetTimeouts(session, *values)

    monkeypatch.setattr(winhttp_get, "_library", lambda: Spy())
    with pytest.raises(WinHttpError):
        winhttp_get._get("127.0.0.1", _closed_port(), "/ok", secure=False, **{**ARGS, "timeout_seconds": 0.0004})
    assert timeouts == [(1, 1, 1, 1)]


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_timeout_must_be_positive(seconds):
    with pytest.raises(ValueError):
        winhttp_get._get("127.0.0.1", _closed_port(), "/ok", secure=False, **{**ARGS, "timeout_seconds": seconds})


def test_handles_are_closed_on_success_and_failure(server, monkeypatch):
    closed = []
    real = winhttp_get._close_handle

    def counting(handle):
        closed.append(handle)
        real(handle)

    monkeypatch.setattr(winhttp_get, "_close_handle", counting)
    _get(server, "/ok")
    assert len(closed) == 3  # 세션·연결·요청
    closed.clear()
    with pytest.raises(WinHttpError):
        winhttp_get._get("127.0.0.1", _closed_port(), "/ok", secure=False, **ARGS)
    assert len(closed) == 3


def test_tls_floor_tries_1_3_then_falls_back_to_1_2_only():
    values = []

    def set_option(_handle, _option, value):
        values.append(value)
        return len(values) > 1  # 첫 지정(TLS 1.3 포함)을 거절하는 Windows

    winhttp_get._set_tls_floor(object(), set_option)
    assert values == [0x2800, 0x0800]


def test_request_stops_when_tls_floor_cannot_be_set():
    with pytest.raises(WinHttpError):
        winhttp_get._set_tls_floor(object(), lambda _handle, _option, _value: False)


def test_missing_dll_is_oserror(monkeypatch):
    def missing():
        raise OSError("winhttp.dll을 열 수 없음")

    monkeypatch.setattr(winhttp_get, "_library", missing)
    with pytest.raises(OSError):
        winhttp_get._get("127.0.0.1", 9, "/ok", secure=False, **ARGS)


def test_dll_is_loaded_from_system32_only(monkeypatch):
    # 이름만 주면 EXE가 있는 폴더를 System32보다 먼저 찾는다. 옆에 놓인 가짜 winhttp.dll을 불러오지 않게 한다.
    calls = []

    class FakeLibrary:
        def __getattr__(self, _name):
            return SimpleNamespace()

    def fake_windll(name, **kwargs):
        calls.append((name, kwargs))
        return FakeLibrary()

    monkeypatch.setattr(winhttp_get, "_loaded", None)
    monkeypatch.setattr(winhttp_get.ctypes, "WinDLL", fake_windll)
    winhttp_get._library()
    assert calls == [("winhttp", {"use_last_error": True, "winmode": 0x800})]  # LOAD_LIBRARY_SEARCH_SYSTEM32


def test_only_the_two_hardening_options_are_set(server, monkeypatch):
    # 인증서 검증을 느슨하게 하는 옵션은 이름(SECURITY_FLAGS) 대신 숫자(31)로도 쓸 수 있어 소스 글자로는 못 막는다.
    # 실제 요청에서 WinHttpSetOption에 넘긴 옵션 번호를 모은다: TLS 하한(84)과 쿠키·리디렉션·자동 인증 끄기(63)뿐이다.
    real = winhttp_get._library()
    options = []

    class Spy:
        def __getattr__(self, name):
            return getattr(real, name)

        def WinHttpSetOption(self, handle, option, buffer, size):
            options.append(option)
            return real.WinHttpSetOption(handle, option, buffer, size)

    monkeypatch.setattr(winhttp_get, "_library", lambda: Spy())
    _get(server, "/ok")
    with pytest.raises(WinHttpError):  # 평문 서버에 TLS로 붙으면 실패한다. 보안 요청 경로의 옵션도 모은다
        winhttp_get._get("127.0.0.1", server.server_address[1], "/ok", secure=True, **ARGS)
    assert sorted(set(options)) == [63, 84]


def test_module_has_no_qt_db_or_python_ssl():
    tree = ast.parse(Path(winhttp_get.__file__).read_text(encoding="utf-8"))
    modules = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    modules |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert {name for name in modules if name.split(".")[0] in {"PySide6", "database", "ssl"}} == set()
