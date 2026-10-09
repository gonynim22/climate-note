# 작업 기록: 미니앱·OCR·AI 활용 라이선스 상세 점검

작성일: 2026-10-09 / 상태: 코드·번들·공식 출처 점검 완료, 고지 수정 및 일부 권리 증빙 확인 전

후속 구현: 사용자가 버전·기능·데이터 유지 조건으로 수정을 승인하여 [v3.9a 고지 정비](2026-10-09-license-notices-update.md)를 완료했다. 아래는 수정 전 점검 기록이며 현재 구현·검증·EXE는 후속 기록을 따른다.

## 목표와 범위

- 목표: 미니앱 5개의 코드·계산 근거·공공 데이터·SVG·모델·런타임·외부 프로그램을 점검하고 한 번에 정비할 목록을 확정한다.
- 변경 대상: 이 점검 기록 및 이전 [설정 라이선스 분석](2026-10-09-license-contest-review.md)의 연결 안내. 고지문과 제품 코드는 점검 결과 확정 후 별도 구현 대상이다.
- 데이터 영향: 없음. 실사용 AppData·DB·salt·실행 중 앱을 읽거나 실행하지 않는다.
- 제외 범위: 출처가 확인되지 않은 자산의 권리 추정, 법률 적합성 인증, 공고 없는 공모전 적격 확정, 배포·커밋·push.
- 시작 시 사용자 변경: AGENTS.md·RELEASE_HISTORY.md 및 미추적 작업 기록을 보존한다.

## 완료 조건

- [x] 미니앱별 의존성·리소스·외부 출처를 확인한다.
- [x] OCR 고정 리비전의 모델·사전·라이선스와 EXE를 대조한다.
- [x] AI 모델 사용과 AI 개발 도구 활용의 조건을 구분한다. 사용한 개발 도구·계약은 미확인이다.
- [x] 확정된 누락, 조건부 확인, 미확인을 구분하여 일괄 수정 목록을 남긴다.
- [x] 점검 명령·결과·재검증 필요 범위를 기록한다.

## 결정과 진행

- 2026-10-09: 이전 설정 점검에 이어 미니앱 전용 심화 점검을 시작했다. 설계 기록은 공무원 AI 개발 공모전·행정업무 효율화 목적을 명시하지만 공모전의 정확한 공고는 아직 없다.
- 2026-10-09: AI 활용 범위/도구를 질문했다. 코드 생성 도구를 임의로 특정하지 않고 모델 출처 조사는 독립적으로 진행한다.
- 2026-10-09: Hugging Face API와 raw 원문에서 실제 사용한 고정 리비전의 Apache-2.0 표기·모델 해시를 확인했다. 한국어 사전은 PaddleOCR 공식 저장소의 사전과 바이트 단위로 일치한다.
- 2026-10-09: HWP 명세의 필수 제품 고지와 PaddlePaddle 저작권 문구 누락을 발견했다. 단순 요약 갱신보다 먼저 정비할 항목으로 분류했다.

## 판정 요약

**미니앱을 제거해야 할 라이선스 비호환을 이번 조사에서 확정하지는 않았다. 그러나 현재 상태를 고지 완료로 판단할 수는 없다.** 특히 HWP 명세 사용 고지와 OCR 원저작자 고지는 확정적으로 보완할 내용이다. 세 계산기의 핵심은 프로젝트 내 Python 구현이며 별도 계산 패키지를 새로 배포하지 않는다.

