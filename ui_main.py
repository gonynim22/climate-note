import sys
import sqlite3
import logging
import calendar
from datetime import date, datetime

_logger = logging.getLogger("app_error")

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QListWidget, QListWidgetItem, QApplication, QLabel,
    QSizePolicy, QLineEdit, QPushButton, QDialog, QFileDialog, QInputDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QUrl, QPoint, QRectF
from PySide6.QtGui import QFont, QDesktopServices, QPainter, QBrush, QPen, QColor

import ctypes
from ctypes import wintypes

# ─── Windows 메시지 상수 ───────────────────────────────────────
WM_POWERBROADCAST = 0x0218
PBT_APMRESUMESUSPEND = 0x0007
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_UNLOCK = 0x0008


def _snap_px_for_screen(screen) -> int:
    """Return the 5mm snap size for a screen."""
    try:
        dpi = screen.physicalDotsPerInch()
    except (AttributeError, RuntimeError):
        dpi = 96
    return max(1, round(dpi * 5 / 25.4))


def _opacity_factor(value: str) -> float:
    """설정 문자열을 setWindowOpacity용 0.30~1.00 배율로 변환."""
    try:
        pct = int(str(value).strip())
    except (ValueError, TypeError):
        pct = 100
    pct = max(db.MIN_APP_OPACITY, min(100, pct))
    return pct / 100.0


def _detach_from_layout(widget) -> None:
    """위젯을 현재 부모 레이아웃에서 분리한다."""
    parent = widget.parentWidget()
    if parent is not None and parent.layout() is not None:
        parent.layout().removeWidget(widget)
    widget.setParent(None)


def _snap_not_past_right(value: int, snap: int) -> int:
    """Snap to the grid without moving a right-side boundary farther right."""
    return (value // snap) * snap


def _right_aligned_grid_x(right_edge: int, width: int, snap: int) -> int:
    """Return a snapped left x whose right edge does not pass right_edge."""
    return _snap_not_past_right(right_edge - width, snap)


def _clamp_window_pos(value: int, lower: int, upper: int) -> int:
    if upper < lower:
        return lower
    return max(lower, min(value, upper))


def _overlap(a, b):
    """AABB 엄격 겹침. 경계 접촉(공유 변)은 비겹침으로 본다."""
    return a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]


def _hard_violation(coords, items, cal, scr, clamped):
    """하드 제약 위반 검사. 위반 종류 문자열 또는 None.

    clamped>0(공간 부족으로 화면 안 강제 배치)일 때는 의도적 겹침이 허용되므로
    '상호 겹침' 검사를 면제하고, 캘린더 교차·화면 이탈만 본다.
    """
    rects = [(coords[i][0], coords[i][1],
              coords[i][0] + items[i][0], coords[i][1] + items[i][1])
             for i in range(len(items)) if coords[i] is not None]
    if clamped == 0:
        for a in range(len(rects)):
            for b in range(a + 1, len(rects)):
                if _overlap(rects[a], rects[b]):
                    return "mutual"
    for r in rects:
        if _overlap(r, cal):
            return "calendar"
    sl, st, sr, sb = scr
    for (x1, y1, x2, y2) in rects:
        if x1 < sl or y1 < st or x2 > sr or y2 > sb:
            return "offscreen"
    return None


def _snap_ceil(value: int, snap: int) -> int:
    return -((-value) // snap) * snap


def _snap_floor(value: int, snap: int) -> int:
    return (value // snap) * snap


def _snapped_values(lower: int, upper: int, snap: int, reverse: bool) -> list[int]:
    """Inclusive snapped coordinate values in [lower, upper]."""
    start = _snap_ceil(lower, snap)
    end = _snap_floor(upper, snap)
    if start > end:
        return []
    if reverse:
        return list(range(end, start - snap, -snap))
    return list(range(start, end + snap, snap))


def _free_rects_around_calendar(cal, scr, gap: int):
    """Return non-overlapping free rectangles after expanding the calendar by gap."""
    scr_l, scr_t, scr_r, scr_b = scr
    cal_l, cal_t, cal_r, cal_b = cal
    if scr_r <= scr_l or scr_b <= scr_t:
        return []

    obs_l = max(scr_l, min(scr_r, cal_l - gap))
    obs_t = max(scr_t, min(scr_b, cal_t - gap))
    obs_r = max(scr_l, min(scr_r, cal_r + gap))
    obs_b = max(scr_t, min(scr_b, cal_b + gap))

    if obs_l >= obs_r or obs_t >= obs_b:
        return [(scr_l, scr_t, scr_r, scr_b)]

    rects = [
        (scr_l, scr_t, scr_r, obs_t),      # above calendar
        (scr_l, obs_b, scr_r, scr_b),      # below calendar
        (scr_l, obs_t, obs_l, obs_b),      # left of calendar
        (obs_r, obs_t, scr_r, obs_b),      # right of calendar
    ]
    return [r for r in rects if r[2] > r[0] and r[3] > r[1]]


def _candidate_positions(size, free_rects, position: str, snap: int):
    """Snapped top-left candidates, ordered from the calendar corner outward."""
    w, h = size
    is_right = "right" in position
    is_bottom = "bottom" in position
    candidates = []
    for left, top, right, bottom in free_rects:
        xs = _snapped_values(left, right - w, snap, reverse=is_right)
        ys = _snapped_values(top, bottom - h, snap, reverse=is_bottom)
        # X-major ordering makes same-width small widgets stack vertically first,
        # then open another column when vertical space is exhausted.
        for x in xs:
            for y in ys:
                candidates.append((x, y))
    return candidates


def _layout_bbox(coords, items):
    bxmin = bymin = bxmax = bymax = None
    for xy, (w, h) in zip(coords, items):
        if xy is None:
            continue
        x, y = xy
        bxmin = x if bxmin is None else min(bxmin, x)
        bymin = y if bymin is None else min(bymin, y)
        bxmax = x + w if bxmax is None else max(bxmax, x + w)
        bymax = y + h if bymax is None else max(bymax, y + h)
    if bxmin is None:
        return (0, 0, 0, 0)
    return (bxmin, bymin, bxmax, bymax)


def _pack_grid(items, order, free_rects, position: str, snap: int, item_gap: int):
    """Greedy grid pack into the L-shaped free space. Returns coords/skipped/bbox."""
    coords = [None] * len(items)
    placed = []
    skipped = 0

    for i in order:
        w, h = items[i]
        chosen = None
        for x, y in _candidate_positions((w, h), free_rects, position, snap):
            rect = (x, y, x + w, y + h)
            overlaps = False
            for px1, py1, px2, py2 in placed:
                padded = (
                    px1 - item_gap,
                    py1 - item_gap,
                    px2 + item_gap,
                    py2 + item_gap,
                )
                if _overlap(rect, padded):
                    overlaps = True
                    break
            if overlaps:
                continue
            chosen = (x, y)
            placed.append(rect)
            break
        if chosen is None:
            skipped += 1
        else:
            coords[i] = chosen

    return coords, skipped, _layout_bbox(coords, items)


def _grid_score(bbox, items, coords, skipped, loose_gap: bool, violated):
    if violated is not None:
        return (1, skipped, 0, 0, 0, 0)
    bxmin, bymin, bxmax, bymax = bbox
    bw = bxmax - bxmin
    bh = bymax - bymin
    area = bw * bh
    used = sum(w * h for xy, (w, h) in zip(coords, items) if xy is not None)
    waste = area - used
    return (0, skipped, 1 if loose_gap else 0, max(bw, bh), area, waste)


def _compute_arrange_layout(items, cal, scr, position, snap):
    """플로팅 위젯 배치 좌표 순수 계산 (L자 빈 공간 2D 패킹). Qt/DB 없음.

    items: [(w,h),...] (호출부 수집순). cal/scr: (left,top,right,bottom).
    position: "bottom-right"|"bottom-left"|"top-right"|"top-left". snap: 5mm 픽셀.
    반환: (coords, skipped_count).
    coords: items와 1:1. 배치된 위젯은 (x,y), 공간 부족으로 정렬에서 제외된
        위젯은 None(호출부가 제자리 유지). 배치된 위젯끼리는 절대 겹치지 않는다.
    skipped_count: 정렬에서 제외된(None) 위젯 수.

    캘린더를 gap만큼 확장해 화면에서 빼면 코너 배치 기준으로 L자 빈 공간이 남는다.
    그 공간의 스냅 격자 후보를 캘린더 코너에서 바깥쪽으로 훑어, 작은 D-Day 위젯은
    같은 열에 먼저 쌓고 공간이 부족할 때만 다음 열/다음 영역을 사용한다.
    """
    if not items:
        return [], 0

    snap = max(1, snap)
    gap = snap
    n = len(items)
    free_rects = _free_rects_around_calendar(cal, scr, gap)
    if not free_rects:
        return [None] * n, n

    # 결정적 후보 정렬키 (모든 키에 index i tie-break)
    base = list(range(n))
    orders = {
        "type_group": list(base),
        "height_desc": sorted(base, key=lambda i: (-items[i][1], i)),
        "width_desc": sorted(base, key=lambda i: (-items[i][0], i)),
        "area_desc": sorted(base, key=lambda i: (-(items[i][0] * items[i][1]), i)),
        "small_first": sorted(base, key=lambda i: (items[i][0] * items[i][1], i)),
    }

    best = None
    cand_seq = 0
    for oname in ("type_group", "height_desc", "width_desc", "area_desc", "small_first"):
        for item_gap in (gap, 0):
            coords, skipped, bbox = _pack_grid(
                items, orders[oname], free_rects, position, snap, item_gap
            )
            violated = _hard_violation(coords, items, cal, scr, 0)
            key = (_grid_score(bbox, items, coords, skipped, item_gap == 0, violated), cand_seq)
            if best is None or key < best[0]:
                best = (key, coords, skipped)
            cand_seq += 1

    if best is None:
        return [None] * n, n

    return best[1], best[2]


def _calendar_corner_coordinates(screen, width: int, height: int, position: str, margin: int = 20) -> tuple[int, int]:
    """Calculate a snapped calendar position inside the selected screen."""
    geo = screen.availableGeometry()
    snap = _snap_px_for_screen(screen)
    _snap = lambda v: round(v / snap) * snap

    if "right" in position:
        target_x = geo.right() - margin - width
    else:
        target_x = geo.left() + margin

    if "bottom" in position:
        target_y = geo.bottom() - margin - height
    else:
        target_y = geo.top() + margin

    x = _snap(target_x)
    y = _snap(target_y)
    x = _clamp_window_pos(x, geo.left(), geo.right() - width + 1)
    y = _clamp_window_pos(y, geo.top(), geo.bottom() - height + 1)
    return x, y


def _clamp_calendar_xy(x: int, y: int, width: int, height: int, geometry) -> tuple[int, int]:
    """창 전체가 작업 영역 안에 남도록 좌표를 보정한다(음수 모니터 좌표 지원)."""
    max_x = geometry.left() + max(0, geometry.width() - width)
    max_y = geometry.top() + max(0, geometry.height() - height)
    return (
        _clamp_window_pos(x, geometry.left(), max_x),
        _clamp_window_pos(y, geometry.top(), max_y),
    )


def _snap_calendar_xy(x: int, y: int, width: int, height: int,
                      geometry, snap: int) -> tuple[int, int]:
    """작업 영역 안에서 캘린더 좌표를 전역 5mm 격자에 맞춘다."""
    snap = max(1, snap)

    def _axis(value: int, lower: int, upper: int) -> int:
        if upper < lower:
            return lower
        snapped_lower = _snap_ceil(lower, snap)
        snapped_upper = _snap_floor(upper, snap)
        if snapped_lower > snapped_upper:
            return _clamp_window_pos(value, lower, upper)
        snapped = round(value / snap) * snap
        return _clamp_window_pos(snapped, snapped_lower, snapped_upper)

    max_x = geometry.left() + max(0, geometry.width() - width)
    max_y = geometry.top() + max(0, geometry.height() - height)
    return (
        _axis(x, geometry.left(), max_x),
        _axis(y, geometry.top(), max_y),
    )


def _clamp_window_to_available_screens(win, screens) -> bool:
    """Move a top-level window fully inside the best available screen.

    A top-left-only check misses windows whose origin is visible but whose
    right or bottom edge was clipped by a resolution/topology change.
    """
    geometries = [screen.availableGeometry() for screen in screens]
    if not geometries:
        return False

    x, y = win.x(), win.y()
    width, height = win.width(), win.height()

    def _fully_inside(geo) -> bool:
        return (
            x >= geo.left()
            and y >= geo.top()
            and x + width <= geo.left() + geo.width()
            and y + height <= geo.top() + geo.height()
        )

    if any(_fully_inside(geo) for geo in geometries):
        return False

    def _target_score(geo) -> tuple[int, int]:
        overlap_width = max(
            0,
            min(x + width, geo.left() + geo.width()) - max(x, geo.left()),
        )
        overlap_height = max(
            0,
            min(y + height, geo.top() + geo.height()) - max(y, geo.top()),
        )
        overlap_area = overlap_width * overlap_height
        center_x = x + width // 2
        center_y = y + height // 2
        nearest_x = max(
            geo.left(),
            min(center_x, geo.left() + geo.width()),
        )
        nearest_y = max(
            geo.top(),
            min(center_y, geo.top() + geo.height()),
        )
        distance = (center_x - nearest_x) ** 2 + (center_y - nearest_y) ** 2
        return overlap_area, -distance

    target = max(geometries, key=_target_score)
    clamped_x, clamped_y = _clamp_calendar_xy(
        x, y, width, height, target
    )
    if (clamped_x, clamped_y) == (x, y):
        return False
    win.move(clamped_x, clamped_y)
    return True


def _nearest_corner_for_rect(rect, screen_rect) -> str:
    """임의 위치의 캘린더가 화면 어느 모서리에 가까운지 반환한다."""
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    sx = (screen_rect[0] + screen_rect[2]) / 2
    sy = (screen_rect[1] + screen_rect[3]) / 2
    vertical = "top" if cy < sy else "bottom"
    horizontal = "left" if cx < sx else "right"
    return f"{vertical}-{horizontal}"


from qfluentwidgets import (
    TransparentToolButton, TransparentPushButton, BodyLabel,
    LineEdit, Theme,
    FluentIcon as FIF, InfoBar, InfoBarPosition, CaptionLabel,
    RoundMenu, Action,
)

from ui_sticky import STICKY_COLORS, WIDGET_WIDTH, DDAY_HEIGHT
from ui_search import SearchWindow
from ui_update import show_update_guide
from fluent_icons import fluent_icon

import database as db
from show_desktop_guard import ShowDesktopKeeper
import holidays

class SmoothCircleButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_color = QColor("white")
        self._is_hovered = False
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, hex_color: str):
        self._bg_color = QColor(hex_color)
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QBrush(self._bg_color))
        pen = QPen(QColor("black"))
        
        if self._is_hovered:
            pen.setWidth(2)
            margin = 1.0
        else:
            pen.setWidth(1)
            margin = 0.5
            
        painter.setPen(pen)
        
        rect = QRectF(self.rect())
        painter.drawEllipse(rect.adjusted(margin, margin, -margin, -margin))


