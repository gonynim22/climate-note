"""두 출력의 차이만 표시한다. 정답은 별도 평가 함수에서만 사용한다."""
from collections import Counter
import unicodedata

MAX_ALIGNMENT_CELLS = 4_000_000


def projection(text):
    """원문을 바꾸지 않고 비공백 글자 → Python/UTF-16 위치를 기록한다."""
    chars, positions, offset = [], [], 0
    for index, char in enumerate(text):
        length = len(char.encode('utf-16-le')) // 2
        if not char.isspace():
            chars.append(char)
            positions.append((index, offset, length))
        offset += length
    return ''.join(chars), positions, offset


def alignment(left, right, all_paths=False, trace=False):
    """left의 문자/간격을 편집 위치로 사용. 모든 최적 경로의 위치 합집합/교집합도 계산한다."""
    n, m = len(left), len(right)
    if (n + 1) * (m + 1) > MAX_ALIGNMENT_CELLS:
        raise ValueError('위치 정렬 한도 초과')
    costs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n:
                costs[i][j] = m - j
            elif j == m:
                costs[i][j] = n - i
            else:
                costs[i][j] = min(costs[i + 1][j + 1] + (left[i] != right[j]),
                                  costs[i + 1][j] + 1, costs[i][j + 1] + 1)

    def edges(i, j):
        # 동률 우선순위를 고정한다. 정답/태그/점수를 선택에 사용하지 않는다.
        if i < n and j < m and costs[i][j] == costs[i + 1][j + 1] + (left[i] != right[j]):
            yield i + 1, j + 1, ('char', i) if left[i] != right[j] else None
        if i < n and costs[i][j] == costs[i + 1][j] + 1:
            yield i + 1, j, ('char', i)
        if j < m and costs[i][j] == costs[i][j + 1] + 1:
            yield i, j + 1, ('gap', i)

    chosen, i, j, edits = set(), 0, 0, []
    while (i, j) != (n, m):
        previous_i, previous_j = i, j
        i, j, site = next(edges(i, j))
        if site is not None:
            chosen.add(site)
            if trace:
                edits.append({'site': site, 'left': list(range(previous_i, i)), 'right': list(range(previous_j, j)),
                              'left_gap': previous_i, 'right_gap': previous_j})
    result = {'distance': costs[0][0], 'chosen': chosen}
    if trace:
        result['edits'] = edits
    if not all_paths:
        return result
    forward = [[0] * (m + 1) for _ in range(n + 1)]
    # 같은 간격의 연속 삽입을 한 경로에서 여러 번 세지 않기 위한 진입 경로 수.
    noninsert = [[0] * (m + 1) for _ in range(n + 1)]
    backward = [[0] * (m + 1) for _ in range(n + 1)]
    forward[0][0] = noninsert[0][0] = backward[n][m] = 1
    for i in range(n + 1):
        for j in range(m + 1):
            for ni, nj, site in edges(i, j):
                forward[ni][nj] += forward[i][j]
                if site is None or site[0] != 'gap':
                    noninsert[ni][nj] += forward[i][j]
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if (i, j) != (n, m):
                backward[i][j] = sum(backward[ni][nj] for ni, nj, _ in edges(i, j))
    counts = Counter()
    for i in range(n + 1):
        for j in range(m + 1):
            for ni, nj, site in edges(i, j):
                if site is not None:
                    paths = noninsert[i][j] if site[0] == 'gap' else forward[i][j]
                    counts[site] += paths * backward[ni][nj]
    total = forward[n][m]
    return result | {'possible': {site for site, count in counts.items() if count},
                     'certain': {site for site, count in counts.items() if count == total},
                     'ambiguous': total > 1}


def marks_for_sites(text, sites):
    compact, positions, end_utf16 = projection(text)
    marks = []
    for kind, index in sorted(sites, key=lambda site: (site[1], site[0] != 'gap')):
        if kind == 'char':
            point, start, length = positions[index]
            end = point + 1
        elif kind == 'gap':
            point, start = positions[index][:2] if index < len(compact) else (len(text), end_utf16)
            end, length = point, 0
        else:
            raise ValueError('지원하지 않는 표시 위치 종류')
        marks.append({'kind': kind, 'index': index, 'start': point, 'end': end,
                      'start_utf16': start, 'length_utf16': length, 'text': text[point:end]})
    return marks


