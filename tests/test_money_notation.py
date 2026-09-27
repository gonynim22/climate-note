"""금액·숫자 표기 순수 계산. 규정 예시·경계·독립 참조 구현 대조."""
from decimal import Decimal
import random

import pytest

from money_notation import (
    LIMIT, NotationError, Reading, official_amount, official_hangul, group_notation,
    parse_decimal, parse_integer, read_number, reading_hangul, round_half_up,
)

FORMAT = "숫자와 세 자리 쉼표만 입력할 수 있습니다."
REF_DIGITS = "영일이삼사오육칠팔구"
REF_GROUPS = ("조", "억", "만", "")
REF_PLACES = ("천", "백", "십", "")


def reference_official(n):
    """16자리로 채운 문자열을 앞에서부터 읽는 별도 구현."""
    text = str(n).rjust(16, "0")
    out = []
    for group in range(4):
        chunk = text[group * 4:group * 4 + 4]
        if chunk == "0000":
            continue
        for offset, char in enumerate(chunk):
            if char != "0":
                out.append(REF_DIGITS[int(char)] + REF_PLACES[offset])
        out.append(REF_GROUPS[group])
    return "".join(out)


def samples():
    rng = random.Random(20260927)
    values = [rng.randrange(1, 10 ** rng.randint(1, 16)) for _ in range(20000)]
    for power in range(17):
        values += [10 ** power, 10 ** power - 1, 10 ** power + 1]
    return [v for v in values if 1 <= v < LIMIT]


def test_regulation_example():
    amount = official_amount(113560)
    assert amount.digits == "113,560"
    assert amount.hangul == "일십일만삼천오백육십"
    assert amount.text == "금113,560원(금일십일만삼천오백육십원)"


@pytest.mark.parametrize("value,expected", [
    (1, "일"), (10, "일십"), (11, "일십일"), (100, "일백"), (1010, "일천일십"),
    (10000, "일만"), (10001, "일만일"), (110000, "일십일만"), (10 ** 8, "일억"),
    (10 ** 8 + 1, "일억일"), (10 ** 12, "일조"), (2 * 10 ** 12, "이조"),
    (LIMIT - 1, "구천구백구십구조구천구백구십구억구천구백구십구만구천구백구십구"),
])
def test_official_hangul_boundaries(value, expected):
    assert official_hangul(value) == expected


def test_official_hangul_matches_reference_for_random_and_boundary_values():
    for value in samples():
        assert official_hangul(value) == reference_official(value), value


@pytest.mark.parametrize("value", [0, -1, LIMIT, LIMIT * 10])
def test_official_amount_rejects_out_of_range(value):
    with pytest.raises(NotationError, match="금액은 1원 이상 1경 미만이어야 합니다."):
        official_amount(value)


@pytest.mark.parametrize("text,expected", [
    ("113560", 113560), ("113,560", 113560), (" 1,234,567 ", 1234567),
    ("-5", -5), ("−5", -5), ("0", 0), ("99999999999999999999", 99999999999999999999),
])
def test_parse_integer_accepts_digits_and_valid_commas(text, expected):
    assert parse_integer(text) == expected


@pytest.mark.parametrize("text,message", [
    ("", "값을 입력하세요."), ("   ", "값을 입력하세요."),
    ("1,2,3", FORMAT), ("12 345", FORMAT), ("１２３", FORMAT), ("12a", FORMAT),
    (",123", FORMAT), ("123,", FORMAT), ("1,2345", FORMAT), ("+5", FORMAT),
    ("12.5", "정수만 입력할 수 있습니다."), ("1,234.5", "정수만 입력할 수 있습니다."),
])
def test_parse_integer_rejects_without_correction(text, message):
    with pytest.raises(NotationError, match=message):
        parse_integer(text)


@pytest.mark.parametrize("text,expected", [
    ("1,234.567", Decimal("1234.567")), ("-0.5", Decimal("-0.5")), ("12", Decimal("12")),
    ("0.000001", Decimal("0.000001")), ("−1,000.25", Decimal("-1000.25")),
])
def test_parse_decimal_is_exact(text, expected):
    assert parse_decimal(text) == expected


