# 작업 기록: 화면 글자 따기 입력 조건·인식 모델 비교

작성일: 2026-10-11 / 상태: 완료 (개발용 비교 도구·실험, 제품 적용 없음)

## 목표와 범위

- 목표: 기존 CTC 진단에서 해결되지 않은 오류에 대해 검출 영역을 고정하고 입력 조건과 인식 모델을 분리 비교한다.
- 변경 대상: `tools/screen_text_lab/`, 관련 자체 검사, 사용법/검증 문서. 모델 비교는 수동 개발 명령이다.
- 데이터 영향: 개발용 합성 corpus와 새 소유 출력 폴더만 사용. 사용자 화면·AppData·DB/salt 접근 없음. 제품·EXE·의존성 lock 변경 없음.
- 시작 시 변경: AGENTS.md·RELEASE_HISTORY.md와 기존 미추적 도구/문서/검사를 모두 보존한다.
- 기준: [검증](../TESTING.md), [제품 계약](../SCREEN_TEXT.md), [이전 CTC 진단](2026-10-11-screen-text-ctc-diagnosis.md).

## 완료 조건

- [x] 같은 검출 영역에서 입력 조건·모델을 따로 선택하고 원본/입력/모델 해시를 보존한다.
- [x] 외부 모델은 출처·라이선스·리비전·사전·SHA-256을 고정하고 개발 폴더에서만 읽는다. 실행 중 다운로드 없음.
- [x] 가짜 세션으로 입력 계약·디코딩·복원·모델 불일치 거부·옵션 미실행을 검사한다.
- [x] 실제 dev 자료의 정확도·신규 오류·표·시간·메모리·모델 용량을 비교하고 HTML에 남긴다.
- [x] 제품 적용/독립 평가와 개발 탐색을 구분한다. 이미 사용한 holdout을 새 최종 평가로 쓰지 않는다.

## 결정과 진행

- 변경 범위/실험 계획을 먼저 기록하고 기존 `karpathy-guidelines`의 작은 변경·검증 기준을 적용한다.
- 검출은 기존 제품 고정. 입력 조건은 글자 영역에만 적용하고 정답 문자열을 추론에 전달하지 않는다. 모델 고유 입력 높이/채널 차이는 계약에 기록한다.
- 후보 모델 조사: 공식 PaddleOCR 한국어 v3 및 EasyOCR 한국어 g2와 현재 v5 비교. 변환본 공급자의 모델 계약/출처를 확인한 것만 실행한다.
- 실제 입력/모델 비교는 개발용 160원문·1,920조건에서 수행할 수 있게 한다. 새 원문·실제 캡처 최종 검증은 후보가 정해진 뒤 별도 단계다.
- 고정 실험표: `tools/screen_text_lab/recipes/model-input-comparison.json`. 기존 dev의 10원문·50조건에서 제품 7조건/v3 3조건/EasyOCR 3조건(13실행·650건)을 먼저 비교하고, 모델별 native와 사전 규칙으로 고른 입력 조건을 전체 dev 1,920개에 적용한다. 선택은 공백 제외 오류→공백 포함 오류→표 셀 오류→조건 이름 순이며 사례마다 정답으로 모델을 고르지 않는다.
- 01:02:53 KST에 세 모델 모두 `ink-light`를 선택해 전체 실행 전에 `output/harness/20261011-010014-ddda620cee/selection-before-full.json`에 동결했다. 사용된 holdout은 재실행하지 않는다.

### 외부 자료·모델 출처

