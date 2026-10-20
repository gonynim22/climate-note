"""
fetch_data.py - 공공데이터포털 API에서 음력/공휴일 데이터 수집 (실제 API 데이터만 저장)
* API가 제공하는 범위(통상 1~2년 뒤까지)만 holidays.py로 생성한다.
* 미래 연도를 임의 계산해 채우지 않는다.
"""
import http.client
import json
import os
import re
import runpy
import shutil
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as ET
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent


class FetchError(Exception):
    """받기 실패. environment=True: 키·네트워크·서비스 문제, False: 응답 내용 문제."""

    def __init__(self, message: str, *, environment: bool):
        super().__init__(message)
        self.environment = environment


def load_api_key(env_path: Path = ROOT / ".env") -> str:
    """환경 변수 우선, 없으면 .env 파일에서 읽는다 (os.environ은 바꾸지 않음)."""
    return os.environ.get("LUNAR_API_KEY") or dotenv_values(env_path).get("LUNAR_API_KEY") or ""


API_KEY = load_api_key()
API_BASE = "https://apis.data.go.kr/B090041/openapi/service"


def _https_only_opener() -> urllib.request.OpenerDirector:
    """HTTPS 프록시만 등록하고 나머지 URL 형식은 거부한다.
    no_proxy는 ProxyHandler의 기존 proxy_bypass 경로에서 그대로 적용된다."""
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


_OPENER = _https_only_opener()


def _api_get(service_path: str, year: int, month: int) -> str:
    label = f"{service_path.split('/')[0]} {year:04d}-{month:02d}"
    if not API_KEY:
        raise FetchError("LUNAR_API_KEY가 없습니다 (.env 확인)", environment=True)
    params = urllib.parse.urlencode({"serviceKey": API_KEY, "solYear": f"{year:04d}",
                                     "solMonth": f"{month:02d}", "numOfRows": "50"})
    try:
        with _OPENER.open(f"{API_BASE}/{service_path}?{params}", timeout=10) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as e:
        # URL·키가 메시지·예외 체인에 남지 않게 형식 이름만 쓴다
        raise FetchError(f"{label} 요청 실패 ({type(e).__name__})", environment=True) from None
    except UnicodeDecodeError:
        raise FetchError(f"{label} 응답 해석 실패", environment=False) from None


def _response_items(xml_text: str, label: str) -> list:
    """응답 XML을 검사해 item 목록을 돌려준다. 이상이면 FetchError."""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, DefusedXmlException):
        raise FetchError(f"{label} 응답 XML 해석 실패", environment=False) from None
    code = (root.findtext(".//header/resultCode") or "").strip()
    if code == "03":
        return []
    if code != "00":
        detail = (root.findtext(".//header/resultMsg") or root.findtext(".//returnAuthMsg") or "").strip()
        raise FetchError(f"{label} API 오류 (결과 코드 {code or '없음'} {detail})".rstrip(), environment=True)
    total_text = (root.findtext(".//body/totalCount") or "").strip()
    if not total_text.isdigit():
        raise FetchError(f"{label} totalCount 이상", environment=False)
    items = root.findall(".//body/items/item")
    if len(items) < int(total_text):
        raise FetchError(f"{label} 항목 부족 ({len(items)}/{total_text})", environment=False)
    return items


def _field(item, tag: str, pattern: str, label: str) -> str:
    value = (item.findtext(tag) or "").strip()
    if not re.fullmatch(pattern, value):
        raise FetchError(f"{label} {tag} 값 이상", environment=False)
    return value


# ── API 호출 함수 ──
def fetch_holidays(year: int, month: int) -> list[dict]:
    label = f"공휴일 {year:04d}-{month:02d}"
    result = []
    for item in _response_items(_api_get("SpcdeInfoService/getRestDeInfo", year, month), label):
        loc = _field(item, "locdate", r"\d{8}", label)
        name = _field(item, "dateName", r".+", label)
        if _field(item, "isHoliday", r"[YN]", label) == "Y":
            result.append({"date": f"{loc[:4]}-{loc[4:6]}-{loc[6:8]}", "name": name})
    return result