@pytest.mark.parametrize("text,message", [
    ("", "값을 입력하세요."), ("1.1234567", "소수는 6자리까지 입력할 수 있습니다."),
    ("1.", FORMAT), (".5", FORMAT), ("1,23.4", FORMAT), ("1e3", FORMAT),
])
def test_parse_decimal_rejects(text, message):
    with pytest.raises(NotationError, match=message):
        parse_decimal(text)


def reference_reading(n):
    if n == 0:
        return "영"
    text = str(abs(n)).rjust(16, "0")
    words = []
    for group in range(4):
        chunk = text[group * 4:group * 4 + 4]
        if chunk == "0000":
            continue
        if group == 2 and chunk == "0001":
            words.append("만")
            continue
        word = ""
        for offset, char in enumerate(chunk):
            if char == "0":
                continue
            place = REF_PLACES[offset]
            word += place if char == "1" and place else REF_DIGITS[int(char)] + place
        words.append(word + REF_GROUPS[group])
    return ("마이너스 " if n < 0 else "") + " ".join(words)


def reference_group(n):
    if n == 0:
        return "0"
    text = str(abs(n)).rjust(16, "0")
    parts = [str(int(text[g * 4:g * 4 + 4])) + REF_GROUPS[g] for g in range(4) if int(text[g * 4:g * 4 + 4])]
    return ("−" if n < 0 else "") + " ".join(parts)


@pytest.mark.parametrize("value,notation,hangul", [
    (1234567898, "12억 3456만 7898", "십이억 삼천사백오십육만 칠천팔백구십팔"),
    (10000, "1만", "만"), (110000, "11만", "십일만"), (100000000, "1억", "일억"),
    (100010000, "1억 1만", "일억 만"), (0, "0", "영"), (1010, "1010", "천십"),
    (-1234, "−1234", "마이너스 천이백삼십사"), (10 ** 12, "1조", "일조"),
])
def test_group_notation_and_reading_examples(value, notation, hangul):
    assert group_notation(value) == notation
    assert reading_hangul(value) == hangul


def test_reading_matches_reference_for_random_signed_values():
    rng = random.Random(44)
    for value in samples():
        signed = -value if rng.random() < .3 else value
        assert reading_hangul(signed) == reference_reading(signed), signed
        assert group_notation(signed) == reference_group(signed), signed


@pytest.mark.parametrize("value,unit,expected", [
    (12345000, 10 ** 4, 12350000), (12344999, 10 ** 4, 12340000), (-12345000, 10 ** 4, -12350000),
    (4999, 10 ** 4, 0), (-5000, 10 ** 4, -10000), (1234567890, 10 ** 7, 1230000000),
    (1235000000, 10 ** 7, 1240000000), (-1235000000, 10 ** 7, -1240000000),
])
def test_round_half_up_uses_magnitude(value, unit, expected):
    assert round_half_up(value, unit) == expected


def test_read_number_scopes_use_rounded_value_everywhere():
    whole = read_number(1234567890, "all", "원")
    assert whole == Reading(1234567890, False, "12억 3456만 7890원",
                            "십이억 삼천사백오십육만 칠천팔백구십 원", "1,234,567,890원")
    man = read_number(1234567890, "man", "원")
    assert (man.value, man.rounded, man.notation) == (1234570000, True, "약 12억 3457만원")
    assert man.hangul == "십이억 삼천사백오십칠만 원"
    assert man.original == "1,234,567,890원"
    eok = read_number(1234567890, "eok", "원")
    assert (eok.notation, eok.hangul) == ("약 12.3억원", "십이억 삼천만 원")
    assert read_number(1230000000, "eok", "원").notation == "12.3억원"
    assert read_number(-1234567890, "eok", "").notation == "약 −12.3억"
    assert read_number(-1234567890, "all", "").original == "−1,234,567,890"
    assert read_number(5, "all", "  ").hangul == "오"


def test_read_number_rejects_limit_and_long_unit():
    with pytest.raises(NotationError, match="절댓값 1경 미만까지 지원합니다."):
        read_number(LIMIT, "all", "")
    with pytest.raises(NotationError, match="절댓값 1경 미만까지 지원합니다."):
        reading_hangul(-LIMIT)
    with pytest.raises(NotationError, match="단위는 8자까지 입력할 수 있습니다."):
        read_number(1, "all", "가나다라마바사아자")
