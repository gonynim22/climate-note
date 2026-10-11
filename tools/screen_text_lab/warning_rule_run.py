"""명시적인 문자 증거 수집과 고정 규칙 비교. 통상 빌드/테스트와 연결하지 않는다."""
import json
from pathlib import Path
import sys

from .corpus import ID_PATTERN, digest, json_hash, read_json
from .runner import read_jsonl, source_inputs


def load_analysis(value):
    from tools.verify import ROOT, inside
    path = Path(value)
    if not path.is_absolute(): path = ROOT / 'output/harness' / path
    directory = inside(path, ROOT / 'output/harness')
    meta = read_json(directory / 'result.json')
    if meta.get('kind') != 'disagreement_analysis' or meta.get('status') != 'completed' or digest(directory / 'cases.jsonl') != meta.get('cases_sha256'):
        raise ValueError('완료된 불일치 분석과 원본 결과 해시가 필요합니다')
    for name, sha in meta['input_files'].items():
        if digest(inside(name, ROOT / 'output/harness')) != sha:
            raise ValueError('원 불일치 분석의 입력이 변경되었습니다')
    rows = read_jsonl(directory / 'cases.jsonl')
    if not rows or len({r['case_id'] for r in rows}) != len(rows) or any(row['split'] != 'dev' or not ID_PATTERN.fullmatch(row['case_id']) for row in rows):
        raise ValueError('중복 없는 개발 자료만 규칙 비교에 사용합니다')
    return directory, meta, rows


def worker(directory):
    import os
    import numpy as np
    from PIL import Image
    from tools.verify import ROOT, inside, write_json
    from screen_text.engine import OcrEngine
    from .runner import append_event
    from .warning_features import collect_case
    directory = inside(directory, ROOT / 'output/harness')
    if Path(os.environ.get('CLIMATENOTE_TEST_APPDATA', '')).resolve() != (directory / 'appdata').resolve():
        raise ValueError('문자 관측은 격리 AppData에서만 실행합니다')
    request = read_json(directory / 'request.json')
    engine = OcrEngine(threads=request['threads'])
    for index, item in enumerate(request['cases']):
        path = inside(item['path'], ROOT / 'output/harness')
        if digest(path) != item['sha256']: raise ValueError('실험 PNG 해시 불일치')
        with Image.open(path) as image:
            rgb = np.asarray(image.convert('RGB')).copy()
        row = {'case_id': item['case_id'], **collect_case(engine, rgb, item['boxes'])}
        for name in ('native', 'alternative'):
            if [r['crop_sha256'] for r in row[name]['regions']] != item['crop_hashes']:
                raise ValueError('원본 검출 crop 해시 불일치')
        append_event(directory / 'features.jsonl', row)
        if (index + 1) % 60 == 0: print(f"문자 관측 {index + 1}/{len(request['cases'])}", flush=True)
    write_json(directory / 'worker-result.json', {'completed': len(request['cases'])})
    return 0


def evaluate(directory, records, features, recipe, assignments):
    from tools.verify import write_json, utc_now
    from .warning_rules import oracle_for, evaluate_rule, select_rule, gate_status
    tune = [row for row in records if assignments[row['source_group_id']] == 'tune']
    check = [row for row in records if assignments[row['source_group_id']] == 'check']
    # 확인용 정답의 위치 채점 전에 조정용의 한 규칙을 파일로 고정한다.
    tune_oracles = {row['case_id']: oracle_for(row) for row in tune}
    comparisons = [{'rule': rule, 'summary': evaluate_rule(tune, features, tune_oracles, rule)[0]} for rule in recipe['rules']]
    selection = select_rule(comparisons, recipe['gate']) | {'frozen_at': utc_now(), 'tune_comparisons_sha256': json_hash(comparisons)}
    write_json(directory / 'selection.json', selection)
    check_oracles = {row['case_id']: oracle_for(row) for row in check}
    oracles = tune_oracles | check_oracles
    baseline_rule = next(rule for rule in recipe['rules'] if rule['id'] == 'all')
    results, details = {}, {}
    for name, subset in (('tune', tune), ('check', check), ('all', records)):
        old, old_detail = evaluate_rule(subset, features, oracles, baseline_rule)
        new, new_detail = evaluate_rule(subset, features, oracles, selection['rule'])
        results[name] = {'baseline': old, 'selected': new, 'gate': gate_status(new, old, recipe['gate'])}
        if name == 'all': details = {'baseline': old_detail, 'selected': new_detail}
    return {'comparisons': comparisons, 'selection': selection, 'evaluation': results,
            'qualified_for_fresh_evaluation': selection['passed_tune_gate'] and results['check']['gate']['passed']}, details