| 미니앱 | 확인한 핵심 구성 | 판정 | 정비할 사항 |
|---|---|---|---|
| 단위 환산기 | `unit_converter.py`: dataclasses·math·re와 수치 정의. Qt UI는 기존 공용 구성 | 별도 계산 엔진 라이선스 발견 없음. 참고 수치/자료 출처 정비 필요 | NIST·KRISS·CODATA·IAU·KEEI·FDA 등 정의 출처를 배포 안내와 연결. NIST SRD 69의 몰질량 6개는 일반 NIST 자료와 구분 |
| 날짜·시간 계산기 | 표준 calendar·datetime, `holidays.py`의 공휴일 데이터 | 별도 날짜 패키지 없음. 공공 데이터 이용범위 확인 | 한국천문연구원 특일 정보 출처·지원 연도 고지. 앱 전체의 음양력 자료도 같은 출처 목록에 정리 |
| 금액·숫자 표기 | `int`·`Decimal`·정규식·자체 한글 숫자 조립 | 별도 상용/외부 변환 라이브러리 발견 없음 | 기존 법령·맞춤법 근거 유지. 법규/계산 근거를 소프트웨어 라이선스와 혼동하지 않기 |
| 문서 형식 변환 | 공개 HWP 헤더 명세, XML 검증, 설치된 Hancom CLI, pywin32·defusedxml | **명세 사용 고지 누락. 외부 제품 이용조건은 별도 확인** | 한컴 지정 문구를 UI·매뉴얼·도움말·소스의 실제 존재하는 구성에 반영. 두 Python 패키지 원문·저작권 보강 |
| 화면 글자 따기 | PaddleOCR ONNX 모델 2개·사전, ONNX Runtime·NumPy, 자체 전후처리·표 구성·Qt 캡처/편집 | 모델 Apache-2.0 사용 근거 확인. **원저작자 고지 보강 필요** | PaddleOCR 원문과 저작권자, 변환본 배포자·리비전·해시·변경 여부를 고지. 런타임 원문 유지·열람 제공 |

## 확정된 발견과 수정 우선순위

### F1 — HWP 공개 명세의 필수 문구 누락 (우선 수정)

