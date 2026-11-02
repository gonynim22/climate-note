"""v4.6 공휴일 테마: 장식 정의와 움직임(Task 6a, Qt 없는 순수 모듈).

시안(mockup-scene.dc.html)의 keyframes 값, 13개 키의 장식 표, 장식 SVG 자원(QtSvg Tiny),
입자 배치의 결정성을 확인한다. 화면(DecorationLayer)은 6b가 따로 검사한다.
"""
from pathlib import Path

import pytest
from PySide6.QtSvg import QSvgRenderer

import holiday_decor as hd
from app_paths import resource_root
from holiday_decor import (
    ANCHOR_REF,
    DECOR,
    DESIGN_SIZE,
    MOTION_KINDS,
    STICKER_BADGES,
    STICKER_DESIGN,
    SURFACES,
    Badge,
    Particles,
    SurfaceDecor,
    motion_state,
    particle_pose,
    place_particles,
    referenced_assets,
    sticker_asset,
)
from holiday_theme import THEME_KEYS, THEMES

_ROOT = resource_root() / "resources" / "holiday_themes"
# Tiny 범위 밖(필터·clipPath·마스크·CSS·외부 참조·비트맵)은 Qt에서 그려지지 않는다.
_BANNED = ("<text", "filter", "clipPath", "mask", "paint-order", "style=", "<image",
           "<style", "href", "<use", "url(")
_SURFACE_KEYS = ("header", "dday", "sticky_band")


def approx(value, expected=None, tol=1e-6):
    return value == pytest.approx(expected, abs=tol)


# ── 움직임: 시안 keyframes ──────────────────────────────────────────

