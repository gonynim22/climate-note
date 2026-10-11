"""저장된 두 제품 판독의 위치 경고를 분석하고 오프라인 HTML로 보여 준다."""
from collections import defaultdict
import json
from pathlib import Path
import shutil

from .corpus import digest, json_hash
from .disagreement import evaluate_case, summarize
from .report import esc, shell


def validate_pair(left, right):
    if not left or not right:
        raise ValueError('비교할 판독이 없습니다')
    for records, profile in ((left, 'native'), (right, 'ink-light')):
        for row in records:
            if row['status'] != 'ok':
                continue
            info = row['prediction'].get('recognizer', {})
            if info.get('id') != 'product' or info.get('input_profile') != profile:
                raise ValueError('product/native와 product/ink-light 실행만 비교합니다')
            prediction = row['prediction']
            encoded = prediction['text'].encode('utf-16-le')
            for start, length, token in prediction['spans_utf16']:
                if start < 0 or length <= 0 or encoded[start * 2:(start + length) * 2].decode('utf-16-le') != token:
                    raise ValueError('기존 경고 UTF-16 위치가 원문과 다릅니다')


def validate_run_models(left, right):
    """같은 이름의 다른 모델/제품 버전을 입력 조건의 효과로 혼동하지 않는다."""
    keys = ('screen_text/engine.py', 'screen_text/layout.py', 'tools/screen_text_lab/recognizers.py')
    for key in keys:
        old = left.get('source_before', {}).get('files', {}).get(key)
        new = right.get('source_before', {}).get('files', {}).get(key)
        if old is None or old != new:
            raise ValueError('두 실행의 제품/입력 변환 코드가 다릅니다')
    first = left.get('engine', {}).get('recognizer', {}).get('files')
    second = right.get('engine', {}).get('recognizer', {}).get('files')
    if not first or first != second:
        raise ValueError('두 실행의 모델/사전 해시가 다릅니다')


def highlighted(text, marks):
    """문자를 삽입/교정하지 않는다. 빈 위치는 CSS 표식으로만 표시한다."""
    chars = {mark['start'] for mark in marks if mark['kind'] == 'char'}
    gaps = {mark['start'] for mark in marks if mark['kind'] == 'gap'}
    output = []
    for index in range(len(text) + 1):
        if index in gaps:
            output.append('<span class="gap" role="img" aria-label="이 위치의 누락 가능성" title="다른 판독에만 글자가 있는 위치"></span>')
        if index < len(text):
            token = esc(text[index])
            output.append(f'<mark>{token}</mark>' if index in chars else token)
    return ''.join(output)


