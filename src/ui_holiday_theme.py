"""공휴일 테마 컨트롤러(v4.6).

오늘 입을 테마를 판정해 화면에 알리는 Qt 객체다. 판정 규칙·색표는 holiday_theme.py에 있고,
여기서는 설정 스위치를 읽어 '지금 테마가 있는가'만 정한다. 테마는 화면 전용이라
이 모듈은 DB에 아무것도 쓰지 않는다(설정 읽기만).

- themeChanged(match): 보이는 테마가 달라졌을 때만 보낸다. match는 HolidayThemeMatch 또는 None.
- pausedChanged(paused): 잠금·숨김 같은 때 장식 움직임을 멈추라는 신호(Task 6 이후 연결).
"""
from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

import database as db
import holiday_theme  # 모듈 속성으로 부른다: holiday_theme.current_match()
from app_paths import resource_root

_logger = logging.getLogger(__name__)

# 토마토 모자 그림. SVG 좌표계는 토마토 그림 상자를 0~100으로 보고, 모자가 상자 위로
# 최대 25단위 나가므로 위쪽 30단위를 더 잡는다(viewBox x y w h).
HAT_VIEWBOX = (0, -30, 100, 130)
# 시안에서 모자 층을 아래로 내린 값(단위). 토마토 그림마다 머리 위치가 달라 따로 맞춘다.
HAT_OFFSET_UNITS = {"tomato.png": 8, "tomato_mini.png": 13}


def hat_pixmap(key: str, box: int, offset_units: float, dpr: float) -> QPixmap:
    """테마 `key`의 토마토 모자를 투명 바탕 QPixmap 한 장에 그린다(화면 전용).

    논리 크기는 `box × round(box * 1.3)`이고 토마토 상자의 위쪽 끝이 픽스맵 y = 0.3 * box다.
    모자를 `offset_units * box / 100`만큼 아래로 내려 그리며, 상자 밖(머리 위)까지 그리려고
    상자보다 위로 0.3 * box만큼 더 큰 한 장으로 만든다. 그림이 없거나 읽지 못하면
    같은 크기의 빈(투명) 그림을 돌려준다(꾸미기일 뿐이라 화면을 막지 않는다).
    """
    dpr = max(float(dpr), 1.0)
    height = round(box * HAT_VIEWBOX[3] / HAT_VIEWBOX[2])
    pix = QPixmap(round(box * dpr), round(height * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    path = resource_root() / "resources" / "holiday_themes" / key / "hat.svg"
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        _logger.warning("토마토 모자 그림을 읽지 못함: %s", key)
        return pix
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    # viewBox 전체(100×130단위)를 box×(1.3*box) 논리 픽셀에 대고, 모자 층만 아래로 내린다.
    target = QRectF(0.0, offset_units * box / 100.0, float(box), box * HAT_VIEWBOX[3] / HAT_VIEWBOX[2])
    renderer.render(painter, target)
    painter.end()
    return pix


class HolidayThemeController(QObject):
    """테마 판정 결과를 쥐고, 바뀔 때만 신호로 알린다."""

    themeChanged = Signal(object)  # HolidayThemeMatch | None
    pausedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._match: holiday_theme.HolidayThemeMatch | None = None
        self._paused = False

    @staticmethod
    def _state_of(match):
        """같은 테마·같은 기간·같은 인사말 상태이면 같은 값이다."""
        if match is None:
            return None
        return (match.theme.key, match.first_day, match.last_day, match.in_holiday)

    @staticmethod
    def _enabled() -> bool:
        """설정 스위치. 키가 없으면 켜짐이다."""
        return db.get_setting(db.SETTING_HOLIDAY_THEME_ENABLED, "1") == "1"

    def refresh(self) -> None:
        """설정과 오늘 날짜로 다시 판정한다. 달라졌을 때만 themeChanged를 보낸다.

        설정을 읽지 못하면 지금 화면을 그대로 둔다(테마는 꾸미기일 뿐이라 오류를 키우지 않는다).
        """
        try:
            enabled = self._enabled()
        except (sqlite3.Error, OSError) as exc:
            _logger.warning("공휴일 테마 설정 읽기 실패: %s", type(exc).__name__)
            return
        match = holiday_theme.current_match() if enabled else None
        changed = self._state_of(match) != self._state_of(self._match)
        self._match = match
        if changed:
            self.themeChanged.emit(match)

    def match(self):
        """지금 입은 테마 판정 결과. 없으면 None."""
        return self._match

    def theme(self):
        """지금 입은 HolidayTheme. 없으면 None."""
        return self._match.theme if self._match is not None else None

    def set_paused(self, paused: bool) -> None:
        """장식 움직임을 멈추거나 이어 간다. 같은 값이면 다시 알리지 않는다."""
        paused = bool(paused)
        if paused == self._paused:
            return
        self._paused = paused
        self.pausedChanged.emit(paused)

    def is_paused(self) -> bool:
        return self._paused
