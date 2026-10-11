"""명시적 수동 성능 진단. 세션/검출 재사용, 소유 worker, 정답 비의존."""
from collections import defaultdict
import hashlib
from pathlib import Path
from time import perf_counter

from .corpus import digest, json_hash, read_json
from .disagreement import disagreement_marks


def recognize_pair(engine, rgb, cancelled=lambda: False):
    """한 번 검출하고 원래 인식 결과를 반환한다. 추가 판독 실패/취소 시 인스턴스 복원."""
    from screen_text import engine as module
    from screen_text.layout import TextBox
    from .engine_adapter import pack_prediction
    from .recognizers import read_regions
    original = engine._read
    missing = object()
    saved = engine.__dict__.get('_read', missing)
    captured = {}

    def dual(image, boxes, cancel):
        native = original(image, boxes, cancel)
        tick = perf_counter()
        if cancel():
            raise module.RecognitionCancelled
        alternative = read_regions(module, engine, image, boxes, cancel,
                                   {'format': 'paddle', 'height': module.REC_HEIGHT, 'channels': 3}, 'ink-light')
        captured.update(boxes=boxes, alternative=alternative, second_read_ms=(perf_counter() - tick) * 1000)
        return native

    engine._read = dual
    try:
        native = pack_prediction(engine.recognize(rgb, cancelled))
        if cancelled():
            raise module.RecognitionCancelled
        scale = min(module.UPSCALE, module.MAX_SIDE / max(rgb.shape[:2]))
        boxes = [TextBox(round(x0 / scale), round(y0 / scale), max(1, round((x1 - x0) / scale)),
                         max(1, round((y1 - y0) / scale)), text.strip(), score)
                 for (x0, y0, x1, y1), (text, score) in zip(captured['boxes'], captured['alternative']) if text.strip()]
        alternative = pack_prediction(boxes)
        warning = disagreement_marks(native['text'], alternative['text'])
        return native, alternative, warning, captured['second_read_ms']
    finally:
        if saved is missing:
            delattr(engine, '_read')
        else:
            engine._read = saved


def select_cases(records):
    """정답/예측/오류를 보지 않고 category×condition별 이미지 해시 한 개를 선택한다."""
    groups = defaultdict(list)
    for row in records:
        groups[(row.get('tags', {}).get('category', 'unknown'), row.get('tags', {}).get('condition', 'unknown'))].append(row)
    return [min(group, key=lambda row: (hashlib.sha256(('warning-v1:' + row['image_sha256']).encode()).hexdigest(), row['case_id']))
            for _, group in sorted(groups.items())]


def timing_summary(rows):
    import math
    import statistics
    result = {}
    for name in ('native_ms', 'dual_ms', 'extra_ms', 'second_read_ms'):
        values = sorted(row[name] for row in rows)
        result[name] = {'count': len(values), 'median': statistics.median(values),
                        'p95': values[math.ceil(len(values) * .95) - 1], 'min': values[0], 'max': values[-1]}
    result['median_paired_ratio'] = statistics.median(row['dual_ms'] / row['native_ms'] for row in rows)
    return result


def worker(directory):
    import os
    import numpy as np
    from PIL import Image
    from tools.verify import ROOT, inside, write_json
    from .runner import append_event
    from .engine_adapter import pack_prediction
    from screen_text.engine import OcrEngine
    directory = inside(directory, ROOT / 'output/harness')
    if Path(os.environ.get('CLIMATENOTE_TEST_APPDATA', '')).resolve() != (directory / 'appdata').resolve():
        raise ValueError('격리된 AppData에서만 성능 진단을 실행합니다')
    request = read_json(directory / 'request.json')
    # 요청에는 PNG 위치/해시만 있다. 정답과 이전 OCR 예측은 worker에 전달하지 않는다.
    tick = perf_counter()
    engine = OcrEngine(threads=request['threads'])
    load_ms = (perf_counter() - tick) * 1000
    images = []
    for item in request['cases']:
        path = inside(item['path'], ROOT / 'output/harness')
        if digest(path) != item['sha256']:
            raise ValueError('측정 PNG 해시 불일치')
        with Image.open(path) as image:
            images.append(np.asarray(image.convert('RGB')).copy())
    for rgb in images[:3]:
        pack_prediction(engine.recognize(rgb))
        recognize_pair(engine, rgb)
    rows = []
    for repeat in range(request['repeats']):
        for index, (item, rgb) in enumerate(zip(request['cases'], images)):
            outputs, times = {}, {}
            order = ('native', 'dual') if (repeat + index) % 2 == 0 else ('dual', 'native')
            for mode in order:
                tick = perf_counter()
                outputs[mode] = pack_prediction(engine.recognize(rgb)) if mode == 'native' else recognize_pair(engine, rgb)
                times[mode] = (perf_counter() - tick) * 1000
            native, alt, warning, second_ms = outputs['dual']
            if native != outputs['native']:
                raise ValueError('이중 판독이 원문/복사/기존 경고를 바꿨습니다')
            row = {'case_id': item['case_id'], 'repeat': repeat, 'order': list(order),
                   'native_ms': times['native'], 'dual_ms': times['dual'],
                   'extra_ms': times['dual'] - times['native'], 'second_read_ms': second_ms,
                   'native_sha256': json_hash(native), 'alternative_sha256': json_hash(alt),
                   'warning': warning}
            rows.append(row)
            append_event(directory / 'timings.jsonl', row)
            if len(rows) % 60 == 0:
                print(f"측정 {len(rows)}/{len(images) * request['repeats']}", flush=True)
    write_json(directory / 'timing-result.json', {'load_ms': load_ms, 'warmup_pairs': min(3, len(images)),
               'unique_cases': len(images), 'repeats': request['repeats'], 'timing': timing_summary(rows)})
    return 0


