# 작업 기록: 최초 실행 크기 선택 — 데스크 뷰 리디자인

작성일: 2026-10-05 / 상태: 완료 — 구현·검증·로컬 커밋·새 EXE 배치

## 목표와 범위

- 목표: 2026-10-04에 추가한 최초 크기 선택 대화상자(A안)의 디자인을 사용자가 고른 ‘시안 1 — 데스크 뷰’로 교체한다. 동작·데이터 흐름은 그대로 두고 화면만 바꾼다.
- 변경 대상: `ui_first_run.py`, `tests/test_first_run.py`, `app_fonts.py`(주석), `AGENTS.md`·`docs/UI_PATTERNS.md`·`docs/ARCHITECTURE.md`·`docs/TESTING.md`의 해당 계약 문구, 이 작업 기록.
- 데이터 영향: 없음. DB v17·Export v2·salt·설정 키·`calendar_scale` seed 경로·`main._initialize_database()` 흐름을 바꾸지 않는다.
- 제외 범위: 앱 버전 변경(v3.8d 유지), 창 테두리/DWM 처리 변경, 다크 테마 색 설계, 새 설정 키, 메인 캘린더·설정창 디자인 변경, GitLab push.
- 시작 시 사용자 변경: 수정된 `AGENTS.md`(보안 검사 push 보류·v3.7a·자체 보안 검사 기록 4줄), `docs/RELEASE_HISTORY.md`, 미추적 `docs/work/` 기록 5개를 보존하고 이번 커밋에 넣지 않는다.

## 확정한 디자인 (사용자 결정, 2026-10-05)

- 시안: 두 시안 중 **시안 1 — 데스크 뷰** 채택. 비교 시안·화면별 배치는 `output/design/first-run-size-redesign-20261005/`의 `index.html`, `desk-view-layouts.html`(로컬, Git 제외)에 있다.
- 넓은 배치(기본 680×500): 왼쪽 240px에 제목 ‘어떤 크기로 / 시작할까요?’, 안내 2줄, 라디오 행 3개(이름 + 짧은 설명). 오른쪽에 모니터 미리보기와 ‘1920×1080 화면 기준 · 오른쪽 아래 기본 위치’ 안내. 아래 오른쪽에 ‘종료’·‘이 크기로 시작’.
- 미리보기: 1920×1080 화면(작업 표시줄 48px)에 `ui_main`의 실제 크기 규칙(기본 380×660, 중간 60%, 크게 −40px)과 오른쪽 아래 20px 기본 위치를 적용한 벡터 그림. 선택하면 창이 그 크기로 움직인다.
- 선택 설명 문구(‘작업 화면 옆에 작은 캘린더를…’ 등)는 **표시하지 않는다**(사용자 요청).
- 낮은 화면(높이 470 미만): 여백·글자 압축, 두 번째 안내는 하단 버튼 왼쪽으로 이동, 모니터는 남는 공간에 맞춰 축소.
- 좁은 화면(폭 580 미만) 또는 매우 낮은 화면(높이 370 미만): 한 열 배치. 위에 ‘기본/중간/크게’ 간단한 버튼 3개, 아래에 모니터 미리보기.
- 글꼴: 제목·크기 이름·시작 버튼은 번들 Pretendard, 본문은 맑은 고딕(사용자 결정). 정수 px.
- 테마: 시스템 다크 모드와 무관하게 **항상 밝게**(앱 본체가 다크 모드를 따르지 않으므로 첫인상을 맞춤, 사용자 결정).

## 완료 조건