def test_motion_keyframes_match_mockup():
    p = 2.0
    # swing: -7° → 7° (교대 반복): 0이면 -7, period면 7, 2·period면 다시 -7
    assert approx(motion_state("swing", 0, p).angle, -7)
    assert approx(motion_state("swing", p, p).angle, 7)
    assert approx(motion_state("swing", 2 * p, p).angle, -7)
    assert approx(motion_state("swing", p / 2, p).angle, 0)  # ease-in-out은 중간이 대칭
    # sway ±4°, wave -9° → 7°
    assert approx(motion_state("sway", 0, p).angle, -4)
    assert approx(motion_state("sway", p, p).angle, 4)
    assert approx(motion_state("wave", 0, p).angle, -9)
    assert approx(motion_state("wave", p, p).angle, 7)
    # kite: (dx, dy, angle) (0, 0, -8) → (-6, 4, 4)
    k0, k1 = motion_state("kite", 0, p), motion_state("kite", p, p)
    assert (k0.dx, k0.dy, k0.angle) == (0, 0, -8)
    assert approx(k1.dx, -6) and approx(k1.dy, 4) and approx(k1.angle, 4)
    # rise(once): dy 16 → 0, period 뒤로는 계속 0
    assert approx(motion_state("rise", 0, p, once=True).dy, 16)
    assert approx(motion_state("rise", p, p, once=True).dy, 0)
    assert approx(motion_state("rise", 5 * p, p, once=True).dy, 0)
    mid = motion_state("rise", p / 2, p, once=True).dy
    assert 0 < mid < 8  # ease-out: 절반 시각에 이미 절반보다 많이 올라와 있다
    # glow: 투명도 0.16 → 0.45, 배율 0.9 → 1.08
    g0, g1 = motion_state("glow", 0, p), motion_state("glow", p, p)
    assert approx(g0.opacity, 0.16) and approx(g0.scale, 0.9)
    assert approx(g1.opacity, 0.45) and approx(g1.scale, 1.08)
    # twinkle: 투명도 0.25 → 1
    assert approx(motion_state("twinkle", 0, p).opacity, 0.25)
    assert approx(motion_state("twinkle", p, p).opacity, 1)
    # spin: 선형 360°
    assert approx(motion_state("spin", 0, p).angle, 0)
    assert approx(motion_state("spin", p / 2, p).angle, 180)
    assert approx(motion_state("spin", p * 1.25, p).angle, 90)
    # bob: dy 0 → -4, drift: dx -6 → 6
    assert approx(motion_state("bob", 0, p).dy, 0)
    assert approx(motion_state("bob", p, p).dy, -4)
    assert approx(motion_state("drift", 0, p).dx, -6)
    assert approx(motion_state("drift", p, p).dx, 6)
    # steam: 0이면 dy 4·투명도 0, 0.4·period면 투명도 0.85, period 직전 dy ≈ -8·투명도 ≈ 0
    s0 = motion_state("steam", 0, p)
    assert approx(s0.dy, 4) and approx(s0.opacity, 0)
    assert approx(motion_state("steam", 0.4 * p, p).opacity, 0.85)
    end = motion_state("steam", p * (1 - 1e-6), p)
    assert approx(end.dy, -8, 1e-3) and approx(end.opacity, 0, 1e-3)
    # prop: period/2에서 scale_x 0.15, 양 끝은 1 (선형)
    assert approx(motion_state("prop", 0, p).scale_x, 1)
    assert approx(motion_state("prop", p / 2, p).scale_x, 0.15)
    assert approx(motion_state("prop", p / 4, p).scale_x, 0.575)  # 선형
    # float: 0%·100% 투명도 0, 25~75%는 1(Particles 값이 곱해진다), dy 14 → -22
    f0 = motion_state("float", 0, p)
    assert approx(f0.opacity, 0) and approx(f0.dy, 14)
    assert approx(motion_state("float", 0.25 * p, p).opacity, 1)
    assert approx(motion_state("float", 0.5 * p, p).opacity, 1)
    assert approx(motion_state("float", 0.75 * p, p).opacity, 1)
    assert approx(motion_state("float", p * (1 - 1e-6), p).opacity, 0, 1e-3)
    assert approx(motion_state("float", p * (1 - 1e-6), p).dy, -22, 1e-3)
    # snow: 선형 진행률 0 → 1을 dx·dy에 담는다(호출 측이 입자별 거리를 곱한다)
    assert approx(motion_state("snow", 0, p).dy, 0)
    assert approx(motion_state("snow", p / 4, p).dy, 0.25)
    assert approx(motion_state("snow", p / 4, p).dx, 0.25)
    assert approx(motion_state("snow", p * 1.5, p).dy, 0.5)  # 한 바퀴 돌고 다시 위에서


def test_motion_phase_is_css_negative_delay():
    """phase는 CSS animation-delay 그대로다: t_eff = t - phase. 음수면 이미 진행된 상태로 시작."""
    p = 2.0
    # 시안 sway2: 2.7s, -1.1s → t=0에서 이미 1.1초 진행
    assert approx(motion_state("swing", 0, p, phase=-p).angle, 7)  # 한 주기 앞섬
    a = motion_state("swing", 0, p, phase=-0.5).angle
    b = motion_state("swing", 0.5, p).angle
    assert approx(a, b)
    # 양수 delay는 시작 전까지 첫 장면(t_eff<0은 0으로 고정)
    assert approx(motion_state("swing", 0.3, p, phase=1.0).angle, -7)
    # steam 세 줄기는 0 / -0.9 / -1.7 위상이 서로 달라 투명도가 다르다
    ops = {round(motion_state("steam", 0.2, 2.6, phase=ph).opacity, 3) for ph in (0, -0.9, -1.7)}
    assert len(ops) == 3


def test_motion_once_clamps_and_non_once_loops():
    p = 2.0
    assert approx(motion_state("swing", 7 * p, p, once=True).angle, 7)  # 끝 상태에 머문다
    assert approx(motion_state("spin", 3 * p, p, once=True).angle, 360)
    assert approx(motion_state("spin", 3.5 * p, p).angle, 180)  # once가 아니면 계속 돈다
    assert approx(motion_state("rise", 1.5 * p, p).dy, motion_state("rise", 0.5 * p, p).dy)  # once가 아니면 되풀이


