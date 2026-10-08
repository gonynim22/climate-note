# 작업 기록: 화면 글자 따기 미니앱

작성일: 2026-10-08 / 상태: Task 8까지 로컬 구현·검증 완료(업무 PC 수동 확인 대기)

## 목표와 범위

- 목표: 공모전(행정업무 효율화)용 다섯 번째 미니앱. 화면 영역의 한국어를 PC 안 소형 모델로 읽고 표는 칸을 유지해 복사한다. 폴더 하나와 등록 한 줄로 걷어낼 수 있다.
- 변경 대상: `screen_text/`, `optional_mini_apps.py`, `ui_mini_apps.py`, `ui_main.py`(공용 연결부), `build.spec`, 의존성·라이선스·문서, `app_info.py`(v3.9).
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·바로가기 6슬롯 유지. 결과·화면은 메모리 전용.
- 제외 범위: 전역 단축키, 파일 끌어놓기, 스티키 보내기, PDF, 기울기 보정, push·Release 게시.
- 시작 시 사용자 변경: `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정과 미추적 `docs/work/` 5개를 보존한다. 시작 HEAD는 계획 커밋.

## 완료 조건

- [x] 설계 문서의 화면 흐름·인식·표 재구성·수명 처리·걷어내기 절차 구현
- [x] `quick --tests` 각 단계, 125/150% 합성 배율, `release` (release는 html 제외 오류 수정 때문에 2회: 아래 증거 표)
- [ ] 업무 PC 수동 확인(캡처 차단, 한글 표 붙여넣기, 혼합 DPI, 실측)

## 결정과 진행

- 2026-10-08: 설계 승인, 계획 작성. 개발 PC 시제품에서 13px 한국어 문장·표를 거의 정확히 읽음(마침표 뒤 공백 누락), 폭 정렬 묶음으로 인식 약 0.2~0.35초. 같은 이미지에서 Windows 내장 OCR은 줄 누락·오인식.
- 2026-10-08 (Task 4 측정 게이트): 합성 표본 16개(본문·선 있는 표·선 없는 표·작은 글씨 × 100/125/150%/9pt, Malgun Gothic)로 소형 모델과 Windows 내장 OCR(`ko`) 비교. 평균 정확도 소형 모델 0.996, Windows OCR 0.575. 인식 시간 최대 0.23초(평균 약 0.11초), 모델 로딩 0.44초. 진행 기준(평균 >= Windows - 0.02, 최대 시간 <= 2.0초) 통과.
  - `UPSCALE` 1.0 유지: small9pt 평균 1.000, 100% 평균 0.996으로 9pt가 낮지 않아 확대 불필요(기준: 0.05 이상 낮을 때만 2.0).
  - `UNSURE_SCORE` 0.80 유지: 정답 상자 133개의 최저 점수 0.817, 오인식 상자 3개는 0.701(표 숫자 1→7), 0.889(시설→시절), 0.915(기간→7간). 0.80으로 0.701만 분리되고 정답 상자는 걸리지 않는다. 0.889·0.915는 정답 점수 범위와 겹쳐 점수로 분리 불가(0.90으로 올리면 3개 중 2개를 잡지만 정답 5개가 함께 걸림).
  - 한계: 정확도는 공백을 무시하고 쟀다. 소형 모델은 마침표·쌍점 뒤와 일부 어절 사이 공백이 빠진다. 합성 표본이라 실제 문서 성능은 업무 PC 확인에서 본다.
  - 실험 파일과 결과는 `output/spike-screen-text-20261008/`(git 미추적).
- 2026-10-08 (Task 4 보강, 공백·순서·시간 한계): 위 평균 0.996/0.575는 공백을 무시한 값이다. 공백 연속을 한 칸으로 모으고 단일 공백은 유지해 같은 편집거리로 다시 쟀다(`spacing_accuracy.py`, `report.md` 끝에 기록).
  - 공백 포함 정확도: 전체 소형 모델 0.940 대 Windows OCR 0.589(게이트는 그대로 통과). 본문 8개 0.887 대 0.850, 표 8개 0.994 대 0.327. 본문 공백 정확도는 125·150%에서 Windows OCR이 더 낫다(body_125 0.895 대 0.930, body_150 0.884 대 0.977, small_125 0.898 대 1.000, small_150 0.898 대 0.959).
  - 결론: 소형 모델은 본문에서 공백을 잃는다(마침표·쌍점 뒤, 일부 어절 사이). 글자는 맞아도 띄어쓰기는 사용자가 확인해야 하며, 앞서 확인한 "마침표 뒤 공백 누락" 한계와 같은 현상이다. 표는 칸 구분이 따로라 영향이 적다.
  - Windows OCR 순서 한계: 표를 열 단위로 내보내는데 정답은 행 단위여서 0.575는 순서 불이익이 들어간 값이다. 순서를 무시한(글자 모음, 공백 무시) 점수는 Windows OCR 약 0.68(0.676), 소형 모델 0.996이다. 남은 차이는 누락된 칸 때문이다.
  - 시간 한계: 표본이 3~5줄이라 최대 0.23초였다. 검토자가 본문을 이어 붙인 24~48줄 이미지로 잰 값은 이 PC에서 1.3~1.4초이므로, 페이지 크기 영역의 인식 시간은 업무 PC에서 따로 확인한다.
- 2026-10-09 (Task 8, 빌드·릴리스): `build.spec`에 `_SCREEN_TEXT` 분기를 넣었다. `full` 1차에서 `test_main_window_settings_brought_to_foreground`가 실패해(공용 연결부가 `reset_succeeded`에 `_discard_optional_mini_apps`를 연결한 것이 기대 목록에 없었음) 기대 목록에 한 줄을 더했다.
  - **release 1차 EXE의 결함**: 1차 `release`(`20261009-011903-4cde3a908d`)는 테스트·빌드·격리 시나리오가 모두 통과했지만, 같은 실행의 `Analysis-00.toc`와 `build.spec` 제외 목록을 흉내 낸 합성 실행에서 `screen_text/layout.py`의 `import html`이 EXE에서 실패함을 찾았다(`warn-build.txt`: `excluded module named html - imported by screen_text.layout`). 격리 시나리오 3개는 도구 창을 열지 않아 놓친다. 폴더가 있을 때 `html`을 제외 목록에서 빼도록 고치고(`ffdbd0f`) 테스트를 더했다. 1차 EXE는 폐기한다.
  - **EXE 안 검증(자동 대체)**: 2차 EXE의 PyInstaller 아카이브에서 `det.onnx`·`rec.onnx`·`dict.txt`의 크기·SHA-256이 `MANIFEST.json`과 일치함을 확인했다. 합성 실행(제외 목록 모듈 import 차단, `Analysis-00.toc`의 포함 모듈과 대조)에서 엔진이 합성 한국어 두 줄을 읽고(`2026년 기후에너지환경부 회의 안내`, `일시10월 9일 장소 대회의실`) 표시 HTML·도구 창 생성까지 차단된 import 없이 통과했다. 소스 환경 기준이며 실제 EXE 클릭 실행은 아니다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tools/verify.py doctor` (Task 1) | 통과 | `20261008-214618-1e951b20f9` (`output/harness/`) | onnxruntime 1.30.0 설치 후. errors 없음 |
