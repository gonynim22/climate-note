"""Display-only file labels. No document characters or stored formats are added."""
from dataclasses import dataclass, replace
import math
import ntpath
import re

from PySide6.QtCore import QPointF, QRectF, Qt, QTextBoundaryFinder
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen,
    QSyntaxHighlighter, QTextBlockUserData, QTextCharFormat, QTextCursor, QTextLayout,
)

from sticky_file_links import FileLink, PREFIX, decode

INK = QColor('#164D96')
PAPER = QColor('#F6F9FE')
OUTLINE = QColor('#93B0D1')
BADGE = QColor('#205795')
LABEL_GAP = 2
WARNING_SPACE = 14
END_PADDING = 4 + LABEL_GAP


@dataclass(frozen=True)
class LinkSpan:
    start: int
    end: int
    href: str
    link: FileLink | None


def block_link_spans(block):
    spans = []
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        href = fragment.charFormat().anchorHref()
        if href.startswith(PREFIX):
            link = decode(href)
            span = LinkSpan(fragment.position(), fragment.position() + fragment.length(), href, link)
            if (spans and spans[-1].end == span.start and link is not None
                    and spans[-1].link is not None
                    and replace(spans[-1].link, underline=link.underline) == link):
                spans[-1] = replace(spans[-1], end=span.end)
            else:
                spans.append(span)
        it += 1
    return spans


def file_type(link):
    extension = ntpath.splitext(link.path)[1][1:] if link else ''
    return extension.upper() if re.fullmatch(r'[A-Za-z0-9]{1,5}', extension) else 'FILE'


@dataclass
class Boundary:
    start: int
    end: int
    text: str
    font: QFont
    before: float = 0
    after: float = 0


@dataclass
class LabelSpec:
    span: LinkSpan  # block-relative; preceding edits may move the block
    kind: str
    badge_font: QFont
    badge_width: float
    boundaries: list
    warning_space: float = 0


class LabelBlockData(QTextBlockUserData):
    def __init__(self):
        super().__init__()
        self.labels = []


def _padding_spacing(font, text, padding):
    # Combining marks and emoji clusters need not have one spacing unit.
    zero = QFont(font)
    zero.setLetterSpacing(QFont.AbsoluteSpacing, 0)
    sample = QFont(zero)
    sample.setLetterSpacing(QFont.AbsoluteSpacing, 16)
    natural = QFontMetricsF(zero).horizontalAdvance(text)
    units = (QFontMetricsF(sample).horizontalAdvance(text) - natural) / 16
    return (QFontMetricsF(font).horizontalAdvance(text) - natural + padding) / max(1, units)


class FileLabelHighlighter(QSyntaxHighlighter):
    """Reserve inline ornament space in the layout, never in the document."""
    def __init__(self, document):
        super().__init__(document)
        self.todo_characters = ()

    def highlightBlock(self, text):
        block = self.currentBlock()
        data = LabelBlockData()
        finder = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, text)
        for absolute in block_link_spans(block):
            span = replace(absolute, start=absolute.start - block.position(), end=absolute.end - block.position())
            finder.setPosition(span.start)
            first_end = min(span.end, finder.toNextBoundary())
            finder.setPosition(span.end)
            last_start = max(span.start, finder.toPreviousBoundary())
            if first_end <= span.start or last_start >= span.end:
                continue
            badge_font = QFont(self.document().defaultFont())
            badge_font.setPixelSize(8)
            badge_font.setBold(True)
            kind = file_type(span.link)
            badge_width = math.ceil(QFontMetricsF(badge_font).horizontalAdvance(kind)) + 6
            ranges = [(span.start, first_end)]
            if (last_start, span.end) != ranges[0]:
                ranges.append((last_start, span.end))
            base = QTextCharFormat()
            base.setForeground(INK)
            base.setBackground(QColor(0, 0, 0, 0))
            base.setFontUnderline(False)
            self.setFormat(span.start, span.end - span.start, base)
            boundaries = []
            for start, end in ranges:
                cursor = QTextCursor(block)
                cursor.setPosition(block.position() + start)
                cursor.setPosition(block.position() + end, QTextCursor.KeepAnchor)
                font = cursor.charFormat().font().resolve(self.document().defaultFont())
                font.setUnderline(False)
                boundary = Boundary(start, end, cursor.selectedText(), font,
                                    badge_width + 7 if start == span.start else 0,
                                    END_PADDING if end == span.end else 0)
                fmt = QTextCharFormat(base)
                fmt.setForeground(QColor(0, 0, 0, 0))
                fmt.setFontLetterSpacingType(QFont.AbsoluteSpacing)
                fmt.setFontLetterSpacing(_padding_spacing(font, boundary.text, boundary.before + boundary.after))
                self.setFormat(start, end - start, fmt)
                boundaries.append(boundary)
            data.labels.append(LabelSpec(span, kind, badge_font, badge_width, boundaries))
        # One highlighter owns both decorations; a second one would replace these ranges.
        offset = 0
        for char in text:
            length = len(char.encode('utf-16-le')) // 2
            if char in self.todo_characters:
                mask = QTextCharFormat()
                mask.setForeground(QColor(0, 0, 0, 0))
                self.setFormat(offset, length, mask)
            offset += length
        self.setCurrentBlockUserData(data if data.labels else None)


