"""일정 시각·기간·반복·알림 규칙(v4.1).

Qt·DB에 의존하지 않는 순수 함수만 둔다. 저장(database.py)·가져오기·화면이 모두 이
모듈의 검증과 펼치기를 함께 쓴다. 읽기는 관대하게(규칙에 어긋난 저장값은 기본값처럼),
쓰기는 validate_options로 엄격하게 다룬다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

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
