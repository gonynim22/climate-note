"""인식 상자를 줄·표로 재구성하고 불확실한 곳을 표시한다.

Qt·numpy를 쓰지 않는 순수 Python이다. 규칙은 docs/SCREEN_TEXT.md를 따른다.
글자를 자동으로 고치지 않고 불확실한 곳만 표시한다(추정 금지).
"""
from dataclasses import dataclass
import html
import re
from statistics import median

UNSURE_SCORE = 0.80          # 이 값 미만의 인식 점수는 확인 필요 (Task 4 측정으로 확정)
LINE_OVERLAP = 0.5           # 세로 겹침이 작은 쪽 높이의 이 비율 이상이면 같은 줄
LOOKALIKE = frozenset("lIOoSB")
_NUMERIC = re.compile(r"[0-9.,%△▲▽+\-()]+")


@dataclass(frozen=True)
class TextBox:
    """원본 이미지 픽셀 좌표의 글자 상자와 인식 결과."""
    x: int
    y: int
    w: int
    h: int
    text: str
    score: float


@dataclass
class Cell:
    text: str
    unsure: bool = False


@dataclass
class TextLine:
    cells: list[Cell]


@dataclass
class Table:
    rows: list[list[Cell]]


def rows_of(block):
    """TextLine은 한 행, Table은 모든 행을 돌려준다."""
    return block.rows if isinstance(block, Table) else [block.cells]


def _physical_lines(boxes):
    """합집합 높이가 다음 줄까지 번지지 않도록 중심 중앙값으로 묶는다."""
    lines = []
    for item in sorted(boxes, key=lambda b: (b.y + b.h / 2, b.x)):
        if lines:
            members = lines[-1]
            center = median(b.y + b.h / 2 for b in members)
            height = median(b.h for b in members)
            if abs(item.y + item.h / 2 - center) <= LINE_OVERLAP * min(height, item.h):
                members.append(item)
                continue
        lines.append([item])
    return [sorted(line, key=lambda b: b.x) for line in lines]


def group_lines(boxes):
    """세로로 겹친 행은 유지하되, 여러 열에서 반복되는 다음 행은 분리한다."""
    lines = []  # [상자 목록, 위, 아래]
    for item in sorted(boxes, key=lambda b: (b.y + b.h / 2, b.x)):
        if lines:
            members, top, bottom = lines[-1]
            overlap = min(bottom, item.y + item.h) - max(top, item.y)
            if overlap >= LINE_OVERLAP * min(bottom - top, item.h):
                members.append(item)
                lines[-1][1], lines[-1][2] = min(top, item.y), max(bottom, item.y + item.h)
                continue
        lines.append([[item], item.y, item.y + item.h])
    result = []
    for members, _, _ in lines:
        physical = _physical_lines(members)
        repeated = any(_repeated_columns(left, right) >= 2
                       for left, right in zip(physical, physical[1:]))
        result.extend(physical if repeated else [sorted(members, key=lambda b: b.x)])
    return result


def _merge_bands(intervals):
    """겹치는 x 구간을 합쳐 왼쪽부터 열 띠 목록을 만든다."""
    bands = []
    for start, end in sorted(intervals):
        if bands and _overlaps((start, end), bands[-1]):
            bands[-1] = (bands[-1][0], max(bands[-1][1], end))
        else:
            bands.append((start, end))
    return bands


def _intervals(line):
    return [(item.x, item.x + item.w) for item in line]


def _overlaps(a, b):
    """작은 구간의 절반 이상 겹쳐야 같은 열로 본다. 가장자리 접촉은 제외한다."""
    return min(a[1], b[1]) - max(a[0], b[0]) >= 0.5 * min(a[1] - a[0], b[1] - b[0])


def _repeated_columns(left, right):
    pairs = [(i, j) for i, a in enumerate(_merge_bands(_intervals(left)))
             for j, b in enumerate(_merge_bands(_intervals(right))) if _overlaps(a, b)]
    return sum(sum(i == a for a, _ in pairs) == 1 and sum(j == b for _, b in pairs) == 1
               for i, j in pairs)


def _compatible(bands, intervals):
    """의미 있는 겹침이 1:1이어야 한다. 강한 대응이 있으면 가장자리 접촉은 버린다."""
    line_bands = _merge_bands(intervals)
    hits = [_band_hits(item, bands) for item in line_bands]
    if any(len(columns) > 1 for columns in hits):
        return False
    for column, band in enumerate(bands):
        fragments = [interval for interval, columns in zip(line_bands, hits) if column in columns]
        if len(fragments) > 1:
            if (fragments[0][0] < band[0] or fragments[-1][1] > band[1]
                    or any(left[1] <= right[0] for left, right in zip(fragments, fragments[1:]))):
                return False
    return True


