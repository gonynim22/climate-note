"""고정된 로컬 인식 모델과 픽셀 전처리 비교. 다운로드/임의 코드 로드는 제공하지 않는다."""
from pathlib import Path
from time import perf_counter

from .corpus import digest, read_json

RECOGNIZERS = ('product', 'paddle-korean-v3', 'easyocr-korean-g2')
INPUT_PROFILES = ('native', 'single', 'pad-2', 'pad-4', 'light', 'ink', 'ink-light')


def validate_options(recognizer, profile, candidate='baseline', diagnose_regions=False, diagnose_ctc=False):
    if recognizer not in (None,*RECOGNIZERS) or profile not in INPUT_PROFILES:
        raise ValueError('지원하지 않는 인식 모델/입력 조건입니다')
    if (recognizer is not None or profile != 'native') and (candidate != 'baseline' or diagnose_regions or diagnose_ctc):
        raise ValueError('모델/입력 비교는 baseline에서 다른 진단 옵션과 별도로 실행합니다')


def model_files(name):
    """registry에 고정된 크기/해시를 매 실행 전후 검증한다. manifest 자체를 신뢰 입력으로 바꾸지 않는다."""
    from tools.verify import ROOT
    if name == 'product':
        from screen_text.engine import verify_models
        paths = verify_models()
        return {'id':name,'format':'paddle','height':48,'channels':3,'append_space':True,
                'dictionary_size':11945,'license':'Apache-2.0'}, paths['rec'], paths['dict'], {
                    role:{'size':path.stat().st_size,'sha256':digest(path)} for role,path in paths.items()}
    if name not in RECOGNIZERS:
        raise ValueError('지원하지 않는 인식 모델입니다')
    entry = read_json(Path(__file__).parent/'recipes/recognizers.json')['models'][name]
    directory = ROOT/'output/screen_text_lab/models'/name
    paths, snapshot = {}, {}
    for item in entry['files']:
        path = directory/item['name']
        if not path.is_file() or path.stat().st_size != item['size'] or digest(path) != item['sha256']:
            raise ValueError(f"개발용 모델 파일 누락/불일치: {name}/{item['name']}")
        paths[item['role']] = path
        snapshot[item['role']] = {'size':item['size'],'sha256':item['sha256']}
    return entry, paths['model'], paths['dict'], snapshot


def model_snapshot(name):
    # 기본 실행의 기존 import/가짜 프로세스 경계를 유지한다. 기본 모델은 source_inputs가 해시를 기록한다.
    return None if name == 'product' else model_files(name)[3]


def load_charset(path, entry):
    from collections import Counter
    with open(path, encoding='utf-8', newline='') as stream:
        chars = [line.rstrip('\r\n') for line in stream]
    if len(chars) != entry['dictionary_size'] or any(len(char) != 1 for char in chars):
        raise ValueError('인식 사전 형식/크기가 맞지 않습니다')
    if entry['append_space']:
        chars.append(' ')
    duplicates = {char for char,count in Counter(chars).items() if count>1}
    if duplicates != set(entry.get('duplicate_characters',[])):
        raise ValueError('인식 사전에 중복 문자가 있습니다')
    return chars


def validate_session(session, entry, charset):
    inputs, outputs = session.get_inputs(), session.get_outputs()
    expected_name = 'x' if entry['format']=='paddle' else 'input'
    if (len(inputs)!=1 or inputs[0].name!=expected_name or inputs[0].type!='tensor(float)' or
        len(inputs[0].shape)!=4 or inputs[0].shape[1:3]!=[entry['channels'],entry['height']]):
        raise ValueError('인식 모델 입력 계약이 맞지 않습니다')
    if len(outputs)!=1 or len(outputs[0].shape)!=3 or outputs[0].shape[-1]!=len(charset)+1:
        raise ValueError('인식 모델과 사전 클래스 수가 맞지 않습니다')


def create_engine(name, threads):
    """기존 검출 모델 + 선택한 인식 모델만 로드한다. 제품 소스/상수 변경 없음."""
    import os
    import onnxruntime as ort
    from screen_text.engine import OcrEngine, verify_models
    entry, rec, dictionary, snapshot = model_files(name)
    started = perf_counter()
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads or min(4,os.cpu_count() or 1)
    options.inter_op_num_threads = 1
    engine = object.__new__(OcrEngine)
    engine._det = ort.InferenceSession(str(verify_models()['det']),options,providers=['CPUExecutionProvider'])
    engine._rec = ort.InferenceSession(str(rec),options,providers=['CPUExecutionProvider'])
    engine._charset = load_charset(dictionary,entry)
    validate_session(engine._rec,entry,engine._charset)
    return engine, entry, {'id':name,'format':entry['format'],'input_height':entry['height'],
            'input_channels':entry['channels'],'charset_size':len(engine._charset),
            'model_bytes':rec.stat().st_size,'files':snapshot,
            'session_load_ms':(perf_counter()-started)*1000}


