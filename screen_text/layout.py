"""인식 상자를 줄·표로 재구성하고 불확실한 곳을 표시한다.

Qt·numpy를 쓰지 않는 순수 Python이다. 규칙은 docs/SCREEN_TEXT.md를 따른다.
글자를 자동으로 고치지 않고 불확실한 곳만 표시한다(추정 금지).
"""
from dataclasses import dataclass
import html
import re

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


def group_lines(boxes):
    """세로 위치로 줄을 묶고 줄 안은 왼쪽부터 정렬한다."""
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
    return [sorted(members, key=lambda b: b.x) for members, _, _ in lines]


def _merge_bands(intervals):
    """겹치는 x 구간을 합쳐 왼쪽부터 열 띠 목록을 만든다."""
    bands = []
    for start, end in sorted(intervals):
        if bands and start < bands[-1][1]:
            bands[-1] = (bands[-1][0], max(bands[-1][1], end))
        else:
            bands.append((start, end))
    return bands


def _intervals(line):
    return [(item.x, item.x + item.w) for item in line]


def _overlaps(a, b):
    """두 구간이 겹치는지 확인한다."""
    return a[0] < b[1] and b[0] < a[1]


def _compatible(bands, intervals):
    """새 줄의 구간이 기존 열 띠와 1:1로만 겹쳐야 같은 표다. 한 구간이 여러 띠에 걸치거나 한 띠가 여러 구간에 걸치면 표를 끝낸다."""
    line_bands = _merge_bands(intervals)
    return (all(sum(_overlaps(i, b) for b in bands) <= 1 for i in line_bands)
            and all(sum(_overlaps(b, i) for i in line_bands) <= 1 for b in bands))


def _table_runs(lines):
    """표가 되는 연속 줄 구간 (시작, 끝, 열 띠). 2칸 이상인 줄 2개 이상이 같은 열에 맞아야 한다."""
    runs, index = [], 0
    while index < len(lines):
        if len(lines[index]) < 2:
            index += 1
            continue
        bands = _merge_bands(_intervals(lines[index]))
        end = index + 1
        while end < len(lines) and len(lines[end]) >= 2:
            if not _compatible(bands, _intervals(lines[end])):
                break
            bands = _merge_bands(bands + _intervals(lines[end]))
            end += 1
        if end - index >= 2 and len(bands) >= 2:
            runs.append((index, end, bands))
        index = end
    return runs


def _cell(items):
    text = " ".join(item.text for item in items).strip()
    return Cell(text, any(item.score < UNSURE_SCORE for item in items))


def _column_of(item, bands):
    center = item.x + item.w / 2
    for column, (start, end) in enumerate(bands):
        if start <= center < end:
            return column
    return min(range(len(bands)), key=lambda c: abs((bands[c][0] + bands[c][1]) / 2 - center))


def _table(lines, bands):
    rows = []
    for line in lines:
        slots = [[] for _ in bands]
        for item in line:
            slots[_column_of(item, bands)].append(item)
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
    runs = {start: (end, bands) for start, end, bands in _table_runs(lines)}
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


def to_plain(blocks):
    return "\n".join(_line_text(row) for block in blocks for row in rows_of(block))


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
