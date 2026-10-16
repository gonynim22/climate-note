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
