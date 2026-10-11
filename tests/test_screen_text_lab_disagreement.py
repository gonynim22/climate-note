"""위치 채점은 작은 완전 탐색으로 대조. 실제 모델/대량 자료는 실행하지 않는다."""
import copy
from functools import lru_cache
from html.parser import HTMLParser
from itertools import product

import pytest

from tools.screen_text_lab.disagreement import alignment, disagreement_marks, evaluate_case, summarize
from tools.screen_text_lab.disagreement_report import highlighted, validate_pair


def run_metadata():
    return {'source_before': {'files': {key: 'same' for key in (
        'screen_text/engine.py', 'screen_text/layout.py', 'tools/screen_text_lab/recognizers.py')}},
        'engine': {'recognizer': {'files': {'rec': {'sha256': 'model'}, 'dict': {'sha256': 'dict'}}}}}


def prediction(text, spans=()):
    return {'text': text, 'spans_utf16': list(spans), 'unsure_count': len(spans)}


def exhaustive(a, b):
    """독립 전향 열거: 모든 최단 편집 스크립트의 위치 집합."""
    @lru_cache(None)
    def visit(i, j):
        if i == len(a) and j == len(b):
            return [(0, frozenset())]
        paths = []
        if i < len(a) and j < len(b):
            cost = int(a[i] != b[j])
            sites = {('char', i)} if cost else set()
            paths.extend((distance + cost, marked | sites) for distance, marked in visit(i + 1, j + 1))
        if i < len(a):
            paths.extend((distance + 1, marked | {('char', i)}) for distance, marked in visit(i + 1, j))
        if j < len(b):
            paths.extend((distance + 1, marked | {('gap', i)}) for distance, marked in visit(i, j + 1))
        best = min(distance for distance, _ in paths)
        return [(distance, sites) for distance, sites in paths if distance == best]
    return visit(0, 0)


def test_all_short_binary_strings_match_independent_enumeration():
    words = [''.join(chars) for length in range(4) for chars in product('ab', repeat=length)]
    for a, b in product(words, repeat=2):
        paths = exhaustive(a, b)
        got = alignment(a, b, all_paths=True)
        sets = [sites for _, sites in paths]
        assert got['distance'] == paths[0][0]
        assert got['possible'] == frozenset.union(*sets)
        assert got['certain'] == frozenset.intersection(*sets)
        assert got['chosen'] in sets
        assert got['ambiguous'] == (len(paths) > 1)


@pytest.mark.parametrize('native,alt,sites', [
    ('커및', '커밋', [('char', 1)]), ('ab', 'axb', [('gap', 1)]),
    ('abc', 'ac', [('char', 1)]), ('', '한글', [('gap', 0)]),
    ('ab', 'abx', [('gap', 2)]), ('  a\n b\t', 'ab', []),
    ('aa', 'a', [('char', 1)]), ('a', 'aaa', [('gap', 1)]),
])
def test_deterministic_marks_and_whitespace(native, alt, sites):
    got = disagreement_marks(native, alt)
    assert [(m['kind'], m['index']) for m in got['marks']] == sites


def test_utf16_astral_and_missing_anchor_preserve_original():
    native = '🙂 커및\n값'
    got = disagreement_marks(native, '🙂 커밋\n값9')
    assert got['marks'][0] == {'kind': 'char', 'index': 2, 'start': 3, 'end': 4,
                              'start_utf16': 4, 'length_utf16': 1, 'text': '및'}
    assert got['marks'][1]['start_utf16'] == 7
    for mark in got['marks']:
        data = native.encode('utf-16-le')
        assert data[mark['start_utf16'] * 2:(mark['start_utf16'] + mark['length_utf16']) * 2].decode('utf-16-le') == mark['text']
    astral = disagreement_marks('a🙂b', 'aXb')['marks'][0]
    assert astral['length_utf16'] == 2


def test_case_alarm_is_not_a_location_hit_and_inputs_never_change():
    native, alt = prediction('abc'), prediction('abz')
    before = copy.deepcopy((native, alt))
    got = evaluate_case(native, alt, 'axc')
    assert got['wrong'] and got['strategies']['combined']['warned']
    assert got['strategies']['combined']['possible_hits'] == 0
    assert got['strategies']['combined']['definite_false'] == 1
    assert (native, alt) == before
    assert evaluate_case(native, alt, 'abc')['warning'] == got['warning']


def test_repeated_letters_have_conservative_position_range():
    got = evaluate_case(prediction('aa'), prediction('a'), 'a')
    assert got['oracle_ambiguous'] and got['oracle_possible'] == 2 and got['oracle_certain'] == 0
    assert got['strategies']['disagreement']['certain_hits'] == 0
    assert got['strategies']['disagreement']['possible_hits'] == 1


