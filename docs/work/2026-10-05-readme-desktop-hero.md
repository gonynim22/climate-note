# 작업 기록: README 바탕화면 대표 이미지

작성일: 2026-10-05 / 상태: 제작·검증 완료 (게시 영수증 별도)

## 목표와 범위

- 목표: README의 이미지 한 장에서 바탕화면 상주 앱과 기본(작게)·크게의 차이를 직관적으로 보여준다.
- 변경 대상: `readme/app.png`, `README.md`의 대체 텍스트, 이 작업 기록.
- 데이터 영향: 없음. 캡처는 실행별 `output/harness/` 안에 만든 합성 데이터만 사용한다.
- 제외 범위: 앱 소스·의존성·버전·DB·EXE 변경, 실사용 앱/데이터 접근.
- 시작 시 사용자 변경: `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정과 기존 미추적 작업 기록 5개를 보존한다.

## 완료 조건

- [x] 기본·크게 실제 Qt UI를 같은 합성 일정/위젯으로 캡처.
- [x] 바탕화면 맥락과 크기 차이를 짧은 문구와 하나의 PNG로 표현.
- [x] 이미지 해상도·연결 경로·README 이미지 1개·Git 변경 범위 확인.
- [x] 원본/README 표시 크기 시각 확인과 실제 검증 결과 기록.
- 게시 단계: 아래 명시한 세 파일만 커밋하고 `git push origin main`의 실제 결과를 별도 영수증에 기록한다.

## 결정과 진행

- 사용자가 이미지 재제작·커밋·push까지 요청했다.
- [UI 계약](../UI_PATTERNS.md)의 기본 380×660과 크게 작업 영역−40px 규칙을 따르고, 설정 이름이 기본임을 표시한다.
- 배경은 제작 이미지, 앱은 합성 데이터를 넣은 실제 소스 UI 캡처로 구성한다. 실제 사용자 바탕화면을 수집하지 않는다.
- [검증 지침](../TESTING.md)에 따라 문서/이미지 변경의 링크·사실·시각 검사를 수행한다. 앱 변경이 없어 전체 테스트/EXE 재빌드는 범위 밖이다.
- 최종 이미지: `readme/app.png`, 2560×1340 PNG. 제목은 “바탕화면 위, 나만의 하루”, 비교는 “작게, 곁에 두고”(기본 크기) / “크게, 한눈에”. 같은 1440×900 가상 바탕화면과 작업 영역 1440×852에서 크기 비율을 유지했다.
- 실제 앱은 Windows Qt의 `QWidget.grab()`으로 캡처하고 HTML의 이미지 요소로 배치했다. 첫 offscreen 플랫폼 시안은 폰트·아이콘 표현이 Windows와 달라 채택하지 않았다. Windows 플랫폼·DPR 2·화면 비표시 속성으로 다시 캡처했다. 제품 코드와 사용자 창을 조작하지 않았다.
- 앱 UI 글자는 생성 모델로 다시 그리지 않았다. 배경은 내장 imagegen 제작 이미지, 바탕화면 아이콘/작업 표시줄은 디자인 요소다. 캡처 시 native 보호 hook은 합성 설정에서만 비활성화했으며 Win+D 문구는 기존 UI 계약을 설명한다. 이번 작업을 Win+D 실기 재검증으로 간주하지 않는다.
- 원본은 `output/harness/20261005-readme-desktop-hero-native-capture/app-previous.png`에 보존했다. 디자인 소스는 `output/design/readme-desktop-hero/hero.html`, 캡처 재현은 같은 디렉터리의 `capture.py <새 실행 ID>`, PNG 렌더는 별도 프로필의 headless Chrome을 사용했다.

### 배경 제작 프롬프트 (내장 imagegen)

> Create a single original Windows desktop wallpaper only, landscape 16:10 at high resolution (ideally 2880x1800). A tranquil atmospheric photographic landscape of softly layered Korean mountain ridges and a still lake at dawn, extremely clean and understated, desaturated eucalyptus and slate blue greens, warm misty ivory sky taking the upper 50 percent, subtly lit water in the lower quarter. Fine smooth mist, premium calm work environment. This image will be used as a background behind real productivity-app screenshots, so use restrained contrast and a low-detail quiet composition. The mountains should sit in the left center with open clean sky on the right, and avoid a dominant focal point. No text, letters, logos, watermarks, screens, devices, people, UI, icons or taskbar. Edge to edge landscape, no borders. Original artwork, not a reproduction of any stock Windows wallpaper.

## 검증 증거

| 명령/범위 | 상태 | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| `python tools/verify.py doctor` | 통과 | `20261005-223510-0d8f78a4f8` / `output/harness/20261005-223510-0d8f78a4f8/summary.md` | 프로젝트 Python 3.13 venv·lock 확인 |
| Windows Qt 기본/크게 캡처 | 통과 | `20261005-readme-desktop-hero-native-capture` / `capture.json` | 기본 380×660, 크게 1400×812, DPR 2, 실행별 합성 AppData |
| 원본/1040px 시각 확인 | 통과 | `output/design/readme-desktop-hero/hero-final.png`, `preview-1040.png` | 제목·크기 차이·바탕화면 맥락. 앱 세부 문구는 원본 확대 시 확인 |
| `.\.venv\Scripts\python.exe output/design/readme-desktop-hero/verify_asset.py` | 통과 | `20261005-readme-desktop-hero-verification` / `output/harness/20261005-readme-desktop-hero-verification/summary.md`, `result.json` | PNG·README 이미지 1개·링크·사용자 변경 보존·diff 확인 |
| 전체 pytest / release / Win+D·KVM 실기 | 미실행 | 해당 없음 | 앱 코드·EXE 변경 없는 문서/이미지 작업 |

## 미해결과 인계

- 남은 문제 / 수동 확인: 앱 실행 기능에 관한 새로운 검사 결과는 주장하지 않는다.
- 변경한 정본 문서: README 대표 이미지와 대체 텍스트.
- 게시 범위: `README.md`, `readme/app.png`, 이 작업 기록만 커밋한다. 기존 사용자 수정 2개와 미추적 기록 5개는 그대로 둔다.
- 배포·커밋·push: 사용자 요청으로 승인됨. 이 기록은 커밋 직전에 작성하므로 커밋 ID·push 종료 코드·원격 HEAD는 `output/harness/20261005-readme-desktop-hero-verification/publish.json`, `push.log`와 최종 응답에 남긴다. EXE 배포는 하지 않는다.
