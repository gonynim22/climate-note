"""오프라인 단위 환산. 정의/출처는 docs/UNIT_CONVERSION.md 참조. DB/Qt 의존 없음."""
from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class Unit:
    id: str
    label: str
    symbol: str
    factor: float = 1.0
    shift: float = 0.0
    kind: str = "linear"
    source: str = "nist"


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    symbol: str
    group: str
    units: tuple[Unit, ...]
    defaults: tuple[str, str]
    note: str = ""

    def unit(self, unit_id: str) -> Unit:
        for unit in self.units:
            if unit.id == unit_id:
                return unit
        raise ValueError("이 분류에 없는 단위입니다.")


@dataclass(frozen=True)
class ConversionConditions:
    density_kg_l: float | None = None
    water_approximation: bool = False
    molar_mass: float | None = None
    temperature_c: float | None = None
    pressure_kpa: float | None = None
    gas_id: str = ""
    temperature_difference: bool = False


# NIST Chemistry WebBook, g/mol. 출처와 확인일은 단위 계약에 보존한다.
GASES = {
    "co2": ("이산화탄소 · CO₂", 44.0095),
    "co": ("일산화탄소 · CO", 28.0101),
    "no2": ("이산화질소 · NO₂", 46.0055),
    "so2": ("이산화황 · SO₂", 64.064),
    "nh3": ("암모니아 · NH₃", 17.0305),
    "h2s": ("황화수소 · H₂S", 34.081),
}
GAS_CONSTANT = 8.31446261815324  # J/(mol K), N_A × k, SI exact


U = Unit
INCH = 0.0254
FOOT = 12 * INCH
POUND = 0.45359237
GRAVITY = 9.80665
US_GALLON = 231 * INCH**3 * 1000  # L, US liquid
UK_GALLON = 4.54609
MILE = 5280 * FOOT
BTU_IT = POUND * 1000 * (5 / 9) * 4.1868

