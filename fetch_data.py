"""
fetch_data.py - 공공데이터포털 API에서 음력/공휴일 데이터 수집 (실제 API 데이터만 저장)
* API가 제공하는 범위(통상 1~2년 뒤까지)만 holidays.py로 생성한다.
* 미래 연도를 임의 계산해 채우지 않는다.
"""
import http.client
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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
    return True, f"OK (공휴일 {len(kh)}건, 음력 {len(lm)}건)"


def main():
    START_YEAR, END_YEAR = 2025, 2050
    print(f"=== 데이터 수집 ({START_YEAR}~{END_YEAR}) ===")
    
    if not API_KEY:
        print("ERROR: API KEY IS MISSING")
        return

    # 1. 음력 데이터 전체 수집
    lunar_mapping = {}
    print("▶ 음력 API 호출 중 (2025~2050)...")
    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            for r in fetch_lunar_month(year, month):
                lunar_mapping[r["date"]] = r["lunar"]
        print(f"  {year}년 음력 완료")
        time.sleep(0.1)

    # 2. 공휴일 데이터 수집 (API가 제공하는 연도만)
    holidays = {}
    print("\n▶ 공휴일 API 호출 중...")
    for year in range(START_YEAR, END_YEAR + 1):
        year_holidays = {}
        api_count = 0
        for month in range(1, 13):
            res = fetch_holidays(year, month)
            api_count += len(res)
            for r in res:
                year_holidays[r["date"]] = r["name"]
            if month % 4 == 0: time.sleep(0.1)
            
        if api_count > 0:
            print(f"  {year}년: API 데이터 사용 ({api_count}건)")
            holidays.update(year_holidays)
        else:
            print(f"  {year}년: API 데이터 없음 (생략)")

    # 3. 저장
    output_path = Path(__file__).parent / "holidays.py"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# holidays.py - 오프라인 한국 공휴일/음력 데이터 (2025-2050)\n")
        f.write("# 자동 생성됨 (fetch_data.py)\n")
        f.write("from datetime import date\n\n")
        
        f.write("KOREAN_HOLIDAYS = {\n")
        curr_y = None
        for k in sorted(holidays.keys()):
            if k[:4] != curr_y:
                curr_y = k[:4]
                f.write(f"\n    # {curr_y}\n")
            f.write(f'    "{k}": "{holidays[k]}",\n')
        f.write("}\n\n")

        f.write("LUNAR_MAPPING = {\n")
        curr_y = None
        for k in sorted(lunar_mapping.keys()):
            if k[:4] != curr_y:
                curr_y = k[:4]
                f.write(f"\n    # {curr_y}\n")
            f.write(f'    "{k}": "{lunar_mapping[k]}",\n')
        f.write("}\n\n")

        f.write('''def get_lunar_date(date_str: str) -> str:
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
''')

    print(f"\n[완료] 공휴일: {len(holidays)}건, 음력: {len(lunar_mapping)}건")

if __name__ == "__main__":
    main()
