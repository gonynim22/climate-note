"""줄 맨 앞 글머리 기호(■ □ ◇ ㅇ)를 모양으로 알아본다. Qt를 쓰지 않고 numpy만 쓴다.

인식 모델은 공문서의 글머리 기호를 거의 읽지 못한다(실제 공문서 PDF에서 ■ 94%·□ 100%·ㅇ 55% 누락). 줄(인식 상자)
맨 앞의 글자 픽셀 덩어리가 글자보다 작고 뒤 글자와 떨어져 있으면 모양(속이 찬 정사각/속이 빈 정사각/마름모/
고리)으로 분류한다. 화면에 있는 모양을 읽을 뿐 글자를 추정하지 않는다. 고리는 ㅇ ◦ ○ o 를 모양으로 구별할 수 없어
'ㅇ'으로 내되 확인 필요로 표시한다. 계약은 docs/SCREEN_TEXT.md를 따른다.
"""
import numpy as np

INK_MIN_DIFF = 24          # 배경 중앙값과 이만큼(0~255) 달라야 글자 픽셀
INK_PEAK_FRACTION = 0.3    # 그리고 가장 진한 글자 픽셀 차이의 이 비율 이상
SEARCH_LEFT = 2.5          # 상자 높이의 이 배수만큼 왼쪽(왼쪽 이웃 상자 전까지)에서 기호를 찾는다
SEARCH_RIGHT = 4.0         # 상자 시작에서 상자 높이의 이 배수까지만 본다(기호와 뒤 글자의 간격을 알기에 충분하다)
MIN_SYMBOL_PX = 3          # 이보다 작은 덩어리(마침표·쉼표)는 기호가 아니다
SYMBOL_GAP_RATIO = 0.5     # 기호와 뒤 글자의 간격은 기호 폭의 이 비율(최소 3px) 이상
SQUARE_HEIGHT_RATIO = 0.72  # 속이 빈 정사각은 줄 글자 높이의 이 비율 이상(고리 ㅇ은 0.12~0.65, 정사각은 0.69~0.95). 애매하면 확인 필요 표시가 붙는 고리 쪽이 안전하다
SQUARE_CORNERS = 0.5       # 또는 네 모서리가 이만큼 차 있으면 정사각
DIAMOND_CORNERS = 0.06     # 마름모는 네 모서리가 비어 있다
FILLED = "■"
HOLLOW_SQUARE = "□"
DIAMOND = "◇"
RING = "ㅇ"
# 모델이 기호를 닮은 글자로 읽었을 때 교체해도 되는 첫 글자
CONFUSABLE = frozenset("0oOㅇCcD.:-□■▪○●ㅁ")


def ink_mask(crop):
    """배경(중앙값 색)과 충분히 다른 글자 픽셀. 옅은 잡음은 글자로 세지 않는다."""
    gray = crop.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    diff = np.abs(gray - np.median(gray))
    peak = float(diff.max())
    if peak <= 0:
        return np.zeros(diff.shape, dtype=bool)
    return diff > max(INK_MIN_DIFF, INK_PEAK_FRACTION * peak)


def _blobs(ink, reference_height=0, limit=4):
    """왼쪽부터 이어진 글자 열 묶음(덩어리)의 모양 특징. 높이 비율은 줄 글자 높이(기호만 든 상자는 이웃 상자의 글자 높이)에 견준다."""
    columns = np.flatnonzero(ink.any(axis=0))
    rows = np.flatnonzero(ink.any(axis=1))
    if columns.size == 0:
        return []
    height = max(int(rows[-1] - rows[0] + 1), reference_height)
    runs, start, previous = [], columns[0], columns[0]
    for column in columns[1:]:
        if column != previous + 1:
            runs.append((start, previous))
            start = column
        previous = column
    runs.append((start, previous))
    blobs = []
    for k, (a, b) in enumerate(runs[:limit]):
        blob = ink[:, a:b + 1]
        occupied = np.flatnonzero(blob.any(axis=1))
        blob = blob[occupied[0]:occupied[-1] + 1]
        blob_h, blob_w = blob.shape
        qw, qh = max(1, round(blob_w * .25)), max(1, round(blob_h * .25))
        corners = float(np.mean([blob[:qh, :qw].mean(), blob[:qh, -qw:].mean(),
                                 blob[-qh:, :qw].mean(), blob[-qh:, -qw:].mean()]))
        cy0, cx0 = int(blob_h * .3), int(blob_w * .3)
        center = float(blob[cy0:max(cy0 + 1, int(blob_h * .7)), cx0:max(cx0 + 1, int(blob_w * .7))].mean())
        blobs.append(dict(width=blob_w, height=blob_h, fill=float(blob.mean()), center=center, corners=corners,
                          relative_height=blob_h / height, left=int(a), right=int(b),
                          gap=int(runs[k + 1][0] - b - 1) if k + 1 < len(runs) else 10 ** 6))
    return blobs


