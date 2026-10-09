# 작업 기록: 공모전 준비를 위한 설정 라이선스 분석

작성일: 2026-10-09 / 상태: 현황 분석 완료, 갱신 및 공모전 규정 대조 미실행

후속 구현: 사용자가 버전·기능·데이터 유지 조건으로 수정을 승인하여 [v3.9a 고지 정비](2026-10-09-license-notices-update.md)를 완료했다. 아래는 수정 전 점검 기록이며 현재 구현·검증·EXE는 후속 기록을 따른다.

후속: 사용자의 미니앱·AI 상세 점검 요청에 따라 [미니앱 상세 점검](2026-10-09-mini-app-license-audit.md)을 추가했다. **HWP 공개 명세의 지정 고지 누락, 모델 LICENSE의 PaddlePaddle 저작권 문구 누락**을 추가 확인했고, OCR 모델의 고정 리비전 Apache-2.0 표기·원격 해시·공식 사전까지 대조했다. 아래의 '원문 파일 있음'은 원저작자 고지까지 완비됐다는 뜻이 아니다.

## 목표와 범위

- 목표: 프로젝트 구조, 설정 라이선스 표시, 고지 원문, 실제 EXE 구성 및 소스 제공 경로를 대조하고 공모전 제출 전 갱신 항목을 정리한다.
- 변경 대상: 이 분석 기록만 작성한다. 사용자 요청은 갱신에 앞선 현황 분석이다.
- 데이터 영향: 없음. 실사용 AppData·DB·salt·실행 중 앱을 접근하지 않는다.
- 제외 범위: 런타임/UI 수정, 의존성 변경, EXE 재빌드, 커밋·push·배포, 공모전 규정 없는 참가 적격 확정.
- 시작 시 사용자 변경: `AGENTS.md`, `docs/RELEASE_HISTORY.md` 수정 및 미추적 작업 기록 5개를 보존한다.

## 완료 조건

- [x] 설정 표시와 저장소 고지문·실제 번들 구성의 차이를 확인한다.
- [x] 공식 라이선스 근거와 프로젝트 내부 근거를 구분한다.
- [x] 공모전 조건에 따라 달라지는 부분 및 갱신 범위를 정리한다. 공고 자체의 적격 판정은 미실행이다.
- [x] 검증 결과와 미실행 범위를 기록한다.

## 결정과 진행

- 2026-10-09: `ui_settings.LICENSE_TEXT`는 6개 구성요소를 하드코딩한 요약이며, `_on_license()`는 확인 버튼만 있는 `MessageBox`를 표시한다. 원문 열기와 앱 GPLv3 및 대응 소스 안내는 없다.
- 2026-10-09: `README.md`와 루트 `LICENSE`는 GPLv3를 명시한다. 기존 라이선스 정비 HOLD 기록은 `docs/RELEASE_HISTORY.md`가 정본이며 이번 분석으로 완료 처리하지 않는다.
- 2026-10-09: 공모전명/공고 URL을 질문했다. 규정이 제공되면 오픈소스 허용, 권리 귀속, 소스 접근 및 AI 활용 조건을 대조한다.
- 2026-10-09: 실제 EXE를 실행하지 않고 PyInstaller `CArchiveReader`로 내부 목록·고지 파일·`ui_settings` 코드 객체의 문자열 상수를 확인했다. 현 소스와 EXE의 고지 내용은 일치한다.
- 2026-10-09: 릴리스 당시 입력 해시와 현재 파일을 대조한 결과 Markdown 문서 외 빌드 입력 차이가 없다. 현재 HEAD는 `ac7306a884205790533d2bc70ed6ccf3b91b3b43`이고 로컬 `origin/main`도 같다. 이는 서버 재조회나 외부 심사자의 접근 확인을 의미하지 않는다. 로컬 `v3.9a` 태그도 존재한다.

## 프로젝트 이해와 조사 기준

