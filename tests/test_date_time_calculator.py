"""초 원본·달력 월말·실제 번들 공휴일에 대한 독립 기준 사례."""

from datetime import date, datetime, time, timezone

import pytest

from date_time_calculator import (
    CalendarDelta, CalendarResult, WorkdayResult, add_calendar,
    calendar_difference, difference_seconds, format_duration, format_minutes,
    interval_seconds, minute_value, parse_date, parse_time, sum_durations,
    working_days,
)


@pytest.mark.parametrize("text,expected", [
    ("2026-09-24", date(2026, 9, 24)), (" 2024-02-29 ", date(2024, 2, 29)),
    ("0001-01-01", date.min), ("9999-12-31", date.max),
])
def test_date_parser(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", [
    "2026-02-29", "2026-04-31", "0000-01-01", "10000-01-01", "20260924",
    "2026-9-24", "26-09-24", "2026-W39-4", "2026/09/24", "", None,
])
def test_date_parser_rejects_invalid_or_ambiguous_inputs(text):
    with pytest.raises(ValueError):
        parse_date(text)


@pytest.mark.parametrize("text,expected", [
    ("12:00", time(12)), ("9:05", time(9, 5)), (" 23:59:59 ", time(23, 59, 59)),
    ("00:00:00", time()), ("9:05:07", time(9, 5, 7)),
])
def test_time_parser_preserves_seconds(text, expected):
    assert parse_time(text) == expected


