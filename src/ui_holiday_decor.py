"""공휴일 테마 장식 레이어(v4.6): 머리줄·D-Day 커버·스티키 띠·토마토 모자 위에 겹쳐 그리는 그림.

무엇을 어디에 놓을지는 holiday_decor.py(Qt 없음)가 정하고, 여기서는 그리기만 한다.
화면 전용이라 DB에 아무것도 쓰지 않는다.

- DecorationLayer는 부모 위젯 전체를 덮는 투명 레이어다. 마우스를 통과시키고, 부모의 다른 자식
  (버튼·글자)보다 아래 층(lower)에 있다. 그릴 것이 없으면 숨는다.
- 움직임은 공용 타이머 하나(FRAME_MS)로 update()만 부른다. 움직이는 조각이 있고, 보이고,
  멈춤 상태가 아니고, 최소화가 아니고, Windows '애니메이션 효과'가 켜진 때만 돈다. 멈춘 동안은
  시간도 멈췄다가(숨김·잠금 구간은 빼고) 다시 보일 때 이어 간다.
- 멈춘 채로 그릴 때도 motion_state를 거친다. 후광은 불투명한 원 그림이라 glow의 투명도(0.16~0.45)가
  있어야 은은하다. 'Windows 애니메이션 끔'에서 떠오르는 해·달(once)은 끝 위치(떠오른 모습)에 둔다.
- 그림은 SVG를 한 번 QPixmap으로 만들어 쓴다(레이어마다 캐시). 프레임마다 SVG를 다시 해석하지 않는다.
"""
from __future__ import annotations

import ctypes
import logging
import math
import sys
import time
from dataclasses import replace

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, Qt, QTimer, QObject
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPixmap, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QWidget

import holiday_decor as hd
from app_paths import resource_root

_logger = logging.getLogger(__name__)

# 초당 24프레임 이하(설계 문서 '그리기·자원 규칙').
FRAME_MS = 42

# 스티키 스티커: 56px 그림을 -6° 기울인다. 기울인 모서리·흰 테두리가 잘리지 않게 사방에 여유를 둔다.
STICKER_BOX = 56
STICKER_PAD = 3
STICKER_LABEL = STICKER_BOX + 2 * STICKER_PAD
STICKER_ANGLE = -6.0
STICKER_INSET = 10   # 본문 오른쪽 아래에서 안쪽으로(그림 기준)

# 눈 개수는 머리줄이 넓을수록 늘리되(중간·크게는 5배 가까이 넓다) 그리는 양이 폭주하지 않게 3배까지만.
_SNOW_MAX_DENSITY = 3.0
# 띠에서 도구 버튼과 장식 사이에 두는 여유(px)와, 이보다 작게 줄여야 하면 그리지 않는 비율.
_BAND_PAD = 2.0
_MIN_FIT_SCALE = 0.5
_BACKDROP_RATIO = 0.3
# 띠 아래로 잘리는 조각을 내려 놓은 뒤에도 띠 안에 최소한 이만큼은 보여야 그린다.
_MIN_VISIBLE = 6.0
# 움직임 허용 여부(Windows 설정)를 다시 읽는 간격(틱). 약 4초.
_RECHECK_TICKS = 96

_STAR_POINTS = ((5, 0), (6.1, 3.9), (10, 5), (6.1, 6.1), (5, 10), (3.9, 6.1), (0, 5), (3.9, 3.9))
_FONT_FAMILY = "Malgun Gothic"


# ── 순수 계산(Qt 객체 없음) ─────────────────────────────────────────

def motion_allowed() -> bool:
    """Windows '애니메이션 효과'(SPI_GETCLIENTAREAANIMATION)가 켜져 있으면 True.

    읽지 못하거나 Windows가 아니면 True(꾸미기일 뿐이라 막지 않는다).
    """
    if sys.platform != "win32":
        return True
    try:
        flag = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(flag), 0)
    except (AttributeError, OSError):
        return True
    return bool(flag.value) if ok else True