- Windows 전용 Python 3.13/PySide6 앱이다. `main.py`가 초기 건강 검사·최초 크기 선택·트레이와 메인을 연결하고 `ui_main.py`가 일정, 스티키, D-Day, 집중, 설정 및 미니앱 수명을 소유한다.
- `database.py`의 SQLite v17, `security.py`의 암호화, Export v2와 백업은 기존 계약이다. 이번 라이선스 정비는 이 데이터 경로를 바꿀 이유가 없다.
- 단위 환산, 날짜·시간, 금액 표기, HWP→HWPX, 선택형 화면 글자 따기를 제공한다. OCR은 ONNX 모델과 런타임을 실제 번들한다. 한글/HWPX 변환기는 사용자의 설치본을 CLI로 호출하고 엔진은 번들하지 않는다.
- `app_info.py` 기준 v3.9a, 2026. 10. 9.이며 PyInstaller one-file로 배포한다. 조사 대상은 `dist/기후노트_v3.9a.exe`, 93,874,139 bytes, SHA-256 `ED4BBD6B15E6224028629A14F33C69DCB0CBAF936E2DB402EE2ED102E4790FDF`다.
- 패키지 설치 목록만으로 배포 목록을 판단하지 않았다. 릴리스 `20261009-132546-f2aab9b4b1`의 `Analysis-00.toc`와 최종 EXE 내부를 함께 읽었다. DLL 안에 정적 포함된 모든 하위 프로젝트까지 확정한 전수 SBOM은 아니다.

## 설정 → 라이선스의 현황

진입점은 `ui_settings.py`의 `licenseBtn`(833행 부근), 내용은 `LICENSE_TEXT`(102행), 표시는 `_on_license()`(1223행)다. 요약을 `qfluentwidgets.MessageBox`로 띄우고 확인 버튼만 제공한다. 저장소 고지 파일을 읽지 않으며 원문·대응 소스 안내 기능이 없다.

| 구성요소 | 실제 버전 / 라이선스 근거 | 설정 요약 | 원문·번들 상태 및 갱신 사항 |
|---|---|---|---|
| 기후노트 | v3.9a / README와 루트 LICENSE의 GPLv3 | 없음 | 앱의 적용 라이선스, 권리자, 무보증, 재배포와 소스 안내 필요 |
| PySide6·Qt·shiboken6 | 6.11.2 / PySide6 메타데이터는 LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; Qt 모듈별 별도 확인 | PySide6 LGPL-3.0만 | LGPL 원문 있음. Qt 전체를 LGPL 하나로 설명하면 실제 번들과 차이가 생김 |
| PySide6-Fluent-Widgets(qfluentwidgets) | 1.11.1 / 설치 메타데이터 GPLv3, GPLv3 전문 | GPLv3 / 상용, 공공기관 납품 시 상용 검토 문구 | GPL 원문 있음. 실제 선택한 경로와 대안 라이선스를 구분해야 함 |
| PySideSix-Frameless-Window | 0.8.0 / LGPLv3 | 없음 | 제3자 고지에 있으며 공용 LGPL 원문 사용. 구성요소 저작권 고지도 대조 필요 |
| Fluent UI System Icons | MIT | 있음 | MIT 원문 있음. THIRD_PARTY_NOTICES의 대표 항목에 별도 출처 정리가 없음 |
| Pretendard | 1.3.9 / OFL-1.1 | 있음 | TTF 4개와 원문 포함 |
| Font Awesome Free | 6.7.2 / 번들 TTF는 OFL-1.1 | 있음 | TTF 2개와 원문 포함. 현재 TTF 표시는 맞음; SVG/JS의 CC BY 4.0과 구분 |
| cryptography | 50.0.0 / Apache-2.0 OR BSD-3-Clause | 버전 없는 요약 | 이중 라이선스 안내 및 두 원문 포함. 네이티브 내부 의존성 별도 대조 |
| PaddleOCR ONNX 모델·사전 | PP-OCRv3 mobile det, Korean PP-OCRv5 mobile rec / 로컬 MANIFEST와 배포자 모델 카드의 Apache-2.0 | 없음 | 모델 LICENSE·리비전·파일별 SHA-256 존재. 설정에 모델 출처 표시 필요 |
| ONNX Runtime | 1.30.0 / MIT | 없음 | MIT와 ThirdPartyNotices 원문 포함 |
| NumPy | 2.2.6 / BSD-3-Clause 및 번들 구성요소별 조건 | 없음 | 원문·하위 고지 포함. OpenBLAS 등의 고지를 유지해야 함 |
| pywin32 | 311 / 설치 메타데이터 PSF | 없음 | 실제 DLL/Python 모듈 포함. 프로젝트 대표 고지와 전용 원문 정비 대상 |
| defusedxml | 0.7.1 / 설치 메타데이터 PSFL | 없음 | 실제 모듈 포함. 고지 정비 대상 |
| darkdetect·colorthief | 0.8.0 BSD-3-Clause / 0.2.1 BSD(메타데이터 표기) | 없음 | 실제 모듈 포함. 버전별 저작권·라이선스 전문 확보 필요 |
| cffi backend·typing_extensions | 2.0.0 MIT / 4.15.0 PSF-2.0 | 없음 | `_cffi_backend` 네이티브 확장, typing_extensions 모듈 포함. 고지 정비 대상 |
| Python·네이티브 런타임·PyInstaller bootloader | Python 3.13 계열, OpenSSL·libffi·SQLite·MSVC 등; PyInstaller 6.19.0은 별도 예외가 있는 GPL 계열 | 없음 | 실제 빌드의 버전·원문·재배포 조건을 전수 목록으로 정리해야 함. PyInstaller를 썼다는 사실만으로 앱 GPL 의무가 생긴다고 설명하면 안 됨 |

