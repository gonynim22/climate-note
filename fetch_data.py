"""
fetch_data.py - 공공데이터포털 API에서 음력/공휴일 데이터 수집 (실제 API 데이터만 저장)
* API가 제공하는 범위(통상 1~2년 뒤까지)만 holidays.py로 생성한다.
* 미래 연도를 임의 계산해 채우지 않는다.
"""
import os
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("LUNAR_API_KEY", "")

# ── API 호출 함수 ──
def fetch_holidays(year: int, month: int) -> list[dict]:
    params = urllib.parse.urlencode({"serviceKey": API_KEY, "solYear": f"{year:04d}", "solMonth": f"{month:02d}", "numOfRows": "50"})
    url = f"http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read().decode("utf-8")
        root = ET.fromstring(data)
        return [{"date": f"{i.findtext('locdate')[:4]}-{i.findtext('locdate')[4:6]}-{i.findtext('locdate')[6:8]}",
                 "name": i.findtext("dateName")}
                for i in root.findall(".//item") if i.findtext("isHoliday") == "Y"]
    except (urllib.error.URLError, ET.ParseError, TimeoutError, OSError):
        return []

def fetch_lunar_month(year: int, month: int) -> list[dict]:
    params = urllib.parse.urlencode({"serviceKey": API_KEY, "solYear": f"{year:04d}", "solMonth": f"{month:02d}", "numOfRows": "50"})
    url = f"http://apis.data.go.kr/B090041/openapi/service/LrsrCldInfoService/getLunCalInfo?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read().decode("utf-8")
        root = ET.fromstring(data)
        return [{"date": f"{i.findtext('solYear')}-{i.findtext('solMonth')}-{i.findtext('solDay')}",
                 "lunar": f"{int(i.findtext('lunMonth'))}.{int(i.findtext('lunDay'))}"}
                for i in root.findall(".//item")]
    except (urllib.error.URLError, ET.ParseError, TimeoutError, OSError, ValueError):
        return []

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