def resolve_rect(surface: str, rect: tuple[float, float, float, float], anchor: str,
                 anchors: dict[str, float], width: float) -> tuple[float, float, float, float]:
    """디자인 rect를 실제 (x, y, w, h)로 바꾼다. y·h는 그대로다(머리줄 높이는 늘리지 않는다).

    - anchor "full": x는 (실제 폭 / 디자인 폭) 비율로 늘린다. 너비는 rect.w가 표면의 디자인 폭과
      같은 '전체 폭 조각'(신정 능선·줄 장식)일 때만 같은 비율로 늘리고, 그 밖의 조각은 크기 그대로다.
    - 그 밖의 anchor: x는 기준점에서의 거리다. 실제 기준점은 anchors에서 읽고, 없으면 기본 크기
      기준값(ANCHOR_REF)에 비율을 곱한다. 크기는 그대로다.
    Qt 코드와 시험이 같은 규칙을 쓰도록 이 함수 한 곳에만 둔다.
    """
    design_w = hd.DESIGN_SIZE[surface][0]
    sx = width / design_w
    x, y, w, h = rect
    if anchor == "full":
        full_width = abs(w - design_w) < 0.5
        return (x * sx, y, w * sx if full_width else w, h)
    base = anchors.get(anchor)
    if base is None:
        base = hd.ANCHOR_REF[surface][anchor] * sx
    return (base + x, y, w, h)


def fit_span(x: float, w: float, lo: float, hi: float,
             min_scale: float = _MIN_FIT_SCALE) -> tuple[float, float] | None:
    """조각(x, 너비 w)을 [lo, hi] 안에 넣는다. 돌려주는 값은 (새 x, 배율).

    들어가면 그대로(배율 1), 넓으면 가운데를 지키며 줄이고, 줄여야 하는 배율이 min_scale보다
    작으면 None(그리지 않는다). 버튼 위를 덮지 않으려고 겹치는 대신 줄이거나 뺀다.
    """
    avail = hi - lo
    if avail <= 0 or w <= 0:
        return None
    scale = min(1.0, avail / w)
    if scale < min_scale:
        return None
    new_w = w * scale
    new_x = (x + w / 2) - new_w / 2
    new_x = max(lo, min(new_x, hi - new_w))
    return new_x, scale


def is_backdrop(surface: str, width: float) -> bool:
    """폭이 표면 디자인 폭의 30% 이상인 넓은 배경 조각(능선·빛줄기·옅은 빛)인가.

    이런 조각은 버튼 뒤로 지나가도 된다(옅은 바탕이고, 피하면 효과가 통째로 사라진다).
    버튼·글자를 피하는 규칙(fit_clear)은 나머지 조각에만 적용한다.
    """
    return width >= hd.DESIGN_SIZE[surface][0] * _BACKDROP_RATIO


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def slide_below(rect: tuple[float, float, float, float], blockers: list[tuple[float, float, float, float]],
                band_h: float, pad: float = _BAND_PAD, min_visible: float = _MIN_VISIBLE
                ) -> tuple[float, float, float, float] | None:
    """띠 아래로 넘쳐 잘리는 조각(떠오르는 달·후광)을 버튼·글자 아래로 내려 놓는다.

    띠 안에 다 들어오는 조각은 그대로 둔다. 가로로 겹치는 장애물의 아래 끝까지 내려가고, 그러면 띠 안에
    min_visible px도 안 남으면 None(그리지 않는다). 잘리는 조각이라 내려도 모양이 달라지지 않는다.
    """
    x, y, w, h = rect
    if y + h <= band_h:
        return rect
    top = y
    for bx, by, bw, bh in blockers:
        if bx < x + w and x < bx + bw and by < y + h and y < by + bh:
            top = max(top, by + bh + pad)
    if band_h - top < min_visible:
        return None
    return (x, top, w, h)