`numpy.libs/libscipy_openblas64_*.dll`은 실제 포함돼 있다. 파일명에 scipy가 있어도 SciPy Python 패키지가 포함됐다는 뜻은 아니다. 이번 EXE에서는 PIL·scipy·pytest·protobuf·flatbuffers를 사용 라이브러리 목록에 무조건 추가하면 부정확하다. 설치 lock과 번들을 구분해야 한다.

## 우선 확인한 문제

### 1. 앱 라이선스와 원문 접근이 빠져 있다

루트 `LICENSE`와 README는 기후노트를 GPLv3로 설명하지만 설정에는 앱 자체의 고지가 없다. 작성자 크레딧은 있지만 법적 권리자 확인을 대신하지 않는다. `GPL-3.0-only`와 `GPL-3.0-or-later` 중 무엇을 부여할지도 권리자 의사에 맞춰 명확히 할 수 있다. 이번 분석에서 임의로 선택하지 않는다.

빌드 datas는 `licenses/`를 포함하지만 루트 `LICENSE`를 따로 넣지 않는다. **GPLv3 전문 자체가 없는 것은 아니다.** 같은 전문이 `licenses/QFluentWidgets-LICENSE.txt`로 이미 들어 있다. 다만 사용자에게 앱의 적용 라이선스와 원문을 쉽게 연결하는 화면이 없다. EXE에 압축된 파일 존재와 사용자의 실제 열람 가능성을 구분해야 한다.

### 2. Qt Virtual Keyboard의 실제 포함을 반영해야 한다

최종 EXE에 `PySide6/Qt6VirtualKeyboard.dll`과 `plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll`이 들어 있다. 공식 Qt 6.11.2 문서는 해당 모듈을 **Commercial or GPLv3**로 명시한다. `build.spec`에서 Python의 QML/Quick 등을 제외해도 네이티브 플러그인 의존 DLL까지 모두 빠지는 것은 아니다. Qt6Qml·Qt6Quick·Qt6Pdf와 qpdf 플러그인도 포함됐다.

이 때문에 Qt 전체를 LGPL로만 표시하거나 QFluentWidgets 상용 계약 하나로 모든 라이선스 문제가 해결된다고 설명할 수 없다. 앱을 GPLv3로 배포하는 방향과 양립할 수 있지만 해당 모듈 및 포함된 제3자 코드의 고지·대응 소스 조건을 함께 정리해야 한다. 필요 없는 플러그인 제거는 기능 영향 검증을 거친 별도 빌드 변경으로 다룬다. 이번에는 제거하지 않았다.

