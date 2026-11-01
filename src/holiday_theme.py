"""공휴일 테마 판정 규칙과 색표(v4.6).

Qt·DB에 의존하지 않는 순수 모듈이다. 화면 코드는 이 모듈이 돌려주는 결과만 읽고,
날짜는 current_match()로만 얻는다. 판정은 holidays.KOREAN_HOLIDAYS 자료의 이름과
날짜만 쓰며 음력·공휴일을 계산하지 않는다. 테마는 화면 전용이라 아무것도 저장하지 않는다.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

import holidays as _holidays

# 판정 순서이자 겹침 마지막 단계(4번)의 우선순위다.
THEME_KEYS: tuple[str, ...] = (
    "newyear", "seollal", "samil", "labor", "children", "buddha", "memorial",
    "constitution", "liberation", "chuseok", "gaecheon", "hangul", "christmas",
)

# 공휴일 이름에 이 글자가 '들어 있으면' 해당 테마의 날짜다(포함 비교).
# 신정의 자료 이름은 '신정'이 아니라 '1월1일'이다.
MATCH_NAMES: dict[str, str] = {
    "newyear": "1월1일",
    "seollal": "설날",
    "samil": "삼일절",
    "labor": "노동절",
    "children": "어린이날",
    "buddha": "부처님오신날",
    "memorial": "현충일",
    "constitution": "제헌절",
    "liberation": "광복절",
    "chuseok": "추석",
    "gaecheon": "개천절",
    "hangul": "한글날",
    "christmas": "기독탄신일",
}

LEAD_DAYS = 3        # 묶음 첫날 며칠 전부터 보이는가
GROUP_GAP_DAYS = 7   # 같은 키의 날짜끼리 이 간격 이내면 한 묶음
DEFAULT_HEADER = "#01295F"  # 테마가 없을 때의 캘린더 머리줄 남색


@dataclass(frozen=True)
class HolidayTheme:
    """테마 하나의 색과 문구. 장식 모양은 화면 모듈이 key로 찾아 그린다."""
    key: str
    header: str      # 캘린더 머리줄
    today: str       # 오늘 칸
    tint: str        # 공휴일 칸 바탕(집중 위젯 바탕의 가운데 색도 같다)
    cover: str       # D-Day 커버
    accent: str      # 점·인사말 강조
    focus_end: str   # 집중 위젯 바탕 끝색
    band: str        # 스티키 띠(색동은 band_stripes가 우선)
    band_icon: str   # 스티키 아이콘
    greeting: str    # 인사말(공휴일 첫날~마지막 날에만 보인다)
    band_stripes: tuple[str, ...] = ()
    motion: bool = True  # 현충일은 추모일이라 움직임이 없다


THEMES: dict[str, HolidayTheme] = {
    t.key: t for t in (
        HolidayTheme("newyear", header="#24315E", today="#B9502C", tint="#FCEFE6",
                     cover="#24315E", accent="#B9502C", focus_end="#F8DCC8",
                     band="#FBDDBF", band_icon="#7A3E22",
                     greeting="새해 첫날, 좋은 시작 되세요"),
        HolidayTheme("seollal", header="#5A1F3A", today="#8E2A4E", tint="#FBEDF1",
                     cover="#5A1F3A", accent="#8E2A4E", focus_end="#F6D5DF",
                     band="#F6B0B0", band_icon="#4A1A30",
                     greeting="새해 복 많이 받으세요",
                     band_stripes=("#F6B0B0", "#FBE38E", "#B5DDB1", "#B4CDF0", "#F4BEDB")),
        HolidayTheme("samil", header="#2B3A5C", today="#2B3A5C", tint="#EEF1F7",
                     cover="#2B3A5C", accent="#2B3A5C", focus_end="#DCE3F0",
                     band="#F2ECDF", band_icon="#2B3A5C",
                     greeting="3·1 정신을 기억합니다"),
        HolidayTheme("labor", header="#5B4636", today="#7A5A3E", tint="#F6EFE6",
                     cover="#5B4636", accent="#7A5A3E", focus_end="#EADBC6",
                     band="#E6D2B5", band_icon="#5B4636",
                     greeting="오늘도 수고 많으셨어요"),
        HolidayTheme("children", header="#2F6FB7", today="#2F6FB7", tint="#EAF3FC",
                     cover="#2F6FB7", accent="#2F6FB7", focus_end="#D3E6FA",
                     band="#DCEBFA", band_icon="#24507F",
                     greeting="마음껏 웃는 하루 되세요"),
        HolidayTheme("buddha", header="#21444A", today="#2D5C63", tint="#EEF5F4",
                     cover="#21444A", accent="#2D5C63", focus_end="#D6EAE7",
                     band="#D9EBE8", band_icon="#21444A",
                     greeting="연등처럼 환한 하루 되세요"),
        HolidayTheme("memorial", header="#3A3F47", today="#3A3F47", tint="#F0F1F3",
                     cover="#3A3F47", accent="#4A515B", focus_end="#E1E3E7",
                     band="#E4E6E9", band_icon="#3A3F47",
                     greeting="희생하신 분들을 기억합니다", motion=False),
        HolidayTheme("constitution", header="#1E4D5C", today="#1E4D5C", tint="#EAF3F5",
                     cover="#1E4D5C", accent="#1E4D5C", focus_end="#D3E7EC",
                     band="#D7E8EC", band_icon="#1E4D5C",
                     greeting="헌법이 세워진 날, 제헌절"),
        HolidayTheme("liberation", header="#173A6B", today="#173A6B", tint="#EAF0F9",
                     cover="#173A6B", accent="#173A6B", focus_end="#D5E1F3",
                     band="#FBE3EA", band_icon="#173A6B",
                     greeting="빛을 되찾은 날, 광복절"),
        HolidayTheme("chuseok", header="#222A5A", today="#3A468C", tint="#EEF0FA",
                     cover="#222A5A", accent="#3A468C", focus_end="#DADFF4",
                     band="#2B3468", band_icon="#FFFFFF",
                     greeting="풍성한 한가위 보내세요"),
        HolidayTheme("gaecheon", header="#245E91", today="#245E91", tint="#EAF2FA",
                     cover="#245E91", accent="#245E91", focus_end="#D2E4F5",
                     band="#D9E9F7", band_icon="#245E91",
                     greeting="하늘이 열린 날, 개천절"),
        HolidayTheme("hangul", header="#2B2A2F", today="#2B2A2F", tint="#F4F0E7",
                     cover="#3B3631", accent="#8A3B30", focus_end="#E8DFCC",
                     band="#F3E7CF", band_icon="#6B4B32",
                     greeting="고운 우리말, 한글날"),
        HolidayTheme("christmas", header="#1D4A3A", today="#1D4A3A", tint="#EEF5EF",
                     cover="#1D4A3A", accent="#2F6A50", focus_end="#D8EADB",
                     band="#DCEBDD", band_icon="#2F5A45",
                     greeting="메리 크리스마스"),
    )
}


@dataclass(frozen=True)
class HolidayThemeMatch:
    """오늘 입을 테마와 그 공휴일 묶음의 기간."""
    theme: HolidayTheme
    first_day: date
    last_day: date
    dates: tuple[date, ...]  # 묶음에 든 실제 공휴일 날짜(대체공휴일 포함)
    in_holiday: bool         # 첫날~마지막 날이면 True(인사말 표시 여부), 예고 기간이면 False


def _parse_dates(holidays: Mapping[str, str]) -> list[tuple[date, str]]:
    """'YYYY-MM-DD' 키만 날짜로 읽는다. 형식이 틀린 키는 건너뛴다."""
    parsed = []
    for raw, name in holidays.items():
        try:
            parsed.append((date.fromisoformat(raw), name))
        except (TypeError, ValueError):
            continue  # 판정 자료의 깨진 행 하나가 화면 전체를 막지 않게 한다
    return parsed


def _groups_for(dates: list[date]) -> list[list[date]]:
    """정렬된 날짜를 GROUP_GAP_DAYS 이내 간격끼리 묶는다."""
    groups: list[list[date]] = []
    for day in sorted(set(dates)):
        if groups and (day - groups[-1][-1]).days <= GROUP_GAP_DAYS:
            groups[-1].append(day)
        else:
            groups.append([day])
    return groups


def resolve_holiday_theme(today: date, holidays: Mapping[str, str]) -> HolidayThemeMatch | None:
    """오늘 입을 테마 하나를 고른다. 없으면 None.

    보이는 기간은 [묶음 첫날 - LEAD_DAYS, 묶음 마지막 날]이다. 기간이 겹치면
    ① 진행 중인 묶음 ② 첫날이 가까운 묶음 ③ 연휴가 긴 묶음 ④ THEME_KEYS 순서로 고른다.
    진행 중인 묶음끼리는 첫날 거리를 0으로 보므로 ②를 건너뛰고 ③으로 간다.
    """
    entries = _parse_dates(holidays)
    best_key = None
    best_match = None
    for index, key in enumerate(THEME_KEYS):
        name = MATCH_NAMES[key]
        # 괄호 없는 '대체공휴일'·'임시공휴일'은 이름에 판정 이름이 없으므로 어느 묶음에도 들지 않는다.
        days = [day for day, label in entries if name in label]
        for group in _groups_for(days):
            first, last = group[0], group[-1]
            if not (first - timedelta(days=LEAD_DAYS) <= today <= last):
                continue
            in_progress = first <= today
            sort_key = (
                0 if in_progress else 1,
                max(0, (first - today).days),
                -(last - first).days,
                index,
            )
            if best_key is None or sort_key < best_key:
                best_key = sort_key
                best_match = HolidayThemeMatch(
                    theme=THEMES[key], first_day=first, last_day=last,
                    dates=tuple(group), in_holiday=in_progress,
                )
    return best_match


def current_match(today: date | None = None) -> HolidayThemeMatch | None:
    """화면 코드가 날짜를 얻는 유일한 입구다. today가 없으면 오늘이다."""
    return resolve_holiday_theme(today or date.today(), _holidays.KOREAN_HOLIDAYS)