| `tools/verify.py quick --tests tests/test_packaging.py tests/test_screen_text_engine.py` (Task 1) | 통과 | `20261008-214620-611fde71dc` (`output/harness/`) | 75개 통과, 실패·오류·skip 0. 모델 SHA-256·size는 고정 리비전과 일치 |
| `tools/verify.py quick --tests tests/test_screen_text_layout.py tests/test_screen_text_engine.py` (Task 3) | 통과 | `20261008-215929-8bc0dfeb0e` (`output/harness/`) | 100개 통과, 실패·오류·skip 0. 엔진 16개는 합성 이미지(Malgun Gothic 13·16px 문장·표)로 실제 모델 인식. 경고 1건은 qfluentwidgets의 scipy 사용 중단 예고(기존) |
| 측정 게이트 `output/spike-screen-text-20261008/measure.py` (Task 4) | 통과 | `output/spike-screen-text-20261008/report.md` | 합성 표본 16개. 평균 0.996 대 0.575, 최대 0.23초. 코드 상수 변경 없음 |
| `tools/verify.py quick --tests tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py tests/test_ui_document_converter.py tests/test_ui_data_lifecycle.py tests/test_money_notation_integration.py tests/test_date_time_integration.py` (Task 5) | 통과 | `20261008-221823-bd62618a5d` (`output/harness/`) | 205개 통과, 실패·오류·skip 0. 선택형 공용 연결부는 가짜 앱(등록부 monkeypatch)으로 검사. 기존 주머니·문서 변환 수명 테스트는 등록부를 빈 튜플로 고정. 경고 1건은 qfluentwidgets의 scipy 사용 중단 예고(기존) |
| `pytest tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py` (Task 5, R8 Hide 이벤트 지점 추가 뒤 재실행) | 통과 | 하네스 실행 ID 없음 (pytest 직접 실행) | 45개 통과. 메인 창 Hide 이벤트 지점(10번째)을 더한 뒤의 확인 |
| `pytest tests/test_screen_text_capture.py` (Task 6) | 통과 | 하네스 실행 ID 없음 (pytest 직접 실행) | 11개 통과, 2회 실행 모두 같은 결과. 가짜 스크린샷만 사용(실제 화면 미사용) |
| `tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_screen_text_layout.py tests/test_screen_text_engine.py tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py tests/test_mini_app_icons.py tests/test_app_paths.py` (Task 7, 100%) | 통과 | `20261009-004034-b099e1ce30` (`output/harness/`) | 208개 통과, 실패·오류·skip 0. 도구 창은 가짜 엔진·가짜 스크린샷으로 검사(실제 화면·모델 미사용). 경고 1건은 qfluentwidgets의 scipy 사용 중단 예고(기존) |
| `QT_SCALE_FACTOR=1.25 tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_optional_mini_apps.py` (Task 7, 125%) | 통과 | `20261009-004102-54c0827a8c` (`output/harness/`) | 118개 통과, 실패·오류·skip 0. 배율 환경변수는 harness 결과에 기록되지 않아 명령으로만 남김 |
| `QT_SCALE_FACTOR=1.5 tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_optional_mini_apps.py` (Task 7, 150%) | 통과 | `20261009-004118-a6fa1bb770` (`output/harness/`) | 118개 통과, 실패·오류·skip 0. 배율 환경변수는 harness 결과에 기록되지 않아 명령으로만 남김 |
| `tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_screen_text_layout.py tests/test_screen_text_engine.py tests/test_optional_mini_apps.py tests/test_ui_mini_apps.py` (Task 7 수정 1차) | 통과 | `20261009-010004-ecdc0a102b` (`output/harness/`) | 194개 통과, 실패·오류·skip 0. 위 100%/125%/150% 실행은 이 수정 이전이라 아래 Task 8에서 125/150%를 다시 돌림 |
| `tools/verify.py full` (Task 8, 1차) | 실패 | `20261009-010930-0c7e23d7af` (`output/harness/`) | 1,747개 통과, 1개 실패: `tests/test_ui.py::test_main_window_settings_brought_to_foreground`. 원인은 Task 5의 공용 연결부가 `reset_succeeded`에 `_discard_optional_mini_apps`를 연결한 것인데 이 테스트의 기대 목록에 빠져 있었음(Task 5~7은 quick만 돌려 놓침). 기대 목록에 한 줄 추가(커밋 `df57575`) |
| `tools/verify.py full` (Task 8, 수정 뒤) | 통과 | `20261009-011354-bc797c1994` (`output/harness/`) | 1,748개 통과, 실패·오류·skip 0. 경고 1건은 qfluentwidgets의 scipy 사용 중단 예고(기존). HEAD `df57575` |
| `QT_SCALE_FACTOR=1.25 tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_optional_mini_apps.py` (Task 8, 125% 재실행) | 통과 | `20261009-011755-5128cee4ca` (`output/harness/`) | 128개 통과, 실패·오류·skip 0. Task 7 수정 뒤의 재실행. 배율 환경변수는 harness 결과에 기록되지 않아 명령으로만 남김 |
| `QT_SCALE_FACTOR=1.5 tools/verify.py quick --tests tests/test_screen_text_ui.py tests/test_screen_text_capture.py tests/test_optional_mini_apps.py` (Task 8, 150% 재실행) | 통과 | `20261009-011812-aab68ad6cc` (`output/harness/`) | 128개 통과, 실패·오류·skip 0. 위와 같음 |
| `osv-scanner scan source -L requirements-lock.txt` (Task 8, OSV-Scanner 2.5.1) | 통과 | 하네스 실행 ID 없음 (`output/harness/20260911-212909-security-6420ac33/bin/osv-scanner_windows_amd64.exe`) | `found 35 packages`, `No issues found`, 종료 코드 0. onnxruntime 1.30.0·flatbuffers 25.12.19·protobuf 7.36.2·numpy 2.2.6 포함 |
| PowerShell `.venv\Scripts\python.exe tools/verify.py release` (Task 8, 1차) | 통과(EXE는 폐기) | `20261009-011903-4cde3a908d` (`output/harness/`) | 1,748개 통과, 빌드·격리 EXE 시나리오 3개(fresh/existing/blocked) 통과. EXE `기후노트_v3.9.exe` 93,816,349 bytes, SHA-256 `98AE6AD38B1E72972BD27324C9FA02323973281E95983C0E3B8A6CAE95D00D12`. `import html` 제외 결함이 있어 폐기하고 아래 2차로 대체. HEAD `863e294`~`df57575` 기준 |
| PowerShell `.venv\Scripts\python.exe tools/verify.py release` (Task 8, 2차, 최종) | 통과 | `20261009-013003-bab27e5f78` (`output/harness/`) | 1,748개 통과(실패·오류·skip 0), 빌드 통과, 격리 EXE 시나리오 3개 통과. HEAD `ffdbd0f`(작업 트리는 사용자 원래 미커밋 변경 때문에 dirty). `smoke.json`의 `exe_sha256`이 아래 EXE 해시와 일치. 격리 시나리오는 도구 창을 열지 않음 |
| EXE 구성 대조 (2차 `build/build/Analysis-00.toc`와 EXE 아카이브) | 통과 | `20261009-013003-bab27e5f78` | 아래 "EXE 대조" 참고 |
| 새 EXE에서 주머니 → 화면 글자 따기 → 합성 이미지 영역 인식 1회 | 수동 미실행 | - | 자동 실행 환경에서 GUI를 조작할 수 없어 업무 PC 확인 목록으로 이관. 위 합성 실행(소스 환경, 제외 모듈 차단)과 아카이브 모델 해시 대조로 대체했으며 이는 실제 EXE 실행이 아님 |
| `tools/verify.py quick --tests tests/test_packaging.py` (Task 8 수정 1차) | 통과 | `20261009-014746-cb3cf72608` (`output/harness/`) | 75개 통과, 실패·오류·skip 0. 빌드 분기 시험이 저장소의 `screen_text/` 폴더에 기대지 않게 고침: 폴더 있음/없음을 모두 빈 임시 폴더로 만들고, `screen_text/`를 잠시 `screen_text.__hidden`으로 바꾼 채 `tests/test_packaging.py` 6개 통과를 확인한 뒤 되돌림(걷어낸 뒤에도 `full`이 통과하도록). `build.spec`은 바뀌지 않아 release 2차 EXE(`20261009-013003-bab27e5f78`)는 그대로 유효. 시험·설계 문서만 변경 |

