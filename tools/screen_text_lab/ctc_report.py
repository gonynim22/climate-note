"""제품 결과와 구분해 표시하는 오프라인 CTC 증거 패널."""
from .report import esc, percent


def mass_label(value):
    return f"{value['log_mass']:.3f}" if value.get('status') == 'ok' else esc(value.get('status', '미측정'))


def case_panel(record):
    evidence = record.get('prediction', {}).get('ctc_diagnostic')
    if not evidence:
        return ''
    panels = []
    for event in evidence.get('events', []):
        if event.get('status') != 'ok':
            panels.append(f"<p>영역 진단 제외: {esc(event.get('status'))} / {esc(event.get('error_type', ''))}</p>")
            continue
        frames = []
        for frame in event['frames']:
            candidates = ' · '.join(f"{item['char'] or '∅'} {item['p']:.4f}" for item in frame['top'])
            frames.append(f"<tr><td>{frame['t']}</td><td>{'사용' if frame['used'] else '절삭'}</td><td>{frame['blank']:.4f}</td><td>{esc(candidates)}</td></tr>")
        runs = ' | '.join(f"{row['char'] or '∅'}[{row['start']}:{row['end']}]" for row in event['argmax_runs'])
        masses = ''
        if 'masses' in event:
            rows = []
            for scope, group in event['masses'].items():
                rows.append(f"<tr><td>{esc(scope)}</td>" + ''.join(f'<td>{mass_label(group[key])}</td>' for key in ('expected', 'greedy', 'beam')) + '</tr>')
            masses = '<table><thead><tr><th>경로 log mass</th><th>정답</th><th>제품 greedy</th><th>beam8</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        panels.append(f'''<details class="panel"><summary>영역 {event['detection_index']+1} · {esc(event['product_text'])} · {event['used_steps']}/{event['full_steps']}단계 사용</summary>
<p>대응 주석: {esc(event.get('expected', '없음 / 모호함'))}</p>
<p>제품 greedy: <code>{esc(event['product_text'])}</code><br>절삭 전 전체 greedy: <code>{esc(event['full_text'])}</code><br>beam8: <code>{esc(event['beam'][0]['text'])}</code></p>
{masses}<p class="muted">음수 log mass는 값이 클수록 해당 분포가 문자열을 더 선호합니다. 같은 영역·같은 공백 조건끼리 비교하세요. 정답 확률이 아닙니다.</p>
<h3>가장 높은 문자 후보의 연속 구간</h3><pre>{esc(runs)}</pre><p class="muted">∅는 CTC blank입니다. 같은 문자가 연속되면 한 번만 남고, blank 뒤에 다시 나오면 별도 글자입니다. [시작:끝]에서 끝 단계는 포함하지 않습니다.</p>
<details><summary>전체 단계별 상위 5개 문자와 blank 점수</summary><div class="table-wrap"><table><thead><tr><th>단계</th><th>제품 입력</th><th>blank</th><th>상위 후보</th></tr></thead><tbody>{''.join(frames)}</tbody></table></div></details></details>''')
    variants = ''.join(f"<h3>{esc(name)}</h3><pre>{esc(value['prediction']['text'])}</pre>" for name,value in evidence.get('variants', {}).items())
    return f'''<section class="panel"><div class="eyebrow">MODEL OUTPUT / CTC</div><h2>모델 출력과 문자 합치기 진단</h2>
<p>진단 상태: {esc(evidence['status'])} · 관측 계산 {evidence.get('diagnostic_ms', 0):.1f} ms</p>
<p>제품 결과는 그대로 보존합니다. 아래는 같은 모델 출력의 가상 비교이며 제품에 적용되지 않습니다. 정답은 추론 후 채점에만 사용합니다.</p>
<p class="muted">beam8/top5는 사전 없는 근사 탐색입니다. 영역 주석은 위치로 대응하므로 잘림·여분 픽셀과 모델 자체 오류를 단독으로 구분하지 못합니다. 전체 처리 시간은 진단 계산을 포함해 제품 지연시간이 아닙니다. 비교 결과의 상자 점수는 기존 값이며 beam의 신뢰도가 아닙니다.</p>{variants}</section>{''.join(panels)}'''


def analysis_panel(analysis):
    if not analysis:
        return ''
    rows = []
    for name, value in analysis['variants'].items():
        pair = value['overall']
        a,b,c = pair['baseline'],pair['candidate'],pair['changes']
        rows.append(f"<tr><td>{esc(name)}</td><td>{percent(a['no_space_cer'])} → {percent(b['no_space_cer'])}</td><td>{c['no_space_recovered']} / {c['no_space_new_wrong']}</td><td>{a['table_correct_cells']}/{a['table_cells']} → {b['table_correct_cells']}/{b['table_cells']}</td></tr>")
    counts = ' · '.join(f'{key}: {value}' for key,value in analysis['no_space_mass_preference'].items())
    return f'''<section class="panel"><div class="eyebrow">CTC DIAGNOSIS</div><h2>출력 절삭과 디코딩을 바꾸어 보면</h2>
<p>진단 {analysis['eligible']}/{analysis['cases']}개 · 상태 {esc(analysis['statuses'])} · 인식 영역 {analysis['events']}개.
절삭 영역 {analysis['truncated_events']}개 중 전체 출력과 다른 문자열 {analysis['full_changes']}개.
beam의 공백 제외 문자열 변경 {analysis['beam_changes_no_space']}개.</p>
<p class="muted">선택 표본의 원인 탐색이며 독립 정확도 평가가 아닙니다. 제품 결과·모델·사전은 유지합니다. 시간 비교와 후보 신뢰도 평가는 하지 않습니다.</p>
<table><thead><tr><th>가상 비교</th><th>공백 제외 CER</th><th>정답 복구 / 신규 오류</th><th>표 정답 셀</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>공백 제외 경로 질량: {esc(counts)}</p><p class="muted">expected_preferred는 정답 문자열, greedy_preferred는 제품 문자열의 모델 경로 질량이 더 큰 오류 영역입니다. 위치 대응 불가·미채점은 별도 제외합니다. 실제 원본과 단계별 후보는 아래 사례에서 확인하세요.</p></section>'''