def _band_hits(interval, bands):
    strong = [column for column, band in enumerate(bands) if _overlaps(interval, band)]
    return strong or [column for column, band in enumerate(bands)
                      if min(interval[1], band[1]) > max(interval[0], band[0])]


def _extend_bands(bands, intervals):
    """대응한 열만 넓힌다. 옆 열과 작은 접촉이 생겨도 열 수를 줄이지 않는다."""
    extended = list(bands)
    for interval in _merge_bands(intervals):
        hits = _band_hits(interval, bands)
        if hits:
            column = hits[0]
            start, end = extended[column]
            extended[column] = (min(start, interval[0]), max(end, interval[1]))
        else:
            extended.append(interval)
    extended.sort()
    for column in range(1, len(extended)):
        left, right = extended[column - 1], extended[column]
        if left[1] > right[0]:
            boundary = (left[1] + right[0]) / 2
            extended[column - 1] = (left[0], boundary)
            extended[column] = (boundary, right[1])
    return extended


def _grow_table(lines, index):
    bands = _merge_bands(_intervals(lines[index]))
    end = index + 1
    while end < len(lines) and len(lines[end]) >= 2:
        if not _compatible(bands, _intervals(lines[end])):
            break
        bands = _extend_bands(bands, _intervals(lines[end]))
        end += 1
    return end, bands


def _nearby(upper, lower):
    gap = min(b.y for b in lower) - max(b.y + b.h for b in upper)
    return gap <= median(b.h for b in lower)


def _separated_columns(line):
    """겹쳐 이어지는 문장 조각만으로 새 표를 시작하지 않는다."""
    count, right = 0, None
    for start, end in sorted(_intervals(line)):
        if right is None or start >= right:
            count += 1
        right = end if right is None else max(right, end)
    return count


def _table_runs(lines):
    """표가 되는 연속 줄 구간 (시작, 끝, 열 띠). 2칸 이상인 줄 2개 이상이 같은 열에 맞아야 한다."""
    runs, index = [], 0
    while index < len(lines):
        if len(lines[index]) < 2 or _separated_columns(lines[index]) < 2:
            index += 1
            continue
        end, bands = _grow_table(lines, index)
        # 드문 머리글이 본문 열 사이에 있을 때 가짜 열을 만들지 않는다.
        # 본문 전체에서 확인한 열에 맞는 경우만 머리글을 첫 칸에 넣는다.
        if index + 2 < len(lines) and len(lines[index]) < len(lines[index + 1]):
            body_end, body_bands = _grow_table(lines, index + 1)
            if body_end - index > 2 and _header_columns(lines[index], body_bands) is not None:
                if not _nearby(lines[index], lines[index + 1]):
                    index += 1
                    continue
                end, bands = body_end, body_bands
        if end - index >= 2 and len(bands) >= 2:
            runs.append((index, end, bands))
        index = end
    return runs


def _cell(items):
    text = " ".join(item.text for line in _physical_lines(items) for item in line).strip()
    return Cell(text, any(item.score < UNSURE_SCORE for item in items))


def _column_of(item, bands):
    interval = (item.x, item.x + item.w)
    overlaps = [max(0, min(interval[1], end) - max(interval[0], start)) for start, end in bands]
    if any(overlaps):
        return max(range(len(bands)), key=overlaps.__getitem__)
    center = item.x + item.w / 2
    return min(range(len(bands)), key=lambda c: abs((bands[c][0] + bands[c][1]) / 2 - center))


def _header_columns(line, bands):
    """본문 열의 가운데에 놓인 병합 머리글만 각 묶음 첫 칸에 대응시킨다."""
    if not 2 <= len(line) < len(bands):
        return None
    centers = [item.x + item.w / 2 for item in line]
    column_centers = [(start + end) / 2 for start, end in bands]
    groups = [[] for _ in line]
    for column, center in enumerate(column_centers):
        nearest = min(range(len(line)), key=lambda i: abs(centers[i] - center))
        groups[nearest].append(column)
    for item, columns in zip(line, groups):
        if not columns:
            return None
        first, last = columns[0], columns[-1]
        left_gap = bands[first][0] - bands[first - 1][1] if first else bands[1][0] - bands[0][1]
        right_gap = bands[last + 1][0] - bands[last][1] if last + 1 < len(bands) else bands[-1][0] - bands[-2][1]
        if item.x < bands[first][0] - left_gap / 2 or item.x + item.w > bands[last][1] + right_gap / 2:
            return None
        if len(columns) > 1:
            positions = [column_centers[c] for c in columns]
            step = median(b - a for a, b in zip(positions, positions[1:]))
            if abs(item.x + item.w / 2 - (positions[0] + positions[-1]) / 2) > step / 2:
                return None
    return [columns[0] for columns in groups]