CATEGORIES = (
    Category("len", "길이", "m", "기본", (
        U("nm", "나노미터", "nm", 1e-9), U("um", "마이크로미터", "µm", 1e-6),
        U("mm", "밀리미터", "mm", .001), U("cm", "센티미터", "cm", .01),
        U("m", "미터", "m"), U("km", "킬로미터", "km", 1000),
        U("in", "인치", "in", INCH), U("ft", "피트", "ft", FOOT),
        U("yd", "야드", "yd", 3 * FOOT), U("mi", "마일", "mi", MILE),
        U("nmi", "해리", "nmi", 1852), U("ja", "자 (척관법)", "자", 10/33, source="kriss"),
        U("ri", "리 (척관법·36정)", "리", 12960 * 10/33, source="kriss"),
        U("ly", "광년 (365.25일)", "ly", 299792458 * 365.25 * 86400, source="iau"),
    ), ("cm", "in"), "리: 척관법 36정 기준. 광년: 진공의 빛·율리우스년 365.25일 기준."),
    Category("mass", "무게", "kg", "기본", (
        U("mg", "밀리그램", "mg", 1e-6), U("g", "그램", "g", .001), U("kg", "킬로그램", "kg"),
        U("t", "톤", "t", 1000), U("gn", "근 (600g)", "근", .6, source="kriss"),
        U("gwan", "관 (3.75kg)", "관", 3.75, source="kriss"),
        U("don", "돈 (3.75g)", "돈", .00375, source="kriss"),
        U("oz", "온스", "oz", POUND/16), U("lb", "파운드", "lb", POUND),
        U("st", "스톤", "st", 14*POUND), U("ct", "캐럿", "ct", .0002),
    ), ("kg", "lb"), "질량 환산. 근은 600g 기준, 온스·파운드는 상용질량(avoirdupois) 기준."),
    Category("vol", "부피", "L", "기본", (
        U("ml", "밀리리터", "mL", .001), U("l", "리터", "L"),
        U("m3", "세제곱미터", "m³", 1000), U("cm3", "세제곱센티미터", "cm³", .001),
        U("doe", "되 (척관법)", "되", 2401/1331, source="kriss"),
        U("mal", "말 (10되)", "말", 24010/1331, source="kriss"),
        U("galus", "갤런 (US liquid)", "US gal", US_GALLON),
        U("qt", "쿼트 (US liquid)", "US qt", US_GALLON/4),
        U("pt", "파인트 (US liquid)", "US pt", US_GALLON/8),
        U("flozus", "액량온스 (US)", "US fl oz", US_GALLON/128),
        U("bbl", "배럴 (석유·42 US gal)", "bbl", US_GALLON*42),
    ), ("l", "galus"), "US liquid 기준. 석유 배럴은 42 US gal. 되·말은 척관법 기준."),
    Category("area", "넓이", "m²", "기본", (
        U("cm2", "제곱센티미터", "cm²", .0001), U("m2", "제곱미터", "m²"),
        U("km2", "제곱킬로미터", "km²", 1e6), U("py", "평", "평", 400/121, source="kriss"),
        U("ar", "아르", "a", 100), U("ha", "헥타르", "ha", 10000),
        U("ft2", "제곱피트", "ft²", FOOT**2), U("ac", "에이커 (국제피트)", "ac", 43560*FOOT**2),
        U("mi2", "제곱마일", "mi²", MILE**2),
    ), ("m2", "py")),
    Category("temp", "온도", "°", "기본", (
        U("c", "섭씨", "°C", 1, 273.15), U("f", "화씨", "°F", 5/9, 459.67),
        U("k", "켈빈", "K"), U("r", "랭킨", "°R", 5/9),
    ), ("c", "f"), "온도값은 절대영도(0 K) 이상입니다. 온도차는 오프셋 없이 환산하며 음수도 허용합니다."),
    Category("speed", "속도", "m/s", "기본", (
        U("ms", "미터/초", "m/s"), U("kmh", "킬로미터/시", "km/h", 1/3.6),
        U("mph", "마일/시", "mph", MILE/3600), U("kn", "노트", "kn", 1852/3600),
        U("fts", "피트/초", "ft/s", FOOT),
    ), ("kmh", "mph")),
    Category("time", "시간", "s", "기본", (
        U("us", "마이크로초", "µs", 1e-6), U("ms_", "밀리초", "ms", .001), U("s", "초", "s"),
        U("min", "분", "min", 60), U("h", "시간", "h", 3600), U("d", "일", "d", 86400),
        U("wk", "주", "wk", 604800), U("mo", "개월 (30일 고정)", "개월", 2592000, source="fixed"),
        U("yr", "년 (365일 고정)", "년", 31536000, source="fixed"),
    ), ("h", "min"), "개월=30일, 년=365일 고정 기간. 실제 달력의 날짜 계산과 다릅니다."),
    Category("data", "데이터", "MB", "기본", (
        U("bit", "비트", "bit", .125), U("B", "바이트", "B"), U("KB", "킬로바이트", "kB", 1e3),
        U("MB", "메가바이트", "MB", 1e6), U("GB", "기가바이트", "GB", 1e9),
        U("TB", "테라바이트", "TB", 1e12), U("PB", "페타바이트", "PB", 1e15),
        U("KiB", "키비바이트", "KiB", 1024), U("MiB", "메비바이트", "MiB", 1024**2),
        U("GiB", "기비바이트", "GiB", 1024**3),
    ), ("GB", "MB"), "kB·MB·GB는 1000배, KiB·MiB·GiB는 1024배 단위입니다."),
    Category("press", "압력", "Pa", "물리", (
        U("pa", "파스칼", "Pa"), U("hpa", "헥토파스칼", "hPa", 100),
        U("kpa", "킬로파스칼", "kPa", 1000), U("mpa", "메가파스칼", "MPa", 1e6),
        U("bar", "바", "bar", 1e5), U("atm", "표준기압", "atm", 101325),
        U("mmhg", "수은주 (0°C)", "mmHg", 13595.1*GRAVITY*.001),
        U("psi", "파운드힘/제곱인치", "psi", POUND*GRAVITY/INCH**2),
        U("kgfcm2", "킬로그램힘/제곱센티미터", "kgf/cm²", GRAVITY*10000),
    ), ("hpa", "atm"), "같은 압력 기준의 단위만 바꿉니다. 절대압과 게이지압의 기준 전환은 하지 않습니다."),
    Category("energy", "에너지", "J", "물리", (
        U("j", "줄", "J"), U("kj", "킬로줄", "kJ", 1000), U("cal", "칼로리 (열화학)", "cal", 4.184),
        U("kcal", "킬로칼로리 (열화학)", "kcal", 4184), U("wh", "와트시", "Wh", 3600),
        U("kwh", "킬로와트시", "kWh", 3.6e6), U("btu", "BTU (IT)", "BTU", BTU_IT),
        U("ev", "전자볼트", "eV", 1.602176634e-19, source="codata"),
        U("toe", "석유환산톤", "toe", 41.868e9, source="keei"),
    ), ("kcal", "kj"), "cal·kcal는 열화학, BTU는 IT 정의. 1 toe=41.868 GJ."),
    Category("power", "전력", "W", "물리", (
        U("mw_", "밀리와트", "mW", .001), U("w", "와트", "W"), U("kw", "킬로와트", "kW", 1000),
        U("mgw", "메가와트", "MW", 1e6), U("gw", "기가와트", "GW", 1e9),
        U("hp", "마력 (영국)", "hp", 550*FOOT*POUND*GRAVITY),
        U("ps", "마력 (미터법)", "PS", 75*GRAVITY), U("btuh", "BTU/시 (IT)", "BTU/h", BTU_IT/3600),
    ), ("kw", "hp")),
    Category("angle", "각도", "∠", "물리", (
        U("deg", "도", "°", math.pi/180), U("rad", "라디안", "rad"),
        U("grad", "그라드", "grad", math.pi/200), U("amin", "각분", "′", math.pi/10800),
        U("asec", "각초", "″", math.pi/648000), U("turn", "회전", "rev", 2*math.pi),
    ), ("deg", "rad")),
    Category("force", "힘", "N", "물리", (
        U("n", "뉴턴", "N"), U("kn_", "킬로뉴턴", "kN", 1000), U("kgf", "킬로그램힘", "kgf", GRAVITY),
        U("lbf", "파운드힘", "lbf", POUND*GRAVITY), U("dyn", "다인", "dyn", 1e-5),
    ), ("kgf", "n")),
    Category("freq", "주파수", "Hz", "물리", (
        U("hz", "헤르츠", "Hz"), U("khz", "킬로헤르츠", "kHz", 1000),
        U("mhz", "메가헤르츠", "MHz", 1e6), U("ghz", "기가헤르츠", "GHz", 1e9),
        U("rpm", "분당 회전", "rpm", 1/60),
    ), ("mhz", "ghz"), "rpm은 회전 빈도입니다. 각속도 rad/s와 구분합니다."),
    Category("co2", "탄소", "CO₂", "환경", (
        U("gco2", "그램 CO₂e", "gCO₂e", .001), U("kgco2", "킬로그램 CO₂e", "kgCO₂e"),
        U("tco2", "톤 CO₂e", "tCO₂e", 1000),
    ), ("kgco2", "tco2"), "이미 산정된 CO₂e의 질량 단위만 환산합니다."),
    Category("gas_fraction", "기체 농도", "ppm", "환경", (
        U("ppm", "ppm (몰분율·10⁻⁶)", "ppm", 1e-6, source="nist_fraction"),
        U("ppb", "ppb (몰분율·10⁻⁹)", "ppb", 1e-9, source="nist_fraction"),
        U("ppt", "ppt (몰분율·10⁻¹²)", "ppt", 1e-12, source="nist_fraction"),
        U("percent", "백분율 (몰분율)", "%", .01, source="nist_fraction"),
        U("umolmol", "마이크로몰/몰", "µmol/mol", 1e-6, source="nist_fraction"),
        U("nmolmol", "나노몰/몰", "nmol/mol", 1e-9, source="nist_fraction"),
        U("molmol", "몰/몰", "mol/mol", source="nist_fraction"),
        U("mgm3", "밀리그램/세제곱미터", "mg/m³", kind="mass_concentration"),
        U("ugm3", "마이크로그램/세제곱미터", "µg/m³", .001, kind="mass_concentration"),
    ), ("ppm", "ppb"), "ppm은 몰분율입니다. 질량 농도는 선택 물질의 몰질량·온도·절대압으로 이상기체를 가정해 계산합니다. 응축·반응·건습 보정은 포함하지 않습니다."),
    Category("mass_fraction", "질량비", "mg/kg", "환경", (
        U("ppm", "ppm (질량분율·10⁻⁶)", "ppm", 1e-6, source="nist_fraction"),
        U("ppb", "ppb (질량분율·10⁻⁹)", "ppb", 1e-9, source="nist_fraction"),
        U("ppt", "ppt (질량분율·10⁻¹²)", "ppt", 1e-12, source="nist_fraction"),
        U("percent", "백분율 (질량분율)", "%", .01, source="nist_fraction"),
        U("mgkg", "밀리그램/킬로그램", "mg/kg", 1e-6, source="nist_fraction"),
        U("ugkg", "마이크로그램/킬로그램", "µg/kg", 1e-9, source="nist_fraction"),
        U("ngkg", "나노그램/킬로그램", "ng/kg", 1e-12, source="nist_fraction"),
        U("gkg", "그램/킬로그램", "g/kg", .001, source="nist_fraction"),
        U("kgkg", "킬로그램/킬로그램", "kg/kg", source="nist_fraction"),
    ), ("ppm", "mgkg"), "질량분율 기준 · 1 ppm = 1 mg/kg. 기체의 몰분율·수질의 mg/L와 구분하세요."),
    Category("water", "수질 농도", "mg/L", "환경", (
        U("mgl", "밀리그램/리터", "mg/L"),
        U("ugl", "마이크로그램/리터", "µg/L", .001),
        U("ngl", "나노그램/리터", "ng/L", 1e-6),
        U("gl", "그램/리터", "g/L", 1000),
        U("mgml", "밀리그램/밀리리터", "mg/mL", 1000),
        U("kgm3", "킬로그램/세제곱미터", "kg/m³", 1000),
        U("gm3", "그램/세제곱미터", "g/m³"),
        U("ppm", "ppm (질량분율·mg/kg)", "ppm", 1e-6, kind="mass_fraction", source="nist_fraction"),
        U("ppb", "ppb (질량분율·µg/kg)", "ppb", 1e-9, kind="mass_fraction", source="nist_fraction"),
    ), ("ppm", "mgl"), "ppm은 질량분율입니다. mg/L = ppm × 용액 밀도(kg/L). 물 기준은 묽은 수용액을 밀도 1로 근사합니다. 직접 입력에는 용질이 아닌 용액 전체의 밀도를 사용하세요."),
    Category("flow", "유량", "m³/h", "환경", (
        U("m3s", "세제곱미터/초", "m³/s"),
        U("m3min", "세제곱미터/분", "m³/min", 1/60),
        U("m3h", "세제곱미터/시", "m³/h", 1/3600),
        U("m3d", "세제곱미터/일", "m³/d", 1/86400),
        U("ls", "리터/초", "L/s", .001),
        U("lmin", "리터/분", "L/min", .001/60),
        U("lh", "리터/시", "L/h", .001/3600),
        U("mlmin", "밀리리터/분", "mL/min", 1e-6/60),
    ), ("m3h", "lmin"), "실제 부피 유량의 크기 기준. Nm³ 등 표준상태 유량으로 보정하지 않습니다."),
    Category("pm", "미세먼지", "µg", "환경", (
        U("ngm3", "나노그램/세제곱미터", "ng/m³", .001), U("ugm3", "마이크로그램/세제곱미터", "µg/m³"),
        U("mgm3", "밀리그램/세제곱미터", "mg/m³", 1000), U("gm3", "그램/세제곱미터", "g/m³", 1e6),
    ), ("ugm3", "mgm3"), "농도 단위 환산. 건강영향이나 담배 개비 수로 비교하지 않습니다."),
    Category("rad", "방사선", "Sv", "환경", (
        U("nsv", "나노시버트", "nSv", 1e-6), U("usv", "마이크로시버트", "µSv", .001),
        U("msv", "밀리시버트", "mSv"), U("sv", "시버트", "Sv", 1000),
        U("mrem", "밀리렘", "mrem", .01), U("rem", "렘", "rem", 10),
    ), ("msv", "usv"), "선량 단위만 환산합니다. 촬영·비행 횟수나 흡수선량 Gy로 바꾸지 않습니다."),
    Category("lux", "조도", "lx", "환경", (
        U("lx", "럭스", "lx"), U("klx", "킬로럭스", "klx", 1000),
        U("fc", "풋캔들", "fc", 1/FOOT**2), U("phot", "포트", "ph", 10000),
    ), ("lx", "fc")),
    Category("db", "음압", "dB", "환경", (
        U("db", "음압레벨 (20µPa 기준)", "dB SPL", kind="log"),
        U("pa_", "음압", "Pa"), U("upa", "음압", "µPa", 1e-6),
        U("ratio", "기준 음압 대비 비율", "배", 2e-5),
    ), ("db", "pa_"), "dB SPL = 20 log₁₀(p / 20µPa). dBA·전력 dB·체감 크기와 구분합니다."),
    Category("cook", "요리 계량", "컵", "생활", (
        U("cupkr", "계량컵 (200mL)", "컵(200)", 200, source="fixed"),
        U("cupus", "계량컵 (240mL)", "컵(240)", 240, source="fda"),
        U("tbsp", "큰술 (15mL)", "큰술", 15, source="fda"),
        U("tsp", "작은술 (5mL)", "작은술", 5, source="fda"),
        U("mlc", "밀리리터", "mL"), U("lc", "리터", "L", 1000),
        U("flozc", "액량온스 (US)", "US fl oz", US_GALLON*1000/128),
    ), ("cupkr", "tbsp"), "표시된 용량의 계량도구 기준. 일반 컵·밥숟가락의 실제 크기와 다를 수 있습니다."),
    Category("fuel", "연비", "km/L", "생활", (
        U("l100", "리터/100킬로미터", "L/100km"), U("kmpl", "킬로미터/리터", "km/L", 100, kind="inverse"),
        U("mpgus", "마일/갤런 (US)", "mpg US", 100*US_GALLON/(MILE/1000), kind="inverse"),
        U("mpguk", "마일/갤런 (UK)", "mpg UK", 100*UK_GALLON/(MILE/1000), kind="inverse"),
    ), ("kmpl", "l100"), "0보다 큰 값만 입력합니다. US/UK 갤런 기준을 구분하세요."),
)
CATEGORY_BY_ID = {category.id: category for category in CATEGORIES}
GROUP_COLORS = {
    "기본": ("#46679C", "#33549E", "#EDF1F8"),
    "물리": ("#B25C8B", "#96406F", "#FAECF4"),
    "환경": ("#2E8F6E", "#257A5F", "#E6F3EE"),
    "생활": ("#B8912C", "#7D670F", "#FBF3DE"),
}