- [x] 구현할 동작과 유지할 계약: 위 디자인. 창 제목·기본 버튼(Enter=시작)·X/Esc/종료=취소·작업 영역 기준 크기 규칙·화면 변경 재배치·키보드(Tab/방향키/Space/Enter/Esc) 유지.
- [x] 관련 자동 검사: quick 프로필(`test_first_run` 50개 포함 107개)을 기본·125%·150% 합성 배율로 실행, 소스 프로세스 취소/확정/기존 실행. EXE 단계는 아래 ‘EXE 빌드·배치’ 참조.
- [x] 필요한 수동 확인: Qt 캡처 18 PNG × 3 배율(100/125/150%) 생성, 이 중 4종(`normal-medium`·`short-large`·`narrow320-compact`·`narrow-short-large`) × 3 배율을 직접 확인(다크 테마 설정에서도 밝게 그려지는지 포함). 나머지 캡처는 생성만 하고 눈으로 확인하지 않았다. 실제 혼합 DPI/KVM은 미확인으로 구분.

## 결정과 진행

- 2026-10-05: 시안 2개 작성(claude.ai 캔버스 + 로컬 HTML) → 시안 1 채택 → Pretendard·항상 밝게·좁은 화면 위 버튼/아래 미리보기·설명 문구 제거 결정.
- 2026-10-05: 구현 계획 [`docs/superpowers/plans/2026-10-05-first-run-desk-view-redesign.md`](../superpowers/plans/2026-10-05-first-run-desk-view-redesign.md) 작성. 사용자 검토 후 구현.
- 2026-10-05: 구현(`ui_first_run.py` 데스크 뷰, `tests/test_first_run.py` 갱신, `app_fonts.py` 주석)과 정본 문서 갱신을 마쳤다.
- 2026-10-05 결정(a): `fit_to_available_geometry`에서 `resize()` 앞에 `self.root.activate()`를 추가했다. 계획 코드대로면 한 열↔두 열 배치 전환 뒤 레이아웃이 아직 갱신되지 않아 창이 요청한 높이보다 크게 남고 Qt가 “Unable to set geometry” 경고를 냈기 때문이다. 활성화로 새 레이아웃의 최소 크기를 먼저 확정한 뒤 크기를 지정한다.
- 2026-10-05 결정(b): 전체 브랜치 최종 리뷰의 수정 묶음에서 (1) `docs/TESTING.md`의 끝 문장들을 복원했고, (2) 빈 머리글 영역을 다시 끌 수 있게 `brand_sub`에 stretch 1을 주고(테스트 추가), (3) UI_PATTERNS·AGENTS 문구를 명확히 하고, (4) 다크 모드 테스트가 Qt의 실제 다크 색 구성표를 쓰도록 바꿨다.
- 2026-10-05 Qt 캡처 비교(시안 `desk-view-layouts.html`과 다른 점): 시안은 모든 칸이 ‘기본’ 선택 상태이나 캡처는 기본·중간·크게를 각각 찍는다. 시안의 창 그림자는 `grab()` 캡처에 없고 1px 테두리만 보인다. 첫 번째 라디오에 키보드 포커스 점선 테두리가 남는다(시안에는 없음, 실제 포커스 표시). 그 외 배치·글꼴·미리보기 위치/크기는 시안과 같게 보였고 잘림·겹침은 없었다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 시안 HTML 캡처(headless Edge) | 확인 | 로컬 캡처, 제품 검사 아님 | 6개 작업 영역 × 기본/중간/크게 표시 확인. Qt 렌더·DPI 검사를 대신하지 않음 |
| `tools/verify.py quick --tests tests/test_first_run.py` (100%) | 통과 | `20261005-011115-5516233ced` (`output/harness/…/summary.md`) | quick 프로필 107개 통과(`test_first_run.py` 50개 포함), 실패 0. 최종 코드 기준 |
| 같은 명령, `QT_SCALE_FACTOR=1.25` | 통과 | `20261005-011137-e19f914523` | quick 프로필 107개 통과(`test_first_run.py` 50개 포함), 실패 0. 합성 배율이며 실제 혼합 DPI 아님 |
| 같은 명령, `QT_SCALE_FACTOR=1.5` | 통과 | `20261005-011157-8f97a11332` | quick 프로필 107개 통과(`test_first_run.py` 50개 포함), 실패 0. 합성 배율이며 실제 혼합 DPI 아님 |
| 소스 프로세스 시작 검사 `output/design/first-run-size-setup/probe_startup.py` | 통과 | `20261005-011221-desk-view-source-startup` | 취소→재표시 후 정상 종료·확정→메인(380×660)·기존 실행 생략 3개 모두 passed, 최상위 passed. 합성 LOCALAPPDATA, 실제 사용자 폴더 미접촉 |
| Qt 캡처 `output/design/first-run-size-redesign-20261005/capture_qt.py` 100% | 통과(직접 확인) | `20261005-011241-desk-view-qt-100` | PNG 18개. `normal-medium`·`short-large`·`narrow320-compact`·`narrow-short-large` 확인 |
| 같은 캡처, `QT_SCALE_FACTOR=1.25` | 통과(직접 확인) | `20261005-011241-desk-view-qt-125` | PNG 18개. 위 4장 확인 |
| 같은 캡처, `QT_SCALE_FACTOR=1.5` | 통과(직접 확인) | `20261005-011241-desk-view-qt-150` | PNG 18개. 위 4장 확인 |