def statistics_table(summary):
    rows = []
    for name, title in (('current', '기존 표시'), ('disagreement', '판독 불일치만'), ('combined', '기존 + 불일치')):
        item = summary['strategies'][name]
        precision = f"{item['certain_hits'] / item['sites']:.1%}~{item['possible_hits'] / item['sites']:.1%}" if item['sites'] else '—'
        rows.append(f"<tr><td>{title}</td><td>{item['tp']}</td><td>{item['fn']}</td><td>{item['fp']}</td><td>{item['tn']}</td><td>{item['wrong_case_with_certain_hit']}~{item['wrong_case_with_possible_hit']}</td><td>{item['sites']}</td><td>{precision}</td></tr>")
    return '<div class="table-wrap"><table><thead><tr><th>경고 방식</th><th>오류 화면 경고</th><th>오류 화면 무경고</th><th>정상 오경고</th><th>정상 무경고</th><th>실제 오류 위치에 적중한 화면</th><th>표시 위치 수</th><th>위치 적중률 범위</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def render(directory, result, rows):
    from tools.verify import atomic_text
    assets = Path(__file__).parent / 'assets'
    for name in ('style.css', 'report.js'):
        shutil.copyfile(assets / name, directory / name)
    style = '<style>mark{background:#ffe5a3;color:#322100}.gap{position:relative}.gap:before{content:"▴";position:absolute;bottom:-.8em;left:-.25em;color:#c24d08;font-size:.8em} .transcript{line-height:2.1;white-space:pre-wrap;overflow-wrap:anywhere} .source-png{max-width:100%;height:auto;image-rendering:auto}.summary-note{border-left:4px solid #d97706;padding-left:18px}</style>'
    table_rows = []
    categories = sorted({row.get('tags', {}).get('category', 'unknown') for row in rows})
    for row in rows:
        case_id, analysis = row['case_id'], row['analysis']
        category = row.get('tags', {}).get('category', 'unknown')
        if analysis['scored']:
            item = analysis['strategies']['combined']
            state = 'hit' if item['possible_hits'] else 'miss' if analysis['wrong'] else 'false' if item['warned'] else 'quiet'
            label = {'hit': '위치 적중 가능', 'miss': '오류 위치 놓침', 'false': '정상 오경고', 'quiet': '정상 무경고'}[state]
            counts = f"{item['certain_hits']}~{item['possible_hits']} / {item['sites']}"
        else:
            state, label, counts = 'excluded', '미채점', '—'
        table_rows.append(f'<tr class="case-row" data-search="{esc((case_id + " " + category).lower())}" data-state="{state}" data-category="{esc(category)}"><td><a href="cases/{case_id}.html">{esc(case_id)}</a></td><td>{esc(category)}</td><td>{label}</td><td>{counts}</td></tr>')
        native, alt = row.get('native', {}), row.get('alternative', {})
        text = native.get('text', '')
        marks = analysis.get('warning', {}).get('marks', [])
        original = f'<section class="panel"><h2>실제 실험 입력 PNG · {esc(row["source_kind"])}</h2><a href="{case_id}.png"><img class="source-png" src="{case_id}.png" alt="실험에 사용한 원본 이미지"></a></section>'
        details = f'<section class="panel"><h2>원문 + 불일치 표시</h2><pre class="transcript">{highlighted(text, marks)}</pre><p>주황 배경: 다른 판독과 다른 글자 · ▴: 누락 가능 위치. 원문을 교정하지 않습니다. 기존 경고와 별도로 보여 줍니다.</p></section>'
        details += f'<section class="panel"><h2>비교용 두 번째 판독</h2><pre class="transcript">{esc(alt.get("text", ""))}</pre><h2>정답</h2><pre class="transcript">{esc(row["expected"]["text"])}</pre></section>'
        if analysis['scored']:
            details += f'<section class="panel"><h2>정답 기준 오류 위치 · 평가 전용</h2><pre class="transcript">{highlighted(text, analysis["oracle_marks"])}</pre><p>아래는 결정적 최소 정렬 하나의 예시입니다. 반복 글자 등으로 여러 최소 정렬이 가능한 경우 통계는 모든 정렬의 범위를 사용합니다.</p><pre>{esc(json.dumps(analysis["strategies"], ensure_ascii=False, indent=2))}</pre></section>'
        atomic_text(directory / 'cases' / (case_id + '.html'), shell(case_id, style + f'<h1>{esc(case_id)}</h1><p>{label} · 실제 위치 적중 / 표시 {counts}</p>' + original + details, '../'))
    summary = result['summary']
    body = style + f'<header><p class="eyebrow">DISAGREEMENT / DEVELOPMENT EXPERIMENT</p><h1>틀린 곳을 제대로 가리키는가</h1><p>실행 {esc(result["run_id"])} · {summary["scored"]}개 채점 / {summary["excluded"]}개 제외</p></header>'
    body += '<section class="panel summary-note"><p><strong>원문과 제품 동작은 그대로입니다.</strong> 이 결과는 경고 진단이며 문자 정확도 개선이 아닙니다. 두 출력의 공백 차이를 제외하고 다른 글자/삽입점을 표시했습니다. 정답은 표시 생성 이후 평가에만 사용했습니다.</p><p>같은 모델이 같은 오답을 내면 놓칩니다. 표 구조·띄어쓰기·화면 픽셀 수준의 글자 위치는 이 지표에 포함되지 않습니다.</p></section>'
    body += '<section class="panel"><h2>화면 경고와 실제 표시 위치를 분리한 결과</h2>' + statistics_table(summary) + f'<p>정답의 최소 정렬이 여러 개인 화면 {summary["ambiguous_cases"]}개. 위치 적중률 하한은 모든 정렬에서 확실히 틀린 위치, 상한은 어느 정렬에서든 틀릴 수 있는 위치입니다. 신뢰구간이 아닙니다. 누락 연속 글자는 한 삽입점으로 세므로 문자 오류 수와 분모가 다릅니다.</p></section>'
    if result.get('benchmark'):
        bench = result['benchmark']
        times = bench['timing']
        body += f'<section class="panel"><h2>같은 세션·검출 1회 반복 성능</h2><p>{bench["unique_cases"]}개 × {bench["repeats"]}회 · 워밍업 {bench["warmup_pairs"]}쌍 · 호출 순서 교대</p><p>중앙값: 기존 {times["native_ms"]["median"]:.2f} ms → 이중 판독 {times["dual_ms"]["median"]:.2f} ms. 쌍별 추가 시간 중앙값 {times["extra_ms"]["median"]:.2f} ms.</p><p>P95: 기존 {times["native_ms"]["p95"]:.2f} ms / 이중 판독 {times["dual_ms"]["p95"]:.2f} ms. PNG 로드·캡처·UI·모델 로드는 제외하며 두 번째 판독·표시 계산은 포함합니다.</p></section>'
    body += '<section class="panel"><h2>내용 종류별 결과</h2>'
    for category, summary_slice in result['categories'].items():
        body += f'<details><summary>{esc(category)} · {summary_slice["scored"]}개</summary>{statistics_table(summary_slice)}</details>'
    body += '</section><section class="panel"><h2>원본·불일치 표시·정답 대조</h2><div class="filters"><input id="search" aria-label="사례 검색" placeholder="사례 ID 검색"><select id="state-filter" aria-label="상태"><option value="all">모든 상태</option><option value="hit">위치 적중 가능</option><option value="miss">오류 위치 놓침</option><option value="false">정상 오경고</option><option value="quiet">정상 무경고</option><option value="excluded">미채점</option></select><select id="category-filter" aria-label="종류"><option value="all">모든 종류</option>' + ''.join(f'<option value="{esc(cat)}">{esc(cat)}</option>' for cat in categories) + f'</select><span id="visible-count">{len(rows)}개</span></div><p id="empty-filter" hidden>해당 사례 없음</p><div class="table-wrap"><table><thead><tr><th>사례</th><th>종류</th><th>결과</th><th>위치 적중 / 표시</th></tr></thead><tbody>' + ''.join(table_rows) + '</tbody></table></div></section>'
    atomic_text(directory / 'report.html', shell('판독 불일치 경고의 위치 검증', body))


