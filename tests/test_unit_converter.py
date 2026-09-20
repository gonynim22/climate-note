"""공식 정의의 독립 기준값과 오류/정밀도 검증. 출처: docs/UNIT_CONVERSION.md."""
import math

import pytest

from unit_converter import CATEGORIES, CATEGORY_BY_ID, RecentHistory, convert, format_number, parse_number


# 각 단위 1의 기준 단위 값. 구현의 factor를 기대값으로 읽지 않는다.
# 기준표의 유효숫자에 맞춘 상대오차 5e-10; 정확 정의 대표값은 아래에서 별도 확인.
GOLDEN = {
    "len": ("m", [1e-9, 1e-6, .001, .01, 1, 1000, .0254, .3048, .9144, 1609.344,
                    1852, .303030303030303, 3927.272727272727, 9460730472580800]),
    "mass": ("kg", [.000001, .001, 1, 1000, .6, 3.75, .00375, .028349523125,
                       .45359237, 6.35029318, .0002]),
    "vol": ("l", [.001, 1, 1000, .001, 1.80390683696469, 18.0390683696469,
                    3.785411784, .946352946, .473176473, .0295735295625, 158.987294928]),
    "area": ("m2", [.0001, 1, 1e6, 3.305785123966942, 100, 10000, .09290304,
                       4046.8564224, 2589988.110336]),
    "temp": ("k", [274.15, 255.92777777777778, 1, .5555555555555556]),
    "speed": ("ms", [1, .277777777777778, .44704, .514444444444444, .3048]),
    "time": ("s", [.000001, .001, 1, 60, 3600, 86400, 604800, 2592000, 31536000]),
    "data": ("B", [.125, 1, 1000, 1e6, 1e9, 1e12, 1e15, 1024, 1048576, 1073741824]),
    "press": ("pa", [1, 100, 1000, 1e6, 100000, 101325, 133.322387415,
                        6894.757293168361, 98066.5]),
    "energy": ("j", [1, 1000, 4.184, 4184, 3600, 3600000, 1055.05585262,
                        1.602176634e-19, 41868000000]),
    "power": ("w", [.001, 1, 1000, 1e6, 1e9, 745.6998715822702, 735.49875, .293071070172222]),
    "angle": ("rad", [.0174532925199433, 1, .015707963267949, .000290888208665722,
                         .00000484813681109536, 6.283185307179586]),
    "force": ("n", [1, 1000, 9.80665, 4.4482216152605, .00001]),
    "freq": ("hz", [1, 1000, 1e6, 1e9, .0166666666666667]),
    "co2": ("kgco2", [.001, 1, 1000]),
    "pm": ("ugm3", [.001, 1, 1000, 1e6]),
    "rad": ("msv", [.000001, .001, 1, 1000, .01, 10]),
    "lux": ("lx", [1, 1000, 10.7639104167097, 10000]),
    "db": ("pa_", [.00002244036908603927, 1, .000001, .00002]),
    "cook": ("mlc", [200, 240, 15, 5, 1, 1000, 29.5735295625]),
    "fuel": ("l100", [1, 100, 235.2145833333333, 282.480936331822]),
}


@pytest.mark.parametrize("category", CATEGORIES, ids=lambda c: c.id)
def test_all_units_against_independent_reference_values(category):
    base, expected = GOLDEN[category.id]
    assert len(category.units) == len(expected)
    for unit, value in zip(category.units, expected):
        assert convert(category.id, unit.id, base, 1) == pytest.approx(value, rel=5e-10, abs=0), unit.id


@pytest.mark.parametrize("category", CATEGORIES, ids=lambda c: c.id)
def test_every_unit_pair_round_trip(category):
    for source in category.units:
        for target in category.units:
            result = convert(category.id, source.id, target.id, 123.456789)
            restored = convert(category.id, target.id, source.id, result)
            assert restored == pytest.approx(123.456789, rel=2e-12, abs=1e-11)


