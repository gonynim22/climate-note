# 작업 기록: 화면 글자 따기 새 모델 두 후보

작성일: 2026-10-11 / 상태: 완료 — 개선 후보 확인, 제품 교체 기준 미달로 확대 종료

## 목표와 범위

- 입력 조정 반복을 종료하고 한국어를 지원하는 다른 판독 모델의 개선 가능성을 확인한다.
- 후보는 PaddleOCR-VL 1.6 및 GLM-OCR 두 개로 고정한다. 공식 모델/llama.cpp 배포 파일을 개발 출력 폴더에만 받으며 SHA-256을 검증한다.
- 제품 코드·모델·가상환경·lock·DB·salt·설정·EXE는 변경하지 않는다. 모델 및 실행기는 `output/screen_text_lab/`, 실행/원문/채점/HTML은 `output/harness/<run-id>/`에 둔다.
- 기존 AGENTS.md·database.py·ui_main.py·UI 테스트/작업 기록과 진단 소스 변경을 보존한다. 통상 테스트/빌드에 실행을 연결하지 않는다.

## 완료 조건

- [x] 한국어·라이선스·파일 크기·Windows 로컬 실행 근거와 고정 버전/해시 기록
- [x] 동일 실제 메모장 dev 48장의 원본 이미지로 두 후보 비교. 보류 12장 미사용
- [x] 공백 포함/제외 문자 오류, 기존 정답 손상, 실패/잘림, 시간과 원문이 있는 HTML 제공
- [x] 채점 재계산·입력 해시·보고서 원문/링크 검증 및 summary/실행 ID 기록

## 고정 결정

- 48개 작은 텍스트 영역 전체를 각 모델의 공식 텍스트 인식 프롬프트로 읽는다. 제품의 줄 검출+CTC 인식과 파이프라인이 다르며, 모델만의 인과 효과나 전체 앱 개선으로 해석하지 않는다. 표/불확실성 표시 정확도는 이번에 측정하지 않는다.
- 원본 PNG를 그대로 입력한다. 프롬프트/픽셀/정답을 보고 후보를 조정하지 않는다. 모델에는 이미지와 공식 프롬프트만 전달하고 정답·태그를 전달하지 않는다. 온도 0, 고정 seed, 출력 상한 1024토큰, 단일 요청 120초. 실패/잘림을 숨기거나 성공 자료만 비교하지 않는다.
- 정확도 후보 기준: 48개 모두 성공, 공백 제외 오류 20% 이상 감소, 기존 비공백 완전 정답의 손상 0, 공백 포함 오류 비증가. 합격 시만 기존 합성 dev로 확대하며 보류 자료는 후보 확정 전 사용하지 않는다.
- 파일 크기와 GPU/CPU 시간도 별도로 판단한다. 미달이면 이번 두 후보의 탐색을 종료하며 같은 자료에 맞춘 프롬프트 튜닝은 하지 않는다.
- 라이선스와 기술 지원의 적합성은 후보 실험의 전제일 뿐 제품 배포 검증 완료를 뜻하지 않는다.

## 근거

