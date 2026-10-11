"""네트워크/서버 없이 열리는 HTML. 자료 문자열은 항상 escape한다."""
import difflib
from html import escape
from pathlib import Path
import shutil

from .metrics import normalize

STATE_LABELS = {"exact": "일치", "wrong": "오류", "unwarned": "무경고 오류", "unscored": "미채점",
                "error": "실행 실패", "not_run": "미실행", "timeout": "시간 초과", "cancelled": "중단",
                "improved": "개선", "regressed": "퇴행", "unchanged": "유지", "changed": "내용 변경"}


def esc(value):
    return escape(str(value), quote=True)


def percent(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def diff_html(expected, actual):
    left, right = normalize(expected), normalize(actual)
    parts = []
    for kind, a, b, c, d in difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if kind == "equal":
            parts.append(esc(right[c:d]))
        else:
            if kind in {"delete", "replace"}:
                parts.append(f'<del title="정답에서 누락 또는 변경">{esc(left[a:b])}</del>')
            if kind in {"insert", "replace"}:
                parts.append(f'<ins title="인식 결과에서 추가 또는 변경">{esc(right[c:d])}</ins>')
    return "".join(parts)


def state_of(record):
    if record["status"] != "ok":
        return record["status"]
    metrics = record.get("metrics")
    if metrics is None:
        return "unscored"
    if metrics["all_exact"]:
        return "exact"
    return "unwarned" if metrics["wrong_without_warning"] else "wrong"


def shell(title, body, root=""):
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'none'; object-src 'none'">
<title>{esc(title)} · 화면 글자 따기 진단실</title><link rel="stylesheet" href="{root}style.css"></head>
<body><div class="layout"><aside class="rail"><a class="brand" href="{root}report.html"><span class="brand-icon" aria-hidden="true">가</span>화면 글자 따기<br><strong>정확도 진단실</strong></a>
<div class="rail-caption">READ · MEASURE · COMPARE</div><nav><a href="{root}report.html">실행 보고서 <span>↗</span></a></nav>
<p class="rail-note">개발용 오프라인 보고서<br>인식 결과를 원본과 대조합니다.</p></aside>
<main>{body}<footer>SCREEN TEXT LAB / 진단 결과는 제품의 정확도 보증이나 배포 승인이 아닙니다.</footer></main></div>
<script src="{root}report.js"></script></body></html>'''


def table_html(rows):
    if not rows:
        return '<p class="muted">표 없음</p>'
    return '<div class="table-wrap"><table class="cells">' + "".join('<tr>' + "".join(f'<td>{esc(cell)}</td>' for cell in row) + '</tr>' for row in rows) + '</table></div>'


def prediction_panel(title, record):
    prediction, metrics = record.get("prediction", {}), record.get("metrics")
    actual = prediction.get("text", "")
    if record["status"] != "ok":
        return f'<section class="panel"><h2>{esc(title)}</h2><p class="badge error">{esc(STATE_LABELS.get(record["status"], record["status"]))}</p><p>{esc(record.get("error_type", "결과 없음"))}</p></section>'
    summary = f'편집 오류 {metrics["errors"]} · CER {percent(metrics["cer"])}' if metrics else "정답 검토 전 · 미채점"
    table_note = ""
    trace_note = ""
    trace = prediction.get("trace")
    if trace:
        minimum = trace.get("min_char_score")
        minimum = "출력 문자 없음" if minimum is None else f"{minimum:.4f}"
        trace_note = f'<p class="muted">실험 {esc(trace["candidate"])} · 검출 {trace["detect_ms"]:.1f} ms · 인식 {trace["read_ms"]:.1f} ms · 비공백 문자 최소 점수 {minimum} (정답 확률 아님)</p>'
    if prediction.get('timing_scope') == 'instrumented_not_product_latency':
        trace_note += '<p class="muted">CTC 진단 계산이 포함된 시간입니다. 제품 지연시간 비교에 사용하지 마세요.</p>'
    if metrics and metrics.get("table"):
        table = metrics["table"]
        table_note = f'<p class="muted">표 셀 정답 {table["correct"]}/{table["cells"]} · 행/열 포함 일치: {"예" if table["exact"] else "아니오"}</p>'
    return f'''<section class="panel"><div class="section-top"><h2>{esc(title)}</h2><span class="mono">{summary}</span></div>
<pre class="transcript">{esc(actual) or '<span class="muted">인식된 글자 없음</span>'}</pre>
<div class="diff-label"><span class="del-key">정답에서 누락·변경</span><span class="ins-key">결과에서 추가·변경</span></div>
<pre class="diff">{diff_html(record['expected']['text'], actual)}</pre>
<p class="muted">제품의 확인 필요 표시 {prediction.get('unsure_count', 0)}곳 · 처리 {prediction.get('total_ms', 0):.1f} ms</p>
{trace_note}{table_note}<details><summary>표 구성과 복사할 텍스트</summary>{table_html(prediction.get('table', []))}<pre>{esc(prediction.get('tsv', ''))}</pre></details></section>'''


def render_case(directory, record, baseline=None, comparison=None):
    from tools.verify import atomic_text
    from .region_report import case_panel
    from .ctc_report import case_panel as ctc_case_panel
    from .recognizer_report import case_panel as recognizer_case_panel
    case_id = record["case_id"]
    state = comparison or state_of(record)
    width, height = record["image_size"]
    boxes = record.get("prediction", {}).get("boxes", [])
    rectangles = []
    box_rows = []
    for index, box in enumerate(boxes, 1):
        x, y, w, h = (float(box[key]) for key in ("x", "y", "w", "h"))
        score = float(box["score"])
        rectangles.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="{"low" if score < .8 else "box"}"/>')
        box_rows.append(f'<tr><td class="mono">{index:02d}</td><td>{esc(box["text"])}</td><td class="mono">{score:.4f}</td><td class="mono">{x:g}, {y:g}, {w:g}, {h:g}</td></tr>')
    region_note = ""
    diagnostic = record.get("prediction", {}).get("region_diagnostic")
    if diagnostic and diagnostic["status"] == "ok":
        for region in record.get("regions", []):
            x0, y0, x1, y1 = region["box"]
            rectangles.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" style="fill:none;stroke:#2563eb;stroke-width:1;stroke-dasharray:4 2"/>')
        region_note = " 파란 점선은 정답 주석 영역입니다."
    tags = " · ".join(f"{key}: {value}" for key, value in record.get("tags", {}).items())
    expected_table = table_html(record["expected"]["table"]) if "table" in record["expected"] else ""
    canvas = f'<div class="canvas" data-width="{width}" style="max-width:{width}px"><img src="{esc(case_id)}.png" width="{width}" height="{height}" alt="{esc(case_id)} 원본 시험 이미지"><svg viewBox="0 0 {width} {height}" aria-hidden="true">{"".join(rectangles)}</svg></div>'
    if not (directory / "cases" / (case_id + ".png")).is_file():
        canvas = '<p class="muted">원본 사본 준비 전에 실행이 종료되었습니다. 실행 오류를 확인하세요.</p>'
    origin = {"synthetic": "합성 이미지", "program_capture": "실제 프로그램 캡처", "user_supplied": "등록된 사용자 자료"}.get(record["source_kind"], record["source_kind"])
    panels = prediction_panel("기준 결과", baseline) + prediction_panel("후보 결과", record) if baseline else prediction_panel("제품 인식 결과", record)
    body = f'''<a class="back" href="../report.html">← 실행 보고서</a><header class="page-heading"><div class="eyebrow">CASE INSPECTOR · {esc(origin)}</div>
<h1>{esc(case_id)}</h1><div class="meta"><span class="badge {esc(state)}">{esc(STATE_LABELS.get(state, state))}</span><span>{width} × {height} px</span><span>{esc(record['split'])}</span></div><p class="muted">{esc(tags)}</p></header>
<section class="panel image-panel"><div class="section-top"><h2>원본 이미지와 인식 영역</h2><div class="image-controls"><label><input id="boxes" type="checkbox" checked> 영역 표시</label><label>확대 <select id="zoom"><option value="fit">맞춤</option><option value="1">100%</option><option value="2">200%</option><option value="4">400%</option></select></label></div></div>
<div class="image-scroll">{canvas}</div>
<p class="muted">주황 테두리는 인식한 영역, 붉은 테두리는 상자 평균 점수 0.8 미만입니다. 테두리 색은 정답 여부를 뜻하지 않습니다.{' 후보의 영역을 표시합니다.' if baseline else ''}{region_note}</p></section>
<section class="panel reference"><div class="section-top"><h2>정답 원문</h2><span class="mono">{esc(record['review_status'])}</span></div><pre class="transcript">{esc(record['expected']['text'])}</pre>{expected_table}</section>
<div class="{'comparison-grid' if baseline else ''}">{panels}</div>
{case_panel(record)}
{ctc_case_panel(record)}
{recognizer_case_panel(record)}
<details class="panel"><summary>인식 상자 {len(boxes)}개 · 평균 점수와 좌표</summary><p class="muted">점수는 모델의 출력이며 정답 확률이 아닙니다. 좌표는 원본 픽셀의 x, y, 폭, 높이입니다.</p><div class="table-wrap"><table><thead><tr><th>번호</th><th>글자</th><th>점수</th><th>좌표</th></tr></thead><tbody>{''.join(box_rows)}</tbody></table></div></details>'''
    atomic_text(directory / "cases" / (case_id + ".html"), shell(case_id, body, "../"))


def condition_panel(analysis):
    if not analysis:
        return ""
    rows = []
    for condition in analysis["conditions"]:
        measured, changes = condition["measured"], condition["changes"]
        delta = "—" if condition["cer_delta"] is None else f'{condition["cer_delta"] * 100:+.2f} %p'
        links = " ".join(f'<a href="cases/{esc(example["case_id"])}.html">악화 예시 {index}</a>'
                         for index, example in enumerate(condition["regression_examples"], 1))
        rows.append(f'''<tr><td>{esc(condition['label'])}</td><td>{condition['pairs']}/{condition['expected_pairs']}</td>
<td>{percent(measured['cer'])}<small>{delta}</small></td><td>{percent(measured['no_space_cer'])}</td>
<td>{measured['exact']}/{measured['scored']}</td><td>{measured['wrong_without_warning']}/{measured['wrong']}</td>
<td>{changes.get('improved', 0)} / {changes.get('regressed', 0)}</td><td>{links or '—'}</td></tr>''')
    return f'''<section class="panel"><div class="eyebrow">SAME CONTENT · DIFFERENT CONDITIONS</div><h2>같은 원문, 화면 조건만 바꾸면</h2>
<p>{esc(analysis['scope'])}</p><p class="muted">원문 {analysis['original_groups']}종 · 이미지 {analysis['records']}개.
전체 평균은 시험 조건에 같은 가중치를 둔 값입니다. 각 줄은 기준(16px 밝음)과 둘 다 채점된 쌍만 사용하며 누락은 비교 수에 표시합니다.
합성 125/150%는 글자와 여백을 함께 키운 렌더 조건입니다. 글꼴 이름은 기본 family이며 글리프별 대체 글꼴을 뜻하지 않습니다.</p>
<div class="table-wrap"><table><thead><tr><th>조건</th><th>비교 / 대상</th><th>CER / 기준 대비</th><th>공백 제외 CER</th><th>문자열 일치</th><th>무경고 / 오류</th><th>개선 / 악화</th><th>원본 확인</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>'''


def warning_panel(analysis):
    if not analysis:
        return ""
    tables = []
    for scope, title in (("strict_all", "공백·표 포함 오류"), ("no_space_text", "공백을 제외한 글자 오류")):
        rows = []
        for row in analysis["scopes"][scope]:
            label = "현재 제품" if row["threshold"] is None else f'제품 + 문자 최소 점수 &lt; {row["threshold"]:g}'
            rows.append(f'<tr><td>{label}</td><td>{row["true_positive"]}</td><td>{row["false_negative"]}</td><td>{row["false_positive"]}</td><td>{row["true_negative"]}</td><td>{percent(row["precision"])}</td></tr>')
        tables.append(f'<h3>{title}</h3><div class="table-wrap"><table><thead><tr><th>경고 방식</th><th>잡은 오류</th><th>놓친 오류</th><th>정상에 경고</th><th>정상·무경고</th><th>경고 중 실제 오류</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    return f'''<section class="panel"><h2>문자 점수로 경고를 늘리면</h2><p>관측 가능한 {analysis['cases']}/{analysis['scored']}개 채점 사례.
관측 없음 {analysis['excluded_missing_trace']}개 · 실패/미채점 {analysis['excluded_unscored_or_failed']}개 별도.
아래는 사례 단위 모의 판정이며 제품 경고와 인식 글자는 바꾸지 않습니다.</p>
<p class="muted">출력된 비공백 문자 중 최저 CTC 점수를 사용합니다. 누락 문자는 점수가 없어 놓칠 수 있습니다.
점수는 정답 확률이 아닙니다. 공백 제외 표에서는 표 구조 오류도 제외하므로 두 기준을 함께 봐야 합니다.</p>{''.join(tables)}</section>'''


def candidate_panel(analysis):
    if not analysis:
        return ""
    groups = [("전체", analysis["overall"])] + [
        (f"{field}: {key}", value) for field, group in analysis["slices"].items() for key, value in group.items()]
    rows = []
    for label, group in groups:
        a, b, c = group["baseline"], group["candidate"], group["changes"]
        time = group["median_time_ratio"]
        time = "—" if time is None else f"{time:.2f}배"
        rows.append(f'''<tr><td>{esc(label)}</td><td>{group['pairs']}/{group['cases']}</td><td>{percent(a['cer'])} → {percent(b['cer'])}</td>
<td>{percent(a['no_space_cer'])} → {percent(b['no_space_cer'])}</td><td>{c['no_space_recovered']} / {c['no_space_new_wrong']}</td>
<td>{a['table_correct_cells']}/{a['table_cells']} → {b['table_correct_cells']}/{b['table_cells']}</td><td>{time}</td></tr>''')
    return f'''<section class="panel"><h2>개선과 새 오류를 함께 비교</h2><p>두 실행 모두 채점된 동일 사례만 비교합니다.
공백 제외 복구/신규 오류는 문자열 완전 일치의 변화를 셉니다. 표는 정답 셀/비교 셀입니다.
시간은 관측 코드 포함 1회 처리 중앙값의 비율이며 반복 성능 측정이 아닙니다.</p>
<div class="table-wrap"><table><thead><tr><th>범위</th><th>쌍 / 대상</th><th>CER</th><th>공백 제외 CER</th><th>복구 / 신규 오류</th><th>표 셀</th><th>시간 비율</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>'''


def render_report(directory, result, records, baseline_records=None, changes=None):
    from tools.verify import atomic_text
    from .region_report import analysis_panel
    from .ctc_report import analysis_panel as ctc_analysis_panel
    from .recognizer_report import model_panel
    directory = Path(directory)
    for name in ("style.css", "report.js"):
        shutil.copyfile(Path(__file__).parent / "assets" / name, directory / name)
    overall = result["metrics"]["overall"]
    comparison = baseline_records is not None
    baseline_by_id = {record["case_id"]: record for record in baseline_records or []}
    changes = changes or {}
    categories = sorted({str(record.get("tags", {}).get("category", "미분류")) for record in records})
    rows = []
    for record in records:
        case_id = record["case_id"]
        state = changes.get(case_id, state_of(record))
        metrics = record.get("metrics")
        category = str(record.get("tags", {}).get("category", "미분류"))
        search = " ".join((case_id, category, record["expected"]["text"], record.get("prediction", {}).get("text", "")))
        errors = metrics["errors"] if metrics else "—"
        delta = ""
        if comparison:
            old = baseline_by_id[case_id].get("metrics")
            delta = str(old["errors"]) + " → " if old else "— → "
        warning = record.get("prediction", {}).get("unsure_count", "—")
        font = record.get("tags", {}).get("font_px", "—")
        theme = record.get("tags", {}).get("theme", "—")
        rows.append(f'''<tr class="case-row" data-state="{esc(state)}" data-category="{esc(category)}" data-search="{esc(search.lower())}"><td><a class="case-link" href="cases/{esc(case_id)}.html">{esc(case_id)} <span>↗</span></a><small>{esc(category)} · {esc(font)}px · {esc(theme)}</small></td><td><span class="badge {esc(state)}">{esc(STATE_LABELS.get(state, state))}</span></td><td class="mono">{delta}{errors}</td><td class="mono">{percent(metrics['cer']) if metrics else '—'}</td><td class="mono">{warning}</td></tr>''')
        render_case(directory, record, baseline_by_id.get(case_id), changes.get(case_id))
    states = sorted({changes.get(record["case_id"], state_of(record)) for record in records})
    filters = ''.join(f'<option value="{esc(state)}">{esc(STATE_LABELS.get(state, state))}</option>' for state in states)
    category_options = ''.join(f'<option value="{esc(category)}">{esc(category)}</option>' for category in categories)
    slice_rows = []
    for key, value in result["metrics"].get("slices", {}).items():
        if key.startswith(("category:", "theme:", "font_px:", "source_kind:")):
            slice_rows.append(f'<tr><td>{esc(key)}</td><td>{value["scored"]}/{value["total"]}</td><td>{percent(value["cer"])}</td><td>{value["wrong_without_warning"]}</td></tr>')
    limitations = ''.join(f'<li>{esc(value)}</li>' for value in result.get("limitations", []))
    compare_note = ""
    if comparison:
        counts = result["comparison"]["counts"]
        compare_note = f'''<section class="comparison-banner"><strong>두 실행의 변화</strong><span>개선 {counts.get('improved',0)}</span><span>퇴행 {counts.get('regressed',0)}</span><span>유지 {counts.get('unchanged',0)}</span><span>내용 변경 {counts.get('changed',0)}</span><span>미채점 {counts.get('unscored',0)}</span><p class="mono">{esc(result['comparison']['baseline'])} → {esc(result['comparison']['candidate'])}</p><p>공통 사례 {len(records)}개 · 비교 제외 {result['comparison']['excluded_baseline']} / {result['comparison']['excluded_candidate']}개</p></section>'''
    status_text = "실행 완료 · 정확도 결과는 아래에 표시" if result["status"] == "completed" else f"실행 상태: {result['status']} · 실패/미실행 사례를 확인하세요"
    median_text = f"{overall['median_ms']:.1f} ms" if overall['median_ms'] is not None else "미측정"
    body = f'''<header class="page-heading"><div class="eyebrow">{'PAIRED COMPARISON' if comparison else 'BASELINE OBSERVATION'} / OFFLINE</div>
<h1>{'두 실행을 비교합니다.' if comparison else '어디서, 어떻게 틀렸을까.'}</h1><p class="lead">원본과 정답을 기준으로 글자 오류와 확인이 필요한 화면을 살펴봅니다.</p><div class="meta"><span class="status-dot"></span><span>{esc(status_text)}</span></div><p class="mono muted">{esc(result['run_id'])} · {esc(result.get('dataset_id',''))} · {esc(result.get('split',''))}</p></header>
{compare_note}<section class="metrics" aria-label="주요 결과"><article><div>글자 오류율 · 공백 포함</div><strong>{percent(overall['cer'])}</strong><small>오류 {overall['errors']} / 정답 {overall['reference_chars']}자</small></article><article><div>전체 문자열 일치</div><strong>{overall['exact']}<em> / {overall['scored']}</em></strong><small>채점 가능한 사례 기준</small></article><article class="attention"><div>틀렸지만 경고 없음</div><strong>{overall['wrong_without_warning']}<em>곳</em></strong><small>오류 사례 {overall['wrong']}개 중</small></article><article><div>처리 성공</div><strong>{overall['completed']}<em> / {overall['total']}</em></strong><small>실행 실패와 미채점 별도 기록</small></article></section>
<section class="panel scope"><strong>이 결과의 범위</strong><ul>{limitations}</ul><p class="muted">원본 묶음별 평균 CER {percent(overall['macro_group_cer'])} · 표 셀 정답 {overall['table_correct_cells']}/{overall['table_cells']} · 처리 중앙값 {median_text}</p></section>
{analysis_panel(result.get('region_analysis'))}
{condition_panel(result.get('condition_analysis'))}
{candidate_panel(result.get('candidate_analysis'))}
{warning_panel(result.get('warning_analysis'))}
{ctc_analysis_panel(result.get('ctc_analysis'))}
{model_panel(result)}
<section class="panel cases-panel"><div class="section-top"><div><div class="eyebrow">EXPLORE THE EVIDENCE</div><h2>사례를 열어 원본과 비교하세요</h2></div><span id="visible-count" class="mono" aria-live="polite">{len(records)}개</span></div>
<div class="filters"><label class="search-label">검색<input id="search" type="search" placeholder="문구 또는 사례 이름 검색"></label><label>결과<select id="state-filter"><option value="all">모든 결과</option>{filters}</select></label><label>내용<select id="category-filter"><option value="all">모든 내용</option>{category_options}</select></label></div>
<div class="table-wrap"><table class="case-table"><thead><tr><th>사례 / 화면 조건</th><th>결과</th><th>{'기준 → 후보 오류' if comparison else '편집 오류'}</th><th>글자 오류율</th><th>확인 필요</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p id="empty-filter" hidden>조건에 맞는 사례가 없습니다.</p></section>
<details class="panel"><summary>조건별 결과 펼치기</summary><div class="table-wrap"><table><thead><tr><th>조건</th><th>채점 / 전체</th><th>글자 오류율</th><th>무경고 오류</th></tr></thead><tbody>{''.join(slice_rows)}</tbody></table></div></details>
<div class="artifact-links"><a href="summary.md">실행 요약</a><a href="result.json">상세 결과 JSON</a><a href="cases.jsonl">사례별 결과</a></div>'''
    # 모델 로드 실패처럼 시간이 없는 실행도 보고서를 열 수 있게 한다.
    atomic_text(directory / "report.html", shell("실행 비교" if comparison else "실행 보고서", body))
    summary = ["# 화면 글자 따기 정확도 진단", "", f"- 실행 ID: {result['run_id']}",
               f"- 상태: {result['status']}", f"- 종류: {result['kind']}",
               f"- 처리 성공: {overall['completed']}/{overall['total']}, 채점: {overall['scored']}",
               f"- 완전 일치: {overall['exact']}/{overall['scored']}",
               f"- 공백 포함 CER: {percent(overall['cer'])}",
               f"- 오류 {overall['errors']}자 / 정답 {overall['reference_chars']}자",
               f"- 무경고 오류: {overall['wrong_without_warning']}/{overall['wrong']}개 오류 사례", "",
               "[HTML 보고서](report.html) · [상세 결과](result.json)", "", "## 확인 범위", ""]
    summary.extend("- " + value for value in result.get("limitations", []))
    if result.get('engine',{}).get('recognizer'):
        info=result['engine']['recognizer']
        summary.extend(['','## 인식 모델·입력 조건','',
            f"- 모델: {info['id']}, 입력: {result['engine']['input_profile']}",
            f"- 인식 모델: {info['model_bytes']} bytes, 문자 클래스(blank 제외): {info['charset_size']}",
            f"- 사전 범위(평가용): {result['engine'].get('charset_coverage')}",
            f"- worker 메모리: {result['engine'].get('memory')}"])
    if result.get('ctc_analysis'):
        ctc = result['ctc_analysis']
        summary.extend(['', '## CTC 원인 진단', '',
            f"- 진단 {ctc['eligible']}/{ctc['cases']}개: {ctc['statuses']}",
            f"- 영역 {ctc['events']}개 / 절삭 {ctc['truncated_events']}개 / 전체 출력과 문자열 차이 {ctc['full_changes']}개",
            f"- 공백 제외 경로 질량: {ctc['no_space_mass_preference']}",
            '- 가상 비교이며 제품 결과 유지. 시간은 진단 계산 포함. 독립 정확도 평가 아님.'])
        for name, value in ctc['variants'].items():
            pair = value['overall']
            summary.append(f"- {name}: 공백 제외 CER {percent(pair['baseline']['no_space_cer'])} → {percent(pair['candidate']['no_space_cer'])}; 복구 {pair['changes']['no_space_recovered']} / 신규 오류 {pair['changes']['no_space_new_wrong']}")
    if result.get("region_analysis"):
        analysis = result["region_analysis"]
        overall_regions = analysis["overall"]
        summary.extend(["", "## 정답 영역 직접 인식", "",
            f"- 비교 {analysis['eligible']}/{analysis['total']}개, 제외 {analysis['excluded']}개: {analysis['statuses']}",
            f"- 같은 사례의 기존 제품 공백 제외 CER: {percent(overall_regions['baseline_cer'])}",
            "- 주석 순서는 영역과 읽기 순서를 모두 알려준 조건이다. 주석은 글꼴 치수이며 완벽한 글리프 경계가 아니다.", "",
            "| 영역 조건 | 직접 인식+제품 구성 CER | 직접 인식+주석 순서 CER | 회복 / 신규 오류 | 양쪽 오류 |",
            "|---|---|---|---|---|"])
        for variant in overall_regions["variants"]:
            changes_regions = variant["case_changes"]
            summary.append(f"| {variant['name']} | {percent(variant['layout_cer'])} | {percent(variant['ordered_cer'])} | {changes_regions['recovered']} / {changes_regions['newly_wrong']} | {changes_regions['both_wrong']} |")
    if result.get("candidate_analysis"):
        paired = result["candidate_analysis"]["overall"]
        a, b, changes = paired["baseline"], paired["candidate"], paired["changes"]
        summary.extend(["", "## 같은 입력의 후보 비교", "",
                        f"- 공통 채점: {paired['pairs']}/{paired['cases']}",
                        f"- 공백 포함 CER: {percent(a['cer'])} → {percent(b['cer'])}",
                        f"- 공백 제외 CER: {percent(a['no_space_cer'])} → {percent(b['no_space_cer'])}",
                        f"- 공백 제외 정답 복구 / 신규 오류: {changes['no_space_recovered']} / {changes['no_space_new_wrong']}",
                        f"- 표 정답 셀: {a['table_correct_cells']}/{a['table_cells']} → {b['table_correct_cells']}/{b['table_cells']}"])
    if result.get("warning_analysis"):
        warning = result["warning_analysis"]
        summary.extend(["", "## 사례 단위 모의 경고 (공백 제외 글자 기준)", "",
                        f"관측 {warning['cases']}/{warning['scored']}개. 표 구조와 위치별 경고는 이 표의 평가 범위 밖이다.", "",
                        "| 경고 방식 | 잡은 오류 | 놓친 오류 | 정상에 경고 | 정상·무경고 |", "|---|---|---|---|---|"])
        for row in warning["scopes"]["no_space_text"]:
            label = "현재 제품" if row["threshold"] is None else f"제품 + 문자 최소 < {row['threshold']}"
            summary.append(f"| {label} | {row['true_positive']} | {row['false_negative']} | {row['false_positive']} | {row['true_negative']} |")
    if result.get("condition_analysis"):
        analysis = result["condition_analysis"]
        summary.extend(["", "## 같은 원문의 조건 비교", "", analysis["scope"], "",
                        "| 조건 | 비교 / 대상 | CER | 공백 제외 CER | 개선 / 악화 |",
                        "|---|---|---|---|---|"])
        for condition in analysis["conditions"]:
            measured, changes = condition["measured"], condition["changes"]
            summary.append(f"| {condition['label']} | {condition['pairs']}/{condition['expected_pairs']} | {percent(measured['cer'])} | {percent(measured['no_space_cer'])} | {changes.get('improved', 0)} / {changes.get('regressed', 0)} |")
    if result.get("error_type"):
        summary.extend(["", "실행 오류: " + result["error_type"]])
    atomic_text(directory / "summary.md", "\n".join(summary) + "\n")