근거: [Qt Virtual Keyboard 6.11.2](https://doc.qt.io/qt-6.11/qtvirtualkeyboard-index.html), [Qt의 LGPL/GPL 조건 안내](https://www.qt.io/development/open-source-lgpl-obligations).

### 3. 공공기관 여부만으로 상용 계약 필요를 결정할 수 없다

현재 문구는 `공공기관 납품 시 상용 라이선스 검토 필요`다. 확인해야 할 것은 실제 취득한 사용권, GPL 준수 배포 여부, 배포 범위와 계약 조건이다. 일반 GPLv3 자체는 유상 배포도 허용하므로 공모전 상금이나 공공기관 사용만을 근거로 자동 유료 라이선스 의무라고 단정하면 안 된다.

한편 QFluentWidgets의 **설치된 1.11.1 메타데이터 설명과 공식 안내에는 비상업 GPL/상업 별도 구매 표현이 함께 있다.** 따라서 이 모순을 숨기거나 상용 구매가 절대 불필요하다고 확약하지 않는다. 현재 설치 배포판의 GPLv3 전문·허락 근거와 적용 배포 범위를 보존하고, 필요한 경우 권리자에게 범위를 확인한다. 설정에는 우선 현재 앱이 따르는 GPLv3 경로를 사실대로 안내하고 미확정 법률 판단 문구를 넣지 않는 편이 적절하다.

근거: 설치 `pyside6_fluent_widgets-1.11.1.dist-info/METADATA`(License: GPLv3 및 License 절), [업스트림 GPL 전문](https://raw.githubusercontent.com/zhiyiYo/PyQt-Fluent-Widgets/PySide6/LICENSE), [공식 라이선스 안내](https://pyqt-fluent-widgets.readthedocs.io/en/latest/license.html), [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#DoesTheGPLAllowMoney).

### 4. 최신 고지와 출처 목록이 화면·문서에 따로 관리된다

`THIRD_PARTY_NOTICES.txt`에는 OCR 관련 항목이 추가돼 있지만 설정 요약에는 반영되지 않았다. 또한 범위 안내의 `2026-08-18`과 `AGENTS.md "Deferred Release Work"` 참조는 현재의 정본 위치 `docs/RELEASE_HISTORY.md` 및 최신 조사 범위와 맞춰야 한다. 기존의 날짜별 역사 기록 자체를 지우지는 않는다.

공휴일·음력은 `fetch_data.py`에서 공공데이터포털 특일·음양력 API를 통해 생성한다. 배포 고지에는 데이터 제공기관·서비스·적용 이용조건을 확인해 별도 출처로 기록하는 것이 좋다. 토마토 PNG, 앱 ICO/PNG와 자체 미니앱 SVG도 제작자·직접 제작/AI 생성 여부·원본 출처를 정리할 대상이다. 이번에 읽은 문서만으로 모든 이미지의 권리 근거를 확정하지 않았다.

HWP 변환은 한글/HWPX 변환기 엔진을 배포하지 않으므로 번들 오픈소스와 구별하여 **별도 설치 프로그램 안내**로 표시한다. 외부 프로그램의 이용·연동 조건 미확인은 `docs/DOCUMENT_CONVERSION.md`에도 남아 있다.

### 5. 공모전에서는 대응 소스 접근 범위가 달라질 수 있다

GPL 소스 제공은 무조건 전 세계 공개를 뜻하지 않는다. 선택한 배포 방식에 맞게 EXE 수령자가 대응 소스를 받을 수 있어야 한다. 기관 내부 GitLab의 Public 표시만으로 외부 심사자 접근이 보장되지는 않는다. 현재 원격 접속·외부 접근 테스트는 하지 않았다.

공모전 제출 EXE에 대응하는 앱 소스·리소스·모델·빌드 스크립트·lock·빌드 안내와 필요한 GPL/LGPL 구성요소의 대응 소스를 받을 방법을 정리한다. 루트 LICENSE 추가나 upstream 홈페이지 링크만으로 이 의무가 전부 끝났다고 판단하지 않는다. 저장소 전체를 무차별 압축하지 않고 현재 제출 버전의 추적 파일 범위를 검토하여 자료를 만든다. `archive/local-v3.5`, 내부 보안 자료, 비밀값, 사용자 DB/salt는 제출 범위가 아니다.

근거: [GPLv3 제1조·제6조](https://www.gnu.org/licenses/gpl.en.html), [GNU FAQ 소스 제공 범위](https://www.gnu.org/licenses/gpl-faq.en.html#DoesTheGPLRequireAvailabilityToPublic).

## 공모전 규정이 있어야 판단할 사항

1. 오픈소스·기존 공개작·기존 개발작의 출품 허용과 개발 기간 제한.
2. 수상작의 저작권 양도·독점 이용·비공개·재배포 제한 요구 및 제3자 구성요소 예외. 자체 창작 부분의 권리와 타인의 OSS 권리를 분리해야 한다.
3. 제출물이 시연 영상뿐인지, EXE·전체 소스까지 포함되는지와 심사자의 접근 환경.
4. 업무상 개발물에 대한 개인/기관의 출품·공개 권한. 소속 표시만으로 권리자를 확정하지 않는다.
5. AI 활용 공개 조건. OCR 모델을 직접 개발했다고 설명하지 않고 공개 모델을 이용한 오프라인 인식·표 복원·앱 통합이라는 자체 개발 범위를 구분한다. 코드/이미지 제작 과정의 AI 이용 신고도 공고 기준으로 확인한다.

공모전명이 없는 현재는 참가 가능 또는 불가능을 확정하지 않는다. GPLv3 소프트웨어라는 사실 자체가 공모전 출품을 일률적으로 금지하는 것은 아니다. 수상·제출 계약과 제3자 권리 조건의 대조가 필요하다.

## 권장 갱신 범위 — 아직 구현하지 않음

- **설정의 라이선스 전용 창**: 앱 이름/버전, GPLv3와 무보증·재배포 안내, 권리자, 정확한 대응 소스 위치를 요약하고 아래에서 구성요소별 이름/버전/라이선스/저작권/출처/원문을 읽을 수 있게 한다. 목록이 길어지므로 전용 열람 영역에 스크롤을 제공하고 설정 본체의 800×560 무스크롤 계약은 유지한다.
- **오프라인 원문 열람**: `app_paths.resource_root()` 기준으로 번들 텍스트를 읽는다. 라이선스 확인을 위해 외부 연결을 요구하지 않는다. 소스 URL은 텍스트·복사 기능으로 안내할 수 있다. 새로운 브라우저 열기를 넣는다면 현재 런타임 예외 계약도 별도 검토한다.
- **자료 정본 통일**: `LICENSE_TEXT`와 고지문이 서로 어긋나지 않게 구성요소 목록을 한 곳에서 관리한다. `screen_text/`를 걷어낸 빌드에서는 OCR 항목도 함께 빠지는 기존 선택형 계약을 유지한다.
- **고지·빌드 갱신**: 앱 LICENSE 접근, 누락된 구성요소 고지, 버전별 원문, 출처·모델 정보, Qt 모듈별 고지를 맞춘다. 필요 시 플러그인 포함 범위를 검토하되 기능 제거를 라이선스 정비에 몰래 섞지 않는다.
- **제출용 자료**: EXE와 일치하는 소스 제공 자료, 실제 번들 기준 구성요소 명세(SBOM), 제3자 고지/원문, 자체 기여와 외부 자산 출처표를 만든다. 파일 SHA-256과 제출 버전을 함께 기록한다.
- **예상 파일**: `ui_settings.py`, 공용 고지 목록/열람 모듈(필요 시), `licenses/*`, `screen_text/licenses/*`, `build.spec`, 관련 패키징/UI 테스트, README 및 정본 배포 기록. DB·암호화·기존 설정 키 변경은 필요 없다.
- **후속 검증**: UI 변경은 관련 quick와 합성 배율에서 원문 열람·복사·스크롤·작업 영역·잠금/닫기 수명 검사, 빌드 변경은 PowerShell release와 최종 EXE 고지/구성 재대조. 기술 검증 통과와 법률·공모전 적격 확인을 구분한다.

## 검증 증거

| 명령/범위 | 상태(통과·실패·미실행) | 실행 ID / 결과 경로 | 검사 입력·유의사항 |
|---|---|---|---|
| 소스·고지·빌드 구성 정적 대조 | 통과(증거 일치 검사 5개) | [정적 분석 summary](../../output/license-review/20261009-v3.9a/summary.md), [result.json](../../output/license-review/20261009-v3.9a/result.json) | 앱 실행 없음. 라이선스 준수 판정이 아닌 EXE·소스·고지 동일성 검사 |
| `.\.venv\Scripts\python.exe tools/verify.py quick --tests tests/test_packaging.py` | 통과: 75개, 실패·오류·skip 0 | `20261009-134320-274c20f873`, [summary.md](../../output/harness/20261009-134320-274c20f873/summary.md), [result.json](../../output/harness/20261009-134320-274c20f873/result.json) | 이번 실행의 실제 결과. 검사 후 런타임 코드 변경 없음. 기존 검사는 고지 파일/표식 등을 검사하며 누락된 모든 구성요소나 법적 준수를 보장하지 않음 |
| data/full/release 재실행 | 미실행 | 해당 없음 | 런타임·의존성·빌드 변경 없음. 과거 release 통과 수를 이번 통과 수로 사용하지 않음 |
| 실제 설정창·외부 심사자 소스 접근·공모전 규정·법적 권리 | 미실행 | 해당 없음 | 정적 분석으로 대체하지 않음 |

## 미해결과 인계

- 공모전 공고와 제출 범위 미확인.
- 변경한 정본 문서: 없음.
- 다음 행동: 공모전 공고 대조 후 위 범위의 고지·설정 UI·제출 자료 갱신. 기존 `docs/RELEASE_HISTORY.md`의 HOLD는 유지한다.
- 배포·커밋·push 여부: 수행하지 않음.
