# 작업 기록: 화면 글자 따기 공백 복원 적용

작성일: 2026-11-06 / 상태: 구현·검증 완료(quick). 커밋·release·push 미수행

## 목표와 범위

- 목표: 인식 모델이 내지 못하는 줄 안 공백을 화면의 실제 빈 틈으로 복원한다. 근거는 [실패 분석 기록](2026-11-05-screen-text-failure-analysis.md). 2026-11-06 사용자 승인("응").
- 변경 대상: `screen_text/engine.py`(`ctc_decode_detail`·`ink_gap_cuts`·`insert_gap_spaces` 추가, `_read`가 공백 위치를 반영), 새 시험 `tests/test_screen_text_space_gaps.py`, 문서 `docs/SCREEN_TEXT.md`·`TESTING.md`·`SCREEN_TEXT_LAB.md`·`AGENTS.md`의 화면 글자 따기 줄.
- 데이터 영향: 없음. 모델·사전·MANIFEST·DB·설정 키·Export 변경 없음. 글자는 바꾸지 않고 공백만 넣는다.
- 제외 범위(분석에서 근거가 없어 보류): 줄 끝 마침표용 상자 확장(B), 위치 찾기 1600px(C). 글머리 기호 복원(미시험), 못 읽는 기호 표시(미시험). 버전 번호·EXE 빌드·release.
- 시작 시 사용자 변경: 없음(미추적 `docs/work/*`와 `motion/`만).

## 완료 조건

- [x] 공백 복원: 글자 높이 0.40배(최소 3px) 이상 빈 열의 가운데를 CTC 위치에 대응해 공백만 삽입
- [x] 유지할 계약: `ctc_decode` 상자마다 한 번 호출(진단 도구 가로채기), 모델·사전·해시 불변, 점수·불확실 표시 불변, 배치 인식 경로 유지
- [x] 관련 자동 검사: 새 시험 17개(순수 함수 8·실제 모델 9) + `test_screen_text_*` 전체
- [ ] 필요한 수동 확인: 업무 PC·실제 한글(HWP)·엑셀 화면에서 공백이 자연스러운지, 앱 창에서 복사 결과 확인, release 후 EXE 격리 실행

## 결정과 진행

- 2026-11-06: TDD. 새 시험을 먼저 작성해 14개 실패(기능 없음 8·공백 복원 6)와 3개 통과(붙여 쓴 단어 보호)를 확인했다. 최소 구현 후 34개(새 17+기존 엔진 17) 통과.
- 2026-11-06: 첫 구현은 `_read`가 `ctc_decode` 대신 `ctc_decode_detail`을 불러 진단 도구 시험 3개가 깨졌다(`test_screen_text_lab_candidates`·`test_screen_text_lab_ctc` 2개). 도구가 `module.ctc_decode`를 가로채 상자마다 한 번 호출됨을 전제로 하기 때문이다. `ctc_decode`는 그대로 한 번 부르고 위치용 분해를 따로 하되, 디코드 결과와 분해의 글자가 같을 때만 공백을 넣도록 고쳐 해결했다(도구·시험은 변경하지 않음).
- 임계값 0.40: 합성(메모장 48장·합성 457장)에서는 0.38~0.42, 독립 글꼴 360장에서는 0.42, 실제 PDF에서는 0.38/0.40/0.42가 81.3/81.1/80.7%로 같았다. 가운데 값을 썼다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tests/test_screen_text_space_gaps.py` 먼저 실행 | 실패(기대) | 14 failed, 3 passed | 구현 전. 기능 없음 8·공백 복원 6 실패 |
| 새 시험 + `test_screen_text_engine.py` | 통과 | 34 passed | 구현 후 |
| `quick --tests tests/test_screen_text_*.py` (첫 구현) | 실패 | `output/harness/20261106-000742-a8381235b5` | 886 중 3 실패(진단 도구가 `ctc_decode` 가로채기) |
| `quick --tests tests/test_screen_text_*.py` (수정 후) | 통과 | `output/harness/20261106-001000-067266b921` | 886 passed, 0 failed |
| `quick --tests tests/test_screen_text_*.py tests/test_mini_app_icons.py` (문서·시험 설명 수정 후 최종) | 통과 | `output/harness/20261106-002828-100632c84a` | 917 passed, 0 failed |
| 제품 코드로 실제 PDF dev 294장 | 완료 | `output/screen_text_lab/analysis-20261105/results/pdf_final.log` | 단어 일치율 61.5% → 80.8%, 글자 오류 4.08% 동일 |
| 열화 이미지 196장×4조건 (원본·JPEG35·잡음·스캔 느낌) | 완료 | `.../results/scan_check.log` | 단어 일치율 끔→제품: 64.0→83.7, 44.3→82.1, 64.7→82.9, 48.5→73.6. 한두 줄 크롭 기준 엉뚱한 공백 10~22→37~47곳, 빠진 공백 148~305→25~44곳 |
| holdout 600장(제품 코드 직접) | 미실행 | | 시험 구현(A40)으로 이미 한 번 썼다(64.8→82.4%). 제품 코드 최종 확인은 새 쪽을 더 뽑아 쓸 것 |
| `data`/`full`/`release` | 미실행 | | 엔진 내부 변경만. EXE 확인은 release 때 |

## 미해결과 인계

- 남은 문제: 글머리 기호(`ㅇ □ ■`), 로마 숫자, `△▲`; 자간이 좁은 한컴 글꼴에서 공백이 빠질 수 있음; 자간이 넓은 글꼴에서 한글 음절 사이에 공백이 끼어들 수 있음(한두 줄 크롭 기준 엉뚱한 공백은 원본 37곳, JPEG 45곳, 잡음 44곳, 스캔 느낌 47곳으로 복원 끔의 10~22곳보다 늘었다. 빠진 공백 감소가 훨씬 커서 순이득이다).
- 변경한 정본 문서: `docs/SCREEN_TEXT.md`(엔진·알려진 한계)·`docs/TESTING.md`·`docs/SCREEN_TEXT_LAB.md`·`AGENTS.md`(화면 글자 따기 줄).
- 다음 행동: 사용자가 결정하면 글머리 기호 복원 시험(spike). 제품 반영 전 새 PDF 쪽·실제 한글/엑셀 캡처로 최종 평가. 버전 번호·release는 별도 요청 때.
- 배포·커밋·push 여부: 수행하지 않음 / 별도 승인 범위