def fetch_lunar_month(year: int, month: int) -> list[dict]:
    label = f"음력 {year:04d}-{month:02d}"
    result = []
    for item in _response_items(_api_get("LrsrCldInfoService/getLunCalInfo", year, month), label):
        date = "-".join((_field(item, "solYear", r"\d{4}", label), _field(item, "solMonth", r"\d{2}", label),
                         _field(item, "solDay", r"\d{2}", label)))
        lunar = f"{int(_field(item, 'lunMonth', r'\d+', label))}.{int(_field(item, 'lunDay', r'\d+', label))}"
        result.append({"date": date, "lunar": lunar})
    return result


CORE_HOLIDAY_NAMES = ("1월1일", "삼일절", "광복절", "개천절", "한글날", "기독탄신일", "설날", "추석")
HOLIDAY_YEARS = range(2025, 2051)


def _pause() -> None:
    time.sleep(0.1)


def merge_holiday_names(entries: Iterable[dict]) -> dict[str, str]:
    """같은 날 이름을 처음 본 순서로 '·'로 합친다 (같은 이름은 한 번만)."""
    names: dict[str, list[str]] = {}
    for entry in entries:
        day_names = names.setdefault(entry["date"], [])
        if entry["name"] not in day_names:
            day_names.append(entry["name"])
    return {date: "·".join(day_names) for date, day_names in names.items()}


def missing_core_names(holidays: Mapping[str, str], year: int) -> list[str]:
    """그 해 공휴일 이름에 들어 있지 않은 핵심 이름 (날짜는 보지 않음)."""
    year_names = [name for date, name in holidays.items() if date.startswith(f"{year:04d}-")]
    return [core for core in CORE_HOLIDAY_NAMES if not any(core in name for name in year_names)]


def fetch_holiday_years(years: Iterable[int]) -> dict[int, dict[str, str]]:
    """연도별 1~12월 공휴일을 받는다. 0건 연도는 빼고, 실패는 FetchError 그대로 올린다."""
    result = {}
    for year in years:
        entries = []
        for month in range(1, 13):
            entries.extend(fetch_holidays(year, month))
            _pause()
        if entries:
            result[year] = merge_holiday_names(entries)
    return result


def select_holiday_years(fetched: Mapping[int, Mapping[str, str]],
                         existing_years: Iterable[int]) -> tuple[dict[str, str], list[int]]:
    """받은 공휴일 중 쓸 연도를 고른다. 기존 연도가 불완전하면 실패, 새 연도는 제외한다."""
    existing = set(existing_years)
    merged: dict[str, str] = {}
    excluded: list[int] = []
    for year in sorted(existing | set(fetched)):
        year_holidays = fetched.get(year, {})
        missing = missing_core_names(year_holidays, year)
        if not missing:
            merged.update(year_holidays)
        elif year in existing:
            raise FetchError(f"{year}년 공휴일이 불완전합니다 (누락: {', '.join(missing)})", environment=False)
        else:
            excluded.append(year)
    return merged, excluded


def verify_holiday_data(hol) -> tuple[bool, str]:
    """재생성된 holidays 모듈이 최소 커버리지를 만족하는지 검증한다.

    hol: KOREAN_HOLIDAYS, LUNAR_MAPPING 속성을 가진 모듈 또는 객체.
    반환: (통과 여부, 사람이 읽는 메시지)
    """
    kh = getattr(hol, "KOREAN_HOLIDAYS", {})
    lm = getattr(hol, "LUNAR_MAPPING", {})
    kh_years = {k[:4] for k in kh}
    lm_years = {k[:4] for k in lm}
    if not kh_years or max(kh_years) < "2027":
        return False, f"공휴일 범위 부족 (최대 {max(kh_years) if kh_years else '없음'})"
    if not lm_years or max(lm_years) < "2050":
        return False, f"음력 범위 부족 (최대 {max(lm_years) if lm_years else '없음'})"
    if len(kh) < 40:
        return False, f"공휴일 건수 비정상 ({len(kh)}건)"
    for year in sorted({int(y) for y in kh_years}):
        missing = missing_core_names(kh, year)
        if missing:
            return False, f"{year}년 핵심 공휴일 누락: {', '.join(missing)}"
    return True, f"OK (공휴일 {len(kh)}건, 음력 {len(lm)}건)"