def _is_rule(blob):
    """표 테두리·괄호처럼 가늘고 긴 덩어리."""
    return blob["width"] / max(blob["height"], 1) < .4 and blob["relative_height"] >= .6


def _classify(blob):
    if (blob["width"] < MIN_SYMBOL_PX or blob["height"] < MIN_SYMBOL_PX
            or blob["gap"] < max(3, int(SYMBOL_GAP_RATIO * blob["width"]))):
        return None
    aspect = blob["width"] / blob["height"]
    relative = blob["relative_height"]
    if blob["fill"] >= .85 and blob["center"] >= .9 and .7 <= aspect <= 1.4 and .2 <= relative <= 1.05:
        return FILLED
    if blob["center"] <= .1 and .75 <= aspect <= 1.3 and relative >= .15:
        if blob["corners"] <= DIAMOND_CORNERS and relative >= .5:
            return DIAMOND
        if relative >= SQUARE_HEIGHT_RATIO or blob["corners"] >= SQUARE_CORNERS:
            return HOLLOW_SQUARE
        return RING
    return None


def _ink_height(image, box):
    """상자 앞부분의 글자 픽셀이 차지하는 세로 높이(글자 없으면 0)."""
    x0, y0, x1, y1 = box
    rows = np.flatnonzero(ink_mask(image[y0:y1, x0:min(x1, x0 + int(round(SEARCH_RIGHT * (y1 - y0))))]).any(axis=1))
    return int(rows[-1] - rows[0] + 1) if rows.size else 0


def _same_row(a, b):
    return min(a[3], b[3]) - max(a[1], b[1]) >= .5 * min(a[3] - a[1], b[3] - b[1])


def leading_symbol(image, index, boxes):
    """index번 상자의 줄 맨 앞 기호. (종류, 시작 x, 끝 x, 기호만 든 상자인가) 또는 None.

    기호는 상자 안이나 바로 왼쪽에 있을 수 있다. 위치 찾기가 기호를 글자와 따로 상자로 자르기도 하므로(기호만
    든 상자), 높이 비율은 같은 줄 오른쪽 이웃 상자의 글자 높이에 견주고 그 상자는 이 기호를 다시 찾지 않는다.
    """
    box = boxes[index]
    x0, y0, x1, y1 = box
    height = y1 - y0
    left_limit = 0
    for j, other in enumerate(boxes):  # 먼저 시작한 같은 줄의 상자(겹치면 그 상자) 몫인 왼쪽은 찾지 않는다
        if j != index and other[0] < x0 and _same_row(other, box):
            left_limit = max(left_limit, min(other[2] + 1, x0))
    x_from = max(left_limit, x0 - int(round(SEARCH_LEFT * height)))
    x_to = min(x1, x0 + int(round(SEARCH_RIGHT * height)))
    if x_to - x_from < 6:
        return None
    reference = max((_ink_height(image, other) for j, other in enumerate(boxes)
                     if j != index and other[0] >= x0 and other[0] - x0 <= 10 * height and _same_row(other, box)), default=0)
    for blob in _blobs(ink_mask(image[y0:y1, x_from:x_to]), reference):
        if _is_rule(blob):
            continue
        kind = _classify(blob)
        if kind is None:
            return None
        alone = blob["gap"] >= 10 ** 6 and x_to == x1  # 상자 안에 이 기호밖에 없다
        return kind, x_from + blob["left"], x_from + blob["right"], alone
    return None


def apply_leading_symbols(image, boxes, results):
    """[(글자, 점수)]를 [(글자, 점수, 확인 필요 앞글자 수)]로. 기호가 보이면 앞에 붙이거나(모델이 건너뜀) 닮은 글자를 교체한다."""
    out = []
    for index, (text, score) in enumerate(results):
        flagged = 0
        found = leading_symbol(image, index, boxes) if text.strip() else None
        if found:
            kind, _, right, alone = found
            body = text.lstrip()
            if alone:  # 기호만 든 상자: 모델이 읽은 것은 모두 이 기호를 잘못 읽은 것이다
                text = kind
            else:
                if right >= boxes[index][0] and body[:1] in CONFUSABLE:  # 상자 안에서 닮은 글자로 읽힌 기호
                    body = body[1:].lstrip()
                text = f"{kind} {body}" if body else kind
            flagged = int(kind == RING)
        out.append((text, score, flagged))
    return out
