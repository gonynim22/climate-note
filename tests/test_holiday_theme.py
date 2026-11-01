import inspect
from datetime import date
import pytest
import holiday_theme as ht
from holidays import KOREAN_HOLIDAYS

VECTORS = [
    ("2026-12-21", None), ("2026-12-22", "christmas"), ("2026-12-26", None),
    ("2026-12-29", "newyear"), ("2027-01-02", None), ("2027-02-03", "seollal"),
    ("2027-02-09", "seollal"), ("2027-02-10", None), ("2027-05-02", "labor"),
    ("2027-05-04", "children"), ("2027-10-10", "hangul"), ("2027-12-26", "christmas"),
    ("2028-04-29", "labor"), ("2028-05-02", "buddha"), ("2028-05-03", "children"),
    ("2028-10-03", "chuseok"), ("2029-01-01", None),
]

@pytest.mark.parametrize("day,expected", VECTORS)
def test_spec_vectors_against_real_data(day, expected):
    m = ht.resolve_holiday_theme(date.fromisoformat(day), KOREAN_HOLIDAYS)
    assert (m.theme.key if m else None) == expected

def test_lead_days_and_in_holiday_flag():
    table = {"2030-03-01": "삼일절"}
    assert ht.resolve_holiday_theme(date(2030, 2, 25), table) is None
    lead = ht.resolve_holiday_theme(date(2030, 2, 26), table)
    assert lead.theme.key == "samil" and lead.in_holiday is False
    day = ht.resolve_holiday_theme(date(2030, 3, 1), table)
    assert day.in_holiday is True and day.dates == (date(2030, 3, 1),)
    assert ht.resolve_holiday_theme(date(2030, 3, 2), table) is None

def test_substitute_with_name_joins_group_and_fills_gap():
    table = {"2030-10-09": "한글날", "2030-10-11": "대체공휴일(한글날)"}
    m = ht.resolve_holiday_theme(date(2030, 10, 10), table)
    assert m.theme.key == "hangul" and m.in_holiday is True
    assert (m.first_day, m.last_day) == (date(2030, 10, 9), date(2030, 10, 11))
    assert m.dates == (date(2030, 10, 9), date(2030, 10, 11))

def test_unnamed_substitute_is_ignored():
    table = {"2030-03-01": "삼일절", "2030-03-02": "대체공휴일"}
    assert ht.resolve_holiday_theme(date(2030, 3, 2), table) is None

def test_combined_name_same_day_uses_key_order():
    table = {"2030-05-05": "어린이날·부처님오신날"}
    assert ht.resolve_holiday_theme(date(2030, 5, 5), table).theme.key == "children"

def test_combined_name_inside_longer_holiday_prefers_longer():
    table = {"2030-10-02": "추석", "2030-10-03": "개천절·추석", "2030-10-04": "추석"}
    assert ht.resolve_holiday_theme(date(2030, 10, 3), table).theme.key == "chuseok"

def test_theme_table_matches_spec():
    assert ht.THEME_KEYS == ("newyear", "seollal", "samil", "labor", "children", "buddha",
                             "memorial", "constitution", "liberation", "chuseok",
                             "gaecheon", "hangul", "christmas")
    assert set(ht.THEMES) == set(ht.THEME_KEYS)
    assert ht.THEMES["christmas"].header == "#1D4A3A"
    assert ht.THEMES["newyear"].today == "#B9502C"
    assert ht.THEMES["chuseok"].band_icon == "#FFFFFF"
    assert ht.THEMES["memorial"].greeting == "희생하신 분들을 기억합니다"
    assert [k for k, t in ht.THEMES.items() if not t.motion] == ["memorial"]
    assert len(ht.THEMES["seollal"].band_stripes) == 5

def test_module_has_no_qt_or_db_imports():
    src = inspect.getsource(ht)
    assert "PySide6" not in src and "import database" not in src

def test_nearer_first_day_wins_when_none_in_progress():
    # 키 순서(samil < labor)와 반대로, 첫날이 더 가까운 노동절이 이겨야 한다.
    table = {"2030-03-01": "노동절", "2030-03-02": "삼일절"}
    assert ht.resolve_holiday_theme(date(2030, 2, 27), table).theme.key == "labor"

def test_in_progress_group_beats_nearer_upcoming_group():
    table = {"2030-03-01": "노동절", "2030-03-02": "노동절", "2030-03-04": "삼일절"}
    assert ht.resolve_holiday_theme(date(2030, 3, 2), table).theme.key == "labor"

def test_gap_over_seven_days_splits_group():
    table = {"2030-03-01": "삼일절", "2030-03-08": "삼일절", "2030-03-09": "삼일절"}
    first = ht.resolve_holiday_theme(date(2030, 3, 1), table)
    assert first.dates == (date(2030, 3, 1), date(2030, 3, 8), date(2030, 3, 9))
    table = {"2030-03-01": "삼일절", "2030-03-09": "삼일절"}
    assert ht.resolve_holiday_theme(date(2030, 3, 1), table).dates == (date(2030, 3, 1),)
    assert ht.resolve_holiday_theme(date(2030, 3, 9), table).dates == (date(2030, 3, 9),)

def test_current_match_uses_real_data_and_given_day():
    m = ht.current_match(date(2026, 12, 25))
    assert m.theme.key == "christmas" and m.in_holiday is True
    assert ht.current_match(date(2026, 12, 26)) is None

@pytest.mark.parametrize("key", ht.THEME_KEYS)
def test_theme_colors_are_hex_and_white_text_is_readable(key):
    theme = ht.THEMES[key]
    for value in (theme.header, theme.today, theme.tint, theme.cover, theme.accent,
                  theme.focus_end, theme.band, theme.band_icon, *theme.band_stripes):
        assert len(value) == 7 and value[0] == "#" and int(value[1:], 16) >= 0

    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    # 머리줄·오늘 칸·D-Day 커버는 흰 글자 기준 4.5:1 이상(설계 문서 '색')
    for value in (theme.header, theme.today, theme.cover):
        assert 1.05 / (luminance(value) + 0.05) >= 4.5, (key, value)
