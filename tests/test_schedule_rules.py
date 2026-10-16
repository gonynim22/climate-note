"""v4.1 일정 시각·기간·반복·알림 규칙(순수 함수) 회귀. 기대값은 손으로 쓴 리터럴이다."""
from datetime import date, timedelta

import pytest

import schedule_rules as rules
from schedule_rules import ScheduleOptions

START = "2026-10-15"  # 목요일


@pytest.mark.parametrize("text,expected", [
    ("9", "09:00"), ("09", "09:00"), ("14", "14:00"), ("930", "09:30"),
    ("0930", "09:30"), ("1430", "14:30"), ("14:30", "14:30"), (" 7:05 ", "07:05"),
    ("0", "00:00"), ("2359", "23:59"),
])
def test_parse_time_input_accepts_short_forms(text, expected):
    assert rules.parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["", "24", "2400", "1260", "9:5", "14:3", "abc", "12345", "-1", "１４３０"])
def test_parse_time_input_rejects_invalid(text):
    with pytest.raises(ValueError):
        rules.parse_time_input(text)


def test_default_options_mean_all_day_single_day_no_repeat_no_alarm():
    options = ScheduleOptions()
    assert options.is_default
    assert options.to_db_values() == ("", "", "", "", "", None)


def test_from_row_reads_db_values_and_tolerates_bad_stored_values():
    row = {"start_time": "14:00", "end_date": "", "repeat_rule": "weekly",
           "repeat_until": "2026-12-31", "repeat_skip": "2026-10-22,2026-10-29",
           "alarm_before": 10}
    assert ScheduleOptions.from_row(row) == ScheduleOptions(
        start_time="14:00", repeat_rule="weekly", repeat_until="2026-12-31",
        repeat_skip=("2026-10-22", "2026-10-29"), alarm_before=10)
    weird = {"start_time": "9시", "end_date": None, "repeat_rule": "biweekly",
             "repeat_until": None, "repeat_skip": None, "alarm_before": "10"}
    assert ScheduleOptions.from_row(weird) == ScheduleOptions()


@pytest.mark.parametrize("options", [
    ScheduleOptions(),
    ScheduleOptions(start_time="09:30"),
    ScheduleOptions(start_time="09:30", alarm_before=10),
    ScheduleOptions(alarm_before=0),
    ScheduleOptions(alarm_before=1440),
    ScheduleOptions(end_date="2026-10-17"),
    ScheduleOptions(end_date="2027-10-15"),
    ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-15"),
    ScheduleOptions(repeat_rule="monthly", repeat_skip=("2026-11-15",)),
])
def test_validate_options_accepts_valid(options):
    assert rules.validate_options(START, options) == options


@pytest.mark.parametrize("options,message", [
    (ScheduleOptions(start_time="9:30"), "시작 시각"),
    (ScheduleOptions(start_time="24:00"), "시작 시각"),
    (ScheduleOptions(end_date="2026-10-15"), "기간"),
    (ScheduleOptions(end_date="2026-10-14"), "기간"),
    (ScheduleOptions(end_date="2027-10-16"), "기간"),
    (ScheduleOptions(end_date="2026/10/17"), "날짜"),
    (ScheduleOptions(repeat_rule="biweekly"), "반복"),
    (ScheduleOptions(repeat_rule="weekly", end_date="2026-10-16"), "여러 날"),
    (ScheduleOptions(repeat_until="2026-12-31"), "반복이 아닌"),
    (ScheduleOptions(repeat_skip=("2026-10-22",)), "반복이 아닌"),
    (ScheduleOptions(repeat_rule="daily", repeat_until="2026-10-14"), "반복 끝"),
    (ScheduleOptions(repeat_rule="daily", repeat_skip=("2026-10-14",)), "건너뛴 날"),
    (ScheduleOptions(alarm_before=10), "알림"),
    (ScheduleOptions(start_time="09:00", alarm_before=15), "알림"),
    (ScheduleOptions(start_time="09:00", alarm_before=True), "알림"),
    (ScheduleOptions(start_time="09:00", alarm_before=10.0), "알림"),
    (ScheduleOptions(start_time=None), "형식"),
])
def test_validate_options_rejects_invalid(options, message):
    with pytest.raises(ValueError, match=message):
        rules.validate_options(START, options)