def disagreement_marks(native, alternative):
    """추론용 순수 함수. 원문/복사 값/기존 경고를 변경하지 않는다."""
    left, _, _ = projection(native)
    right, _, _ = projection(alternative)
    aligned = alignment(left, right)
    return {'version': 1, 'distance': aligned['distance'],
            'marks': marks_for_sites(native, aligned['chosen'])}


def existing_sites(prediction):
    _, positions, _ = projection(prediction['text'])
    return {('char', index) for index, (_, offset, _) in enumerate(positions)
            if any(start <= offset < start + length for start, length, _ in prediction['spans_utf16'])}


def evaluate_case(native, alternative, expected=None):
    """경고를 먼저 만든 뒤 정답과 대조. 입력 prediction은 읽기만 한다."""
    warning = disagreement_marks(native['text'], alternative['text'])
    generated = {(mark['kind'], mark['index']) for mark in warning['marks']}
    strategies = {'current': existing_sites(native), 'disagreement': generated,
                  'combined': existing_sites(native) | generated}
    result = {'warning': warning, 'scored': expected is not None}
    if expected is None:
        return result
    if any(unicodedata.normalize('NFC', text) != text for text in (native['text'], expected)):
        return result | {'scored': False, 'reason': 'non_nfc_position_evaluation'}
    compact = projection(native['text'])[0]
    oracle = alignment(compact, projection(expected)[0], all_paths=True)
    result.update(wrong=oracle['distance'] > 0, oracle_distance=oracle['distance'],
                  oracle_ambiguous=oracle['ambiguous'],
                  oracle_possible=len(oracle['possible']), oracle_certain=len(oracle['certain']),
                  oracle_marks=marks_for_sites(native['text'], oracle['chosen']), strategies={})
    for name, sites in strategies.items():
        # lower/upper는 각 위치의 모호성 범위다. 동시에 가능한 한 정렬의 통계로 주장하지 않는다.
        warned = bool(generated) if name == 'disagreement' else native['unsure_count'] > 0 or (name == 'combined' and bool(generated))
        result['strategies'][name] = {'warned': warned, 'sites': len(sites),
            'certain_hits': len(sites & oracle['certain']), 'possible_hits': len(sites & oracle['possible']),
            'definite_false': len(sites - oracle['possible']),
            'missed_certain': len(oracle['certain'] - sites),
            'char_sites': sum(kind == 'char' for kind, _ in sites),
            'gap_sites': sum(kind == 'gap' for kind, _ in sites)}
    return result


def summarize(evaluations):
    rows = [row for row in evaluations if row['analysis']['scored']]
    result = {'total': len(evaluations), 'scored': len(rows),
              'excluded': len(evaluations) - len(rows),
              'ambiguous_cases': sum(row['analysis']['oracle_ambiguous'] for row in rows),
              'oracle_possible_sites': sum(row['analysis']['oracle_possible'] for row in rows),
              'oracle_certain_sites': sum(row['analysis']['oracle_certain'] for row in rows), 'strategies': {}}
    for name in ('current', 'disagreement', 'combined'):
        counts = Counter()
        for row in rows:
            analysis, item = row['analysis'], row['analysis']['strategies'][name]
            counts['tp' if item['warned'] and analysis['wrong'] else
                   'fp' if item['warned'] else 'fn' if analysis['wrong'] else 'tn'] += 1
            counts['wrong_case_with_certain_hit'] += int(analysis['wrong'] and item['certain_hits'] > 0)
            counts['wrong_case_with_possible_hit'] += int(analysis['wrong'] and item['possible_hits'] > 0)
            for key in ('sites', 'certain_hits', 'possible_hits', 'definite_false', 'missed_certain', 'char_sites', 'gap_sites'):
                counts[key] += item[key]
        result['strategies'][name] = {key: counts[key] for key in (
            'tp', 'fp', 'fn', 'tn', 'wrong_case_with_certain_hit', 'wrong_case_with_possible_hit',
            'sites', 'certain_hits', 'possible_hits', 'definite_false', 'missed_certain', 'char_sites', 'gap_sites')}
    return result
