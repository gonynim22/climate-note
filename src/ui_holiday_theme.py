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

from PySide6.QtCore import QObject, Signal

import database as db
import holiday_theme  # 모듈 속성으로 부른다: holiday_theme.current_match()

_logger = logging.getLogger(__name__)


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
