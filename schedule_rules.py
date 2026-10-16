"""일정 시각·기간·반복·알림 규칙(v4.1).

Qt·DB에 의존하지 않는 순수 함수만 둔다. 저장(database.py)·가져오기·화면이 모두 이
모듈의 검증과 펼치기를 함께 쓴다. 읽기는 관대하게(규칙에 어긋난 저장값은 기본값처럼),
쓰기는 validate_options로 엄격하게 다룬다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
import calendar
from datetime import date, datetime, time, timedelta

REPEAT_RULES = ("", "daily", "weekdays", "weekly", "monthly", "yearly")
TIMED_ALARMS = (0, 10, 30, 60, 1440)
ALLDAY_ALARMS = (0, 1440)
MAX_SPAN_DAYS = 365
MAX_SKIPS = 500
KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")  # date.weekday() 순서

_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIME_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_TIME_INPUT_RE = re.compile(r"^([0-9]{1,2})(?::?([0-9]{2}))?$")


def parse_date(value) -> date:
    """'YYYY-MM-DD'만 받는다. 틀리면 ValueError."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError(f"날짜 형식이 올바르지 않습니다: {value!r}")
    return date.fromisoformat(value)


def parse_time_input(text) -> str:
    """'9'·'930'·'1430'·'14:30'을 'HH:MM'으로 바꾼다. 틀리면 ValueError."""
    match = _TIME_INPUT_RE.match((text or "").strip())
    if not match:
        raise ValueError("시각은 0930·14:30처럼 입력합니다.")
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) is not None else 0
    if hour > 23 or minute > 59:
        raise ValueError("시각은 00:00부터 23:59까지입니다.")
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class ScheduleOptions:
    """일정 한 건의 세부 설정. 기본값은 '하루 종일·하루·반복 없음·알림 없음'이다."""

    start_time: str = ""
    end_date: str = ""
    repeat_rule: str = ""
    repeat_until: str = ""
    repeat_skip: tuple[str, ...] = ()
    alarm_before: int | None = None

    @property
    def is_default(self) -> bool:
        return self == ScheduleOptions()

    @classmethod
    def from_row(cls, row) -> "ScheduleOptions":
        """DB 행(sqlite3.Row·dict)을 관대하게 읽는다. 규칙에 어긋난 값은 기본값처럼 다룬다."""
        def text(name: str) -> str:
            value = row[name]
            return value if isinstance(value, str) else ""

        start_time = text("start_time")
        rule = text("repeat_rule")
        alarm = row["alarm_before"]
        return cls(
            start_time=start_time if _TIME_RE.match(start_time) else "",
            end_date=text("end_date"),
            repeat_rule=rule if rule in REPEAT_RULES else "",
            repeat_until=text("repeat_until"),
            repeat_skip=tuple(day for day in text("repeat_skip").split(",") if day),
            alarm_before=alarm if type(alarm) is int else None,
        )

    def to_db_values(self) -> tuple:
        """(start_time, end_date, repeat_rule, repeat_until, repeat_skip, alarm_before) 순서."""
        return (self.start_time, self.end_date, self.repeat_rule,
                self.repeat_until, ",".join(self.repeat_skip), self.alarm_before)


def validate_options(start: str, options: ScheduleOptions) -> ScheduleOptions:
    """세부 설정이 규칙에 맞는지 검사하고 정규화(건너뛴 날 정렬·중복 제거)해 돌려준다."""
    for name in ("start_time", "end_date", "repeat_rule", "repeat_until"):
        if not isinstance(getattr(options, name), str):
            raise ValueError("세부 설정 형식이 올바르지 않습니다.")
    if not isinstance(options.repeat_skip, tuple) or not all(
            isinstance(day, str) for day in options.repeat_skip):
        raise ValueError("세부 설정 형식이 올바르지 않습니다.")
    start_day = parse_date(start)
    if options.start_time and not _TIME_RE.match(options.start_time):
        raise ValueError("시작 시각 형식이 올바르지 않습니다.")
    if options.repeat_rule not in REPEAT_RULES:
        raise ValueError("지원하지 않는 반복입니다.")
    if options.end_date:
        end_day = parse_date(options.end_date)
        if end_day <= start_day or (end_day - start_day).days > MAX_SPAN_DAYS:
            raise ValueError("기간 끝 날짜가 올바르지 않습니다.")
        if options.repeat_rule:
            raise ValueError("여러 날 일정은 반복할 수 없습니다.")
    if not options.repeat_rule and (options.repeat_until or options.repeat_skip):
        raise ValueError("반복이 아닌 일정에는 끝 날짜·건너뛴 날을 둘 수 없습니다.")
    if options.repeat_until and parse_date(options.repeat_until) < start_day:
        raise ValueError("반복 끝 날짜가 시작보다 앞섭니다.")
    skips = tuple(sorted(set(options.repeat_skip)))
    if len(skips) > MAX_SKIPS:
        raise ValueError("건너뛴 날이 너무 많습니다.")
    for day in skips:
        if parse_date(day) < start_day:
            raise ValueError("건너뛴 날이 시작보다 앞섭니다.")
    if options.alarm_before is not None:
        allowed = TIMED_ALARMS if options.start_time else ALLDAY_ALARMS
        if type(options.alarm_before) is not int or options.alarm_before not in allowed:
            raise ValueError("지원하지 않는 알림입니다.")
    return replace(options, repeat_skip=skips)


ALLDAY_ALARM_TIME = time(9, 0)