def _table(lines, bands):
    rows = []
    denser_body = any(len(_merge_bands(_intervals(body))) > len(lines[0]) for body in lines[1:])
    header = _header_columns(lines[0], bands) if denser_body else None
    for index, line in enumerate(lines):
        slots = [[] for _ in bands]
        columns = header if index == 0 and header is not None else [_column_of(item, bands) for item in line]
        for item, column in zip(line, columns):
            slots[column].append(item)
        rows.append([_cell(slot) for slot in slots])
    return Table(rows)


def _mark_lookalikes(table):
    """숫자처럼 보이는 열에서 숫자와 닮은 영문자가 섞인 칸을 확인 필요로 표시한다."""
    trans_map = str.maketrans("lIOoSB", "110058")

    def is_numeric_like(text):
        translated = text.translate(trans_map)
        return _NUMERIC.fullmatch(translated) is not None

    for column in range(len(table.rows[0])):
        cells = [row[column] for row in table.rows if row[column].text]
        numeric_like = [cell for cell in cells if is_numeric_like(cell.text)]
        if not cells or len(numeric_like) * 2 < len(cells):
            continue
        for cell in cells:
            if is_numeric_like(cell.text) and any(ch.isdigit() for ch in cell.text) and LOOKALIKE & set(cell.text):
                cell.unsure = True


def build_blocks(boxes):
    """글자 상자를 위에서 아래로 TextLine·Table 블록 목록으로 만든다."""
    lines = group_lines(boxes)
    runs, previous_end = {}, 0
    for start, end, bands in _table_runs(lines):
        if start > previous_end:
            header, first = lines[start - 1], lines[start]
            denser_body = any(len(_merge_bands(_intervals(line))) > len(header) for line in lines[start:end])
            if (denser_body and _nearby(header, first)
                    and _header_columns(header, bands) is not None):
                start -= 1
        runs[start] = (end, bands)
        previous_end = end
    blocks, index = [], 0
    while index < len(lines):
        if index in runs:
            end, bands = runs[index]
            table = _table(lines[index:end], bands)
            _mark_lookalikes(table)
            blocks.append(table)
            index = end
        else:
            blocks.append(TextLine([_cell([item]) for item in lines[index]]))
            index += 1
    return blocks


def _clean(text):
    """탭·줄바꿈이 칸 경계를 깨지 않도록 공백 하나로 바꾼다."""
    return " ".join(text.split())


def _line_text(cells):
    return " ".join(_clean(cell.text) for cell in cells if cell.text)


def _utf16_len(text):
    """QTextCursor 위치는 UTF-16 코드 단위다. 이모지 같은 BMP 밖 글자는 2로 센다."""
    return len(text.encode("utf-16-le")) // 2


def plain_with_spans(blocks):
    """(글자 모음, 확인 필요 칸 위치)를 함께 만든다.

    위치는 (시작, 길이, 칸 글자)이며 문서 순서다. 시작·길이는 UTF-16 코드 단위라
    QTextCursor.setPosition에 그대로 쓴다. 글자 모음은 to_plain과 같은 문자열이다.
    """
    lines, spans, offset = [], [], 0
    for block in blocks:
        for row in rows_of(block):
            position, parts = offset, []
            for cell in row:
                if not cell.text:
                    continue
                token = _clean(cell.text)
                if cell.unsure and token:
                    spans.append((position, _utf16_len(token), token))
                parts.append(token)
                position += _utf16_len(token) + 1
            line = " ".join(parts)
            lines.append(line)
            offset += _utf16_len(line) + 1
    return "\n".join(lines), spans


def to_plain(blocks):
    return plain_with_spans(blocks)[0]


def to_tsv(blocks):
    lines = []
    for block in blocks:
        if isinstance(block, Table):
            lines.extend("\t".join(_clean(cell.text) for cell in row) for row in block.rows)
        else:
            lines.append(_line_text(block.cells))
    return "\n".join(lines)


def to_html(blocks):
    parts = []
    for block in blocks:
        if isinstance(block, Table):
            rows = "".join(
                "<tr>" + "".join(f"<td>{html.escape(_clean(cell.text))}</td>" for cell in row) + "</tr>"
                for row in block.rows
            )
            parts.append(f'<table border="1" cellspacing="0" cellpadding="2">{rows}</table>')
        else:
            parts.append(f"<p>{html.escape(_line_text(block.cells))}</p>")
    return "<html><body>" + "".join(parts) + "</body></html>"


def unsure_count(blocks):
    return sum(cell.unsure for block in blocks for row in rows_of(block) for cell in row)


def has_table(blocks):
    return any(isinstance(block, Table) for block in blocks)
