"""화면 글자 따기 사용법 애니메이션. 그림 파일 없이 QPainter 벡터로만 그려 어떤 배율에서도 또렷하다.

세 장면(영역 고르기 → 글자 읽기 → 표로 붙여넣기)을 6초 한 바퀴로 되풀이한다. 위젯이 보일 때만 돌고
(showEvent·hideEvent), 저장·설정·파일·네트워크·로그를 쓰지 않는다. 표본 글자는 모두 꾸며 낸 값이다.
"""
from PySide6.QtCore import QAbstractAnimation, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

DURATION_MS = 6000
SCENE_W, SCENE_H = 420, 190  # 그림 좌표계. 위젯 크기에 맞춰 비율을 지켜 줄이거나 늘린다
CAPTION_H = 46  # 아래 설명 줄과 단계 점이 차지하는 높이
CAPTIONS = (
    "① 끌어서 글자가 있는 영역을 고릅니다",
    "② PC 안에서 글자를 읽습니다 (인터넷 없음)",
    "③ 표 모양 그대로 한글·엑셀에 붙여넣습니다",
)
ROWS = (("구분", "점검", "위반"), ("대전", "42", "3"), ("세종", "18", "1"), ("충북", "51", "4"))
PLACEHOLDER_WIDTHS = ((20, 20, 20), (20, 13, 7), (20, 13, 7), (20, 13, 7))
UNSURE_CELL = (3, 1)  # 3단계에서 노랗게 표시하는 칸(충북의 51)
COLUMNS, ROW_COUNT, CELL_COUNT = 3, 4, 12

CARD_W, CARD_H, CARD_Y = 176, 156, 26
GRID_X, GRID_Y, COL_W, ROW_H = 13, 46, 50, 20  # 카드 안 표 위치(카드 왼쪽 위 기준)와 칸 크기
DOC_CENTER_X, DOC_LEFT_X, SHEET_X = 122, 14, 230

STAGE_BG, STAGE_BORDER = QColor("#F5F7FA"), QColor("#E1E6ED")
CARD_BORDER, LINE, BAR, BAR_STRONG = QColor("#D3DAE4"), QColor("#DCE1E8"), QColor("#D3DAE4"), QColor("#B3BECC")
GRID_BORDER, HEADER_FILL, SHEET_HEADER, STRIP_FILL = QColor("#B3BECC"), QColor("#EEF1F5"), QColor("#EAF2FE"), QColor("#F1F3F7")
INK, STRONG, MUTED = QColor("#253447"), QColor("#172B4D"), QColor("#677180")
ACCENT, ORANGE, YELLOW, AMBER, TAG = QColor("#2563EB"), QColor("#E8590C"), QColor("#FFE58A"), QColor("#E5B93C"), QColor("#8A4B08")
DOT_IDLE, ARROW = QColor("#CDD5E0"), QColor("#91AACA")
CURSOR_SHAPE = ((0, 0), (0, 16), (4.2, 12.2), (7.2, 18.6), (9.8, 17.4), (6.9, 11.2), (12.2, 11.2))


def _clamp(value):
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _seg(value, start, end):
    """value가 start에서 end로 가는 동안 0에서 1로 올라가는 비율."""
    return _clamp((value - start) / (end - start))


def _ease(value):
    value = _clamp(value)
    return value * value * (3.0 - 2.0 * value)


def _faded(color, alpha):
    result = QColor(color)
    result.setAlphaF(_clamp(alpha) * color.alphaF())
    return result