@pytest.mark.parametrize("cid,source,target,value,expected", [
    ("temp", "c", "f", -40, -40), ("temp", "c", "f", 100, 212),
    ("temp", "c", "k", -273.15, 0), ("temp", "f", "k", -459.67, 0),
    ("fuel", "kmpl", "l100", 20, 5), ("fuel", "mpgus", "l100", 30, 7.84048611111111),
    ("db", "db", "upa", 0, 20), ("db", "db", "ratio", 20, 10),
    ("db", "ratio", "db", 1, 0), ("db", "db", "upa", -20, 2),
    ("data", "GB", "GiB", 1, .9313225746154785), ("mass", "lb", "kg", 1, .45359237),
    ("len", "in", "cm", 1, 2.54), ("angle", "turn", "deg", 1, 360),
])
def test_defined_values_and_boundaries(cid, source, target, value, expected):
    assert convert(cid, source, target, value) == pytest.approx(expected, rel=2e-14, abs=1e-12)


@pytest.mark.parametrize("cid,source,target,value", [
    ("temp", "c", "f", -273.150000001), ("temp", "f", "k", -459.6701),
    ("temp", "k", "k", -1), ("fuel", "kmpl", "l100", 0), ("fuel", "l100", "l100", -1),
    ("db", "pa_", "db", 0), ("db", "ratio", "pa_", -1),
    ("len", "ly", "nm", 1e308), ("len", "nm", "ly", 1e-308),
    ("db", "db", "pa_", 1e6), ("db", "db", "pa_", -1e6),
    ("fuel", "kmpl", "l100", 1e-320), ("len", "cm", "m", math.inf),
    ("len", "m", "m", math.nan), ("shoe", "mm", "eu", 100), ("len", "kg", "m", 1),
])
def test_invalid_conversion_is_explicit(cid, source, target, value):
    with pytest.raises(ValueError):
        convert(cid, source, target, value)


@pytest.mark.parametrize("text,value", [("1,234.5", 1234.5), ("  -40 ", -40), ("1e6", 1e6),
    (".5", .5), ("1.", 1), ("0e9999", 0), ("1,000e-3", 1), ("-0", 0)])
def test_whole_number_parser(text, value):
    assert parse_number(text) == value


@pytest.mark.parametrize("text", ["12abc", "1,23", "1,000,00", "1 000", "NaN", "Infinity", "1e999",
    "1e-999", "١٢", "1+2", "1.2.3", "9"*97, "--1", "1,234.5,6"])
def test_invalid_number_is_not_partially_parsed(text):
    with pytest.raises(ValueError):
        parse_number(text)


@pytest.mark.parametrize("text", ["", " ", "-", "+", ".", "-.", "1e", "1e+", "1e-"])
def test_partial_input_is_preserved(text):
    assert parse_number(text) is None


@pytest.mark.parametrize("value,expected", [(0, "0"), (-0.0, "0"), (1234567, "1,234,570"),
    (1.234567e-8, "1.23457 ×10^-8"), (1e12, "1 ×10^12"), (.0001, "0.0001"),
    (999999.9, "1,000,000"), (-40.0, "-40"), (2.540000000000001, "2.54")])
def test_six_digit_display_only(value, expected):
    assert format_number(value) == expected


def test_repeated_swap_does_not_round_the_calculation_value():
    value = original = 123.456789012345
    for _ in range(100):
        value = float(repr(convert("len", "cm", "in", value)))
        value = float(repr(convert("len", "in", "cm", value)))
    assert value == pytest.approx(original, rel=2e-14)


def test_recents_use_identity_not_rounded_label_and_keep_twelve():
    history = RecentHistory()
    for value in range(15):
        history.add("len", "cm", "in", str(value))
    assert len(history.items) == 12
    assert history.items[-1].value == 3
    history.add("len", "cm", "in", "14.00")
    assert len(history.items) == 12
    assert history.items[0].text == "14.00"
    history.add("len", "cm", "in", "14.0000001")
    assert history.items[1].value == 14
    before = history.items.copy()
    with pytest.raises(ValueError):
        history.add("fuel", "kmpl", "l100", "0")
    history.add("len", "cm", "in", "-")
    assert history.items == before


def test_registry_has_only_the_approved_categories_and_complete_defaults():
    assert len(CATEGORIES) == 21
    assert sum(len(c.units) for c in CATEGORIES) == 147
    assert len(CATEGORY_BY_ID) == len(CATEGORIES)
    ids = {u.id for c in CATEGORIES for u in c.units}
    assert not ids.intersection({"shoe", "tree", "cig", "xray", "mach", "majigi", "spoon", "elec"})
    for category in CATEGORIES:
        assert len({u.id for u in category.units}) == len(category.units)
        assert all(category.unit(uid) for uid in category.defaults)
        assert all(u.factor > 0 for u in category.units)