BASIS_SUMMARIES = {
    "len": "척관법·광년 정의 확인", "mass": "질량 기준 · 근 600g",
    "vol": "US liquid · 척관법", "time": "개월 30일 · 년 365일 고정",
    "data": "십진 / 이진 단위 구분", "press": "같은 압력 기준",
    "energy": "열화학 cal · IT BTU", "power": "영국 / 미터법 마력",
    "force": "힘 단위 · 표준중력 정의", "freq": "회전 빈도 기준",
    "co2": "이미 산정된 CO₂e", "mass_fraction": "질량분율 · ppm = mg/kg",
    "flow": "실제 부피 기준", "pm": "질량 농도 기준", "rad": "Sv / rem 선량 기준",
    "db": "dB SPL · 20µPa 기준", "cook": "표시된 계량 용량 기준", "fuel": "US / UK 갤런 구분",
}

_MANTISSA = r"[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)"
_NUMBER = re.compile(_MANTISSA + r"(?:[eE][+-]?[0-9]+)?\Z")
_PARTIAL = re.compile(_MANTISSA + r"[eE][+-]?\Z")


def parse_number(text: str) -> float | None:
    """None은 아직 입력 중. 오류와 0을 구별하며 숫자 접두사만 읽지 않는다."""
    text = text.strip()
    if len(text) > 96:
        raise ValueError("숫자는 96자 이내로 입력하세요.")
    if text in ("", "+", "-", ".", "+.", "-.") or _PARTIAL.fullmatch(text):
        return None
    if not _NUMBER.fullmatch(text):
        raise ValueError("숫자와 올바른 쉼표·소수점만 입력하세요.")
    value = float(text.replace(",", ""))
    mantissa = re.split("[eE]", text)[0]
    if not math.isfinite(value) or (value == 0 and re.search("[1-9]", mantissa)):
        raise ValueError("계산할 수 있는 숫자 범위를 벗어났습니다.")
    return value