def test_motion_state_rejects_bad_input():
    with pytest.raises(ValueError):
        motion_state("nope", 0, 1)
    with pytest.raises(ValueError):
        motion_state("swing", 0, 0)


# ── 장식 표 ─────────────────────────────────────────────────────────

def test_constants():
    assert SURFACES == ("header", "dday", "sticky_band", "hat")
    assert DESIGN_SIZE == {"header": (380, 70), "dday": (220, 95),
                           "sticky_band": (220, 30), "hat": (100, 130)}
    assert ANCHOR_REF["header"] == {"full": 0.0, "left_gap": 77.0, "center": 190.0,
                                    "right_gap": 245.0, "right": 380.0,
                                    "span_l": 106.0, "span_r": 267.5}
    assert STICKER_DESIGN == 48


def test_decor_covers_all_themes():
    assert set(DECOR) == set(THEME_KEYS)
    for key in THEME_KEYS:
        for surface in _SURFACE_KEYS:
            assert isinstance(DECOR[key][surface], SurfaceDecor), (key, surface)
    assert isinstance(DECOR["children"]["hat"], SurfaceDecor)
    assert [s.motion for s in DECOR["children"]["hat"].sprites] == ["prop"]
    # 모자 장식은 어린이날만 갖는다
    assert all("hat" not in DECOR[k] for k in THEME_KEYS if k != "children")


def test_every_theme_has_visible_decoration_somewhere():
    for key in THEME_KEYS:
        assert DECOR[key]["header"] != SurfaceDecor(), key
        assert DECOR[key]["dday"] != SurfaceDecor(), key
        # 설날 스티키 띠는 색동 바탕 자체가 장식이라 따로 그리지 않는다(Task 4가 칠한다)
        if key != "seollal":
            assert DECOR[key]["sticky_band"] != SurfaceDecor(), key


def test_memorial_has_no_motion():
    assert THEMES["memorial"].motion is False
    for surface in _SURFACE_KEYS:
        decor = DECOR["memorial"][surface]
        assert all(s.motion is None for s in decor.sprites), surface
        assert decor.particles == (), surface
    assert any(DECOR["memorial"][s].sprites or DECOR["memorial"][s].base for s in _SURFACE_KEYS)


def test_motion_themes_move_somewhere_except_static_ones():
    for key in THEME_KEYS:
        if key == "memorial":
            continue
        moving = any(
            any(s.motion for s in DECOR[key][surface].sprites) or DECOR[key][surface].particles
            for surface in _SURFACE_KEYS
        )
        assert moving, key


def test_sprites_use_known_motion_with_period():
    for key in THEME_KEYS:
        for surface, decor in DECOR[key].items():
            for sprite in decor.sprites:
                if sprite.motion is None:
                    continue
                assert sprite.motion in MOTION_KINDS, (key, surface, sprite)
                assert sprite.period > 0, (key, surface, sprite)
                assert 0.0 <= sprite.origin[0] <= 1.0 and 0.0 <= sprite.origin[1] <= 1.0
            for sprite in decor.sprites:
                assert sprite.anchor in ANCHOR_REF.get(surface, {"full": 0.0}), (key, surface, sprite)
    # 시안 anim(...) 인자 그대로 몇 가지를 고정한다
    ny = {s.asset: s for s in DECOR["newyear"]["header"].sprites}
    assert (ny["newyear/sun.svg"].motion, ny["newyear/sun.svg"].period, ny["newyear/sun.svg"].once) == ("rise", 3.5, True)
    assert (ny["newyear/halo.svg"].motion, ny["newyear/halo.svg"].period) == ("glow", 3.0)
    seol = {s.asset: s for s in DECOR["seollal"]["header"].sprites}
    assert (seol["seollal/pouch.svg"].motion, seol["seollal/pouch.svg"].period) == ("swing", 2.6)
    assert (seol["seollal/kite.svg"].motion, seol["seollal/kite.svg"].period) == ("kite", 3.8)
    lib = {s.asset: s for s in DECOR["liberation"]["header"].sprites}
    assert (lib["liberation/rays.svg"].motion, lib["liberation/rays.svg"].period) == ("spin", 80.0)
    steam = [s for s in DECOR["labor"]["header"].sprites if s.motion == "steam"]
    assert [(s.period, s.phase) for s in steam] == [(2.6, 0.0), (2.6, -0.9), (2.6, -1.7)]
    prop = DECOR["children"]["hat"].sprites[0]
    assert (prop.motion, prop.period) == ("prop", 0.45)


