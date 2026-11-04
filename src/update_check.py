"""새 버전 확인: 버전 판정과 고정 주소 요청 한 번. Qt·DB가 없다(설정 '인터넷 접속'을 켠 PC만 호출된다).

- 보내는 것은 고정 주소의 GET뿐이다. 일정·메모·설정·PC 식별 정보를 보내지 않는다.
- 어떤 실패도 예외로 내보내지 않고 분류해서 돌려준다. 사용자에게는 보이지 않는다.
- urllib.request·ssl은 일부러 모듈 맨 위에서 import한다. EXE에서 모듈이 빠지면 시작 때 드러나야지,
  조용한 확인 실패로 묻히면 안 된다(build.spec의 excludes에 http·email을 넣으면 안 된다).
"""

from dataclasses import dataclass
import http.client
import json
import re
import ssl
import urllib.error
import urllib.request

RELEASES_URL = ("https://gitlab.aigov.go.kr/api/v4/projects/647/releases"
                "?per_page=1&order_by=released_at&sort=desc")  # 리디렉션 없는 주소(permalink는 3xx라 쓰지 않는다)
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


def https_only_opener() -> urllib.request.OpenerDirector:
    """HTTPS 프록시만 등록하고 나머지 URL 형식은 거부한다. 리디렉션 처리기를 넣지 않아 3xx는 실패다.

    no_proxy는 ProxyHandler의 기존 proxy_bypass 경로에서 그대로 적용된다.
    fetch_data.py와 같은 구성이지만 그 파일은 EXE에 들어가지 않아 공유하지 않는다.
    """
    proxies = {scheme: address for scheme, address in urllib.request.getproxies().items()
               if scheme == "https"}
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler(proxies),
                    urllib.request.UnknownHandler(),
                    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                    urllib.request.HTTPDefaultErrorHandler(),
                    urllib.request.HTTPErrorProcessor()):
        opener.add_handler(handler)
    return opener


def check_latest(opener=None) -> CheckResult:
    """고정 주소를 한 번 읽는다. 작업 스레드에서 호출된다."""
    request = urllib.request.Request(
        RELEASES_URL, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        client = opener if opener is not None else https_only_opener()
        with client.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:  # 3xx도 여기로 온다(리디렉션을 따르지 않는다)
        exc.close()
        return CheckResult(failure=f"http-{exc.code}")
    except urllib.error.URLError as exc:
        return CheckResult(failure="timeout" if isinstance(exc.reason, TimeoutError) else "connection")
    except TimeoutError:
        return CheckResult(failure="timeout")
    except (OSError, http.client.HTTPException, ValueError):  # 인증서·연결 끊김·프록시 주소 오류
        return CheckResult(failure="connection")
    if len(body) > MAX_RESPONSE_BYTES:
        return CheckResult(failure="format")
    return read_result(body)