def run(analysis, threads=4):
    from tools.verify import ROOT, create_run_dir, isolated_env, doctor, utc_now, write_json, atomic_text
    from tools.smoke_release import managed_launch
    from .warning_rules import split_groups
    from .warning_rule_report import render
    if not 1 <= threads <= 64: raise ValueError('스레드는 1~64개입니다')
    source, source_meta, records = load_analysis(analysis)
    recipe_path = Path(__file__).parent / 'recipes/warning-rules.json'
    recipe = read_json(recipe_path)
    assignments = split_groups(records, recipe['split_seed'], recipe['tune_fraction'])
    directory = create_run_dir()
    env = isolated_env(directory)
    before = source_inputs()
    inputs = {str(source / name): digest(source / name) for name in ('result.json', 'cases.jsonl')}
    inputs.update(source_meta['input_files'])
    request = {'threads': threads, 'cases': [{'case_id': row['case_id'], 'path': str(source / 'cases' / (row['case_id'] + '.png')),
        'sha256': row['image_sha256'], 'boxes': [r['box'] for r in row['native']['recognizer']['regions']],
        'crop_hashes': [r['crop_sha256'] for r in row['native']['recognizer']['regions']]} for row in records]}
    result = {'kind': 'warning_rule_comparison', 'status': 'running', 'run_id': directory.name,
              'started_at': utc_now(), 'source_run': source.name, 'source_before': before, 'input_files': inputs,
              'recipe': recipe, 'recipe_sha256': digest(recipe_path), 'assignments': assignments,
              'limitations': ['모두 이전에 사용한 합성 dev: 확인용도 새 독립 평가가 아님',
                 '고정 검출 영역에서 문자 점수만 재관측. 문장/복사/기존 경고를 바꾸지 않음',
                 'CTC 점수는 정답 확률이 아님. 누락 지점은 인접 문자 점수 대용',
                 '공백/표 구조/픽셀 문자 위치 평가 제외. 기존 NFC/미검토 위치 제외 보존',
                 '2회 인식+점수 관측 시간은 제품 지연시간으로 사용하지 않음',
                 '브라우저 시각 검사는 기존 정책 차단으로 미실행']}
    write_json(directory / 'plan.json', {'recipe': recipe, 'recipe_sha256': digest(recipe_path), 'assignments': assignments,
                                       'source_sha256': inputs, 'frozen_at': utc_now()})
    write_json(directory / 'request.json', request)
    write_json(directory / 'result.json', result)
    atomic_text(directory / 'summary.md', f'# 경고 조건 비교\n\n{directory.name}: running\n')
    print(f'실행 ID: {directory.name}', flush=True)
    try:
        result['doctor'] = doctor()
        if result['doctor']['errors']: raise ValueError('환경 doctor 실패')
        command = [sys.executable, str(ROOT / 'tools/smoke_release.py'), '_launch', sys.executable,
                   '-m', 'tools.screen_text_lab', '_warning-features', str(directory)]
        with managed_launch(command, env, directory / 'worker.log') as (_, process):
            code = process.wait(timeout=900)
        result['worker_returncode'] = code
        if code: raise ValueError('문자 관측 worker 실패')
        observed = read_jsonl(directory / 'features.jsonl')
        by_id = {row['case_id']: row for row in observed}
        if len(observed) != len(records) or len(by_id) != len(records): raise ValueError('문자 관측 수 불일치')
        keys = ('text', 'tsv', 'html', 'table', 'boxes', 'blocks', 'unsure_count', 'spans_utf16')
        for row in records:
            for name in ('native', 'alternative'):
                if json_hash({key: row[name][key] for key in keys}) != json_hash(by_id[row['case_id']][name]['prediction']):
                    raise ValueError('문자 관측이 이전 판독과 다릅니다')
        result['features_sha256'] = digest(directory / 'features.jsonl')
        result['prediction_pairs_verified'] = len(records)
        evaluation, details = evaluate(directory, records, by_id, recipe, assignments)
        result.update(evaluation)
        write_json(directory / 'details.json', details)
        result['details_sha256'] = digest(directory / 'details.json')
        render(directory, source, result, records, by_id, details)
        result['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        # 모델/관측/보고서 오류를 실행 실패로 보존한다. 자동 재시도는 하지 않는다.
        result.update(status='cancelled' if isinstance(error, KeyboardInterrupt) else 'error', error_type=type(error).__name__, error=str(error))
    finally:
        result['source_after'] = source_inputs()
        if before['files'] != result['source_after']['files'] or any(digest(Path(path)) != sha for path, sha in inputs.items()) or any(digest(Path(item['path'])) != item['sha256'] for item in request['cases']):
            result['status'] = 'inputs_changed'
        result['finished_at'] = utc_now()
        write_json(directory / 'result.json', result)
        atomic_text(directory / 'summary.md', f"# 경고 조건 비교\n\n실행 {directory.name}: {result['status']}\n\n" +
                    '```json\n' + json.dumps({key: result.get(key) for key in ('selection', 'evaluation', 'qualified_for_fresh_evaluation')}, ensure_ascii=False, indent=2) + '\n```\n\n' + '\n'.join(result['limitations']))
    return directory, 0 if result['status'] == 'completed' else 1
