"""v4.1 일정 시각·기간·반복·알림 규칙(순수 함수) 회귀. 기대값은 손으로 쓴 리터럴이다."""
from datetime import date, timedelta

import pytest

import schedule_rules as rules
from schedule_rules import ScheduleOptions

START = "2026-10-15"  # 목요일


@pytest.mark.parametrize("end,expected", [
    ("2026-10-17", "~ 17일(토) · 3일"),
    ("2026-11-02", "~ 11월 2일(월) · 19일"),
    ("2027-01-03", "~ 2027년 1월 3일(일) · 81일"),
    ("2027-10-14", "~ 2027년 10월 14일(목) · 365일"),
])
def test_period_short_caption(end, expected):
    assert rules.period_short_caption(START, end) == expected


@pytest.mark.parametrize("options,expected", [
    (ScheduleOptions(start_time="15:00", alarm_before=0), "정시, 15:00에 알림"),
    (ScheduleOptions(start_time="15:00", alarm_before=10), "10분 전, 14:50에 알림"),
    (ScheduleOptions(start_time="15:00", alarm_before=30), "30분 전, 14:30에 알림"),
    (ScheduleOptions(start_time="15:00", alarm_before=60), "1시간 전, 14:00에 알림"),
    (ScheduleOptions(start_time="15:00", alarm_before=1440), "하루 전, 10월 14일(수) 15:00에 알림"),
    (ScheduleOptions(start_time="00:05", alarm_before=10), "10분 전, 10월 14일(수) 23:55에 알림"),
    (ScheduleOptions(alarm_before=0), ""),
    (ScheduleOptions(alarm_before=1440), ""),
    (ScheduleOptions(start_time="15:00"), ""),
    (ScheduleOptions(), ""),
])
def test_alarm_caption(options, expected):
    assert rules.alarm_caption(date(2026, 10, 15), options) == expected


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


OCT_WEEKS = [
    ["", "", "", "", "2026-10-01", "2026-10-02", "2026-10-03"],
    ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10"],
    ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"],
]


def test_week_segments_split_at_week_and_month_edges_and_assign_lanes():
    spans = {
        7: ("2026-09-29", "2026-10-02"),   # 지난달에서 이어짐 → 왼쪽 끝이 각짐
        8: ("2026-10-08", "2026-10-12"),   # 주를 넘김 → 두 조각
        9: ("2026-10-09", "2026-10-10"),   # 8과 겹침 → 둘째 차선
    }
    assert rules.week_segments(OCT_WEEKS, spans) == [
        rules.SpanSegment(7, 0, 4, 5, False, True, 0),
        rules.SpanSegment(8, 1, 4, 6, True, False, 0),
        rules.SpanSegment(9, 1, 5, 6, True, True, 1),
        rules.SpanSegment(8, 2, 0, 1, False, True, 0),
    ]


def test_lanes_put_longer_span_first_when_starting_together():
    spans = {1: ("2026-10-11", "2026-10-13"), 2: ("2026-10-11", "2026-10-16")}
    segments = rules.week_segments(OCT_WEEKS, spans)
    assert [(s.key, s.lane) for s in segments] == [(2, 0), (1, 1)]


def test_korean_captions_and_pills():
    assert rules.repeat_caption("2026-10-15", "weekly") == "매주 목요일"
    assert rules.repeat_caption("2026-10-31", "monthly") == "매월 31일 (없는 달은 마지막 날)"
    assert rules.repeat_caption("2026-10-31", "monthly", note=False) == "매월 31일"
    assert rules.repeat_caption("2026-10-15", "monthly") == "매월 15일"
    assert rules.repeat_caption("2028-02-29", "yearly") == "매년 2월 29일 (평년은 2월 28일)"
    assert rules.repeat_caption("2026-10-15", "weekdays") == "평일(월~금)"
    assert rules.repeat_caption("2026-10-15", "daily") == "매일"
    assert rules.repeat_pill("2026-10-15", ScheduleOptions(repeat_rule="weekly", repeat_until="2026-12-31")) == (
        "매주 목 · ~12.31")
    assert rules.repeat_pill("2026-10-15", ScheduleOptions(repeat_rule="yearly")) == "매년 10.15"
    assert rules.time_pill(ScheduleOptions(start_time="15:00", alarm_before=10)) == "15:00 · 10분 전"
    assert rules.time_pill(ScheduleOptions(start_time="15:00")) == "15:00"
    assert rules.alarm_label(ScheduleOptions(alarm_before=0), short=True) == "당일 9시"
    assert rules.alarm_label(ScheduleOptions(alarm_before=1440)) == "하루 전 오전 9시"
    assert rules.alarm_label(ScheduleOptions(start_time="10:00", alarm_before=60)) == "1시간 전"
    assert rules.alarm_label(ScheduleOptions()) == ""
    assert rules.span_pill("2026-10-21", ScheduleOptions(end_date="2026-10-23")) == "~10.23 · 3일"
    assert rules.range_text("2026-10-21", "2026-10-23") == "10.21~10.23"
    assert rules.range_text("2026-12-30", "2027-01-02") == "26.12.30~27.01.02"
    assert rules.korean_date(D("2026-10-15")) == "10월 15일 (목)"
    assert rules.period_caption("2026-10-21", "2026-10-23") == "10월 21일(수) ~ 23일(금) · 3일"
    assert rules.period_caption("2026-10-30", "2026-11-02") == "10월 30일(금) ~ 11월 2일(월) · 4일"