def test_validate_options_sorts_and_dedups_skips_and_caps_count():
    options = ScheduleOptions(repeat_rule="daily", repeat_skip=("2026-10-20", "2026-10-16", "2026-10-20"))
    assert rules.validate_options(START, options).repeat_skip == ("2026-10-16", "2026-10-20")
    many = tuple((date(2027, 1, 1) + timedelta(days=i)).isoformat() for i in range(501))
    with pytest.raises(ValueError, match="건너뛴 날"):
        rules.validate_options(START, ScheduleOptions(repeat_rule="daily", repeat_skip=many))


def test_validate_options_rejects_bad_start_date():
    with pytest.raises(ValueError, match="날짜"):
        rules.validate_options("2026-7-1", ScheduleOptions(start_time="09:00"))


from datetime import datetime

D = date.fromisoformat


def days(start, options, first, last):
    return [d.isoformat() for d in rules.occurrence_dates(start, options, D(first), D(last))]


def test_single_day_occurs_only_on_its_date():
    assert days("2026-10-15", ScheduleOptions(), "2026-10-01", "2026-10-31") == ["2026-10-15"]
    assert days("2026-10-15", ScheduleOptions(), "2026-10-16", "2026-10-31") == []


def test_period_covers_each_day_inside_the_range():
    options = ScheduleOptions(end_date="2026-11-02")
    assert days("2026-10-30", options, "2026-10-01", "2026-10-31") == ["2026-10-30", "2026-10-31"]
    assert days("2026-10-30", options, "2026-11-01", "2026-11-30") == ["2026-11-01", "2026-11-02"]