@pytest.mark.parametrize("text", [
    "24:00", "18:60", "18:59:60", "12", "12:1", "12:00:1", "-1:00", "",
    "12:00:00.1", "12:00Z", "12:00+09:00", "１２:００", None,
])
def test_time_parser_rejects_invalid_inputs(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_user_example_and_manual_break():
    start = datetime(2026, 9, 24, 12)
    end = datetime(2026, 9, 24, 18, 59)
    assert difference_seconds(start, end) == 25140
    assert interval_seconds(start, end) == 25140
    assert interval_seconds(start, end, 60) == 21540
    assert format_minutes(interval_seconds(start, end)) == "419분"
    assert format_duration(interval_seconds(start, end)) == "6시간 59분"


def test_exact_seconds_negative_difference_and_explicit_next_day():
    start = datetime(2026, 9, 24, 23, 59, 30)
    end = datetime(2026, 9, 25, 0, 0, 1)
    assert difference_seconds(start, end) == 31
    assert difference_seconds(end, start) == -31
    assert interval_seconds(start, end) == 31
    with pytest.raises(ValueError, match="종료가 시작보다"):
        interval_seconds(end, start)


@pytest.mark.parametrize("break_minutes", [-1, 2, .5, True])
def test_break_must_be_whole_nonnegative_minutes_within_interval(break_minutes):
    with pytest.raises(ValueError):
        interval_seconds(datetime(2026, 1, 1), datetime(2026, 1, 1, 0, 1, 30), break_minutes)


def test_zero_interval_and_break_equal_to_interval():
    start = datetime(2026, 1, 1)
    assert interval_seconds(start, start) == 0
    assert interval_seconds(start, datetime(2026, 1, 1, 0, 1), 1) == 0


@pytest.mark.parametrize("invalid", [
    datetime(2026, 1, 1, microsecond=1), datetime(2026, 1, 1, tzinfo=timezone.utc),
    date(2026, 1, 1), "2026-01-01",
])
def test_wall_clock_calculation_rejects_timezone_or_partial_seconds(invalid):
    with pytest.raises(ValueError):
        difference_seconds(invalid, datetime(2026, 1, 1))


@pytest.mark.parametrize("base,arguments,expected,adjusted", [
    (datetime(2026, 1, 31), {"months": 1}, datetime(2026, 2, 28), True),
    (datetime(2024, 1, 31), {"months": 1}, datetime(2024, 2, 29), True),
    (datetime(2024, 2, 29), {"years": 1}, datetime(2025, 2, 28), True),
    (datetime(2024, 2, 29), {"years": 1, "months": 1}, datetime(2025, 3, 29), False),
    (datetime(2026, 3, 31), {"months": 1, "sign": -1}, datetime(2026, 2, 28), True),
    (datetime(2026, 1, 31, 23, 59, 59), {"months": 1, "seconds": 1}, datetime(2026, 3, 1), True),
    (datetime(2026, 1, 31), {"months": 2}, datetime(2026, 3, 31), False),
    (datetime(2026, 1, 1), {"days": 1, "hours": 25, "minutes": 61, "seconds": 61}, datetime(2026, 1, 3, 2, 2, 1), False),
])
def test_calendar_add_moves_combined_months_once_before_fixed_time(base, arguments, expected, adjusted):
    assert add_calendar(base, **arguments) == CalendarResult(expected, adjusted)


@pytest.mark.parametrize("base,arguments", [
    (datetime(1, 1, 1), {"months": 1, "sign": -1}),
    (datetime(9999, 12, 31), {"months": 1}),
    (datetime(9999, 12, 31, 23, 59, 59), {"seconds": 1}),
    (datetime(1, 1, 1), {"seconds": 1, "sign": -1}),
    (datetime(2026, 1, 1), {"days": 10 ** 30}),
    (datetime(2026, 1, 1), {"months": -1}),
    (datetime(2026, 1, 1), {"minutes": 1.5}),
    (datetime(2026, 1, 1), {"sign": 0}),
    (datetime(2026, 1, 1), {"sign": True}),
])
def test_calendar_add_rejects_unsupported_input_or_date_overflow(base, arguments):
    with pytest.raises(ValueError):
        add_calendar(base, **arguments)


@pytest.mark.parametrize("start,end,expected", [
    (datetime(2026, 1, 31), datetime(2026, 2, 28), CalendarDelta(1, 0, 1, 0, 0, 0, 0)),
    (datetime(2026, 1, 31, 12), datetime(2026, 2, 28, 11), CalendarDelta(1, 0, 0, 27, 23, 0, 0)),
    (datetime(2024, 2, 29), datetime(2025, 3, 29, 1, 2, 3), CalendarDelta(1, 1, 1, 0, 1, 2, 3)),
    (datetime(2026, 3, 30), datetime(2026, 1, 31), CalendarDelta(-1, 0, 1, 30, 0, 0, 0)),
    (datetime(2026, 1, 1), datetime(2026, 1, 1), CalendarDelta(0, 0, 0, 0, 0, 0, 0)),
    (datetime(1, 1, 1), datetime(9999, 12, 31, 23, 59, 59), CalendarDelta(1, 9998, 11, 30, 23, 59, 59)),
])
def test_calendar_difference_uses_maximum_combined_month_anchor(start, end, expected):
    assert calendar_difference(start, end) == expected


def test_workdays_do_not_double_subtract_holiday_weekends():
    # 2026-09-24~30: 추석 24·25·26일 중 26일은 토요일, 27일은 일요일.
    assert working_days(date(2026, 9, 24), date(2026, 9, 30)) == WorkdayResult(3, 7, 4)
    assert working_days(date(2026, 9, 24), date(2026, 9, 30), exclude_holidays=False) == WorkdayResult(5, 7, 2)
    assert working_days(date(2026, 9, 24), date(2026, 9, 30), excluded_weekdays=()) == WorkdayResult(4, 7, 3)


@pytest.mark.parametrize("include_start,include_end,expected", [
    (True, True, WorkdayResult(5, 5, 0)), (False, True, WorkdayResult(4, 4, 0)),
    (True, False, WorkdayResult(4, 4, 0)), (False, False, WorkdayResult(3, 3, 0)),
])
def test_workday_endpoint_choices(include_start, include_end, expected):
    assert working_days(date(2026, 9, 14), date(2026, 9, 18),
                        include_start=include_start, include_end=include_end) == expected


@pytest.mark.parametrize("include_start,include_end,expected", [
    (True, True, 1), (False, True, 0), (True, False, 0), (False, False, 0),
])
def test_workday_same_date_is_not_counted_twice(include_start, include_end, expected):
    assert working_days(date(2026, 9, 14), date(2026, 9, 14),
                        include_start=include_start, include_end=include_end) == WorkdayResult(expected, expected, 0)


def test_workdays_custom_weekdays_and_all_weekdays_excluded():
    assert working_days(date(2026, 9, 14), date(2026, 9, 20), excluded_weekdays={0, 2}) == WorkdayResult(5, 7, 2)
    assert working_days(date(2026, 9, 24), date(2026, 9, 30), excluded_weekdays=range(7)) == WorkdayResult(0, 7, 7)


@pytest.mark.parametrize("start,end", [
    (date(2024, 12, 31), date(2025, 1, 2)), (date(2027, 12, 31), date(2028, 1, 1)),
    (date(2040, 1, 1), date(2040, 1, 2)),
])
def test_missing_holiday_year_is_not_treated_as_zero_holidays(start, end):
    with pytest.raises(ValueError, match="2025–2027년"):
        working_days(start, end)
    assert working_days(start, end, exclude_holidays=False).total == (end - start).days + 1


def test_workdays_full_supported_date_range_without_holidays():
    # 그레고리력 독립 기준: 3,652,059일 = 521,722주 + 월~금 5일.
    assert working_days(date.min, date.max, exclude_holidays=False) == WorkdayResult(2608615, 3652059, 1043444)
    assert working_days(date.max, date.max, exclude_holidays=False, include_start=False) == WorkdayResult(0, 0, 0)
    assert working_days(date.min, date.min, exclude_holidays=False, include_end=False) == WorkdayResult(0, 0, 0)


@pytest.mark.parametrize("kwargs", [
    {"excluded_weekdays": {-1}}, {"excluded_weekdays": {7}}, {"excluded_weekdays": {True}},
    {"excluded_weekdays": None}, {"exclude_holidays": "yes"}, {"include_end": 1},
])
def test_workdays_reject_invalid_options(kwargs):
    with pytest.raises(ValueError):
        working_days(date(2026, 9, 14), date(2026, 9, 18), **kwargs)


def test_workdays_reject_reversed_dates_and_datetime():
    with pytest.raises(ValueError, match="종료 날짜"):
        working_days(date(2026, 9, 18), date(2026, 9, 14))
    with pytest.raises(ValueError):
        working_days(datetime(2026, 9, 14), date(2026, 9, 18))


def test_signed_duration_sum_preserves_seconds_and_zero():
    assert sum_durations([25170, -1800, 31]) == 23401
    assert sum_durations([30, -31]) == -1
    assert sum_durations(iter([])) == 0
    with pytest.raises(ValueError):
        sum_durations([60, 1.5])


@pytest.mark.parametrize("seconds,duration,minutes", [
    (0, "0초", "0분"), (30, "30초", "0분 30초"), (25170, "6시간 59분 30초", "419분 30초"),
    (-90, "-1분 30초", "-1분 30초"), (90061, "1일 1시간 1분 1초", "1,501분 1초"),
])
def test_duration_text_is_exact(seconds, duration, minutes):
    assert format_duration(seconds) == duration
    assert format_minutes(seconds) == minutes


@pytest.mark.parametrize("seconds,exact,floor,nearest,ceil", [
    (0, "0", "0", "0", "0"), (25140, "419", "419", "419", "419"),
    (25170, "419.5", "419", "420", "420"), (1, "0.016666666667", "0", "0", "1"),
    (59, "0.983333333333", "0", "1", "1"), (-1, "-0.016666666667", "-1", "0", "0"),
    (-90, "-1.5", "-2", "-2", "-1"), (-89, "-1.483333333333", "-2", "-1", "-1"),
])
def test_minute_copy_policies_are_explicit(seconds, exact, floor, nearest, ceil):
    assert minute_value(seconds) == exact
    assert minute_value(seconds, "floor") == floor
    assert minute_value(seconds, "nearest") == nearest
    assert minute_value(seconds, "ceil") == ceil


def test_minute_copy_rejects_unknown_policy():
    with pytest.raises(ValueError):
        minute_value(60, "unknown")


@pytest.mark.parametrize("function", [format_minutes, format_duration, minute_value])
@pytest.mark.parametrize("value", [1.5, True, "60"])
def test_duration_formatters_reject_non_integer_seconds(function, value):
    with pytest.raises(ValueError):
        function(value)