def prepare_crop(crop, profile):
    import numpy as np
    if profile in ('native','single'):
        return crop
    if profile in ('pad-2','pad-4'):
        pad = int(profile[-1])
        return np.pad(crop,((pad,pad),(pad,pad),(0,0)),mode='edge')
    pixels = crop.astype(np.float32)
    border = np.concatenate((pixels[0],pixels[-1],pixels[:,0],pixels[:,-1]))
    background = np.median(border,axis=0)
    if np.mean(np.max(np.abs(border-background),axis=1)<=16)<.85:
        return crop
    if profile in ('ink','ink-light'):
        distance=np.max(np.abs(pixels-background),axis=2)
        contrast=float(distance.max())
        if contrast<24:
            return crop
        ys,xs=np.nonzero(distance>max(12.,contrast*.18))
        if len(xs)<4:
            return crop
        x0,x1,y0,y1=xs.min(),xs.max()+1,ys.min(),ys.max()+1
        pad=max(1,round((y1-y0)*.2))
        if y1-y0<4 or (x1-x0+pad*2)/(y1-y0+pad*2)>2*crop.shape[1]/crop.shape[0]:
            return crop
        pixels=np.empty((y1-y0+pad*2,x1-x0+pad*2,3),dtype=np.float32)
        pixels[:]=background
        pixels[pad:-pad,pad:-pad]=crop[y0:y1,x0:x1]
    if profile in ('light','ink-light') and float(background.mean())<127.5:
        pixels=255.-pixels
    return pixels


def input_tensor(crop, entry):
    import numpy as np
    height=entry['height']
    width=max(8,int(np.ceil(height*crop.shape[1]/crop.shape[0])))
    if entry['format']=='paddle':
        from screen_text.engine import resize_bilinear
        pixels=resize_bilinear(crop,width,height)[:,:,::-1]
        return ((pixels/255.-.5)/.5).transpose(2,0,1).astype(np.float32)
    # EasyOCR 고유 계약: 64px 회색조·Pillow bicubic. 전체 EasyOCR 파이프라인 재현은 아님.
    from PIL import Image
    pixels=np.asarray(Image.fromarray(np.clip(crop,0,255).astype(np.uint8)).convert('L').resize((width,height),Image.Resampling.BICUBIC))
    return ((pixels.astype(np.float32)/255.-.5)/.5)[None]


def probabilities(output, entry, classes):
    import numpy as np
    if output.ndim!=3 or output.shape[2]!=classes or not np.isfinite(output).all():
        raise ValueError('인식 출력 차원/값이 맞지 않습니다')
    if entry['format']=='easyocr':
        exp=np.exp(output-output.max(axis=2,keepdims=True))
        return exp/exp.sum(axis=2,keepdims=True)
    if output.min()<0 or output.max()>1 or not np.allclose(output.sum(axis=2),1.,atol=2e-4):
        raise ValueError('인식 모델 출력이 확률 분포가 아닙니다')
    return output


def read_regions(module, engine, image, boxes, cancelled, entry, profile, evidence=None, observer=None):
    import hashlib
    import numpy as np
    tensors=[]
    if evidence is not None:
        evidence.clear()
    for index,(x0,y0,x1,y1) in enumerate(boxes):
        original=image[y0:y1,x0:x1]
        crop=prepare_crop(original,profile)
        tensor=input_tensor(crop,entry)
        tensors.append(tensor)
        if evidence is not None:
            evidence.append({'detection_index':index,'box':[x0,y0,x1,y1],
                'crop_shape':list(original.shape),'prepared_shape':list(crop.shape),'tensor_shape':list(tensor.shape),
                'crop_sha256':hashlib.sha256(original.tobytes()).hexdigest(),
                'tensor_sha256':hashlib.sha256(tensor.tobytes()).hexdigest()})
    results=[('',0.)]*len(boxes)
    order=sorted(range(len(boxes)),key=lambda i:tensors[i].shape[2])
    batch_size=1 if profile=='single' else module.REC_BATCH
    for start in range(0,len(order),batch_size):
        if cancelled():
            raise module.RecognitionCancelled
        ids=order[start:start+batch_size]
        widest=max(tensors[i].shape[2] for i in ids)
        batch=np.zeros((len(ids),entry['channels'],entry['height'],widest),dtype=np.float32)
        for slot,i in enumerate(ids):
            width=tensors[i].shape[2]
            batch[slot,:,:,:width]=tensors[i]
            if entry['format']=='easyocr':
                batch[slot,:,:,width:]=tensors[i][:,:,-1:]
        name='x' if entry['format']=='paddle' else 'input'
        probs=probabilities(engine._rec.run(None,{name:batch})[0],entry,len(engine._charset)+1)
        if len(probs)!=len(ids):
            raise ValueError('인식 모델 배치 출력 수가 맞지 않습니다')
        for slot,i in enumerate(ids):
            steps=max(1,int(np.ceil(probs.shape[1]*tensors[i].shape[2]/widest))) if entry['format']=='paddle' else probs.shape[1]
            if evidence is not None:
                evidence[i].update(batch_width=widest,used_steps=steps,full_steps=probs.shape[1])
            results[i]=module.ctc_decode(probs[slot,:steps],engine._charset)
            if observer is not None:
                observer(i, probs[slot,:steps], engine._charset, results[i])
    return results


def process_memory():
    """소유 worker 프로세스의 현재/최대 working set. 모델 단독 메모리로 해석하지 않는다."""
    import ctypes
    import os
    if os.name!='nt':
        return {'scope':'worker_process','status':'unsupported'}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
            'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    value=Counters();value.cb=ctypes.sizeof(value)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(value),value.cb):
        return {'scope':'worker_process','status':'error','winerror':ctypes.get_last_error()}
    return {'scope':'worker_process','status':'ok','working_set_bytes':value.WorkingSetSize,
            'peak_working_set_bytes':value.PeakWorkingSetSize}
