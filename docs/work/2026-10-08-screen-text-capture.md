# 작업 기록: 화면 글자 따기 미니앱

작성일: 2026-10-08 / 상태: 진행 중

## 목표와 범위

- 목표: 공모전(행정업무 효율화)용 다섯 번째 미니앱. 화면 영역의 한국어를 PC 안 소형 모델로 읽고 표는 칸을 유지해 복사한다. 폴더 하나와 등록 한 줄로 걷어낼 수 있다.
- 변경 대상: `screen_text/`, `optional_mini_apps.py`, `ui_mini_apps.py`, `ui_main.py`(공용 연결부), `build.spec`, 의존성·라이선스·문서, `app_info.py`(v3.9).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·바로가기 6슬롯 유지. 결과·화면은 메모리 전용.
- 제외 범위: 전역 단축키, 파일 끌어놓기, 스티키 보내기, PDF, 기울기 보정, push·Release 게시.
- 시작 시 사용자 변경: `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 5개를 보존한다. 시작 HEAD는 계획 커밋.

## 완료 조건

- [ ] 설계 문서의 화면 흐름·인식·표 재구성·수명 처리·걷어내기 절차 구현
- [ ] `quick --tests` 각 단계, 125/150% 합성 배율, `release` 1회
- [ ] 업무 PC 수동 확인(캡처 차단, 한글 표 붙여넣기, 혼합 DPI, 실측)

## 결정과 진행

- 2026-10-08: 설계 승인, 계획 작성. 개발 PC 시제품에서 13px 한국어 문장·표를 거의 정확히 읽음(마침표 뒤 공백 누락), 폭 정렬 묶음으로 인식 약 0.2~0.35초. 같은 이미지에서 Windows 내장 OCR은 줄 누락·오인식.
- 2026-10-08 (Task 4 측정 게이트): 합성 표본 16개(본문·선 있는 표·선 없는 표·작은 글씨 × 100/125/150%/9pt, Malgun Gothic)로 소형 모델과 Windows 내장 OCR(`ko`) 비교. 평균 정확도 소형 모델 0.996, Windows OCR 0.575. 인식 시간 최대 0.23초(평균 약 0.11초), 모델 로딩 0.44초. 진행 기준(평균 >= Windows - 0.02, 최대 시간 <= 2.0초) 통과.
  - `UPSCALE` 1.0 유지: small9pt 평균 1.000, 100% 평균 0.996으로 9pt가 낮지 않아 확대 불필요(기준: 0.05 이상 낮을 때만 2.0).
  - `UNSURE_SCORE` 0.80 유지: 정답 상자 133개의 최저 점수 0.817, 오인식 상자 3개는 0.701(표 숫자 1→7), 0.889(시설→시절), 0.915(기간→7간). 0.80으로 0.701만 분리되고 정답 상자는 걸리지 않는다. 0.889·0.915는 정답 점수 범위와 겹쳐 점수로 분리 불가(0.90으로 올리면 3개 중 2개를 잡지만 정답 5개가 함께 걸림).
  - 한계: 정확도는 공백을 무시하고 쟀다. 소형 모델은 마침표·쌍점 뒤와 일부 어절 사이 공백이 빠진다. 합성 표본이라 실제 문서 성능은 업무 PC 확인에서 본다.
  - 실험 파일과 결과는 `output/spike-screen-text-20261008/`(git 미추적).

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tools/verify.py doctor` (Task 1) | 통과 | `20261008-214618-1e951b20f9` (`output/harness/`) | onnxruntime 1.30.0 설치 후. errors 없음 |
| `tools/verify.py quick --tests tests/test_packaging.py tests/test_screen_text_engine.py` (Task 1) | 통과 | `20261008-214620-611fde71dc` (`output/harness/`) | 75개 통과, 실패·오류·skip 0. 모델 SHA-256·size는 고정 리비전과 일치 |
| `tools/verify.py quick --tests tests/test_screen_text_layout.py tests/test_screen_text_engine.py` (Task 3) | 통과 | `20261008-215929-8bc0dfeb0e` (`output/harness/`) | 100개 통과, 실패·오류·skip 0. 엔진 16개는 합성 이미지(Malgun Gothic 13·16px 문장·표)로 실제 모델 인식. 경고 1건은 qfluentwidgets의 scipy 사용 중단 예고(기존) |
| 측정 게이트 `output/spike-screen-text-20261008/measure.py` (Task 4) | 통과 | `output/spike-screen-text-20261008/report.md` | 합성 표본 16개. 평균 0.996 대 0.575, 최대 0.23초. 코드 상수 변경 없음 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 업무 PC 확인 전부
- 변경한 정본 문서: (Task 8에서 기입)
- 다음 행동: Task 1부터 진행
- 배포·커밋·push 여부: 로컬 커밋만. push·Release 게시는 별도 승인