def _finite(value: float, nonzero: bool = False) -> float:
    if not math.isfinite(value) or (nonzero and value == 0):
        raise ValueError("결과가 계산 범위를 벗어났습니다.")
    return value


def _positive(value: float | None, name: str) -> float:
    if value is None or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name}은 유한한 양수를 입력하세요.")
    return value


def _check_fraction(value: float, factor: float) -> None:
    maximum = 1 / factor
    if value > maximum and not math.isclose(value, maximum, rel_tol=2e-15):
        raise ValueError("분율은 100% 이하를 입력하세요.")


def crosses_concentration_basis(category_id: str, from_id: str, to_id: str) -> bool:
    category = CATEGORY_BY_ID[category_id]
    return category_id in ("water", "gas_fraction") and category.unit(from_id).kind != category.unit(to_id).kind


def convert(category_id: str, from_id: str, to_id: str, value: float,
            *, conditions: ConversionConditions = ConversionConditions()) -> float:
    category = CATEGORY_BY_ID.get(category_id)
    if category is None:
        raise ValueError("알 수 없는 분류입니다.")
    source, target = category.unit(from_id), category.unit(to_id)
    _finite(value)
    if category_id in ("gas_fraction", "mass_fraction", "water", "flow") and value < 0:
        raise ValueError("농도·유량은 0 이상을 입력하세요.")
    if (category_id == "mass_fraction" or source.kind == "mass_fraction"
            or (category_id == "gas_fraction" and source.kind == "linear")):
        _check_fraction(value, source.factor)
    if category_id == "temp" and not conditions.temperature_difference and value < -source.shift:
        raise ValueError("절대영도(0 K) 이상을 입력하세요.")
    if category_id == "fuel" and value <= 0:
        raise ValueError("연비는 0보다 큰 값을 입력하세요.")
    if category_id == "db" and source.kind != "log" and value <= 0:
        raise ValueError("음압·비율은 0보다 큰 값을 입력하세요.")
    if source.id == target.id:
        return value
    try:
        if category_id == "temp" and conditions.temperature_difference:
            return _finite(value * (source.factor / target.factor), value != 0)
        if crosses_concentration_basis(category_id, from_id, to_id):
            if category_id == "water":
                bridge = _finite(_positive(conditions.density_kg_l, "용액 밀도") * 1e6, True)
                source_is_fraction = source.kind == "mass_fraction"
            else:
                mass = _positive(conditions.molar_mass, "물질의 몰질량")
                pressure = _positive(conditions.pressure_kpa, "절대압")
                temperature = conditions.temperature_c
                if temperature is None or not math.isfinite(temperature) or temperature <= -273.15:
                    raise ValueError("기체 온도는 -273.15°C보다 커야 합니다.")
                bridge = _finite(pressure * 1e6 * mass / GAS_CONSTANT / (temperature + 273.15), True)
                source_is_fraction = source.kind == "linear"
            scale = bridge if source_is_fraction else 1 / bridge
            result = _finite(value * _finite(source.factor / target.factor * scale, True), value != 0)
            if not source_is_fraction:
                _check_fraction(result, target.factor)
            return result
        if source.kind == target.kind and source.kind in ("mass_fraction", "mass_concentration"):
            return _finite(value * (source.factor / target.factor), value != 0)
        if source.kind == target.kind == "linear" and category_id != "temp":
            return _finite(value * (source.factor / target.factor), value != 0)
        if source.kind == "inverse":
            base = _finite(source.factor / value, True)
        elif source.kind == "log":
            base = _finite(10**(value/20 + math.log10(2e-5)), True)
        else:
            shifted = value + source.shift
            base = _finite(shifted * source.factor, shifted != 0)
        if target.kind == "inverse":
            return _finite(target.factor / base, True)
        if target.kind == "log":
            return _finite(20 * (math.log10(base) - math.log10(2e-5)))
        scaled = _finite(base / target.factor, base != 0)
        return _finite(scaled - target.shift)
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("결과가 계산 범위를 벗어났습니다.") from exc