@dataclass
class LabelVisual:
    span: LinkSpan
    rect: QRectF
    badge_rect: QRectF | None
    warning_rect: QRectF | None
    spec: LabelSpec
    glyphs: list


def refresh_warning_spacing(edit):
    """Resize only layout formats: rehighlight() would change document revision.

    Preserve IME preedit ranges until composition ends; the dashed outline still
    reflects the status while the warning icon waits for its layout space.
    """
    document = edit.document()
    block = document.begin()
    while block.isValid():
        data = block.userData()
        layout = block.layout()
        if isinstance(data, LabelBlockData) and not layout.preeditAreaText():
            ranges = layout.formats()
            changed = False
            for spec in data.labels:
                span = replace(spec.span, start=spec.span.start + block.position(),
                               end=spec.span.end + block.position())
                space = WARNING_SPACE if edit.link_error(span) else 0
                if space == spec.warning_space:
                    continue
                boundary = spec.boundaries[-1]
                for index, current in enumerate(ranges):
                    if current.start <= boundary.start and current.start + current.length >= boundary.end:
                        # Qt can merge equal adjacent ranges; split just this grapheme.
                        replacements = []
                        for start, end, is_boundary in (
                            (current.start, boundary.start, False),
                            (boundary.start, boundary.end, True),
                            (boundary.end, current.start + current.length, False),
                        ):
                            if start == end:
                                continue
                            item = QTextLayout.FormatRange()
                            item.start, item.length = start, end - start
                            fmt = QTextCharFormat(current.format)
                            if is_boundary:
                                fmt.setFontLetterSpacing(_padding_spacing(
                                    boundary.font, boundary.text,
                                    boundary.before + END_PADDING + space))
                            item.format = fmt
                            replacements.append(item)
                        ranges[index:index + 1] = replacements
                        boundary.after = END_PADDING + space
                        spec.warning_space = space
                        changed = True
                        break
            if changed:
                layout.setFormats(ranges)
                document.markContentsDirty(block.position(), block.length())
        block = block.next()


