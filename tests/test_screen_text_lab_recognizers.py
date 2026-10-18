"""모델 없이 입력 계약·원본 보존·해시 검증·선택 경계를 검사한다."""
import copy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from tools.screen_text_lab.recognizers import (prepare_crop,input_tensor,read_regions,probabilities,
    validate_session,validate_options,load_charset,model_files,RECOGNIZERS,INPUT_PROFILES)


def entry(kind='paddle'):
    return {'format':kind,'height':48 if kind=='paddle' else 64,'channels':3 if kind=='paddle' else 1,
            'dictionary_size':2,'append_space':False}


def test_input_profiles_preserve_original_and_separate_brightness_geometry():
    crop=np.full((20,50,3),15,np.uint8);crop[6:14,8:42]=220
    saved=crop.copy()
    assert prepare_crop(crop,'native') is crop
    light=prepare_crop(crop,'light')
    assert light.shape==crop.shape and light[0,0,0]==240 and light[7,9,0]==35
    ink=prepare_crop(crop,'ink')
    assert ink.shape==(12,38,3) and ink[0,0,0]==15
    assert np.array_equal(prepare_crop(crop,'ink-light'),255-ink)
    assert prepare_crop(crop,'pad-2').shape==(24,54,3)
    assert np.array_equal(crop,saved)
    blank=np.full((20,50,3),240,np.uint8)
    assert prepare_crop(blank,'ink') is blank
    complex_crop=np.random.default_rng(42).integers(0,256,(20,50,3),dtype=np.uint8)
    assert prepare_crop(complex_crop,'ink-light') is complex_crop


def test_model_specific_channels_resize_and_probability_contract():
    color=np.empty((10,20,3),np.uint8);color[:]=[255,0,0]
    tensor=input_tensor(color,entry())
    assert tensor.shape==(3,48,96) and tensor.dtype==np.float32
    assert np.all(tensor[0]==-1) and np.all(tensor[2]==1)
    gray=input_tensor(color,entry('easyocr'))
    assert gray.shape==(1,64,128)
    assert np.allclose(gray,76/127.5-1)
    logits=np.array([[[10000.,9999.,-10000.]]],np.float32)
    result=probabilities(logits,entry('easyocr'),3)
    assert np.isfinite(result).all() and result.sum()==pytest.approx(1)
    with pytest.raises(ValueError,match='분포'):
        probabilities(logits,entry(),3)
    with pytest.raises(ValueError,match='차원'):
        probabilities(np.array([[[np.nan,0.,1.]]]),entry(),3)


def test_native_paddle_reader_equals_actual_product_and_cancels():
    from screen_text import engine as module
    class Session:
        def __init__(self): self.inputs=[]
        def run(self,_,feed):
            self.inputs.append(feed['x'].copy())
            return [np.eye(3,dtype=np.float32)[[[1,1,0,1,2,2,0,2],[2,0,2,0,0,0,0,0]]]]
    engine=object.__new__(module.OcrEngine);engine._charset=['#','s'];engine._rec=Session()
    image=np.random.default_rng(20).integers(0,256,(10,40,3),dtype=np.uint8)
    boxes=[[20,0,40,10],[0,0,10,10]]
    before=engine._read(image,boxes,lambda:False)
    evidence=[]
    after=read_regions(module,engine,image,boxes,lambda:False,entry(),'native',evidence)
    assert before==after and np.array_equal(*engine._rec.inputs)
    assert evidence[1]['used_steps']==4 and evidence[0]['used_steps']==8
    assert evidence[1]['crop_sha256']==hashlib.sha256(image[:,:10].tobytes()).hexdigest()
    with pytest.raises(module.RecognitionCancelled):
        read_regions(module,engine,image,boxes,lambda:True,entry(),'native',evidence)


def test_easyocr_uses_edge_padding_full_steps_and_common_ctc():
    from screen_text import engine as module
    class Session:
        def run(self,_,feed):
            assert set(feed)=={'input'}
            batch=feed['input']
            assert batch.shape==(2,1,64,128)
            assert np.array_equal(batch[0,:,:,64:],np.repeat(batch[0,:,:,63:64],64,axis=2))
            logits=np.full((2,8,3),-10.,np.float32)
            logits[:,:,0]=10.;logits[:,7,0]=-10.;logits[:,7,2]=10.
            return [logits]
    engine=SimpleNamespace(_rec=Session(),_charset=['#','s'])
    evidence=[]
    got=read_regions(module,engine,np.zeros((10,40,3),np.uint8),[[0,0,10,10],[20,0,40,10]],lambda:False,entry('easyocr'),'native',evidence)
    assert [text for text,_ in got]==['s','s']
    assert all(row['used_steps']==8 for row in evidence)