def test_options_summary_and_search_suffix():
    weekly = ScheduleOptions(start_time="10:00", repeat_rule="weekly", alarm_before=10)
    assert rules.options_summary("2026-10-05", weekly) == "10:00 · 10분 전 · 매주 월요일"
    period = ScheduleOptions(end_date="2026-10-23", alarm_before=0)
    assert rules.options_summary("2026-10-21", period) == "알림 당일 오전 9시 · 10.21~10.23"
    until = ScheduleOptions(repeat_rule="daily", repeat_until="2026-12-31")
    assert rules.options_summary("2026-10-15", until) == "매일 · 12월 31일까지"
    assert rules.options_summary("2026-10-15", ScheduleOptions()) == ""
    assert rules.search_suffix("2026-10-05", ScheduleOptions(repeat_rule="weekly")) == " (매주 월요일 반복)"
    assert rules.search_suffix("2026-10-31", ScheduleOptions(repeat_rule="monthly")) == " (매월 31일 반복)"
    assert rules.search_suffix("2026-10-21", ScheduleOptions(end_date="2026-10-23")) == " (~10.23)"
    assert rules.search_suffix("2026-10-21", ScheduleOptions()) == ""
    assert rules.search_suffix("2026-7-1", ScheduleOptions(repeat_rule="weekly")) == ""


def test_alarm_subtitle():
    now = datetime(2026, 10, 15, 14, 50)
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), now) == "10분 뒤 시작 · 10월 15일 (목)"
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 15, 0)) == "지금 시작 · 10월 15일 (목)"
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 15, 3)) == (
        "15:00에 시작함 · 10월 15일 (목)")
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 13, 0)) == "15:00 시작 · 10월 15일 (목)"
    # '1시간 전' 알림이 울리는 때(정확히 60분 전, 몇 초 늦어도)는 '1시간 뒤 시작'(§4.9). 61분부터는 시각을 쓴다.
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 14, 0)) == (
        "1시간 뒤 시작 · 10월 15일 (목)")
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 14, 0, 1)) == (
        "1시간 뒤 시작 · 10월 15일 (목)")
    assert rules.alarm_subtitle("15:00", D("2026-10-15"), datetime(2026, 10, 15, 13, 59)) == "15:00 시작 · 10월 15일 (목)"
    assert rules.alarm_subtitle("00:30", D("2026-10-16"), datetime(2026, 10, 15, 23, 30)) == (
        "1시간 뒤 시작 · 10월 16일 (금)")
    assert rules.alarm_subtitle("09:00", D("2026-10-16"), now) == "내일 09:00 시작 · 10월 16일 (금)"
    assert rules.alarm_subtitle("", D("2026-10-15"), now) == "오늘 하루 종일 · 10월 15일 (목)"
    assert rules.alarm_subtitle("", D("2026-10-16"), now) == "내일 하루 종일 · 10월 16일 (금)"
    assert rules.alarm_subtitle("", D("2026-10-14"), now) == "하루 종일 · 10월 14일 (수)"


def test_until_caption_detail_lines_and_unknown_rule_suffix():
    assert rules.until_caption("2026-12-31") == "12월 31일(목)까지"
    weekly = ScheduleOptions(start_time="10:00", repeat_rule="weekly", repeat_until="2026-12-28", alarm_before=10)
    assert rules.detail_lines("2026-10-05", weekly) == [
        "시작: 10:00", "매주 월요일 반복 · 끝: 12월 28일(월)까지", "알림: 10분 전"]
    period = ScheduleOptions(end_date="2026-10-23", alarm_before=0)
    assert rules.detail_lines("2026-10-21", period) == ["기간: 10.21~10.23 · 3일", "알림: 당일 오전 9시"]
    assert rules.detail_lines("2026-10-21", ScheduleOptions(repeat_rule="daily")) == ["매일 반복 · 끝: 계속"]
    assert rules.detail_lines("2026-10-21", ScheduleOptions()) == []
    assert rules.search_suffix("2026-10-05", ScheduleOptions(repeat_rule="biweekly")) == ""