def test_sprite_absolute_positions_stay_on_the_surface():
    """anchor 기준 거리로 바꾼 rect가 디자인 면 안(조금 넘침은 허용)에 놓이는지 — 기준 계산 실수를 잡는다."""
    spill_ok = {"liberation/rays.svg"}  # 빛줄기는 면 밖까지 번져 면에서 잘린다
    for key in THEME_KEYS:
        for surface in _SURFACE_KEYS:
            width, height = DESIGN_SIZE[surface]
            for s in DECOR[key][surface].sprites:
                if s.asset in spill_ok:
                    continue
                x = s.rect[0] + ANCHOR_REF[surface][s.anchor]
                y, w, h = s.rect[1], s.rect[2], s.rect[3]
                assert -2 <= x and x + w <= width + 2, (key, surface, s.asset, x, w)
                assert -45 <= y and y <= height, (key, surface, s.asset, y)  # 달·해는 아래에서 떠오른다
                assert w > 0 and h > 0


def test_header_clear_zones_are_respected_for_gap_sprites():
    """left_gap·right_gap 기준 장식은 버튼 묶음이 아니라 빈 곳(x 77~135, 245~290) 쪽에 놓인다."""
    for key in THEME_KEYS:
        for s in DECOR[key]["header"].sprites:
            x = s.rect[0] + ANCHOR_REF["header"][s.anchor]
            if s.anchor == "right_gap":
                assert x >= 230, (key, s.asset, x)
            if s.anchor == "left_gap" and s.rect[1] < 46:  # 위쪽 막대 행(버튼이 있는 곳)
                assert x >= 77 - 40, (key, s.asset, x)


def test_samil_hand_flags_are_six_in_two_free_spans_and_never_shrink():
    flags = DECOR["samil"]["header"].sprites
    assert [s.anchor for s in flags] == ["span_l"] * 3 + ["span_r"] * 3
    assert all(s.asset == "samil/flag.svg" and s.motion == "wave" and s.min_scale == 1.0 for s in flags)
    assert len({(s.period, s.phase) for s in flags}) == 6                  # 번갈아 흔들린다
    for anchor in ("span_l", "span_r"):                                    # 빈 곳 가운데에서 -40·0·+40
        centers = sorted(s.rect[0] + s.rect[2] / 2 for s in flags if s.anchor == anchor)
        assert centers == [-40.0, 0.0, 40.0]
    # 기본값은 그대로: 다른 조각은 0.5까지 줄일 수 있다
    assert hd.Sprite("a.svg", (0, 0, 1, 1)).min_scale == 0.5
    assert all(s.min_scale == 0.5 for k in ("gaecheon", "chuseok") for s in DECOR[k]["header"].sprites)


def test_gaecheon_clouds_and_chuseok_grass_use_free_span_anchors():
    anchors = {}
    for key in ("gaecheon", "chuseok"):
        for s in DECOR[key]["header"].sprites:
            anchors.setdefault(s.asset, []).append(s.anchor)
    assert anchors["gaecheon/cloud_plain.svg"] == ["span_l", "span_r"]
    assert anchors["chuseok/susuki_l.svg"] == ["span_l"] and anchors["chuseok/susuki_r.svg"] == ["span_r"]


# ── 자원: Tiny SVG ──────────────────────────────────────────────────

def _viewbox(path: Path) -> tuple[float, float, float, float]:
    import re
    text = path.read_text(encoding="utf-8")
    m = re.search(r'viewBox="([^"]+)"', text)
    assert m, path
    vals = tuple(float(v) for v in m.group(1).replace(",", " ").split())
    assert len(vals) == 4, path
    return vals  # type: ignore[return-value]