def benchmark(baseline, candidate, repeats=5, threads=4):
    import subprocess
    import sys
    from tools.verify import ROOT, create_run_dir, doctor, isolated_env, utc_now, write_json, atomic_text
    from tools.smoke_release import managed_launch
    from .runner import source_inputs, read_jsonl
    from .compare import load_run, pair_records
    if not 2 <= repeats <= 20 or not 1 <= threads <= 64:
        raise ValueError('반복은 2~20회, 스레드는 1~64개입니다')
    left_dir, left_meta, left = load_run(baseline)
    right_dir, right_meta, right = load_run(candidate)
    from .disagreement_report import validate_pair, validate_run_models
    validate_run_models(left_meta, right_meta)
    validate_pair(left, right)
    left, right, _, _ = pair_records(left, right)
    if any(row['status'] != 'ok' for row in left + right):
        raise ValueError('성능 측정은 두 판독 모두 완료된 실행이 필요합니다')
    selected = select_cases(left)
    if not selected or len(selected) > 256:
        raise ValueError('성능 표본은 1~256개입니다')
    directory = create_run_dir()
    env = isolated_env(directory)
    before = source_inputs()
    files = {str(path): digest(path) for path in (left_dir / 'result.json', left_dir / 'cases.jsonl', right_dir / 'result.json', right_dir / 'cases.jsonl')}
    request = {'repeats': repeats, 'threads': threads,
               'cases': [{'case_id': row['case_id'], 'path': str(left_dir / 'cases' / (row['case_id'] + '.png')),
                          'sha256': row['image_sha256']} for row in selected]}
    result = {'kind': 'disagreement_benchmark', 'status': 'running', 'run_id': directory.name, 'started_at': utc_now(),
              'source_before': before, 'baseline': left_dir.name, 'candidate': right_dir.name, 'input_files': files,
              'selection_rule': 'category-condition / lowest seeded image hash / no outcomes',
              'limitations': ['기존 합성 dev 선택 표본, 새 독립 정확도 평가 아님',
                              'CPU 고정 PNG 처리, PNG 로드/캡처/UI/모델 로드 시간 제외',
                              '검출 1회·동일 세션, 두 번째 인식/줄·표 구성/표시 계산 포함; 제품 적용 아님']}
    write_json(directory / 'request.json', request)
    write_json(directory / 'result.json', result)
    atomic_text(directory / 'summary.md', f'# 불일치 경고 처리 시간\n\n{directory.name}: running\n')
    try:
        environment = doctor()
        result['doctor'] = environment
        if environment['errors']:
            raise ValueError('환경 doctor 실패')
        command = [sys.executable, str(ROOT / 'tools/smoke_release.py'), '_launch', sys.executable,
                   '-m', 'tools.screen_text_lab', '_disagreement-benchmark', str(directory)]
        with managed_launch(command, env, directory / 'worker.log') as (_, process):
            code = process.wait(timeout=600)
        result['worker_returncode'] = code
        if code:
            raise ValueError('성능 진단 worker 실패')
        measurements = read_json(directory / 'timing-result.json')
        rows = read_jsonl(directory / 'timings.jsonl')
        if len(rows) != len(selected) * repeats:
            raise ValueError('성능 진단 레코드 수 불일치')
        # 시간 측정 밖에서 기존 두 실행과 전 필드 대조. worker는 정답을 보지 않는다.
        native_by_id, alt_by_id = ({row['case_id']: row['prediction'] for row in records} for records in (left, right))
        keys = ('text', 'tsv', 'html', 'table', 'boxes', 'blocks', 'unsure_count', 'spans_utf16')
        for row in rows:
            for name, mapping in (('native', native_by_id), ('alternative', alt_by_id)):
                if row[name + '_sha256'] != json_hash({key: mapping[row['case_id']][key] for key in keys}):
                    raise ValueError('반복 판독과 기존 결과 불일치')
        result.update(measurements, status='completed', verified_pairs=len(rows), timings_sha256=digest(directory / 'timings.jsonl'))
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        result.update(status='cancelled' if isinstance(error, KeyboardInterrupt) else 'error', error_type=type(error).__name__, error=str(error))
    after = source_inputs()
    result['source_after'] = after
    if before['files'] != after['files'] or any(digest(Path(path)) != value for path, value in files.items()) or any(digest(Path(item['path'])) != item['sha256'] for item in request['cases']):
        result['status'] = 'inputs_changed'
    result['finished_at'] = utc_now()
    write_json(directory / 'result.json', result)
    summary = result.get('timing', {})
    atomic_text(directory / 'summary.md', f"# 불일치 경고 처리 시간\n\n실행 {directory.name}: {result['status']}\n\n선택 {len(selected)}개 × {repeats}회. 워밍업 3쌍, 호출 순서 교대.\n\n" +
                '\n'.join(f"- {key}: {value}" for key, value in summary.items()) + '\n\n' + '\n'.join(result['limitations']))
    return directory, 0 if result['status'] == 'completed' else 1
