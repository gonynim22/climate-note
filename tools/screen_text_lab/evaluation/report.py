"""Small standalone HTML for a saved-record study; text is always escaped."""
from html import escape
import json
from pathlib import Path


def render_report(analysis, decision=None):
    """Return an offline report without image fetching, JavaScript or OCR."""
    esc = lambda value: escape(str(value), quote=True)
    metrics = {key: analysis[key] for key in ("input_sha256", "expected_cases", "scored_pairs", "excluded_pairs",
                                              "baseline", "candidate", "bootstrap", "transitions", "integrity_issues")}
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>OCR independent evaluation</title>',
             '<style>body{font:15px sans-serif;margin:28px;color:#17233c}table{border-collapse:collapse;width:100%}',
             'td,th{border:1px solid #ccc;padding:8px;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere}',
             'th{background:#eef3fa}details{margin:14px 0}</style>',
             '<h1>저장된 OCR 결과의 독립 비교</h1><p>모델 실행·제품 변경·배포 승인이 아닙니다.</p>',
             '<pre>' + esc(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False)) + '</pre>']
    if decision is not None:
        parts.append('<h2>지표별 판정</h2><pre>' + esc(json.dumps(decision, ensure_ascii=False, indent=2, allow_nan=False)) + '</pre>')
    parts.append('<table><thead><tr><th>사례 / 독립 그룹</th><th>정답</th><th>기준</th><th>후보</th></tr></thead><tbody>')
    for row in analysis["rows"]:
        parts.append('<tr><td>' + esc(row["case_id"]) + '<br>' + esc(row["cluster"]) + '</td>')
        for text in (row["metadata"]["expected"]["text"], row["baseline_text"], row["candidate_text"]):
            parts.append('<td><pre>' + esc(text) + '</pre></td>')
        parts.append('</tr>')
        if row["baseline"]["table"] is not None:
            parts.append('<tr><td>표</td>')
            for table in (row["metadata"]["expected"]["table"], row["baseline_table"], row["candidate_table"]):
                parts.append('<td><pre>' + esc(json.dumps(table, ensure_ascii=False)) + '</pre></td>')
            parts.append('</tr>')
    parts.append('</tbody></table><h2>범위와 한계</h2><ul>')
    parts.extend('<li>' + esc(value) + '</li>' for value in analysis["limitations"])
    parts.append('</ul></html>')
    return ''.join(parts)


def save_report(directory, analysis, decision=None):
    """Write only to a newly created caller-owned directory, without overwrites."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    result = {"analysis": analysis, "decision": decision}
    with open(directory / "result.json", "x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    with open(directory / "report.html", "x", encoding="utf-8") as stream:
        stream.write(render_report(analysis, decision))
    status = decision["status"] if decision else "research_comparison_only"
    with open(directory / "summary.md", "x", encoding="utf-8") as stream:
        stream.write(f"# OCR saved-record evaluation\n\nStatus: {status}\n\n"
                     f"Pairs: {analysis['scored_pairs']} / {analysis['expected_cases']}\n\n"
                     f"Input SHA-256: `{analysis['input_sha256']}`\n\n"
                     "No model execution or deployment approval. See result.json and report.html.\n")
    return directory / "report.html"