def test_metadata_shape_charset_and_explicit_duplicate_space(tmp_path):
    e=entry()
    path=tmp_path/'dict.txt';path.write_text('a\nb\n',encoding='utf-8')
    assert load_charset(path,e)==['a','b']
    path.write_text('a\n \n',encoding='utf-8')
    with pytest.raises(ValueError,match='중복'):load_charset(path,e|{'append_space':True})
    assert load_charset(path,e|{'append_space':True,'duplicate_characters':[' ']})==['a',' ',' ']
    session=SimpleNamespace(get_inputs=lambda:[SimpleNamespace(name='x',shape=['N',3,48,'W'],type='tensor(float)')],
                            get_outputs=lambda:[SimpleNamespace(shape=['N','T',3])])
    validate_session(session,e,['a','b'])
    with pytest.raises(ValueError,match='클래스'):validate_session(session,e,['a'])
    with pytest.raises(ValueError,match='입력'):validate_session(session,entry('easyocr'),['a','b'])


def test_missing_or_tampered_registered_assets_refused(tmp_path,monkeypatch):
    from tools import verify
    from tools.screen_text_lab import recognizers
    monkeypatch.setattr(verify,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='누락/불일치'):model_files('easyocr-korean-g2')
    model_dir=tmp_path/'output/screen_text_lab/models/easyocr-korean-g2';model_dir.mkdir(parents=True)
    (model_dir/'rec.onnx').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='누락/불일치'):model_files('easyocr-korean-g2')
    with pytest.raises(ValueError,match='지원하지'):model_files('../outside')


def test_manual_options_reject_mixed_experiments_before_model_load():
    from tools.screen_text_lab.__main__ import parser
    from tools.screen_text_lab.runner import run
    args=parser().parse_args(['run','--corpus','unused'])
    assert args.recognizer is None and args.input_profile=='native'
    for args in [('product','native','upscale-2',False,False),('product','native','baseline',False,True),
                 (None,'pad-2','baseline',True,False)]:
        with pytest.raises(ValueError,match='별도'):validate_options(*args)
    with pytest.raises(ValueError,match='별도'):
        run('unused',recognizer='easyocr-korean-g2',diagnose_ctc=True)
    for model in RECOGNIZERS:
        for profile in INPUT_PROFILES: validate_options(model,profile)


def test_adapter_records_inputs_and_worker_metadata_without_ground_truth(tmp_path,monkeypatch):
    from PIL import Image
    from screen_text import engine as module
    from tools.screen_text_lab import recognizers
    from tools.screen_text_lab.engine_adapter import ProductEngine
    class Session:
        def run(self,_,feed): return [np.array([[[.01,.98,.01]]],dtype=np.float32)]
    engine=object.__new__(module.OcrEngine);engine._charset=['a','b'];engine._rec=Session()
    engine._detect=lambda image, cancelled=lambda: False:[[0,0,20,10]]
    info={'id':'product','input_height':48,'input_channels':3,'model_bytes':1,'charset_size':2}
    monkeypatch.setattr(recognizers,'create_engine',lambda name,threads:(engine,entry(),info))
    adapter=ProductEngine(recognizer='product',input_profile='pad-2')
    path=tmp_path/'case.png';Image.new('RGB',(20,10),'white').save(path)
    got=adapter.recognize(path)
    assert got['text']=='a'
    assert got['trace']['detection_boxes']==[[0,0,20,10]]
    assert got['recognizer']['regions'][0]['prepared_shape']==[14,24,3]
    with pytest.raises(ValueError,match='별도'):adapter.recognize(path,ctc_case={})
    from tools.screen_text_lab.recognizer_report import case_panel,model_panel
    got['recognizer']['id']='<script>unsafe</script>'
    assert '<script>' not in case_panel({'prediction':got}) and '&lt;script&gt;' in case_panel({'prediction':got})
    assert '인식 모델 파일' in model_panel({'engine':{'recognizer':info}})


def test_comparison_rejects_different_detection_crop(tmp_path):
    from test_screen_text_lab import make_case,record_for
    from tools.screen_text_lab.compare import pair_records
    left=record_for(make_case(tmp_path),'정답')
    left['prediction']['recognizer']={'regions':[{'box':[0,0,20,10],'crop_sha256':'a'}]}
    right=copy.deepcopy(left)
    pair_records([left],[right])
    right['prediction']['recognizer']['regions'][0]['crop_sha256']='b'
    with pytest.raises(ValueError,match='crop'):pair_records([left],[right])