def format_number(value: float) -> str:
    _finite(value)
    if value == 0:
        return "0"
    rounded = float(f"{value:.6g}")
    if abs(rounded) >= 1e12 or abs(rounded) < 1e-4:
        mantissa, exponent = f"{value:.5e}".split("e")
        return f"{mantissa.rstrip('0').rstrip('.')} ×10^{int(exponent)}"
    decimals = max(0, 5 - math.floor(math.log10(abs(rounded))))
    text = f"{rounded:,.{decimals}f}"
    return text.rstrip("0").rstrip(".") if decimals else text


@dataclass(frozen=True)
class RecentConversion:
    category_id: str
    from_id: str
    to_id: str
    text: str
    value: float
    conditions: ConversionConditions = ConversionConditions()


class RecentHistory:
    """실행 중 계산만 보관한다. 영속화·DB 접근 없음."""
    def __init__(self):
        self.items: list[RecentConversion] = []

    def add(self, category_id: str, from_id: str, to_id: str, text: str,
            *, conditions: ConversionConditions = ConversionConditions()) -> None:
        value = parse_number(text)
        if value is None:
            return
        convert(category_id, from_id, to_id, value, conditions=conditions)
        entry = RecentConversion(category_id, from_id, to_id, text, value, conditions)
        key = (category_id, from_id, to_id, value, conditions)
        self.items = [entry] + [r for r in self.items if
            (r.category_id, r.from_id, r.to_id, r.value, r.conditions) != key][:11]
