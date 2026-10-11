"""경고 감소와 놓친 오류를 같이 보여 주는 오프라인 보고서."""
from pathlib import Path
import shutil

from .disagreement_report import highlighted
from .disagreement import marks_for_sites
from .report import esc, shell


def row_cells(summary):
    return ''.join(f'<td>{summary[key]}</td>' for key in ('scored', 'tp', 'fn', 'fp', 'certain_cases', 'possible_cases', 'sites', 'cli_certain_cases'))


def table(rows):
    return '<div class="table-wrap"><table><thead><tr><th>조건</th><th>채점</th><th>오류 화면 경고</th><th>오류 무경고</th><th>정상 오경고</th><th>확실 위치 적중 화면</th><th>가능 위치 적중 화면</th><th>표시 수</th><th>CLI 확실 적중</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def render(directory, source, result, records, evidence, details):
    from tools.verify import atomic_text
    from .warning_rules import gate_status
    assets = Path(__file__).parent / 'assets'
    for name in ('style.css', 'report.js'): shutil.copyfile(assets / name, directory / name)
    selected = result['selection']
    tune_groups = sum(part == 'tune' for part in result['assignments'].values())
    check_groups = sum(part == 'check' for part in result['assignments'].values())
    body = f'<header><p class="eyebrow">WARNING RULES / DEVELOPMENT EXPERIMENT</p><h1>오경고를 줄이면 무엇을 놓치는가</h1><p>{esc(directory.name)} · 고정 규칙 {len(result["recipe"]["rules"])}개 · 선택: {esc(selected["rule"]["id"])}</p></header>'
    outcome = '새 자료 검증 후보 확보' if result['qualified_for_fresh_evaluation'] else '채택 기준 미달 · 기존 규칙 유지'
    body += f'<section class="panel"><h2>{outcome}</h2><p>원문·문자 정확도·제품은 그대로입니다. 기존 경고를 유지하며 불일치 표시를 일부 거르는 실험입니다. 기존 원문을 그룹 단위로 {tune_groups}개 조정 / {check_groups}개 확인에 나눴습니다. 두 부분 모두 이전에 본 dev 자료이며 새로운 독립 평가가 아닙니다.</p><p>조정 단계 채택 기준: 오류 화면 경고·확실한 위치 적중 각각 95% 이상 유지, 정상 오경고 20% 이상 감소, CLI 확실 적중 90% 이상 유지. 확인용 결과를 보고 규칙을 다시 고르지 않았습니다.</p></section>'
    for name, title in (('tune', '조정용 · 선택에 사용'), ('check', '확인용 · 선택 후 공개'), ('all', '전체 · 설명용 재집계')):
        pair = result['evaluation'][name]
        rows = [f'<tr><td>기존 + 모든 불일치</td>{row_cells(pair["baseline"])}</tr>',
                f'<tr><td>기존 + {esc(selected["rule"]["id"])}</td>{row_cells(pair["selected"])}</tr>']
        body += f'<section class="panel"><h2>{title}</h2>{table(rows)}<p>기준 충족: {"예" if pair["gate"]["passed"] else "아니오"} · {esc(pair["gate"]["checks"])}</p></section>'
    baseline = result['evaluation']['tune']['baseline']
    rows = []
    for comparison in result['comparisons']:
        state = gate_status(comparison['summary'], baseline, result['recipe']['gate'])
        label = '기준' if comparison['rule']['id'] == 'all' else '통과' if state['passed'] else '탈락'
        rows.append(f'<tr><td>{esc(comparison["rule"]["id"])} · {label}</td>{row_cells(comparison["summary"])}</tr>')
    body += '<section class="panel"><h2>고정한 모든 조건의 조정용 결과</h2>' + table(rows) + '<p>문자 점수는 보정된 정답 확률이 아닙니다. 누락 위치는 인접 문자 점수를 사용합니다. none 점수는 기존 불일치 경고를 보존합니다. 규칙 정의는 같은 폴더 plan.json, 선택 시점은 selection.json에 있습니다.</p></section>'
    old = {row['case_id']: row for row in details['baseline']}
    new = {row['case_id']: row for row in details['selected']}
    # 오경고를 줄인 사례와 실제 오류 표시를 잃은 사례를 함께 표시한다.
    examples = []
    for title, predicate in (
        ('정상 화면의 경고를 줄인 사례', lambda a, b: a.get('scored') and not a.get('wrong') and a['warned'] and not b['warned']),
        ('실제 오류의 위치 표시를 잃은 사례', lambda a, b: a.get('certain_hits', 0) > b.get('certain_hits', 0)),
        ('경고가 남은 정상 화면', lambda a, b: b.get('scored') and not b.get('wrong') and b['warned']),
    ):
        chosen = [row for row in records if predicate(old[row['case_id']], new[row['case_id']])][:3]
        examples.extend((title, row) for row in chosen)
    (directory / 'examples').mkdir()
    for title, row in examples:
        case_id = row['case_id']
        shutil.copyfile(source / 'cases' / (case_id + '.png'), directory / 'examples' / (case_id + '.png'))
        marks = marks_for_sites(row['native']['text'], {tuple(site) for site in new[case_id]['kept']})
        all_marks = marks_for_sites(row['native']['text'], {tuple(site) for site in old[case_id]['kept']})
        body += f'<section class="panel"><h2>{title}</h2><p>{esc(case_id)} · {esc(result["assignments"][row["source_group_id"]])}</p><a href="examples/{case_id}.png"><img style="max-width:100%;height:auto" src="examples/{case_id}.png" alt="실험 원본 합성 PNG"></a><h3>기존 불일치 표시</h3><pre class="transcript">{highlighted(row["native"]["text"], all_marks)}</pre><h3>선택 조건의 불일치 표시</h3><pre class="transcript">{highlighted(row["native"]["text"], marks)}</pre><h3>정답</h3><pre>{esc(row["expected"]["text"])}</pre></section>'
    body += '<section class="panel"><h2>제한</h2><p>' + '</p><p>'.join(esc(line) for line in result['limitations']) + '</p></section>'
    style = '<style>mark{background:#ffe5a3;color:#322100}.gap{position:relative}.gap:before{content:"▴";position:absolute;bottom:-.8em;left:-.25em;color:#c24d08}.transcript{line-height:2.1;white-space:pre-wrap;overflow-wrap:anywhere}</style>'
    atomic_text(directory / 'report.html', shell('경고 조건 비교', style + body))
