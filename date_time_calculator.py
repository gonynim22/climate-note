"""오프라인 날짜·시간 계산. 원본 기간은 소수점 없는 정수 초로 유지한다."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Iterable

from holidays import KOREAN_HOLIDAYS


HOLIDAY_DATES = frozenset(date.fromisoformat(key) for key in KOREAN_HOLIDAYS)
HOLIDAY_YEARS = frozenset(day.year for day in HOLIDAY_DATES)
HOLIDAY_RANGE = f"{min(HOLIDAY_YEARS)}–{max(HOLIDAY_YEARS)}년"


@dataclass(frozen=True)
class CalendarResult:
    value: datetime
    adjusted: bool


@dataclass(frozen=True)
class CalendarDelta:
    sign: int
    years: int
    months: int
    days: int
    hours: int
    minutes: int
    seconds: int


@dataclass(frozen=True)
class WorkdayResult:
    count: int
    total: int
    excluded: int


def _integer(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label}은 정수로 입력해 주세요.")


def _datetime(value: datetime) -> None:
    if not isinstance(value, datetime):
        raise ValueError("날짜와 시각을 함께 입력해 주세요.")
    if value.tzinfo is not None:
        raise ValueError("시간대 변환 없이 현지 날짜와 시각을 입력해 주세요.")
    if value.microsecond:
        raise ValueError("시각은 초 단위까지 입력해 주세요.")


def parse_date(text: str) -> date:
    """YYYY-MM-DD 형식. 잘못된 날짜를 다음 달로 넘겨 보정하지 않는다."""
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text.strip()):
        raise ValueError("날짜를 YYYY-MM-DD 형식으로 입력해 주세요.")
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise ValueError("유효한 날짜를 입력해 주세요. 지원 범위는 1~9999년입니다.") from exc


def parse_time(text: str) -> time:
    """24시간제 H:MM / HH:MM / HH:MM:SS를 읽는다."""
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?", text.strip()):
        raise ValueError("시각을 12:00 또는 12:00:30 형식으로 입력해 주세요.")
    parts = [int(part) for part in text.strip().split(":")]
    try:
        return time(*parts)
    except ValueError as exc:
        raise ValueError("시각은 00:00:00~23:59:59 범위로 입력해 주세요.") from exc


def difference_seconds(start: datetime, end: datetime) -> int:
    """종료 - 시작. 역순은 음수이며 부동소수점 total_seconds를 쓰지 않는다."""
    _datetime(start)
    _datetime(end)
    delta = end - start
    return delta.days * 86400 + delta.seconds


def interval_seconds(start: datetime, end: datetime, break_minutes: int = 0) -> int:
    """근무 구간의 순서와 휴게 공제 범위를 검사한다."""
    elapsed = difference_seconds(start, end)
    _integer(break_minutes, "휴게 분")
    if elapsed < 0:
        raise ValueError("종료가 시작보다 빠릅니다. 날짜·다음 날 설정을 확인하거나 시작과 종료를 바꿔 주세요.")
    if break_minutes < 0:
        raise ValueError("휴게 분은 0 이상으로 입력해 주세요.")
    result = elapsed - break_minutes * 60
    if result < 0:
        raise ValueError("휴게 공제가 전체 시간 구간을 초과합니다.")
    return result


def add_calendar(base: datetime, *, years: int = 0, months: int = 0,
                 days: int = 0, hours: int = 0, minutes: int = 0,
                 seconds: int = 0, sign: int = 1) -> CalendarResult:
    """년·월을 한 번 이동한 뒤 일·시·분·초를 적용한다. 크기는 양수, 방향은 sign."""
    _datetime(base)
    _integer(sign, "연산 방향")
    if sign not in (-1, 1):
        raise ValueError("더하기 또는 빼기를 선택해 주세요.")
    for label, value in (("년", years), ("월", months), ("일", days),
                         ("시간", hours), ("분", minutes), ("초", seconds)):
        _integer(value, label)
        if value < 0:
            raise ValueError(f"{label}은 0 이상으로 입력하고 더하기·빼기를 선택해 주세요.")
    total_month = (base.year - 1) * 12 + base.month - 1 + sign * (years * 12 + months)
    if not 0 <= total_month < 9999 * 12:
        raise ValueError("계산 결과가 지원 범위인 1~9999년을 벗어납니다.")
    year, month = divmod(total_month, 12)
    year, month = year + 1, month + 1
    day = min(base.day, monthrange(year, month)[1])
    adjusted = day != base.day
    moved = base.replace(year=year, month=month, day=day)
    fixed_seconds = sign * (days * 86400 + hours * 3600 + minutes * 60 + seconds)
    try:
        return CalendarResult(moved + timedelta(seconds=fixed_seconds), adjusted)
    except OverflowError as exc:
        raise ValueError("계산 결과가 지원 범위인 1~9999년을 벗어납니다.") from exc


def calendar_difference(start: datetime, end: datetime) -> CalendarDelta:
    """정렬한 앞 시각에서 뒤를 넘지 않는 최대 총 월수를 한 번 적용해 분해한다."""
    elapsed = difference_seconds(start, end)
    sign = (elapsed > 0) - (elapsed < 0)
    first, last = (start, end) if elapsed >= 0 else (end, start)
    months = (last.year - first.year) * 12 + last.month - first.month
    anchor = add_calendar(first, months=months).value
    if anchor > last:
        months -= 1
        anchor = add_calendar(first, months=months).value
    years, months = divmod(months, 12)
    remaining = difference_seconds(anchor, last)
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds = divmod(remaining, 60)
    return CalendarDelta(sign, years, months, days, hours, minutes, seconds)


def working_days(start: date, end: date, *, excluded_weekdays=frozenset({5, 6}),
                 exclude_holidays: bool = True, include_start: bool = True,
                 include_end: bool = True) -> WorkdayResult:
    """양 끝 포함 선택 후 요일·공휴일의 합집합을 뺀다. 긴 구간은 주 단위 집계."""
    if type(start) is not date or type(end) is not date:
        raise ValueError("근무일 계산에는 시작 날짜와 종료 날짜를 입력해 주세요.")
    if end < start:
        raise ValueError("종료 날짜가 시작 날짜보다 빠릅니다. 시작과 종료를 바꿔 주세요.")
    if any(type(value) is not bool for value in (exclude_holidays, include_start, include_end)):
        raise ValueError("포함일과 공휴일 제외 여부를 선택해 주세요.")
    try:
        weekdays = frozenset(excluded_weekdays)
    except TypeError as exc:
        raise ValueError("제외할 요일을 선택해 주세요.") from exc
    for weekday in weekdays:
        _integer(weekday, "요일 번호")
        if not 0 <= weekday <= 6:
            raise ValueError("요일 번호는 월요일 0부터 일요일 6까지입니다.")
    if exclude_holidays and any(year not in HOLIDAY_YEARS for year in range(start.year, end.year + 1)):
        raise ValueError(f"공휴일 자료는 {HOLIDAY_RANGE}만 있습니다. 해당 범위로 바꾸거나 공휴일 제외를 꺼 주세요.")
    first = start.toordinal() + (not include_start)
    last = end.toordinal() - (not include_end)
    total = max(0, last - first + 1)
    if not total:
        return WorkdayResult(0, 0, 0)
    weeks, extra = divmod(total, 7)
    count = weeks * (7 - len(weekdays))
    first_weekday = (first - 1) % 7
    count += sum((first_weekday + offset) % 7 not in weekdays for offset in range(extra))
    if exclude_holidays:
        count -= sum(first <= holiday.toordinal() <= last and holiday.weekday() not in weekdays
                     for holiday in HOLIDAY_DATES)
    return WorkdayResult(count, total, total - count)


def sum_durations(rows: Iterable[int]) -> int:
    total = 0
    for seconds in rows:
        _integer(seconds, "기간 초")
        total += seconds
    return total


def format_duration(seconds: int) -> str:
    _integer(seconds, "기간 초")
    sign = "-" if seconds < 0 else ""
    days, remainder = divmod(abs(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, remainder = divmod(remainder, 60)
    parts = [f"{value:,}{label}" for value, label in
             ((days, "일"), (hours, "시간"), (minutes, "분"), (remainder, "초")) if value]
    return sign + " ".join(parts) if parts else "0초"


def format_minutes(seconds: int) -> str:
    _integer(seconds, "기간 초")
    sign = "-" if seconds < 0 else ""
    minutes, remainder = divmod(abs(seconds), 60)
    return f"{sign}{minutes:,}분" + (f" {remainder}초" if remainder else "")


def minute_value(seconds: int, policy: str = "exact") -> str:
    """복사용 분 숫자. exact는 최대 소수 12자리, 반올림 동점은 0에서 먼 쪽.

    1초/60분의 순환소수는 유한 숫자로 복사할 수 없어 12자리에서 반올림한다.
    본문 결과·계산 기록은 format_minutes와 정수 초를 사용해 원본을 보존한다.
    floor/ceil은 수학적 내림/올림이다(-90초 → -2 / -1분).
    """
    _integer(seconds, "기간 초")
    if policy == "floor":
        return str(seconds // 60)
    if policy == "ceil":
        return str(-(-seconds // 60))
    if policy == "nearest":
        result = (abs(seconds) + 30) // 60
        return str(-result if seconds < 0 else result)
    if policy != "exact":
        raise ValueError("분 숫자의 소수·내림·반올림·올림 방식을 선택해 주세요.")
    scale = 10 ** 12
    scaled = (abs(seconds) * scale + 30) // 60
    whole, fractional = divmod(scaled, scale)
    result = str(whole)
    if fractional:
        result += "." + f"{fractional:012d}".rstrip("0")
    return ("-" if seconds < 0 and scaled else "") + result