검증 단계(Task 3)에서 실패한 실행은 없었다. 위 ID는 모두 최종 코드 기준이며, 구현 중 이전 실행 ID는 통과 증거로 쓰지 않았다. 구현 중 발견한 문제는 위 결정 (a)(b)에 남겼다.

구현 중(Task 1) 실패한 두 실행은 삭제하지 않고 증거로 보존한다. `20261005-003852-2778edbe45`는 새 상수 `PREVIEW_SCREEN_WIDTH`가 아직 없어 `ImportError`로 멈춘 **예상된 RED** 실행이고, `20261005-003953-80b0858a8f`는 레이아웃 테스트 2개(`test_dialog_layout_fits_work_area[800-400-False-True]`, `test_work_area_round_trip_reflows_without_old_minimum`)가 실패해 결정 (a)의 `self.root.activate()` 추가로 이어진 실행이다.

캡처 직접 확인 결과: 다크 테마를 설정했는데도 세 배율 모두 흰 바탕으로 그려지고 제목이 Pretendard 굵은 글씨다. `normal-medium`은 왼쪽에 제목·안내 2줄·라디오 3행, 오른쪽에 모니터 미리보기(중간 창이 오른쪽 아래)와 하단 버튼이 보인다. `short-large`는 안내 1줄, 라디오 행 압축, 하단 왼쪽 ‘설정에서 언제든 바꿀 수 있어요.’, 큰 창이 모니터 거의 전체를 덮는다. `narrow320-compact`와 `narrow-short-large`는 한 열이고 ‘기본/중간/크게’ 버튼 3개가 안내 아래, 미리보기 위에 있으며 ‘크게’에서는 창이 모니터를 거의 덮는다. 잘림·겹침·어두운 영역은 없었다.

## EXE 빌드·배치

사용자 요청으로 기능 커밋 `016549e` 기준 새 EXE를 빌드하고 격리 검증한 뒤 `dist`에 배치했다. 앱 버전은 v3.8d 그대로이고 EXE 이름도 같다.

- **release 실행**: `20261005-011942-c676bed1f4` (PowerShell, `tools/verify.py release`) — **통과**. [summary.md](../../output/harness/20261005-011942-c676bed1f4/summary.md)
  - 테스트 1,626개 통과, 실패·오류·건너뜀 0 (pytest 229.0초, 경고 1건은 `qfluentwidgets`가 쓰는 scipy 네임스페이스 사용 중단 예고).
  - 빌드 통과(PyInstaller 6.19.0, 49.1초).
  - 격리 EXE 시나리오 3개 통과: `fresh`(‘기후노트 — 처음 설정’ 창 확인 `first_run_setup_seen: true`, 확정 후 기본 380×660 메인, DB v17·`calendar_scale=compact`), `existing`(최초 설정 창 없이 저장 데이터로 시작), `blocked`(기존 데이터 보존). 종료는 전용 Job 강제 종료이며 정상 종료 확인은 하지 않았다(`graceful_quit_verified: false`).