def test_existing_warnings_union_and_unreviewed_denominators():
    old = prediction('🙂a', [(0, 2, '🙂')])
    result = evaluate_case(old, prediction('🙂x'), 'Xa')
    assert result['strategies']['current']['certain_hits'] == 1
    assert result['strategies']['combined']['sites'] == 2
    assert result['strategies']['combined']['definite_false'] == 1
    rows = [{'analysis': result}, {'analysis': evaluate_case(old, prediction('🙂x'))}]
    got = summarize(rows)
    assert (got['scored'], got['excluded'], got['strategies']['combined']['tp']) == (1, 1, 1)
    assert not evaluate_case(prediction('가'), prediction('가'), '가')['scored']


def test_alignment_bound_is_explicit(monkeypatch):
    from tools.screen_text_lab import disagreement
    monkeypatch.setattr(disagreement, 'MAX_ALIGNMENT_CELLS', 8)
    with pytest.raises(ValueError, match='한도'):
        alignment('aa', 'aa')


def test_html_marks_escape_content_and_preserve_text():
    class Text(HTMLParser):
        def __init__(self): super().__init__(); self.value = ''
        def handle_data(self, value): self.value += value
    value = '<script>🙂& "a"</script>'
    marks = disagreement_marks(value, value + 'x')['marks']
    html = highlighted(value, marks)
    parsed = Text(); parsed.feed(html)
    assert parsed.value == value
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'class="gap"' in html


def test_profile_and_utf16_corruption_refused():
    a = {'status': 'ok', 'prediction': prediction('a', [(0, 1, 'a')])}
    a['prediction']['recognizer'] = {'id': 'product', 'input_profile': 'native'}
    b = copy.deepcopy(a); b['prediction']['recognizer']['input_profile'] = 'ink-light'
    validate_pair([a], [b])
    a['prediction']['spans_utf16'][0] = (0, 1, 'b')
    with pytest.raises(ValueError, match='UTF-16'): validate_pair([a], [b])
    b['prediction']['recognizer']['id'] = 'another'
    with pytest.raises(ValueError): validate_pair([b], [b])


@pytest.mark.parametrize('outcome', ['ok', 'failure', 'cancel'])
def test_shared_detector_reader_restores_on_success_failure_cancel(monkeypatch, outcome):
    import numpy as np
    from screen_text import engine as module
    from tools.screen_text_lab import recognizers
    from tools.screen_text_lab.disagreement_benchmark import recognize_pair
    engine = object.__new__(module.OcrEngine)
    calls = []
    engine._detect = lambda rgb: calls.append('detect') or [(0, 0, 20, 10)]
    original = lambda rgb, boxes, cancel: [('커및', .99)]
    engine._read = original
    def second(module, owner, rgb, boxes, cancel, entry, profile):
        assert owner is engine and profile == 'ink-light'
        if outcome == 'failure': raise ValueError('추가 판독 실패')
        if outcome == 'cancel': raise module.RecognitionCancelled
        return [('커밋', .97)]
    monkeypatch.setattr(recognizers, 'read_regions', second)
    if outcome == 'ok':
        native, alt, warning, _ = recognize_pair(engine, np.zeros((10, 20, 3), np.uint8))
        assert native['text'] == '커및' and alt['text'] == '커밋'
        assert warning['marks'][0]['text'] == '및'
    else:
        with pytest.raises(ValueError if outcome == 'failure' else module.RecognitionCancelled):
            recognize_pair(engine, np.zeros((10, 20, 3), np.uint8))
    assert calls == ['detect'] and engine._read is original


def test_timing_selection_has_no_outcome_dependency_and_paired_statistics():
    from tools.screen_text_lab.disagreement_benchmark import select_cases, timing_summary
    records = [{'case_id': str(i), 'image_sha256': str(i), 'tags': {'category': str(i % 2), 'condition': 'light'},
                'expected': {'text': '정답'}, 'metrics': {'errors': i}} for i in range(8)]
    before = [row['case_id'] for row in select_cases(records)]
    for row in records: row.update(expected={}, metrics={}, prediction={})
    assert before == [row['case_id'] for row in select_cases(list(reversed(records)))]
    got = timing_summary([{'native_ms': 10, 'dual_ms': 15, 'extra_ms': 5, 'second_read_ms': 4},
                          {'native_ms': 20, 'dual_ms': 30, 'extra_ms': 10, 'second_read_ms': 9}])
    assert got['extra_ms']['median'] == 7.5 and got['median_paired_ratio'] == 1.5


def test_manual_command_defaults_and_no_implicit_run():
    from tools.screen_text_lab.__main__ import parser
    args = parser().parse_args(['benchmark-disagreement', '--baseline', 'a', '--candidate', 'b'])
    assert args.repeats == 5 and args.threads == 4
    args = parser().parse_args(['disagreement', '--baseline', 'a', '--candidate', 'b'])
    assert args.benchmark is None


def test_optional_evidence_does_not_change_tensors_or_predictions():
    import numpy as np
    from types import SimpleNamespace
    from screen_text import engine as module
    from tools.screen_text_lab.recognizers import read_regions
    feeds = []
    def run(_, feed):
        feeds.append(feed['x'].copy())
        return [np.array([[[.01, .99]]], dtype=np.float32)]
    engine = SimpleNamespace(_rec=SimpleNamespace(run=run), _charset=['가'])
    args = (module, engine, np.zeros((10, 20, 3), np.uint8), [(0, 0, 20, 10)], lambda: False,
            {'format': 'paddle', 'height': 48, 'channels': 3}, 'ink-light')
    assert read_regions(*args, []) == read_regions(*args)
    assert np.array_equal(feeds[0], feeds[1])


