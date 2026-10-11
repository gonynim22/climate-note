"""고정 규칙의 적용과 원문 그룹 분할. 런타임 규칙은 정답/태그를 받지 않는다."""
from collections import defaultdict
import hashlib
import math

from .disagreement import alignment, existing_sites, projection


def split_groups(records, seed, fraction=.75):
    categories, membership = defaultdict(set), {}
    for row in records:
        group, category = row['source_group_id'], row.get('tags', {}).get('category', 'unknown')
        if group in membership and membership[group] != category:
            raise ValueError('동일 원문 그룹의 분류가 다릅니다')
        membership[group] = category
        categories[category].add(group)
    assignments = {}
    for category, groups in sorted(categories.items()):
        if len(groups) < 2:
            raise ValueError('분류별 원문 그룹이 2개 이상 필요합니다')
        ordered = sorted(groups, key=lambda group: (hashlib.sha256((seed + ':' + group).encode()).hexdigest(), group))
        count = min(len(ordered) - 1, max(1, math.floor(len(ordered) * fraction)))
        assignments.update({group: 'tune' if i < count else 'check' for i, group in enumerate(ordered)})
    return assignments


def retain(feature, distance, rule):
    mode = rule['mode']
    a, b, gain = feature['native_score'], feature['alternative_score'], feature['gain']
    if mode == 'all': return True
    if mode == 'distance': return distance <= rule['threshold']
    if mode == 'no-gaps': return feature['kind'] != 'gap'
    if mode == 'gap-score': return feature['kind'] != 'gap' or b is None or b >= rule['threshold']
    # 점수를 얻지 못한 곳은 추가 경고를 임의로 제거하지 않는다.
    if a is None or gain is None: return True
    if mode == 'native': return a <= rule['threshold']
    if mode == 'gain': return gain >= rule['threshold']
    if mode == 'either': return a <= rule['native'] or gain >= rule['gain']
    if mode == 'both': return a <= rule['native'] and gain >= rule['gain']
    raise ValueError('지원하지 않는 경고 규칙')


def retained_sites(features, rule):
    return {(row['kind'], row['index']) for row in features['sites'] if retain(row, features['distance'], rule)}


def oracle_for(record):
    import unicodedata
    native, expected = record['native']['text'], record['expected']['text']
    if not record['analysis']['scored']:
        return None
    if any(unicodedata.normalize('NFC', text) != text for text in (native, expected)):
        return None
    return alignment(projection(native)[0], projection(expected)[0], all_paths=True)


def evaluate_rule(records, evidence, oracles, rule):
    summary = {key: 0 for key in ('total', 'scored', 'excluded', 'tp', 'fp', 'fn', 'tn', 'certain_cases', 'possible_cases',
                                  'sites', 'certain_hits', 'possible_hits', 'definite_false', 'cli_certain_cases')}
    details = []
    for row in records:
        summary['total'] += 1
        case_id = row['case_id']
        oracle = oracles[case_id]
        proposed = retained_sites(evidence[case_id]['features'], rule)
        sites = existing_sites(row['native']) | proposed
        warned = row['native']['unsure_count'] > 0 or bool(proposed)
        item = {'case_id': case_id, 'kept': sorted(proposed), 'warned': warned, 'scored': oracle is not None}
        if oracle is None:
            summary['excluded'] += 1
        else:
            wrong = oracle['distance'] > 0
            certain, possible = len(sites & oracle['certain']), len(sites & oracle['possible'])
            summary['scored'] += 1
            summary['tp' if warned and wrong else 'fp' if warned else 'fn' if wrong else 'tn'] += 1
            summary['certain_cases'] += int(certain > 0)
            summary['possible_cases'] += int(possible > 0)
            summary['sites'] += len(sites)
            summary['certain_hits'] += certain
            summary['possible_hits'] += possible
            summary['definite_false'] += len(sites - oracle['possible'])
            summary['cli_certain_cases'] += int(certain > 0 and row['tags'].get('category') == 'cli')
            item.update(wrong=wrong, certain_hits=certain, possible_hits=possible, sites=len(sites))
        details.append(item)
    return summary, details


def gate_status(summary, baseline, gate):
    checks = {'tp_retained': summary['tp'] >= baseline['tp'] * gate['min_tp_retention'],
              'certain_retained': summary['certain_cases'] >= baseline['certain_cases'] * gate['min_certain_hit_retention'],
              'false_reduced': summary['fp'] < baseline['fp'] and summary['fp'] <= baseline['fp'] * gate['max_fp_ratio'],
              'cli_retained': summary['cli_certain_cases'] >= baseline['cli_certain_cases'] * gate['min_cli_certain_hit_retention']}
    return {'passed': all(checks.values()), 'checks': checks}


def select_rule(comparisons, gate):
    baseline = next(row['summary'] for row in comparisons if row['rule']['id'] == 'all')
    eligible = [row for row in comparisons if row['rule']['id'] != 'all' and gate_status(row['summary'], baseline, gate)['passed']]
    chosen = min(eligible, key=lambda row: (row['summary']['fp'], -row['summary']['certain_cases'], row['summary']['sites'], row['rule']['id'])) if eligible else next(row for row in comparisons if row['rule']['id'] == 'all')
    return {'rule': chosen['rule'], 'passed_tune_gate': bool(eligible), 'eligible_count': len(eligible)}