HOLIDAYS_PATH = ROOT / "holidays.py"

_MODULE_FUNCTIONS = '''def get_lunar_date(date_str: str) -> str:
    return LUNAR_MAPPING.get(date_str, "")

def get_holiday(date_str: str) -> str:
    return KOREAN_HOLIDAYS.get(date_str, "")

def is_holiday(date_str: str) -> bool:
    return date_str in KOREAN_HOLIDAYS

def holiday_last_year() -> int:
    """공휴일 데이터가 있는 마지막 연도 (데이터 만료 알림용)"""
    if not KOREAN_HOLIDAYS:
        return 0
    return max(int(k[:4]) for k in KOREAN_HOLIDAYS)
'''


def _render_dict(name: str, data: Mapping[str, str]) -> str:
    lines = [f"{name} = {{"]
    current_year = None
    for key in sorted(data):
        if key[:4] != current_year:
            current_year = key[:4]
            lines.append(f"\n    # {current_year}")
        lines.append(f"    {json.dumps(key, ensure_ascii=False)}: {json.dumps(data[key], ensure_ascii=False)},")
    lines.append("}\n\n")
    return "\n".join(lines)


def render_holidays_module(holidays: Mapping[str, str], lunar: Mapping[str, str]) -> str:
    """holidays.py 전체 내용을 만든다 (줄바꿈은 \\n, 파일에 쓸 때 플랫폼 기본값으로 바뀜)."""
    return ("# holidays.py - 오프라인 한국 공휴일/음력 데이터 (2025-2050)\n"
            "# 자동 생성됨 (fetch_data.py)\n"
            "from datetime import date\n\n"
            + _render_dict("KOREAN_HOLIDAYS", holidays)
            + _render_dict("LUNAR_MAPPING", lunar)
            + _MODULE_FUNCTIONS)