def test_decor_assets_exist_and_are_tiny_svg():
    assets = referenced_assets()
    assert assets, "참조된 자원이 없다"
    for rel in sorted(assets | {sticker_asset(k) for k in THEME_KEYS}):
        path = _ROOT / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        for token in _BANNED:
            assert token not in text, (rel, token)
        assert QSvgRenderer(str(path)).isValid(), rel
        assert 'xmlns="http://www.w3.org/2000/svg"' in text, rel


def test_no_orphan_svg_files():
    """자원 폴더에는 참조되는 SVG(+모자·스티커)만 있다 — 안 쓰는 그림이 쌓이지 않게."""
    used = referenced_assets() | {sticker_asset(k) for k in THEME_KEYS} | {f"{k}/hat.svg" for k in THEME_KEYS}
    found = {p.relative_to(_ROOT).as_posix() for p in _ROOT.rglob("*.svg")}
    assert found == used, (sorted(found - used), sorted(used - found))
    assert {p.name for p in _ROOT.iterdir()} == set(THEME_KEYS)


def test_base_viewbox_matches_surface_or_tile():
    for key in THEME_KEYS:
        for surface in _SURFACE_KEYS:
            decor = DECOR[key][surface]
            if decor.base is None:
                assert decor.base_tile == 0.0
                continue
            vb = _viewbox(_ROOT / decor.base)
            width, height = DESIGN_SIZE[surface]
            assert vb[0] == 0 and vb[1] == 0, decor.base
            assert vb[3] == height, decor.base
            assert vb[2] == (decor.base_tile or width), decor.base


def test_sprite_viewbox_aspect_matches_rect():
    """스프라이트를 rect에 그릴 때 찌그러지지 않는다(viewBox 가로세로비 = rect 가로세로비)."""
    for key in THEME_KEYS:
        for surface, decor in DECOR[key].items():
            for s in decor.sprites:
                vb = _viewbox(_ROOT / s.asset)
                assert (vb[2] / vb[3]) == pytest.approx(s.rect[2] / s.rect[3], rel=0.04), (key, surface, s.asset, vb, s.rect)


def test_sticker_svgs_use_48_viewbox_and_have_white_outline_shapes():
    for key in THEME_KEYS:
        vb = _viewbox(_ROOT / sticker_asset(key))
        assert vb == (0, 0, STICKER_DESIGN, STICKER_DESIGN), key
        text = (_ROOT / sticker_asset(key)).read_text(encoding="utf-8")
        assert "#FFFFFF" in text, key  # 스티커 흰 테두리(paint-order 대신 흰 도형을 먼저 그린다)


def test_sticker_badges_only_for_lettered_stickers():
    assert set(STICKER_BADGES) == {"hangul", "constitution"}
    for key, badges in STICKER_BADGES.items():
        assert badges and all(isinstance(b, Badge) for b in badges)
        for b in badges:
            x, y, w, h = b.rect
            assert 0 <= x and 0 <= y and x + w <= STICKER_DESIGN and y + h <= STICKER_DESIGN, (key, b)
            assert b.fill == "", (key, b)  # 바탕은 sticker.svg가 그리고 Badge는 글자만
            assert b.text.replace("\n", "") in {"한글", "헌법"}


def test_header_and_dday_badges_are_hangul_stamp_only():
    stamp = DECOR["hangul"]["header"].badges
    assert [b.text for b in stamp] == ["한"] and stamp[0].fill == "#B5443B"
    assert [b.text for b in DECOR["hangul"]["dday"].badges] == ["한"]
    for key in THEME_KEYS:
        if key != "hangul":
            for surface in _SURFACE_KEYS:
                assert DECOR[key][surface].badges == (), (key, surface)


# ── 입자 ────────────────────────────────────────────────────────────

