"""새 버전 확인: 버전 판정과 고정 주소 요청 한 번. Qt·DB가 없다(설정 '인터넷 접속'을 켠 PC만 호출된다).

- 보내는 것은 고정 주소의 GET뿐이다. 일정·메모·설정·PC 식별 정보를 보내지 않는다.
- 어떤 실패도 예외로 내보내지 않고 분류해서 돌려준다. 사용자에게는 보이지 않는다.
- 통신은 winhttp_get(Windows 내장 WinHTTP)이 맡는다. 배포 EXE에는 Python용 OpenSSL이 없어 urllib로는
  HTTPS를 열 수 없다. urllib.request는 프록시 설정을 읽는 데만 쓴다(지금까지와 같은 방식으로 읽는다).
- winhttp_get·urllib.request는 일부러 모듈 맨 위에서 import한다. EXE에서 모듈이 빠지면 시작 때 드러나야지,
  조용한 확인 실패로 묻히면 안 된다(build.spec의 excludes에 http·email·ctypes를 넣으면 안 된다).
"""

from dataclasses import dataclass
import json
import logging
import re
import urllib.parse
import urllib.request

import winhttp_get

_logger = logging.getLogger("app_error")  # ERROR 수준 로거라 .error()로 쓴다. 예외 종류 이름만 남긴다

RELEASES_URL = ("https://gitlab.aigov.go.kr/api/v4/projects/647/releases"
                "?per_page=1&order_by=released_at&sort=desc")  # 리디렉션 없는 주소(permalink는 3xx라 쓰지 않는다)
_HOST = urllib.parse.urlsplit(RELEASES_URL).hostname
USER_AGENT = "ClimateNote-UpdateCheck"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 256 * 1024

_TAG = re.compile(r"v([0-9]{1,4})\.([0-9]{1,4})([a-z]?)")  # 자릿수 제한: int()의 긴 숫자 ValueError를 막는다


@dataclass(frozen=True)
class CheckResult:
    """failure가 None이면 응답을 정상으로 읽었다. 이때 latest_tag가 None이면 판단할 Release가 없다."""

    latest_tag: str | None = None
    failure: str | None = None  # "timeout" | "connection" | "http-<코드>" | "format"


def parse_version(tag: object) -> tuple[int, int, str] | None:
    """`v4.6`, `v4.5a`, `v4.10` 형식만 (주, 부, 글자)로 읽는다. 글자 없음 < a < b."""
    matched = _TAG.fullmatch(tag) if isinstance(tag, str) else None
    if matched is None:
        return None
    return int(matched[1]), int(matched[2]), matched[3]


def is_newer(tag: object, current: object) -> bool:
    """둘 다 형식에 맞고 tag가 더 높을 때만 True."""
    latest, running = parse_version(tag), parse_version(current)
    return latest is not None and running is not None and latest > running


def read_result(body: bytes) -> CheckResult:
    """응답 본문에서 tag_name 하나만 읽는다. 그 밖의 필드는 upcoming_release만 본다."""
    try:
        releases = json.loads(body)
    except (ValueError, RecursionError):  # 깊게 중첩된 배열은 RecursionError다
        return CheckResult(failure="format")
    if not isinstance(releases, list):
        return CheckResult(failure="format")
    if not releases:
        return CheckResult()
    release = releases[0]
    if not isinstance(release, dict):
        return CheckResult(failure="format")
    if release.get("upcoming_release"):
        return CheckResult()
    tag = release.get("tag_name")
    return CheckResult(latest_tag=tag) if parse_version(tag) is not None else CheckResult(failure="format")


def proxy_for(host: str) -> str | None:
    """이 호스트에 쓸 HTTPS 프록시를 '호스트:포트'로 돌려준다. 없거나 예외 대상이면 None.

    읽는 방식은 urllib과 같다(환경 변수 → Windows 인터넷 설정, no_proxy·예외 목록 적용).
    자동 구성 스크립트(PAC)와 프록시 인증은 지원하지 않는다. 주소에 사용자 정보가 있으면 ValueError다.
    """
    address = urllib.request.getproxies().get("https")
    if not address or urllib.request.proxy_bypass(host):
        return None
    parts = urllib.parse.urlsplit(address if "//" in address else "//" + address)
    if parts.username is not None or parts.password is not None or not parts.hostname:
        raise ValueError("쓸 수 없는 프록시 주소입니다.")
    name = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{name}:{parts.port}" if parts.port else name  # 잘못된 포트는 parts.port가 ValueError를 낸다


def check_latest(fetch=None) -> CheckResult:
    """고정 주소를 한 번 읽는다. 작업 스레드에서 호출된다.

    fetch는 winhttp_get.https_get과 같은 모양이다(시험용). 없으면 부를 때 winhttp_get.https_get을 찾는다.
    """
    try:
        client = fetch if fetch is not None else winhttp_get.https_get
        response = client(RELEASES_URL, headers={"Accept": "application/json"}, user_agent=USER_AGENT,
                          timeout_seconds=TIMEOUT_SECONDS, max_bytes=MAX_RESPONSE_BYTES + 1,
                          proxy=proxy_for(_HOST))
    except winhttp_get.WinHttpError as exc:
        return CheckResult(failure="timeout" if exc.timed_out else "connection")
    except TimeoutError:
        return CheckResult(failure="timeout")
    except (OSError, ValueError):  # 인증서·연결 끊김·프록시 주소 오류·winhttp.dll을 열지 못함
        return CheckResult(failure="connection")
    except Exception as exc:  # 최후 수단: 통신 층(ctypes)의 예상 밖 예외도 내보내지 않는다(작업 스레드가 죽는다)
        _logger.error("새 버전 확인 통신 층 예외: %s", type(exc).__name__)
        return CheckResult(failure="connection")
    if not 200 <= response.status <= 299:  # 3xx도 여기다(리디렉션을 따르지 않는다)
        return CheckResult(failure=f"http-{response.status}")
    if len(response.body) > MAX_RESPONSE_BYTES:
        return CheckResult(failure="format")
    return read_result(response.body)
