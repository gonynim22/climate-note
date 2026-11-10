"""Windows 내장 통신(WinHTTP)으로 HTTPS GET을 한 번 보낸다. Qt·DB·설정·로그를 모른다.

배포 EXE에는 Python용 OpenSSL이 없다(검사 지적 조치, 2026-11-10). TLS와 인증서 검증은 Windows가 맡는다.

- 요청은 한 번이다. 리디렉션·쿠키·자동 인증을 끄고 클라이언트 인증서를 보내지 않는다.
- 인증서 검증은 WinHTTP 기본값 그대로다. 검증을 건너뛰거나 느슨하게 하는 옵션은 어디에서도 지정하지 않는다.
  인증서 폐기 확인도 켜지 않는다(이전의 Python 통신과 같다).
- TLS는 1.2 이상만 허용한다.
- 공개 함수 https_get은 https 주소만 받는다. 평문 요청(_get의 secure=False)은 로컬 서버를 쓰는 시험 전용이다.

상수 이름과 뜻은 Microsoft 문서를 따른다(값은 Windows SDK winhttp.h. 동작은 tests/test_winhttp_get.py가 고정).
https://learn.microsoft.com/windows/win32/winhttp/option-flags
https://learn.microsoft.com/windows/win32/api/winhttp/nf-winhttp-winhttpopen
https://learn.microsoft.com/windows/win32/winhttp/error-messages
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import re
import time
import urllib.parse

TOTAL_TIMEOUT_FACTOR = 3  # 요청 하나의 전체 상한 = timeout_seconds × 3 (조금씩 끝없이 오는 응답을 끊는다)

WINHTTP_ACCESS_TYPE_NO_PROXY = 1
WINHTTP_ACCESS_TYPE_NAMED_PROXY = 3
WINHTTP_FLAG_SECURE = 0x00800000
WINHTTP_OPTION_DISABLE_FEATURE = 63          # 요청 핸들 전용
WINHTTP_DISABLE_COOKIES = 0x00000001
WINHTTP_DISABLE_REDIRECTS = 0x00000002
WINHTTP_DISABLE_AUTHENTICATION = 0x00000004
WINHTTP_OPTION_SECURE_PROTOCOLS = 84         # 세션 핸들 전용
WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 = 0x00000800
WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3 = 0x00002000
WINHTTP_QUERY_STATUS_CODE = 19
WINHTTP_QUERY_FLAG_NUMBER = 0x20000000
ERROR_WINHTTP_TIMEOUT = 12002

_HEADER_NAME = re.compile(r"[A-Za-z0-9-]+")
_HANDLE = ctypes.c_void_p
_DWORD_P = ctypes.POINTER(wintypes.DWORD)
_SIGNATURES = {
    "WinHttpOpen": ([wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD], _HANDLE),
    "WinHttpSetTimeouts": ([_HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int], wintypes.BOOL),
    "WinHttpConnect": ([_HANDLE, wintypes.LPCWSTR, wintypes.WORD, wintypes.DWORD], _HANDLE),
    "WinHttpOpenRequest": ([_HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            ctypes.POINTER(wintypes.LPCWSTR), wintypes.DWORD], _HANDLE),
    "WinHttpSetOption": ([_HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
    "WinHttpSendRequest": ([_HANDLE, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                            wintypes.DWORD, ctypes.c_size_t], wintypes.BOOL),
    "WinHttpReceiveResponse": ([_HANDLE, ctypes.c_void_p], wintypes.BOOL),
    "WinHttpQueryHeaders": ([_HANDLE, wintypes.DWORD, wintypes.LPCWSTR, ctypes.c_void_p, _DWORD_P, _DWORD_P],
                            wintypes.BOOL),
    "WinHttpQueryDataAvailable": ([_HANDLE, _DWORD_P], wintypes.BOOL),
    "WinHttpReadData": ([_HANDLE, ctypes.c_void_p, wintypes.DWORD, _DWORD_P], wintypes.BOOL),
    "WinHttpCloseHandle": ([_HANDLE], wintypes.BOOL),
}
_loaded = None


class WinHttpError(OSError):
    """WinHTTP 호출 실패. code는 GetLastError 값, timed_out은 시간 초과 여부."""

    def __init__(self, code: int, *, timed_out: bool = False):
        super().__init__(f"WinHTTP 오류 {code}")
        self.code = code
        self.timed_out = timed_out


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes  # 많아야 max_bytes 바이트


def _library():
    """인자·반환 형식을 선언한 winhttp.dll. 열지 못하면 OSError다."""
    global _loaded
    if _loaded is None:
        library = ctypes.WinDLL("winhttp", use_last_error=True)
        for name, (arguments, result) in _SIGNATURES.items():
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result  # 64비트에서 핸들이 잘리지 않게 한다
        _loaded = library
    return _loaded


def _failure() -> WinHttpError:
    code = ctypes.get_last_error()
    return WinHttpError(code, timed_out=code == ERROR_WINHTTP_TIMEOUT)


def _set_dword_option(handle, option: int, value: int) -> bool:
    number = wintypes.DWORD(value)
    return bool(_library().WinHttpSetOption(handle, option, ctypes.byref(number), ctypes.sizeof(number)))


def _set_tls_floor(session, set_option=_set_dword_option) -> None:
    """TLS 1.2 이상만 허용한다. 1.3 지정을 거절하는 Windows에서는 1.2만 지정한다."""
    modern = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 | WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3
    if set_option(session, WINHTTP_OPTION_SECURE_PROTOCOLS, modern):
        return
    if not set_option(session, WINHTTP_OPTION_SECURE_PROTOCOLS, WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2):
        raise _failure()  # 하한을 걸지 못하면 요청하지 않는다


def _close_handle(handle) -> None:
    _library().WinHttpCloseHandle(handle)


def _header_lines(headers: dict[str, str]) -> str:
    lines = []
    for name, value in headers.items():
        if not _HEADER_NAME.fullmatch(name) or "\r" in value or "\n" in value:
            raise ValueError("헤더 이름·값에 쓸 수 없는 문자가 있습니다.")
        lines.append(f"{name}: {value}\r\n")
    return "".join(lines)


def https_get(url: str, *, headers: dict[str, str], user_agent: str, timeout_seconds: float,
              max_bytes: int, proxy: str | None = None) -> Response:
    """https 주소에 GET을 한 번 보내고 상태 코드와 본문(많아야 max_bytes)을 돌려준다.

    proxy는 None이거나 '호스트:포트'다. 실패는 WinHttpError(통신)·OSError(DLL)·ValueError(주소·헤더)다.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError("https 주소만 요청할 수 있습니다.")
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return _get(parts.hostname, parts.port or 443, path, secure=True, headers=headers, user_agent=user_agent,
                timeout_seconds=timeout_seconds, max_bytes=max_bytes, proxy=proxy)


