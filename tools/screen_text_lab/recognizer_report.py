"""입력 조건/모델 계약을 결과와 함께 표시한다."""
from .report import esc


def case_panel(record):
    info=record.get('prediction',{}).get('recognizer')
    if not info:
        return ''
    rows=[]
    for row in info['regions']:
        rows.append(f"<tr><td>{row['detection_index']+1}</td><td>{esc(row['crop_shape'])}</td><td>{esc(row['prepared_shape'])}</td><td>{esc(row['tensor_shape'])}</td><td>{row['batch_width']}</td><td><code>{esc(row['crop_sha256'])}</code><br><code>{esc(row['tensor_sha256'])}</code></td></tr>")
    return f'''<section class="panel"><h2>인식 모델과 입력 조건</h2><p>{esc(info['id'])} · {esc(info['input_profile'])} · 높이 {info['input_height']}px / {info['input_channels']}채널</p>
<p class="muted">원본 검출 영역은 고정합니다. 전처리와 모델별 높이·채널·보간 규칙은 다를 수 있습니다. 점수는 공통 CTC 평균이며 모델 간 정답 확률로 비교하지 않습니다.</p>
<details><summary>영역별 크기와 입력 해시</summary><div class="table-wrap"><table><thead><tr><th>영역</th><th>원본 HWC</th><th>전처리 HWC</th><th>정규화 CHW</th><th>배치 폭</th><th>원본 / 정규화 SHA-256</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details></section>'''


def model_panel(result):
    engines=result.get('recognizers') or {'실행':result.get('engine',{})}
    rows=[]
    for label,engine in engines.items():
        info=engine.get('recognizer')
        if not info:
            continue
        memory=engine.get('memory',{}).get('peak_working_set_bytes')
        memory='미측정' if memory is None else f'{memory/1048576:.1f} MiB'
        coverage=engine.get('charset_coverage',{})
        rows.append(f"<tr><td>{esc(label)}</td><td>{esc(info['id'])}<br>{esc(engine.get('input_profile','native'))}</td><td>{info['model_bytes']/1048576:.2f} MiB</td><td>{info['charset_size']}</td><td>{esc(coverage.get('unsupported_occurrences','미측정'))}</td><td>{memory}</td></tr>")
    if not rows:
        return ''
    return f'''<section class="panel"><h2>모델 비교 조건과 비용</h2><table><thead><tr><th>범위</th><th>모델 / 입력</th><th>인식 모델 파일</th><th>문자 클래스</th><th>정답 중 사전에 없는 글자</th><th>worker 최대 working set</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class="muted">파일 크기는 인식 모델 단독이며 EXE 크기가 아닙니다. 메모리는 검출·인식·이미지·Python을 포함한 worker 전체 값입니다. 사전 범위는 추론 후 평가용이며 정답을 인식기에 전달하지 않습니다. 모델 점수/경고는 보정하지 않았으므로 직접 비교할 수 없습니다.</p></section>'''