class CalendarDayButton(QWidget):
    """달력 날짜 셀 위젯 (compact / expanded 2-모드)"""

    _CHIP_HEIGHT = 16
    _CHIP_SPACING = 2
    _MAX_CHIPS = 6

    def __init__(self, day: int, is_today: bool, event_colors: list,
                 is_current_month: bool, target_date: str, is_holiday: bool = False,
                 weekday_col: int = -1, count: int = 0, mode: str = "compact",
                 parent=None, *, calendar_scale: str = "compact"):
        super().__init__(parent)
        self.setObjectName("calendarDayButton")
        self.target_date = target_date
        self._callback = None
        self._is_today = is_today
        self._day = day
        self._event_colors = list(event_colors)
        self._is_current_month = is_current_month
        self._is_holiday = is_holiday
        self._weekday_col = weekday_col
        self._mode = mode
        self._chip_font_px = 13 if calendar_scale == "large" else 10
        self._chip_height = 22 if calendar_scale == "large" else self._CHIP_HEIGHT
        self._chip_spacing = 3 if calendar_scale == "large" else self._CHIP_SPACING
        self._count = count
        self._events = []
        self._rendering_events = False
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(0)

        # 날짜 라벨
        self.day_label = QLabel(str(day) if day > 0 else "")
        self.day_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(11)
        if is_today:
            font.setBold(True)
        self.day_label.setFont(font)
        layout.addWidget(self.day_label)

        # 색상 사각형 (RichText로 다중 색상 표시)
        self.squares_label = QLabel("")
        self.squares_label.setAlignment(Qt.AlignCenter)
        self.squares_label.setFixedHeight(14)
        self.squares_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.squares_label)

        # 총 일정 개수 (회색 숫자, 0이면 빈칸)
        self.count_label = QLabel("")
        self.count_label.setAlignment(Qt.AlignCenter)
        self.count_label.setFixedHeight(12)
        layout.addWidget(self.count_label)

        # expanded 전용: 일정 칩 컨테이너
        self._chips_container = QWidget(self)
        self._chips_container.setObjectName("calendarDayChipsContainer")
        self._chips_container.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._chips_container.setStyleSheet(
            "#calendarDayChipsContainer { background: transparent; border: none; }"
        )
        self._chips_layout = QVBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(2, 0, 2, 0)
        self._chips_layout.setSpacing(self._chip_spacing)
        self._chips_layout.setAlignment(Qt.AlignTop)
        layout.addWidget(self._chips_container, 1)

        self._update_squares(event_colors)
        self.set_count(count)
        self._set_style(False)
        self.setCursor(Qt.PointingHandCursor)
        self._set_mode(mode)

    def set_count(self, n: int):
        """그날 총 일정 수 표시 (0이면 빈칸)"""
        self._count = n
        self.count_label.setText(str(n) if n > 0 else "")

    def _update_squares(self, colors: list):
        """색상 사각형 업데이트 (최대 3개)"""
        self._event_colors = list(colors)
        if not colors:
            self.squares_label.setText("")
            return
        spans = [f'<span style="color:{c};">■</span>' for c in colors[:3]]
        self.squares_label.setText(" ".join(spans))

    def _set_style(self, selected: bool):
        """오늘, 선택, 공휴일 여부에 따른 통합 스타일 적용"""
        base_color = "#1a1a1a"
        count_color = "#9aa0a6"
        bg_style = "border-radius: 6px;"

        if self._weekday_col == 0:
            base_color = "#D32F2F"
        elif self._weekday_col == 6:
            base_color = "#1565C0"

        if self._is_holiday:
            base_color = "#D32F2F"  # 공휴일 = 빨강 (요일 무관)

        if not self._is_current_month:
            base_color = "#BDBDBD"  # 비현재월(빈 셀) — 기존 동작 보존

        if self._is_today:
            bg_style += "background: #01295F;"
            base_color = "white"
            count_color = "rgba(255,255,255,200)"
        elif selected:
            bg_style += "background: rgba(1,41,95,20);"

        self.setStyleSheet(f"#calendarDayButton {{ {bg_style} }}")
        self.day_label.setStyleSheet(f"color: {base_color}; background: transparent; padding: 2px;")
        self.squares_label.setStyleSheet("font-size: 10px; background: transparent;")
        self.count_label.setStyleSheet(
            f"color: {count_color}; font-size: 9px; font-weight: bold; background: transparent;"
        )

    def _set_mode(self, mode: str):
        """compact / expanded 모드 전환."""
        self._mode = mode if mode in ("compact", "expanded") else "compact"
        is_expanded = self._mode == "expanded"
        self.squares_label.setVisible(not is_expanded)
        self.count_label.setVisible(not is_expanded)
        self._chips_container.setVisible(is_expanded)
        if is_expanded:
            self.set_events(self._events)
        else:
            self._update_squares(self._event_colors)
            self.set_count(self._count)

    def _make_chip(self, text: str, color: str, dim: bool = False) -> QLabel:
        """단일 일정 칩 라벨을 만든다."""
        chip = QLabel(self._chips_container)
        chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        chip.setFixedHeight(self._chip_height)
        chip.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        font = chip.font()
        font.setPixelSize(self._chip_font_px)
        font.setBold(dim)
        chip.setFont(font)
        avail = max(10, self._chips_container.width() - 12)
        chip.setText(chip.fontMetrics().elidedText(text, Qt.ElideRight, avail))
        chip.setToolTip(text)
        if dim:
            chip.setStyleSheet(
                "background: rgba(0,0,0,16); color: #757575; "
                "border-radius: 4px; padding-left: 4px;"
            )
        else:
            chip.setStyleSheet(
                f"background: {color}; color: #1a1a1a; "
                "border-radius: 4px; padding-left: 4px;"
            )
        return chip

    def set_events(self, events: list):
        """expanded 셀 일정 칩 데이터를 갱신한다."""
        self._events = list(events)
        if self._mode != "expanded" or self._rendering_events:
            return
        self._rendering_events = True
        try:
            while self._chips_layout.count():
                item = self._chips_layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            if not events:
                return
            avail_h = self._chips_container.height()
            per = self._chip_height + self._chip_spacing
            fit = max(1, avail_h // per) if avail_h > 0 else self._MAX_CHIPS
            max_show = min(self._MAX_CHIPS, fit)
            if len(events) > max_show:
                keep = max(1, max_show - 1)
                visible = events[:keep]
                remaining = len(events) - keep
            else:
                visible = events
                remaining = 0
            for event in visible:
                chip = self._make_chip(event["content"], event["color"])
                self._chips_layout.addWidget(chip)
                chip.show()
            if remaining > 0:
                overflow = self._make_chip(f"+{remaining} 더", "", dim=True)
                self._chips_layout.addWidget(overflow)
                overflow.show()
        finally:
            self._rendering_events = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._mode == "expanded":
            self.set_events(self._events)

    def set_callback(self, callback):
        self._callback = callback

    def set_selected(self, selected: bool):
        self._set_style(selected)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._callback and self.target_date:
            self._callback(self.target_date)


class LockOverlay(QWidget):
    """PIN 입력을 위한 잠금 화면 오버레이"""
    unlocked = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("lockOverlay")
        self.setStyleSheet("""
            #lockOverlay {
                background: #1e1e2e; /* Fully opaque dark background */
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        icon_lbl = QLabel("🔒")
        icon_lbl.setStyleSheet("font-size: 48px; color: white;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        title = BodyLabel("잠겨 있음", self)
        title.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.pin_input = LineEdit(self)
        self.pin_input.setPlaceholderText("4자리 PIN 입력")
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setMaxLength(4)
        self.pin_input.setFixedWidth(150)
        self.pin_input.returnPressed.connect(self._check_pin)
        layout.addWidget(self.pin_input, 0, Qt.AlignCenter)

        self.error_lbl = CaptionLabel("", self)
        self.error_lbl.setStyleSheet("color: #FF7043;") # Light orange/red
        layout.addWidget(self.error_lbl)

        unlock_btn = TransparentPushButton("잠금 해제", self)
        unlock_btn.setStyleSheet("color: white; border: 1px solid white;")
        unlock_btn.clicked.connect(self._check_pin)
        layout.addWidget(unlock_btn, 0, Qt.AlignCenter)

    def _check_pin(self):
        entered = self.pin_input.text()
        correct = db.get_setting(db.SETTING_PRIVACY_PIN, "0000")
        if entered == correct:
            self.unlocked.emit()
            self.pin_input.clear()
            self.error_lbl.setText("")
        else:
            self.error_lbl.setText("PIN이 올바르지 않습니다.")
            self.pin_input.clear()

    def showEvent(self, event):
        super().showEvent(event)
        self.pin_input.setFocus()


import os
from PySide6.QtCore import QFileInfo, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider

class ShortcutSlot(QWidget):
    def __init__(self, shortcut_id: int, parent=None):
        super().__init__(parent)
        self.shortcut_id = shortcut_id
        self.path = ""
        self.name = ""
        
        # 슬롯 전체 크기 (아이콘 64x64 + 간격 + 텍스트)
        self.setFixedSize(64, 82)
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 아이콘 버튼 (64x64 사각형)
        self.btn = QPushButton(self)
        self.btn.setFixedSize(64, 64)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px dashed #444444;
                border-radius: 8px;
                color: #212121;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FFFFFF;
                border: 1px dashed #0078D4;
                color: #0078D4;
            }
        """)
        self.btn.setText("+")
        self.btn.clicked.connect(self._on_click)
        self.btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn.customContextMenuRequested.connect(
            lambda pos: self._show_manage_menu(self.btn.mapToGlobal(pos))
        )
        layout.addWidget(self.btn)
        
        # 이름 라벨
        self.name_label = QLabel("", self)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("font-size: 10px; color: #444444; font-weight: normal;")
        self.name_label.setFixedWidth(64)
        self.name_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.name_label.customContextMenuRequested.connect(
            lambda pos: self._show_manage_menu(self.name_label.mapToGlobal(pos))
        )
        layout.addWidget(self.name_label)
        
        # 삭제 버튼
        self.delete_btn = TransparentToolButton(FIF.CLOSE, self.btn)
        self.delete_btn.setFixedSize(18, 18)
        self.delete_btn.setIconSize(QSize(10, 10))
        self.delete_btn.move(46, 0)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._on_delete)
        self.delete_btn.hide()

    def update_data(self, name: str, path: str):
        self.name = name
        self.path = path
        
        if not self.path:
            # 1. 완전 빈 슬롯
            self.btn.setIcon(QIcon())
            self.btn.setText("+")
            self.name_label.setText("")
            self.name_label.setStyleSheet("font-size: 10px; color: #444444;")
            self.setToolTip("클릭하거나 파일·폴더를 드래그해 등록")
            self.btn.setStyleSheet("""
                QPushButton {
                    background: #FFFFFF;
                    border: 1px dashed #444444;
                    border-radius: 8px;
                    color: #212121;
                    font-size: 24px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #FFFFFF;
                    border: 1px dashed #0078D4;
                    color: #0078D4;
                }
            """)
            self.delete_btn.hide()
            
        elif os.path.exists(self.path):
            # 2. 정상적인 바로가기
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(self.path))
            self.btn.setIcon(icon)
            self.btn.setIconSize(QSize(48, 48))
            self.btn.setText("")
            
            display_name = self.name if self.name else os.path.basename(self.path)
            metrics = self.name_label.fontMetrics()
            elided_name = metrics.elidedText(display_name, Qt.ElideRight, 60)
            self.name_label.setText(elided_name)
            self.name_label.setStyleSheet("font-size: 10px; color: #444444;")
            self.setToolTip(f"{display_name}\n우클릭하여 관리")
            
            self.btn.setStyleSheet("""
                QPushButton {
                    background: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background: #F5F5F5;
                    border: 1px solid #0078D4;
                }
            """)
            self.delete_btn.show()
            
        else:
            # 3. 연결 끊김 (파일이 삭제됨)
            self.btn.setIcon(FIF.INFO.icon(color=QColor("#FF4D4F"))) # 빨간색 경고 아이콘
            self.btn.setIconSize(QSize(32, 32))
            self.btn.setText("")
            
            display_name = self.name if self.name else os.path.basename(self.path)
            self.name_label.setText("(!)" + display_name[:5])
            self.name_label.setStyleSheet("font-size: 10px; color: #FF4D4F; font-weight: bold;")
            self.setToolTip(
                f"파일을 찾을 수 없음: {self.path}\n클릭하여 경로 다시 지정"
            )
            
            self.btn.setStyleSheet("""
                QPushButton {
                    background: #FFF1F0;
                    border: 1px solid #FF4D4F;
                    border-radius: 8px;
                }
            """)
            self.delete_btn.show()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.btn.setStyleSheet("""
                QPushButton {
                    background: #E3F2FD;
                    border: 2px dashed #0078D4;
                    border-radius: 8px;
                }
            """)

    def dragLeaveEvent(self, event):
        self.update_data(self.name, self.path)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            path = url.toLocalFile()
            if path:
                if self._assign_path(path, preserve_name=False):
                    event.acceptProposedAction()

    @staticmethod
    def _default_target_name(path: str) -> str:
        normalized = os.path.normpath(path)
        base_name = os.path.basename(normalized)
        if os.path.isfile(path):
            return os.path.splitext(base_name)[0]
        if base_name:
            return base_name
        drive, _tail = os.path.splitdrive(normalized)
        root_name = drive.rstrip("\\/") or normalized.rstrip("\\/")
        return root_name.rsplit("\\", 1)[-1] or root_name

    def _persist(self, name: str, path: str) -> bool:
        try:
            db.update_shortcut(self.shortcut_id, name, path)
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("바로가기 저장 실패 (id=%s): %s", self.shortcut_id, e)
            InfoBar.error(
                title="저장 실패",
                content="바로가기를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return False
        self.update_data(name, path)
        return True

    def _assign_path(self, path: str, *, preserve_name: bool = True) -> bool:
        name = self.name.strip() if preserve_name and self.name.strip() else ""
        if not name:
            name = self._default_target_name(path)
        return self._persist(name, path)

    def _select_file(self):
        path, _selected_filter = QFileDialog.getOpenFileName(
            self.window(), "바로가기 파일 선택", "", "모든 파일 (*)"
        )
        if path:
            self._assign_path(path)

    def _select_folder(self):
        path = QFileDialog.getExistingDirectory(
            self.window(), "바로가기 폴더 선택"
        )
        if path:
            self._assign_path(path)

    def _rename(self):
        name, accepted = QInputDialog.getText(
            self.window(),
            "바로가기 이름",
            "표시할 이름:",
            QLineEdit.Normal,
            self.name,
        )
        name = name.strip()
        if accepted and name:
            self._persist(name, self.path)

    def _build_registration_menu(self):
        menu = RoundMenu(parent=self)
        menu.setWindowOpacity(1.0)
        file_action = Action(FIF.DOCUMENT, "파일 선택", menu)
        file_action.triggered.connect(self._select_file)
        menu.addAction(file_action)
        folder_action = Action(FIF.FOLDER, "폴더 선택", menu)
        folder_action.triggered.connect(self._select_folder)
        menu.addAction(folder_action)
        return menu

    def _show_registration_menu(self):
        menu = self._build_registration_menu()
        menu.closedSignal.connect(menu.deleteLater)
        menu.exec(self.btn.mapToGlobal(QPoint(0, self.btn.height())))

    def _build_manage_menu(self):
        menu = RoundMenu(parent=self)
        menu.setWindowOpacity(1.0)
        rename_action = Action(FIF.EDIT, "이름 변경", menu)
        rename_action.triggered.connect(self._rename)
        menu.addAction(rename_action)
        repair_action = Action(FIF.SYNC, "경로 다시 지정", menu)
        repair_action.triggered.connect(
            lambda: QTimer.singleShot(0, self._show_registration_menu)
        )
        menu.addAction(repair_action)
        delete_action = Action(FIF.DELETE, "삭제", menu)
        delete_action.triggered.connect(self._on_delete)
        menu.addAction(delete_action)
        return menu

    def _show_manage_menu(self, global_pos=None):
        if not self.path:
            self._show_registration_menu()
            return
        menu = self._build_manage_menu()
        menu.closedSignal.connect(menu.deleteLater)
        if not isinstance(global_pos, QPoint):
            global_pos = self.btn.mapToGlobal(QPoint(0, self.btn.height()))
        menu.exec(global_pos)

    def _on_click(self):
        if self.path and os.path.exists(self.path):
            try:
                os.startfile(self.path)
            except Exception as e:
                _logger.error(f"바로가기 실행 실패: {e}")
        elif self.path:
            InfoBar.warning(
                title="파일 없음",
                content="원본 파일이나 폴더를 찾을 수 없어 경로를 다시 지정합니다.",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=3000
            )
            self._show_registration_menu()
        else:
            self._show_registration_menu()

    def _on_delete(self):
        self._persist("", "")

class ShortcutSidebarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("shortcutSidebar")
        self.setFixedWidth(80)
        
        # 커스텀 위젯의 스타일 배경색이 확실히 그려지도록 설정
        self.setAttribute(Qt.WA_StyledBackground)
        
        self.setStyleSheet("""
            #shortcutSidebar {
                background: #F4F5F7;
                border-top-left-radius: 12px;
                border-bottom-left-radius: 12px;
                border-right: 1px solid rgba(206, 210, 216, 150);
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(10)

        # Title
        title = QLabel("바로가기")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 11px; color: #212121; font-weight: bold;")
        layout.addWidget(title)

        self.slots = []
        for i in range(1, 7):
            slot = ShortcutSlot(i, self)
            self.slots.append(slot)
            layout.addWidget(slot)

        layout.addStretch()

    def load_shortcuts(self):
        shortcuts = db.get_shortcuts()
        for data in shortcuts:
            idx = data["id"] - 1
            if 0 <= idx < len(self.slots):
                self.slots[idx].update_data(data["name"], data["path"])


class MainCalendarWindow(QWidget):
    """프레임리스 메인 캘린더 창 — 헤더 드래그와 모서리 배치를 모두 지원."""

    def __init__(self):
        super().__init__()
        self._current_year = date.today().year
        self._current_month = date.today().month
        self._selected_date = date.today().isoformat()
        self._today = date.today().isoformat()  # 오늘 재동기화 기준(자정 롤오버 감지)
        self._sticky_windows = {}  # note_id -> StickyNoteWindow
        self._dday_windows = {}    # widget_id -> DDayWidgetWindow
        self._focus_windows = {}   # widget_id -> FocusWidgetWindow
        self._sticky_side_panel = None      # StickySidePanel (large 모드 우측 패널)
        self._sticky_in_panel_mode = False  # large 모드에서 미니 패널 사용 중 여부
        self._dday_side_panel = None
        self._dday_in_panel_mode = False
        self._focus_side_panel = None
        self._focus_in_panel_mode = False
        self._settings_window = None
        self._trash_window = None
        self._expanded_row = None
        self._day_cells = {}  # date_str -> CalendarDayButton
        self._is_locked = False
        self._hidden_to_tray = False
        self._search_window = None
        self._show_lunar = db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1"
        self._schedule_color = db.DEFAULT_SCHEDULE_COLOR
        self._calendar_drag_offset = None
        self._calendar_drag_press_global = None
        self._calendar_drag_started = False
        self._calendar_drag_targets = set()
        self._watched_screen_ids = set()
        self._keep_desktop_unavailable_warned = False

        # 위젯 개수 상한 정리(집중 1·D-Day 5). 로드/패널 적용 이전에 1회.
        try:
            self._widget_trim_result = db.enforce_widget_limits()
        except sqlite3.Error as e:
            _logger.error("위젯 개수 정리 실패: %s", e)
            self._widget_trim_result = {"focus": 0, "dday": 0}

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Window |
            Qt.Tool
        )
        # WorkerW/Progman 재부모화 방식의 구형 바탕화면 모드는 사용하지 않는다.

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(380, 500)
        self.setMaximumWidth(380)
        self.resize(380, 660)

        # ── Win+D(바탕화면 보기)/모두 최소화에도 유지 ──
        self._show_desktop_keeper = ShowDesktopKeeper(
            enabled=self._keep_desktop_enabled(),
            parent=self,
        )
        self._show_desktop_keeper.guard(self)

        self._build_ui()
        self._apply_sidebar_visibility()
        self._apply_calendar_scale()
        self._load_open_sticky_notes()
        self._load_open_dday_widgets()
        self._load_open_focus_widgets()
        self._apply_app_opacity()

        # ── 주기적 자동 저장 (30초) ──
        self._last_auto_backup_date = date.today().isoformat()
        self._periodic_save_timer = QTimer(self)
        self._periodic_save_timer.setInterval(30_000)
        self._periodic_save_timer.timeout.connect(
            self._check_daily_auto_backup
        )
        self._periodic_save_timer.timeout.connect(self._periodic_save)
        self._periodic_save_timer.timeout.connect(self._check_day_rollover)
        self._periodic_save_timer.start()

        # 업그레이드 정리 안내(정리된 위젯이 있을 때만, 창 표시 후 모달)
        if self._widget_trim_result.get("focus") or self._widget_trim_result.get("dday"):
            QTimer.singleShot(1500, self._warn_widget_trim)

        # ── 화면 변경 감지 (듀얼 모니터/GPU 전환) ──
        self._screen_change_timer = QTimer(self)
        self._screen_change_timer.setSingleShot(True)
        self._screen_change_timer.setInterval(500)
        self._screen_change_timer.timeout.connect(self._on_screen_changed)

        app = QApplication.instance()
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._on_screen_removed)
        for screen in app.screens():
            self._watch_screen_geometry(screen)

        # ── 세션 변경 알림 등록 (Win+L 감지용) ──
        if sys.platform == "win32":
            try:
                import ctypes
                WTS_CURRENT_SERVER_HANDLE = 0
                NOTIFY_FOR_THIS_SESSION = 0
                ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                    int(self.winId()), NOTIFY_FOR_THIS_SESSION
                )
            except OSError:
                _logger.warning("WTS 세션 알림 등록 실패")

        # (Resume 잠금은 nativeEvent에서 처리하므로 필터 불필요)

    def _on_sidebar_setting_changed(self):
        """사이드바 설정 변경을 현재 캘린더 스케일에 맞게 반영."""
        if self._current_calendar_scale() != "compact":
            self._apply_calendar_scale()
        else:
            self._apply_sidebar_visibility()

    def _apply_sidebar_visibility(self):
        show_sidebar = db.get_setting(db.SETTING_SHOW_SIDEBAR, "0") == "1"
        
        # 시각적 업데이트 중단 (최소화)
        self.setUpdatesEnabled(False)
        
        header_section = self.right_content.findChild(QWidget, "headerSection")
        calendar_section = self.right_content.findChild(QWidget, "calendarSection")
        
        new_width = 460 if show_sidebar else 380
        
        # 1. 스타일 상태 업데이트 (setStyleSheet 대신 프로퍼티 변경으로 성능 최적화)
        if header_section:
            header_section.setProperty("sidebarActive", "true" if show_sidebar else "false")
            header_section.style().unpolish(header_section)
            header_section.style().polish(header_section)
            
        if calendar_section:
            calendar_section.setProperty("sidebarActive", "true" if show_sidebar else "false")
            calendar_section.style().unpolish(calendar_section)
            calendar_section.style().polish(calendar_section)

        # 2. 사이드바 가시성 조절
        self.sidebar.setVisible(show_sidebar)
        
        # 3. 제약 조건 업데이트
        self.setMinimumSize(new_width, 500)
        self.setMaximumWidth(new_width)
        
        # 4. 위치 및 크기 한 번에 적용 (setGeometry)
        screen = self._get_target_screen()
        if screen:
            self._apply_calendar_geometry(new_width, self.height(), screen)
            
        self.setUpdatesEnabled(True)
        self.update()

    # ─── 전체 투명도 ─────────────────────────────────────────────
    def _get_app_opacity(self) -> float:
        return _opacity_factor(
            db.get_setting(db.SETTING_APP_OPACITY, db.DEFAULT_APP_OPACITY)
        )

    def _apply_app_opacity(self, factor: float | None = None) -> None:
        """메인창과 열린 플로팅 위젯에 투명도를 일괄 적용."""
        if factor is None:
            factor = self._get_app_opacity()
        self.setWindowOpacity(factor)
        for registry in (self._sticky_windows, self._dday_windows, self._focus_windows):
            for win in registry.values():
                win.setWindowOpacity(factor)

    def _keep_desktop_enabled(self) -> bool:
        return db.get_setting(
            db.SETTING_KEEP_ON_SHOW_DESKTOP, db.DEFAULT_KEEP_ON_SHOW_DESKTOP
        ) == "1"

    def _register_floating_widget(self, win, factor: float | None = None) -> None:
        """새 플로팅 위젯 공통 등록: 투명도 적용 + Win+D 유지 가드."""
        win.setWindowOpacity(self._get_app_opacity() if factor is None else factor)
        self._show_desktop_keeper.guard(win)

    def _show_floating_widget(self, win) -> None:
        """예약된 표시도 잠금·트레이·현재 레지스트리/패널 상태를 확인한다."""
        if self._is_locked or self._hidden_to_tray:
            return
        for windows, in_panel in (
            (self._sticky_windows, self._sticky_in_panel_mode),
            (self._dday_windows, self._dday_in_panel_mode),
            (self._focus_windows, self._focus_in_panel_mode),
        ):
            if any(current is win for current in windows.values()):
                if not in_panel:
                    win.show()
                    win.raise_()
                return

    def _on_keep_desktop_changed(self) -> None:
        """설정에서 '바탕화면 고정' 토글 변경 시 실시간 반영."""
        enabled = self._keep_desktop_enabled()
        self._show_desktop_keeper.set_enabled(enabled)
        if enabled:
            self._warn_keep_desktop_unavailable_once()

    def _warn_keep_desktop_unavailable_once(self) -> None:
        """Win+D 감시 훅 설치 실패를 창 수명 동안 한 번만 안내한다."""
        if (
            self._keep_desktop_unavailable_warned
            or not self._keep_desktop_enabled()
            or self._show_desktop_keeper.is_operational()
        ):
            return

        self._keep_desktop_unavailable_warned = True
        InfoBar.warning(
            title="바탕화면 고정",
            content="바탕화면 고정 기능을 시작하지 못했습니다. 일반 창으로 동작합니다.",
            parent=self,
            position=InfoBarPosition.BOTTOM,
            duration=5000,
        )

    # ─── 캘린더 스케일 ───────────────────────────────────────────
    def _current_calendar_scale(self) -> str:
        scale = db.get_setting(db.SETTING_CALENDAR_SCALE, db.DEFAULT_CALENDAR_SCALE)
        return scale if scale in db.CALENDAR_SCALES else db.DEFAULT_CALENDAR_SCALE

    def _calendar_scale_geometry(self, scale: str, screen) -> tuple[int, int]:
        """작업 영역 안에서 현재 스케일의 창 크기를 계산."""
        show_sidebar = db.get_setting(db.SETTING_SHOW_SIDEBAR, "0") == "1"
        compact_width = 460 if show_sidebar else 380
        geo = screen.availableGeometry()
        if scale == "compact":
            return min(compact_width, geo.width()), min(660, geo.height())
        if scale == "medium":
            width = max(compact_width, int(geo.width() * 0.60))
            height = max(500, int(geo.height() * 0.60))
        else:
            width = max(compact_width, geo.width() - 40)
            height = max(500, geo.height() - 40)
        return min(width, geo.width()), min(height, geo.height())

    def _calendar_position_mode(self) -> str:
        mode = db.get_setting(
            db.SETTING_CALENDAR_POSITION_MODE,
            db.DEFAULT_CALENDAR_POSITION_MODE,
        )
        return mode if mode in ("corner", "free") else db.DEFAULT_CALENDAR_POSITION_MODE

    def _saved_calendar_xy(self) -> tuple[int, int] | None:
        try:
            x = int(db.get_setting(db.SETTING_CALENDAR_X, ""))
            y = int(db.get_setting(db.SETTING_CALENDAR_Y, ""))
        except (TypeError, ValueError):
            return None
        return x, y

    def _calendar_xy_for_size(self, width: int, height: int, fallback_screen) -> tuple[int, int]:
        """저장된 자유 위치를 복원하고, 없으면 설정 모서리 좌표를 사용한다."""
        if self._calendar_position_mode() == "free":
            saved = self._saved_calendar_xy()
            if saved is not None:
                x, y = saved
                # 크기 변경 뒤 새 중심점으로 화면을 고르면, 좌측 모니터의
                # 저장 좌표가 넓어진 창 폭 때문에 우측 화면으로 오인될 수 있다.
                # 드래그 완료 때 함께 저장한 타겟 화면을 우선한다.
                screen = fallback_screen
                if screen is None:
                    screen = QApplication.screenAt(QPoint(x, y))
                screen = screen or QApplication.primaryScreen()
                if screen is not None:
                    return _clamp_calendar_xy(
                        x, y, width, height, screen.availableGeometry()
                    )

        screen = fallback_screen or QApplication.primaryScreen()
        if screen is None:
            return self.x(), self.y()
        position = db.get_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
        return _calendar_corner_coordinates(screen, width, height, position)

    def _apply_calendar_geometry(self, width: int, height: int, screen) -> None:
        """현재 위치 모드에 맞게 크기와 좌표를 함께 적용한다."""
        x, y = self._calendar_xy_for_size(width, height, screen)
        self.setGeometry(x, y, width, height)
        if self._calendar_position_mode() == "free":
            saved = self._saved_calendar_xy()
            if saved != (x, y):
                db.save_setting(db.SETTING_CALENDAR_X, str(x))
                db.save_setting(db.SETTING_CALENDAR_Y, str(y))

    def _reparent_schedule_panel(self, scale: str):
        """일정 패널을 compact 하단과 expanded 우측 컬럼 사이에서 이동."""
        expanded = scale != "compact"
        calendar_section = self.right_content.findChild(QWidget, "calendarSection")
        main_layout = self.container.layout()
        if expanded:
            if self._expanded_row is None:
                self._expanded_row = QWidget(self.container)
                column = QVBoxLayout(self._expanded_row)
                column.setContentsMargins(0, 0, 0, 0)
                column.setSpacing(0)
                main_layout.addWidget(self._expanded_row, 0)
            self._expanded_row.setVisible(True)
            _detach_from_layout(self.schedule_panel)
            self.schedule_panel.setParent(self._expanded_row)
            self.schedule_panel.setMinimumWidth(300)
            self.schedule_panel.setMaximumWidth(360)
            self.schedule_panel.layout().setContentsMargins(12, 12, 12, 12)
            # large에서는 아래에 스티키 패널이 이어지므로 일정 패널 우하단은
            # 각지게 두고(=0px), medium에서는 우측 끝이므로 우하단까지 라운드한다.
            bottom_right = "0px" if scale == "large" else "12px"
            self.schedule_panel.setStyleSheet(f"""
                QWidget#schedulePanel {{
                    background: #FFFFFF;
                    border: 1px solid rgba(206, 210, 216, 180);
                    border-top-right-radius: 12px;
                    border-bottom-right-radius: {bottom_right};
                }}
            """)
            # large 우측 컬럼은 [일정 : 스티키] 세로 비율을 3:7로 둔다(스티키 영역 확대).
            self._expanded_row.layout().addWidget(self.schedule_panel, 3)
            self.schedule_panel.show()
            main_layout.setStretchFactor(self.right_content, 1)
        else:
            _detach_from_layout(self.schedule_panel)
            self.schedule_panel.setMinimumWidth(0)
            self.schedule_panel.setMaximumWidth(16777215)
            self.schedule_panel.layout().setContentsMargins(0, 0, 0, 0)
            self.schedule_panel.setStyleSheet(
                "QWidget#schedulePanel { background: transparent; border: none; }"
            )
            if calendar_section is not None:
                self.schedule_panel.setParent(calendar_section)
                calendar_section.layout().addWidget(self.schedule_panel, 1)
            self.schedule_panel.show()
            if self._expanded_row is not None:
                self._expanded_row.setVisible(False)
            main_layout.setStretchFactor(self.right_content, 0)

    def _apply_calendar_scale(self):
        """저장된 compact/medium/large 설정을 즉시 반영."""
        scale = self._current_calendar_scale()
        expanded = scale != "compact"
        screen = self._get_target_screen()

        self.setUpdatesEnabled(False)
        if expanded:
            sidebar_visible = True
        else:
            sidebar_visible = db.get_setting(db.SETTING_SHOW_SIDEBAR, "0") == "1"
        self.sidebar.setVisible(sidebar_visible)

        for object_name in ("headerSection", "calendarSection"):
            section = self.right_content.findChild(QWidget, object_name)
            if section is not None:
                section.setProperty("sidebarActive", "true" if sidebar_visible else "false")
                section.setProperty("expanded", "true" if expanded else "false")
                section.style().unpolish(section)
                section.style().polish(section)

        self._reparent_schedule_panel(scale)
        self._apply_dday_side_panel(scale == "large")
        self._apply_focus_side_panel(scale == "large")
        self._apply_sticky_side_panel(scale == "large")
        if expanded:
            self.setMaximumWidth(16777215)
            self.setMinimumSize(500, 500)
        else:
            base_width = 460 if db.get_setting(db.SETTING_SHOW_SIDEBAR, "0") == "1" else 380
            self.setMinimumSize(base_width, 500)
            self.setMaximumWidth(base_width)

        if screen is not None:
            width, height = self._calendar_scale_geometry(scale, screen)
            if expanded:
                self.setMinimumSize(min(width, 600), 500)
            self._apply_calendar_geometry(width, height, screen)

        self.setUpdatesEnabled(True)
        self.update()
        self._refresh_calendar()

    # ─── UI 구성 ────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 컨테이너 (투명 래퍼)
        self.container = QWidget(self)
        self.container.setObjectName("mainContainer")
        self.container.setStyleSheet("""
            #mainContainer {
                background: transparent;
                border-radius: 12px;
                border: none;
            }
        """)
        outer.addWidget(self.container)

        main_layout = QHBoxLayout(self.container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = ShortcutSidebarWidget(self.container)
        main_layout.addWidget(self.sidebar)
        self.sidebar.load_shortcuts()

        self.right_content = QWidget(self.container)
        self.right_content.setObjectName("rightContent")
        self.right_content.setStyleSheet("#rightContent { background: transparent; }")
        right_layout = QVBoxLayout(self.right_content)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        main_layout.addWidget(self.right_content)

        # ── 헤더 섹션 (네이비) ──
        header_section = QWidget(self.right_content)
        header_section.setObjectName("headerSection")
        header_section.setStyleSheet("""
            #headerSection {
                background: #01295F;
                border-top-right-radius: 12px;
                border-top-left-radius: 12px;
            }
            #headerSection[sidebarActive="true"] {
                border-top-left-radius: 0px;
            }
            #headerSection[expanded="true"] {
                border-top-right-radius: 0px;
            }
        """)

        header_layout = QVBoxLayout(header_section)
        header_layout.setContentsMargins(12, 12, 12, 8)
        header_layout.setSpacing(8)
        right_layout.addWidget(header_section)

        # ── 상단 바 ──
        self._build_top_bar(header_layout)
        self._calendar_drag_targets = {header_section, self.month_label}
        for target in self._calendar_drag_targets:
            target.installEventFilter(self)
        self.installEventFilter(self)
        self.month_label.setCursor(Qt.SizeAllCursor)
        self.month_label.setToolTip("드래그하여 캘린더 이동")

        # ── 법령정보 검색 바 (구분선 포함 컨테이너) ──
        self.law_search_container = QWidget(header_section)
        law_container_layout = QVBoxLayout(self.law_search_container)
        law_container_layout.setContentsMargins(0, 4, 0, 4)
        law_container_layout.setSpacing(0)

        self._build_law_search_bar(law_container_layout)

        header_layout.addWidget(self.law_search_container)
        self.law_search_container.setVisible(
            db.get_setting(db.SETTING_SHOW_LAW_SEARCH, "1") == "1"
        )

        # ── 캘린더 섹션 (화이트) ──
        calendar_section = QWidget(self.right_content)
        calendar_section.setObjectName("calendarSection")
        calendar_section.setStyleSheet("""
            #calendarSection {
                background: #FFFFFF;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                border: 1px solid rgba(206, 210, 216, 180);
            }
            #calendarSection[sidebarActive="true"] {
                border-bottom-left-radius: 0px;
                border-left: none;
            }
            #calendarSection[expanded="true"] {
                border-bottom-right-radius: 0px;
                border-right: none;
            }
        """)

        calendar_layout = QVBoxLayout(calendar_section)
        calendar_layout.setContentsMargins(12, 8, 12, 12)
        calendar_layout.setSpacing(8)
        right_layout.addWidget(calendar_section)

        # ── 요일 헤더 ──
        self._build_weekday_header(calendar_layout)

        # ── 달력 그리드 ──
        self.calendar_grid = QGridLayout()
        self.calendar_grid.setSpacing(2)
        calendar_layout.addLayout(self.calendar_grid)

        # ── 구분선 ──
        divider = QLabel()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(206, 210, 216, 120);")
        calendar_layout.addWidget(divider)

        # ── 하단: 선택 날짜 + 일정 ──
        self._build_bottom_panel(calendar_layout)



    def _build_top_bar(self, parent_layout: QVBoxLayout):
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(0)

        header_pill_style = """
            QPushButton {
                color: #FFFFFF;
                background: rgba(255, 255, 255, 18);
                border-radius: 9px;
                border: 1px solid rgba(255, 255, 255, 55);
                padding: 0px 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 42);
                border: 1px solid rgba(255, 255, 255, 95);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 72);
            }
        """

        header_icon_style = """
            QToolButton {
                color: #FFFFFF;
                background: rgba(255, 255, 255, 18);
                border-radius: 9px;
                border: 1px solid rgba(255, 255, 255, 55);
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 42);
                border: 1px solid rgba(255, 255, 255, 95);
            }
            QToolButton:pressed {
                background: rgba(255, 255, 255, 72);
            }
        """

        header_flat_icon_style = """
            QToolButton {
                color: #FFFFFF;
                background: transparent;
                border: none;
                border-radius: 8px;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 28);
            }
            QToolButton:pressed {
                background: rgba(255, 255, 255, 50);
            }
        """

        # 좌측: 오늘 / 새 항목
        left_widget = QWidget(self)
        left_widget.setObjectName("headerLeftGroup")
        left_widget.setFixedWidth(92)
        left_group = QHBoxLayout()
        left_group.setContentsMargins(0, 0, 0, 0)
        left_group.setSpacing(8)
        left_widget.setLayout(left_group)

        today_btn = TransparentPushButton("오늘", self)
        today_btn.setObjectName("headerTodayButton")
        today_btn.setFixedSize(52, 32)
        today_btn.setToolTip("오늘 날짜로 이동")
        today_btn.setStyleSheet(header_pill_style)
        today_btn.clicked.connect(self._on_today)
        left_group.addWidget(today_btn)

        self._add_btn = TransparentToolButton(FIF.ADD, self)
        self._add_btn.setObjectName("headerAddButton")
        self._add_btn.setFixedSize(32, 32)
        self._add_btn.setIcon(fluent_icon("add", "#FFFFFF", 24))
        self._add_btn.setIconSize(QSize(15, 15))
        self._add_btn.setToolTip("새 노트 / D-Day")
        self._add_btn.setStyleSheet(header_icon_style)
        self._add_btn.clicked.connect(self._on_add_menu)
        left_group.addWidget(self._add_btn)
        top_bar.addWidget(left_widget)

        top_bar.addStretch(1)

        # ◀ 연월 ▶ 그룹
        nav_group = QHBoxLayout()
        nav_group.setSpacing(4)

        self.prev_btn = TransparentToolButton(FIF.LEFT_ARROW, self)
        self.prev_btn.setObjectName("monthNavButton")
        self.prev_btn.setFixedSize(24, 32)
        self.prev_btn.setIcon(fluent_icon("chevron_left", "#FFFFFF", 24))
        self.prev_btn.setIconSize(QSize(18, 18))
        self.prev_btn.setStyleSheet("""
            QToolButton#monthNavButton {
                color: #FFFFFF;
                background: transparent;
                border: none;
            }
            QToolButton#monthNavButton:hover {
                background: rgba(255, 255, 255, 25);
                border-radius: 8px;
            }
            QToolButton#monthNavButton:pressed {
                background: rgba(255, 255, 255, 45);
            }
        """)
        self.prev_btn.clicked.connect(self._on_prev_month)
        nav_group.addWidget(self.prev_btn)

        self.month_label = BodyLabel("", self)
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setStyleSheet("color: #FFFFFF;")
        self.month_label.setFixedSize(92, 32)
        self.month_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        month_font = QFont()
        month_font.setPixelSize(16)
        month_font.setBold(True)
        self.month_label.setFont(month_font)
        nav_group.addWidget(self.month_label)

        self.next_btn = TransparentToolButton(FIF.RIGHT_ARROW, self)
        self.next_btn.setObjectName("monthNavButton")
        self.next_btn.setFixedSize(24, 32)
        self.next_btn.setIcon(fluent_icon("chevron_right", "#FFFFFF", 24))
        self.next_btn.setIconSize(QSize(18, 18))
        self.next_btn.setStyleSheet("""
            QToolButton#monthNavButton {
                color: #FFFFFF;
                background: transparent;
                border: none;
            }
            QToolButton#monthNavButton:hover {
                background: rgba(255, 255, 255, 25);
                border-radius: 8px;
            }
            QToolButton#monthNavButton:pressed {
                background: rgba(255, 255, 255, 45);
            }
        """)
        self.next_btn.clicked.connect(self._on_next_month)
        nav_group.addWidget(self.next_btn)

        top_bar.addLayout(nav_group)
        top_bar.addStretch(1)

        right_widget = QWidget(self)
        right_widget.setObjectName("headerRightGroup")
        right_widget.setFixedWidth(92)
        right_group = QHBoxLayout()
        right_group.setContentsMargins(0, 0, 0, 0)
        right_group.setSpacing(6)
        right_group.setAlignment(Qt.AlignRight)
        right_widget.setLayout(right_group)

        # 검색
        search_btn = TransparentToolButton(FIF.SEARCH, self)
        search_btn.setObjectName("headerSearchButton")
        search_btn.setFixedSize(32, 32)
        search_btn.setIcon(fluent_icon("search", "#FFFFFF", 24))
        search_btn.setIconSize(QSize(21, 21))
        search_btn.setToolTip("일정 검색")
        search_btn.setStyleSheet(header_flat_icon_style)
        search_btn.clicked.connect(self._on_search)
        right_group.addWidget(search_btn)

        self._more_btn = TransparentToolButton(FIF.MORE, self)
        self._more_btn.setObjectName("headerMoreButton")
        self._more_btn.setFixedSize(32, 32)
        self._more_btn.setIcon(fluent_icon("more_vertical", "#FFFFFF", 24))
        self._more_btn.setIconSize(QSize(21, 21))
        self._more_btn.setToolTip("더보기")
        self._more_btn.setStyleSheet(header_flat_icon_style)
        self._more_btn.clicked.connect(self._on_more_menu)
        right_group.addWidget(self._more_btn)
        top_bar.addWidget(right_widget)

        parent_layout.addLayout(top_bar)

    def _build_law_search_bar(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(0)

        search_box = QWidget(self)
        search_box.setObjectName("lawSearchBox")
        search_box.setFixedHeight(36)
        search_box.setStyleSheet("""
            QWidget#lawSearchBox {
                background: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 70);
                border-radius: 10px;
            }
        """)
        box_layout = QHBoxLayout(search_box)
        box_layout.setContentsMargins(12, 0, 4, 0)
        box_layout.setSpacing(6)

        self.law_search_input = LineEdit(self)
        self.law_search_input.setPlaceholderText("AI 법령정보 또는 키워드 검색...")
        self.law_search_input.setFixedHeight(30)
        self.law_search_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.law_search_input.setStyleSheet("""
            LineEdit, QLineEdit {
                background: transparent;
                color: #FFFFFF;
                border: none;
                padding: 0px;
                font-size: 13px;
            }
            LineEdit:focus, QLineEdit:focus {
                border: none;
            }
        """)
        self.law_search_input.returnPressed.connect(self._on_law_search)
        box_layout.addWidget(self.law_search_input, 1)

        search_btn = TransparentToolButton(FIF.ROBOT, self)
        search_btn.setObjectName("lawSearchSubmitButton")
        search_btn.setIcon(fluent_icon("bot", "#FFFFFF", 24))
        search_btn.setIconSize(QSize(18, 18))
        search_btn.setToolTip("법제처 AI 검색 실행")
        search_btn.setFixedSize(30, 30)
        search_btn.setStyleSheet("""
            QToolButton#lawSearchSubmitButton {
                color: #FFFFFF;
                background: transparent;
                border: none;
                border-radius: 8px;
            }
            QToolButton#lawSearchSubmitButton:hover {
                background: rgba(255, 255, 255, 28);
            }
            QToolButton#lawSearchSubmitButton:pressed {
                background: rgba(255, 255, 255, 50);
            }
        """)
        search_btn.clicked.connect(self._on_law_search)
        box_layout.addWidget(search_btn)

        row.addWidget(search_box)

        parent_layout.addLayout(row)

    def _make_menu_action(self, menu: "RoundMenu", icon_name: str, text: str, slot) -> Action:
        """RoundMenu용 아이콘 액션 생성(공통 헬퍼)."""
        act = Action(fluent_icon(icon_name, size=24), text, menu)
        act.triggered.connect(slot)
        return act

    def _apply_header_menu_style(self, menu: "RoundMenu") -> None:
        """상단 드롭다운 메뉴 hover/selected 강조색을 앱 톤으로 맞춘다."""
        menu.view.setStyleSheet("""
            MenuActionListWidget::item:hover,
            MenuActionListWidget::item:selected {
                background-color: #01295F;
                color: #FFFFFF;
            }
            MenuActionListWidget::item:selected:active {
                background-color: #15355F;
                color: #FFFFFF;
            }
        """)

    def _build_more_menu(self) -> "RoundMenu":
        # plain QMenu + QSS border-radius 는 라이브 Windows에서 배경이 투명해지는
        # 문제가 있어, 불투명·라운드·그림자 내장 RoundMenu를 사용한다.
        menu = RoundMenu(parent=self)
        # 전체 투명도 설정과 무관하게 메뉴는 항상 또렷해야 한다.
        menu.setWindowOpacity(1.0)
        self._apply_header_menu_style(menu)
        menu.addAction(self._make_menu_action(menu, "arrow_sort_color", "자동정렬", self._on_arrange_sticky_notes))
        menu.addAction(self._make_menu_action(menu, "arrow_sync_color", "앱 업데이트", self._on_update_guide))
        menu.addAction(self._make_menu_action(menu, "delete_color", "휴지통", self._on_open_trash))
        menu.addAction(self._make_menu_action(menu, "settings_color", "설정", self._on_settings))
        menu.addSeparator()
        menu.addAction(self._make_menu_action(menu, "subtract_color", "앱 최소화", self._minimize_to_tray))
        return menu

    def _on_more_menu(self):
        menu = self._build_more_menu()
        pos = self._more_btn.mapToGlobal(QPoint(0, self._more_btn.height()))
        menu.exec(pos)

    def _on_law_search(self):
        from urllib.parse import quote_plus
        keyword = self.law_search_input.text().strip()
        if not keyword:
            return
        params = (
            f"query={quote_plus(keyword)}"
            "&pageNum=1"
            "&pagePer=10"
            "&searchType=1"
            "&modelYn=N"
            "&keywordSearchYn=N"
            "&searchResultLsKndCd=0"
            "&searchKndCd=0"
            "&mainType=main"
            "&detailSearchYn=N"
            "&sortCode=0"
            "&aiAstCd=0"
        )
        url = QUrl(f"https://www.law.go.kr/LSW/ais/searchList.do?{params}")
        QDesktopServices.openUrl(url)

    def _build_weekday_header(self, parent_layout: QVBoxLayout):
        weekdays = ["일", "월", "화", "수", "목", "금", "토"]
        header_layout = QGridLayout()
        header_layout.setSpacing(2)
        for col, day in enumerate(weekdays):
            lbl = QLabel(day)
            lbl.setAlignment(Qt.AlignCenter)
            color = "#D32F2F" if col == 0 else ("#1565C0" if col == 6 else "")
            if color:
                lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            else:
                lbl.setStyleSheet("color: #1a1a1a; font-size: 11px; font-weight: bold;")
            header_layout.addWidget(lbl, 0, col)
        parent_layout.addLayout(header_layout)

    def _build_bottom_panel(self, parent_layout: QVBoxLayout):
        # compact에서는 달력 하단, expanded에서는 우측 컬럼으로 이동하는 일정 패널
        self.schedule_panel = QWidget(self)
        self.schedule_panel.setObjectName("schedulePanel")
        panel_layout = QVBoxLayout(self.schedule_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(8)
        parent_layout.addWidget(self.schedule_panel, 1)

        # 선택 날짜 라벨 + 일정 개수
        date_row = QHBoxLayout()
        self.selected_date_label = BodyLabel("날짜를 선택하세요", self)
        self.selected_date_label.setStyleSheet("color: #1a1a1a;")
        date_row.addWidget(self.selected_date_label)
        
        # 음력 정보 라벨 (녹색)
        self.lunar_info_label = BodyLabel("", self)
        self.lunar_info_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 11px;")
        date_row.addWidget(self.lunar_info_label)

        # 공휴일명 라벨 (빨강) — 음력 설정과 무관하게 항상 표시
        self.holiday_info_label = BodyLabel("", self)
        self.holiday_info_label.setStyleSheet("color: #D32F2F; font-weight: bold; font-size: 11px;")
        date_row.addWidget(self.holiday_info_label)

        date_row.addStretch()
        self.count_label = BodyLabel("", self)
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.count_label.setStyleSheet("color: #757575; font-size: 11px;")
        date_row.addWidget(self.count_label)
        panel_layout.addLayout(date_row)

        # 일정 입력
        schedule_input_row = QHBoxLayout()

        self.schedule_color_btn = SmoothCircleButton(self)
        self.schedule_color_btn.setFixedSize(22, 22)
        self.schedule_color_btn.setToolTip("일정 색상 선택 (클릭하여 순환)")
        self.schedule_color_btn.clicked.connect(self._on_cycle_schedule_color)
        self._update_schedule_color_btn()
        schedule_input_row.addWidget(self.schedule_color_btn)

        self.schedule_input = LineEdit(self)
        self.schedule_input.setPlaceholderText("일정 추가...")
        self.schedule_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.schedule_input.returnPressed.connect(self._on_add_schedule)
        schedule_input_row.addWidget(self.schedule_input, 1)
        add_btn = TransparentToolButton(FIF.ADD, self)
        add_btn.clicked.connect(self._on_add_schedule)
        schedule_input_row.addWidget(add_btn)
        panel_layout.addLayout(schedule_input_row)

        # 일정 리스트
        self.schedule_list = QListWidget(self)
        self.schedule_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.schedule_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; }
            QListWidget::item { padding: 3px; }
        """)
        self.schedule_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.schedule_list.customContextMenuRequested.connect(
            self._on_schedule_context_menu
        )
        self.schedule_list.itemDoubleClicked.connect(self._on_edit_schedule)
        self._editing_item = None  # 현재 인라인 편집 중인 아이템
        self._finish_current_edit = None  # 현재 편집 종료 콜백
        panel_layout.addWidget(self.schedule_list, 1)

        # 상태 표시 라벨 (자동 저장 등) - 가장 하단으로 이동
        self.status_label = CaptionLabel("", self)
        self.status_label.setStyleSheet("color: #0078D4;")
        self.status_label.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(self.status_label)

    # ─── 달력 갱신 ──────────────────────────────────────────────
    def _refresh_calendar(self):
        short_year = self._current_year % 100
        self.month_label.setText(f"{short_year}년 {self._current_month}월")

        # 그리드 초기화
        while self.calendar_grid.count():
            item = self.calendar_grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._day_cells = {}

        today = date.today()
        event_date_colors = db.get_all_schedule_date_colors()
        event_date_counts = db.get_all_schedule_date_counts()
        schedule_palette = db.get_schedule_palette()
        self._show_lunar = db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1"
        calendar_scale = self._current_calendar_scale()
        cell_mode = "expanded" if calendar_scale != "compact" else "compact"
        month_events = (
            db.get_schedules_for_month(self._current_year, self._current_month)
            if cell_mode == "expanded" else {}
        )

        # 달력 계산 (일요일 시작)
        cal = calendar.Calendar(firstweekday=6).monthdayscalendar(
            self._current_year, self._current_month
        )

        for row_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
                is_current = day != 0
                actual_day = day if is_current else 0
                target_date = ""
                if is_current:
                    target_date = f"{self._current_year:04d}-{self._current_month:02d}-{actual_day:02d}"

                is_today = (
                    is_current and
                    self._current_year == today.year and
                    self._current_month == today.month and
                    actual_day == today.day
                )
                event_colors = [
                    db.schedule_display_color(color, schedule_palette)
                    for color in event_date_colors.get(target_date, [])
                ]
                is_holiday = bool(target_date) and holidays.is_holiday(target_date)
                count = event_date_counts.get(target_date, 0)

                cell = CalendarDayButton(
                    actual_day, is_today, event_colors, is_current, target_date,
                    is_holiday, col_idx, count, cell_mode, self,
                    calendar_scale=calendar_scale,
                )
                if cell_mode == "expanded" and target_date:
                    cell.set_events([
                        {
                            **event,
                            "color": db.schedule_display_color(
                                event.get("color"), schedule_palette
                            ),
                        }
                        for event in month_events.get(target_date, [])
                    ])
                if target_date:
                    cell.set_callback(self._on_date_selected)
                    self._day_cells[target_date] = cell
                    if target_date == self._selected_date:
                        cell.set_selected(True)

                self.calendar_grid.addWidget(cell, row_idx, col_idx)

        # 선택된 날짜 정보 갱신 (루프 완료 후)
        if self._selected_date in self._day_cells:
            self._on_date_selected(self._selected_date)
    def _on_date_selected(self, date_str: str):
        """날짜 클릭 시 하단 패널 업데이트"""
        old_cell = self._day_cells.get(self._selected_date)
        if old_cell is not None:
            try:
                old_cell.set_selected(False)
            except RuntimeError:
                pass  # C++ 객체가 이미 삭제된 경우 안전 무시
        self._selected_date = date_str
        if date_str in self._day_cells:
            self._day_cells[date_str].set_selected(True)
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            self.selected_date_label.setText(
                f"{d.year}년 {d.month}월 {d.day}일"
            )
            
            # 음력 정보 업데이트
            if self._show_lunar:
                lunar = holidays.get_lunar_date(date_str)
                if lunar:
                    lm, ld = lunar.split('.')
                    self.lunar_info_label.setText(f" (음력: {lm}월 {ld}일)")
                else:
                    self.lunar_info_label.setText("")
            else:
                self.lunar_info_label.setText("")
                
        except ValueError:
            self.selected_date_label.setText(date_str)
            self.lunar_info_label.setText("")

        hol = holidays.get_holiday(date_str)
        self.holiday_info_label.setText(f" · {hol}" if hol else "")
        self._load_schedules()

    def _load_schedules(self):
        # 진행 중인 편집이 있으면 저장 후 종료 (위젯 파괴 전에 처리)
        if self._finish_current_edit:
            self._finish_current_edit(True)
        self._editing_item = None
        self._finish_current_edit = None
        # 기존 아이템 위젯 명시적 해제 (메모리 누수 방지)
        for i in range(self.schedule_list.count()):
            item = self.schedule_list.item(i)
            widget = self.schedule_list.itemWidget(item)
            if widget:
                self.schedule_list.removeItemWidget(item)
                widget.deleteLater()
        self.schedule_list.clear()
        try:
            schedules = db.get_schedules(self._selected_date)
            schedule_palette = db.get_schedule_palette()
            for s in schedules:
                self._add_schedule_item(
                    s["id"], s["content"],
                    decryption_failed=s.get("_decryption_failed", False),
                    color=s.get("color", db.DEFAULT_SCHEDULE_COLOR),
                    display_color=db.schedule_display_color(
                        s.get("color"), schedule_palette
                    ),
                )
        except (sqlite3.Error, OSError) as e:
            _logger.error("일정 로드 실패: %s", e)
        self._update_count()

    def _add_schedule_item(self, schedule_id: int, content: str,
                           decryption_failed: bool = False,
                           color: str = None, display_color: str = None):
        if color is None:
            color = db.DEFAULT_SCHEDULE_COLOR
        if display_color is None:
            display_color = db.schedule_display_color(color)

        item = QListWidgetItem()
        item.setData(Qt.UserRole, schedule_id)
        item.setData(Qt.UserRole + 1, content)
        item.setData(Qt.UserRole + 2, color)
        self.schedule_list.addItem(item)

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(4)

        color_dot = QLabel("●")
        color_dot.setFixedSize(16, 16)
        color_dot.setAlignment(Qt.AlignCenter)
        color_dot.setStyleSheet(
            f"color: {display_color}; font-size: 14px; background: transparent;"
        )
        row_layout.addWidget(color_dot)

        text_label = BodyLabel(content)
        if decryption_failed:
            text_label.setStyleSheet("color: #D32F2F; font-style: italic;")
        else:
            text_label.setStyleSheet("color: #1a1a1a;")
        row_layout.addWidget(text_label, 1)

        delete_btn = TransparentToolButton(FIF.DELETE)
        delete_btn.setFixedSize(24, 24)
        delete_btn.clicked.connect(
            lambda checked=False, i=item, sid=schedule_id: self._on_delete_schedule(i, sid)
        )
        row_layout.addWidget(delete_btn)

        row_widget.setProperty("schedule_color", color)
        item.setSizeHint(row_widget.sizeHint())
        self.schedule_list.setItemWidget(item, row_widget)

    def _build_schedule_context_menu(self, item: QListWidgetItem) -> "RoundMenu":
        """일정 행 우클릭용 편집·삭제 메뉴를 만든다."""
        schedule_id = item.data(Qt.UserRole)
        menu = RoundMenu(parent=self)
        menu.setWindowOpacity(1.0)
        self._apply_header_menu_style(menu)

        edit_action = Action(FIF.EDIT, "편집", menu)
        edit_action.triggered.connect(
            lambda checked=False, i=item: self._on_edit_schedule(i)
        )
        menu.addAction(edit_action)

        delete_action = Action(FIF.DELETE, "삭제", menu)
        delete_action.triggered.connect(
            lambda checked=False, i=item, sid=schedule_id:
                self._on_delete_schedule(i, sid)
        )
        menu.addAction(delete_action)
        return menu

    def _on_schedule_context_menu(self, pos: QPoint):
        """우클릭한 일정 행 옆에 편집·삭제 메뉴를 표시한다."""
        if self._is_locked:
            return
        item = self.schedule_list.itemAt(pos)
        if item is None:
            return
        menu = self._build_schedule_context_menu(item)
        menu.closedSignal.connect(menu.deleteLater)
        menu.exec(self.schedule_list.viewport().mapToGlobal(pos))

    def _refresh_cell_for_date(self, date_str: str):
        """일정 변경 후 해당 날짜 셀만 현재 모드에 맞게 갱신."""
        cell = self._day_cells.get(date_str)
        if not cell:
            return
        schedules = db.get_schedules(date_str)
        schedule_palette = db.get_schedule_palette()
        cell.set_count(len(schedules))
        if getattr(cell, "_mode", "compact") == "expanded":
            cell.set_events([
                {
                    "content": schedule["content"],
                    "color": db.schedule_display_color(
                        schedule.get("color") or db.DEFAULT_SCHEDULE_COLOR,
                        schedule_palette,
                    ),
                }
                for schedule in schedules
            ])
        else:
            colors = {s.get("color") or db.DEFAULT_SCHEDULE_COLOR for s in schedules}
            color_order = {color[0]: index for index, color in enumerate(db.SCHEDULE_COLORS)}
            ordered = sorted(colors, key=lambda color: color_order.get(color, 99))
            cell._update_squares([
                db.schedule_display_color(color, schedule_palette)
                for color in ordered
            ])

    def _on_delete_schedule(self, item: QListWidgetItem, schedule_id: int):
        if self._is_locked:
            return
        try:
            db.delete_schedule(schedule_id)
            row = self.schedule_list.row(item)
            widget = self.schedule_list.itemWidget(item)
            if widget:
                self.schedule_list.removeItemWidget(item)
                widget.deleteLater()
            self.schedule_list.takeItem(row)
            self._refresh_cell_for_date(self._selected_date)
            self._update_count()
        except (sqlite3.Error, OSError, ValueError):
            InfoBar.error(
                title="삭제 오류",
                content="일정 삭제 중 오류가 발생했습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )

    def _on_add_schedule(self):
        if self._is_locked:
            return
        text = self.schedule_input.text().strip()
        if not text or not self._selected_date:
            return
        try:
            new_id = db.add_schedule(self._selected_date, text, self._schedule_color)
            self._add_schedule_item(new_id, text, color=self._schedule_color)
            self.schedule_input.clear()
            self._refresh_cell_for_date(self._selected_date)
            self._update_count()
        except (sqlite3.Error, OSError, ValueError):
            InfoBar.error(
                title="저장 오류",
                content="일정 저장 중 오류가 발생했습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )

    def _on_edit_schedule(self, item: QListWidgetItem):
        """더블클릭 → 인라인 편집 모드"""
        if self._is_locked:
            return
        # 이미 편집 중이면 기존 편집을 저장 후 종료
        if self._editing_item is not None:
            if self._finish_current_edit:
                self._finish_current_edit(True)
            if self._editing_item is not None:
                return
        schedule_id = item.data(Qt.UserRole)
        old_text = item.data(Qt.UserRole + 1)
        color = item.data(Qt.UserRole + 2)
        if not schedule_id or not old_text:
            return

        self._editing_item = item
        row_widget = self.schedule_list.itemWidget(item)
        if not row_widget:
            self._editing_item = None
            return
        layout = row_widget.layout()

        # text_label(index 1)을 숨기고 LineEdit 삽입
        text_label = layout.itemAt(1).widget()
        text_label.hide()

        edit = QLineEdit(row_widget)
        edit.setText(old_text)
        edit.setAttribute(Qt.WA_InputMethodEnabled, True)
        edit.setStyleSheet("background: #FFF; border: 1px solid #0078D4; border-radius: 3px; padding: 1px 4px;")
        layout.insertWidget(2, edit, 1)
        edit.setFocus()
        edit.selectAll()

        def _finish_edit(save: bool):
            if self._editing_item is not item:
                return
            self._editing_item = None
            self._finish_current_edit = None
            new_text = edit.text().strip()
            # LineEdit 제거, 라벨 복원
            edit.hide()
            layout.removeWidget(edit)
            edit.deleteLater()
            text_label.show()

            if save and new_text and new_text != old_text:
                try:
                    db.update_schedule(schedule_id, content=new_text)
                    text_label.setText(new_text)
                    item.setData(Qt.UserRole + 1, new_text)
                    self._refresh_cell_for_date(self._selected_date)
                except (sqlite3.Error, OSError, ValueError):
                    InfoBar.error(
                        title="수정 오류",
                        content="일정 수정 중 오류가 발생했습니다.",
                        parent=self,
                        position=InfoBarPosition.BOTTOM,
                        duration=3000,
                    )

        self._finish_current_edit = _finish_edit

        edit.returnPressed.connect(lambda: _finish_edit(True))

        # Escape 키 처리
        orig_key = edit.keyPressEvent
        def _key_press(event):
            if event.key() == Qt.Key_Escape:
                _finish_edit(False)
            else:
                orig_key(event)
        edit.keyPressEvent = _key_press

        # 포커스 잃으면 저장
        def _focus_out(e):
            _finish_edit(True)
            QLineEdit.focusOutEvent(edit, e)
        edit.focusOutEvent = _focus_out

    def _update_count(self):
        n = self.schedule_list.count()
        self.count_label.setText(f"총 {n}개" if n > 0 else "")

    def _update_schedule_color_btn(self):
        self.schedule_color_btn.set_color(
            db.schedule_display_color(self._schedule_color)
        )

    def _on_cycle_schedule_color(self):
        colors = [c[0] for c in db.SCHEDULE_COLORS]
        try:
            idx = colors.index(self._schedule_color)
            self._schedule_color = colors[(idx + 1) % len(colors)]
        except ValueError:
            self._schedule_color = colors[0]
        self._update_schedule_color_btn()

    # ─── 오늘로 이동 ─────────────────────────────────────────────
    def _on_today(self):
        today = date.today()
        self._today = today.isoformat()
        self._current_year = today.year
        self._current_month = today.month
        self._refresh_calendar()
        self._on_date_selected(today.isoformat())

    def _sync_to_today_if_changed(self):
        """트레이에서 다시 보일 때, 날짜가 바뀌었으면 오늘로 이동한다.

        오늘 계산은 __init__에서 1회만 하므로, 트레이 상주 앱이 자정을 넘기면
        캘린더가 어제에 박제된다. 다시 보이는 시점에 재동기화한다.
        같은 날이면 사용자가 보던 달을 그대로 둔다.
        """
        if date.today().isoformat() != self._today:
            self._on_today()

    def _check_day_rollover(self):
        """표시 중 자정을 넘기면 오늘 하이라이트만 조용히 갱신(보던 달·선택 유지).

        숨김 상태에서는 아무 것도 하지 않아 _today를 어제로 남겨둔다 →
        다음에 다시 보일 때 _sync_to_today_if_changed()가 오늘로 이동시킨다.
        """
        if not self.isVisible():
            return
        today = date.today().isoformat()
        if today != self._today:
            self._today = today
            self._refresh_calendar()

    def _check_daily_auto_backup(self):
        """트레이 상주 중 날짜가 바뀌면 최신 저장 뒤 일일 묶음을 만든다."""
        today = date.today().isoformat()
        if today == self._last_auto_backup_date:
            return
        if not self.save_all_sticky_notes():
            self.status_label.setText("자동백업 보류: 스티키 저장 실패")
            return
        if db.backup_database():
            self._last_auto_backup_date = today
            return
        self.status_label.setText("자동백업을 만들지 못했습니다")

    # ─── 이전/다음 달 ───────────────────────────────────────────
    def _on_prev_month(self):
        if self._current_month == 1:
            self._current_year -= 1
            self._current_month = 12
        else:
            self._current_month -= 1
        self._refresh_calendar()

    def _on_next_month(self):
        if self._current_month == 12:
            self._current_year += 1
            self._current_month = 1
        else:
            self._current_month += 1
        self._refresh_calendar()

    # ─── 주기적 자동 저장 ─────────────────────────────────────────
    def _periodic_save(self):
        """30초마다 열린 모든 스티키 노트 자동 저장"""
        saved = False
        error_occurred = False
        for win in list(self._sticky_windows.values()):
            try:
                if win.isVisible():
                    win.save()
                    saved = True
            except (RuntimeError, OSError, ValueError):
                error_occurred = True

        if saved:
            self.status_label.setText("자동 저장 중...")
            QTimer.singleShot(3000, lambda: self.status_label.setText(""))
        
        if error_occurred:
            self.status_label.setText("자동 저장 기능 비활성화")
            self.status_label.setStyleSheet("color: #DC3545;")
            QTimer.singleShot(5000, self._reset_status_label)

    def _reset_status_label(self):
        self.status_label.setText("")
        self.status_label.setStyleSheet("color: #0078D4;")

    # ─── 추가 메뉴 (스티키 노트 / D-Day / 집중 모드) ─────────────
    def _build_add_menu(self) -> "RoundMenu":
        menu = RoundMenu(parent=self)
        menu.setWindowOpacity(1.0)
        self._apply_header_menu_style(menu)
        menu.addAction(self._make_menu_action(menu, "note_color", "스티키 노트", self._on_new_sticky_note))
        menu.addAction(self._make_menu_action(menu, "calendar_color", "D-Day 위젯", self._on_new_dday_widget))
        menu.addAction(self._make_menu_action(menu, "timer_color", "집중 모드", self._on_new_focus_widget))
        return menu

    def _on_add_menu(self):
        menu = self._build_add_menu()
        pos = self._add_btn.mapToGlobal(QPoint(0, self._add_btn.height()))
        menu.exec(pos)

    # ─── 스티키 노트 ────────────────────────────────────────────
    def _on_new_sticky_note(self):
        if self._is_locked:
            return
        from ui_sticky import StickyNoteWindow
        # 최대 10개 제한
        open_count = len([w for w in self._sticky_windows.values() if w.isVisible()])
        if open_count >= 10:
            InfoBar.warning(
                title="노트 제한",
                content="스티키 노트는 최대 10개까지 생성할 수 있습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
            return
        # 색상 순환 (열린 노트 수 기준)
        color_idx = open_count % len(STICKY_COLORS)
        color = STICKY_COLORS[color_idx][0]
        # 위치 오프셋 (겹침 방지)
        offset = open_count * 30
        note_id = db.create_sticky_note("memo", x=200 + offset, y=200 + offset, color=color)
        note_data = {
            "type": "memo", "content": "",
            "x_pos": 200 + offset, "y_pos": 200 + offset,
            "width": WIDGET_WIDTH, "height": DDAY_HEIGHT * 2 + StickyNoteWindow._snap_px(),
            "is_open": 1, "is_pinned": 0,
            "color": color,
        }
        win = StickyNoteWindow(note_id, note_data)
        win.note_closed.connect(self._on_sticky_note_closed)
        self._register_floating_widget(win)
        self._sticky_windows[note_id] = win
        self._show_floating_widget(win)
        if self._sticky_in_panel_mode:
            win.hide()
            if self._sticky_side_panel is not None:
                self._sticky_side_panel.reload()

    def _load_open_sticky_notes(self):
        from ui_sticky import StickyNoteWindow
        try:
            notes = db.get_open_sticky_notes()
            factor = self._get_app_opacity()
            for note in notes:
                if note["id"] in self._sticky_windows:
                    continue  # 기존 편집 원본과 대기 중인 자동저장을 유지한다.
                win = StickyNoteWindow(note["id"], note)
                win.note_closed.connect(self._on_sticky_note_closed)
                self._register_floating_widget(win, factor)
                self._sticky_windows[note["id"]] = win
                self._show_floating_widget(win)
        except (sqlite3.Error, OSError) as e:
            _logger.error("스티키 노트 로드 실패: %s", e)

    def _on_sticky_note_closed(self, note_id: int):
        """스티키 노트 삭제 시 참조 정리 (메모리 해제)"""
        win = self._sticky_windows.pop(note_id, None)
        if win:
            win.deleteLater()

    def _on_open_trash(self):
        """휴지통 창 열기(단일 인스턴스 재사용)."""
        if self._is_locked:
            return
        from ui_trash import StickyTrashWindow
        if self._trash_window is None or not self._trash_window.isVisible():
            if self._trash_window is not None:
                self._trash_window.deleteLater()
            self._trash_window = StickyTrashWindow()
            self._trash_window.restore_requested.connect(self._restore_sticky_note)
        else:
            self._trash_window._refresh()
        self._trash_window.show()
        self._trash_window.raise_()

    def _restore_sticky_note(self, note_id: int):
        """휴지통에서 복구: db 복구 후 원위치에 노트 창 재생성."""
        if self._is_locked:
            return
        from ui_sticky import StickyNoteWindow
        db.restore_sticky_note(note_id)
        if note_id in self._sticky_windows:
            return
        note = next((n for n in db.get_open_sticky_notes() if n["id"] == note_id), None)
        if note is None:
            return
        win = StickyNoteWindow(note_id, note)
        win.note_closed.connect(self._on_sticky_note_closed)
        self._register_floating_widget(win)
        self._sticky_windows[note_id] = win
        self._show_floating_widget(win)
        if self._sticky_in_panel_mode:
            win.hide()
            if self._sticky_side_panel is not None:
                self._sticky_side_panel.reload()

    def _show_sticky_handoff_error(self):
        InfoBar.error(
            title="스티키 전환 보류",
            content="스티키 노트를 저장하지 못해 보기 전환을 완료하지 않았습니다. 잠시 후 다시 시도해 주세요.",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000,
        )

    def _apply_sticky_side_panel(self, large: bool) -> bool:
        """최신 원본 저장에 성공한 뒤에만 플로팅/패널 소유권을 넘긴다."""
        if large and not self._sticky_in_panel_mode:
            if not self.save_all_sticky_notes():
                self._show_sticky_handoff_error()
                return False
            if self._sticky_side_panel is None:
                from ui_sticky_panel import StickySidePanel
                self._sticky_side_panel = StickySidePanel(self._expanded_row)
                self._sticky_side_panel.note_trashed.connect(self._on_panel_note_trashed)
            # 진입 직전까지는 플로팅 창이 단일 최신 원본이다. 재사용 패널의
            # 오래된 카드가 DB를 다시 쓰지 않도록 flush 없이 새로 읽는다.
            if not self._sticky_side_panel.reload(flush_pending=False):
                self._show_sticky_handoff_error()
                return False
            for win in self._sticky_windows.values():
                win.hide()
            self._sticky_in_panel_mode = True
        elif not large and self._sticky_in_panel_mode:
            if not self.save_all_sticky_notes():
                self._show_sticky_handoff_error()
                return False
            if not self._restore_floating_sticky_content():
                self._show_sticky_handoff_error()
                return False
            if self._sticky_side_panel is not None:
                if self._expanded_row is not None and self._expanded_row.layout() is not None:
                    self._expanded_row.layout().removeWidget(self._sticky_side_panel)
                self._sticky_side_panel.hide()
                self._sticky_side_panel.setParent(None)
            if self.isVisible() and not self._is_locked:
                for win in self._sticky_windows.values():
                    win.show()
            self._sticky_in_panel_mode = False

        # 일정 패널은 _reparent_schedule_panel에서 매번 재부착되므로, large에서는
        # 스티키 패널을 항상 그 뒤(아래)로 재배치해 카드 순서를
        # [일정(우상단) → 스티키(우하단)]로 고정한다. (재적용 시 순서 뒤바뀜 방지)
        if large and self._sticky_side_panel is not None and self._expanded_row is not None:
            layout = self._expanded_row.layout()
            if layout is not None:
                self._sticky_side_panel.setParent(self._expanded_row)
                layout.removeWidget(self._sticky_side_panel)
                # [일정 : 스티키] = 3 : 7 (스티키 영역을 일정보다 넓게)
                layout.addWidget(self._sticky_side_panel, 7)
                self._sticky_side_panel.show()
        return True

    def _on_panel_note_trashed(self, note_id: int):
        win = self._sticky_windows.pop(note_id, None)
        if win is not None:
            try:
                win.note_closed.disconnect()
            except (TypeError, RuntimeError) as e:
                _logger.debug("패널 휴지통 정리 중 note_closed 연결 해제 생략: %s", e)
            win.close()
            win.deleteLater()

    def _restore_floating_sticky_content(self) -> bool:
        """플로팅 스티키 창 본문을 DB 최신값으로 재로드한다."""
        try:
            notes = {n["id"]: n for n in db.get_open_sticky_notes()}
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.warning("스티키 재로드 실패: %s", e)
            return False
        try:
            for note_id, win in self._sticky_windows.items():
                note = notes.get(note_id)
                if note is None:
                    continue
                content = note["content"]
                win.text_edit.blockSignals(True)
                try:
                    if content.strip().startswith("<"):
                        win.text_edit.setHtml(content)
                    else:
                        win.text_edit.setPlainText(content)
                finally:
                    win.text_edit.blockSignals(False)
        except (RuntimeError, OSError, ValueError) as e:
            _logger.warning("스티키 플로팅 창 본문 적용 실패: %s", e)
            return False
        return True

    def _apply_dday_side_panel(self, large: bool):
        if large and not self._dday_in_panel_mode:
            for win in self._dday_windows.values():
                win.hide()
            if self._dday_side_panel is None:
                from ui_dday_panel import DDaySidePanel
                self._dday_side_panel = DDaySidePanel(self._expanded_row)
                self._dday_side_panel.edit_requested.connect(self._on_panel_dday_edit)
                self._dday_side_panel.delete_requested.connect(self._on_panel_dday_delete)
                self._dday_side_panel.create_requested.connect(self._on_new_dday_widget)
            self._refresh_dday_panel()
            self._dday_in_panel_mode = True
        elif not large and self._dday_in_panel_mode:
            if self._dday_side_panel is not None:
                if self._expanded_row is not None and self._expanded_row.layout() is not None:
                    self._expanded_row.layout().removeWidget(self._dday_side_panel)
                self._dday_side_panel.hide()
                self._dday_side_panel.setParent(None)
            if self.isVisible() and not self._is_locked:
                for win in self._dday_windows.values():
                    win.show()
            self._dday_in_panel_mode = False

        if large and self._dday_side_panel is not None and self._expanded_row is not None:
            layout = self._expanded_row.layout()
            if layout is not None:
                self._dday_side_panel.setParent(self._expanded_row)
                layout.removeWidget(self._dday_side_panel)
                layout.addWidget(self._dday_side_panel, 0)
                self._dday_side_panel.show()

    def _refresh_dday_panel(self):
        if self._dday_side_panel is not None:
            self._dday_side_panel.reload()

    def _on_panel_dday_edit(self, widget_id: int):
        """미니 D-Day 카드 더블클릭 → 편집 다이얼로그."""
        win = self._dday_windows.get(widget_id)
        if win is None:
            return
        from ui_dday import DDayCreateDialog
        dlg = DDayCreateDialog(self, win._name, win._target_date)
        if dlg.exec() == QDialog.Accepted:
            name, target_date = dlg.get_result()
            win._name = name
            win._target_date = target_date
            win.name_label.setText(name)
            win._update_countdown()
            db.update_dday_widget(widget_id, name=name, target_date=target_date)
            self._refresh_dday_panel()
        dlg.deleteLater()

    def _on_panel_dday_delete(self, widget_id: int):
        """미니 D-Day 카드 X → 확인 후 영구 삭제(숨은 플로팅 창 정리 포함)."""
        from qfluentwidgets import Dialog
        dlg = Dialog("삭제 확인", "이 D-Day를 삭제하시겠습니까?", self)
        dlg.yesButton.setText("삭제")
        dlg.cancelButton.setText("취소")
        confirmed = dlg.exec()
        dlg.deleteLater()  # 0026_RESLEAK
        if not confirmed:
            return
        try:
            db.delete_dday_widget(widget_id)
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("미니 D-Day 삭제 실패: %s", e)
            return
        win = self._dday_windows.get(widget_id)
        if win is not None:
            win._refresh_timer.stop()
        self._on_dday_widget_closed(widget_id)  # 레지스트리 pop + deleteLater
        self._refresh_dday_panel()

    def _apply_focus_side_panel(self, large: bool):
        if large and not self._focus_in_panel_mode:
            for win in self._focus_windows.values():
                win.hide()
            if self._focus_side_panel is None:
                from ui_focus_panel import FocusSidePanel
                self._focus_side_panel = FocusSidePanel(self._expanded_row)
                self._focus_side_panel.close_requested.connect(self._on_panel_focus_close)
            self._refresh_focus_panel()
            self._focus_in_panel_mode = True
        elif not large and self._focus_in_panel_mode:
            if self._focus_side_panel is not None:
                self._focus_side_panel.clear()
                if self._expanded_row is not None and self._expanded_row.layout() is not None:
                    self._expanded_row.layout().removeWidget(self._focus_side_panel)
                self._focus_side_panel.hide()
                self._focus_side_panel.setParent(None)
            if self.isVisible() and not self._is_locked:
                for win in self._focus_windows.values():
                    win.show()
            self._focus_in_panel_mode = False

        if large and self._focus_side_panel is not None and self._expanded_row is not None:
            layout = self._expanded_row.layout()
            if layout is not None:
                self._focus_side_panel.setParent(self._expanded_row)
                layout.removeWidget(self._focus_side_panel)
                layout.addWidget(self._focus_side_panel, 0)
                self._focus_side_panel.show()

    def _refresh_focus_panel(self):
        if self._focus_side_panel is None:
            return
        source = next(iter(self._focus_windows.values()), None)
        if source is not None:
            self._focus_side_panel.bind(source)
        else:
            self._focus_side_panel.clear()

    def _on_panel_focus_close(self):
        """집중 미니카드 X → 확인 후 단일 집중 세션 종료."""
        source = next(iter(self._focus_windows.values()), None)
        if source is None:
            return
        from qfluentwidgets import Dialog
        dlg = Dialog("종료 확인", "집중 모드를 종료하시겠습니까?", self)
        dlg.yesButton.setText("종료")
        dlg.cancelButton.setText("취소")
        confirmed = dlg.exec()
        dlg.deleteLater()  # 0026_RESLEAK
        if not confirmed:
            return
        # 플로팅 창의 종료 경로 재사용: 타이머 정지 + DB 삭제 + widget_closed(→레지스트리 pop)
        source._on_close()
        if self._focus_side_panel is not None:
            self._focus_side_panel.clear()

    # ─── D-Day 위젯 ────────────────────────────────────────────
    def _focus_at_limit(self) -> bool:
        return len(self._focus_windows) >= 1

    def _dday_at_limit(self) -> bool:
        return len(self._dday_windows) >= 5

    def _on_new_dday_widget(self):
        if self._is_locked:
            return
        from ui_dday import DDayCreateDialog, DDayWidgetWindow
        if self._dday_at_limit():
            InfoBar.warning(
                title="위젯 제한",
                content="D-Day 위젯은 최대 5개까지 만들 수 있습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
            return

        open_count = len(self._dday_windows)
        dlg = DDayCreateDialog(self)
        if dlg.exec() and not self._is_locked:
            name, target_date = dlg.get_result()
            offset = open_count * 30
            color_idx = open_count % len(STICKY_COLORS)
            color = STICKY_COLORS[color_idx][0]
            widget_id = db.create_dday_widget(name, target_date, x=100 + offset, y=100 + offset, color=color)
            data = {
                "name": name, "target_date": target_date,
                "x_pos": 100 + offset, "y_pos": 100 + offset,
                "is_open": 1, "color": color,
            }
            win = DDayWidgetWindow(widget_id, data)
            win.widget_closed.connect(self._on_dday_widget_closed)
            self._register_floating_widget(win)
            self._dday_windows[widget_id] = win
            if self._dday_in_panel_mode:
                win.hide()
                self._refresh_dday_panel()
            else:
                QTimer.singleShot(0, lambda: self._show_floating_widget(win))

    def _load_open_dday_widgets(self):
        from ui_dday import DDayWidgetWindow
        try:
            widgets = db.get_open_dday_widgets()
            factor = self._get_app_opacity()
            for w in widgets:
                if w["id"] in self._dday_windows:
                    continue
                win = DDayWidgetWindow(w["id"], w)
                win.widget_closed.connect(self._on_dday_widget_closed)
                self._register_floating_widget(win, factor)
                if self._dday_in_panel_mode:
                    win.hide()
                else:
                    QTimer.singleShot(0, lambda _w=win: self._show_floating_widget(_w))
                self._dday_windows[w["id"]] = win
        except (sqlite3.Error, OSError) as e:
            _logger.error("D-Day 위젯 로드 실패: %s", e)
        if self._dday_in_panel_mode:
            for win in self._dday_windows.values():
                win.hide()
            self._refresh_dday_panel()

    def _on_dday_widget_closed(self, widget_id: int):
        win = self._dday_windows.pop(widget_id, None)
        if win:
            win.deleteLater()

    # ─── 집중 모드 위젯 ─────────────────────────────────────────
    def _on_new_focus_widget(self):
        if self._is_locked:
            return
        from ui_focus import FocusCreateDialog, FocusWidgetWindow
        if self._focus_at_limit():
            InfoBar.warning(
                title="위젯 제한",
                content="집중 모드는 1개만 사용할 수 있습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )
            return

        open_count = len(self._focus_windows)
        dlg = FocusCreateDialog(self)
        if dlg.exec() == QDialog.Accepted and not self._is_locked:
            goal, mode_key, start_now = dlg.get_result()
            offset = open_count * 30
            widget_id = db.create_focus_widget(goal, mode_key, x=140 + offset, y=140 + offset)
            label, focus_minutes, break_minutes = db.FOCUS_MODES.get(mode_key, db.FOCUS_MODES[db.DEFAULT_FOCUS_MODE])
            data = {
                "goal": goal,
                "mode_key": mode_key,
                "focus_minutes": focus_minutes,
                "break_minutes": break_minutes,
                "x_pos": 140 + offset,
                "y_pos": 140 + offset,
                "is_open": 1,
                "is_pinned": 0,
            }
            win = FocusWidgetWindow(widget_id, data, auto_start=start_now)
            win.widget_closed.connect(self._on_focus_widget_closed)
            self._register_floating_widget(win)
            self._focus_windows[widget_id] = win
            if self._focus_in_panel_mode:
                win.hide()
                self._refresh_focus_panel()
            else:
                QTimer.singleShot(0, lambda: self._show_floating_widget(win))

    def _load_open_focus_widgets(self):
        from ui_focus import FocusWidgetWindow
        try:
            widgets = db.get_open_focus_widgets()
            factor = self._get_app_opacity()
            for w in widgets:
                if w["id"] in self._focus_windows:
                    continue  # 실행 중인 집중 세션을 idle 인스턴스로 교체하지 않는다.
                win = FocusWidgetWindow(w["id"], w)
                win.widget_closed.connect(self._on_focus_widget_closed)
                self._register_floating_widget(win, factor)
                if self._focus_in_panel_mode:
                    win.hide()
                else:
                    QTimer.singleShot(0, lambda _w=win: self._show_floating_widget(_w))
                self._focus_windows[w["id"]] = win
        except (sqlite3.Error, OSError) as e:
            _logger.error("집중 모드 위젯 로드 실패: %s", e)
        if self._focus_in_panel_mode:
            for win in self._focus_windows.values():
                win.hide()
            self._refresh_focus_panel()

    def _on_focus_widget_closed(self, widget_id: int):
        win = self._focus_windows.pop(widget_id, None)
        if win:
            win.deleteLater()

    def _warn_widget_trim(self):
        """업그레이드 시 상한 초과 위젯을 정리했음을 모달로 안내."""
        focus_n = self._widget_trim_result.get("focus", 0)
        dday_n = self._widget_trim_result.get("dday", 0)
        parts = []
        if focus_n:
            parts.append(f"집중 모드 {focus_n}개")
        if dday_n:
            parts.append(f"D-Day {dday_n}개")
        if not parts:
            return
        from qfluentwidgets import Dialog
        body = (
            "이전 버전에서 만든 위젯이 많아 일부를 정리했습니다.\n"
            f"{' · '.join(parts)}를 닫았습니다(집중 1개·D-Day 최신 5개만 표시).\n"
            "닫힌 위젯의 데이터는 보존됩니다."
        )
        dlg = Dialog("위젯 정리 안내", body, self)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.cancelButton.hide()
        dlg.yesButton.setText("확인")
        dlg.exec()
        try:
            dlg.deleteLater()
        except RuntimeError as e:
            _logger.debug("위젯 정리 안내 다이얼로그 정리 생략: %s", e)

    # ─── 스티키 노트 자동 정렬 ────────────────────────────────────
    def _on_arrange_sticky_notes(self):
        """열린 모든 플로팅 위젯을 캘린더 바깥 기준 그리드 배열 (5mm 스냅)"""
        visible_sticky = sorted(
            (w for w in self._sticky_windows.values() if w.isVisible()),
            key=lambda w: w.height(),
            reverse=True,
        )
        visible_dday = [w for w in self._dday_windows.values() if w.isVisible()]
        visible_focus = [w for w in self._focus_windows.values() if w.isVisible()]
        # D-Day(95px)·집중(78px)은 높이 고정이므로 height 정렬 불필요 — DB 생성 순서(id) 유지
        visible = visible_dday + visible_focus + visible_sticky

        if not visible:
            InfoBar.info(
                title="정렬",
                content="열린 노트/위젯이 없습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=2000,
            )
            return

        scr = QApplication.screenAt(self.frameGeometry().center()) or self._get_target_screen()
        snap = max(1, round(scr.physicalDotsPerInch() * 5 / 25.4)) if scr else 19
        screen_geo = scr.availableGeometry() if scr else QApplication.primaryScreen().availableGeometry()
        if screen_geo is None:
            return

        cal = (
            self.x(),
            self.y(),
            self.x() + self.width(),
            self.y() + self.height(),
        )
        scr_tuple = (
            screen_geo.left(), screen_geo.top(),
            screen_geo.left() + screen_geo.width(),
            screen_geo.top() + screen_geo.height(),
        )
        pos = _nearest_corner_for_rect(cal, scr_tuple)
        items = [(w.width(), w.height()) for w in visible]

        coords, skipped = _compute_arrange_layout(items, cal, scr_tuple, pos, snap)

        for win, xy in zip(visible, coords):
            if xy is None:
                continue  # 공간 부족으로 정렬 제외 — 제자리 유지(겹침 방지)
            x, y = xy
            win.move(x, y)
            if hasattr(win, "note_id"):
                db.update_sticky_note(win.note_id, x_pos=x, y_pos=y)
            elif win in self._dday_windows.values():
                db.update_dday_widget(win.widget_id, x_pos=x, y_pos=y)
            elif win in self._focus_windows.values():
                db.update_focus_widget(win.widget_id, x_pos=x, y_pos=y)

        if skipped > 0:
            InfoBar.warning(
                title="정렬",
                content=f"공간이 부족해 {skipped}개 위젯은 정렬에서 제외했습니다.",
                parent=self,
                position=InfoBarPosition.BOTTOM,
                duration=3000,
            )

    # ─── 검색 창 ────────────────────────────────────────────────
    def _on_search(self):
        if self._is_locked:
            return
        if self._search_window is None or not self._search_window.isVisible():
            if self._search_window is not None:
                self._search_window.deleteLater()
            self._search_window = SearchWindow()
            self._search_window.date_selected.connect(self._navigate_to_date)
        self._search_window.show()
        self._search_window.raise_()

    def _on_update_guide(self):
        show_update_guide(self)

    def _navigate_to_date(self, date_str: str):
        """검색 결과 클릭 시 해당 날짜로 캘린더 이동"""
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(date_str, "%Y-%m-%d")
            self._current_year = d.year
            self._current_month = d.month
            self._refresh_calendar()
            self._on_date_selected(date_str)
        except ValueError:
            pass

    # ─── 설정 창 ────────────────────────────────────────────────
    def _on_settings(self):
        if self._is_locked:
            return
        from ui_settings import SettingsWindow
        if self._settings_window is None or not self._settings_window.isVisible():
            if self._settings_window is not None:
                self._settings_window.deleteLater()
            self._settings_window = SettingsWindow(
                on_reset_callback=self._on_factory_reset,
                on_import_callback=self._on_import_complete,
                on_quit_callback=self.prepare_for_quit,
                on_lunar_changed=self._refresh_calendar,
                on_law_search_changed=self._on_law_search_changed,
                on_position_changed=self._position_to_corner,
                on_sidebar_changed=self._on_sidebar_setting_changed,
                on_opacity_changed=self._apply_app_opacity,
                on_scale_changed=self._apply_calendar_scale,
                on_keep_changed=self._on_keep_desktop_changed,
                on_schedule_colors_changed=self._on_schedule_colors_changed,
                on_prepare_data_change=self.prepare_for_data_change,
                on_before_reset=self._discard_data_widgets,
            )
        # 스티키/위젯(Qt.Tool)이 앞에 있어도 설정창을 확실히 포그라운드로:
        # raise_()만으로는 Windows에서 활성 창이 바뀌지 않으므로 최소화 해제 + activateWindow.
        win = self._settings_window
        win.show()
        win.setWindowState((win.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        win.raise_()
        win.activateWindow()
        # 달력이 화면 끝 코너에 있을 때 설정창이 화면 밖으로 열려 우측 컬럼이
        # 잘리는 문제 방지: 표시 후 프레임이 화면(작업 영역)을 넘으면 안으로 이동.
        # 프레임 지오메트리가 확정된 뒤 판정하도록 다음 이벤트 루프 턴에 실행.
        QTimer.singleShot(0, lambda: self._clamp_window_to_screen(win)
                          if self._settings_window is win else None)

    def _clamp_window_to_screen(self, win) -> None:
        """top-level 창의 프레임이 현재 화면 작업 영역을 벗어나면 안으로 이동한다."""
        screen = win.screen() or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        fg = win.frameGeometry()
        dx = dy = 0
        if fg.right() > avail.right():
            dx = avail.right() - fg.right()
        if fg.bottom() > avail.bottom():
            dy = avail.bottom() - fg.bottom()
        if fg.left() + dx < avail.left():
            dx = avail.left() - fg.left()
        if fg.top() + dy < avail.top():
            dy = avail.top() - fg.top()
        if dx or dy:
            win.move(win.x() + dx, win.y() + dy)

    def prepare_for_data_change(self) -> bool:
        """가져오기/초기화 보호백업에 현재 모드의 최신 편집을 담는다."""
        return not self._is_locked and self.save_all_sticky_notes()

    def _discard_data_widgets(self) -> None:
        """초기화 전 모든 이전 데이터 편집기/타이머를 정지하고 폐기한다."""
        if self._finish_current_edit:
            self._finish_current_edit(False)
        # 패널은 숨긴 상태에서도 타이머와 플로팅 원본 참조를 갖는다.
        for name in ("sticky", "dday", "focus"):
            panel = getattr(self, f"_{name}_side_panel")
            if panel is not None:
                for timer in panel.findChildren(QTimer):
                    timer.stop()
                panel.hide()
                _detach_from_layout(panel)
                panel.deleteLater()
                setattr(self, f"_{name}_side_panel", None)
            setattr(self, f"_{name}_in_panel_mode", False)
            windows = getattr(self, f"_{name}_windows")
            for win in list(windows.values()):
                for timer in win.findChildren(QTimer):
                    timer.stop()
                win.hide()
                self._show_desktop_keeper.unguard(win)
                win.deleteLater()
            windows.clear()

    def _on_factory_reset(self):
        # 직접 호출에도 안전하고, before_reset에서 이미 폐기했으면 빈 작업이다.
        self._discard_data_widgets()
        self._on_import_complete()
        if self._search_window is not None:
            self._search_window.result_table.setRowCount(0)
            self._search_window.result_count_label.setText("")
        if self._trash_window is not None:
            self._trash_window._refresh()

    def _on_import_complete(self):
        """Import 완료 후 DB 설정과 열린 UI를 즉시 다시 동기화한다."""
        self._show_lunar = (
            db.get_setting(db.SETTING_SHOW_LUNAR, "0") == "1"
        )
        self._apply_calendar_scale()
        self._apply_app_opacity()
        self._on_keep_desktop_changed()
        self._on_law_search_changed()
        self.sidebar.load_shortcuts()
        self._update_schedule_color_btn()
        if self._selected_date:
            self._load_schedules()
        self._load_open_sticky_notes()
        self._load_open_dday_widgets()
        self._load_open_focus_widgets()
        if self._sticky_in_panel_mode and self._sticky_side_panel is not None:
            if not self._sticky_side_panel.reload():
                self._show_sticky_handoff_error()

    def _on_law_search_changed(self):
        """설정에서 법령검색 토글 변경 시 검색바 표시/숨김"""
        visible = db.get_setting(db.SETTING_SHOW_LAW_SEARCH, "1") == "1"
        self.law_search_container.setVisible(visible)

    def _on_schedule_colors_changed(self):
        """일정 슬롯 표시색 변경을 기존 DB 행 수정 없이 즉시 다시 그린다."""
        self._update_schedule_color_btn()
        self._refresh_calendar()

    # ─── 최소화 (트레이) ─────────────────────────────────────────
    def _minimize_to_tray(self):
        self._hidden_to_tray = True
        self.hide()
        for win in self._sticky_windows.values():
            win.hide()
        for win in self._dday_windows.values():
            win.hide()
        for win in self._focus_windows.values():
            win.hide()

    # ─── 보스 키: 숨김/복원 ─────────────────────────────────────
    def toggle_visibility(self):
        if self.isVisible():
            self._minimize_to_tray()
        else:
            self._hidden_to_tray = False
            self.show()
            self._sync_to_today_if_changed()
            for windows in (self._sticky_windows, self._dday_windows, self._focus_windows):
                for win in windows.values():
                    self._show_floating_widget(win)

    # ─── 종료 시 전체 저장 ─────────────────────────────────────
    def save_all_sticky_notes(self) -> bool:
        """최신 편집 원본을 즉시 저장하고 전체 성공 여부를 반환한다."""
        if self._sticky_in_panel_mode:
            if self._sticky_side_panel is None:
                _logger.error("스티키 패널 모드인데 패널이 없어 종료 저장을 중단합니다")
                return False
            try:
                return bool(self._sticky_side_panel.save_all())
            except (RuntimeError, sqlite3.Error, OSError, ValueError) as e:
                _logger.error("스티키 패널 종료 저장 실패: %s", e)
                return False

        all_saved = True
        for win in list(self._sticky_windows.values()):
            try:
                if not win.save():
                    all_saved = False
            except (RuntimeError, sqlite3.Error, OSError, ValueError) as e:
                all_saved = False
                _logger.error(
                    "스티키 노트 종료 저장 실패 (id=%s): %s",
                    getattr(win, "note_id", "?"),
                    e,
                )
        return all_saved

    def prepare_for_quit(self) -> bool:
        """정상 종료 전에 스티키 저장을 확정하고 실패하면 종료를 보류한다."""
        if self.save_all_sticky_notes():
            return True
        _logger.error("스티키 노트 저장 실패로 앱 종료를 보류합니다")
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        InfoBar.error(
            title="종료하지 않았습니다",
            content="스티키 노트를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000,
        )
        return False

    def _get_target_screen(self):
        """환경설정에 지정된 타겟 모니터 객체를 반환합니다. (범위 초과 시 메인 모니터)"""
        screens = QApplication.screens()
        try:
            target_idx = int(db.get_setting(db.SETTING_TARGET_SCREEN, "0"))
            if 0 <= target_idx < len(screens):
                return screens[target_idx]
        except ValueError:
            pass
        return QApplication.primaryScreen()

    # ─── 모서리 고정 배치 ─────────────────────────────────────────
    def _position_to_corner(self):
        """설정된 모서리 위치로 지정된 화면의 모서리에 캘린더 배치 (5mm 스냅 그리드 적용)"""
        screen = self._get_target_screen()
        if not screen:
            return
        pos = db.get_setting(db.SETTING_CALENDAR_POSITION, "bottom-right")
        x, y = _calendar_corner_coordinates(screen, self.width(), self.height(), pos)
        self.move(x, y)
        db.save_setting(db.SETTING_CALENDAR_X, str(x))
        db.save_setting(db.SETTING_CALENDAR_Y, str(y))
        db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "corner")

    def _watch_screen_geometry(self, screen) -> None:
        """새로 연결된 화면까지 geometryChanged 감시에 포함한다."""
        screen_id = id(screen)
        if screen_id in self._watched_screen_ids:
            return
        self._watched_screen_ids.add(screen_id)
        screen.geometryChanged.connect(
            lambda *_args: self._screen_change_timer.start()
        )
        screen.availableGeometryChanged.connect(
            lambda *_args: self._screen_change_timer.start()
        )

    def _on_screen_added(self, screen) -> None:
        self._watch_screen_geometry(screen)
        self._screen_change_timer.start()

    def _on_screen_removed(self, screen) -> None:
        self._watched_screen_ids.discard(id(screen))
        self._screen_change_timer.start()

    def _on_screen_changed(self):
        """화면 구성 변경 시 모든 창의 위치를 DB 저장값으로 복원하고, 화면 밖이면 보정"""
        screens = QApplication.screens()
        if not screens:
            return

        # 1) 캘린더 기하 복원. 자유 위치는 저장 좌표, 기존 사용자는 모서리 설정 유지.
        # medium/large는 화면 크기에 비례하는 스케일이므로 좌표만 보정하면
        # 가로 모니터 크기로 만든 창이 세로 모니터에서 우·하단이 잘린다
        # (KVM 본체 전환으로 모니터가 끊겼다 붙을 때 실제로 발생). 드래그
        # 완료와 같은 규칙으로 목적지 화면 기준 크기를 먼저 다시 계산한다.
        screen = self._get_target_screen()
        if screen is not None:
            scale = self._current_calendar_scale()
            width, height = self._calendar_scale_geometry(scale, screen)
            if scale != "compact":
                # 축소된 화면으로 옮길 때 최소 폭이 새 폭을 막지 않도록
                # _apply_calendar_scale과 같은 기준으로 다시 잡는다.
                self.setMinimumSize(min(width, 600), 500)
            self._apply_calendar_geometry(width, height, screen)

        # 2) 스티키 노트 위치 복원
        try:
            notes = db.get_open_sticky_notes()
            note_map = {n["id"]: n for n in notes}
        except (sqlite3.Error, OSError) as e:
            _logger.warning("스티키 노트 목록 조회 실패: %s", e)
            note_map = {}
        for note_id, win in self._sticky_windows.items():
            note_data = note_map.get(note_id)
            if note_data:
                win.move(note_data["x_pos"], note_data["y_pos"])
            if _clamp_window_to_available_screens(win, screens):
                try:
                    db.update_sticky_note(note_id, x_pos=win.x(), y_pos=win.y())
                except (sqlite3.Error, OSError) as e:
                    _logger.warning("스티키 노트 위치 보정 저장 실패 (id=%s): %s", note_id, e)

        # 3) D-Day 위젯 위치 복원
        try:
            widgets = db.get_open_dday_widgets()
            widget_map = {w["id"]: w for w in widgets}
        except (sqlite3.Error, OSError) as e:
            _logger.warning("D-Day 위젯 목록 조회 실패: %s", e)
            widget_map = {}
        for widget_id, win in self._dday_windows.items():
            widget_data = widget_map.get(widget_id)
            if widget_data:
                win.move(widget_data["x_pos"], widget_data["y_pos"])
            if _clamp_window_to_available_screens(win, screens):
                try:
                    db.update_dday_widget(widget_id, x_pos=win.x(), y_pos=win.y())
                except (sqlite3.Error, OSError) as e:
                    _logger.warning("D-Day 위젯 위치 보정 저장 실패 (id=%s): %s", widget_id, e)

        # 4) 집중 모드 위젯 위치 복원
        try:
            focus_widgets = db.get_open_focus_widgets()
            focus_map = {w["id"]: w for w in focus_widgets}
        except (sqlite3.Error, OSError) as e:
            _logger.warning("집중 모드 위젯 목록 조회 실패: %s", e)
            focus_map = {}
        for widget_id, win in self._focus_windows.items():
            widget_data = focus_map.get(widget_id)
            if widget_data:
                win.move(widget_data["x_pos"], widget_data["y_pos"])
            if _clamp_window_to_available_screens(win, screens):
                try:
                    db.update_focus_widget(widget_id, x_pos=win.x(), y_pos=win.y())
                except (sqlite3.Error, OSError) as e:
                    _logger.warning("집중 모드 위젯 위치 보정 저장 실패 (id=%s): %s", widget_id, e)

    # ─── 잠금 기능 ──────────────────────────────────────────────
    def nativeEvent(self, event_type, message):
        """Windows 이벤트를 직접 가로채서 절전 모드 해제 및 세션 잠금 해제 감지"""
        try:
            if event_type == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))

                should_lock = (
                    (msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMESUSPEND) or
                    (msg.message == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_UNLOCK)
                )
                if should_lock and not self._is_locked:
                    if db.get_setting(db.SETTING_USE_PRIVACY_LOCK, "0") == "1":
                        self._lock()
        except (OSError, ValueError):
            _logger.debug("nativeEvent 처리 중 예외 (PySide6 버전 호환성)")

        return super().nativeEvent(event_type, message)

    def eventFilter(self, obj, event) -> bool:
        """헤더 배경/연월 라벨 드래그로 프레임리스 캘린더를 이동한다."""
        event_type = event.type()
        if event_type in (
            QEvent.Type.WindowDeactivate,
            QEvent.Type.UngrabMouse,
        ):
            self._reset_calendar_drag()

        if obj in self._calendar_drag_targets:
            if (
                self._current_calendar_scale() == "large"
                and event_type in (
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.MouseMove,
                    QEvent.Type.MouseButtonRelease,
                )
            ):
                self._reset_calendar_drag()
                return False
            if (event_type == QEvent.Type.MouseButtonPress
                    and event.button() == Qt.LeftButton):
                press_global = event.globalPosition().toPoint()
                self._calendar_drag_offset = (
                    press_global - self.frameGeometry().topLeft()
                )
                self._calendar_drag_press_global = press_global
                self._calendar_drag_started = False
                event.accept()
                return True
            if (event_type == QEvent.Type.MouseMove
                    and self._calendar_drag_offset is not None
                    and bool(event.buttons() & Qt.LeftButton)):
                current_global = event.globalPosition().toPoint()
                if not self._calendar_drag_started:
                    delta = current_global - self._calendar_drag_press_global
                    if delta.manhattanLength() < QApplication.startDragDistance():
                        event.accept()
                        return True
                    self._calendar_drag_started = True
                new_pos = current_global - self._calendar_drag_offset
                screen = (
                    QApplication.screenAt(current_global)
                    or QApplication.screenAt(new_pos)
                    or self.screen()
                    or self._get_target_screen()
                )
                snap = _snap_px_for_screen(screen)
                new_pos.setX(round(new_pos.x() / snap) * snap)
                new_pos.setY(round(new_pos.y() / snap) * snap)
                self.move(new_pos)
                event.accept()
                return True
            if (event_type == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.LeftButton
                    and self._calendar_drag_offset is not None):
                release_global = event.globalPosition().toPoint()
                did_drag = self._calendar_drag_started
                self._reset_calendar_drag()
                if did_drag:
                    self._finish_calendar_drag(release_global)
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _reset_calendar_drag(self) -> None:
        self._calendar_drag_offset = None
        self._calendar_drag_press_global = None
        self._calendar_drag_started = False

    def _finish_calendar_drag(self, release_global: QPoint | None = None) -> None:
        """목적지 화면 크기에 맞춰 보정한 드래그 위치를 설정에 저장한다."""
        screen = (
            QApplication.screenAt(release_global)
            if release_global is not None else None
        )
        screen = screen or QApplication.screenAt(self.frameGeometry().center())
        screen = screen or self.screen() or self._get_target_screen()
        if screen is None:
            return

        # large/medium은 화면 비율 기반 크기다. 큰 화면에서 만든 창을 작은
        # 보조 모니터로 옮길 때 좌표만 clamp하면 우·하단이 잘리므로 목적지
        # 화면 기준 크기를 먼저 다시 계산한다.
        width, height = self._calendar_scale_geometry(
            self._current_calendar_scale(), screen
        )
        self.resize(width, height)
        width, height = self.width(), self.height()
        x, y = _snap_calendar_xy(
            self.x(), self.y(), width, height,
            screen.availableGeometry(),
            _snap_px_for_screen(screen),
        )
        self.move(x, y)

        screens = QApplication.screens()
        try:
            screen_index = screens.index(screen)
        except ValueError:
            screen_index = 0

        geo = screen.availableGeometry()
        calendar_rect = (x, y, x + self.width(), y + self.height())
        screen_rect = (
            geo.left(), geo.top(),
            geo.left() + geo.width(), geo.top() + geo.height(),
        )
        nearest_corner = _nearest_corner_for_rect(calendar_rect, screen_rect)

        try:
            # mode는 마지막에 기록한다. 좌표 저장 중 중단돼도 기존 corner 동작이 남는다.
            db.save_setting(db.SETTING_CALENDAR_X, str(x))
            db.save_setting(db.SETTING_CALENDAR_Y, str(y))
            db.save_setting(db.SETTING_TARGET_SCREEN, str(screen_index))
            db.save_setting(db.SETTING_CALENDAR_POSITION, nearest_corner)
            db.save_setting(db.SETTING_CALENDAR_POSITION_MODE, "free")
        except (sqlite3.Error, OSError, ValueError) as e:
            _logger.error("캘린더 위치 저장 실패: %s", e)

    def _lock(self):
        self._is_locked = True
        # 잠금 당시 실행 중인 파일/확인 대화상자는 취소한다.
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.reject()
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
        for win in (self._search_window, self._settings_window, self._trash_window):
            if win is not None:
                win.setEnabled(False)
                win.hide()
        if not hasattr(self, "lock_overlay"):
            self.lock_overlay = LockOverlay(self.container)
            self.lock_overlay.unlocked.connect(self._unlock)
        
        self.lock_overlay.resize(self.container.size())
        self.lock_overlay.show()
        self.lock_overlay.raise_()

        # 스티키 노트 + D-Day + 집중 모드 위젯 숨김 (개인정보 보호 일관성)
        for win in self._sticky_windows.values():
            win.hide()
        for win in self._dday_windows.values():
            win.hide()
        for win in self._focus_windows.values():
            win.setProperty("privacyLocked", True)
            win._hide_encouragement_bubble()
            win.hide()

    def _unlock(self):
        self._is_locked = False
        if hasattr(self, "lock_overlay"):
            self.lock_overlay.hide()

        for win in (self._search_window, self._settings_window, self._trash_window):
            if win is not None:
                win.setEnabled(True)
        for win in self._focus_windows.values():
            win.setProperty("privacyLocked", False)
        # 보조 창은 사용자가 다시 열고, 위젯은 현재 모드에 맞게 복원한다.
        for windows in (self._sticky_windows, self._dday_windows, self._focus_windows):
            for win in windows.values():
                self._show_floating_widget(win)

    def showEvent(self, event):
        super().showEvent(event)
        if (
            not self._keep_desktop_unavailable_warned
            and self._keep_desktop_enabled()
            and not self._show_desktop_keeper.is_operational()
        ):
            QTimer.singleShot(0, self._warn_keep_desktop_unavailable_once)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "lock_overlay") and self.lock_overlay.isVisible():
            self.lock_overlay.resize(self.container.size())

    def closeEvent(self, event):
        event.ignore()
        self._minimize_to_tray()