def stored_row(**overrides):
    """DB 행처럼 읽히는 dict. 기본은 규칙에 맞는 '하루 종일·반복 없음' 행이다."""
    row = {"date": "2026-10-15", "start_time": "", "end_date": "", "repeat_rule": "",
           "repeat_until": "", "repeat_skip": "", "alarm_before": None}
    row.update(overrides)
    return row


def test_from_row_drops_alarm_that_does_not_fit_the_start_time_mode():
    """시각 방식에 맞지 않는 저장 알림은 없는 것으로 읽어, 표시 함수가 KeyError를 내지 않는다."""
    broken_time = ScheduleOptions.from_row(stored_row(start_time="9시", alarm_before=10))
    assert broken_time == ScheduleOptions()
    off_list = ScheduleOptions.from_row(stored_row(start_time="09:00", alarm_before=15))
    assert off_list == ScheduleOptions(start_time="09:00")
    assert rules.time_pill(off_list) == "09:00"
    assert rules.options_summary(START, off_list) == "09:00"
    assert rules.detail_lines(START, off_list) == ["시작: 09:00"]
    # 하루 종일에는 0·1440만 허용된다(10·30·60은 시각 일정 전용).
    assert ScheduleOptions.from_row(stored_row(alarm_before=30)) == ScheduleOptions()
    # 규칙에 맞는 값은 그대로 읽는다.
    assert ScheduleOptions.from_row(stored_row(start_time="09:00", alarm_before=30)) == ScheduleOptions(
        start_time="09:00", alarm_before=30)
    assert ScheduleOptions.from_row(stored_row(alarm_before=1440)) == ScheduleOptions(alarm_before=1440)


def test_from_row_blanks_malformed_dates_and_end_date_not_after_the_row_date():
    """깨진 날짜 저장값은 읽을 때 걸러, 펼치기가 ValueError를 내거나 일정이 사라지지 않게 한다."""
    options = ScheduleOptions.from_row(stored_row(
        end_date="2026/10/17", repeat_rule="daily", repeat_until="garbage",
        repeat_skip="2026-10-20,x,2026-13-01,2026-10-22"))
    assert options == ScheduleOptions(repeat_rule="daily", repeat_skip=("2026-10-20", "2026-10-22"))
    assert days("2026-10-15", options, "2026-10-15", "2026-10-23") == [
        "2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19", "2026-10-21", "2026-10-23"]
    # 줄의 날짜보다 앞서거나 같은 끝 날짜는 버린다(없으면 일정이 통째로 안 보인다).
    assert ScheduleOptions.from_row(stored_row(end_date="2026-10-15")).end_date == ""
    assert ScheduleOptions.from_row(stored_row(end_date="2026-10-14")).end_date == ""
    assert ScheduleOptions.from_row(stored_row(end_date="2026-10-17")).end_date == "2026-10-17"
    # 줄의 날짜 자체가 깨졌으면 비교하지 않고, 형식이 맞는 끝 날짜는 둔다.
    assert ScheduleOptions.from_row(stored_row(date="2026-7-1", end_date="2026-10-17")).end_date == "2026-10-17"
    # 'date' 열이 없는 행(dict)도 읽는다.
    plain = stored_row(end_date="2026-10-17")
    del plain["date"]
    assert ScheduleOptions.from_row(plain).end_date == "2026-10-17"


def test_from_row_reads_sqlite_rows_with_the_same_rules():
    import sqlite3
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT '2026-10-15' AS date, '14:00' AS start_time, '2026-10-12' AS end_date, '' AS repeat_rule, "
            "'' AS repeat_until, '' AS repeat_skip, 15 AS alarm_before").fetchone()
    assert ScheduleOptions.from_row(row) == ScheduleOptions(start_time="14:00")


def test_format_checks_reject_a_trailing_newline():
    """정규식 $는 끝의 줄바꿈을 통과시키므로 전체 일치(fullmatch)로 검사한다."""
    with pytest.raises(ValueError, match="시작 시각"):
        rules.validate_options(START, ScheduleOptions(start_time="09:30\n"))
    with pytest.raises(ValueError, match="날짜"):
        rules.parse_date("2026-10-15\n")
    with pytest.raises(ValueError, match="날짜"):
        rules.validate_options("2026-10-15\n", ScheduleOptions())
    with pytest.raises(ValueError, match="날짜"):
        rules.validate_options(START, ScheduleOptions(end_date="2026-10-17\n"))