- [PaddleOCR-VL 1.6 공식 GGUF](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF): Apache-2.0, `OCR:` 프롬프트, llama.cpp 로컬 사용. [한국어 지원](https://github.com/PaddlePaddle/PaddleOCR).
- [GLM-OCR 공식 모델](https://huggingface.co/zai-org/GLM-OCR): MIT, 메타데이터에 ko, `Text Recognition:` 프롬프트. [llama.cpp 조직 변환본](https://huggingface.co/ggml-org/GLM-OCR-GGUF).
- [llama.cpp v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0)의 nightly-tag가 지정한 b11429 Windows x64 portable. 설치/전역 PATH 변경 없음.
- [PP-OCRv6 공식 안내](https://www.paddleocr.ai/main/en/index.html): 50개 언어에 한국어가 포함되지 않아 단순 후속 교체 후보에서 제외한다.
- [진단 계약](../SCREEN_TEXT_LAB.md), [제품 계약](../SCREEN_TEXT.md), [검증](../TESTING.md), [직전 분할 종료 기록](2026-10-11-screen-text-short-regions.md).

## 검증 증거

| 범위 | 상태 | 실행 ID / 결과 | 한계 |
|---|---|---|---|
| 후보 고정·추론·비교 | 통과 | `20261011-133348-b70eeeeb66`, [summary](../../output/harness/20261011-133348-b70eeeeb66/summary.md), [result](../../output/harness/20261011-133348-b70eeeeb66/result.json), [HTML](../../output/harness/20261011-133348-b70eeeeb66/report.html) | 48 × 2건 성공, 잘림·실패 0. 단일 메모장/시험 원문/JPEG 유래/AI 검토 정답 |
| 모델·실행기 출처/해시 | 통과 | [고정 자산 계획](../../output/harness/20261011-133348-b70eeeeb66/assets-plan.json), [실제 파일](../../output/harness/20261011-133348-b70eeeeb66/assets.json), [라이선스 출처](../../output/harness/20261011-133348-b70eeeeb66/license-sources.json) | HF LFS SHA-256 / GitHub release digest 대조, 프로젝트 venv/lock 변경 없음 |
| 재채점·이미지·HTML 원문 | 통과 | [verification](../../output/harness/20261011-133348-b70eeeeb66/verification.json) | 96결과 재계산, 48 PNG 해시, 49 HTML·192표시 원문·345로컬 링크. 브라우저 시각 검사는 미실행 |
| GLM 출력 형식 보조 분석 | 통과 | [supplement](../../output/harness/20261011-133348-b70eeeeb66/supplement.json) | 사후에 HTML 표 두 개의 글자만 추출. 원문/기준 점수와 구분, 추론/프롬프트 수정 없음 |
| GLM CPU 확인 3장 | 통과 | [실제 결과](../../output/harness/20261011-133348-b70eeeeb66/glm-cpu-sanity/result.json) | 사후 백엔드 확인. GPU와 출력은 다르지만 한국어 오독/기존 정답 손상 지속. 전체 CPU 평가 아님 |
| 합성 dev 확대·보류 자료·제품 빌드 | 미실행 | | 두 후보 고정 기준 미달로 계획된 중단. 제품 코드/통상 실행기를 수정하지 않아 전체 pytest/빌드는 미실행 |

실행 명령은 프로젝트 `.venv/Scripts/python.exe -X utf8`로 실행 폴더의 `prepare.py`, `evaluate.py paddle-vl-1.6`, `evaluate.py glm-ocr-q8`, `cpu_check.py`, `supplement.py`, `report.py` 순서다. 사후 검사는 정확도 후보/공식 프롬프트를 추가하거나 변경하지 않았다. 재현 코드·원 응답·인식 전 계획·모델 원문 안내·라이선스와 실행 명령을 실행 폴더에 남겼다.

## 결과와 판단

| 조건 | 공백 제외 오류 / 3,006자 | 공백 포함 오류 / 3,742자 | 비공백 완전 정답 | 완전 복구 / 새 오답 | 중앙 / p95 |
|---|---:|---:|---:|---:|---:|
| 제품 기준 | 129 (4.2914%) | 435 | 26/48 | 기준 | 155 / 263ms |
| PaddleOCR-VL 1.6 | 70 (2.3287%) | 175 | 30/48 | 6 / 2 | 922 / 1,153ms |
| GLM Q8 원문 | 664 (22.0892%) | 760 | 5/48 | 0 / 21 | 606 / 1,512ms |

- Paddle의 공백 제외 오류는 **45.7% 감소**했다. 단, 새 오답 2장(동일 원문의 100/150% 캡처)에서 `COUNT`를 `COUNTY`로 출력해 기존 정답 보존 기준에 미달했다. [실제 원본/출력](../../output/harness/20261011-133348-b70eeeeb66/cases/notepad-cli-layout-02--zoom150.html)을 남겼고 PNG도 직접 대조했다. 역슬래시 태그 8장을 제외한 40장에서도 78 → 39개 / 2,430자로 감소한다.
- GLM은 HTML 표를 두 번 출력해 원문 664개에는 태그의 삽입도 포함한다. 사후에 표 글자만 추출하면 **306개(10.1796%)**, 새 오답 19장으로 여전히 기준보다 나쁘다. 이 보조 수치는 원문 점수/고정 채택 기준을 대체하지 않는다.
- GLM CPU 3장에서도 기준에서 맞던 한국어 문장을 오독했다. Vulkan과 CPU 출력이 다르므로 GPU 구현 영향이 전혀 없다고 단정하지 않는다. CPU 전체 결과나 GLM의 모든 실행/양자화 설정으로 일반화하지 않으며, 원문/프롬프트 조정 없이 이번 후보를 종료한다.
- Paddle 모델+시각부 **1,817,539,616 bytes**, GLM **1,434,837,056 bytes**이고 실행기 별도다. 각각 공식 고정 revision을 받았으며 개발 출력 폴더 밖에 설치하지 않았다. 제품 소형 모델보다 배포 부담이 크다.
- 시간은 GTX 1650 Vulkan로 각 한 번 측정했다. 제품 기준은 ONNX CPU라서 동일 하드웨어 경로의 속도 대조가 아니다. Paddle 모델 시작 6.84초 및 첫 요청 6.31초가 별도로 있었으며 중앙값만으로 최초 대기를 해석하지 않는다. 기존 앱/사용자 데이터에 접근하지 않고 소유 Windows Job의 로컬 서버를 종료했다.
- 후보 탐색의 결과는 **한 후보의 오류 감소 확인 / 즉시 교체 기준 미달**이다. 합성 dev·보류 자료 확대 및 제품 변경/빌드로 넘어가지 않는다. 제품에 적용된 정확도 개선량은 여전히 0이다.

## 미해결과 인계

- 실제 CLI·다양한 앱/글꼴/Windows DPI·독립 사람 정답·표·제품 캡처 흐름은 이번 48장에 포함되지 않는다.
- 제품 적용·빌드·커밋·push: 수행하지 않음.

### 세션 종료 메모: 현재 모델 추가 학습 가능성

- **후속 검토 완료**: [소형 모델 추가 학습 검토](2026-10-11-screen-text-finetuning-review.md)에 공식 가중치/사전/환경 대조, 길이·사전 밖 글자 문제, 학습 전 원본 재현과 제한된 실험안을 남겼다. 설치·학습·제품 적용은 미실행이다.

- **개선 방법이 소진된 것은 아니다.** 지금까지는 입력 조정·재인식·다른 모델 비교를 했으며, 현재 `korean_PP-OCRv5_mobile_rec`의 추가 학습은 아직 하지 않았다. 앞선 중단 판단을 학습 불가능으로 해석하지 않는다.
- [공식 한국어 사전학습 모델](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html)이 공개되어 있다. 후속 투자 후보의 우선순위는 **현재 소형 모델의 Windows 화면 글자 특화 미세학습**이다. 같은 구조·문자 목록을 유지하면 현재 약 13.4MB 인식 모델 수준의 크기를 유지할 수 있지만, 정확도 개선은 미검증이다.
- 다음 세션의 첫 검토: 공식 학습 가중치·설정·문자 목록과 현재 ONNX의 대응 확인 → 별도 학습 환경 및 ONNX 재변환/출력 동등성 확인 → 범위를 정한 학습 실험 계획. 아직 설치·학습은 시작하지 않았다. 제품 `.venv`/lock·모델은 유지한다.
- 학습 자료는 다양한 글꼴·크기·배율·테마의 글자 이미지/정답 쌍으로 구성하고 문장·숫자·경로·기호를 섞는다. 일부 자동 합성 + 실제 자료를 활용한다. [일반 미세학습 가이드](https://www.paddleocr.ai/v2.10.0/en/ppocr/model_train/finetune.html)의 5,000개 권고는 성공 보장이나 이번 실험의 확정 수량이 아니다. 기존 실제 보류 12장은 학습에 쓰지 않고 독립 실제 평가 자료의 범위도 보강해야 한다.
- 다른 후속 후보: 지원 앱에서는 [UI Automation TextPattern](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-textpattern-overview)으로 원문을 직접 읽을 수 있으나 이미지/모든 프로그램에 적용되지 않는다. 구현하지 않았다.
- 별도 UI 개선 제안: ‘불확실한 곳 없음’을 ‘자동으로 표시된 확인 항목은 없습니다. 인식 오류가 남아 있을 수 있습니다.’처럼 의미가 정확한 안내로 바꾸기. 이것도 제안만 했으며 아직 적용하지 않았다.
