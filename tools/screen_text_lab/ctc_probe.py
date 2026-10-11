"""실제 제품의 단일 CTC 패스를 관측한다. 관측값은 제품 반환값에 영향을 주지 않는다."""
from collections import deque
from contextlib import contextmanager
from time import perf_counter

from .ctc_analysis import BEAM_WIDTH, TOP_K, inspect_output


def match_annotations(boxes, regions):
    def overlap(a, b):
        area = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
        small = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
        return area / small if small else 0.
    matches = [[j for j, region in enumerate(regions) if overlap(box, region['box']) >= .5] for box in boxes]
    counts = {j: sum(j in row for row in matches) for j in range(len(regions))}
    return {i: regions[row[0]]['text'] for i, row in enumerate(matches)
            if len(row) == 1 and counts[row[0]] == 1 and isinstance(regions[row[0]].get('text'), str)}


@contextmanager
def capture_ctc(module, engine, case):
    import numpy as np
    original_read, original_rec, original_decode = engine._read, engine._rec, module.ctc_decode
    missing = object()
    saved_read = engine.__dict__.get('_read', missing)
    evidence = {'version': 1, 'status': 'ok', 'beam_width': BEAM_WIDTH, 'top_k': TOP_K,
                'events': [], 'diagnostic_ms': 0., 'timing_scope': 'instrumented_not_product_latency'}
    queue = deque()
    order, annotations, boxes, active = [], {}, [], False

    class RecProxy:
        def run(self, *args, **kwargs):
            result = original_rec.run(*args, **kwargs)
            if active:
                queue.extend(result[0][slot] for slot in range(len(result[0])))
            return result

    def decode(probs, charset):
        product = original_decode(probs, charset)
        if not active:
            return product
        started = perf_counter()
        event = {}
        try:
            index = order[len(evidence['events'])]
            full = queue.popleft()
            if not np.shares_memory(full, probs) or not np.array_equal(full[:len(probs)], probs):
                raise ValueError('CTC slice does not match actual inference output')
            event = {'detection_index': index, 'box': list(boxes[index]),
                     'annotation_status': 'matched' if index in annotations else 'unmatched_or_ambiguous'}
            event.update(inspect_output(full, len(probs), charset, product, annotations.get(index)))
        except Exception as error:
            # 진단 실패를 보존하되 이미 얻은 제품 결과는 그대로 돌려준다.
            evidence['status'] = 'error'
            event.update(status='error', error_type=type(error).__name__)
        evidence['events'].append(event)
        evidence['diagnostic_ms'] += (perf_counter()-started)*1000
        return product

    def read(image, selected, cancelled):
        nonlocal active, order, annotations, boxes
        boxes = selected
        evidence['work_image_size'] = [int(image.shape[1]), int(image.shape[0])]
        if evidence['work_image_size'] != case['image_size'] or len(boxes) > 128:
            evidence['status'] = 'input_resized' if evidence['work_image_size'] != case['image_size'] else 'box_limit'
            return original_read(image, selected, cancelled)
        widths = [max(8, int(np.ceil(module.REC_HEIGHT * (x1-x0) / max(1, y1-y0)))) for x0,y0,x1,y1 in boxes]
        order = sorted(range(len(boxes)), key=lambda i: widths[i])
        annotations = match_annotations(boxes, case.get('regions', [])) if case.get('review_status') in {'generated', 'reviewed'} else {}
        active = True
        try:
            result = original_read(image, selected, cancelled)
            if len(evidence['events']) != len(boxes) or queue:
                evidence['status'] = 'error'
            return result
        finally:
            active = False

    try:
        engine._rec, engine._read, module.ctc_decode = RecProxy(), read, decode
        yield evidence
    finally:
        engine._rec, module.ctc_decode = original_rec, original_decode
        if saved_read is missing:
            delattr(engine, '_read')
        else:
            engine._read = saved_read


def finish_diagnosis(evidence, case, pack_prediction):
    from screen_text.layout import TextBox
    from .metrics import score_case
    if evidence['status'] != 'ok':
        return evidence
    events = sorted(evidence['events'], key=lambda row: row['detection_index'])
    if any(row['status'] != 'ok' for row in events):
        return evidence | {'status': 'limited'}
    evidence['variants'] = {}
    for variant in ('full_greedy', 'beam8'):
        boxes = []
        for row in events:
            text = (row['full_text'] if variant == 'full_greedy' else row['beam'][0]['text']).strip()
            x0,y0,x1,y1 = row['box']
            if text:
                boxes.append(TextBox(x0,y0,x1-x0,y1-y0,text,row['product_score']))
        prediction = pack_prediction(boxes)
        evidence['variants'][variant] = {'prediction': prediction, 'metrics': score_case(case,prediction),
                                         'score_scope': 'baseline_scores_retained_not_beam_confidence'}
    return evidence


def summarize_ctc(records):
    from collections import Counter
    from .diagnostic_analysis import analyze_candidates
    diagnosed = [r for r in records if 'ctc_diagnostic' in r.get('prediction', {})]
    if not diagnosed:
        return None
    eligible = [r for r in diagnosed if r['status']=='ok' and r.get('metrics') and r['prediction']['ctc_diagnostic']['status']=='ok']
    summary = {'cases':len(diagnosed), 'eligible':len(eligible),
               'statuses':dict(Counter(r['prediction']['ctc_diagnostic']['status'] for r in diagnosed)), 'variants':{}}
    for variant in ('full_greedy','beam8'):
        right = [r | r['prediction']['ctc_diagnostic']['variants'][variant] for r in eligible]
        summary['variants'][variant] = analyze_candidates(eligible,right)
    events = [e for r in eligible for e in r['prediction']['ctc_diagnostic']['events']]
    summary['events'] = len(events)
    summary['truncated_events'] = sum(e['used_steps'] < e['full_steps'] for e in events)
    summary['full_changes'] = sum(e['product_text'] != e['full_text'] for e in events)
    summary['beam_changes_no_space'] = sum(''.join(e['product_text'].split()) != ''.join(e['beam'][0]['text'].split()) for e in events)
    preference = Counter()
    for e in events:
        if 'expected' not in e:
            preference['unmatched_annotation'] += 1
        elif ''.join(e['expected'].split()) == ''.join(e['product_text'].split()):
            preference['correct_greedy'] += 1
        else:
            a,b = (e['masses']['no_space'][key] for key in ('expected','greedy'))
            if a['status']!='ok' or b['status']!='ok':
                preference['unscorable_mass'] += 1
            else:
                delta = a['log_mass']-b['log_mass']
                preference['expected_preferred' if delta>1e-6 else 'greedy_preferred' if delta < -1e-6 else 'tie'] += 1
    summary['no_space_mass_preference'] = dict(preference)
    return summary
