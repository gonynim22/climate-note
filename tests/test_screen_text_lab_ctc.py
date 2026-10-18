"""작은 분포의 완전 탐색과 가짜 모델로 CTC 관측을 검증한다. 실제 모델 로드 없음."""
from collections import defaultdict
import copy
from itertools import product
import json
import math

import numpy as np
import pytest

from tools.screen_text_lab.ctc_analysis import (collapse, independent_greedy, inspect_output,
    prefix_beam, sequence_log_mass, text_mass)
from tools.screen_text_lab.ctc_probe import capture_ctc, match_annotations, summarize_ctc
from tools.screen_text_lab.engine_adapter import ProductEngine
from tools.screen_text_lab.metrics import score_case
from tools.screen_text_lab.runner import base_record


def exhaustive(probs, spaces=()):
    result = defaultdict(float)
    for path in product(range(probs.shape[1]), repeat=len(probs)):
        result[tuple(i for i in collapse(path) if i not in spaces)] += math.prod(float(probs[t,i]) for t,i in enumerate(path))
    return {key:value for key,value in result.items() if value > 0}


@pytest.mark.parametrize('steps', [0,1,2,3,5])
def test_sequence_mass_and_unpruned_beam_match_all_paths(steps):
    probs = np.random.default_rng(42+steps).dirichlet([1,1,1], size=steps)
    truth = exhaustive(probs)
    beam = dict(prefix_beam(probs, width=1000, top_k=3))
    assert beam.keys() == truth.keys()
    for tokens, mass in truth.items():
        assert math.exp(sequence_log_mass(probs,tokens)) == pytest.approx(mass)
        assert math.exp(beam[tokens]) == pytest.approx(mass)
    assert sequence_log_mass(probs, (1,)*(steps+1)) == -math.inf


def test_space_marginalization_equals_remove_spaces_after_ctc():
    probs = np.random.default_rng(72).dirichlet([1,1,1,1], size=4)
    truth = exhaustive(probs, spaces=(3,))
    for tokens, mass in truth.items():
        assert math.exp(sequence_log_mass(probs,tokens,(3,))) == pytest.approx(mass)
    assert text_mass(probs, '가 나', ['가','나',' '], True) == text_mass(probs, '가나', ['가','나',' '], True)
    assert text_mass(probs, '밖', ['가','나',' '])['status'] == 'out_of_charset'
    assert text_mass(probs, '가', ['가','가',' '])['status'] == 'unsupported_charset'


def test_repeat_needs_blank_and_sequence_best_can_differ_from_greedy():
    probs = np.array([[.40,.35,.25],[.40,.35,.25]])
    assert independent_greedy(probs,['a','b']) == ''
    assert prefix_beam(probs)[0][0] == (1,)
    onehot = np.eye(3)[[1,1,0,1,2,2,0,2]]
    assert independent_greedy(onehot,['#','s']) == '##ss'
    assert prefix_beam(onehot) == [((1,1,2,2),0.)]
    assert text_mass(onehot,'###ss',['#','s']) == {'status':'impossible','log_mass':None}
    json.dumps(inspect_output(onehot,len(onehot),['#','s'],('##ss',1.),'##ss'),allow_nan=False)


@pytest.mark.parametrize('bad', ['negative','nan','unnormalized','wrong_classes','wrong_product'])
def test_invalid_output_is_rejected(bad):
    probs = np.array([[.1,.9]])
    expected = ('a',.9)
    if bad == 'negative': probs[0] = [-.1,1.1]
    elif bad == 'nan': probs[0,0] = np.nan
    elif bad == 'unnormalized': probs *= .1
    elif bad == 'wrong_classes': probs = np.array([[1.]])
    else: expected = ('b',.9)
    with pytest.raises(ValueError):
        inspect_output(probs,1,['a'],expected)


def fake_adapter():
    from screen_text.engine import OcrEngine
    class Session:
        calls = 0
        def run(self, _, feed):
            self.calls += 1
            # width順: short crop uses first four steps; suffix is a separate character.
            assert feed['x'].shape == (2,3,48,96)
            return [np.eye(3,dtype=np.float32)[[[1,1,0,1,2,2,0,2], [2,2,0,2,0,0,0,0]]]]
    engine = object.__new__(OcrEngine)
    engine._rec,engine._charset = Session(), ['#','s']
    engine._detect = lambda image, cancelled=lambda: False: [[20,0,40,10],[0,0,10,10]]
    adapter = object.__new__(ProductEngine)
    adapter.engine, adapter.candidate = engine, 'baseline'
    case = {'case_id':'ctc','source_group_id':'ctc','source_kind':'synthetic','split':'dev',
            'review_status':'generated','image_size':[40,10], 'tags':{},'expected':{'text':'## ss'},
            'regions':[{'box':[0,0,10,10],'text':'##'},{'box':[20,0,40,10],'text':'ss'}]}
    return adapter,case


def png(tmp_path):
    from PIL import Image
    path = tmp_path/'case.png'
    Image.new('RGB',(40,10),'white').save(path)
    return path


