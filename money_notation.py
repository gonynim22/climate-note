"""금액·숫자 표기 도우미의 순수 계산. Qt·DB·네트워크에 접근하지 않는다.

근거: 「행정업무의 운영 및 혁신에 관한 규정 시행규칙」 제2조(금액 한글 병기),
한글 맞춤법 제43·44항(단위 명사·만 단위 띄어쓰기). 상세 계약은 docs/MONEY_NOTATION.md.
금액과 정수는 int, 환산은 Decimal만 쓰며 float와 내장 round()는 쓰지 않는다.
"""
from dataclasses import dataclass
from decimal import Decimal
import re

LIMIT = 10 ** 16  # 1경. 모든 모드의 절댓값 상한(미만)

_DIGITS = "영일이삼사오육칠팔구"
_SMALL = ("", "십", "백", "천")
_BIG = ("", "만", "억", "조")
_INTEGER = r"(?:\d{1,3}(?:,\d{3})+|\d+)"
_INTEGER_RE = re.compile(rf"([-−]?)({_INTEGER})", re.ASCII)
_FRACTION_RE = re.compile(rf"[-−]?{_INTEGER}\.\d+", re.ASCII)
_DECIMAL_RE = re.compile(rf"([-−]?)({_INTEGER})(?:\.(\d+))?", re.ASCII)
_FORMAT_MESSAGE = "숫자와 세 자리 쉼표만 입력할 수 있습니다."


class NotationError(ValueError):
    """사용자에게 그대로 보여 줄 한국어 입력 오류."""


@dataclass(frozen=True)
class OfficialAmount:
    digits: str  # '113,560'
    hangul: str  # '일십일만삼천오백육십'
    text: str    # '금113,560원(금일십일만삼천오백육십원)'


def parse_integer(text: str) -> int:
    """앞뒤 공백만 제거하고 정수 전체를 검증한다. 잘못된 값은 보정하지 않는다."""
    raw = text.strip()
    if not raw:
        raise NotationError("값을 입력하세요.")
    match = _INTEGER_RE.fullmatch(raw)
    if match is None:
        if _FRACTION_RE.fullmatch(raw):
            raise NotationError("정수만 입력할 수 있습니다.")
        raise NotationError(_FORMAT_MESSAGE)
    value = int(match.group(2).replace(",", ""))
    return -value if match.group(1) else value


def parse_decimal(text: str) -> Decimal:
    """단위 환산 입력. 소수는 6자리까지 정확한 Decimal로 받는다."""
    raw = text.strip()
    if not raw:
        raise NotationError("값을 입력하세요.")
    match = _DECIMAL_RE.fullmatch(raw)
    if match is None:
        raise NotationError(_FORMAT_MESSAGE)
    sign, integer, fraction = match.groups()
    if fraction is not None and len(fraction) > 6:
        raise NotationError("소수는 6자리까지 입력할 수 있습니다.")
    value = Decimal(integer.replace(",", "") + (f".{fraction}" if fraction else ""))
    return -value if sign else value


def _groups(value: int) -> list[int]:
    """0 이상 정수를 낮은 자리부터 네 자리 묶음으로 나눈다."""
    groups = []
    while value:
        value, group = divmod(value, 10000)
        groups.append(group)
    return groups


def _group_hangul(value: int, official: bool) -> str:
    """네 자리 묶음 하나를 읽는다. official이면 십·백·천 앞의 '일'도 적는다."""
    text = ""
    for position in range(3, -1, -1):
        digit = value // 10 ** position % 10
        if digit == 0:
            continue
        if digit == 1 and position > 0 and not official:
            text += _SMALL[position]
        else:
            text += _DIGITS[digit] + _SMALL[position]
    return text


def official_hangul(n: int) -> str:
    """공문서 금액 한글. 모든 자리에 '일'을 적고 공백 없이 붙여 쓴다(변조 방지 관례)."""
    if not 1 <= n < LIMIT:
        raise NotationError("금액은 1원 이상 1경 미만이어야 합니다.")
    groups = _groups(n)
    return "".join(
        _group_hangul(group, True) + _BIG[index]
        for index, group in reversed(list(enumerate(groups))) if group
    )


def official_amount(n: int) -> OfficialAmount:
    hangul = official_hangul(n)
    digits = f"{n:,}"
    return OfficialAmount(digits, hangul, f"금{digits}원(금{hangul}원)")


SCOPES = ("all", "man", "eok")


@dataclass(frozen=True)
class Reading:
    value: int       # 표시 범위를 적용한 값
    rounded: bool    # 반올림으로 값이 바뀌었는지
    notation: str    # '약 12억 3457만원'
    hangul: str      # '십이억 삼천사백오십칠만 원'
    original: str    # '1,234,567,890원'


def _check_limit(n) -> None:
    if abs(n) >= LIMIT:
        raise NotationError("절댓값 1경 미만까지 지원합니다.")


def _signed_digits(n: int) -> str:
    return ("−" if n < 0 else "") + f"{abs(n):,}"


def group_notation(n: int) -> str:
    """한글 맞춤법 제44항 예시 형식 '12억 3456만 7898'. 묶음 안에는 쉼표를 넣지 않는다."""
    _check_limit(n)
    if n == 0:
        return "0"
    groups = _groups(abs(n))
    text = " ".join(f"{group}{_BIG[index]}" for index, group in reversed(list(enumerate(groups))) if group)
    return "−" + text if n < 0 else text


def reading_hangul(n: int) -> str:
    """만 단위로 띄어 읽는다. 십·백·천 앞의 '일'과 만 묶음의 '일'을 생략한다."""
    _check_limit(n)
    if n == 0:
        return "영"
    parts = []
    groups = _groups(abs(n))
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if not group:
            continue
        head = "" if index == 1 and group == 1 else _group_hangul(group, False)
        parts.append(head + _BIG[index])
    text = " ".join(parts)
    return "마이너스 " + text if n < 0 else text


def round_half_up(n: int, unit: int) -> int:
    """절댓값 기준 사사오입(0에서 먼 쪽). unit은 10 이상의 10의 거듭제곱이다."""
    magnitude = (abs(n) + unit // 2) // unit * unit
    return -magnitude if n < 0 else magnitude


def read_number(n: int, scope: str, unit_text: str = "") -> Reading:
    _check_limit(n)
    unit = unit_text.strip()
    if len(unit) > 8:
        raise NotationError("단위는 8자까지 입력할 수 있습니다.")
    if scope == "all":
        value = n
    elif scope == "man":
        value = round_half_up(n, 10 ** 4)
    elif scope == "eok":
        value = round_half_up(n, 10 ** 7)
    else:
        raise ValueError(f"알 수 없는 표시 범위입니다: {scope}")
    rounded = value != n
    if scope == "eok":
        eok = abs(Decimal(value)) / Decimal(10 ** 8)
        body = ("−" if value < 0 else "") + f"{eok:,.1f}억"
    else:
        body = group_notation(value)
    notation = ("약 " if rounded else "") + body + unit
    hangul = reading_hangul(value) + (f" {unit}" if unit else "")
    return Reading(value, rounded, notation, hangul, _signed_digits(n) + unit)