@pytest.mark.parametrize('outcome', ['ok', 'report_error', 'inputs_changed'])
def test_analysis_report_and_failure_status_keep_input_intact(tmp_path, monkeypatch, outcome):
    import json
    from tools import verify
    from tools.screen_text_lab import compare, runner, disagreement_report as report
    from test_screen_text_lab import make_case, record_for
    source_dirs, records = [], []
    for name, profile, value in [('a', 'native', '<a>'), ('b', 'ink-light', '<b>')]:
        folder = tmp_path / name; (folder / 'cases').mkdir(parents=True)
        case = make_case(folder / 'cases', text='<b>')
        row = record_for(case, value)
        row['prediction']['recognizer'] = {'id': 'product', 'input_profile': profile, 'regions': []}
        (folder / 'result.json').write_text('{}', encoding='utf-8')
        (folder / 'cases.jsonl').write_text(json.dumps(row), encoding='utf-8')
        source_dirs.append(folder); records.append([row])
    saved = copy.deepcopy(records)
    output = tmp_path / 'out'; output.mkdir()
    monkeypatch.setattr(verify, 'create_run_dir', lambda: output)
    monkeypatch.setattr(verify, 'isolated_env', lambda directory: {})
    snapshots = iter([{'files': {}}, {'files': {'changed': 'hash'}}])
    monkeypatch.setattr(runner, 'source_inputs', lambda: next(snapshots) if outcome == 'inputs_changed' else {'files': {}})
    monkeypatch.setattr(compare, 'load_run', lambda key: (source_dirs[key], run_metadata(), records[key]))
    if outcome == 'report_error':
        def fail(*args): raise OSError('보고서 실패')
        monkeypatch.setattr(report, 'render', fail)
        with pytest.raises(OSError): report.analyze(0, 1)
    elif outcome == 'inputs_changed':
        with pytest.raises(ValueError, match='입력이 변경'): report.analyze(0, 1)
    else:
        assert report.analyze(0, 1) == output / 'report.html'
        assert (output / 'cases/sample.html').is_file()
        text = (output / 'cases/sample.html').read_text(encoding='utf-8')
        assert '<b>' not in text and '&lt;b&gt;' in text
        assert '&lt;<mark>a</mark>&gt;' in text
    meta = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert meta['status'] == {'ok': 'completed', 'report_error': 'error', 'inputs_changed': 'inputs_changed'}[outcome]
    assert records == saved


def test_same_model_name_with_different_assets_or_code_refused():
    from tools.screen_text_lab.disagreement_report import validate_run_models
    a, b = run_metadata(), run_metadata()
    validate_run_models(a, b)
    b['engine']['recognizer']['files']['rec']['sha256'] = 'other'
    with pytest.raises(ValueError, match='모델/사전'): validate_run_models(a, b)
    b = run_metadata(); b['source_before']['files']['screen_text/engine.py'] = 'other'
    with pytest.raises(ValueError, match='코드'): validate_run_models(a, b)


def test_benchmark_worker_isolated_and_prediction_only(tmp_path, monkeypatch):
    import json
    from PIL import Image
    from screen_text import engine as module
    from tools import verify
    from tools.screen_text_lab import recognizers
    from tools.screen_text_lab.corpus import digest
    from tools.screen_text_lab.disagreement_benchmark import worker
    from tools.screen_text_lab.runner import read_jsonl
    directory = tmp_path / 'output/harness/unit'; directory.mkdir(parents=True)
    path = directory / 'input.png'; Image.new('RGB', (20, 10), 'white').save(path)
    (directory / 'request.json').write_text(json.dumps({'repeats': 2, 'threads': 1,
        'cases': [{'case_id': 'unit', 'path': str(path), 'sha256': digest(path)}]}), encoding='utf-8')
    monkeypatch.setattr(verify, 'ROOT', tmp_path)
    monkeypatch.setenv('CLIMATENOTE_TEST_APPDATA', str(directory / 'appdata'))
    engine = object.__new__(module.OcrEngine)
    engine._detect = lambda rgb: [(0, 0, 20, 10)]
    engine._read = lambda rgb, boxes, cancel: [('ab', .99)]
    monkeypatch.setattr(module, 'OcrEngine', lambda threads: engine)
    monkeypatch.setattr(recognizers, 'read_regions', lambda *args: [('ax', .98)])
    assert worker(directory) == 0
    rows = read_jsonl(directory / 'timings.jsonl')
    assert len(rows) == 2 and rows[0]['order'] != rows[1]['order']
    assert rows[0]['native_sha256'] == rows[1]['native_sha256']
    assert rows[0]['warning']['marks'][0]['text'] == 'b'
    monkeypatch.setenv('CLIMATENOTE_TEST_APPDATA', str(directory / 'wrong'))
    with pytest.raises(ValueError, match='격리'): worker(directory)