## EXE 대조 (release 2차 `20261009-013003-bab27e5f78`)

- 산출물: `output/harness/20261009-013003-bab27e5f78/dist/기후노트_v3.9.exe` (루트 `dist/`는 교체하지 않음. 루트에는 v3.8e만 남아 있음)
- 크기 93,857,207 bytes. v3.8e(59,049,343 bytes)보다 34,807,864 bytes(약 58.9%) 큼. 설계 예상(약 100MB 안팎)보다 작음.
- SHA-256 `5763CB403EF19E08C86D28102D3A0CDAAF7D4D1F6EA2A09A693E919BC67003F8`
- `Analysis-00.toc`: `screen_text/models/{det.onnx,rec.onnx,dict.txt,MANIFEST.json,LICENSE}`, `screen_text/icon.svg`, `screen_text/licenses/{numpy-LICENSE.txt,onnxruntime-LICENSE.txt,onnxruntime-ThirdPartyNotices.txt}` 포함. `onnxruntime/capi/onnxruntime.dll`·`onnxruntime_pybind11_state.pyd`, `numpy` 모듈과 `numpy/_core/_multiarray_umath` 확장, `numpy.libs`(OpenBLAS·msvcp140 DLL) 포함. `screen_text`·`screen_text.{capture,engine,layout,window}` 모듈 포함. `html`·`html.entities` 포함(2차).
- mingw(`C:\\Program Files\\Git\\mingw64\\bin`) DLL 부재(TOC·아카이브 모두 0건). `libcrypto-3.dll`·`libssl-3.dll`은 기존과 같은 전역 Python `DLLs` 폴더 출처.
- `google\\protobuf`·`flatbuffers` **미포함 확인**: TOC에 없다. 그래서 두 패키지의 라이선스 원문·고지는 번들 `screen_text/licenses/`에 더하지 않았다(THIRD_PARTY_NOTICES에도 항목 없음). lock에만 있는 개발 환경 의존성이다.
- 합성 실행의 로드 모듈 99개(numpy·onnxruntime·screen_text) 중 TOC에 PYMODULE로 없는 것은 확장 모듈(.pyd) 5개뿐이며 모두 BINARIES에 있다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 업무 PC 확인 전부(페이지 크기 영역 인식 시간 포함). 새 EXE에서 주머니 → 화면 글자 따기 → 인식 1회(실제 EXE 클릭 실행)도 이 목록에 포함. 격리 시나리오가 도구 창을 열지 않으므로 이 수동 확인이 첫 실제 EXE 인식 확인이다
- 변경한 정본 문서: `AGENTS.md`(계약 항목·아이콘 색·미니앱 버튼 항목), `README_detail.md`(기능 목록), `docs/ARCHITECTURE.md`(Module Map 두 행), `docs/TESTING.md`(화면 글자 따기 문단), `docs/SCREEN_TEXT.md`(신규 계약), `licenses/THIRD_PARTY_NOTICES.txt`, 설계 문서 §3·§4·§7·§8·§11·§14. 아직 v3.8e로 남은 곳: `README_detail.md`의 현재 버전·다운로드·EXE 해시 문단과 `AGENTS.md`의 버전 이력(루트 `dist/`가 v3.8e이고 게시 전이라 릴리스 상태 문서 갱신 때 함께 정리)
- 다음 행동: 최종 검토 → 업무 PC 수동 확인(캡처 차단, 한글 표 붙여넣기, 혼합 DPI, 실측, 새 EXE 인식 1회) → 릴리스 상태 문서 정리와 `dist/` 교체 여부 결정
- 배포·커밋·push 여부: 로컬 커밋만(Task 8: `863e294`, `df57575`, `ffdbd0f`와 증거 갱신 커밋). 루트 `dist/` 교체, push, Release 게시는 별도 승인