def _get(host: str, port: int, path: str, *, secure: bool, headers: dict[str, str], user_agent: str,
         timeout_seconds: float, max_bytes: int, proxy: str | None) -> Response:
    lines = _header_lines(headers)
    winhttp = _library()
    deadline = time.monotonic() + timeout_seconds * TOTAL_TIMEOUT_FACTOR

    def within_deadline():
        if time.monotonic() > deadline:
            raise WinHttpError(ERROR_WINHTTP_TIMEOUT, timed_out=True)

    session = connection = request = None
    try:
        access = WINHTTP_ACCESS_TYPE_NAMED_PROXY if proxy else WINHTTP_ACCESS_TYPE_NO_PROXY
        session = winhttp.WinHttpOpen(user_agent, access, proxy or None, None, 0)
        if not session:
            raise _failure()
        if secure:
            _set_tls_floor(session)
        milliseconds = int(timeout_seconds * 1000)
        if not winhttp.WinHttpSetTimeouts(session, milliseconds, milliseconds, milliseconds, milliseconds):
            raise _failure()
        connection = winhttp.WinHttpConnect(session, host, port, 0)
        if not connection:
            raise _failure()
        request = winhttp.WinHttpOpenRequest(connection, "GET", path, None, None, None,
                                             WINHTTP_FLAG_SECURE if secure else 0)
        if not request:
            raise _failure()
        single_request = WINHTTP_DISABLE_COOKIES | WINHTTP_DISABLE_REDIRECTS | WINHTTP_DISABLE_AUTHENTICATION
        if not _set_dword_option(request, WINHTTP_OPTION_DISABLE_FEATURE, single_request):
            raise _failure()
        within_deadline()
        if not winhttp.WinHttpSendRequest(request, lines or None, len(lines), None, 0, 0, 0):
            raise _failure()
        within_deadline()
        if not winhttp.WinHttpReceiveResponse(request, None):
            raise _failure()
        status, size = wintypes.DWORD(), wintypes.DWORD(ctypes.sizeof(wintypes.DWORD))
        if not winhttp.WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, None,
                                           ctypes.byref(status), ctypes.byref(size), None):
            raise _failure()
        chunks, total = [], 0
        while total < max_bytes:
            within_deadline()
            available = wintypes.DWORD()
            if not winhttp.WinHttpQueryDataAvailable(request, ctypes.byref(available)):
                raise _failure()
            if not available.value:
                break
            wanted = min(available.value, max_bytes - total)
            buffer, read = ctypes.create_string_buffer(wanted), wintypes.DWORD()
            if not winhttp.WinHttpReadData(request, buffer, wanted, ctypes.byref(read)):
                raise _failure()
            if not read.value:
                break
            chunks.append(buffer.raw[:read.value])
            total += read.value
        return Response(status.value, b"".join(chunks))
    finally:
        for handle in (request, connection, session):
            if handle:
                _close_handle(handle)