def fit_clear(rect: tuple[float, float, float, float], blockers: list[tuple[float, float, float, float]],
              pad: float = _BAND_PAD, min_scale: float = _MIN_FIT_SCALE
              ) -> tuple[float, float, float, float] | None:
    """조각 rect를 버튼·글자 자리(blockers)와 겹치지 않게 만든다. 못 만들면 None(그리지 않는다).

    세로로 겹치는 장애물만 본다. 겹치면 가운데를 지키며 장애물 사이 빈 곳에 맞춰 줄이거나(배율이
    min_scale 이상일 때) 빈 쪽으로 옮긴다. 줄이거나 옮긴 뒤 다른 장애물에 닿으면 한 번 더 맞추고,
    그래도 겹치면 뺀다. 버튼 위를 덮느니 장식을 빼는 쪽이 계약이다(설계 문서 '크기별').
    """
    x, y, w, h = rect
    for _ in range(3):
        current = (x, y, w, h)
        hits = [b for b in blockers if _overlaps(current, b)]
        if not hits:
            return current
        cx = x + w / 2
        lo, hi = -math.inf, math.inf
        for bx, _by, bw, _bh in hits:
            if bx <= cx <= bx + bw:
                return None  # 가운데가 버튼·글자 위면 옮겨 봐야 제자리가 아니다
            if bx + bw / 2 <= cx:
                lo = max(lo, bx + bw + pad)
            else:
                hi = min(hi, bx - pad)
        fitted = fit_span(x, w, lo, hi, min_scale)
        if fitted is None:
            return None
        new_x, scale = fitted
        y += (h - h * scale) / 2
        x, w, h = new_x, w * scale, h * scale
    final = (x, y, w, h)
    return None if any(_overlaps(final, b) for b in blockers) else final


def map_band_y(surface: str, y: float, h: float, band_h: float | None) -> float:
    """디자인 y를 실제 띠 높이(band_h)에 맞춘다. band_h가 없거나 디자인 높이와 같으면 그대로다.

    디자인 높이의 위쪽 끝에 붙은 조각은 위에, 아래쪽 끝에 붙은 조각(능선·땅·떠오르는 달)은 띠의 아래에,
    나머지와 위·아래를 다 덮는 조각은 가운데에 둔다. 띠 안에 들어올 만한 크기(h <= band_h)는 띠 밖으로
    나가지 않게 눌러 둔다(머리줄은 70px 디자인을 52px 띠에 놓으므로 가운데 조각이 위로 잘리지 않게).
    """
    design_h = hd.DESIGN_SIZE[surface][1]
    if not band_h or abs(band_h - design_h) < 0.5:
        return y
    shift = band_h - design_h
    top = y <= 0.5
    bottom = y + h >= design_h - 1.0
    if top and not bottom:
        mapped = y
    elif bottom and not top:
        mapped = y + shift
    else:
        mapped = y + shift / 2
    if h <= band_h:
        mapped = max(0.0, min(mapped, band_h - h))
    return mapped


def map_band_span(surface: str, rect: tuple[float, float, float, float],
                  band_h: float | None) -> tuple[float, float]:
    """조각의 실제 (y, h). 표면 전체 폭·전체 높이를 덮는 바탕(신정 능선)은 띠 높이로 늘리고,
    나머지는 크기를 지키며 map_band_y로 놓는다."""
    design_w, design_h = hd.DESIGN_SIZE[surface]
    _x, y, w, h = rect
    if (band_h and abs(band_h - design_h) >= 0.5 and w >= design_w * 0.9
            and y <= 0.5 and design_h - 1.0 <= y + h <= design_h + 1.0):
        return 0.0, float(band_h)
    return map_band_y(surface, y, h, band_h), h


def scaled_particles(spec: hd.Particles, width: float, surface: str) -> hd.Particles:
    """전체 폭 기준 눈은 면 폭에 비례해 개수를 늘린다(최대 3배). 나머지는 손으로 놓은 점이라 그대로다."""
    if spec.kind != "snow" or spec.anchor != "full":
        return spec
    density = min(_SNOW_MAX_DENSITY, max(1.0, width / hd.DESIGN_SIZE[surface][0]))
    return replace(spec, count=max(1, round(spec.count * density)))


# ── 그리기 도우미 ───────────────────────────────────────────────────

def _renderer_for(cache: dict, asset: str) -> QSvgRenderer | None:
    renderer = cache.get(asset)
    if renderer is None:
        path = resource_root() / "resources" / "holiday_themes" / asset
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            _logger.warning("공휴일 장식 그림을 읽지 못함: %s", asset)
        cache[asset] = renderer
    return renderer if renderer.isValid() else None


def _blank_pixmap(width: float, height: float, dpr: float) -> QPixmap:
    pix = QPixmap(max(1, math.ceil(width * dpr)), max(1, math.ceil(height * dpr)))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    return pix