class UsageGuide(QWidget):
    """[영역 고르기] → [글자 읽기] → [표로 붙여넣기]를 보여 주는 벡터 애니메이션."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("screenTextGuide")
        self.setAccessibleName("화면 글자 따기 사용법")
        self.setAccessibleDescription(" / ".join(CAPTIONS))
        self.setToolTip("누르면 처음부터 다시 봅니다")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._progress = 0.0
        self._fade = 1.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(DURATION_MS)
        self._animation.setLoopCount(-1)
        self._animation.valueChanged.connect(self._on_value)

    # ── 제어 ──
    def start(self):
        if not self.is_running():
            self._animation.start()

    def stop(self):
        self._animation.stop()

    def restart(self):
        self._animation.stop()
        self._progress = 0.0
        self._animation.start()
        self.update()

    def is_running(self):
        return self._animation.state() == QAbstractAnimation.Running

    def step(self):
        return min(2, int(self._progress * 3.0))

    def progress(self):
        return self._progress

    def caption(self):
        return CAPTIONS[self.step()]

    def set_progress(self, progress):
        """시험·정지 화면용: 애니메이션을 멈추고 그 시점의 한 장면을 그린다."""
        self._animation.stop()
        self._progress = _clamp(float(progress))
        self.update()

    def _on_value(self, value):
        self._progress = _clamp(float(value))
        self.update()

    # ── 배치 ──
    def sizeHint(self):
        return QSize(420, 236)

    def minimumSizeHint(self):
        return QSize(280, 160)

    def scene_rect(self):
        """위젯 안에서 그림이 차지하는 칸(비율을 지키고 가운데에 둔다)."""
        height = max(1, self.height() - CAPTION_H)
        scale = min(self.width() / SCENE_W, height / SCENE_H)
        width, tall = SCENE_W * scale, SCENE_H * scale
        return QRectF((self.width() - width) / 2, (height - tall) / 2, width, tall)

    def caption_rect(self):
        return QRectF(8, self.height() - CAPTION_H + 2, max(1, self.width() - 16), 24)

    # ── 이벤트 ──
    def showEvent(self, event):
        super().showEvent(event)
        self.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.stop()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.restart()
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        progress = self._progress
        # 한 바퀴의 처음과 끝은 서서히 나타나고 사라져 되풀이가 끊겨 보이지 않는다
        self._fade = min(_seg(progress, 0.0, 0.02), _seg(1.0 - progress, 0.0, 0.03))
        scene = self.scene_rect()
        painter.save()
        painter.translate(round(scene.left()), round(scene.top()))
        painter.scale(scene.width() / SCENE_W, scene.height() / SCENE_H)
        painter.setOpacity(self._fade)
        self._paint_scene(painter, progress * 3.0)
        painter.restore()
        self._paint_caption(painter, progress * 3.0)
        painter.end()

    # ── 그리기 도우미 ──
    def _text(self, painter, rect, text, pixels, color, bold=False, align=Qt.AlignLeft | Qt.AlignVCenter):
        font = QFont(self.font())
        font.setPixelSize(pixels)
        font.setBold(bold)
        font.setHintingPreference(QFont.PreferNoHinting)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, align, text)

    def _set_alpha(self, painter, alpha=1.0):
        painter.setOpacity(self._fade * _clamp(alpha))

    @staticmethod
    def _cell_rect(left, top, row, column):
        return QRectF(left + GRID_X + column * COL_W, top + GRID_Y + row * ROW_H, COL_W, ROW_H)

    def _card(self, painter, left, top):
        painter.setPen(Qt.NoPen)
        for grow, alpha in ((3, 7), (2, 10), (1, 16)):
            painter.setBrush(QColor(24, 46, 76, alpha))
            painter.drawRoundedRect(QRectF(left - grow, top - grow + 2, CARD_W + 2 * grow, CARD_H + 2 * grow), 8 + grow, 8 + grow)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(CARD_BORDER, 1))
        painter.drawRoundedRect(QRectF(left + 0.5, top + 0.5, CARD_W - 1, CARD_H - 1), 7, 7)

    def _grid(self, painter, left, top, rows, header_fill):
        """표 틀: 첫 줄 바탕, 안쪽 가는 선, 바깥 테두리."""
        area = QRectF(left + GRID_X, top + GRID_Y, COLUMNS * COL_W, rows * ROW_H)
        painter.fillRect(QRectF(area.left(), area.top(), area.width(), ROW_H), header_fill)
        painter.setPen(QPen(LINE, 1))
        for row in range(1, rows):
            painter.drawLine(QPointF(area.left(), area.top() + row * ROW_H), QPointF(area.right(), area.top() + row * ROW_H))
        for column in range(1, COLUMNS):
            painter.drawLine(QPointF(area.left() + column * COL_W, area.top()), QPointF(area.left() + column * COL_W, area.bottom()))
        painter.setPen(QPen(GRID_BORDER, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(area)
        return area

    def _paint_scene(self, painter, t):
        step2, step3 = t - 1.0, t - 2.0
        slide = _ease(_seg(step3, 0.0, 0.22))
        doc_x = DOC_CENTER_X + (DOC_LEFT_X - DOC_CENTER_X) * slide
        sheet_in = _ease(_seg(step3, 0.04, 0.26))
        painter.setPen(QPen(STAGE_BORDER, 1))
        painter.setBrush(STAGE_BG)
        painter.drawRoundedRect(QRectF(0.5, 0.5, SCENE_W - 1, SCENE_H - 1), 10, 10)
        self._text(painter, QRectF(doc_x + 2, 6, 120, 16), "스캔 문서", 11, MUTED)
        self._paint_arrow(painter, step3)
        if sheet_in > 0.0:
            self._set_alpha(painter, sheet_in)
            sheet_x = SHEET_X + (1.0 - sheet_in) * 22
            self._text(painter, QRectF(sheet_x + 2, 6, 120, 16), "한글·엑셀", 11, MUTED)
            self._paint_sheet(painter, sheet_x, step3, sheet_in)
            self._set_alpha(painter)
        self._paint_document(painter, doc_x, t, step2, step3)

    # ── 왼쪽 문서(1·2단계의 주인공) ──
    def _paint_document(self, painter, left, t, step2, step3):
        top = CARD_Y
        keep = 1.0 - 0.65 * _seg(step3, 0.0, 0.2)  # 3단계에서는 선택 표시를 옅게 한다
        self._card(painter, left, top)
        painter.setPen(Qt.NoPen)
        for offset, height, width, color in ((14, 6, 80, BAR_STRONG), (28, 4, 148, BAR), (36, 4, 118, BAR),
                                             (138, 4, 148, BAR), (146, 4, 96, BAR)):
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(left + GRID_X, top + offset, width, height), height / 2, height / 2)
        area = self._grid(painter, left, top, ROW_COUNT, HEADER_FILL)
        for index in range(CELL_COUNT):
            row, column = divmod(index, COLUMNS)
            cell = self._cell_rect(left, top, row, column)
            read = _ease(_seg(step2, 0.52 + 0.22 * index / 11, 0.62 + 0.22 * index / 11))
            if read < 1.0:  # 읽기 전: 글자 대신 회색 자리 표시
                self._set_alpha(painter, 1.0 - read)
                painter.setPen(Qt.NoPen)
                painter.setBrush(BAR_STRONG if row == 0 else BAR)
                width = PLACEHOLDER_WIDTHS[row][column]
                painter.drawRoundedRect(QRectF(cell.left() + 8, cell.center().y() - 2.5, width, 5), 2.5, 2.5)
            if read > 0.0:  # 읽은 뒤: 또렷한 글자
                self._set_alpha(painter, read)
                text_rect = cell.adjusted(8, (1.0 - read) * 2, -2, (1.0 - read) * 2)
                self._text(painter, text_rect, ROWS[row][column], 10, STRONG if row == 0 else INK, bold=row == 0)
            self._set_alpha(painter)
        self._paint_scan(painter, area, step2)
        for index in range(CELL_COUNT):  # 칸마다 하나씩 나타나는 주황 상자
            row, column = divmod(index, COLUMNS)
            appear = _ease(_seg(step2, 0.04 + 0.34 * index / 11, 0.16 + 0.34 * index / 11))
            read = _ease(_seg(step2, 0.52 + 0.22 * index / 11, 0.62 + 0.22 * index / 11))
            alpha = appear * (1.0 - 0.45 * read) * keep
            if alpha <= 0.01:
                continue
            inset = 3 + (1.0 - appear) * 4
            box = self._cell_rect(left, top, row, column).adjusted(inset, inset, -inset, -inset)
            painter.setPen(QPen(_faded(ORANGE, alpha), 1.2))
            painter.setBrush(_faded(ORANGE, 0.12 * alpha))
            painter.drawRoundedRect(box, 3, 3)
        self._paint_selection(painter, left, top, t, keep)

    def _paint_scan(self, painter, area, step2):
        """2단계 앞부분에 선택 영역을 위에서 아래로 훑는 주황 선."""
        sweep = _seg(step2, 0.02, 0.5)
        if not 0.0 < sweep < 1.0:
            return
        y = area.top() + sweep * area.height()
        envelope = min(1.0, sweep / 0.08, (1.0 - sweep) / 0.08)
        painter.save()
        painter.setClipRect(area)
        glow = QLinearGradient(0, y - 16, 0, y)
        glow.setColorAt(0.0, _faded(ORANGE, 0.0))
        glow.setColorAt(1.0, _faded(ORANGE, 0.28 * envelope))
        painter.fillRect(QRectF(area.left(), y - 16, area.width(), 16), glow)
        painter.setPen(QPen(_faded(ORANGE, 0.9 * envelope), 1.5))
        painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        painter.restore()

    def _paint_selection(self, painter, left, top, t, keep):
        """끌어서 고르는 점선 사각형과 마우스 화살표(1단계). 사각형은 2단계 내내 남는다."""
        start = QPointF(left + GRID_X - 6, top + GRID_Y - 6)
        end = QPointF(left + GRID_X + COLUMNS * COL_W + 6, top + GRID_Y + ROW_COUNT * ROW_H + 6)
        drag = _ease(_seg(t, 0.15, 0.72))
        corner = start + (end - start) * drag
        if drag > 0.0:
            box = QRectF(start, corner).normalized()
            painter.setBrush(_faded(ORANGE, 0.07 * keep))
            pen = QPen(_faded(ORANGE, keep), 1.5)
            pen.setDashPattern([3.5, 2.5])
            pen.setDashOffset(-t * 14)
            painter.setPen(pen)
            painter.drawRoundedRect(box, 3, 3)
            handles = _seg(t, 0.72, 0.85) * keep
            if handles > 0.0:  # 다 고른 뒤 네 모서리 손잡이
                painter.setPen(QPen(_faded(ORANGE, handles), 1.2))
                painter.setBrush(_faded(QColor("#FFFFFF"), handles))
                for point in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
                    painter.drawRect(QRectF(point.x() - 2.5, point.y() - 2.5, 5, 5))
        visible = _seg(t, 0.0, 0.08) * (1.0 - _seg(t, 1.0, 1.18))
        if visible > 0.0:
            far = QPointF(start.x() - 30, start.y() - 24)
            tip = far + (start - far) * _ease(_seg(t, 0.0, 0.15)) + (end - start) * drag
            self._paint_cursor(painter, tip, visible)

    def _paint_cursor(self, painter, tip, alpha):
        path = QPainterPath()
        for index, (x, y) in enumerate(CURSOR_SHAPE):
            point = QPointF(tip.x() + x, tip.y() + y)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        shadow = QPainterPath(path)
        shadow.translate(1.2, 1.6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_faded(QColor(24, 46, 76, 70), alpha))
        painter.drawPath(shadow)
        painter.setPen(QPen(_faded(INK, alpha), 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(_faded(QColor("#FFFFFF"), alpha))
        painter.drawPath(path)

    # ── 오른쪽 시트(3단계의 주인공)와 화살표 ──
    def _paint_arrow(self, painter, step3):
        shown = _ease(_seg(step3, 0.14, 0.26))
        if shown <= 0.0:
            return
        y = CARD_Y + GRID_Y + 40
        x0, x1 = DOC_LEFT_X + CARD_W + 6, SHEET_X - 6
        painter.setPen(QPen(_faded(ARROW, shown), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(x0, y), QPointF(x1, y))
        painter.drawLine(QPointF(x1 - 5, y - 5), QPointF(x1, y))
        painter.drawLine(QPointF(x1 - 5, y + 5), QPointF(x1, y))
        flow = _seg(step3, 0.2, 0.24) * (1.0 - _seg(step3, 0.46, 0.5))
        if flow > 0.0:  # 글자가 시트로 흘러가는 파란 점
            position = x0 + (((step3 - 0.2) / 0.15) % 1.0) * (x1 - x0 - 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(_faded(ACCENT, flow))
            painter.drawEllipse(QPointF(position, y), 3.2, 3.2)

    def _paint_sheet(self, painter, left, step3, appear):
        top = CARD_Y
        self._card(painter, left, top)
        painter.setPen(QPen(STAGE_BORDER, 1))
        painter.setBrush(STAGE_BG)
        painter.drawRoundedRect(QRectF(left + 10.5, top + 10.5, CARD_W - 21, 13), 4, 4)  # 수식 입력줄
        strip = QRectF(left + GRID_X, top + 32, COLUMNS * COL_W, 14)
        painter.fillRect(strip, STRIP_FILL)
        painter.setPen(QPen(LINE, 1))
        for column in range(1, COLUMNS):
            painter.drawLine(QPointF(strip.left() + column * COL_W, strip.top()), QPointF(strip.left() + column * COL_W, strip.bottom()))
        for column, letter in enumerate("ABC"):
            self._text(painter, QRectF(strip.left() + column * COL_W, strip.top(), COL_W, 14), letter, 9, MUTED, align=Qt.AlignCenter)
        self._grid(painter, left, top, ROW_COUNT + 1, SHEET_HEADER)
        painter.setPen(QPen(GRID_BORDER, 1))
        painter.drawLine(QPointF(strip.left(), strip.top()), QPointF(strip.right(), strip.top()))
        unsure_row, unsure_col = UNSURE_CELL
        flagged = _ease(_seg(step3, 0.40, 0.48))
        if flagged > 0.0:
            cell = self._cell_rect(left, top, unsure_row, unsure_col)
            painter.setPen(QPen(_faded(AMBER, flagged), 1))
            painter.setBrush(_faded(YELLOW, flagged))
            painter.drawRect(cell.adjusted(0.5, 0.5, -0.5, -0.5))
        for index in range(CELL_COUNT):
            row, column = divmod(index, COLUMNS)
            filled = _ease(_seg(step3, 0.20 + 0.14 * index / 11, 0.28 + 0.14 * index / 11))
            if filled <= 0.0:
                continue
            self._set_alpha(painter, appear * filled)
            cell = self._cell_rect(left, top, row, column)
            self._text(painter, cell.adjusted(8, (1.0 - filled) * 2, -2, (1.0 - filled) * 2), ROWS[row][column], 10,
                       STRONG if row == 0 else INK, bold=row == 0)
        self._set_alpha(painter, appear)
        popped = _ease(_seg(step3, 0.46, 0.56))
        if popped > 0.0:  # 확인 꼬리표
            cell = self._cell_rect(left, top, unsure_row, unsure_col)
            center = QPointF(cell.right() - 17, cell.center().y())
            tag = QRectF(0, 0, 26 * popped, 13 * popped)
            tag.moveCenter(center)
            painter.setPen(Qt.NoPen)
            painter.setBrush(_faded(TAG, popped))
            painter.drawRoundedRect(tag, 6.5 * popped, 6.5 * popped)
            if popped > 0.6:
                self._text(painter, QRectF(center.x() - 13, center.y() - 8, 26, 16), "확인", 10, _faded(QColor("#FFFFFF"), popped),
                           bold=True, align=Qt.AlignCenter)

    # ── 아래 설명 줄과 단계 점 ──
    def _paint_caption(self, painter, t):
        step = self.step()
        rise = _ease(_seg(t - step, 0.0, 0.18))
        area = self.caption_rect()
        text = CAPTIONS[step]
        for pixels in (13, 12, 11):
            font = QFont(self.font())
            font.setPixelSize(pixels)
            if QFontMetrics(font).horizontalAdvance(text) <= area.width():
                break
        else:
            font = QFont(self.font())
            font.setPixelSize(11)
            text = QFontMetrics(font).elidedText(text, Qt.ElideRight, int(area.width()))
        painter.setOpacity((0.25 + 0.75 * rise) * self._fade)  # 한 바퀴 끝에서 그림과 함께 사라진다
        self._text(painter, area.translated(0, (1.0 - rise) * 3), text, pixels, INK, align=Qt.AlignCenter)
        painter.setOpacity(self._fade)
        center_y = self.height() - 11
        painter.setPen(Qt.NoPen)
        for index in range(3):
            current = index == step
            painter.setBrush(ACCENT if current else DOT_IDLE)
            radius = 4 if current else 3
            painter.drawEllipse(QPointF(self.width() / 2 + (index - 1) * 16, center_y), radius, radius)