- 공식 모델 계약: [PaddleOCR 한국어 v3 설정](https://github.com/PaddlePaddle/PaddleOCR/blob/dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf/configs/rec/PP-OCRv3/multi_language/korean_PP-OCRv3_mobile_rec.yml), [공식 모델 목록](https://paddlepaddle.github.io/PaddleOCR/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html). 공급자의 일반 벤치마크를 앱의 정확도로 쓰지 않는다.
- v3 ONNX는 [GreatV/oar-ocr v0.3.0](https://github.com/GreatV/oar-ocr/releases/tag/v0.3.0)의 `korean_pp-ocrv3_mobile_rec.onnx` 9,912,841 bytes, SHA-256 `d30dbf20502044dc0e697f047564ac015e7083e4766fdc9d0fcd225aa2b0f20d`. 공급자 release API digest와 다운로드를 대조했다. 공식 사전/라이선스 리비전 `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf`.
- EasyOCR ONNX는 [iText 변환본](https://huggingface.co/itextresearch/itext-EasyOCR-korean_g2/tree/dd1e6f2ef5e8d633245f648454e16f29df25fec5) 16,074,370 bytes, SHA-256 `fa1028e57feff4a95777b190c496ddf351223f107b1e075449705c0e94661cbd`. Hugging Face 고정 리비전의 LFS digest와 대조했다. [변환 절차](https://github.com/itext/itext-pdfocr-java/tree/develop/easyOcr_to_onnx_export)에서 64px 가정을 확인했다. 변환 코드를 실행하지 않았다.
- EasyOCR 사전·라이선스는 [JaidedAI 고정 리비전](https://github.com/JaidedAI/EasyOCR/blob/363afb184047ce452e436f4224f3098422df872e/easyocr/config.py)에서 확보했다. 문구를 임의 보완하지 않고 g2 사전 문자열만 AST로 읽어 줄별 UTF-8로 저장했다. source/derived 사전을 모두 해시로 고정한다. [원 입력 구현](https://github.com/JaidedAI/EasyOCR/blob/363afb184047ce452e436f4224f3098422df872e/easyocr/recognition.py)의 gray/bicubic/끝 픽셀 패딩을 따른다. 전체 EasyOCR 프로그램의 검출/대비 재시도/전용 신뢰도는 비교 범위 밖이다.
- 두 모델 공급 자료는 Apache-2.0을 표시하며 원문 LICENSE를 개발 자산과 함께 보존한다. 제품 배포 라이선스 목록에 추가하거나 배포하지 않았다.
- 모델/사전 준비 중 첫 EasyOCR 사전 추출은 전체 config dict 안 함수 표현식 때문에 `ast.literal_eval`이 실패했다. 원격 코드를 실행하지 않고 g2 characters 문자열 노드만 선택해 재생성했다. v3 공식 사전의 공백 중복도 초기 일반 검사에서 거부됐다. 모델의 3,690클래스/공식 CTC 공백 추가 계약을 확인해 해당 모델의 중복 공백 두 클래스를 명시적으로 보존하고 자체 검사로 검증했다. 이를 인식 실행 실패나 임의 사전 교정으로 처리하지 않는다.

## 검증 증거

| 범위 | 상태 | 실행 ID / 결과 경로 | 유의사항 |
|---|---|---|---|
| 초기 자체 검사 | 통과 | [20261011-005923-f3fb3fdebd](../../output/harness/20261011-005923-f3fb3fdebd/summary.md) | 관련 8파일 215 passed / 실패·skip 0, 실제 모델 없음. 기존 scipy deprecated import 경고 1개 |
| 최종 자체 검사 | 통과 | [20261011-011301-7ac3bf94a2](../../output/harness/20261011-011301-7ac3bf94a2/summary.md) | 메모리 안내 문구의 범위 명확화 후 215 passed / 실패·skip 0 |
| 50개·13조합 탐색 | 완료 | [pilot-runs.json](../../output/harness/20261011-010014-ddda620cee/pilot-runs.json) | 650건, 기존 오류를 알고 고른 dev 표본 |
| 전체 dev 비교 | 완료 | [full-runs.json](../../output/harness/20261011-010014-ddda620cee/full-runs.json) | 1,920개×6조합, 독립 평가 아님. 전체 19실행 12,170건 성공 |
| 통합 HTML | 생성 완료 | [report](../../output/harness/20261011-010014-ddda620cee/report.html), [summary](../../output/harness/20261011-010014-ddda620cee/summary.md), [verification](../../output/harness/20261011-010014-ddda620cee/verification.json) | 원본 PNG와 실제 tensor에서 만든 전/후 12개 미리보기. 기존 브라우저 정책 차단을 우회하지 않음 |

### 최종 결과

- 제품 native 기준은 이전 dev의 744/46,692자(공백 제외 CER 1.5934%)와 일치했다. 새 `ink-light`는 632자(CER 1.3536%)이며 기존 `rec-ink-native` 결과와 **1,920개 모두 동일하게 재현**됐다. 새 정확도 개선으로 더하지 않는다.
- 정규화 후보의 공백 제외 완전 복구 100개/신규 오류 50개, 오류 감소 사례 140개/증가 80개. 표 정답 셀 1,791/1,836→1,787/1,836. CLI는 오류 108→107자에 신규 오류 사례 21개, 숫자는 오류 56→60자다. 전체 평균으로 CLI 개선을 주장하지 않는다.
- 정답 문자열과 사전의 추론 후 대조: 제품도 `℃`, `★`가 없어 24개 사례의 해당 24자를 정확한 코드포인트로 출력할 수 없다. v3는 1,296개 사례/2,568자, EasyOCR g2는 672개 사례/1,248자가 사전 밖이다. 새 사전 글자를 임의 추가하면 출력 클래스/가중치가 대응하지 않으므로 사전만 늘리지 않는다.
- 원래 결과를 유지하는 모의 경고 분석(사례 단위·공백 제외 글자만, 표 구조/실제 강조 위치 제외): 현재는 오류 441개 중 9개 발견/432개 누락·정상 1,479개 중 11개 오경고. 현재 경고에 두 입력 결과 불일치를 합치면 217개 발견/224개 누락·정상 오경고 60개다. 49개 추가 오경고와 추가 추론 비용을 평가해야 하며, 제품 기능이나 글자 정확도 개선으로 적용한 결과가 아니다.

| 모델 / 입력 | 공백 제외 CER | 오류/정답 글자 | 전체 실행 ID |
|---|---|---|---|
| 제품 v5 / native | 1.5934% | 744/46,692 | [20261011-010256-097ca51bd9](../../output/harness/20261011-010256-097ca51bd9/summary.md) |
| 제품 v5 / ink-light | 1.3536% | 632/46,692 | [20261011-010444-d15fea65d6](../../output/harness/20261011-010444-d15fea65d6/summary.md) |
| 한국어 v3 / native | 17.3734% | 8,112/46,692 | [20261011-010627-ffb6e0ae22](../../output/harness/20261011-010627-ffb6e0ae22/summary.md) |
| 한국어 v3 / ink-light | 16.5532% | 7,729/46,692 | [20261011-010748-c3b2597b89](../../output/harness/20261011-010748-c3b2597b89/summary.md) |
| EasyOCR g2 / native | 15.8635% | 7,407/46,692 | [20261011-010909-f3e955249f](../../output/harness/20261011-010909-f3e955249f/summary.md) |
| EasyOCR g2 / ink-light | 14.4265% | 6,736/46,692 | [20261011-011101-52111e412b](../../output/harness/20261011-011101-52111e412b/summary.md) |

- 모델/입력 6조합의 검출 좌표와 원 crop 해시는 동일하다. 두 Paddle 모델은 같은 입력 조건의 tensor 해시도 일치한다. 제품 native와 이전 기준은 텍스트·표·상자/점수·복사·경고·채점까지 1,920개 모두 같다.
- 처리 중앙값은 제품 native/정규화 약 36.22/36.26ms, v3 약 26.24/26.28ms, EasyOCR 약 40.29/40.83ms다. worker 전체 peak working set은 각각 276.1/278.6, 219.7/220.3, 275.4/264.6 MiB. 입력 해시 관측 포함 1회 측정이며 모델 단독 메모리/반복 성능 보증이 아니다.
- **판단:** 이번 두 대체 모델은 교체하지 않는다. 정규화 전면 적용도 신규 오류 50개/표 퇴행 때문에 하지 않는다. 제품·모델·사전·DB/설정·의존성·빌드는 그대로이며 제품에 적용된 정확도 변화는 0이다.

### 최종 검증과 제한

- 19개 실제 OCR 실행 중 코드/입력/모델 해시는 고정됐다. 실행 완료 후 공통 제한 안내의 `최대 메모리 미측정`을 `모델 단독 최대 메모리 미측정`으로 한 번 명확히 했다. worker 전체 peak는 실제 측정되어 있었으며, 추론/전처리/채점 변경은 없다. 이전 runner 사본을 통합 폴더에 보존하고 이 한 문구만 다름을 보고서 생성 때 문자열·SHA-256으로 검사했다. 기존 원 실행 증거는 수정하지 않았다. 최종 자체 검사는 문구 변경 뒤 다시 통과했다.
- 실제 입력 미리보기: `cond-symbols-013--wide`, `cond-cli-006--font10`의 native/ink-light 4개를 직접 확인했다. 보고서의 12개 미리보기 모두 저장된 tensor 해시와 대조한 뒤 RGB로 시각화한 것이며 배치의 추가 오른쪽 패딩은 제외한다.
- 최종 산출물 검증 통과: 실제 19실행·12,170개 레코드 재채점/PNG 해시, HTML 12,190개와 로컬 참조 85,696개, 문서 링크 64개. 실행 수/반복 조건을 고유 원문 수로 더하지 않는다. 세부 결과는 통합 폴더의 `verification.json`에 남겼다.
- 브라우저 HTML 시각 확인은 이전 정책 차단으로 미실행. 정적 링크/이스케이프/PNG 확인과 구분한다. 새로운 우회 경로를 사용하지 않았다.
- 통상 테스트/빌드/앱 시작에는 실제 대량 실험이나 다운로드를 연결하지 않았다. `git diff --check` 통과. 제품 파일·requirements/lock·공용 하네스·빌드 소스 변경 없음.

## 미해결과 인계

- 새 원문·실제 캡처 평가, 제품 적용/빌드: 이번 개발 실험 후 별도 판단.
- 후속 우선순위: 현재 v5 유지, 두 입력의 불일치로 오류 검토 신호를 만드는 방식의 위치 적중률·오경고·추가 지연시간 평가. 정규화 자동 대체와 구분한다. 선택 규칙을 고정한 뒤 새 원문/실제 캡처로 독립 검증한다.
- 정본 갱신: [사용법](../SCREEN_TEXT_LAB.md), [검증](../TESTING.md), [제품 계약](../SCREEN_TEXT.md).
- 배포·커밋·push: 수행하지 않음.