def _rounded_path(w: float, h: float, tl: float, tr: float, br: float, bl: float) -> QPainterPath:
    """모서리마다 반지름이 다른 둥근 사각형(0, 0, w, h)."""
    path = QPainterPath()
    path.moveTo(tl, 0)
    path.lineTo(w - tr, 0)
    if tr:
        path.arcTo(w - 2 * tr, 0, 2 * tr, 2 * tr, 90, -90)
    path.lineTo(w, h - br)
    if br:
        path.arcTo(w - 2 * br, h - 2 * br, 2 * br, 2 * br, 0, -90)
    path.lineTo(bl, h)
    if bl:
        path.arcTo(0, h - 2 * bl, 2 * bl, 2 * bl, 270, -90)
    path.lineTo(0, tl)
    if tl:
        path.arcTo(0, 0, 2 * tl, 2 * tl, 180, -90)
    path.closeSubpath()
    return path


def _draw_badge(painter: QPainter, badge: hd.Badge, rect: QRectF) -> None:
    """도장·책 표지 글자. 맑은 고딕 굵게, rect 가운데 정렬, rect 가운데를 축으로 angle만큼 돌린다."""
    painter.save()
    center = rect.center()
    painter.translate(center)
    painter.rotate(badge.angle)
    painter.translate(-center)
    if badge.fill:
        radius = min(rect.width(), rect.height()) * hd.BADGE_RADIUS_RATIO
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(badge.fill))
        painter.drawRoundedRect(rect, radius, radius)
    font = QFont(_FONT_FAMILY)
    font.setPixelSize(badge.font_px)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(badge.color))
    painter.drawText(rect, Qt.AlignCenter, badge.text)
    painter.restore()


def sticker_pixmap(key: str, dpr: float = 1.0) -> QPixmap:
    """스티키 스티커: sticker.svg + 글자(STICKER_BADGES)를 56px로 그려 -6° 기울인 투명 QPixmap.

    그림 크기는 STICKER_LABEL(사방 STICKER_PAD 여유). 글자는 SVG <text>가 아니라 QPainter로 그린다.
    그림이 없거나 읽지 못하면 같은 크기의 빈 그림을 돌려준다(꾸미기일 뿐이라 화면을 막지 않는다).
    """
    dpr = max(float(dpr), 1.0)
    pix = _blank_pixmap(STICKER_LABEL, STICKER_LABEL, dpr)
    renderer = _renderer_for({}, hd.sticker_asset(key))
    if renderer is None:
        return pix
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.translate(STICKER_LABEL / 2, STICKER_LABEL / 2)
    painter.rotate(STICKER_ANGLE)
    painter.translate(-STICKER_BOX / 2, -STICKER_BOX / 2)
    k = STICKER_BOX / hd.STICKER_DESIGN
    painter.scale(k, k)
    renderer.render(painter, QRectF(0, 0, hd.STICKER_DESIGN, hd.STICKER_DESIGN))
    for badge in hd.STICKER_BADGES.get(key, ()):
        _draw_badge(painter, badge, QRectF(*badge.rect))
    painter.end()
    return pix


def make_sticker_label(parent: QWidget) -> QLabel:
    """스티커를 얹을 투명 레이블. 마우스를 통과시켜 본문 편집·크기 조절을 가로채지 않는다."""
    label = QLabel(parent)
    label.setObjectName("holidaySticker")
    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    label.setStyleSheet("background: transparent;")
    label.setFixedSize(STICKER_LABEL, STICKER_LABEL)
    label.hide()
    return label


# ── 공용 프레임 시계 ────────────────────────────────────────────────