def label_visuals(edit):
    refresh_warning_spacing(edit)
    edit.document().documentLayout().documentSize()
    first = edit.cursorForPosition(edit.viewport().rect().topLeft()).block()
    last = edit.cursorForPosition(edit.viewport().rect().bottomRight()).block()
    visuals = []
    block = first
    while block.isValid() and block.blockNumber() <= last.blockNumber():
        data = block.userData()
        layout = block.layout()
        if isinstance(data, LabelBlockData) and layout.lineCount():
            first_line = layout.lineAt(0)
            caret = edit.cursorRect(QTextCursor(block))
            origin = QPointF(caret.x() - first_line.cursorToX(0)[0], caret.y() - first_line.y())
            for spec in data.labels:
                span = replace(spec.span, start=spec.span.start + block.position(), end=spec.span.end + block.position())
                for number in range(layout.lineCount()):
                    line = layout.lineAt(number)
                    start = max(spec.span.start, line.textStart())
                    end = min(spec.span.end, line.textStart() + line.textLength())
                    if start >= end:
                        continue
                    x0, x1 = line.cursorToX(start)[0], line.cursorToX(end)[0]
                    rtl = x0 > x1
                    left, right = min(x0, x1), max(x0, x1)
                    if end == spec.span.end:
                        if rtl:
                            left += LABEL_GAP + spec.warning_space
                        else:
                            right -= LABEL_GAP + spec.warning_space
                    rect = QRectF(origin.x() + left, origin.y() + line.y() + 1,
                                  max(1, right - left), max(1, line.height() - 2))
                    if not rect.intersects(QRectF(edit.viewport().rect())):
                        continue
                    badge_rect = None
                    if start == spec.span.start:
                        bx = rect.right() - spec.badge_width - 3 if rtl else rect.left() + 3
                        badge_height = min(11, max(1, rect.height() - 4))
                        badge_rect = QRectF(bx, rect.center().y() - badge_height / 2,
                                            spec.badge_width, badge_height)
                    warning_rect = None
                    if end == spec.span.end and spec.warning_space:
                        wx = rect.left() - 15 if rtl else rect.right() + 3
                        warning_rect = QRectF(wx, rect.center().y() - 6, 12, 12)
                    glyphs = []
                    for boundary in spec.boundaries:
                        if start <= boundary.start < end:
                            a, b = line.cursorToX(boundary.start)[0], line.cursorToX(boundary.end)[0]
                            x = min(a, b) + (boundary.after if a > b else boundary.before)
                            glyphs.append((boundary, QPointF(origin.x() + x, origin.y() + line.y() + line.ascent())))
                    visuals.append(LabelVisual(span, rect, badge_rect, warning_rect, spec, glyphs))
        block = block.next()
    return visuals


def paint_label_backgrounds(edit, visuals):
    painter = QPainter(edit.viewport())
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(PAPER)
    for visual in visuals:
        painter.drawRoundedRect(visual.rect, 4, 4)
    painter.end()


def paint_label_details(edit, visuals):
    painter = QPainter(edit.viewport())
    painter.setRenderHint(QPainter.Antialiasing)
    selection = edit.textCursor()
    for visual in visuals:
        error = edit.link_error(visual.span)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(OUTLINE, 1, Qt.DashLine if error else Qt.SolidLine))
        painter.drawRoundedRect(visual.rect.adjusted(.5, .5, -.5, -.5), 4, 4)
        if visual.badge_rect is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(BADGE)
            painter.drawRoundedRect(visual.badge_rect, 2, 2)
            painter.setFont(visual.spec.badge_font)
            painter.setPen(Qt.white)
            painter.drawText(visual.badge_rect, Qt.AlignCenter, visual.spec.kind)
        for boundary, point in visual.glyphs:
            position = visual.span.start - visual.spec.span.start + boundary.start
            selected = selection.hasSelection() and selection.selectionStart() <= position < selection.selectionEnd()
            painter.setFont(boundary.font)
            painter.setPen(edit.palette().highlightedText().color() if selected else INK)
            painter.drawText(point, boundary.text)
        if error and visual.warning_rect is not None:
            rect = visual.warning_rect
            shape = QPainterPath()
            shape.moveTo(rect.center().x(), rect.top())
            shape.lineTo(rect.right(), rect.bottom())
            shape.lineTo(rect.left(), rect.bottom())
            shape.closeSubpath()
            painter.setPen(QColor('#9A6700'))
            painter.setBrush(QColor('#FFD166'))
            painter.drawPath(shape)
            painter.setFont(visual.spec.badge_font)
            painter.drawText(rect.adjusted(0, 2, 0, 0), Qt.AlignCenter, '!')
    painter.end()