- **EXE 포함 코드·Qt·원본 경로 검사**: 통과. 포함 모듈 13개가 현재 소스와 모두 일치(`ui_first_run` 포함), Qt DLL 4개 원본 일치·버전 6.11.2.0, BINARY 원본 경로에 Git/mingw 없음(`mingw_binaries: []`). [artifact-verification/summary.md](../../output/harness/20261005-011942-c676bed1f4/artifact-verification/summary.md)
- **동결 EXE 시작 검사**: `20261005-012754-desk-view-frozen-startup` — 취소(정상 종료)·확정(메인 380×660)·기존 실행(메인 380×660) 3개 모두 passed, 최상위 passed. 합성 LOCALAPPDATA를 사용했고 실제 사용자 폴더는 건드리지 않았다.
- **배치**: 실행 중인 기후노트 프로세스 없음을 확인한 뒤 같은 볼륨에서 임시 파일 복사 → SHA-256 확인 → `os.replace`로 교체했다. 배치 후 해시를 다시 계산해 release EXE와 같음을 확인했다. [placement.json](../../output/harness/20261005-011942-c676bed1f4/placement.json)

| 항목 | 경로 | 크기 | SHA-256 |
|---|---|---|---|
| 새 EXE (배치됨) | `dist/기후노트_v3.8d.exe` | 58,720,841 bytes | `2DE52766166D1CE5C42ED1ECF0FADC0A4AE8AA82BB0141DEA573748780A10DC1` |
| 이전 EXE (보존) | `output/harness/20261005-011942-c676bed1f4/previous/기후노트_v3.8d.exe` | 58,711,162 bytes | `BF1CD3E08E0832BCE3D07B0B422816D5C3712712D73270A89C31F4C55F43BFA4` |

- 이전 EXE 보존 경위: 배치 시작 시 `dist/`가 비어 있었다. 10월 5일 00:57에 사용자가 `dist/기후노트_v3.8d.exe`를 휴지통으로 지운 것으로 보이며(휴지통에 같은 이름·58,711,162 bytes·해시 `BF1CD3E0…`인 파일이 있음), 이 EXE는 강제로 건드리지 않았다. 그래서 `previous/`에는 같은 해시의 10월 4일 release EXE(`output/harness/20261004-231750-7a836dcd41/dist/`)를 복사해 보존했다. `artifact-verification`의 이전 EXE 값도 같은 파일에서 계산했다.
- 이번 단계는 제품 코드를 바꾸지 않았다. 자동 검증은 배포 승인이 아니며, 실제 Windows 잠금·혼합 DPI/KVM·Win+D·Defender·서명은 여전히 수동 확인 대상이다. GitLab 게시와 push는 하지 않았다.

## 미해결과 인계

- 남은 문제 / 수동 확인: 실제 Windows 잠금 상태, 실제 혼합 DPI·KVM 전환, 실제 PC 최초 실행에서의 화면은 수동 확인이며 미확인이다. 위 125%/150%는 합성 배율이다.
- 변경한 정본 문서: AGENTS.md(계약 줄·글꼴 줄·기록 관리 첫 항목), docs/UI_PATTERNS.md, docs/ARCHITECTURE.md, docs/TESTING.md.
- 다음 행동: 사용자가 `dist/기후노트_v3.8d.exe`를 직접 실행해 실제 PC에서 첫 화면을 확인한다. 실제 혼합 DPI/KVM·Win+D·Defender는 자동 검증에 포함되지 않았다.
- 배포·커밋·push 여부: 로컬 커밋만 수행. push·GitLab 게시는 하지 않음. EXE는 사용자 요청으로 재빌드·배치했다.