class _FrameClock(QObject):
    """FRAME_MS마다 움직이는 레이어에게 update()를 시키는 공용 타이머. 움직이는 레이어가 없으면 서 있다."""

    def __init__(self) -> None:
        super().__init__(QCoreApplication.instance())
        self._layers: list[DecorationLayer] = []
        self._ticks = 0
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def add(self, layer: DecorationLayer) -> None:
        if layer not in self._layers:
            self._layers.append(layer)
        if not self._timer.isActive():
            self._timer.start()

    def discard(self, layer: DecorationLayer) -> None:
        if layer in self._layers:
            self._layers.remove(layer)
        if not self._layers:
            self._timer.stop()

    def is_active(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        self._ticks += 1
        recheck = self._ticks % _RECHECK_TICKS == 0
        for layer in list(self._layers):
            if not shiboken6.isValid(layer):
                self._layers.remove(layer)
                continue
            if recheck:
                layer.sync_animation()  # Windows 애니메이션 설정이 바뀌었을 수 있다
            if layer.is_animating():
                layer.update_frame()
        if not self._layers:
            self._timer.stop()


_clock: _FrameClock | None = None


def frame_clock() -> _FrameClock:
    global _clock
    if _clock is None or not shiboken6.isValid(_clock):
        _clock = _FrameClock()
    return _clock


# ── 레이어 ──────────────────────────────────────────────────────────

class DecorationLayer(QWidget):
    """부모 전체를 덮는 마우스 투과 장식 레이어. surface는 holiday_decor.SURFACES 중 하나다."""

    def __init__(self, surface: str, parent: QWidget):
        if surface not in hd.SURFACES:
            raise ValueError(f"알 수 없는 장식 표면: {surface}")
        super().__init__(parent)
        self.setObjectName("holidayDecor")
        self._surface = surface
        self._key: str | None = None
        self._decor: hd.SurfaceDecor | None = None
        self._has_motion = False
        self._paused = False
        self._motion_ok = True
        self._running = False
        self._elapsed = 0.0          # 멈춘 구간을 뺀 누적 초
        self._run_since = 0.0
        self._anchors: dict[str, float] = {}
        self._radii = (0.0, 0.0, 0.0, 0.0)   # 왼쪽 위·오른쪽 위·오른쪽 아래·왼쪽 아래
        self._band_h: float | None = None
        self._blockers: list[tuple[float, float, float, float]] = []
        self._hat_offset = 0.0
        self._sync_callback = None
        self._window = None
        self._dpr = 0.0
        self._renderers: dict[str, QSvgRenderer] = {}
        self._pixmaps: dict[tuple, QPixmap] = {}
        self._particle_stamp: tuple | None = None
        self._particle_sets: list[tuple[hd.Particles, tuple[hd.Particle, ...]]] = []

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)
        self.lower()
        self.hide()

    # ── 설정 ────────────────────────────────────────────────────────

    def surface(self) -> str:
        return self._surface

    def theme_key(self) -> str | None:
        """지금 입은 테마 키. 그릴 것이 없으면 None."""
        return self._key

    def set_theme(self, key: str | None) -> None:
        """테마를 바꾼다. key가 없거나 이 표면에 그릴 것이 없으면 숨는다. 같은 값이면 아무것도 하지 않는다."""
        decor = hd.DECOR.get(key, {}).get(self._surface) if key else None
        if decor is not None and not (decor.base or decor.sprites or decor.particles or decor.badges):
            decor = None
        new_key = key if decor is not None else None
        if new_key != self._key:
            self._key = new_key
            self._decor = decor
            self._has_motion = decor is not None and (
                bool(decor.particles) or any(s.motion for s in decor.sprites))
            self._elapsed = 0.0                       # 새 테마는 첫 장면부터
            self._run_since = time.monotonic()
            self._pixmaps.clear()
            self._particle_stamp = None
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.setVisible(self._decor is not None)
        self.sync_animation()
        self.update()

    def set_paused(self, paused: bool) -> None:
        """잠금 같은 때 움직임을 멈추거나 이어 간다. 그림은 그대로 두고 시간만 선다."""
        paused = bool(paused)
        if paused != self._paused:
            self._paused = paused
        self.sync_animation()

    def is_paused(self) -> bool:
        return self._paused

    def set_anchors(self, anchors: dict[str, float]) -> None:
        """실제 기준점(px). 이름은 left_gap·center·right_gap·right. 빠진 이름은 기본 크기 값에 비율을 곱해 쓴다."""
        new = {name: float(value) for name, value in anchors.items()}
        if new != self._anchors:
            self._anchors = new
            self.update()

    def anchors(self) -> dict[str, float]:
        """지금 쓰는 기준점(없는 이름은 기본 크기 값에 폭 비율을 곱해 채운다)."""
        sx = self._virtual_width() / hd.DESIGN_SIZE[self._surface][0]
        merged = {name: ref * sx for name, ref in hd.ANCHOR_REF[self._surface].items()}
        merged.update(self._anchors)
        return merged

    def set_corner_radii(self, top_left: float, top_right: float,
                         bottom_right: float = 0.0, bottom_left: float = 0.0) -> None:
        """부모의 둥근 모서리에 맞춰 장식을 잘라 낸다."""
        radii = (float(top_left), float(top_right), float(bottom_right), float(bottom_left))
        if radii != self._radii:
            self._radii = radii
            self.update()

    def set_band_height(self, height: float | None) -> None:
        """실제 띠 높이. 디자인 높이와 다르면 map_band_y 규칙으로 세로 위치를 맞춘다(스티키 띠)."""
        value = float(height) if height else None
        if value != self._band_h:
            self._band_h = value
            self.update()

    def set_blockers(self, rects) -> None:
        """버튼·글자가 있는 자리(부모 좌표 (x, y, w, h) 목록). 장식은 이 자리를 피하거나 줄거나 빠진다."""
        new = [tuple(float(v) for v in r) for r in rects]
        if new != self._blockers:
            self._blockers = new
            self.update()

    def set_hat_offset(self, units: float) -> None:
        """hat 표면: 모자 그림을 아래로 내린 값(디자인 단위). 모자 SVG와 같은 만큼 스프라이트도 내린다."""
        if float(units) != self._hat_offset:
            self._hat_offset = float(units)
            self.update()

    def set_geometry_sync(self, callback) -> None:
        """부모가 크기를 바꾸거나 배치될 때마다 부르는 함수(기준점·모서리 갱신용)를 등록한다."""
        self._sync_callback = callback
        self._run_sync()

    def _run_sync(self) -> None:
        if self._sync_callback is not None:
            self._sync_callback()

    def update_frame(self) -> None:
        """움직임 한 프레임. 실제로 그리는 띠 높이까지만 다시 그리게 한다.

        머리줄 레이어는 검색 줄까지 부모를 덮지만 장식은 위쪽 막대 행에만 있다. 전체를 다시 그리게 하면
        부모와 그 위 버튼들이 안 그려지는 영역까지 프레임마다 다시 그려진다.
        """
        if self._surface == "hat":
            self.update()
            return
        band = self._band_h or hd.DESIGN_SIZE[self._surface][1]
        self.update(0, 0, self.width(), min(self.height(), int(math.ceil(band))))

    def is_animating(self) -> bool:
        """타이머를 돌려 움직이는 중이면 True."""
        return self._running

    def elapsed(self) -> float:
        """움직이기 시작한 뒤 경과 초(멈춘 구간 제외)."""
        if self._running:
            return self._elapsed + (time.monotonic() - self._run_since)
        return self._elapsed

    # ── 움직임 켜고 끄기 ────────────────────────────────────────────

    def _wants_motion(self) -> bool:
        if self._decor is None or not self._has_motion or self._paused or not self.isVisible():
            return False
        window = self.window()
        if window is not None and window.isMinimized():
            return False
        return self._motion_ok

    def sync_animation(self) -> None:
        """지금 상태(보임·멈춤·최소화·Windows 설정)에 맞춰 타이머 가입을 맞춘다. 여러 번 불러도 안전하다."""
        self._motion_ok = motion_allowed()
        want = self._wants_motion()
        if want and not self._running:
            self._running = True
            self._run_since = time.monotonic()
            frame_clock().add(self)
        elif not want and self._running:
            self._stop()

    def _stop(self) -> None:
        if self._running:
            self._elapsed += time.monotonic() - self._run_since
            self._running = False
        if _clock is not None and shiboken6.isValid(_clock):
            _clock.discard(self)

    def showEvent(self, event):
        super().showEvent(event)
        window = self.window()
        if window is not self._window:
            if self._window is not None and shiboken6.isValid(self._window):
                self._window.removeEventFilter(self)
            self._window = window
            if window is not None and window is not self.parentWidget():
                window.installEventFilter(self)
        self.sync_animation()

    def hideEvent(self, event):
        self._stop()  # 이 시점에는 isVisible()이 이미 False이므로 판정 없이 바로 멈춘다
        super().hideEvent(event)

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Type.WindowStateChange and (obj is self._window or obj is self.parentWidget()):
            self.sync_animation()  # 최소화·복원
        elif obj is self.parentWidget():
            if et == QEvent.Type.Resize:
                self.setGeometry(obj.rect())
                self._run_sync()
            elif et in (QEvent.Type.Show, QEvent.Type.LayoutRequest, QEvent.Type.DynamicPropertyChange):
                self._run_sync()
        return False

    # ── 그리기 ──────────────────────────────────────────────────────

    def _scale(self) -> float:
        """hat은 100 단위 폭을 실제 폭에 맞춰 균등 배율로 그린다. 나머지는 1."""
        return self.width() / 100.0 if self._surface == "hat" else 1.0

    def _virtual_width(self) -> float:
        k = self._scale()
        return self.width() / k if k else float(self.width())

    def _pixmap(self, asset: str, w: float, h: float, k: float) -> QPixmap | None:
        """asset을 (w x h)*k 논리 px로 한 번 그려 둔 QPixmap(레이어마다 캐시)."""
        dpr = self._dpr
        key = (asset, round(w * k * dpr), round(h * k * dpr))
        pix = self._pixmaps.get(key)
        if pix is None:
            renderer = _renderer_for(self._renderers, asset)
            if renderer is None:
                return None
            pix = _blank_pixmap(w * k, h * k, dpr)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, pix.width() / dpr, pix.height() / dpr))
            painter.end()
            self._pixmaps[key] = pix
        return pix

    def _base_pixmap(self, decor: hd.SurfaceDecor, width: float, height: float) -> QPixmap | None:
        """base 한 장(늘리기) 또는 조각 되풀이(base_tile)를 표면 크기 한 장으로 합쳐 캐시한다."""
        dpr = self._dpr
        key = ("base", decor.base, round(width * dpr), round(height * dpr))
        pix = self._pixmaps.get(key)
        if pix is not None:
            return pix
        renderer = _renderer_for(self._renderers, decor.base)
        if renderer is None:
            return None
        pix = _blank_pixmap(width, height, dpr)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if decor.base_tile > 0:
            # 조각 경계를 기기 픽셀에 맞춰(125%·150% 배율에서 이음매가 비치지 않게) 누적 오차 없이 놓는다.
            count = math.ceil(width / decor.base_tile)
            for i in range(count):
                x0 = round(i * decor.base_tile * dpr) / dpr
                x1 = round((i + 1) * decor.base_tile * dpr) / dpr
                renderer.render(painter, QRectF(x0, 0, x1 - x0, height))
        else:
            renderer.render(painter, QRectF(0, 0, width, height))
        painter.end()
        self._pixmaps[key] = pix
        return pix

    def _particles(self, width: float) -> list[tuple[hd.Particles, tuple[hd.Particle, ...]]]:
        stamp = (self._key, round(width))
        if stamp != self._particle_stamp:
            self._particle_sets = [
                (spec, hd.place_particles(scaled_particles(spec, width, self._surface)))
                for spec in self._decor.particles
            ]
            self._particle_stamp = stamp
        return self._particle_sets

    def paintEvent(self, event):
        decor = self._decor
        if decor is None or self.width() <= 0 or self.height() <= 0:
            return
        dpr = self.devicePixelRatioF()
        if dpr != self._dpr:
            self._pixmaps.clear()
            self._dpr = dpr
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        k = self._scale()
        vw = self._virtual_width()
        design_h = hd.DESIGN_SIZE[self._surface][1]
        band_h = self._band_h or design_h
        t = self.elapsed()

        # 표면 사각형으로 자른다(해·달·빛줄기가 면 밖으로 나가고, 부모의 둥근 모서리도 따른다).
        if self._surface == "hat":
            clip_h = float(self.height())
        else:
            clip_h = min(float(self.height()), float(band_h))
        tl, tr, br, bl = self._radii
        painter.setClipPath(_rounded_path(self.width(), clip_h, tl, tr, br, bl))
        if self._surface == "hat":
            painter.scale(k, k)
            painter.translate(0, self._hat_offset)

        anchors = self.anchors()
        if decor.base:
            self._paint_base(painter, decor, vw, band_h)
        for sprite, rect in self._visible_sprites(decor, anchors, vw):
            self._paint_sprite(painter, sprite, rect, k, t)
        for _spec, items in self._particles(vw):
            for item in items:
                self._paint_particle(painter, item, anchors, vw, t)
        for badge in decor.badges:
            x, y, w, h = resolve_rect(self._surface, badge.rect, badge.anchor, anchors, vw)
            _draw_badge(painter, badge, QRectF(x, map_band_y(self._surface, y, h, self._band_h), w, h))
        painter.end()

    def _paint_base(self, painter, decor, vw, band_h) -> None:
        pix = self._base_pixmap(decor, vw, band_h)
        if pix is not None:
            painter.drawPixmap(QRectF(0, 0, vw, band_h), pix, QRectF(pix.rect()))

    def _sprite_rect(self, sprite, anchors, vw):
        """(x, y, w, h)를 실제 값으로. 버튼·글자 자리와 겹치면 줄이거나 옮기고, 안 되면 None(그리지 않는다)."""
        x, y, w, h = resolve_rect(self._surface, sprite.rect, sprite.anchor, anchors, vw)
        y, h = map_band_span(self._surface, (x, y, w, h), self._band_h)
        rect = (x, y, w, h)
        if self._blockers and not is_backdrop(self._surface, sprite.rect[2]):
            slid = slide_below(rect, self._blockers, self._band_h or hd.DESIGN_SIZE[self._surface][1])
            return None if slid is None else fit_clear(slid, self._blockers)
        return rect

    def _visible_sprites(self, decor, anchors, vw):
        """그릴 조각과 실제 rect를 튜플 순서대로. follows 조각은 다음 조각이 그려질 때만 남는다."""
        rects = [self._sprite_rect(s, anchors, vw) for s in decor.sprites]
        shown = [False] * len(rects)
        for i in range(len(rects) - 1, -1, -1):
            shown[i] = rects[i] is not None and (
                not decor.sprites[i].follows or (i + 1 < len(rects) and shown[i + 1]))
        return [(s, r) for s, r, ok in zip(decor.sprites, rects, shown) if ok]

    def _paint_sprite(self, painter, sprite, rect, k, t) -> None:
        x, y, w, h = rect
        pix = self._pixmap(sprite.asset, w, h, k)
        if pix is None:
            return
        if sprite.motion is None:
            state = hd.MotionState()
        else:
            at = t
            if not self._motion_ok and sprite.once:
                at = sprite.period + max(0.0, sprite.phase)   # Windows 애니메이션 끔: 떠오른 모습
            state = hd.motion_state(sprite.motion, at, sprite.period, sprite.phase, sprite.once)
        painter.save()
        ox, oy = x + w * sprite.origin[0], y + h * sprite.origin[1]
        painter.translate(ox + state.dx, oy + state.dy)
        painter.rotate(state.angle)
        painter.scale(state.scale * state.scale_x, state.scale)
        painter.translate(-ox, -oy)
        painter.setOpacity(max(0.0, min(1.0, state.opacity)))
        painter.drawPixmap(QRectF(x, y, w, h), pix, QRectF(pix.rect()))
        painter.restore()

    def _paint_particle(self, painter, item, anchors, vw, t) -> None:
        px, py, opacity = hd.particle_pose(item, t)
        x = resolve_rect(self._surface, (px, 0.0, 0.0, 0.0), item.anchor, anchors, vw)[0]
        if item.kind == "snow":
            # 눈은 한 바퀴 내내 이어서 움직이므로 띠 높이에 비례해 줄인다(띠 아래 끝까지 내려온다).
            y = py * (self._band_h / hd.DESIGN_SIZE[self._surface][1]) if self._band_h else py
        else:
            # 떠오르는 자모·반짝이는 별은 놓인 자리(item.y)로 띠 안의 위치를 정하고 움직임은 그대로 더한다.
            y = py + map_band_y(self._surface, item.y, item.size, self._band_h) - item.y
        opacity = max(0.0, min(1.0, opacity))
        if opacity <= 0.0:
            return
        # 반짝이·자모는 손으로 놓은 점이라 버튼·글자 위에 놓이면 그리지 않는다(눈은 지나가는 점이라 그대로).
        if item.kind != "snow" and self._blockers:
            box = (x, y, item.size, item.size)
            if any(_overlaps(box, b) for b in self._blockers):
                return
        color = QColor(item.color)
        painter.save()
        painter.setOpacity(opacity)
        if item.kind == "snow":
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x, y, item.size, item.size))
        elif item.kind == "stars":
            scale = item.size / 10.0
            polygon = QPolygonF([QPointF(x + sx * scale, y + sy * scale) for sx, sy in _STAR_POINTS])
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(polygon)
        else:  # jamo: 시안의 line-height 1(글자 높이 = 글자 크기)에 맞춘다
            font = QFont(_FONT_FAMILY)
            font.setPixelSize(round(item.size))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(color)
            lead = (QFontMetricsF(font).height() - item.size) / 2
            painter.drawText(QRectF(x, y - lead, item.size * 2, item.size * 2),
                             Qt.AlignLeft | Qt.AlignTop, item.char)
        painter.restore()
