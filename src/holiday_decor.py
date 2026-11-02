"""공휴일 테마 장식 정의와 움직임 계산(v4.6).

Qt·DB에 의존하지 않는 순수 모듈이다. 어떤 표면(머리줄·D-Day 커버·스티키 띠·토마토 모자)에
무슨 그림을 어디에 놓고 어떻게 움직일지를 데이터로만 적고, 그리는 일(QtSvg·QPainter)은
화면 모듈(ui_holiday_decor)이 한다. 모양·좌표·주기는 시안 mockup-scene.dc.html의
`f.<블록>B` 블록과 `st.*`·`anim(...)` 값 그대로다.

좌표 규칙
- 모든 rect·area는 표면의 '디자인 좌표'다: 머리줄 380x70, D-Day 220x95, 스티키 띠 220x30,
  모자 100x130(hat.svg viewBox의 y -30을 0으로 옮긴 공간).
- `anchor`가 "full"이면 x에 (실제 폭 / 디자인 폭)을 곱해 놓고 크기는 그대로 둔다. 다만 rect 너비가
  표면의 디자인 폭과 같은 전체 폭 조각(능선·줄 장식)은 너비도 같은 비율로 늘린다. 그 밖의 anchor는
  기준점 + rect.x에 크기 그대로 놓는다. 기준점의 디자인 값은 ANCHOR_REF에 있고 실제 기준점(버튼 위치)은
  화면 모듈이 set_anchors로 받는다. y·높이는 비례하지 않는다(머리줄 높이는 70 고정).
- rect.x는 '기준점에서의 거리'다(왼쪽이면 음수). 표를 읽기 쉽게 시안의 절대 x를 넣으면
  _sp()가 기준점을 빼서 저장한다.
- 그리기 순서: base → sprites(튜플 순서) → particles → badges. 시안에서 해·달이 능선 '아래'로
  떠오르는 테마(신정)는 능선을 base가 아니라 해 '뒤의' 정지 스프라이트로 둔다.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

# ── 표면 ────────────────────────────────────────────────────────────

SURFACES = ("header", "dday", "sticky_band", "hat")
DESIGN_SIZE = {"header": (380, 70), "dday": (220, 95), "sticky_band": (220, 30), "hat": (100, 130)}

# anchor 이름 → 기본 크기 표면에서의 기준 x. header는 left_gap=_add_btn 오른쪽 끝,
# center=month_label 가운데, right_gap=next_btn 오른쪽 끝, right=오른쪽 끝이다.
# span_l·span_r은 버튼 묶음 사이 빈 곳의 가운데다: 왼쪽은 '+' 오른쪽 끝~이전 달 버튼 왼쪽 끝(시안 x 77~135),
# 오른쪽은 다음 달 버튼 오른쪽 끝~검색 버튼 왼쪽 끝(시안 x 245~290). 실제 값은 화면 모듈이 위젯 위치에서
# 읽으므로 중간·크게에서는 빈 곳이 넓어지고 기본 크기에서는 거의 사라진다(그럴 땐 조각이 빠진다).
# sticky_band는 왼쪽 도구 버튼 묶음 오른쪽 끝(82), 빈 곳의 가운데(137), 닫기 버튼 왼쪽 끝(192), 오른쪽 끝.
ANCHOR_REF: dict[str, dict[str, float]] = {
    "header": {"full": 0.0, "left_gap": 77.0, "center": 190.0, "right_gap": 245.0, "right": 380.0,
               "span_l": 106.0, "span_r": 267.5},
    "dday": {"full": 0.0},
    "sticky_band": {"full": 0.0, "left_gap": 82.0, "center": 137.0, "right_gap": 192.0, "right": 220.0},
    "hat": {"full": 0.0},
}

# 스티커는 sticker.svg(viewBox 48x48)를 56px 상자에 그린다. STICKER_BADGES의 좌표·글자 크기는
# 이 48 공간 기준이며 -6° 회전 전이다(화면 모듈이 같은 변환으로 56px에 옮긴다).
STICKER_DESIGN = 48

# Badge 바탕(fill이 있을 때)의 둥근 모서리 = min(너비, 높이) * 이 값. 15px '한' 도장 ≈ 2, 22px ≈ 3.
BADGE_RADIUS_RATIO = 0.14
# 떠오르는 자모의 가운데 구간 투명도(시안 B의 --op).
JAMO_ALPHA = 0.55


def sticker_asset(key: str) -> str:
    """스티커 그림 경로(resources/holiday_themes 기준). 모든 키가 갖는다."""
    return f"{key}/sticker.svg"


# ── 데이터 형식 ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Sprite:
    """SVG 한 장을 rect에 놓는다. motion이 있으면 motion_state로 움직인다.

    asset  resources/holiday_themes 기준 경로("newyear/sun.svg"). viewBox 가로세로비 = rect 비율.
    rect   (x, y, w, h). x는 anchor 기준점에서의 거리, 나머지는 디자인 px.
    motion MOTION_KINDS 중 하나 또는 None(정지). period는 초, phase는 CSS animation-delay 그대로
           (음수면 이미 진행된 상태로 시작). origin은 회전·배율 중심(rect의 비율, 0~1).
    once   True면 한 번 재생하고 끝 상태에 머문다(시안의 `both` 한 번 재생).
    follows True면 튜플에서 바로 다음 조각이 그려질 때만 그린다(바람개비 막대·커피잔 김처럼 혼자는
           의미가 없는 조각). 버튼과 겹쳐 다음 조각이 빠지면 같이 빠진다.
    min_scale 버튼과 겹쳐 줄여야 할 때 허용하는 가장 작은 배율(기본 0.5). 1이면 줄이지 않고 비킬 수만
           있다(손 태극기는 좁은 틈에 구겨 넣지 않고 그 자리에서 뺀다).
    """
    asset: str
    rect: tuple[float, float, float, float]
    anchor: str = "full"
    motion: str | None = None
    period: float = 0.0
    phase: float = 0.0
    origin: tuple[float, float] = (0.5, 0.5)
    once: bool = False
    follows: bool = False
    min_scale: float = 0.5


@dataclass(frozen=True)
class Particles:
    """무작위처럼 흩어지는 작은 조각 묶음. 배치는 seed로 정해진다(place_particles).

    kind   "snow"(떨어지는 눈송이 원) / "jamo"(떠오르는 자모 글자) / "stars"(깜빡이는 네 갈래 별)
    area   (x, y, w, h). x는 anchor 기준점에서의 거리. w·h가 0이면 그 점 하나.
    size   (최소, 최대). snow·stars는 원 지름·별 크기 px, jamo는 글자 px(최소~최대 중 정수 하나).
    chars  jamo가 쓸 글자. i번째 입자는 chars[i % len(chars)].
    anchor 시안의 위치 기준(Sprite.anchor와 같다). 기본 "full".
    """
    kind: str
    count: int
    area: tuple[float, float, float, float]
    size: tuple[float, float]
    color: str
    seed: int
    chars: str = ""
    anchor: str = "full"


@dataclass(frozen=True)
class Badge:
    """글자 장식('한' 도장·'한글'·'헌법'). SVG <text>가 아니라 QPainter로 맑은 고딕을 써서 그린다.

    text   줄바꿈은 "\\n". rect 가운데에 가운데 정렬한다.
    fill   바탕색. ""이면 글자만 그린다(스티커는 바탕을 sticker.svg가 그린다).
           바탕이 있으면 둥근 사각형(BADGE_RADIUS_RATIO)을 먼저 칠한다.
    font_px 디자인 단위 글자 크기. angle은 rect 가운데를 축으로 한 회전(도, 시계 방향이 +).
    """
    text: str
    rect: tuple[float, float, float, float]
    fill: str
    color: str
    font_px: int
    angle: float
    anchor: str = "full"


@dataclass(frozen=True)
class SurfaceDecor:
    """표면 하나의 장식. 비어 있으면 그릴 것이 없다.

    base       움직이지 않는 도형을 합친 SVG. base_tile이 0이면 표면 전체(디자인 크기)로 늘려 그리고,
               0보다 크면 viewBox 폭이 base_tile인 조각을 x=0부터 가로로 되풀이해 채운다.
    """
    base: str | None = None
    sprites: tuple[Sprite, ...] = ()
    particles: tuple[Particles, ...] = ()
    badges: tuple[Badge, ...] = ()
    base_tile: float = 0.0


# ── 움직임 ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MotionState:
    """한 순간의 변형. dx·dy는 px, angle은 도(시계 방향 +), scale_x·scale은 배율, opacity는 곱할 투명도."""
    dx: float = 0
    dy: float = 0
    angle: float = 0
    scale_x: float = 1
    scale: float = 1
    opacity: float = 1


def _bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """CSS cubic-bezier(x1, y1, x2, y2) 타이밍 함수."""
    def ease(p: float) -> float:
        if p <= 0.0:
            return 0.0
        if p >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(48):
            s = (lo + hi) / 2
            x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2 + s ** 3
            if x < p:
                lo = s
            else:
                hi = s
        s = (lo + hi) / 2
        return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s * s * y2 + s ** 3
    return ease


_EASE_IN_OUT = _bezier(0.42, 0.0, 0.58, 1.0)
_EASE_OUT = _bezier(0.0, 0.0, 0.58, 1.0)


def _lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p


def _alt(**ends: tuple[float, float]) -> Callable[[float], MotionState]:
    """교대 반복 움직임: 필드마다 (시작값, 끝값)을 eased 진행률로 섞는다."""
    def build(p: float) -> MotionState:
        return MotionState(**{name: _lerp(a, b, p) for name, (a, b) in ends.items()})
    return build


# 교대 반복(CSS `ease-in-out infinite alternate`): 한 주기에 시작→끝, 다음 주기에 끝→시작.
_ALTERNATE: dict[str, Callable[[float], MotionState]] = {
    "swing": _alt(angle=(-7, 7)),
    "sway": _alt(angle=(-4, 4)),
    "wave": _alt(angle=(-9, 7)),
    "kite": _alt(dx=(0, -6), dy=(0, 4), angle=(-8, 4)),
    "glow": _alt(opacity=(0.16, 0.45), scale=(0.9, 1.08)),
    "twinkle": _alt(opacity=(0.25, 1)),
    "bob": _alt(dy=(0, -4)),
    "drift": _alt(dx=(-6, 6)),
}

MOTION_KINDS = frozenset(_ALTERNATE) | {"rise", "spin", "steam", "prop", "float", "snow"}


def _steam(frac: float) -> MotionState:
    # 0% dy 4·투명도 0 → 40% 투명도 0.85 → 100% dy -8·투명도 0 (ease-out)
    dy = _lerp(4, -8, _EASE_OUT(frac))
    if frac < 0.4:
        opacity = 0.85 * _EASE_OUT(frac / 0.4)
    else:
        opacity = 0.85 * (1 - _EASE_OUT((frac - 0.4) / 0.6))
    return MotionState(dy=dy, opacity=opacity)


def _float(frac: float) -> MotionState:
    # 0%·100% 투명도 0, 25~75%는 1(입자의 알파가 곱해진다), dy 14 → -22 (ease-in-out)
    dy = _lerp(14, -22, _EASE_IN_OUT(frac))
    if frac < 0.25:
        opacity = _EASE_IN_OUT(frac / 0.25)
    elif frac <= 0.75:
        opacity = 1.0
    else:
        opacity = 1 - _EASE_IN_OUT((frac - 0.75) / 0.25)
    return MotionState(dy=dy, opacity=opacity)


# 한 방향으로 되풀이(CSS `infinite`, alternate 없음). frac은 한 주기 안 진행률 0~1.
_LOOP: dict[str, Callable[[float], MotionState]] = {
    "spin": lambda f: MotionState(angle=360 * f),
    "steam": _steam,
    "float": _float,
    # 프로펠러: scaleX 1 → 0.15 → 1 (선형). 얇아졌다 펴지며 도는 것처럼 보인다.
    "prop": lambda f: MotionState(scale_x=1 - 0.85 * (1 - abs(2 * f - 1))),
    # 눈: 선형 진행률을 dx·dy에 담는다. 호출 측(particle_pose)이 입자별 이동 거리를 곱한다.
    "snow": lambda f: MotionState(dx=f, dy=f),
}


def motion_state(kind: str, t: float, period: float, phase: float = 0.0, once: bool = False) -> MotionState:
    """움직임 종류 kind의 t초(앱이 움직이기 시작한 뒤) 시점 변형.

    - phase는 CSS animation-delay 그대로다. 안쪽 시각은 t_eff = t - phase이므로 음수 phase(시안의
      `-1.1s`)는 이미 그만큼 진행된 채 시작한다. t_eff < 0(양수 delay 전)은 0으로 고정해 첫 장면을 둔다.
    - 교대 반복(swing·sway·wave·kite·glow·twinkle·bob·drift)은 t_eff=0이 시작값, period가 끝값,
      2·period가 다시 시작값이다. 되돌아가는 주기도 같은 ease-in-out이다.
    - once=True면 period 이후 끝 상태에 머문다. rise는 한 번 재생(ease-out)이며 once=False면 되풀이한다.
    - float는 투명도에 0~1 곡선(0%·100% 0, 25~75% 1)만 담는다. 입자 쪽 알파(Particles)가 곱한다.
    """
    if period <= 0:
        raise ValueError("period는 0보다 커야 합니다")
    alternate = _ALTERNATE.get(kind)
    loop = _LOOP.get(kind)
    if alternate is None and loop is None and kind != "rise":
        raise ValueError(f"알 수 없는 움직임: {kind}")
    cycles = max(0.0, t - phase) / period
    finished = once and cycles >= 1.0
    if kind == "rise":
        frac = 1.0 if finished else cycles - math.floor(cycles)
        return MotionState(dy=_lerp(16, 0, _EASE_OUT(frac)))
    if alternate is not None:
        if finished:
            u = 1.0
        else:
            n = math.floor(cycles)
            frac = cycles - n
            u = frac if n % 2 == 0 else 1.0 - frac
        return alternate(_EASE_IN_OUT(u))
    frac = 1.0 if finished else cycles - math.floor(cycles)
    return loop(frac)  # type: ignore[misc]


# ── 입자 ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Particle:
    """place_particles가 돌려주는 입자 하나. x·y는 Particles.area와 같은 좌표(x는 anchor 기준 거리)."""
    kind: str
    x: float
    y: float
    size: float
    period: float
    phase: float
    alpha: float
    anchor: str = "full"
    drift: float = 0.0   # snow: 한 바퀴 동안 옆으로 흐르는 거리
    y_from: float = 0.0  # snow: 한 바퀴의 시작·끝 y(면 위·아래 밖)
    y_to: float = 0.0
    char: str = ""
    color: str = "#FFFFFF"


def _rng(seed: int) -> Callable[[], float]:
    """시안과 같은 선형 합동 난수(0 이상 1 미만). 같은 seed면 같은 수열이다."""
    state = seed

    def rnd() -> float:
        nonlocal state
        state = (state * 9301 + 49297) % 233280
        return state / 233280
    return rnd


def place_particles(p: Particles) -> tuple[Particle, ...]:
    """Particles를 입자 목록으로 펼친다. 같은 Particles면 언제나 같은 결과다(난수는 p.seed에서만 나온다)."""
    ax, ay, aw, ah = p.area
    smin, smax = p.size
    rnd = _rng(p.seed)
    out: list[Particle] = []
    for i in range(p.count):
        if p.kind == "snow":
            size = round(smin + rnd() * (smax - smin), 1)
            x = ax + round(rnd() * max(0.0, aw - 4))
            rnd()  # 시안이 처음 위치에 쓰던 값(우리는 한 바퀴 전체를 쓰므로 버린다)
            period = round(5 + rnd() * 4, 1)
            phase = round(-rnd() * 9, 1)
            drift = float(round(-8 + rnd() * 16))
            alpha = round(0.45 + rnd() * 0.5, 2)
            out.append(Particle("snow", x, ay, size, period, phase, alpha, p.anchor, drift,
                                ay - 6, ay + ah + 2, "", p.color))
        elif p.kind == "jamo":
            x = ax + rnd() * aw
            y = ay + rnd() * ah
            size = min(smax, smin + int(rnd() * 3))          # 시안: 13~15px
            period = float(6 + int(rnd() * 3))                # 시안: 6~8초
            phase = round(-rnd() * 6.5, 1)                    # 시안: 글자마다 어긋난 음수 delay
            out.append(Particle("jamo", x, y, size, period, phase, JAMO_ALPHA,
                                p.anchor, 0.0, 0.0, 0.0, p.chars[i % len(p.chars)], p.color))
        elif p.kind == "stars":
            x = ax + rnd() * aw
            y = ay + rnd() * ah
            size = round(smin + rnd() * (smax - smin), 1)
            period = round(1.7 + rnd() * 0.9, 1)
            phase = round(-rnd() * 1.5, 1)
            out.append(Particle("stars", x, y, size, period, phase, 1.0, p.anchor, 0.0, 0.0, 0.0, "", p.color))
        else:
            raise ValueError(f"알 수 없는 입자: {p.kind}")
    return tuple(out)


def particle_pose(pt: Particle, t: float) -> tuple[float, float, float]:
    """입자의 t초 시점 (x, y, 투명도). x는 anchor 기준 거리, y는 디자인 좌표다."""
    if pt.kind == "snow":
        p = motion_state("snow", t, pt.period, pt.phase).dy
        return pt.x + pt.drift * p, pt.y_from + (pt.y_to - pt.y_from) * p, pt.alpha
    if pt.kind == "jamo":
        ms = motion_state("float", t, pt.period, pt.phase)
        return pt.x + ms.dx, pt.y + ms.dy, pt.alpha * ms.opacity
    ms = motion_state("twinkle", t, pt.period, pt.phase)
    return pt.x, pt.y, pt.alpha * ms.opacity


# ── 장식 표 ─────────────────────────────────────────────────────────

def _sp(surface: str, asset: str, anchor: str, x: float, y: float, w: float, h: float,
        motion: str | None = None, period: float = 0.0, phase: float = 0.0,
        origin: tuple[float, float] = (0.5, 0.5), once: bool = False, follows: bool = False,
        min_scale: float = 0.5) -> Sprite:
    """시안의 절대 x를 받아 기준점에서의 거리로 바꾼 Sprite를 만든다."""
    return Sprite(asset, (x - ANCHOR_REF[surface][anchor], y, w, h), anchor, motion, period, phase,
                  origin, once, follows, min_scale)


def _pt(surface: str, kind: str, anchor: str, x: float, y: float, w: float, h: float,
        count: int, size: tuple[float, float], color: str, seed: int, chars: str = "") -> Particles:
    return Particles(kind, count, (x - ANCHOR_REF[surface][anchor], y, w, h), size, color, seed, chars, anchor)


def _star(surface: str, anchor: str, x: float, y: float, size: float, color: str, seed: int) -> Particles:
    """시안에서 손으로 놓은 별 하나(정확한 위치, 깜빡임 주기·위상은 seed에서)."""
    return _pt(surface, "stars", anchor, x, y, 0, 0, 1, (size, size), color, seed)


def _hs(*a, **k) -> Sprite:
    return _sp("header", *a, **k)


def _ds(*a, **k) -> Sprite:
    return _sp("dday", *a, **k)


def _bs(*a, **k) -> Sprite:
    return _sp("sticky_band", *a, **k)


def _lantern_sprites() -> tuple[Sprite, ...]:
    """부처님오신날 머리줄 연등 9개: 위치·색 5색 반복·swing 주기 2.6+(i%3)*0.4·위상 -0.5*i."""
    colors = ("pink", "yellow", "red", "green", "orange")
    spots = ((18, 4), (62, 6), (104, 7), (146, 6), (188, 3), (230, 6), (272, 7), (316, 7), (356, 5))
    return tuple(
        # 그림은 12x18 연등 둘레에 은은한 빛 번짐을 위해 (-4,-3) 여백을 둔 20x24 상자다.
        _hs(f"buddha/lantern_{colors[i % 5]}.svg", "full", x - 4, y - 3, 20, 24,
            "swing", round(2.6 + (i % 3) * 0.4, 1), round(-i * 0.5, 1), (0.5, 0.125))
        for i, (x, y) in enumerate(spots)
    )


# samil 손 태극기 6개: 빈 곳(span_l·span_r) 가운데에서 3개씩 한 묶음. 시안은 기본 크기의 버튼 아래 띠에
# 서 있었지만 위쪽 막대 행(52px)에 맞추면 그 자리가 버튼 높이와 겹쳐서, 버튼 묶음 사이 빈 곳으로 옮겼다.
# 묶음 안 간격과 번갈아 흔들리는 주기·위상은 시안의 값이다. 기본 크기는 빈 곳이 12px 이하라 6개 모두 빠진다.
_FLAG_STEP = 40.0
_HAND_FLAGS = (  # (기준점, 빈 곳 가운데에서 깃발 가운데까지 거리, 주기, 위상)
    ("span_l", -_FLAG_STEP, 1.5, 0.0), ("span_l", 0.0, 1.8, -0.5), ("span_l", _FLAG_STEP, 1.6, -0.9),
    ("span_r", -_FLAG_STEP, 1.4, -0.3), ("span_r", 0.0, 1.7, -1.1), ("span_r", _FLAG_STEP, 1.5, -0.7),
)

_GOLD_STAR = {"newyear": "#FFD9A0", "chuseok": "#FFF4CC", "constitution": "#F4E3B0"}


def _build() -> dict[str, dict[str, SurfaceDecor]]:
    d: dict[str, dict[str, SurfaceDecor]] = {}

    # 신정: 능선 두 겹은 해 '뒤의' 정지 스프라이트(해가 능선 아래로 떠오른다). 후광은 은은히 숨 쉰다.
    d["newyear"] = {
        "header": SurfaceDecor(
            sprites=(
                _hs("newyear/halo.svg", "right_gap", 236, 16, 64, 64, "glow", 3.0),
                _hs("newyear/sun.svg", "right_gap", 250, 30, 36, 36, "rise", 3.5, once=True),
                _hs("newyear/header.svg", "full", 0, 0, 380, 70),
            ),
            particles=(
                _star("header", "left_gap", 98, 12, 7, _GOLD_STAR["newyear"], 101),
                _star("header", "left_gap", 124, 48, 5, _GOLD_STAR["newyear"], 102),
                _star("header", "right", 356, 9, 6, _GOLD_STAR["newyear"], 103),
            ),
        ),
        "dday": SurfaceDecor(sprites=(
            _ds("newyear/halo.svg", "full", 148, 34, 54, 54, "glow", 3.0),
            _ds("newyear/sun.svg", "full", 160, 46, 30, 30, "rise", 3.5, once=True),
            _ds("newyear/dday.svg", "full", 0, 0, 220, 95),
        )),
        "sticky_band": SurfaceDecor(sprites=(
            _bs("newyear/sun_band.svg", "center", 140, 8, 13, 13, "rise", 3.5, once=True),
            _bs("newyear/sticky_band.svg", "full", 0, 18, 220, 12),
        )),
    }

    # 설날: 색동 띠 + 복주머니·방패연(머리줄), 매듭(D-Day). 스티키 띠는 색동 바탕(Task 4)이 장식이다.
    d["seollal"] = {
        "header": SurfaceDecor(
            base="seollal/header.svg", base_tile=70,
            sprites=(
                _hs("seollal/pouch.svg", "left_gap", 96, 0, 20, 30, "swing", 2.6, origin=(0.5, 0.0)),
                _hs("seollal/kite.svg", "right_gap", 252, 5, 24, 40, "kite", 3.8, origin=(0.5, 0.75)),
            ),
        ),
        "dday": SurfaceDecor(
            base="seollal/dday.svg", base_tile=70,
            sprites=(_ds("seollal/knot.svg", "full", 162, 0, 22, 64, "swing", 3.4, origin=(0.5, 0.0)),),
        ),
        "sticky_band": SurfaceDecor(),
    }

    # 삼일절: 손 태극기 6개가 번갈아 흔들린다(머리줄, 빈 곳 두 군데에 3개씩), 무궁화(D-Day·띠).
    d["samil"] = {
        "header": SurfaceDecor(sprites=tuple(
            _hs("samil/flag.svg", anchor, ANCHOR_REF["header"][anchor] + dx - 9, 48, 18, 26,
                "wave", period, phase, (2.5 / 18, 1.0), min_scale=1.0)
            for anchor, dx, period, phase in _HAND_FLAGS
        )),
        "dday": SurfaceDecor(sprites=(_ds("samil/mugunghwa.svg", "full", 162, 32, 32, 32),)),
        "sticky_band": SurfaceDecor(sprites=(_bs("samil/mugunghwa.svg", "center", 140, 8, 14, 14),)),
    }

    # 노동절: 김 나는 커피잔 + 아래 박음질 점선(머리줄·띠).
    d["labor"] = {
        "header": SurfaceDecor(
            base="labor/header.svg", base_tile=90,
            sprites=(
                _hs("labor/steam.svg", "right_gap", 258, 2, 6, 16, "steam", 2.6, 0.0, follows=True),
                _hs("labor/steam.svg", "right_gap", 264, 2, 6, 16, "steam", 2.6, -0.9, follows=True),
                _hs("labor/steam.svg", "right_gap", 270, 2, 6, 16, "steam", 2.6, -1.7, follows=True),
                _hs("labor/cup.svg", "right_gap", 254, 20, 28, 24),
            ),
        ),
        "dday": SurfaceDecor(sprites=(
            _ds("labor/steam.svg", "full", 169, 24, 6, 16, "steam", 2.6, 0.0, follows=True),
            _ds("labor/steam.svg", "full", 176, 24, 6, 16, "steam", 2.6, -0.9, follows=True),
            _ds("labor/cup.svg", "full", 164, 40, 28, 24),
        )),
        "sticky_band": SurfaceDecor(base="labor/sticky_band.svg", base_tile=90),
    }

    # 어린이날: 돌아가는 바람개비 2 + 떠 있는 풍선 2(머리줄), 풍선 3(D-Day), 색 점(띠).
    d["children"] = {
        "header": SurfaceDecor(sprites=(
            _hs("children/stick.svg", "left_gap", 104, 21, 2, 50, follows=True),
            _hs("children/pinwheel_a.svg", "left_gap", 92, 8, 26, 26, "spin", 3.2),
            _hs("children/stick_short.svg", "right_gap", 268, 25, 2, 46, follows=True),
            _hs("children/pinwheel_b.svg", "right_gap", 256, 12, 26, 26, "spin", 4.2, -1.0),
            _hs("children/balloon_yellow.svg", "center", 134, 1, 12, 22, "bob", 2.4),
            _hs("children/balloon_pink.svg", "center", 232, 2, 12, 22, "bob", 2.9, -1.0),
        )),
        "dday": SurfaceDecor(sprites=(
            _ds("children/balloon_red.svg", "full", 156, 30, 12, 22, "bob", 2.4),
            _ds("children/balloon_yellow.svg", "full", 170, 24, 12, 22, "bob", 2.9, -1.0),
            _ds("children/balloon_green.svg", "full", 184, 32, 12, 22, "bob", 2.1, -0.4),
        )),
        "sticky_band": SurfaceDecor(sprites=(_bs("children/sticky_band.svg", "center", 104, 8, 76, 14),)),
        # 모자의 프로펠러(좌표는 hat 공간: hat.svg의 y -11 → 19). 6b가 정지 프로펠러를 hat.svg에서 걷어 낸다.
        "hat": SurfaceDecor(sprites=(
            _sp("hat", "children/propeller.svg", "full", 27.6, 14.4, 44.8, 9.2, "prop", 0.45),
        )),
    }

    # 부처님오신날: 위쪽 줄에 연등 9개 + 줄(머리줄), 큰 연등 하나(D-Day), 작은 연등 줄(띠).
    d["buddha"] = {
        "header": SurfaceDecor(base="buddha/header.svg", base_tile=190, sprites=_lantern_sprites()),
        "dday": SurfaceDecor(sprites=(
            # 20x50 연등 둘레에 빛 번짐 여백(-6,-2)을 둔 32x58 상자.
            _ds("buddha/lantern_big.svg", "full", 160, -2, 32, 58, "swing", 3.4, origin=(0.5, 2 / 58)),
        )),
        "sticky_band": SurfaceDecor(sprites=(_bs("buddha/sticky_band.svg", "center", 96, 0, 96, 30),)),
    }

    # 현충일: 추모일이라 움직임이 없다. 조기(깃발 폭만큼 내려 단 태극기)와 흰 국화뿐이다.
    d["memorial"] = {
        "header": SurfaceDecor(sprites=(
            _hs("memorial/chrysanthemum.svg", "left_gap", 96, 27, 22, 22),
            _hs("memorial/halfmast.svg", "right_gap", 264, 4, 20, 62),
        )),
        "dday": SurfaceDecor(sprites=(_ds("memorial/chrysanthemum.svg", "full", 164, 34, 30, 30),)),
        "sticky_band": SurfaceDecor(sprites=(
            _bs("memorial/chrysanthemum_small.svg", "center", 140, 7, 16, 16),
        )),
    }

    # 제헌절: 펼친 책 + 흔들리는 태극기 + 반짝이 2(머리줄), 책(D-Day), 줄 노트(띠).
    d["constitution"] = {
        "header": SurfaceDecor(
            sprites=(
                _hs("constitution/book.svg", "right_gap", 248, 10, 36, 26),
                _hs("constitution/flag.svg", "left_gap", 98, 4, 18, 26, "wave", 1.8, origin=(2.5 / 18, 1.0)),
            ),
            particles=(
                _star("header", "right_gap", 236, 6, 6, _GOLD_STAR["constitution"], 131),
                _star("header", "right_gap", 287, 4, 5, _GOLD_STAR["constitution"], 132),
            ),
        ),
        "dday": SurfaceDecor(sprites=(_ds("constitution/book.svg", "full", 160, 38, 36, 26),)),
        "sticky_band": SurfaceDecor(base="constitution/sticky_band.svg"),
    }

    # 광복절: 아래 가운데서 퍼지는 빛줄기(80초에 한 바퀴) + 무궁화 + 흔들리는 태극기.
    d["liberation"] = {
        "header": SurfaceDecor(sprites=(
            _hs("liberation/rays.svg", "center", 70, -28, 240, 240, "spin", 80.0),
            _hs("liberation/mugunghwa.svg", "left_gap", 94, 26, 24, 24),
            _hs("liberation/flag.svg", "right_gap", 256, 2, 22, 32, "wave", 1.8, origin=(3 / 22, 1.0)),
        )),
        "dday": SurfaceDecor(
            base="liberation/dday.svg",
            sprites=(_ds("liberation/mugunghwa.svg", "full", 162, 32, 32, 32),),
        ),
        "sticky_band": SurfaceDecor(sprites=tuple(
            _bs("liberation/mugunghwa.svg", "center", x, 9, 12, 12) for x in (112, 136, 160)
        )),
    }

    # 추석: 떠오르는 보름달(+후광) + 흔들리는 억새 + 반짝이는 별(머리줄).
    cs = _GOLD_STAR["chuseok"]
    d["chuseok"] = {
        "header": SurfaceDecor(
            sprites=(
                _hs("chuseok/halo.svg", "center", 148, 38, 84, 84, "glow", 3.0),
                _hs("chuseok/moon.svg", "center", 160, 50, 60, 60, "rise", 3.5, once=True),
                _hs("chuseok/susuki_l.svg", "span_l", 106 - 40, 46, 80, 24, "sway", 3.2, origin=(0.5, 1.0)),
                _hs("chuseok/susuki_r.svg", "span_r", 267.5 - 40, 46, 80, 24, "sway", 2.7, -1.1, origin=(0.5, 1.0)),
            ),
            particles=(
                _star("header", "left_gap", 96, 10, 7, cs, 141), _star("header", "left_gap", 126, 52, 5, cs, 142),
                _star("header", "right", 352, 8, 6, cs, 143), _star("header", "left_gap", 16, 8, 5, cs, 144),
                _star("header", "right_gap", 238, 12, 5, cs, 145), _star("header", "right_gap", 274, 6, 6, cs, 146),
            ),
        ),
        "dday": SurfaceDecor(
            sprites=(
                _ds("chuseok/halo.svg", "full", 147, 19, 54, 54, "glow", 3.0),
                _ds("chuseok/moon_small.svg", "full", 158, 30, 32, 32),
            ),
            particles=(
                _star("dday", "full", 150, 40, 6, cs, 151), _star("dday", "full", 204, 58, 5, cs, 152),
                _star("dday", "full", 128, 56, 4, cs, 153), _star("dday", "full", 140, 30, 4, cs, 154),
            ),
        ),
        "sticky_band": SurfaceDecor(sprites=(_bs("chuseok/sticky_band.svg", "center", 108, 0, 64, 30),)),
    }

    # 개천절: 위 가운데서 내려오는 옅은 빛 + 좌우로 흐르는 전통 구름 4(머리줄).
    d["gaecheon"] = {
        "header": SurfaceDecor(sprites=(
            _hs("gaecheon/beam.svg", "center", 130, 0, 120, 70),
            _hs("gaecheon/cloud_swirl.svg", "left_gap", 82, 5, 44, 20, "drift", 7.0),
            _hs("gaecheon/cloud_swirl.svg", "right_gap", 246, 8, 40, 18, "drift", 9.0, -3.0),
            _hs("gaecheon/cloud_plain.svg", "span_l", 106 - 17, 50, 34, 16, "drift", 9.0, -3.0),
            _hs("gaecheon/cloud_plain.svg", "span_r", 267.5 - 17, 52, 34, 16, "drift", 7.0),
        )),
        "dday": SurfaceDecor(sprites=(
            _ds("gaecheon/cloud_swirl.svg", "full", 134, 34, 44, 20, "drift", 7.0),
            _ds("gaecheon/cloud_plain.svg", "full", 168, 52, 33, 15, "drift", 9.0, -3.0),
        )),
        "sticky_band": SurfaceDecor(sprites=(
            _bs("gaecheon/cloud_solid.svg", "center", 108, 6, 36, 16),
            _bs("gaecheon/cloud_solid.svg", "center", 150, 11, 30, 14),
        )),
    }

    # 한글날: 원고지 격자 + 떠오르며 사라지는 자모 + 붉은 '한' 도장.
    jam = "#EADFC8"
    d["hangul"] = {
        "header": SurfaceDecor(
            base="hangul/header.svg", base_tile=19,
            particles=(
                _pt("header", "jamo", "left_gap", 80, 28, 0, 0, 1, (13, 15), jam, 161, "ㄱ"),
                _pt("header", "jamo", "left_gap", 100, 40, 0, 0, 1, (13, 15), jam, 162, "ㅎ"),
                _pt("header", "jamo", "left_gap", 119, 24, 0, 0, 1, (13, 15), jam, 163, "ㅏ"),
                _pt("header", "jamo", "right_gap", 248, 36, 0, 0, 1, (13, 15), jam, 164, "ㄴ"),
                _pt("header", "jamo", "right_gap", 266, 22, 0, 0, 1, (13, 15), jam, 165, "ㅇ"),
            ),
            badges=(Badge("한", (357 - 380, 51, 15, 15), "#B5443B", "#FFFFFF", 9, -6, "right"),),
        ),
        "dday": SurfaceDecor(
            base="hangul/dday.svg", base_tile=18,
            badges=(Badge("한", (170, 38, 22, 22), "#B5443B", "#FFFFFF", 12, -8, "full"),),
        ),
        "sticky_band": SurfaceDecor(base="hangul/sticky_band.svg", base_tile=15),
    }

    # 크리스마스: 위쪽 솔잎 가랜드·장식 볼·아래 쌓인 눈 + 내리는 눈(머리줄), 트리·눈(D-Day), 솔가지(띠).
    d["christmas"] = {
        "header": SurfaceDecor(
            base="christmas/header.svg", base_tile=76,
            particles=(_pt("header", "snow", "full", 0, 0, 380, 70, 26, (2, 4.5), "#FFFFFF", 11),),
        ),
        "dday": SurfaceDecor(
            base="christmas/dday.svg", base_tile=11,
            sprites=(_ds("christmas/tree.svg", "full", 150, 24, 44, 46),),
            particles=(_pt("dday", "snow", "full", 0, 0, 220, 95, 9, (1.8, 3.2), "#FFFFFF", 31),),
        ),
        "sticky_band": SurfaceDecor(
            base="christmas/sticky_band.svg", base_tile=11,
            sprites=(_bs("christmas/branch.svg", "center", 112, 9, 46, 19),),
        ),
    }
    return d


DECOR: dict[str, dict[str, SurfaceDecor]] = _build()

# 글자가 있는 스티커: 바탕(흰 테두리·도장·책 표지)은 sticker.svg가 그리고 글자는 Badge로 둔다.
# 좌표·글자 크기는 STICKER_DESIGN(48) 공간, 회전 전이다. angle은 도장·책이 스티커 안에서 갖는 기울기
# (스티커 전체의 -6°는 따로 더해진다). 시안: 도장 80%·글자 14px(56px 상자) → 48 공간 12px.
STICKER_BADGES: dict[str, tuple[Badge, ...]] = {
    "hangul": (Badge("한\n글", (8.25, 8.25, 31.5, 31.5), "", "#FFFFFF", 12, -8.0),),
    "constitution": (Badge("헌\n법", (16.7, 11.0, 18.0, 26.0), "", "#E6C27A", 12, 4.0),),
}


def referenced_assets() -> set[str]:
    """DECOR가 가리키는 모든 SVG 경로(resources/holiday_themes 기준). 스티커·모자 SVG는 제외."""
    found: set[str] = set()
    for surfaces in DECOR.values():
        for decor in surfaces.values():
            if decor.base:
                found.add(decor.base)
            found.update(s.asset for s in decor.sprites)
    return found