def test_probe_tracks_width_sort_and_slice_without_altering_product(tmp_path):
    from screen_text import engine as module
    adapter,case = fake_adapter()
    path = png(tmp_path)
    original_decode,original_rec = module.ctc_decode,adapter.engine._rec
    normal = adapter.recognize(path)
    result = adapter.recognize(path,ctc_case=case)
    for key in ('text','table','tsv','html','boxes','blocks','unsure_count','spans_utf16'):
        assert result[key] == normal[key]
    evidence = result['ctc_diagnostic']
    assert evidence['status'] == 'ok'
    first,second = evidence['events']
    assert (first['detection_index'], first['product_text'], first['full_text'], first['used_steps']) == (1,'##','##ss',4)
    assert first['expected'] == '##' and second['expected'] == 'ss'
    assert result['trace']['decoded_segments'] == normal['trace']['decoded_segments']
    assert adapter.engine._rec is original_rec and module.ctc_decode is original_decode
    assert '_read' not in adapter.engine.__dict__ and original_rec.calls == 2
    assert result['timing_scope'] == 'instrumented_not_product_latency'
    record = base_record(case) | {'status':'ok','prediction':result,'metrics':score_case(case,result)}
    analysis = summarize_ctc([record])
    assert analysis['events'] == 2 and analysis['truncated_events'] == analysis['full_changes'] == 1
    assert analysis['variants']['full_greedy']['overall']['changes']['no_space_new_wrong'] == 1
    # Ground truth changes only after-the-fact mass, never decoder output.
    changed = copy.deepcopy(case)
    changed['regions'][0]['text'] = 'ssss'
    other = adapter.recognize(path,ctc_case=changed)['ctc_diagnostic']
    assert first['beam'] == other['events'][0]['beam']


def test_probe_failure_keeps_result_and_inference_failure_restores(tmp_path, monkeypatch):
    from tools.screen_text_lab import ctc_probe
    from screen_text import engine as module
    adapter,case = fake_adapter()
    path = png(tmp_path)
    original_decode,original_rec = module.ctc_decode,adapter.engine._rec
    def fail(*args): raise ValueError('diagnostic only failure')
    monkeypatch.setattr(ctc_probe,'inspect_output',fail)
    result = adapter.recognize(path,ctc_case=case)
    assert result['text'] == '## ss' and result['ctc_diagnostic']['status'] == 'error'
    assert module.ctc_decode is original_decode and adapter.engine._rec is original_rec
    def fail_model(*args): raise RuntimeError('model failure')
    original_rec.run = fail_model
    with pytest.raises(RuntimeError, match='model failure'):
        adapter.recognize(path,ctc_case=case)
    assert module.ctc_decode is original_decode and adapter.engine._rec is original_rec
    assert '_read' not in adapter.engine.__dict__
    with pytest.raises(module.RecognitionCancelled):
        with capture_ctc(module,adapter.engine,case):
            adapter.engine._read(np.zeros((10,40,3),dtype=np.uint8),[[0,0,10,10]],lambda:True)
    assert module.ctc_decode is original_decode and adapter.engine._rec is original_rec


def test_matching_ambiguity_unreviewed_and_limits(tmp_path):
    adapter,case = fake_adapter()
    assert match_annotations([[0,0,40,10]],case['regions']) == {}
    assert match_annotations([[0,0,10,10]]*2,case['regions']) == {}
    case['review_status'] = 'unreviewed'
    evidence = adapter.recognize(png(tmp_path),ctc_case=case)['ctc_diagnostic']
    assert all('expected' not in row for row in evidence['events'])
    case['image_size'] = [80,20]
    assert adapter.recognize(png(tmp_path),ctc_case=case)['ctc_diagnostic']['status'] == 'input_resized'
    huge = np.tile([.1,.9],(1025,1))
    assert inspect_output(huge,len(huge),['a'],('a',.9))['status'] == 'step_limit'


def test_cli_selection_is_explicit_and_validated_before_run(tmp_path):
    from tools.screen_text_lab.__main__ import parser
    from tools.screen_text_lab.runner import run
    from test_screen_text_lab import make_case,write_manifest
    args = parser().parse_args(['run','--corpus','unused'])
    assert not args.diagnose_ctc and args.case_id is None
    args = parser().parse_args(['run','--corpus','unused','--diagnose-ctc','--case-id','one','--case-id','two'])
    assert args.diagnose_ctc and args.case_id == ['one','two']
    with pytest.raises(ValueError,match='baseline'): run('unused',candidate='upscale-2',diagnose_ctc=True)
    with pytest.raises(ValueError,match='별도'): run('unused',diagnose_ctc=True,diagnose_regions=True)
    write_manifest(tmp_path,[make_case(tmp_path)])
    for ids in ([],['sample','sample'],['missing']):
        with pytest.raises(ValueError,match='case-id'):
            run(tmp_path,case_ids=ids)


def test_ctc_report_escapes_original_strings(tmp_path):
    from tools.screen_text_lab.ctc_report import case_panel, analysis_panel
    adapter,case = fake_adapter()
    result = adapter.recognize(png(tmp_path),ctc_case=case)
    record = base_record(case) | {'status':'ok','prediction':result,'metrics':score_case(case,result)}
    result['ctc_diagnostic']['events'][0]['expected'] = '<script>unsafe</script>'
    html = case_panel(record)
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert '전체 단계별 상위 5개' in html and '제품 지연시간이 아닙니다' in html
    assert '진단 1/1개' in analysis_panel(summarize_ctc([record]))