def test_daily_and_weekdays():
    assert days("2026-10-15", ScheduleOptions(repeat_rule="daily"), "2026-10-13", "2026-10-18") == [
        "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18"]
    # 2026-10-17은 토요일: 평일 반복은 시작일이 주말이면 그 날을 건너뛴다.
    assert days("2026-10-17", ScheduleOptions(repeat_rule="weekdays"), "2026-10-17", "2026-10-23") == [
        "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]


def test_weekly_keeps_the_start_weekday():
    assert days("2026-10-05", ScheduleOptions(repeat_rule="weekly"), "2026-10-01", "2026-10-31") == [
        "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]


def test_monthly_on_31_uses_the_last_day_of_short_months():
    assert days("2026-01-31", ScheduleOptions(repeat_rule="monthly"), "2026-01-01", "2026-05-31") == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]


def test_yearly_leap_day_falls_back_to_feb_28():
    assert days("2024-02-29", ScheduleOptions(repeat_rule="yearly"), "2024-01-01", "2028-12-31") == [
        "2024-02-29", "2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]


def test_until_is_inclusive_and_skips_are_removed():
    options = ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-26", repeat_skip=("2026-10-12",))
    assert days("2026-10-05", options, "2026-10-01", "2026-12-31") == ["2026-10-05", "2026-10-19", "2026-10-26"]


def test_nothing_before_the_start_date_and_empty_range():
    assert days("2026-10-15", ScheduleOptions(repeat_rule="daily"), "2026-10-01", "2026-10-14") == []
    assert days("2026-10-15", ScheduleOptions(repeat_rule="daily"), "2026-10-20", "2026-10-19") == []


def test_occurs_on():
    options = ScheduleOptions(repeat_rule="weekly")
    assert rules.occurs_on("2026-10-05", options, D("2026-10-19"))
    assert not rules.occurs_on("2026-10-05", options, D("2026-10-20"))


def test_add_months_clamps_to_month_end():
    assert rules.add_months(D("2026-01-31"), 1) == D("2026-02-28")
    assert rules.add_months(D("2026-12-15"), 1) == D("2027-01-15")
    assert rules.add_months(D("2026-03-31"), -1) == D("2026-02-28")


def test_occurrence_sort_key_puts_all_day_first_then_time():
    items = [(True, "16:00", 3), (False, "", 5), (True, "09:00", 9), (False, "", 2), (True, "09:00", 4)]
    ordered = sorted(items, key=lambda item: rules.occurrence_sort_key(*item))
    assert ordered == [(False, "", 2), (False, "", 5), (True, "09:00", 4), (True, "09:00", 9), (True, "16:00", 3)]


def test_alarm_times_for_timed_all_day_period_and_repeat():
    after, until = datetime(2026, 10, 14, 0, 0), datetime(2026, 10, 16, 23, 59)
    timed = ScheduleOptions(start_time="15:00", alarm_before=10)
    assert rules.alarm_times("2026-10-15", timed, after, until) == [
        (D("2026-10-15"), datetime(2026, 10, 15, 14, 50))]
    eve = ScheduleOptions(alarm_before=1440)
    assert rules.alarm_times("2026-10-16", eve, after, until) == [
        (D("2026-10-16"), datetime(2026, 10, 15, 9, 0))]
    period = ScheduleOptions(end_date="2026-10-17", alarm_before=0)
    assert rules.alarm_times("2026-10-15", period, after, until) == [
        (D("2026-10-15"), datetime(2026, 10, 15, 9, 0))]
    daily = ScheduleOptions(start_time="10:00", repeat_rule="daily", repeat_skip=("2026-10-15",), alarm_before=0)
    assert rules.alarm_times("2026-10-01", daily, after, until) == [
        (D("2026-10-14"), datetime(2026, 10, 14, 10, 0)),
        (D("2026-10-16"), datetime(2026, 10, 16, 10, 0))]


def test_alarm_window_is_exclusive_after_inclusive_until():
    options = ScheduleOptions(start_time="15:00", alarm_before=0)
    due = datetime(2026, 10, 15, 15, 0)
    assert rules.alarm_times("2026-10-15", options, due, due.replace(hour=16)) == []
    assert rules.alarm_times("2026-10-15", options, due.replace(hour=14), due) == [(D("2026-10-15"), due)]
    assert rules.alarm_times("2026-10-15", ScheduleOptions(start_time="15:00"), due.replace(hour=0), due) == []


def test_alarm_item_key():
    item = rules.AlarmItem(7, "2026-10-15", datetime(2026, 10, 15, 14, 50), "회의", "#4CC9F0", "15:00")
    assert item.key == (7, "2026-10-15", datetime(2026, 10, 15, 14, 50))
    assert item.decryption_failed is False


def test_with_start_time_keeps_only_alarms_valid_in_both_modes():
    assert rules.with_start_time(ScheduleOptions(start_time="09:00", alarm_before=10), "").alarm_before is None
    assert rules.with_start_time(ScheduleOptions(start_time="09:00", alarm_before=1440), "").alarm_before == 1440
    assert rules.with_start_time(ScheduleOptions(alarm_before=0), "13:00") == ScheduleOptions(
        start_time="13:00", alarm_before=0)
    # 시각만 바꾸면(시각→시각) 알림을 그대로 둔다.
    assert rules.with_start_time(ScheduleOptions(start_time="09:00", alarm_before=10), "10:30") == (
        ScheduleOptions(start_time="10:30", alarm_before=10))


def test_with_repeat_clears_or_resets_dependent_fields():
    base = ScheduleOptions(repeat_rule="weekly", repeat_until="2026-12-31", repeat_skip=("2026-10-22",))
    assert rules.with_repeat(base, "2026-10-15", "") == ScheduleOptions()
    assert rules.with_repeat(base, "2026-10-15", "monthly") == ScheduleOptions(
        repeat_rule="monthly", repeat_until="2026-12-31")
    assert rules.with_repeat(base, "2026-10-15", "weekly") is base
    assert rules.with_repeat(ScheduleOptions(end_date="2026-10-17"), "2026-10-15", "daily") == ScheduleOptions(
        repeat_rule="daily")


def test_clear_part():
    full = ScheduleOptions(start_time="09:00", alarm_before=10)
    assert rules.clear_part(full, START, "time") == ScheduleOptions()
    assert rules.clear_part(full, START, "alarm") == ScheduleOptions(start_time="09:00")
    assert rules.clear_part(ScheduleOptions(end_date="2026-10-17"), START, "period") == ScheduleOptions()
    assert rules.clear_part(ScheduleOptions(repeat_rule="daily", repeat_until="2026-11-01"), START, "repeat") == (
        ScheduleOptions())
    with pytest.raises(ValueError):
        rules.clear_part(full, START, "colour")


def test_rebase_options_keeps_period_length_and_drops_stale_until():
    assert rules.rebase_options(ScheduleOptions(end_date="2026-10-17"), START, "2026-10-20").end_date == "2026-10-22"
    repeat = ScheduleOptions(repeat_rule="weekly", repeat_until="2026-10-18", repeat_skip=("2026-10-22",))
    assert rules.rebase_options(repeat, START, "2026-10-25") == ScheduleOptions(repeat_rule="weekly")
    assert rules.rebase_options(repeat, START, "2026-10-16") == ScheduleOptions(
        repeat_rule="weekly", repeat_until="2026-10-18")
    assert rules.rebase_options(repeat, START, START) is repeat
