"""정답을 쓰지 않는 CTC 탐색과, 추론 후의 문자열 점수 계산."""
import math

NEG_INF = float('-inf')
BEAM_WIDTH = 8
TOP_K = 5
MAX_STEPS = 1024


def logadd(a, b):
    if a == NEG_INF:
        return b
    if b == NEG_INF:
        return a
    return max(a, b) + math.log1p(math.exp(-abs(a-b)))


def collapse(indices):
    return tuple(value for i, value in enumerate(indices) if value and (i == 0 or value != indices[i-1]))


def prefix_beam(probs, width=BEAM_WIDTH, top_k=TOP_K):
    """blank/nonblank 끝 확률을 분리해 같은 prefix의 경로 질량을 합친다."""
    import numpy as np
    beams = {(): (0., NEG_INF)}
    for row in probs:
        top = set(np.argsort(-row, kind='stable')[:top_k].tolist()) | {0}
        next_beams = {}
        def add(prefix, blank=NEG_INF, nonblank=NEG_INF):
            if blank == nonblank == NEG_INF:
                return
            pb, pn = next_beams.get(prefix, (NEG_INF, NEG_INF))
            next_beams[prefix] = (logadd(pb, blank), logadd(pn, nonblank))
        for prefix, (pb, pn) in beams.items():
            total = logadd(pb, pn)
            if row[0] > 0:
                add(prefix, blank=total + math.log(float(row[0])))
            for token in sorted(top | ({prefix[-1]} if prefix else set())):
                if token == 0 or row[token] <= 0:
                    continue
                logp = math.log(float(row[token]))
                if prefix and prefix[-1] == token:
                    add(prefix, nonblank=pn+logp)
                    add(prefix+(token,), nonblank=pb+logp)
                else:
                    add(prefix+(token,), nonblank=total+logp)
        beams = dict(sorted(next_beams.items(), key=lambda pair: (-logadd(*pair[1]), pair[0]))[:width])
    return [(tokens, logadd(*pair)) for tokens, pair in sorted(beams.items(), key=lambda pair: (-logadd(*pair[1]), pair[0]))]


def sequence_log_mass(probs, tokens, space_ids=()):
    """전체 경로의 CTC 문자열 질량. space_ids를 blank에 합쳐 공백을 주변화한다."""
    import numpy as np
    labels = [0]
    for token in tokens:
        if token == 0 or token in space_ids:
            raise ValueError('target must contain nonblank labels')
        labels.extend((token, 0))
    selected = probs[:, labels].astype(np.float64)
    if space_ids:
        selected[:, ::2] = (probs[:, 0].astype(np.float64) + probs[:, list(space_ids)].sum(axis=1, dtype=np.float64))[:, None]
    with np.errstate(divide='ignore'):
        logp = np.log(selected)
    previous = np.full(len(labels), -np.inf)
    previous[0] = 0.
    skip = np.array([i >= 2 and label != 0 and label != labels[i-2] for i, label in enumerate(labels)])
    for row in logp:
        move_one = np.concatenate(([-np.inf], previous[:-1]))
        move_two = np.concatenate(([-np.inf, -np.inf], previous[:-2]))[:len(labels)]
        previous = row + np.logaddexp(np.logaddexp(previous, move_one), np.where(skip, move_two, -np.inf))
    return float(previous[0]) if len(labels) == 1 else logadd(float(previous[-1]), float(previous[-2]))


def text_mass(probs, text, charset, no_space=False):
    mapping = {char: i for i, char in enumerate(charset, 1)}
    if any(len(char) != 1 for char in charset) or len(mapping) != len(charset):
        return {'status': 'unsupported_charset'}
    chars = ''.join(text.split()) if no_space else text
    if any(char not in mapping for char in chars):
        return {'status': 'out_of_charset'}
    spaces = tuple(mapping[char] for char in mapping if char.isspace()) if no_space else ()
    value = sequence_log_mass(probs, [mapping[char] for char in chars], spaces)
    return {'status': 'ok' if math.isfinite(value) else 'impossible', 'log_mass': value if math.isfinite(value) else None}


def independent_greedy(probs, charset):
    indices = probs.argmax(axis=1).tolist()
    return ''.join(charset[i-1] for i in collapse(indices))


def inspect_output(full, used_steps, charset, product, expected=None):
    import numpy as np
    if full.ndim != 2 or full.shape[1] != len(charset)+1 or not 0 < used_steps <= len(full):
        raise ValueError('CTC output dimensions do not match')
    if not np.isfinite(full).all() or full.min() < 0 or full.max() > 1 or not np.allclose(full.sum(axis=1), 1., atol=2e-4):
        raise ValueError('CTC output is not a probability distribution')
    used = full[:used_steps]
    independent = independent_greedy(used, charset)
    if independent != product[0]:
        raise ValueError('Independent CTC collapse differs from product')
    all_text = independent_greedy(full, charset)
    result = {'status': 'ok', 'used_steps': used_steps, 'full_steps': len(full), 'product_text': product[0],
              'product_score': product[1], 'full_text': all_text, 'collapse_matches': True,
              'row_sum_max_error': float(np.max(np.abs(full.sum(axis=1)-1.)))}
    if len(full) > MAX_STEPS:
        return result | {'status': 'step_limit'}
    beam = prefix_beam(used)
    result['beam'] = [{'text': ''.join(charset[i-1] for i in tokens), 'log_mass_lower_bound': mass}
                      for tokens, mass in beam[:3]]
    argmax = full.argmax(axis=1)
    top = np.argsort(-full, axis=1, kind='stable')[:, :TOP_K]
    result['frames'] = [{'t': t, 'used': t < used_steps, 'blank': float(full[t, 0]),
                         'top': [{'id': int(i), 'char': charset[i-1] if i else '', 'p': float(full[t, i])} for i in ids]}
                        for t, ids in enumerate(top)]
    runs = []
    for t, token in enumerate(argmax.tolist()):
        if not runs or runs[-1]['id'] != token:
            runs.append({'id': token, 'char': charset[token-1] if token else '', 'start': t, 'end': t+1})
        else:
            runs[-1]['end'] = t+1
    result['argmax_runs'] = runs
    if expected is not None:
        result['expected'] = expected
        result['masses'] = {scope: {name: text_mass(used, text, charset, scope == 'no_space')
                                  for name, text in [('expected', expected), ('greedy', product[0]), ('beam', result['beam'][0]['text'])]}
                            for scope in ('strict', 'no_space')}
    return result