def add_months(day: date, months: int) -> date:
    """달 단위로 옮긴다. 없는 날짜는 그 달의 마지막 날로 맞춘다."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def occurrence_dates(start: str, options: ScheduleOptions, first: date, last: date) -> list[date]:
    """[first, last] 안에서 일정이 나타나는 날짜(오름차순)."""
    if last < first:
        return []
    begin = parse_date(start)
    if options.end_date:
        end = parse_date(options.end_date)
        low, high = max(begin, first), min(end, last)
        return [low + timedelta(days=i) for i in range((high - low).days + 1)] if low <= high else []
    rule = options.repeat_rule
    if not rule:
        return [begin] if first <= begin <= last else []
    stop = min(last, parse_date(options.repeat_until)) if options.repeat_until else last
    low = max(begin, first)
    if low > stop:
        return []
    result: list[date] = []
    if rule in ("daily", "weekdays"):
        day = low
        while day <= stop:
            if rule == "daily" or day.weekday() < 5:
                result.append(day)
            day += timedelta(days=1)
    elif rule == "weekly":
        day = low + timedelta(days=(begin.weekday() - low.weekday()) % 7)
        while day <= stop:
            result.append(day)
            day += timedelta(days=7)
    elif rule == "monthly":
        year, month = low.year, low.month
        while True:
            day = _clamped(year, month, begin.day)
            if day > stop:
                break
            if day >= low:
                result.append(day)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    elif rule == "yearly":
        year = low.year
        while True:
            day = _clamped(year, begin.month, begin.day)
            if day > stop:
                break
            if day >= low:
                result.append(day)
            year += 1
    skips = set(options.repeat_skip)
    return [day for day in result if day.isoformat() not in skips]


def occurs_on(start: str, options: ScheduleOptions, day: date) -> bool:
    return bool(occurrence_dates(start, options, day, day))


def occurrence_sort_key(shows_time: bool, start_time: str, schedule_id: int) -> tuple:
    """하루 목록 순서: 시각 없이 보이는 것(하루 종일·기간 둘째 날 이후) 먼저 ID 순, 그다음 시각·ID 순."""
    return (1, start_time, schedule_id) if shows_time else (0, "", schedule_id)


def alarm_base(day: date, options: ScheduleOptions) -> datetime:
    """알림 기준 시각: 그 날의 시작 시각(하루 종일이면 09:00)."""
    if options.start_time:
        hour, minute = (int(part) for part in options.start_time.split(":"))
        return datetime.combine(day, time(hour, minute))
    return datetime.combine(day, ALLDAY_ALARM_TIME)


def alarm_times(start: str, options: ScheduleOptions, after: datetime, until: datetime) -> list[tuple[date, datetime]]:
    """after < 알림 ≤ until 인 (날짜, 알림 시각) 목록. 기간 일정은 첫날만 알린다."""
    if options.alarm_before is None or until <= after:
        return []
    shift = timedelta(minutes=options.alarm_before)
    first = (after + shift).date() - timedelta(days=1)
    last = (until + shift).date() + timedelta(days=1)
    days_found = occurrence_dates(start, options, first, last)
    if options.end_date:
        begin = parse_date(start)
        days_found = [day for day in days_found if day == begin]
    result = []
    for day in days_found:
        due = alarm_base(day, options) - shift
        if after < due <= until:
            result.append((day, due))
    return result


@dataclass(frozen=True)
class AlarmItem:
    """알릴 일정 한 건(어느 날짜의 어느 시각에 울릴지)."""

    schedule_id: int
    occurrence_date: str
    due: datetime
    content: str
    color: str
    start_time: str
    decryption_failed: bool = False

    @property
    def key(self) -> tuple:
        return (self.schedule_id, self.occurrence_date, self.due)


def with_start_time(options: ScheduleOptions, start_time: str) -> ScheduleOptions:
    """시각을 바꾼다. 하루 종일↔시각으로 방식이 바뀔 때만 두 방식에 모두 있는 알림(0·1440)을 남긴다."""
    if bool(start_time) == bool(options.start_time):
        return replace(options, start_time=start_time)
    alarm = options.alarm_before if options.alarm_before in (None, 0, 1440) else None
    return replace(options, start_time=start_time, alarm_before=alarm)


def with_repeat(options: ScheduleOptions, start: str, rule: str) -> ScheduleOptions:
    """반복을 바꾼다. 끄면 끝 날짜·건너뛴 날도 지우고, 종류를 바꾸면 건너뛴 날을 비운다."""
    if rule == options.repeat_rule:
        return options
    if not rule:
        return replace(options, repeat_rule="", repeat_until="", repeat_skip=())
    until = options.repeat_until
    if until and parse_date(until) < parse_date(start):
        until = ""
    return replace(options, repeat_rule=rule, repeat_until=until, repeat_skip=(), end_date="")


def clear_part(options: ScheduleOptions, start: str, kind: str) -> ScheduleOptions:
    """알약의 ×: 그 항목만 지운다(시각을 지우면 알림도 지운다)."""
    if kind == "time":
        return replace(options, start_time="", alarm_before=None)
    if kind == "alarm":
        return replace(options, alarm_before=None)
    if kind == "period":
        return replace(options, end_date="")
    if kind == "repeat":
        return with_repeat(options, start, "")
    raise ValueError(f"알 수 없는 항목입니다: {kind}")


def rebase_options(options: ScheduleOptions, old_start: str, new_start: str) -> ScheduleOptions:
    """고른 날짜가 바뀔 때 보류 중 값을 새 날짜 기준으로 옮긴다(기간 길이 유지, 지난 끝 날짜 제거)."""
    if old_start == new_start:
        return options
    end_date = ""
    if options.end_date:
        length = parse_date(options.end_date) - parse_date(old_start)
        end_date = (parse_date(new_start) + length).isoformat()
    until = options.repeat_until
    if until and parse_date(until) < parse_date(new_start):
        until = ""
    return replace(options, end_date=end_date, repeat_until=until, repeat_skip=())
