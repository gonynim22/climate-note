"""일정 시각·기간·반복·알림 규칙(v4.1).

Qt·DB에 의존하지 않는 순수 함수만 둔다. 저장(database.py)·가져오기·화면이 모두 이
모듈의 검증과 펼치기를 함께 쓴다. 읽기는 관대하게(규칙에 어긋난 저장값은 기본값처럼),
쓰기는 validate_options로 엄격하게 다룬다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
import calendar
import math
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
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError(f"날짜 형식이 올바르지 않습니다: {value!r}")
    return date.fromisoformat(value)


def parse_time_input(text) -> str:
    """'9'·'930'·'1430'·'14:30'을 'HH:MM'으로 바꾼다. 틀리면 ValueError."""
    match = _TIME_INPUT_RE.fullmatch((text or "").strip())
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

        def valid_date(value: str) -> str:
            try:
                parse_date(value)
            except ValueError:
                return ""
            return value

        start_time = text("start_time")
        if not _TIME_RE.fullmatch(start_time):
            start_time = ""
        rule = text("repeat_rule")
        alarm = row["alarm_before"]
        allowed = TIMED_ALARMS if start_time else ALLDAY_ALARMS
        end_date = valid_date(text("end_date"))
        # 줄의 날짜보다 늦지 않은 끝 날짜는 일정이 보이지 않게 만들므로 버린다.
        row_date = valid_date(text("date")) if "date" in row.keys() else ""
        if end_date and row_date and end_date <= row_date:
            end_date = ""
        return cls(
            start_time=start_time,
            end_date=end_date,
            repeat_rule=rule if rule in REPEAT_RULES else "",
            repeat_until=valid_date(text("repeat_until")),
            repeat_skip=tuple(day for day in text("repeat_skip").split(",") if valid_date(day)),
            alarm_before=alarm if type(alarm) is int and alarm in allowed else None,
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
    if options.start_time and not _TIME_RE.fullmatch(options.start_time):
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


@dataclass(frozen=True)
class SpanSegment:
    """한 주 줄 안의 기간 막대 조각."""

    key: int          # 일정 ID
    row: int          # 달력의 주 번호(0부터)
    first_col: int    # 0=일요일
    last_col: int
    starts: bool      # 이 조각에서 일정이 시작하는가(왼쪽 둥근 끝)
    ends: bool        # 이 조각에서 일정이 끝나는가(오른쪽 둥근 끝)
    lane: int = 0


def week_segments(weeks: list[list[str]], spans: dict[int, tuple[str, str]]) -> list[SpanSegment]:
    """weeks: 주마다 7칸의 'YYYY-MM-DD' 또는 ''(빈칸). spans: 일정 ID → (시작, 끝)."""
    segments = []
    for row, days_in_week in enumerate(weeks):
        for key, (span_start, span_end) in spans.items():
            cols = [col for col, day in enumerate(days_in_week) if day and span_start <= day <= span_end]
            if not cols:
                continue
            first_col, last_col = cols[0], cols[-1]
            segments.append(SpanSegment(
                key, row, first_col, last_col,
                days_in_week[first_col] == span_start, days_in_week[last_col] == span_end,
            ))
    return assign_lanes(segments)


def assign_lanes(segments: list[SpanSegment]) -> list[SpanSegment]:
    """같은 주에서 시작 열·긴 순·ID 순으로 겹치지 않는 가장 위 차선을 준다."""
    placed = []
    taken: dict[int, list[list[tuple[int, int]]]] = {}
    ordered = sorted(segments, key=lambda s: (s.row, s.first_col, -(s.last_col - s.first_col), s.key))
    for segment in ordered:
        lanes = taken.setdefault(segment.row, [])
        lane = 0
        while lane < len(lanes) and any(
                not (segment.last_col < a or segment.first_col > b) for a, b in lanes[lane]):
            lane += 1
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append((segment.first_col, segment.last_col))
        placed.append(replace(segment, lane=lane))
    return placed


def korean_date(day: date) -> str:
    return f"{day.month}월 {day.day}일 ({KOREAN_WEEKDAYS[day.weekday()]})"


def repeat_caption(start: str, rule: str, *, note: bool = True) -> str:
    day = parse_date(start)
    if rule == "daily":
        return "매일"
    if rule == "weekdays":
        return "평일(월~금)"
    if rule == "weekly":
        return f"매주 {KOREAN_WEEKDAYS[day.weekday()]}요일"
    if rule == "monthly":
        extra = " (없는 달은 마지막 날)" if note and day.day >= 29 else ""
        return f"매월 {day.day}일{extra}"
    if rule == "yearly":
        extra = " (평년은 2월 28일)" if note and (day.month, day.day) == (2, 29) else ""
        return f"매년 {day.month}월 {day.day}일{extra}"
    return ""


def repeat_pill(start: str, options: ScheduleOptions) -> str:
    day = parse_date(start)
    short = {
        "daily": "매일", "weekdays": "평일",
        "weekly": f"매주 {KOREAN_WEEKDAYS[day.weekday()]}",
        "monthly": f"매월 {day.day}일", "yearly": f"매년 {day.month}.{day.day}",
    }.get(options.repeat_rule, "")
    if short and options.repeat_until:
        until = parse_date(options.repeat_until)
        short += f" · ~{until.month:02d}.{until.day:02d}"
    return short


def alarm_label(options: ScheduleOptions, *, short: bool = False) -> str:
    if options.alarm_before is None:
        return ""
    if options.start_time:
        return {0: "정시", 10: "10분 전", 30: "30분 전", 60: "1시간 전", 1440: "하루 전"}[options.alarm_before]
    if short:
        return {0: "당일 9시", 1440: "하루 전 9시"}[options.alarm_before]
    return {0: "당일 오전 9시", 1440: "하루 전 오전 9시"}[options.alarm_before]


def time_pill(options: ScheduleOptions) -> str:
    if not options.start_time:
        return ""
    alarm = alarm_label(options)
    return f"{options.start_time} · {alarm}" if alarm else options.start_time


def alarm_caption(day: date, options: ScheduleOptions) -> str:
    """세부 카드의 시각 알림 설명. 다른 날에 울리면 날짜도 붙인다."""
    if not options.start_time or options.alarm_before is None:
        return ""
    alarm_at = alarm_base(day, options) - timedelta(minutes=options.alarm_before)
    when = alarm_at.strftime("%H:%M")
    if alarm_at.date() != day:
        alarm_day = alarm_at.date()
        when = f"{alarm_day.month}월 {alarm_day.day}일({KOREAN_WEEKDAYS[alarm_day.weekday()]}) {when}"
    return f"{alarm_label(options)}, {when}에 알림"


def span_days(start: str, options: ScheduleOptions) -> int:
    if not options.end_date:
        return 1
    return (parse_date(options.end_date) - parse_date(start)).days + 1


def span_pill(start: str, options: ScheduleOptions) -> str:
    if not options.end_date:
        return ""
    end = parse_date(options.end_date)
    return f"~{end.month:02d}.{end.day:02d} · {span_days(start, options)}일"


def range_text(start: str, end: str) -> str:
    a, b = parse_date(start), parse_date(end)
    if a.year == b.year:
        return f"{a.month:02d}.{a.day:02d}~{b.month:02d}.{b.day:02d}"
    return f"{a.year % 100:02d}.{a.month:02d}.{a.day:02d}~{b.year % 100:02d}.{b.month:02d}.{b.day:02d}"


def period_caption(start: str, end: str) -> str:
    a, b = parse_date(start), parse_date(end)
    left = f"{a.month}월 {a.day}일({KOREAN_WEEKDAYS[a.weekday()]})"
    if (a.year, a.month) == (b.year, b.month):
        right = f"{b.day}일({KOREAN_WEEKDAYS[b.weekday()]})"
    else:
        right = f"{b.month}월 {b.day}일({KOREAN_WEEKDAYS[b.weekday()]})"
    return f"{left} ~ {right} · {(b - a).days + 1}일"


def period_short_caption(start: str, end: str) -> str:
    """세부 카드 기간 글자. 끝날의 달·해는 시작일과 다를 때만 붙인다."""
    a, b = parse_date(start), parse_date(end)
    right = f"{b.day}일({KOREAN_WEEKDAYS[b.weekday()]})"
    if (a.year, a.month) != (b.year, b.month):
        right = f"{b.month}월 {right}"
    if a.year != b.year:
        right = f"{b.year}년 {right}"
    return f"~ {right} · {(b - a).days + 1}일"


def options_summary(start: str, options: ScheduleOptions) -> str:
    """편집 요약·툴팁용 한 줄. 예: '10:00 · 10분 전 · 매주 월요일'."""
    parts = []
    if options.start_time:
        parts.append(options.start_time)
    alarm = alarm_label(options)
    if alarm:
        parts.append(alarm if options.start_time else f"알림 {alarm}")
    if options.end_date:
        parts.append(range_text(start, options.end_date))
    if options.repeat_rule:
        parts.append(repeat_caption(start, options.repeat_rule))
        if options.repeat_until:
            until = parse_date(options.repeat_until)
            parts.append(f"{until.month}월 {until.day}일까지")
    return " · ".join(parts)


def search_suffix(start: str, options: ScheduleOptions) -> str:
    """검색 결과 본문 칸 끝의 표시용 꼬리(저장값은 바꾸지 않는다)."""
    try:
        if options.repeat_rule:
            caption = repeat_caption(start, options.repeat_rule, note=False)
            return f" ({caption} 반복)" if caption else ""
        if options.end_date:
            end = parse_date(options.end_date)
            return f" (~{end.month:02d}.{end.day:02d})"
    except ValueError:
        return ""
    return ""


def alarm_subtitle(start_time: str, day: date, now: datetime) -> str:
    """알림 카드 설명 줄. 예: '10분 뒤 시작 · 10월 15일 (목)'."""
    if start_time:
        hour, minute = (int(part) for part in start_time.split(":"))
        base = datetime.combine(day, time(hour, minute))
        minutes = math.ceil((base - now).total_seconds() / 60)
        if minutes < 0:
            head = f"{start_time}에 시작함"
        elif minutes == 0:
            head = "지금 시작"
        elif minutes < 60:
            head = f"{minutes}분 뒤 시작"
        elif minutes == 60:
            head = "1시간 뒤 시작"  # '1시간 전' 알림이 울리는 때(§4.9)
        elif day == now.date() + timedelta(days=1):
            head = f"내일 {start_time} 시작"
        else:
            head = f"{start_time} 시작"
    elif day == now.date():
        head = "오늘 하루 종일"
    elif day == now.date() + timedelta(days=1):
        head = "내일 하루 종일"
    else:
        head = "하루 종일"
    return f"{head} · {korean_date(day)}"


def until_caption(until: str) -> str:
    """반복 끝 설명. 예: '12월 31일(목)까지'."""
    day = parse_date(until)
    return f"{day.month}월 {day.day}일({KOREAN_WEEKDAYS[day.weekday()]})까지"


def detail_lines(start: str, options: ScheduleOptions) -> list[str]:
    """목록 툴팁에서 본문 다음 줄로 붙일 설명. 기본값이면 빈 목록."""
    lines = []
    if options.start_time:
        lines.append(f"시작: {options.start_time}")
    if options.end_date:
        lines.append(f"기간: {range_text(start, options.end_date)} · {span_days(start, options)}일")
    if options.repeat_rule:
        end = until_caption(options.repeat_until) if options.repeat_until else "계속"
        lines.append(f"{repeat_caption(start, options.repeat_rule)} 반복 · 끝: {end}")
    alarm = alarm_label(options)
    if alarm:
        lines.append(f"알림: {alarm}")
    return lines