def analyze(baseline, candidate, benchmark_run=None):
    from tools.verify import ROOT, inside, create_run_dir, isolated_env, utc_now, write_json, atomic_text
    from .compare import load_run, pair_records
    from .runner import source_inputs
    from .metrics import score_case
    left_dir, left_meta, left = load_run(baseline)
    right_dir, right_meta, right = load_run(candidate)
    validate_run_models(left_meta, right_meta)
    validate_pair(left, right)
    left, right, _, _ = pair_records(left, right)
    for directory, records in ((left_dir, left), (right_dir, right)):
        for record in records:
            if digest(directory / 'cases' / (record['case_id'] + '.png')) != record['image_sha256']:
                raise ValueError('실험 PNG 해시 불일치')
            if record['status'] == 'ok' and score_case(record, record['prediction']) != record['metrics']:
                raise ValueError('저장된 채점과 재채점 불일치')
    directory = create_run_dir()
    isolated_env(directory)
    (directory / 'cases').mkdir()
    before = source_inputs()
    result = {'kind': 'disagreement_analysis', 'run_id': directory.name, 'status': 'running', 'started_at': utc_now(),
              'baseline': left_dir.name, 'candidate': right_dir.name, 'source_before': before,
              'input_files': {str(path): digest(path) for path in (left_dir / 'result.json', left_dir / 'cases.jsonl', right_dir / 'result.json', right_dir / 'cases.jsonl')},
              'rule': 'nonspace / raw Unicode / Levenshtein diagonal-delete-insert / preserve native',
              'limitations': ['저장된 개발 자료의 재분석이며 새 독립 평가 아님; 자료 출처와 환경은 사례별 기록 참조', '공백·표 구조·픽셀 단위 문자 위치는 평가 제외',
                              '원문에서의 UTF-16 문자/삽입점 위치; 반복 문자열은 모든 최소 정렬 범위',
                              '제품 인식 동작/원문/복사 결과 변경 없음', '브라우저 시각 검사는 기존 정책 차단으로 미실행']}
    write_json(directory / 'result.json', result)
    atomic_text(directory / 'summary.md', f'# 판독 불일치 경고\n\n{directory.name}: running\n')
    rows = []
    try:
        if benchmark_run:
            path = Path(benchmark_run)
            if not path.is_absolute():
                path = ROOT / 'output/harness' / path
            path = inside(path, ROOT / 'output/harness')
            meta = json.loads((path / 'result.json').read_text(encoding='utf-8'))
            if meta.get('kind') != 'disagreement_benchmark' or meta.get('status') != 'completed' or meta['baseline'] != left_dir.name or meta['candidate'] != right_dir.name or meta['timings_sha256'] != digest(path / 'timings.jsonl'):
                raise ValueError('성능 결과의 입력/완료 상태/해시 불일치')
            result['benchmark'] = {key: meta[key] for key in ('run_id', 'unique_cases', 'repeats', 'warmup_pairs', 'timing', 'verified_pairs')}
            result['input_files'][str(path / 'result.json')] = digest(path / 'result.json')
        for native, alt in zip(left, right):
            eligible = native['status'] == alt['status'] == 'ok'
            analysis = evaluate_case(native['prediction'], alt['prediction'], native['expected']['text'] if native['review_status'] != 'unreviewed' else None) if eligible else {'scored': False, 'reason': 'prediction_incomplete'}
            row = {key: native[key] for key in ('case_id', 'source_group_id', 'source_kind', 'split', 'tags', 'image_sha256', 'expected')}
            row.update(analysis=analysis, native=native.get('prediction', {}), alternative=alt.get('prediction', {}))
            rows.append(row)
            shutil.copyfile(left_dir / 'cases' / (row['case_id'] + '.png'), directory / 'cases' / (row['case_id'] + '.png'))
        groups = defaultdict(list)
        for row in rows:
            groups[row.get('tags', {}).get('category', 'unknown')].append(row)
        result.update(summary=summarize(rows), categories={key: summarize(value) for key, value in sorted(groups.items())})
        atomic_text(directory / 'cases.jsonl', ''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in rows))
        result['cases_sha256'] = digest(directory / 'cases.jsonl')
        render(directory, result, rows)
        result['status'] = 'completed'
    except Exception as error:
        result.update(status='error', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result['source_after'] = source_inputs()
        if before['files'] != result['source_after']['files'] or any(digest(Path(path)) != value for path, value in result['input_files'].items()):
            result['status'] = 'inputs_changed'
        result['finished_at'] = utc_now()
        write_json(directory / 'result.json', result)
        atomic_text(directory / 'summary.md', f"# 판독 불일치 경고\n\n실행 {directory.name}: {result['status']}\n\n" +
                    '```json\n' + json.dumps(result.get('summary', {}), ensure_ascii=False, indent=2) + '\n```\n\n' + '\n'.join(result['limitations']))
    if result['status'] != 'completed':
        raise ValueError('진단 도중 입력이 변경되어 결과를 채택할 수 없습니다')
    return directory / 'report.html'
