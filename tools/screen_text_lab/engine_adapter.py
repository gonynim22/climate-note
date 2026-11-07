"""제품 경로를 그대로 호출한다. 실제 엔진 import는 worker 생성 때만 한다."""
from dataclasses import asdict
from contextlib import contextmanager, nullcontext
from time import perf_counter


def pack_prediction(boxes):
    from screen_text.layout import (Table, build_blocks, plain_with_spans, rows_of,
                                    to_plain, to_tsv, to_html, unsure_count)
    blocks = build_blocks(boxes)
    text, spans = plain_with_spans(blocks)
    if text != to_plain(blocks):
        raise ValueError("제품 plain_with_spans/to_plain 결과가 다릅니다")
    return {"text": text, "tsv": to_tsv(blocks), "html": to_html(blocks),
            "table": [[cell.text for cell in row] for block in blocks if isinstance(block, Table) for row in block.rows],
            "boxes": [asdict(box) for box in boxes],
            "blocks": [{"kind": "table" if isinstance(block, Table) else "line",
                        "rows": [[asdict(cell) for cell in row] for row in rows_of(block)]} for block in blocks],
            "unsure_count": unsure_count(blocks), "spans_utf16": spans}


@contextmanager
def plain_detection(module):
    """진단은 원본 좌표의 상자가 필요하다. 여백과 2배 확대를 끄고 위치 찾기를 한 번만 돌린다."""
    saved = module.DET_MARGIN, module.SMALL_TEXT_PX
    module.DET_MARGIN, module.SMALL_TEXT_PX = 0, 0
    try:
        yield
    finally:
        module.DET_MARGIN, module.SMALL_TEXT_PX = saved


class ProductEngine:
    def __init__(self, threads=None, candidate="baseline", recognizer=None, input_profile='native'):
        from .experiments import candidate_settings
        candidate_settings(candidate)
        from .recognizers import validate_options
        validate_options(recognizer,input_profile,candidate)
        self.candidate = candidate
        from screen_text.engine import OcrEngine
        started = perf_counter()
        self.model_info = None
        self.input_evidence = []
        self.input_profile = input_profile
        if recognizer is not None or input_profile != 'native':
            from .recognizers import create_engine, read_regions
            from screen_text import engine as module
            self.engine, entry, self.model_info = create_engine(recognizer or 'product',threads)
            self.engine._read = lambda image,boxes,cancelled: read_regions(
                module,self.engine,image,boxes,cancelled,entry,input_profile,self.input_evidence)
        else:
            self.engine = OcrEngine(threads=threads)
        self.load_ms = (perf_counter() - started) * 1000

    def recognize(self, path, region_case=None, ctc_case=None):
        import numpy as np
        from PIL import Image
        if region_case is not None and self.candidate != "baseline":
            raise ValueError("영역 분리 진단은 baseline에서만 지원합니다")
        if ctc_case is not None and (self.candidate != "baseline" or region_case is not None):
            raise ValueError("CTC 진단은 baseline에서 영역 진단과 별도로 실행합니다")
        started = perf_counter()
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB")).copy()
        loaded = perf_counter()
        from screen_text import engine as engine_module
        from .experiments import observe_engine
        from .ctc_probe import capture_ctc, finish_diagnosis
        comparing = getattr(self,'model_info',None) is not None
        if comparing and (region_case is not None or ctc_case is not None):
            raise ValueError('모델/입력 비교는 다른 진단 옵션과 별도로 실행합니다')
        diagnosing = comparing or region_case is not None or ctc_case is not None
        with plain_detection(engine_module) if diagnosing else nullcontext():
            with observe_engine(engine_module, self.engine, self.candidate, capture_boxes=region_case is not None or comparing) as trace:
                with capture_ctc(engine_module, self.engine, ctc_case) if ctc_case is not None else nullcontext() as evidence:
                    boxes = self.engine.recognize(rgb)
        recognized = perf_counter()
        result = pack_prediction(boxes)
        result.update(trace=trace, image_load_ms=(loaded - started) * 1000,
                      recognize_ms=(recognized - loaded) * 1000,
                      layout_ms=(perf_counter() - recognized) * 1000,
                      total_ms=(perf_counter() - started) * 1000)
        if comparing:
            result['recognizer'] = {'id':self.model_info['id'],'input_profile':self.input_profile,
                'input_height':self.model_info['input_height'],'input_channels':self.model_info['input_channels'],
                'regions':list(self.input_evidence),'score_scope':'common_ctc_mean_not_cross_model_confidence'}
        if ctc_case is not None:
            result['timing_scope'] = 'instrumented_not_product_latency'
            try:
                result['ctc_diagnostic'] = finish_diagnosis(evidence, ctc_case, pack_prediction)
            except Exception as error:
                # 후처리 진단 실패도 제품 인식 성공과 구분한다.
                result['ctc_diagnostic'] = evidence | {'status': 'error', 'error_type': type(error).__name__}
        if region_case is not None:
            from .region_diagnostics import diagnose_regions
            try:
                result["region_diagnostic"] = diagnose_regions(self.engine, rgb, region_case, trace["detection_boxes"], pack_prediction)
            except Exception as error:
                # 추가 진단 실패와 이미 얻은 제품 결과를 분리해 보존한다.
                result["region_diagnostic"] = {"version": 1, "status": "error", "error_type": type(error).__name__}
        return result