def read_holidays_module(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """holidays.py를 실행해 (KOREAN_HOLIDAYS, LUNAR_MAPPING)을 읽는다."""
    namespace = runpy.run_path(str(path))
    return dict(namespace["KOREAN_HOLIDAYS"]), dict(namespace["LUNAR_MAPPING"])


def write_holidays_module(path: Path, holidays: Mapping[str, str], lunar: Mapping[str, str],
                          backup_dir: Path) -> Path:
    """임시 파일에 쓰고 다시 읽어 검증한 뒤, 백업하고 교체한다. 백업 파일 경로를 돌려준다."""
    path = Path(path)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            pending = Path(stream.name)
            stream.write(render_holidays_module(holidays, lunar))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            read_hol, read_lunar = read_holidays_module(pending)
        except (SyntaxError, KeyError, ValueError, OSError) as e:
            raise FetchError(f"생성 파일을 읽을 수 없습니다 ({type(e).__name__})", environment=False) from None
        if read_hol != dict(holidays) or read_lunar != dict(lunar):
            raise FetchError("생성 파일 내용이 입력과 다릅니다", environment=False)
        ok, message = verify_holiday_data(SimpleNamespace(KOREAN_HOLIDAYS=read_hol, LUNAR_MAPPING=read_lunar))
        if not ok:
            raise FetchError(f"생성 데이터 검증 실패: {message}", environment=False)
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / path.name
        shutil.copy2(path, backup)
        os.replace(pending, path)
        return backup
    finally:
        if pending is not None and pending.exists():
            pending.unlink()  # 이 호출이 만든 임시 파일만 정리한다.


@dataclass(frozen=True)
class HolidayDiff:
    added: dict[str, str]
    removed: dict[str, str]
    renamed: dict[str, tuple[str, str]]  # 날짜 -> (이전, 새)


def diff_holidays(old: Mapping[str, str], new: Mapping[str, str]) -> HolidayDiff:
    """날짜 기준으로 추가·삭제·이름 변경을 나눈다."""
    return HolidayDiff(
        added={d: new[d] for d in new if d not in old},
        removed={d: old[d] for d in old if d not in new},
        renamed={d: (old[d], new[d]) for d in old if d in new and old[d] != new[d]},
    )


@dataclass(frozen=True)
class RefreshResult:
    status: str  # "up_to_date" | "updated" | "blocked"
    diff: HolidayDiff
    excluded_years: list[int]
    checked_at: str
    years: tuple[int, int]
    backup: Path | None


def _default_backup_dir() -> Path:
    return ROOT / "output" / "holiday-refresh" / datetime.now().strftime("%Y%m%d-%H%M%S")


def refresh_holidays(path: Path = HOLIDAYS_PATH, backup_dir: Path | None = None,
                     years: Iterable[int] = HOLIDAY_YEARS) -> RefreshResult:
    """공휴일만 다시 받아 비교한다. 추가만 있으면 교체하고, 삭제·변경이 있으면 쓰지 않는다."""
    years = list(years)
    old_holidays, old_lunar = read_holidays_module(path)
    existing_years = {int(date[:4]) for date in old_holidays}
    fetched = fetch_holiday_years(sorted(set(years) | existing_years))
    new_holidays, excluded = select_holiday_years(fetched, existing_years)
    diff = diff_holidays(old_holidays, new_holidays)
    checked_at = datetime.now().isoformat(timespec="seconds")
    span = (min(fetched), max(fetched)) if fetched else (min(years), max(years))
    backup = None
    if diff.removed or diff.renamed:
        status = "blocked"
    elif diff.added:
        backup = write_holidays_module(path, new_holidays, old_lunar, backup_dir or _default_backup_dir())
        status = "updated"
    else:
        status = "up_to_date"
    return RefreshResult(status, diff, excluded, checked_at, span, backup)


def fetch_lunar_years(years: Iterable[int]) -> dict[str, str]:
    """연도별 1~12월 음력을 받는다. 실패는 FetchError 그대로 올린다."""
    lunar: dict[str, str] = {}
    for year in years:
        for month in range(1, 13):
            for r in fetch_lunar_month(year, month):
                lunar[r["date"]] = r["lunar"]
        print(f"  {year}년 음력 완료")
        _pause()
    return lunar


def _print_diff(diff: HolidayDiff, excluded: list[int]) -> None:
    for date, name in sorted(diff.added.items()):
        print(f"  추가 {date} {name}")
    for date, name in sorted(diff.removed.items()):
        print(f"  삭제 {date} {name}")
    for date, (before, after) in sorted(diff.renamed.items()):
        print(f"  변경 {date} {before} -> {after}")
    if excluded:
        print(f"  제외 연도(핵심 공휴일 부족): {', '.join(map(str, excluded))}")
    if not (diff.added or diff.removed or diff.renamed):
        print("  공휴일 변경 없음")


def main() -> int:
    """음력·공휴일을 모두 다시 받아 holidays.py를 재생성한다 (삭제·변경도 받아들이는 수동 경로)."""
    print(f"=== 데이터 수집 ({HOLIDAY_YEARS[0]}~{HOLIDAY_YEARS[-1]}) ===")
    if not API_KEY:
        print("ERROR: LUNAR_API_KEY가 없습니다 (.env 확인)")
        return 1
    try:
        old_holidays, _ = read_holidays_module(HOLIDAYS_PATH)
        existing_years = {int(date[:4]) for date in old_holidays}
        print("▶ 음력 API 호출 중...")
        lunar = fetch_lunar_years(HOLIDAY_YEARS)
        print("\n▶ 공휴일 API 호출 중...")
        fetched = fetch_holiday_years(sorted(set(HOLIDAY_YEARS) | existing_years))
        holidays, excluded = select_holiday_years(fetched, existing_years)
        print("\n▶ 기존 holidays.py와 비교")
        _print_diff(diff_holidays(old_holidays, holidays), excluded)
        backup = write_holidays_module(HOLIDAYS_PATH, holidays, lunar, _default_backup_dir())
    except FetchError as e:
        print(f"ERROR: {e}")
        return 1
    print(f"\n[완료] 공휴일: {len(holidays)}건, 음력: {len(lunar)}건 (백업: {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
