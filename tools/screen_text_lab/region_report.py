"""단계 진단을 기존 오프라인 보고서에 표시한다."""
from .report import esc, percent

LABELS = {"as-annotated": "주석 영역 그대로", "pad-2": "주석 영역 +2px"}
STATUS = {"unreviewed": "정답 미검토", "missing_annotations": "영역 주석 없음",
          "missing_region_text": "영역별 정답 없음", "incomplete_annotations": "주석 순서/내용이 원문 전체와 불일치",
          "input_resized": "제품 입력 축소/확대 발생", "size_limit": "단계 진단 상자 수 상한 초과", "error": "추가 진단 실패"}


def case_panel(record):
    diagnostic = record.get("prediction", {}).get("region_diagnostic")
    if not diagnostic:
        return ""
    if diagnostic["status"] != "ok":
        return f'<section class="panel"><h2>영역 분리 진단 제외</h2><p>{esc(STATUS.get(diagnostic["status"], diagnostic["status"]))}</p><p class="muted">기존 제품 결과와 별도 상태입니다.</p></section>'
    variants = diagnostic["variants"]
    summaries = []
    for variant in variants:
        summaries.append(f'''<tr><td>{LABELS[variant['name']]}</td><td><pre>{esc(variant['prediction']['text'])}</pre></td>
<td>{variant['metrics']['no_space']['errors']}</td><td>{variant['ordered_no_space']['errors']}</td><td>{variant['read_ms']:.1f} ms</td></tr>''')
    regions = []
    for index, row in enumerate(variants[0]["regions"]):
        geometry = diagnostic["geometry"]["regions"][index]
        ratio = geometry["height_ratio"]
        ratio = "—" if ratio is None else f"{ratio:.2f}배"
        outputs = ''.join(f'<td><pre>{esc(value["regions"][index]["text"])}</pre><small>오류 {value["regions"][index]["no_space"]["errors"]}자</small></td>' for value in variants)
        regions.append(f'<tr><td>{index + 1}</td><td><pre>{esc(row["expected"])}</pre></td>{outputs}<td>{percent(geometry["coverage"])}</td><td>{ratio}</td><td>{len(geometry["matched_detections"])}</td></tr>')
    geometry = diagnostic["geometry"]
    return f'''<section class="panel"><h2>정답 좌표를 알려주면 어떻게 읽을까</h2>
<p>같은 제품 인식기와 줄·표 구성 함수를 사용했습니다. 정답 문자열은 채점에만 씁니다. 모든 오류 수는 공백 제외 글자 기준입니다.</p>
<p class="muted">주석은 글꼴 치수 사각형입니다. 그 자체가 완벽한 글리프 경계는 아니며 +2px 조건으로 여백 민감도를 함께 봅니다.
주석 순서 결과는 읽기 순서까지 알려준 조건이므로 제품 줄·표 결과와 구분합니다. 표 구조 점수는 상세 JSON에 있습니다.</p>
<div class="table-wrap"><table><thead><tr><th>직접 인식 영역</th><th>제품 줄·표 구성 후</th><th>구성 후 오류</th><th>주석 순서 오류</th><th>추가 인식 시간</th></tr></thead><tbody>{''.join(summaries)}</tbody></table></div>
<p class="muted">낮은 피복 주석 {geometry['low_coverage_regions']}개 · 여러 검출과 겹친 주석 {geometry['multi_detection_regions']}개 · 여러 주석과 겹친 검출 {geometry['multi_region_detections']}개 · 대응 없는 검출 {geometry['unmatched_detections']}개 · 크게 겹친 검출 쌍 {len(geometry['large_overlap_pairs'])}개 · 작은 검출 {geometry['small_detections']}개. 확정 누락/중복 판정이 아닙니다.</p>
<details><summary>영역별 원문·직접 인식·기하 관측</summary><div class="table-wrap"><table><thead><tr><th>영역</th><th>정답</th><th>그대로 인식</th><th>+2px 인식</th><th>피복률</th><th>상자/주석 높이</th><th>겹친 검출</th></tr></thead><tbody>{''.join(regions)}</tbody></table></div></details></section>'''


def analysis_panel(analysis):
    if not analysis:
        return ""
    groups = [("전체", analysis["overall"])] + [(f"{field}: {key}", group)
        for field, slices in analysis["slices"].items() for key, group in slices.items()]
    rows = []
    for label, group in groups:
        for variant in group["variants"]:
            changes = variant["case_changes"]
            rows.append(f'''<tr><td>{esc(label)}<small>{group['cases']}개 · {LABELS[variant['name']]}</small></td><td>{percent(group['baseline_cer'])}</td>
<td>{percent(variant['layout_cer'])}</td><td>{percent(variant['ordered_cer'])}</td><td>{changes['recovered']} / {changes['newly_wrong']}</td><td>{changes['both_wrong']}</td></tr>''')
    geometry = analysis["overall"]["geometry"]
    statuses = " · ".join(f"{STATUS.get(key, key)} {count}개" for key, count in analysis["statuses"].items())
    return f'''<section class="panel"><div class="eyebrow">ANNOTATED REGIONS · SAME RECOGNIZER</div><h2>영역을 알려준 직접 인식</h2>
<p>비교 {analysis['eligible']}/{analysis['total']}개 · 제외 {analysis['excluded']}개. {esc(statuses)}</p>
<p>원본과 같은 인식기에 주석 좌표만 제공합니다. 결과 텍스트나 제품 경고를 고치지 않습니다.
아래는 공백 제외 CER입니다. 주석 순서 결과에는 읽기 순서를 알려주는 효과도 들어 있으므로 제품 줄·표 구성 후 결과와 함께 봐야 합니다.</p>
<p class="muted">주석 영역은 완벽한 픽셀 경계가 아닙니다. 회복/신규 오류/양쪽 오류는 기존 제품과 주석 순서 문자열의 완전 일치로 비교하며, 확정적인 원인 분류는 아닙니다.
표 구조와 영역별 오류는 상세 JSON에 별도 기록합니다. 추가 진단 시간은 제품 처리 시간과 분리합니다.</p>
<p>주석 {geometry['regions']}개 / 검출 {geometry['detections']}개 · 낮은 피복 {geometry['low_coverage_regions']}개 · 여러 검출과 겹친 주석 {geometry['multi_detection_regions']}개 · 대응 없는 검출 {geometry['unmatched_detections']}개 · 크게 겹친 검출 쌍 {geometry['large_overlap_pairs']}개.</p>
<details open><summary>전체·화면 조건·내용별 비교</summary><div class="table-wrap"><table><thead><tr><th>범위 / 주석 조건</th><th>제품 CER</th><th>직접 인식+제품 구성 CER</th><th>직접 인식+주석 순서 CER</th><th>회복 / 신규 오류</th><th>양쪽 오류</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details></section>'''
