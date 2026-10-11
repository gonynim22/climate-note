"""점수 관측·고정 규칙·누출 방지 자체 검사. 실제 모델/대량 자료 없음."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools.screen_text_lab.warning_features import emitted_tokens, pack_scored, site_features, collect_case
from tools.screen_text_lab.warning_rules import split_groups, retain, evaluate_rule, select_rule, gate_status, oracle_for
from tools.screen_text_lab.disagreement import evaluate_case

RECIPE = json.loads((Path(__file__).parents[1] / 'tools/screen_text_lab/recipes/warning-rules.json').read_text(encoding='utf-8'))


def make_record(case_id='one', native='ab', alternative='ax', expected='ax', group='g1', warning=False):
    a = {'text': native, 'unsure_count': int(warning), 'spans_utf16': [(0, 1, native[0])] if warning else []}
    b = {'text': alternative}
    return {'case_id': case_id, 'source_group_id': group, 'tags': {'category': 'cli'}, 'native': a,
            'alternative': b, 'expected': {'text': expected}, 'analysis': evaluate_case(a, b, expected)}


def test_ctc_emission_blank_repeat_and_space_match_product():
    from screen_text.engine import ctc_decode
    probs = np.array([[.05, .85, .1], [.05, .9, .05], [1, 0, 0], [.05, .8, .15], [.05, .1, .85]])
    decoded = ctc_decode(probs, ['a', ' '])
    tokens = emitted_tokens(probs, ['a', ' '], decoded)
    assert tokens['text'] == 'aa ' and tokens['scores'] == pytest.approx([.85, .8, .85])
    with pytest.raises(ValueError): emitted_tokens(probs, ['a', ' '], ('wrong', 1))


def test_table_reading_order_duplicate_text_and_empty_box_keep_scores():
    boxes = [(100, 30, 120, 40), (0, 0, 20, 10), (100, 0, 120, 10), (0, 30, 20, 40), (0, 60, 20, 70)]
    raw = [('a', .4), (' a ', .8), ('🙂', .9), ('a', .7), (' ', .9)]
    tokens = {i: {'text': text, 'scores': [score] * len(text)} for i, (text, score) in enumerate(raw)}
    got, scores = pack_scored(boxes, raw, tokens, 1)
    assert got['text'] == 'a 🙂\na a'
    assert scores == [.8, .9, .7, .4]
    assert got['table'] == [['a', '🙂'], ['a', 'a']]


def test_features_distinguish_direct_char_and_gap_neighbours():
    got = site_features('🙂 ab', '🙂 axz', [.99, .9, .7], [.99, .9, .95, .96])
    assert got['distance'] == 2
    char, gap = got['sites']
    assert char['text'] == 'b' and char['native_score'] == .7 and char['alternative_score'] == .95
    assert not char['native_uses_neighbours'] and char['gain'] == pytest.approx(.25)
    assert gap['kind'] == 'gap' and gap['native_uses_neighbours'] and gap['native_score'] == .7
    empty = site_features('', 'a', [], [.9])['sites'][0]
    assert empty['native_score'] is None and empty['gain'] is None
    with pytest.raises(ValueError, match='수가'): site_features('a', 'b', [], [.9])
    with pytest.raises(ValueError, match='범위'): site_features('a', 'b', [float('nan')], [.9])


def test_every_registered_rule_boundaries_and_missing_scores():
    ids = [rule['id'] for rule in RECIPE['rules']]
    assert len(ids) == len(set(ids)) == 19
    feature = {'kind': 'char', 'native_score': .98, 'alternative_score': .98, 'gain': 0.0}
    for rule in RECIPE['rules']:
        assert isinstance(retain(feature, 1, rule), bool)
    assert retain(feature, 1, {'mode': 'native', 'threshold': .98})
    assert not retain(feature, 1, {'mode': 'native', 'threshold': .979})
    assert retain(feature, 1, {'mode': 'gain', 'threshold': 0})
    assert not retain(feature, 1, {'mode': 'gain', 'threshold': .001})
    assert not retain(feature | {'kind': 'gap'}, 1, {'mode': 'no-gaps'})
    assert retain(feature | {'native_score': None, 'gain': None}, 1, {'mode': 'native', 'threshold': .8})


def test_split_keeps_all_variants_and_ignores_labels_order():
    rows = [{'source_group_id': f'{cat}-{group}', 'tags': {'category': cat}, 'expected': variant}
            for cat in ('cli', 'table') for group in range(8) for variant in range(3)]
    result = split_groups(rows, 'fixed')
    assert list(result.values()).count('tune') == 12 and list(result.values()).count('check') == 4
    for row in rows: row['expected'] = 'changed'
    assert split_groups(list(reversed(rows)), 'fixed') == result
    rows.append({'source_group_id': 'cli-0', 'tags': {'category': 'other'}})
    with pytest.raises(ValueError): split_groups(rows, 'fixed')


def test_filter_keeps_existing_warning_and_reports_lost_hits():
    row = make_record(warning=True)
    saved = copy.deepcopy(row)
    evidence = {'one': {'features': site_features('ab', 'ax', [.99, .999], [.99, .99])}}
    oracles = {'one': oracle_for(row)}
    all_summary, _ = evaluate_rule([row], evidence, oracles, {'mode': 'all'})
    filtered, details = evaluate_rule([row], evidence, oracles, {'mode': 'native', 'threshold': .9})
    assert all_summary['certain_cases'] == 1 and filtered['certain_cases'] == 0
    assert filtered['tp'] == 1 and filtered['sites'] == 1 and details[0]['warned']
    assert row == saved
    # 정답을 바꿔도 런타임 규칙이 남긴 표시는 같아야 한다.
    row['expected']['text'] = 'ab'; oracles['one'] = oracle_for(row)
    second, new_details = evaluate_rule([row], evidence, oracles, {'mode': 'native', 'threshold': .9})
    assert new_details[0]['kept'] == details[0]['kept'] and second['fp'] == 1


def test_selection_rejects_false_warning_gain_that_loses_real_errors():
    baseline = {'fp': 20, 'tp': 100, 'certain_cases': 80, 'cli_certain_cases': 20, 'sites': 200}
    rejected = baseline | {'fp': 0, 'certain_cases': 70}
    assert not gate_status(rejected, baseline, RECIPE['gate'])['passed']
    choices = [{'rule': {'id': 'all'}, 'summary': baseline}, {'rule': {'id': 'bad'}, 'summary': rejected}]
    assert select_rule(choices, RECIPE['gate'])['rule']['id'] == 'all'
    good = baseline | {'fp': 15, 'certain_cases': 77, 'tp': 96, 'cli_certain_cases': 19}
    choices.append({'rule': {'id': 'good'}, 'summary': good})
    assert select_rule(choices, RECIPE['gate'])['rule']['id'] == 'good'


def test_collect_fake_inference_is_pixel_only_and_does_not_patch_engine():
    from screen_text import engine as module
    class Session:
        def run(self, _, feed):
            return [np.array([[[.01, .98, .01], [.01, .01, .98]]], dtype=np.float32)]
    engine = object.__new__(module.OcrEngine); engine._rec = Session(); engine._charset = ['a', 'b']
    before = dict(engine.__dict__)
    got = collect_case(engine, np.full((10, 20, 3), 255, np.uint8), [(0, 0, 20, 10)])
    assert got['native']['prediction']['text'] == 'ab'
    assert got['native']['scores'] == pytest.approx([.98, .98])
    assert got['features']['sites'] == [] and engine.__dict__ == before
    with pytest.raises(module.RecognitionCancelled):
        collect_case(engine, np.zeros((10, 20, 3), np.uint8), [(0, 0, 20, 10)], lambda: True)
    assert engine.__dict__ == before


def test_selection_file_is_frozen_before_check_oracle(tmp_path, monkeypatch):
    from tools.screen_text_lab import warning_rule_run, warning_rules
    records = [make_record('tune', group='g1'), make_record('check', group='g2')]
    evidence = {row['case_id']: {'features': site_features('ab', 'ax', [.99, .7], [.99, .95])} for row in records}
    original = warning_rules.oracle_for
    def guarded(row):
        if row['case_id'] == 'check': assert (tmp_path / 'selection.json').is_file()
        return original(row)
    monkeypatch.setattr(warning_rules, 'oracle_for', guarded)
    result, _ = warning_rule_run.evaluate(tmp_path, records, evidence, RECIPE, {'g1': 'tune', 'g2': 'check'})
    assert result['selection']['rule']['id'] == 'all'
    assert result['evaluation']['check']['baseline']['tp'] == 1


def test_html_escapes_and_has_real_png_example(tmp_path):
    from PIL import Image
    from tools.screen_text_lab.warning_rule_report import render
    from tools.screen_text_lab.warning_rule_run import evaluate
    source = tmp_path / 'source'; (source / 'cases').mkdir(parents=True)
    directory = tmp_path / 'report'; directory.mkdir()
    row = make_record(native='<a>', alternative='<b>', expected='<a>')
    row.update(source_kind='synthetic', image_sha256='unused')
    Image.new('RGB', (10, 10), 'white').save(source / 'cases/one.png')
    evidence = {'one': {'features': site_features('<a>', '<b>', [.9] * 3, [.9] * 3)}}
    # 작은 보고서 검사에만 사용하는 두 그룹.
    extra = make_record('two', group='g2')
    Image.new('RGB', (10, 10), 'white').save(source / 'cases/two.png')
    evidence['two'] = {'features': site_features('ab', 'ax', [.9] * 2, [.9] * 2)}
    assignments = {'g1': 'tune', 'g2': 'check'}
    result, details = evaluate(directory, [row, extra], evidence, RECIPE, assignments)
    result.update(assignments=assignments, recipe=RECIPE, limitations=['<script>unsafe</script>'])
    render(directory, source, result, [row, extra], evidence, details)
    html = (directory / 'report.html').read_text(encoding='utf-8')
    assert '&lt;script&gt;' in html and '<script>unsafe</script>' not in html
    assert '&lt;a&gt;' in html and (directory / 'examples/one.png').is_file()


def test_cli_warning_rule_experiment_is_explicit():
    from tools.screen_text_lab.__main__ import parser
    args = parser().parse_args(['warning-rules', '--analysis', 'saved'])
    assert args.threads == 4 and args.analysis == 'saved'


def test_feature_worker_uses_isolated_image_only_request(tmp_path, monkeypatch):
    from PIL import Image
    from screen_text import engine as module
    from tools import verify
    from tools.screen_text_lab import warning_rule_run, warning_features
    from tools.screen_text_lab.corpus import digest
    directory = tmp_path / 'output/harness/unit'; directory.mkdir(parents=True)
    path = directory / 'input.png'; Image.new('RGB', (20, 10), 'white').save(path)
    request = {'threads': 1, 'cases': [{'case_id': 'one', 'path': str(path), 'sha256': digest(path),
                                       'boxes': [[0, 0, 20, 10]], 'crop_hashes': ['hash']}]}
    (directory / 'request.json').write_text(json.dumps(request), encoding='utf-8')
    monkeypatch.setattr(verify, 'ROOT', tmp_path)
    monkeypatch.setenv('CLIMATENOTE_TEST_APPDATA', str(directory / 'appdata'))
    monkeypatch.setattr(module, 'OcrEngine', lambda threads: object())
    def collect(engine, rgb, boxes):
        assert rgb.shape == (10, 20, 3) and boxes == [[0, 0, 20, 10]]
        return {name: {'regions': [{'crop_sha256': 'hash'}]} for name in ('native', 'alternative')}
    monkeypatch.setattr(warning_features, 'collect_case', collect)
    assert warning_rule_run.worker(directory) == 0
    assert json.loads((directory / 'worker-result.json').read_text())['completed'] == 1
    monkeypatch.setenv('CLIMATENOTE_TEST_APPDATA', str(directory / 'wrong'))
    with pytest.raises(ValueError, match='격리'): warning_rule_run.worker(directory)


def test_worker_failure_is_recorded_and_plan_precedes_launch(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from PIL import Image
    from tools import verify, smoke_release
    from tools.screen_text_lab import warning_rule_run
    from tools.screen_text_lab.corpus import digest
    source = tmp_path / 'source'; (source / 'cases').mkdir(parents=True)
    (source / 'result.json').write_text('{}'); (source / 'cases.jsonl').write_text('')
    records = [make_record('one', group='g1'), make_record('two', group='g2')]
    for row in records:
        path = source / 'cases' / (row['case_id'] + '.png'); Image.new('RGB', (10, 10), 'white').save(path)
        row['image_sha256'] = digest(path); row['native']['recognizer'] = {'regions': []}
    output = tmp_path / 'out'; output.mkdir()
    monkeypatch.setattr(warning_rule_run, 'load_analysis', lambda value: (source, {'input_files': {}}, records))
    monkeypatch.setattr(warning_rule_run, 'source_inputs', lambda: {'files': {}})
    monkeypatch.setattr(verify, 'create_run_dir', lambda: output)
    monkeypatch.setattr(verify, 'isolated_env', lambda directory: {})
    monkeypatch.setattr(verify, 'doctor', lambda: {'errors': []})
    @contextmanager
    def failed(*args):
        assert (output / 'plan.json').is_file()
        yield None, SimpleNamespace(wait=lambda timeout: 1)
    monkeypatch.setattr(smoke_release, 'managed_launch', failed)
    directory, code = warning_rule_run.run('unused')
    assert directory == output and code == 1
    result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert result['status'] == 'error' and result['worker_returncode'] == 1
    assert not (output / 'selection.json').exists()