`hwp_conversion.py::validate_hwp_header()`는 공개 명세의 FileHeader와 보호 플래그를 구현하며 `docs/DOCUMENT_CONVERSION.md`도 해당 HWP 5.0 명세를 근거로 명시한다. [한컴의 파일 형식 공개·사용권 안내](https://www.store.hancom.com/support/downloadCenter/hwpOwpml)는 이를 참고한 결과물에 아래 문구를 UI·매뉴얼·도움말·소스 등 존재하는 구성마다 기재하도록 요구한다.

> 본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.

점검 당시 이 문구는 추적 대상 제품 코드·문서·고지 파일 검색에서 발견되지 않았다. 향후 이 작업 기록에 문구가 생겼다는 이유로 제품 고지까지 완료됐다고 판단하면 안 된다.

- 반영 대상: `ui_document_converter.py`의 접근 가능한 안내 또는 정보 보기, 설정의 제3자/외부 구성 안내, `hwp_conversion.py` 등 명세 사용 소스, `docs/DOCUMENT_CONVERSION.md` 및 실제 배포되는 사용자 안내 `README_detail.md`의 해당 절.
- UI에 긴 법률 문구를 반복 배치할 필요는 없으나 실제로 접근 가능한 고지여야 한다. 설정의 공통 원문 열람에서 연결하는 방안은 가능하며 명세의 각 요구 구성도 챙긴다.
- 한컴 명세의 저작권·고지 조건과 사용자의 설치된 한글/변환기 사용권은 별개의 문제다. 이 문구를 넣는 것만으로 외부 제품 계약 검토가 끝나는 것은 아니다.

### F2 — 모델 LICENSE가 PaddleOCR 원문이 아닌 공통 양식 (우선 수정)

`screen_text/models/LICENSE`는 `licenses/cryptography-LICENSE.APACHE.txt`와 바이트 단위로 동일하다. 구현 계획에도 이 파일을 복사하는 명령이 있다. Apache-2.0 약관 본문은 있으나 끝부분이 `Copyright [yyyy] [name of copyright owner]`라는 양식으로 남아 있다.

반면 직접 확보한 [PaddleOCR 원문 LICENSE](https://github.com/PaddlePaddle/PaddleOCR/blob/dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf/LICENSE)에는 `Copyright (c) 2016 PaddlePaddle Authors. All Rights Reserved.`가 들어 있다. 공백을 정규화해 비교해도 이 저작권 문구와 http/https 차이가 남는다.

- `screen_text/models/LICENSE`를 출처가 확인되는 PaddleOCR 원문으로 보강하고 원저작자 고지를 보존한다. 날짜/저작권자를 임의로 새로 만들지 않는다.
- 별도 모델 출처 문서에서 원 모델 개발자(PaddleOCR/PaddlePaddle), ONNX 변환본 공급자(monkt), 변환 도구 표기(paddle2onnx), 다운로드 고정 리비전과 파일 해시, 앱에서 가중치를 수정하지 않았다는 사실을 구분한다.
- 고정 monkt 저장소에는 별도 LICENSE·NOTICE 파일이 없다(트리 목록 및 두 URL의 404 확인). 대신 README의 front matter와 본문에 Apache-2.0, 원 모델·변환 출처가 명시돼 있다. **없는 원본 NOTICE를 발견했다고 하거나 임의의 내용을 원본 NOTICE라고 만들지 않는다.** 자체 출처 문서는 ATTRIBUTION 등의 이름으로 명확히 구별할 수 있다.
- Apache의 재배포 조건은 전문 제공, 변경 파일 표시, 관련 원저작권·귀속 고지 보존, 원본 NOTICE가 있는 경우 그 고지 보존이다. [Apache-2.0 §4](https://www.apache.org/licenses/LICENSE-2.0)

### F3 — 모델·런타임 표시는 따로 관리되어 설정에서 누락 (수정)

설정은 앞선 점검처럼 OCR을 전혀 표시하지 않는다. `THIRD_PARTY_NOTICES.txt`에는 모델·ONNX Runtime·NumPy가 있지만 이를 읽는 UI가 없다. 모델 LICENSE 존재만 검사하는 테스트도 원저작자 고지 누락을 찾지 못한다.

- 설정 목록에 모델 2종, 한국어 사전, ONNX Runtime 1.30.0, NumPy 2.2.6과 각 원문을 연결한다.
- 선택형 앱이 제거되는 빌드에서는 OCR 목록도 빠지도록 한다. 사용자 DB·설정 키를 추가할 필요가 없다.
- 필수 파일뿐 아니라 원저작자, 모델 리비전, 실제 번들 유무, 고지문을 열 수 있는지까지 검증한다.

### F4 — HWP 관련 패키지와 공용 간접 의존성 고지 누락 (수정)

`pywin32==311`은 COM structured storage와 Windows Job을 위해 실제 포함되고, `defusedxml==0.7.1`도 HWPX 검증에 포함된다. 두 패키지의 설치 메타데이터는 PSF 계열이고 defusedxml 원문은 PSF version 2다. 현재 대표 고지에는 두 항목이 없다. 패키지별 실제 원문·저작권자와 변경 여부를 확보해 추가해야 한다. 이와 함께 앞선 점검에서 찾은 darkdetect·colorthief·cffi backend·typing_extensions·Python·Qt 네이티브 구성 고지를 일괄 정리한다.

## OCR 공급 경로: 무엇을 어디까지 확인했는가

| 단계 | 확보한 증거 | 결과 |
|---|---|---|
| ONNX 변환본 공급자 | `monkt/paddleocr-onnx` 리비전 `7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65`의 API 메타데이터·README | Apache-2.0 표기, PaddleOCR 원 모델 및 paddle2onnx 변환 출처 확인 |
| 위치 모델 원 공급자 | `PaddlePaddle/PP-OCRv3_mobile_det`, 리비전 `58f4e5b132e34e516486fb0d0266c662feb48ca1` | 공식 모델 카드 Apache-2.0 확인 |
| 한국어 인식 원 공급자 | `PaddlePaddle/korean_PP-OCRv5_mobile_rec`, 리비전 `c02ecaf1f22bfd1c618cce154fd19185b47e663a` | 공식 모델 카드 Apache-2.0 확인 |
| 사전 원본 | PaddleOCR 리비전 `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf`의 `ppocr/utils/dict/ppocrv5_korean_dict.txt` | 내려받은 파일·로컬 dict·EXE dict 모두 일치 |
| 실제 배포물 | v3.9a EXE SHA-256 `ED4BBD6B15E6224028629A14F33C69DCB0CBAF936E2DB402EE2ED102E4790FDF` | 아래 3개 파일이 로컬 및 공급자 고정 리비전과 일치 |

| 파일 | 바이트 | SHA-256 |
|---|---:|---|
| det.onnx | 2,429,873 | `ee40e80071ba3a320d4efda75f3e22047a7d049e9bf7bcaaf9daea23fc21b935` |
| rec.onnx | 13,401,252 | `322f140154c820fcb83c3d24cfe42c9ec70dd1a1834163306a7338136e4f1eaa` |
| dict.txt | 47,451 | `a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7` |

가중치 두 개는 Hugging Face의 LFS SHA-256/size, 사전은 원격 파일 및 Git blob ID까지 대조했다. 앱은 받은 ONNX를 그대로 싣고 자체 학습·미세조정·추가 변환을 하지 않은 배포물이다. **원래 Paddle 가중치에서 ONNX로 변환하는 과정을 이번에 독립 재현한 것은 아니다.** 정확한 원 학습 체크포인트 해시·학습 자료 권리는 위 모델 카드만으로 전수 검증되지 않는다. 공개 모델의 명시된 사용 허락과 공급 경로를 확인한 결과로 한정한다.

공식 모델 출처: [위치 모델](https://huggingface.co/PaddlePaddle/PP-OCRv3_mobile_det), [한국어 모델](https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec), [사용한 변환본 고정 리비전](https://huggingface.co/monkt/paddleocr-onnx/tree/7b02d0a30a07ba2b92ad1ff5a8941ae2c633de65). Apache-2.0 구성요소를 GPLv3 프로젝트에 포함하는 방향은 [Apache 공식 호환성 안내](https://www.apache.org/licenses/GPL-compatibility.html)와 맞는다. 모델 때문에 기후노트 전체를 Apache로 바꿀 필요는 없으며 기존 GPL/제3자 조건은 유지한다.

## ONNX Runtime·NumPy와 포함되지 않은 도구

- `screen_text/licenses/onnxruntime-LICENSE.txt`, `onnxruntime-ThirdPartyNotices.txt`, `numpy-LICENSE.txt`는 설치한 배포판의 파일과 바이트 단위로 동일하며 최종 EXE에도 그대로 들어 있다. 이 부분의 원문 보존은 확인했다.
- ONNX Runtime은 MIT이지만 네이티브 라이브러리 안의 여러 구성요소 고지를 함께 제공한다. 원문 첫머리의 번역/현지화 금지 안내를 존중해 원문은 유지하고 한국어 요약을 별도로 둔다.
- NumPy에는 OpenBLAS·LAPACK 및 GCC runtime exception 등의 고지가 있다. 단순히 BSD-3-Clause 한 줄로 바꾸면서 하위 고지를 삭제하지 않는다.
- ORT 통합 고지에는 TensorFlow·PyTorch·Transformers·DeepSeek 등의 이름도 나온다. **그 목록만 보고 해당 AI 모델/서비스가 기후노트에서 실행된다고 설명하면 잘못이다.** 제품·플랫폼 전체를 포괄하는 제3자 고지와 실제 사용 구성을 구분한다.
- 현재 Python 번들에는 paddle·paddleocr·paddlex·cv2·torch·transformers·PIL·scipy·google.protobuf·flatbuffers 패키지가 없다. 그러나 Python 패키지 미포함이 C++ 라이브러리 내부의 protobuf·flatbuffers 등 정적 코드까지 없다는 증거는 아니다. 원문 고지는 그대로 보존한다.
- Paddle2ONNX는 변환본 공급자가 사용한 도구로 기록된다. 기후노트가 이 도구나 전체 PaddleOCR 실행 프레임워크를 배포하는 것은 아니다.
- 전처리·연결요소·CTC 해독은 `screen_text/engine.py`, 표 재구성/TSV·HTML은 `layout.py`에 구현돼 있다. 별도 외부 구현을 import하지 않는 점은 확인했지만 전 세계 코드와의 유사성·차용 여부를 입증한 것은 아니다. 개발용 AI가 제공한 코드의 출처 문제는 생성 기록/제공 도구 확인이 필요하다.

## 세 계산 미니앱의 근거 자료

### 단위 환산기

외부 환산 라이브러리를 포장한 형태가 아니다. 25분류·182항목과 계산식은 프로젝트의 `Unit` 정의 및 Python 코드로 구현돼 있고, `Unit.source`와 `docs/UNIT_CONVERSION.md`에 NIST·KRISS·CODATA·IAU·KEEI·FDA 등 근거가 있다. 기관 자료의 그림·책 전체·웹 코드를 번들한 정황은 이번 조사에서 발견하지 않았다.

일반 단위 정의와 자료집의 창작적 표현·데이터베이스 전체 이용을 구분해야 한다. 특히 `GASES`의 몰질량 6개는 NIST Chemistry WebBook SRD 69에서 확인했다. NIST는 SRD와 일반 정부 자료의 권리 체계를 다르게 안내한다. **NIST 자료라서 전부 무제한 재배포 가능하다고 쓰면 부정확하다.** 현재의 소수 사실값 이용을 SRD 전체의 무단 복제로 단정할 근거도 없다. 수치를 바꾸거나 임의 환산하지 않고 출처·접근일·사용 범위(6개 값)를 기록하며, 자료집/표를 크게 복제·확장할 때는 별도 조건을 재검토한다. [NIST 권리 정책](https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications), [몰질량 산정 설명](https://webbook.nist.gov/chemistry/faq/)

### 날짜·시간 계산기

별도 `python-holidays`, dateutil 등의 패키지를 사용하지 않는다. 프로젝트의 `holidays.py`를 읽는다. 공공데이터포털의 [한국천문연구원 특일 정보](https://www.data.go.kr/data/15012690/openapi.do)와 앱 전체의 [음양력 정보](https://www.data.go.kr/data/15012679/openapi.do)는 이번 조회에서 무료·이용허락범위 제한 없음으로 표시됐다. 출처표에 제공기관·서비스 URL·지원 범위를 기록하는 방향이 적절하며 임의로 공공누리 특정 유형을 붙이지 않는다. API 트래픽/계정 조건은 데이터 사용 고지와 별도이며 앱 런타임은 API를 호출하지 않는다.

### 금액·숫자 표기

`int`·`Decimal`과 자체 함수로 숫자를 한글로 조립한다. 제3자 숫자읽기 라이브러리·유료 금융 API는 없다. 화면에는 시행규칙 제2조의 근거도 이미 있다. 법령/한글 맞춤법을 계산 근거로 삼는 것과 제3자 프로그램 복제는 구분해야 하며 별도 프로그램 라이선스가 새로 필요한 정황은 발견하지 않았다. 국립국어원 답변·법령 설명문 전체를 복제하는 변경은 이번 범위가 아니다.

## HWP 외부 실행 프로그램의 조건

- 기후노트는 설치 경로를 확인하고 공식 명령줄로 별도 프로세스를 실행한다. [한컴 공식 CLI 도움말](https://help.hancom.com/hoffice120/ko-KR/HwpxConverter/convert/convert.htm)에서 이 사용 방법을 확인했다.
- `pythoncom` 사용은 HWP 파일의 structured storage 읽기이며 HwpObject COM API로 문서 편집을 제어하는 코드가 아니다. 레지스트리의 HwpObject 등록은 설치 확인에 사용한다. 다른 한컴 SDK·웹기안기·뷰어 계약을 현재 CLI에 그대로 대입하지 않는다.
- EXE에서 한글/HwpxConverter 엔진 EXE·DLL 항목은 발견하지 않았다. 별도 설치 프로그램의 한컴·Microsoft 등 라이선스를 모두 기후노트 번들 구성이라고 표시해서는 안 된다.
- 로컬 변환기 설치 폴더에는 제3자 notice 파일이 있지만 그것만으로 한컴 제품 자체의 기관·제3자 앱 호출 허락을 확정할 수 없다. CLI가 공식 기능이라는 점과 특정 조직의 계약 범위는 별개다. 현재 사용하는 한글·변환기 버전의 EULA/기관 계약은 미확인이다.
- 권장 안내: 한글과 공식 HWPX 변환기를 별도 설치한 환경에서 사용하며 해당 프로그램의 사용권은 별도로 적용된다고 명시한다. 설치본·DLL·설치 프로그램을 출품 패키지에 임의 추가하지 않는다.

## 아이콘·사용법 애니메이션·개발용 AI

### 현재 배포되는 자산

- 미니앱 아이콘 5개와 launcher/upcoming 2개는 자체 SVG 파일이다. 코드 검사에서 `<image>`, data 이미지, 외부 href는 없었고 EXE 내부 파일과 모두 일치했다.
- 예전 단위 환산기의 생성 PNG는 v3.8c에 삭제됐다는 기록과 현재 번들 부재를 확인했다. 현재 미니앱에 과거 생성 PNG 이용조건을 적용할 대상으로 넣지 않는다.
- 화면 글자 따기의 사용법은 `screen_text/guide.py`의 QPainter 벡터 코드·합성 표본 글자다. 별도 생성 영상·사진·음원·웹폰트가 추가되지 않았다. 따라서 이 안내 때문에 새로운 이미지/영상 배포 라이선스가 자동으로 생기는 구조는 아니다.
- SVG의 단순 도형 형태나 파일에 저작권 주석이 없다는 사실만으로 독자 제작·무차용을 보증할 수는 없다. AI가 작성했는지, 기존 아이콘을 참고·복사했는지는 사용자의 제작 기록을 받아 자산 출처표에 남겨야 한다.
- 앱 전체에 남은 토마토 PNG·앱 ICO/PNG의 제작 출처는 이전 분석의 미확인 사항이다. 미니앱 벡터 확인으로 이 문제까지 완료 처리하지 않는다.

### AI 사용을 구분하는 네 가지 항목

| 항목 | 현재 확인 결과 | 일괄 정비 방향 |
|---|---|---|
| 실행 중 OCR 모델 | 공개 사전학습 모델을 로컬 ONNX Runtime CPU로 사용, 모델 변조 없이 배포 | 모델·사전·런타임 고지와 공급자 증거 보존 |
| AI로 코드/화면 설계 | 설계 기록에 앱이 AI로 개발됐다고 명시. 구체 도구·계정·이용시점 미확인 | 도구명·당시 약관·출력물 이용조건·관련 출처 표시·인간 수정/검증 기록을 확인 |
| AI 생성 이미지/아이콘 | 현재 미니앱은 SVG/코드 벡터. 앱 전체 PNG 출처 미확인 | 자산별 생성 도구·참조 이미지·수정 이력을 정리. 무조건 '직접 제작'으로 적지 않기 |
| 사용자가 OCR한 글자/표 | 화면 원자료를 읽어 텍스트/HTML/TSV로 복사 | OCR 도구의 라이선스와 원자료의 권리를 구분. 인식만으로 원문 이용권을 새로 얻는 것은 아님 |

특정 AI 도구를 썼다는 이유만으로 GPL/Apache가 자동 부여되거나 기존 OSS 고지를 생략할 수 있는 것은 아니다. 반대로 외부 AI 서비스를 실행 중 호출하지 않는 프로그램에 개발용 AI 서비스를 런타임 의존성으로 나열할 필요도 없다. 공모전의 AI 활용 설명에는 별도로 기록한다.

AI 출력의 계약상 이용권과 법률상 독점 저작권 인정은 같은 문제가 아니다. 한국의 [정부 안내](https://m.korea.kr/news/policyNewsView.do?newsId=148927815)는 인간의 창작적 기여를 구분한다. 이번 조사에서 모든 코드·이미지의 저작권 귀속을 확정하지 않는다. 공급 도구와 제작 과정 확인 없이 'AI가 작성했으므로 저작권 문제가 전혀 없다'고 설명할 수 없다.

### 출품 설명에 사용할 수 있는 사실 기반 초안

> 공개된 PaddleOCR 사전학습 모델의 ONNX 변환본을 활용해 인터넷 연결 없이 화면의 한국어를 인식합니다. 기후노트는 영역 선택, 로컬 실행 연결, 줄·표 재구성, 결과 편집, 표 형태 복사 및 기존 앱과의 통합 기능을 구현했습니다. 모델·라이브러리별 출처와 라이선스를 제공합니다.

이 문구는 고지 기능을 실제 보강한 뒤 쓰며, 현재 화면에 완성된 고지를 제공한다고 미리 주장하지 않는다. 개발용 생성형 AI의 이름·활용 단계와 인간의 검토/수정은 확인된 정보로 추가한다. '자체 학습한 한국어 AI 모델'이나 '모든 구성요소를 독자 개발'이라고 표현할 근거는 없다. 합성 표본의 정확도 0.996도 일반 실문서 성능 보장으로 바꾸지 않는다.

## 한 번에 정비할 변경 목록과 완료 기준

| 우선순위 | 변경 묶음 | 예상 파일 | 완료 기준 |
|---|---|---|---|
| 1 | PaddleOCR 원저작자·모델 출처 | `screen_text/models/LICENSE`, 모델 출처 문서, `licenses/THIRD_PARTY_NOTICES.txt` | 원문 저작권 보존, 원모델·변환본·리비전·해시·무수정 구분; 모델 3개 바이트 불변 |
| 1 | 한컴 명세 사용 고지 | 변환기 UI/소스, `docs/DOCUMENT_CONVERSION.md`, 사용자 설명, 공통 고지 | 지정 문구가 실제 존재하는 UI·매뉴얼·도움말·소스에 제공됨 |
| 1 | 설정 라이선스 열람 | `ui_settings.py`, 필요 시 공용 고지 모듈 | 앱 GPLv3 및 모든 실제 구성요소의 원문을 오프라인으로 읽을 수 있음 |
| 1 | Python·공용 의존성·Qt 정비 | `licenses/*`, `build.spec`, 배포 기록 | 실제 EXE 기준 목록, 누락 저작권·원문 보강, Qt Virtual Keyboard 등 모듈별 조건 반영 |
| 2 | 데이터·계산·자산 출처 | 출처 문서, 사용자 설명, 공통 고지 | 공휴일/음양력, 계산 근거, SVG/PNG의 출처와 확인 범위를 구분 |
| 2 | 대응 소스·제출자료 | 제출 버전 자료, README, 구성요소 명세 | 외부 심사자가 해당 EXE의 소스·리소스·빌드 방법과 필요한 의존 소스를 받을 수 있음 |
| 조건 확인 | 생성형 AI·기관 권한·공모전·Hancom 계약 | AI 활용/출품 기록, 실제 계약·공고 | 사실 확인 후 출품 설명에 반영. 근거 없이 유료 필수·면제·권리 양도를 단정하지 않음 |

필수 검증은 고지 파일 존재뿐 아니라 원저작권 문구 보존, OCR 포함/제거 두 빌드의 목록 일치, UI 원문 접근, 파일 누락 시 처리, 잠금·숨김·종료 수명, 좁은 화면/배율에서 원문 열람을 포함한다. 제품 코드 변경 시 관련 quick, 최종 배포물 변경 시 PowerShell release 및 EXE 내부 고지/모델 해시 대조를 수행한다. DB v17·Export v2·salt·설정 키·사용자 원문을 바꾸지 않는다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 유의사항 |
|---|---|---|---|
| 미니앱 코드·계약·출처 정적 조사 | 완료 | 이 문서와 원문 링크 | 코드를 읽은 범위의 판단. 전 세계 소스 유사도 감사는 아님 |
| `.\.venv\Scripts\python.exe output/license-review/20261009-mini-apps/review.py` | 증거 일치 26/26 통과 | [summary.md](../../output/license-review/20261009-mini-apps/summary.md), [result.json](../../output/license-review/20261009-mini-apps/result.json) | 모델/사전 원격·로컬·EXE 대조, 런타임 고지 원본 및 SVG 일치. 라이선스 적합성 26건 통과라는 의미가 아님 |
| 공개 원문 확보 | 완료(정상 200 및 LICENSE/NOTICE 404 구분) | [초기 요청 기록](../../output/license-review/20261009-mini-apps/upstream-downloads.json), [후속 요청 기록](../../output/license-review/20261009-mini-apps/upstream-followup.json) | 고정 HF 리비전, 공식 PaddleOCR commit, 원문 SHA-256 보존. 별도 LICENSE/NOTICE 부재를 숨기지 않음 |
| 전체 회귀·EXE 재빌드 | 미실행 | 해당 없음 | 코드·빌드 변경 없는 라이선스 조사 |
| 이전 quick 실행 | 이전 증거로만 참조 | `20261009-134320-274c20f873` | 이전 턴 75개 통과. 이번 라이선스 누락이 해결됐다는 근거로 사용하지 않음 |

## 미해결과 인계

- 공모전 공고, AI 개발 도구 및 이미지 제작 과정 확인.
- 원학습 체크포인트의 ONNX 변환 독립 재현·학습 데이터 권리 전수 조사 미실행. 모델 사용 허락은 공급자 및 원모델 공식 표기로 확인.
- 한글/HWPX 변환기의 조직별 계약과 제품 EULA 미확인. 별도 연락·문의는 보내지 않았다.
- 다음 행동: 위 일괄 정비 목록으로 제품 고지·열람 UI·배포 자료를 구현. 이 기록만으로 수정 완료 처리하지 않는다.
- 변경한 정본 문서: 없음.
- 배포·커밋·push 여부: 수행하지 않음.
