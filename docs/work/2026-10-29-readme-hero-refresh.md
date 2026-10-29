# 작업 기록: README 대표 이미지 v4.5 갱신

작성일: 2026-10-29 / 상태: 제작·검증 완료 (게시 영수증 별도)

## 목표와 범위

- 목표: 사용자가 승인한 구성으로 앱 이름·새 아이콘을 강조하고 현재 v4.5 화면으로 README 대표 이미지를 갱신한 뒤 main에 push한다.
- 변경 대상: `readme/app.png`, `README.md` 대체 텍스트, 이 작업 기록.
- 데이터 영향: 없음. 실제 UI 캡처에는 새 `output/harness/` 하위 합성 데이터만 사용한다.
- 제외 범위: 제품 코드·DB·salt·설정·의존성·EXE·공개 Release 변경, 실사용 데이터/바탕화면 접근.
- 시작 상태: main `59495d0`, 원격 main과 일치, 추적 파일 변경 없음. 기존 미추적 작업 문서 12개와 `motion/`은 보존하고 커밋에서 제외한다.

## 완료 조건

- [x] 오른쪽 WINDOWS DESKTOP·기능 나열 삭제, 이름/아이콘 확대, 슬로건 축소.
- [x] 기본/크게 중복 배지와 하단 오른쪽 문구 삭제, 배경·좌우 비교·Win+D 안내 유지.
- [x] 실제 v4.5 기본/크게 UI와 새 아이콘으로 갱신, 기본 사이드바·일정 시각/반복/기간 예시 반영.
- [x] 원본 및 README 표시 크기 시각 확인, PNG·링크·변경 범위 검증.
- 게시 단계: 이번 세 파일만 커밋하고 `git push origin main`의 실제 결과와 원격 HEAD를 아래 후속 영수증에 기록한다.

## 결정과 진행

- 2026-10-29: 사용자가 제안 전체와 제작·push를 승인했다. 기존 디자인 소스 `output/design/readme-desktop-hero/hero.html`과 배경을 재사용해 새 작업 폴더에서 수정한다. 앱 글자를 생성 이미지로 다시 그리지 않고 실제 Windows Qt 위젯을 캡처한다.
- 정본: [UI 계약](../UI_PATTERNS.md), [아키텍처](../ARCHITECTURE.md), [검증](../TESTING.md). 앱 변경이 없는 문서/이미지 작업이므로 링크·사실·시각·변경 범위를 확인한다.
- 최종 구성: 이름 37→68px, 새 SVG 아이콘 58→88px, 슬로건 88→52px. 상단 여백을 정리해 PNG는 2560×1340→2560×1260이다. 오른쪽 두 문구·크기 배지·하단 오른쪽 문구를 제거하고 두 비교 제목과 Win+D 안내는 유지한다.
- 캡처: 2026-10-29 합성 일정, 바로가기 3개, 스티키·D-Day·집중 위젯을 실제 Windows Qt에서 DPR 2로 그렸다. 기본 460×660, 크게 1400×812를 동일한 1440×900 가상 바탕화면(작업 영역 1440×852)에 원래 비율로 배치했다. 반복 회의·기간 교육·시각/알림 예시가 보이며 시계 버튼·오늘 원형 표시·새 아이콘을 반영했다.
- 배경과 작업 표시줄은 기존 디자인 요소다. 실사용 바탕화면은 수집하지 않았고, native 보호 hook은 합성 설정에서만 끈 상태로 캡처했다. Win+D 실기 검증으로 간주하지 않는다.
- 제작 소스는 `output/design/readme-hero-v45/`에 보존했다. `capture.py <새 실행 ID>`로 합성 캡처를 만들고 `hero.html` 경로를 맞춘 뒤 `render.py`로 렌더한다. 이전 PNG는 `output/harness/20261029-readme-hero-v45/app-before.png`에 보존했다.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `tools/verify.py doctor` | 통과 | `20261029-202330-de9dc52557/summary.md` | Windows/Python 3.13·lock 일치 |
| 합성 데이터 Windows Qt 캡처 | 통과 | `20261029-readme-hero-v45-capture/capture.json` | 기본 460×660 / 크게 1400×812 / DPR 2, 실제 데이터와 native hook 사용 안 함 |
| `output/design/readme-hero-v45/verify_asset.py` | 통과 | `output/harness/20261029-readme-hero-v45/summary.md`, `result.json`, `layout.json` | PNG·브라우저 리소스/폰트/배치 경계·README/작업 기록 링크·diff·기존 파일 해시 확인 |
| 원본/README 시각 확인 | 통과 | `output/design/readme-hero-v45/hero-final.png`, `preview-1040.png` | 2560px 원본과 1040px 표시에서 위계·구도·잘림 확인 |
| 전체 pytest / release / 실기 Win+D·KVM | 미실행 | 해당 없음 | 제품 코드·EXE 변경 없는 대표 이미지 작업 |

## 미해결과 인계

- 최종 PNG: 1,181,170 bytes, SHA-256 `58265f05457f6890830af9dc81ef3df92bd24e07519c78d0100481508342aa8c`.
- 남은 문제 / 수동 확인: 앱 동작에 관한 새 검증 결과는 주장하지 않는다. 변경 대상 외 추적 파일 530개와 기존 미추적 파일 37개의 SHA-256을 보존했다.
- 변경한 정본 문서: README 대표 이미지와 대체 텍스트.
- 배포·커밋·push: 사용자 승인에 따라 `README.md`, `readme/app.png`, 이 기록만 커밋한다. 커밋 직전에 기록했으므로 실제 결과·커밋 ID·원격 HEAD는 `output/harness/20261029-readme-hero-v45/publish.json`과 `push.log`를 따른다. EXE 배포는 하지 않는다.