def test_particles_are_deterministic():
    p = Particles("snow", 26, (0, 0, 380, 70), (2, 4.5), "#FFFFFF", seed=11)
    assert place_particles(p) == place_particles(p)
    other = Particles("snow", 26, (0, 0, 380, 70), (2, 4.5), "#FFFFFF", seed=12)
    assert place_particles(p) != place_particles(other)
    assert len(place_particles(p)) == 26
    # DECOR 안의 모든 입자도 두 번 불러 같다
    for key in THEME_KEYS:
        for surface in _SURFACE_KEYS:
            for ps in DECOR[key][surface].particles:
                assert place_particles(ps) == place_particles(ps)


def test_snow_placement_stays_inside_area_and_moves_linearly():
    p = Particles("snow", 40, (0, 0, 380, 70), (2, 4.5), "#FFFFFF", seed=7)
    flakes = place_particles(p)
    for f in flakes:
        assert 0 <= f.x <= 380 - 4 + 1e-9
        assert 2 <= f.size <= 4.5
        assert 5 <= f.period <= 9 and -9 <= f.phase <= 0
        assert 0.45 <= f.alpha <= 0.95
        assert f.y_from < 0 and f.y_to > 70  # 면 위에서 시작해 아래로 빠진다
    f = flakes[0]
    # 진행률 0.2·0.4·0.6 시점(한 바퀴 안): y는 시간에 대해 선형이다
    ys = [particle_pose(f, f.period * (2 + frac) + f.phase)[1] for frac in (0.2, 0.4, 0.6)]
    assert (ys[1] - ys[0]) == pytest.approx(ys[2] - ys[1], abs=1e-9)
    assert ys[2] > ys[1] > ys[0]  # 아래로 내려간다
    assert particle_pose(f, f.period * 2 + f.phase)[1] == pytest.approx(f.y_from)  # 진행률 0은 면 위
    assert particle_pose(f, f.period * 2 + f.phase)[2] == pytest.approx(f.alpha)


def test_jamo_and_stars_particles():
    jamo = [ps for ps in DECOR["hangul"]["header"].particles if ps.kind == "jamo"]
    assert "".join(ps.chars for ps in jamo) == "ㄱㅎㅏㄴㅇ"
    placed = [pt for ps in jamo for pt in place_particles(ps)]
    assert len(placed) == 5 and {pt.char for pt in placed} == set("ㄱㅎㅏㄴㅇ")
    assert len({pt.phase for pt in placed}) > 1  # 글자마다 위상이 달라 한꺼번에 오르내리지 않는다
    for pt in placed:
        assert pt.period in (6.0, 7.0, 8.0) and -6.5 <= pt.phase <= 0 and 13 <= pt.size <= 15
        x, y, a = particle_pose(pt, 0.0)
        assert 0.0 <= a <= 0.55 + 1e-9  # float: 0%는 투명
        mid = particle_pose(pt, pt.period * 0.5 + pt.phase + 2 * pt.period)  # 한 주기 중 50% 시점(t_eff = t - phase)
        assert mid[2] == pytest.approx(0.55)
    stars = [ps for key in ("chuseok", "newyear", "constitution") for sf in _SURFACE_KEYS
             for ps in DECOR[key][sf].particles if ps.kind == "stars"]
    assert stars
    for ps in stars:
        for pt in place_particles(ps):
            assert 1.5 <= pt.period <= 2.7 and -1.6 <= pt.phase <= 0
            op = particle_pose(pt, 0.0)[2]
            assert 0.25 - 1e-9 <= op <= 1.0


def test_snow_only_in_christmas():
    for key in THEME_KEYS:
        kinds = {ps.kind for sf in _SURFACE_KEYS for ps in DECOR[key][sf].particles}
        if key == "christmas":
            assert "snow" in kinds
        else:
            assert "snow" not in kinds, key
    assert sum(ps.count for ps in DECOR["christmas"]["header"].particles) == 26
    assert sum(ps.count for ps in DECOR["christmas"]["dday"].particles) == 9


def test_module_has_no_qt_imports():
    source = Path(hd.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source and "import database" not in source
