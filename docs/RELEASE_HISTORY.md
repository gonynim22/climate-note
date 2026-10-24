# 릴리스 검증 이력과 보류 과제

이 파일은 기존 AGENTS.md의 검증 증빙·미해결 조사 기록을 2026-09-06에 이전한 것입니다. 과거 통과 결과는 현재 소스 검증을 대신하지 않습니다. 라이선스 보류 상태는 그대로 유지합니다.

## v4.4b 꼭 고칠 것: Win+D 가려짐·글자 따기 숨은 창·검사 도구 (2026-10-25)

- 바탕화면을 누른 뒤(바탕화면이 이미 활성) Win+D를 누르면 셸이 foreground 알림 없이 바탕화면만 올려 캘린더가 다음 Win+D까지 가려지던 문제를 고친다. 바탕화면이 활성인 동안 루트 데스크톱 창의 `EVENT_OBJECT_REORDER`에서 바탕화면이 감시 창을 덮었을 때만 기존 Win+D와 같은 pulse를 한다. 수정 전/후 실화면 기록(합성 데이터 소스 앱)에서 가려짐이 약 2.3초 → 0회다.
- 화면 글자 따기에서 영역 고르기 대기·선택 중 화면 구성이 바뀌면 오버레이만 조용히 닫혀 도구 창이 숨은 채 남던 문제(R17)를 고친다. 화면 변경 경로만 `hide_owned_popups(restore=True)`로 창을 바뀐 화면에 맞춰 다시 보인다.
- 검사 도구: 입력 변경 감지를 저장소 파일 전체(기록·홍보·비공개 제외)로 넓혀 OCR 모델·fixture·고지 JSON을 포함하고(319→371개), 기존 데이터 seed에 시각+알림·기간·반복 일정을 넣어 값으로 비교하며, release가 빌드 직후 BINARY 출처와 EXE 안 Qt DLL 원본 일치를 자동 검사한다([교차검증](work/2026-10-19-a-report-crosscheck.md) F1·F2·F4).
- 앱 아이콘을 사용자가 만든 새 디자인(흰 둥근 사각·청록 궤도·대륙 지구·올리브 잎가지, `icon/climate_note_style16_continents_final.svg`)으로 바꿨다. 파일 이름은 그대로이며 EXE 아이콘은 9크기, 트레이 아이콘은 7크기를 담아 작은 크기에서도 축소로 흐려지지 않는다(이전에는 각 1크기).
- 표시 버전/출시일 `v4.4b` / `2026. 10. 25.`, EXE `기후노트_v4.4b.exe`, Windows `4.4.2.0`. DB v18·Export v3·salt·설정 키·의존성은 유지한다. 검증·실화면 기록·남은 후속은 [작업 기록](work/2026-10-24-v4.4b-must-fixes.md)을 따른다.
- 검증·배치: full `20261025-001625-9550d6de48` 3,031개, PowerShell release `20261025-003507-a06b277eff`의 3,031개·새 빌드·EXE 구성 자동 검사(BINARY 64·검증 환경 밖 0·Qt DLL 15 원본 일치)·격리 실행 4개(기존 데이터에 일정 세부 설정 포함) 통과. 포함 목록은 v4.4a와 같고(1,018개) 크기 +2,584 bytes. `dist/기후노트_v4.4b.exe` 94,195,077 bytes, SHA-256 `348A3BCFEEBEFA9A58A4006BD58FF39CD6AB6FA7ED7B3DACABA778479FF22922`, 서명 `NotSigned`. 1차 release `20261025-002514-2948a33121`은 무관한 팝업 시험 1개 실패(검사 중 포커스 이동, 빌드 전 중단)로 폐기했다.

## v4.4a 바탕화면 클릭 깜빡임 수정 (2026-10-24)

- '바탕화면 고정'이 켜져 있을 때 다른 창이 캘린더 위에 있는 상태로 바탕화면을 누르면 그 창이 잠깐 사라졌다가 다시 나타나던 문제를 고친다. 바탕화면 클릭도 Win+D와 같은 바탕화면 활성화 알림을 내므로 `ShowDesktopKeeper`가 350ms topmost pulse를 했다. v3.4 데스크톱 레이어 도입 때부터 있던 동작이다.
- 알림 순간 마우스 버튼이 바탕화면 위에서 눌려 있으면 pulse하지 않는다. Win+D·'바탕화면 보기' 버튼은 알림 뒤 7~250ms에 바탕화면을 올리므로 기존 pulse를 유지한다(알림 시점 '덮임' 판단은 실화면에서 Win+D 보호를 깨뜨려 폐기).
- 표시 버전/출시일 `v4.4a` / `2026. 10. 24.`, EXE `기후노트_v4.4a.exe`, Windows `4.4.1.0`. DB v18·Export v3·salt·설정 키·의존성은 유지한다. push 전 로컬 OSV 1건(Low)으로 EXE 미포함 `setuptools`만 84.1.0으로 올렸다. PowerShell release `20261024-215637-302c493969` 3,014개·빌드·격리 실행 4개 통과, EXE 94,192,493 bytes, SHA-256 `D4CC9E7D…`. 검증·실화면 기록·남은 후속은 [작업 기록](work/2026-10-24-desktop-click-flicker.md)을 따른다.

## v4.4 파일 변환 확장·D안 (2026-10-20)

- 네 번째 미니앱을 파일 변환으로 넓혀 사진 상호 변환·작은 JPG·ICO·PDF 묶기, PDF 쪽별 PNG/JPG, CSV/TXT 인코딩 변환을 제공한다. D안 파일 넣기 → 추천 → 결과 비교와 창 안 관계도를 적용한다.
- 기존 HWP 엔진/Job 계약, DB v18·Export v3·salt·설정 키·바로가기 6슬롯·의존성을 유지한다. 새 파일 변환은 별도 Job의 일괄 프로세스와 부모 비덮어쓰기 확정을 사용한다.
- 표시 버전 `v4.4`, 출시일 `2026. 10. 20.`, EXE `기후노트_v4.4.exe`, Windows `4.4.0.0`. 검증/실패 이력·새 EXE·수동 미확인·게시 여부는 [작업 기록](work/2026-10-20-file-converter-redesign.md)을 따른다. 아래 v4.3 검사 수와 해시는 이번 구현의 통과 근거가 아니다.
- 같은 v4.4에 공휴일 데이터 최신화·만료 안내([작업 기록](work/2026-10-20-holiday-data-refresh.md))를 포함했다. push 보안 검사 대응으로 EXE 미포함 pillow를 13.0.0으로 올렸고, 같은 날 스티키 체크박스 간격 수정(체크 시 취소선이 상자에 붙어 보임)도 더했다. 배포 EXE는 이 모두를 담아 2026-10-21에 다시 빌드한 것(SHA-256 `BEEB3C4D…`)이며 검증은 [최종 빌드 기록](work/2026-10-21-v4.4-release.md)을 따른다.

## v4.3 교차검증 우선 수정 (2026-10-18)

- 스티키 저장 실패 표시·크기 전환 보류, 반복 경계·조기 종료·손상 행 표시 fallback, PIN 검증값·입력 대기·긴 이동 파일 암호, OCR 자원 상한·취소, 환산 조건·위젯 표시 상한을 보완한다.
- 표시 버전 `v4.3`, EXE 이름 `기후노트_v4.3.exe`, Windows `4.3.0.0`. DB v18·Export v3·본문 암호문·salt·의존성을 유지한다. `privacy_pin` 값은 보호백업 후 검증값으로 바뀌며 새 긴 암호 파일과 잠금 검증에는 v4.3 이상이 필요하다.
- 구현 `de979bb` 기준 PowerShell release `20261018-222736-af0ec7a31a`에서 **2,857개 검사·새 EXE·격리 실행 4개 시나리오** 통과. 검사 중 입력 불변, Qt DLL 15개 환경/v4.2 동일, BINARY 64개에 Git mingw 혼입 없음. `dist/기후노트_v4.3.exe` **94,140,392 bytes**, SHA-256 **`130F80C2E3D1E40C4A016AC6E99D0049FA1FF7FCE0932F5B7E92D3A51FA95721`**, Windows `4.3.0.0`, 서명 `NotSigned`. v4.2 대비 +8,831 bytes(+0.0094%).
- 구현 main push와 서버 Gitleaks·Semgrep·OSV-Scanner·Trivy·Syft 검사 통과. GitLab Release 게시는 사용자가 수행한다. 실제 UI·혼합 DPI/KVM/Win+D 등 수동 미확인과 이전 실패 이력은 [작업 기록](work/2026-10-18-v4.3-priority-fixes.md)에 구분한다.

## v4.2 일정 세부 설정 카드 리디자인 (2026-10-18)

- 폭 320px의 Azure 머리띠·한 줄 선택 바·아이콘 라벨, 알림 시각 설명·짧은 기간 문구·연결된 달력 띠. 시계 버튼·알약·목록·알림 카드와 기존 저장/수명 동작은 유지한다.
- DB v18·Export v3·설정 키·salt·저장값 변경 없음. 표시 버전 `v4.2`, EXE `기후노트_v4.2.exe`, Windows 버전 `4.2.0.0`.
- 검증·배치: 100/125/150% quick 각 323개, PowerShell release `20261018-004151-9317903930`의 2,828개 테스트·새 빌드·격리 EXE 4개(fresh/existing/blocked/upgrade) 통과. 빌드 입력 `f6f5371`. Qt DLL 15개가 환경/이전 v4.1과 동일하고 Git mingw DLL 혼입은 없다. `dist/기후노트_v4.2.exe` 94,131,561 bytes, SHA-256 `6A6914E0DEA4BEE1CC5D84608675F40C33EA7FE35CAD1BA1DD230CC05CD0C440`.
- 구현 `330cd34`·버전 테스트 갱신 `f6f5371`은 `git push origin main` 완료, 서버 Gitleaks/Semgrep/OSV-Scanner/Trivy/Syft 검사 통과. 첫 release의 이전 버전 기대값 실패와 수동 미확인 범위는 [작업 기록](work/2026-10-18-schedule-options-card-redesign.md)에 구분한다. GitLab Release는 사용자가 게시하며 이번 작업에서는 생성하지 않았다.

## v4.1 일정 시각·알림·반복·기간 (2026-10-17)

- 일정에 시작 시각·여러 날 기간·반복(매일·평일·매주·매월·매년, 끝 날짜·이 날만 삭제)·앱 안 알림을 더한다. 시안 `output/design/schedule-features-20261015/index.html`(로컬 시안, Git 제외), 설계 `docs/superpowers/specs/2026-10-16-schedule-time-repeat-period-design.md`.
- DB v18은 일정 표에 열 6개만 한 트랜잭션으로 더하고 기존 값은 바꾸지 않는다. Export v3, 새 설정 키 `schedule_alarm_seen_at`(Export 제외). v4.0a 이하 EXE는 v18 데이터를 보면 데이터를 바꾸지 않고 '데이터 보호를 위해 실행을 중단했습니다'(구조 또는 무결성 확인 실패 문구) 창으로 시작을 멈춘다. 이 문구는 바꿀 수 없으므로 v4.1은 예전 형식 DB를 올린 실행에서 한 번 '기후노트 업데이트 안내' 창으로 미리 알린다. 되돌리려면 `backups/calendar_pre_v18_v17.db`를 쓴다(그 뒤 입력분 제외, 절차는 README_detail).
- 표시 버전 `v4.1`, EXE `기후노트_v4.1.exe`, Windows `4.1.0.0`. 검증·빌드 결과는 [작업 기록](work/2026-10-16-v4.1-schedule-time-repeat-period.md)을 따른다.
- 검증·배치: full `20261017-122828-e65b6630d7` 2,802개·100/125/150% quick `20261017-123419-3d913ab1d6`·`20261017-123528-84933a2a25`·`20261017-123637-d88f9586be` 각 357개(앱 코드 기준 `bea1e87`), PowerShell release `20261017-124725-10b03e7f88` 2,802개·새 빌드·격리 실행 4개(fresh·existing·blocked·upgrade, 기준 `25496b1`) 통과. 실제 v4.0a EXE 업그레이드·구버전 차단·되돌리기 리허설 통과. `dist/기후노트_v4.1.exe` 94,126,398 bytes, SHA-256 `2B1859EAC61A692790E77AB813219AACAE25AF7F770A0F6A615F095402DA5535`.

## v4.0a 백업 검증 임시 짝 파일 누적 수정 (2026-10-15)

- v3.5부터 백업 검증용 임시 DB의 `-wal`/`-shm`이 데이터 폴더와 `backups\`에 무제한으로 쌓이던 결함을 고친다. 백업 사본이 원본의 WAL 머리값을 물려받아, 읽기 전용 검증 연결이 짝 파일을 만들고 지우지 못한 것이 원인이다. 5일 보존 규칙은 `.cnbak`에만 적용되어 이 파일들은 정리되지 않았다(합성 재현: 하루 2회 시작 10일에 230개·3.7MB).
- 임시 사본을 지울 때 짝 파일도 함께 지우고, 시작 시 이전 버전이 남긴 짝 파일을 이름 패턴·짝 `.db` 부재·빈 `-wal` 조건으로만 정리한다. 사용자는 EXE만 교체하면 첫 실행에서 정리된다. 정상 `calendar.db-wal/-shm`을 잘못 지우면 최근 저장분을 잃을 수 있으므로 수동 삭제는 안내하지 않는다.
- 표시 버전/출시일 `v4.0a` / `2026. 10. 15.`, EXE `기후노트_v4.0a.exe`, Windows File/Product Version `4.0.1.0`. DB v17·Export v2·암호화·salt·백업 묶음 형식·설정 키·의존성은 유지한다. 검증·빌드 결과는 [작업 기록](work/2026-10-15-backup-sidecar-cleanup.md)을 따른다.

## v4.0 표 구성 개선·버전 갱신 (2026-10-11)

- 최초 소형 OCR 모델·사전을 유지하면서 표의 행·열 배치와 여러 줄 셀의 읽기 순서를 개선한다. 글자 인식 모델의 정확도 향상을 주장하지 않으며 추가 학습은 보류한다. 앞서 `main`에 반영한 미니앱 공용 창 틀·캘린더 위치 편집·바로가기 기본값 개선도 포함한다.
- 표시 버전/출시일 `v4.0` / `2026. 10. 11.`, EXE `기후노트_v4.0.exe`, Windows File/Product Version `4.0.0.0`. DB v17·Export v2·암호화·salt·설정 키·의존성·기존 모델은 유지한다.
- 전체 검사·새 빌드·격리 실행·번들 대조·로컬 배치·커밋·push의 실제 결과는 [v4.0 작업 기록](work/2026-10-11-v4.0-release.md)에 남긴다. GitLab Release 업로드와 실제 업무 PC 수동 확인·라이선스 보류 과제는 별도다.

## v3.9a 화면 글자 따기 표 구성 개선 (2026-10-11, 버전 유지)

- 병합 라벨 때문에 숫자 행이 합쳐지거나 여러 줄 셀의 읽기 순서가 뒤섞이는 문제를 줄인다. 기존 소형 OCR 모델·사전·MANIFEST·의존성·DB/설정은 유지한다. 추가 학습 후보는 품질 실패로 미채택하고 사용자 결정에 따라 학습을 보류한다.
- [표 구성 검증](work/2026-10-11-screen-text-table-layout.md)과 [현재 EXE 빌드/검증 기록](work/2026-10-11-screen-text-table-build.md)을 구분한다. 개발 표본에서의 표 배치 개선을 글자 인식 모델의 정확도 개선으로 표현하지 않는다. 외부 게시·push와 기존 수동 검사/라이선스 보류는 별도다.

## v3.9a 라이선스 안내·고지 정비 (2026-10-09, 버전 유지)

- 설정의 별도 원문 열람 창, 기본 19개+선택형 OCR 3개 목록, HWP 지정 문구, PaddleOCR 원저작권/출처, Python 구성요소 및 Qt 하위 고지를 보강했다. 기능 로직·DB v17·Export v2·salt·설정·모델/사전·Qt/lock은 유지했다.
- PowerShell `release` **20261009-183942-21246a4373**에서 **1,816개 테스트·새 빌드·격리 EXE 3개 시나리오**를 통과했다. 125/150% quick는 각 82개 통과했고 실제 EXE에서 설정 → 라이선스 → GPL/OCR 원문 → 닫기를 추가 확인했다. 라이선스 조작 전후 합성 데이터 raw/평문/ID/salt가 동일했다.
- 최종 `dist/기후노트_v3.9a.exe`: **94,012,479 bytes**, Windows **3.9.1.0**, SHA-256 **`3C80DBB06028A035EAADD866A21940D5AA95143E6CF61B5A2907E4DD92B6A41A`**. 이전 사용법 안내 빌드와 표시 버전이 같으므로 해시로 구분한다. 이전 `ED4BBD6B…0FDF` 파일은 `output/harness/20261009-132546-f2aab9b4b1/dist/`에 보존했다.
- 고지/목록 39개가 소스와 일치하고 모델·사전·Qt/네이티브 DLL·폰트·아이콘 등 160개 파일은 이전 EXE와 동일하다. mingw 혼입 없음. 전체 SBOM·대응 소스 전달·기관/자산/공모전 조건·서명은 별도 보류다. GitLab Release 게시는 별도이며 사용자 후속 요청으로 AGENTS 갱신·소스 커밋·main push를 진행한다. 실패한 보조 검사와 최종 검증을 구분한 [작업 기록](work/2026-10-09-license-notices-update.md)을 따른다.

## v3.8b 날짜·시간 계산기 스크롤 제거 (2026-09-24 후속)

- A안의 크기를 유지하며 시작/종료 날짜를 두 열로 배치하고 입력 폼 스크롤을 제거했다. 시간 합산은 이전/다음으로 한 항목씩 편집하며 숨긴 항목을 포함한 전체 결과를 표시한다. 낮은 화면은 여백과 보조 안내를 압축한다.
- v3.8b·계산 엔진·최대 24개 합산·최근 12개·DB/Export/salt/설정 계약을 유지한다. 현재 검사·새 EXE·커밋·수동 미확인은 [스크롤 제거 기록](work/2026-09-24-date-time-no-scroll.md)을 따른다. 아래 최초 구현 결과는 이번 UI 수정 전 기록이다.

## v3.8b 날짜·시간 계산기 (2026-09-24)

- A안 날짜·시간 계산기를 두 번째 미니앱으로 추가한다. 시간 차이·달력 연산·근무일·기간/구간 합산을 제공하고 정수 초 원본과 총 분 표시, 수동 휴게, 월말 보정, 공휴일 자료 범위를 구분한다.
- 표시 버전 v3.8b, Windows 3.8.2.0, EXE `기후노트_v3.8b.exe`. DB v17·Export v2·salt·기존 설정/바로가기·Qt/lock을 유지한다. 입력과 기록은 메모리 전용이다. 현재 검사·새 EXE·커밋·수동 미확인은 [v3.8b 기록](work/2026-09-24-v3.8b-date-time-calculator.md)을 따른다.

## v3.8a 조건을 반영하는 단위 환산 (2026-09-24)

- 25분류·182항목. 수질 ppm/ppb↔질량 농도는 용액 밀도, 기체 몰분율↔mg/m³·µg/m³는 물질의 몰질량/온도/절대압을 명시적으로 사용한다. 온도값/온도차를 구분하고 전체 기준 설명을 접어 읽도록 정리했다. 조건은 최근 12개와 함께 메모리에만 보존한다.
- 표시 버전 v3.8a, Windows 버전 3.8.1.0, EXE `기후노트_v3.8a.exe`. DB v17·Export v2·salt·기존 본문/설정/바로가기·Qt 6.11.2·lock을 유지한다. 실제 검사·산출물·커밋·수동 미확인은 [v3.8a 기록](work/2026-09-23-v3.8a-water-conversion-plan.md)을 따른다.

## v3.8 환산기 그림자·분류 가독성 (2026-09-23 후속)

- 실행된 환산기에도 부드러운 그림자를 적용했다. 내용 440×580px를 유지하고 기본 외곽 488×628px로 표시하며, 좁은 작업 영역에서는 내용 최소 너비에 맞춰 그림자 여백/blur를 줄인다.
- 분류 목록은 132px 폭, 28px 행/0px 간격, 이름 13px/기호 12px로 가독성을 높였다. 계산·최근 기록·DB v17·Export v2·salt·기존 설정·의존성·v3.8을 유지한다. 이번 검증·EXE·커밋·수동 미확인은 [그림자·가독성 기록](work/2026-09-23-unit-converter-shadow.md)을 따른다.

## v3.8 미니앱 주머니 구분감·작은 타일 (2026-09-23)

- 그림자와 옅은 파랑 제목 영역을 추가하고 본체를 240×280px(그림자 포함 288×328px)로 줄였다. 92×92px 타일 4개를 2×2로 배치하며 환산기는 번들 생성 이미지를, 예정 타일 3개는 비활성 `곧 출시 예정` 안내를 표시한다.
- 버전·DB v17·Export v2·salt·기존 바로가기/설정·환산기 계산/최근 기록·의존성은 유지한다. 이번 검증·빌드·산출물·커밋·수동 미확인은 [주머니 개선 기록](work/2026-09-23-mini-app-pocket-redesign.md)을 따른다. 이전 주머니 크기와 당시 통과 결과는 아래에 보존한다.

## v3.8 미니앱 타일·환산기 확대·환경 단위 (2026-09-21)

- 주머니를 332px 정사각형, 앱 항목을 132px 정사각형 타일의 2열 격자로 변경했다. 항목이 늘면 목록만 스크롤한다. 환산기는 440×580px로 확대하고 숫자/단위 선택/분류 글자를 함께 키웠다.
- 기체 농도(몰분율 ppm·ppb·ppt·%), 질량비(ppm·mg/kg), 수질 농도(mg/L 등), 유량을 추가해 25분류·178항목을 제공한다. 밀도/분자량/온도/압력이 필요한 서로 다른 기준의 환산은 추정하지 않는다.
- v3.8/3.8.0.0·DB v17·Export v2·salt·설정·기존 사용자 바로가기·의존성은 유지한다. 이번 검증·새 EXE·커밋은 [확대·환경 단위 기록](work/2026-09-21-mini-app-environment.md)을 따른다. 아래 최초 v3.8 결과는 이번 수정 전 기록이다.

## v3.8 단위 환산기 (2026-09-21)

- 미니앱 주머니의 실행 카드에서 21분류·147항목 단위 환산기를 연다. 별도 창 1개, 원본 디자인의 어두운 분류 목록과 결과 카드, 입력 검증·단위 교환·실행 중 최근 12개 기록을 제공한다. 추정 환산은 제외하며 계수 정의/출처는 [단위 계약](UNIT_CONVERSION.md)을 따른다.
- DB v17·Export v2·암호화·salt·기존 설정/바로가기·의존성 유지. 표시 버전 v3.8, Windows 3.8.0.0, EXE `기후노트_v3.8.exe`. 소스와 신규 EXE의 실제 검증·해시·커밋·수동 미확인은 [구현 기록](work/2026-09-20-v3.8-unit-converter.md)을 따른다. 기존 v3.7b 산출물을 보존한다.

## v3.7b 미니앱 버튼·빈 주머니 (2026-09-20)

- 80px 사이드바 최상단에 64×48px 미니앱 버튼을 추가하고 기존 바로가기 6개를 아래로 배치했다. 기본 높이에서는 전부 표시하고 짧은 화면에서는 목록만 스크롤한다. 주머니는 제목/닫기/빈 안내를 표시하며 단위 환산기 기능은 아직 없다. 기존 6개 ID/이름/경로/관리·드롭, DB v17·Export v2·salt·암호화·설정 키·의존성·v3.7b/3.7.2.0을 유지한다.
- 소스·AGENTS 커밋 `bb95ccc` 후 `release` **20260920-231715-72ee145267**에서 **798개 테스트·새 EXE·격리 3개 시나리오**를 통과했다. 검사 전후 입력 불변, 실제 미니앱 코드/apps.svg/Qt 6.11.2 DLL 대조 후 `dist/기후노트_v3.7b.exe`로 배치했다. **57,951,181 bytes**, SHA-256 **`460D0C42BF0CE4A329CB971C744AEAAEF2C2BE04A82594BF0589888099BFEDA4`**. 기존 EXE 보호본과 세부 증빙은 [미니앱 작업 기록](work/2026-09-20-mini-app-pocket.md)을 따른다.
- 관련 quick 314개와 native 팝업 대기 보강 후 quick 141개, 125%/150% 합성 배율 각 79개 통과 및 소스 Qt 렌더 확인. 실제 혼합 DPI/KVM/Win+D/IME·정상 종료 수동 확인·Defender·서명·GitLab push/게시는 미실행이다.

## v3.7b 캘린더 이동 토글·테두리 스마일 (2026-09-20)

- 검색과 더보기 사이 A안 이동 토글로 기본/중간/크게의 수동 드래그를 제어한다. 새 `calendar_move_enabled` 키는 기본 ON fallback, 명시적 토글 때 저장하며 재시작/크기 전환/Export·Import에 유지한다. 일정 이모지 버튼은 색상 원과 외경 22px를 공유하는 벡터 스마일로 바꾸고 26px 클릭 영역·선택/Undo·본문 저장을 유지한다.
- 소스·AGENTS 커밋 `5cd3e38` 후 `release` **20260920-222103-a3b365cc44**에서 **775개 테스트·새 EXE·격리 3개 시나리오**를 통과했다. 검사 전후 입력 불변, Qt 6.11.2 DLL/수정 모듈 대조 후 `dist/기후노트_v3.7b.exe`로 배치했다. **57,944,043 bytes**, SHA-256 **`E69D477E24B579BC68D7757183394AE5A5AB6197A786E78412A9893EF811F49D`**. [현재 작업 기록](work/2026-09-20-calendar-move-toggle.md).
- 관련 quick 166개와 125%/150% 합성 배율 각 78개를 통과했고 소스 Qt 렌더를 확인했다. v3.7b/3.7.2.0·DB v17·Export v2·salt·기존 본문·의존성 유지. 실제 혼합 DPI/KVM/Win+D/한글 IME와 GitLab 게시/push는 별도 미실행이다.

## v3.7b 스티키 파일 링크 (2026-09-20)

- **B+C 파일 라벨과 간격 개선**: 옅은 둥근 라벨·확장자 배지·끊김 점선/주의 표시·툴바 테두리의 [최초 구현](work/2026-09-20-sticky-file-labels.md) 후, 배지 글꼴/채움을 줄이고 정상 링크 뒤 16px 빈 경고 공간을 2px 간격으로 축소했다. 경고 공간은 필요한 상태에서만 표시 배치로 갱신하며 본문·revision·Undo·IME preedit를 보존한다. 버전 v3.7b/3.7.2.0·DB v17·Export v2·기존 HTML/href·salt·의존성을 유지한다.
- **당시 빌드/배치**: AGENTS.md와 소스를 `085fd78`로 커밋한 뒤 `release` **20260920-205858-837fd234ab**에서 **755개 테스트·새 EXE·격리 시나리오 3개**를 통과했다. 검사 전후 입력 불변, 실제 Qt 6.11.2 DLL/체인 SVG/라벨 모듈 대조 후 `dist/기후노트_v3.7b.exe`로 배치했다. **57,939,983 bytes**, SHA-256 **`3BEE70A22C92656EE25E681725C7C33DCAA297D13ACF18B3B5849AA572282B19`**. [간격 개선 기록](work/2026-09-20-sticky-link-spacing-fix.md). 아래 723개 테스트 EXE는 B+C 적용 전의 이전 산출물이다.
- **이전 후속 수정**: 연결 버튼을 새 창 화살표에서 체인 SVG로 교체하고, 파일창에 연결할 선택 문구를 표시했다. 실제 양방향 드래그→두 보기 버튼→파일창 수락/취소에서 파일명으로 대체되지 않는 것을 확인했다. `release` **20260920-124000-f584ef3ff4**에서 **723개 테스트·새 EXE·3개 격리 시나리오**가 통과했다. [수정/재빌드 기록](work/2026-09-20-sticky-link-selection-fix.md).
- **이전 커밋 후 빌드**: AGENTS.md와 수정 소스를 `c72351f`로 커밋한 뒤 `release` **20260920-124614-fdedd0671c**에서 **723개 테스트·새 EXE·3개 격리 시나리오**를 다시 통과했다. 검사 전후 입력/커밋 ID 일치, 실제 체인 SVG/Qt DLL 대조 완료.
- **이전 dist 배치 기록**: `기후노트_v3.7b_링크수정.exe` **57,932,513 bytes**, SHA-256 `7F66DEA83EF2BF71FCF23937250E5F9E1EA4CBB52A7BF2D8044E18EE5E888F08`. 당시 기존 표준 이름 EXE는 파일 잠금으로 교체가 차단되어 별도 파일로 배치했다. 버전·DB·salt·의존성 유지, 게시/push 미수행.
- **커밋 전 산출물 보존**: `기후노트_v3.7b.exe` **57,931,806 bytes**, SHA-256 `F180AFA43396DF7A555E22AE42812000C8DBE03BF4FFD0DE8AD47EEE6DBB0CE9`. 기존 경로와 `dist/previous-v3.7b-20260920-124000/`에 보관했다. 아래 최초 v3.7b도 `dist/previous-v3.7b-20260920-123004/`에 보관했다.

- 후속 빌드 요청으로 `release` 실행 `20260920-123004-b4d09d59a8`에서 **717개 테스트·격리 EXE 3개 시나리오**를 통과했다. 실제 포함 Qt DLL 3개가 검증 venv의 `6.11.2.0`과 바이트/해시 일치하고 파일 링크 모듈이 PYZ에 포함됨을 확인했다. [빌드 기록](work/2026-09-20-v3.7b-build.md)에 결과를 남긴다.
- 검증한 `dist/기후노트_v3.7b.exe`: **57,930,902 bytes**, SHA-256 `A23C4A59D0AFBBBD6369E2DACA1AFBFE1FD6E016A9FE6CC86CC3A243222937E9`, Windows `3.7.2.0`, 서명 `NotSigned`. 기존 v3.7a EXE는 그대로 보존했다. GitLab 게시/push와 실제 UI·IME·PC 이동·혼합 DPI/KVM은 미확인/미수행이다.

- 플로팅/large 미니 패널에서 선택 문구·파일명에 로컬 파일을 연결한다. 파란 밑줄과 화면 전용 주의 표시, Ctrl+클릭 열기, 다시 연결/해제, 파일 드롭을 제공한다. 다른 PC의 같은 경로를 자동으로 열지 않으며 재선택한 연결만 갱신한다.
- 기존 HTML anchor에 연결 정보를 담고 기존 암호화/백업 경로를 사용한다. DB v17·Export v2·salt·키 유도·기존 설정·의존성은 유지한다. Export는 현재 편집 저장 성공 후 snapshot을 읽는다.
- `app_info.py`: `v3.7b` / `2026. 9. 20.`, 향후 EXE `기후노트_v3.7b.exe`, Windows File/Product Version `3.7.2.0`. [구현 기록](work/2026-09-20-sticky-file-links.md)에 현재 입력의 검증 결과와 남은 수동 확인을 기록한다.
- 최초 구현 작업은 소스·버전·로컬 커밋 범위였으며 EXE 빌드는 위 후속 검증으로 갱신한다. GitLab push/Release 게시·실제 한글 IME/탐색기 드롭/기본 프로그램/혼합 DPI/KVM 검증은 수행하지 않았다. 이전 v3.7a 산출물 해시·통과 수는 v3.7b 결과가 아니다. 기존 보안 회신·취약점·라이선스/SBOM/서명 보류 유지.

## v3.7 캘린더 요일 열 너비 수정 검증 (2026-09-11)

- 세로 화면에서 일정 칩의 말줄임 결과가 열 최소 너비로 되먹임되어 금·토가 좁아지는 문제를 수정했다. 칩의 가로 sizeHint를 열 너비 계산에서 제외하고 날짜/요일 제목 그리드 7열에 동일한 stretch를 적용한다. 앱 v3.7·DB v17·Export v2·Qt 6.11.2·암호화·salt·저장 경로·설정 키를 유지한다.
- `release` 실행 `20260911-210624-06a98aabf3`: 전체 pytest **663건 통과**, 새 EXE 빌드 및 신규 설치·기존 합성 데이터 보존·손상 salt 시작 차단 **3개 시나리오 통과**. 실행 전후 검사 입력은 동일하다. 기존 합성 데이터의 8개 테이블 raw/복호화 내용·ID·salt 해시가 유지됐다.
- 신규 `기후노트_v3.7.exe`: **57,907,537 bytes**, SHA-256 `0A3A85C1E082A81CEFE742FE63BDE642427D0A389ACE11D4309277ACACB2F379`, File/Product Version `3.7.0.0`, Authenticode `NotSigned`. 로컬 사용용 복사본은 `dist/calendar-column-fix-20260911/`에 두고 기존 EXE는 보존했다.
- 열 너비·말줄임·데이터 보존 회귀와 합성 배율별 결과는 [요일 열 너비 수정 기록](work/2026-09-11-calendar-column-width-fix.md)을 본다. 실제 회사 PC 혼합 DPI/KVM·정상 종료 수동 확인·Defender·GitLab Release 게시 및 기존 라이선스/SBOM/서명 과제는 별도 미완료다. 검증 뒤 변경한 README와 이 이력은 결과·링크만 갱신하며 런타임 코드와 빌드 입력은 유지한다.

## v3.7 컬러 이모지 수정 검증 (2026-09-10)

- Windows Qt 6.10.2 글리프 캐시에서 스마일·다트 등의 우측·하단 한 픽셀 누락을 재현했다. Qt/PySide6·Addons·Essentials·shiboken6만 6.11.2로 갱신했으며 lock과 제3자 고지를 함께 반영했다. 앱 v3.7·DB v17·본문 Unicode·암호화·설정·salt 계약은 유지한다.
- `release` 실행 `20260910-205636-204363fb6e`: 전체 pytest **655건 통과**, EXE 빌드와 신규 설치·기존 합성 데이터 보존·손상 salt 시작 차단의 격리 실행 **3개 시나리오 통과**. 실행 전후 입력 해시가 동일하다. 125%·150%의 관련 `quick` 검사도 각각 **68건 통과**했다.
- 신규 `기후노트_v3.7.exe`: **57,907,537 bytes**, SHA-256 `9677998585F0507D6219BE61EEDD80C75046A76A84A65A05A60520F6F6B26810`, File/Product Version `3.7.0.0`, Authenticode `NotSigned`. 로컬 사용용 복사본은 `dist/emoji-fix-20260910/`에 두었고 기존 EXE·사용자 캡처는 보존했다.
- 명령·보고서·검사 입력·합성 렌더 확인은 [글리프 잘림 작업 기록](work/2026-09-10-schedule-emoji-glyph-clipping.md)에 남긴다. 실제 듀얼 모니터·혼합 DPI/KVM·정상 종료 수동 확인·Defender·GitLab Release 게시와 기존 라이선스/SBOM/서명 과제는 미완료다.

## v3.7 소스 업데이트 (2026-09-09)

- 표시 버전·출시일은 `app_info.py`의 `v3.7` / `2026. 9. 9.`로 변경했다. 빌드 시 EXE 이름은 `기후노트_v3.7.exe`, Windows 숫자 버전은 `3.7.0.0`이 된다.
- 가져오기 전 최신 스티키 저장을 확정하고 기존 편집기·집중 타이머를 재사용한다. large 패널에는 가져온 메모 목록을 반영한다.
- 초기화 보호백업 이후 이전 플로팅·패널의 타이머와 가드 참조를 폐기해, 재사용된 ID의 새 데이터에 오래된 객체가 쓰지 않게 한다.
- PIN 잠금 중 트레이 복원·보조 창·예약된 위젯 표시를 차단하고 활성 모달/팝업을 취소한다. 집중 자동 완료는 기록하되 휴식 팝업을 열지 않는다.
- **DB 스키마 v17, 암호화 방식, `.salt`, 저장 경로와 기존 설정 키는 유지한다.** 버전 업데이트를 위한 데이터 초기화·일괄 변환은 없다. `database.py`와 `security.py`는 수정하지 않았다.
- 자동 검증의 실제 실행 ID·결과·입력 해시는 [v3.7 작업 기록](work/2026-09-09-v3.7-version-commit.md)에 남긴다. [수정 작업 기록](work/2026-09-08-data-lifecycle-privacy-fix.md)의 검증은 버전 변경 전 근거다.
- 이 기록 시점에는 v3.7 EXE 빌드·격리 실행·Defender 검사·GitLab 태그/Release/업로드가 미실행이었다. 이후 로컬 빌드·격리 검증은 위 2026-09-10 기록을 본다. 실제 Windows 잠금/절전·Win+D·혼합 DPI/KVM과 기존 보류 과제는 완료 처리하지 않는다.
- [사용성 점검](work/2026-09-08-usage-review.md)의 편집 직후 Export(R4), 집중 수동 종료 기록(R6), large 스티키 상한(R7)은 별도 후속 과제다.

## v3.6b 및 이전 상태 기록

App display name: **기후노트** | Internal path: `MyDesktopCalendar` | Version: **v3.6b** (2026.8.22)

> 🛠️ **v3.6b 개발 빌드 완료(2026-08-22).** 하단 일정 행을 우클릭하면 불투명 `RoundMenu`에 `편집`·`삭제`가 표시된다. 기존 오른쪽 휴지통 버튼과 더블클릭 인라인 편집은 그대로 유지하며, 메뉴 액션도 기존 `_on_edit_schedule()`·`_on_delete_schedule()` 경로를 재사용한다. DB 스키마·암호화·일정 저장 형식은 변경하지 않았다. 전체 테스트 536건을 통과했다. 로컬 빌드 `dist/기후노트_v3.6b.exe`는 58,280,125 bytes, SHA-256 `08B9FCC2493B97D8C61746E4DBBE427D73C4C108C33995A87C4D7077BB472BDA`, File/Product Version `3.6.2.0`, Authenticode `NotSigned`다. GitLab 태그·Release 생성과 EXE 업로드는 아직 하지 않았다.

> ✅ **v3.6 산출물 검증 완료(2026-08-18).** 앱 런타임 코드는 v3.5와 동일하며, 변경분은 표시 버전·제3자 라이선스 고지·저장소 정비다. 전체 테스트 518건, 격리 신규 설치, v3.5 데이터 업데이트 시나리오, Defender 검사를 통과했다. 상세는 아래 "v3.6 Release Verification Snapshot"을 본다. **배포 방식은 GitLab Releases를 사용하고 `dist/`를 git에 커밋하지 않는다**(EXE 55.6 MiB가 릴리스마다 히스토리에 영구 누적되기 때문).

> ✅ **v3.5 배포 진행 결정(2026-08-15).** 설정 하단 버전 문구와 앱 메타데이터를 v3.5로 올렸으며, 정상 종료 전 스티키 저장 게이트·바로가기 인라인 관리·시작 전 데이터 건강 검사·DB와 `.salt`를 한 파일로 묶는 자동백업을 포함한다. **DB 스키마와 암호화 방식은 v3.4의 v17을 그대로 유지하며 기존 행을 일괄 수정하지 않는다.** 기술 검증 결과를 바탕으로 현 산출물의 배포를 진행한다.

> ⚠️ **라이선스 정비는 해결된 것이 아니라 명시적으로 보류한 후속 과제다.** `PySide6-Fluent-Widgets 1.11.1`의 GPLv3 준수 배포 또는 별도 상용 라이선스 확보, PySide6/Qt 고지·소스 제공 조건, 실제 번들 기준 SBOM을 아래 체크리스트대로 정리해야 한다. 이 기록을 삭제하거나 "완료"로 바꾸려면 근거 문서·산출물·해시를 함께 남긴다.

> ✅ **v3.4는 2026-08-04 정식 버전으로 확정됐다.** v3.3 릴리스 후보의 변경분(**D-Day Cover Tint 리디자인 + Pretendard 번들·캘린더 자유 이동·일정 3슬롯 표시색 설정·스티키 벡터 체크박스**)에 v3.4 변경분(**large 모드 캘린더 드래그 비활성·`바탕화면 고정` 명칭 및 데스크톱 바로 위 z-order 고정·large 일정 칩 가독성 개선**)을 합친 버전이다. `manual.qmd`와 온나라 업데이트 안내 초안도 v3.4 기준으로 갱신했다.

> ✅ **2026-08-06 v3.4 정식 산출물 재검증 완료.** 전체 테스트 467개, PyInstaller 산출물의 격리 실행·신규 v17 DB 무결성·필수 리소스·Windows 버전 정보와 Windows Defender 검사를 통과했다. 2026-08-04에 확인한 실제 Win32 z-order와 동일 DPI 듀얼 모니터 결과도 유지한다. 외부 게시 전 운영 확인 항목은 실제 Win+D 직후 Explorer/브라우저 전환, 음수 좌표·혼합 DPI 다중 모니터 육안 확인, **2026-08-05 접수된 특정 PC의 설정/휴지통 멈춤 원인 분리**, QFluentWidgets 배포 라이선스 경로 확정과 필요 시 Authenticode 서명이다.


## Known Investigation: 특정 PC 설정/휴지통 멈춤 (2026-08-05)

- **확인된 제보**: 대부분의 PC는 정상이지만 특정 PC의 기본 모드에서 더보기의 `설정` 또는 `휴지통`을 누르면 잠깐 로딩 커서가 나온 뒤 기후노트 입력이 멈춘다. 같은 더보기 메뉴의 `앱 업데이트`는 정상이며 `%LOCALAPPDATA%\MyDesktopCalendar\error.log`에는 기록이 없다.
- **배제된 설명**: 설정창이 뒤나 화면 밖에 열렸다는 사실만으로 메인 창 입력이 막히지는 않는다. 같은 메뉴의 업데이트 창이 열리므로 `RoundMenu` 전체나 일반 top-level 창 생성 문제로도 단정하지 않는다.
- **현재 가설(미확정)**: 설정과 휴지통이 공통으로 GUI 스레드에서 수행하는 동기 DB 조회/WAL 잠금이 1순위 공통 후보다. 설정에는 별도로 `available_system_fonts()` → `QFontDatabase.families()` 전체 열거가 있어 손상·충돌 글꼴 또는 Windows Font Cache 정지도 후보지만, 이것만으로 휴지통 멈춤까지 설명할 수는 없다.
- **진단 원칙**: import 직전/생성자 진입/DB 조회 전후/글꼴 열거 전후/show 완료를 파일에 먼저 `flush`+`fsync`하여 마지막 통과 지점을 남긴다. 원인이 확인되기 전에는 글꼴만 고치고 전체 문제가 해결됐다고 판단하지 않는다.
- **사용자 조치 순서**: 글꼴 열거에서만 멈추면 최근 설치 글꼴 제거 → `제어판 > 모양 및 개인 설정 > 글꼴 > 글꼴 설정`의 기본값 복원 → 재부팅 → Windows Font Cache 초기화 순으로 점검한다. DB 단계에서 멈추면 앱 완전 종료·중복 프로세스·보안 프로그램의 DB 잠금을 먼저 확인한다.

## v3.6a Release Verification Snapshot

검증일: **2026-08-19**

- v3.6 대비 변경분은 **모니터 구성 변경 시 캘린더 크기 재계산 수정**(`_on_screen_changed`), 번들 리소스 경로 통일(`app_paths.resource_root()`), 토마토 이미지의 `resources/images/` 이동, 버전 표기 규칙 확장이다. **DB 스키마·암호화·저장 형식은 그대로이며 `user_version=17`을 유지한다.**
- 전체 테스트: `535 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 빌드 산출물: `dist/기후노트_v3.6a.exe`, 60,910,082 bytes, SHA-256 `EC11C94B6346026A904F29F8ADEA590BBB0D0FD6B117EE5201C50B65979A6029`. Windows File/Product Version `3.6.1.0`, OriginalFilename `기후노트_v3.6a.exe`, Authenticode `NotSigned`.
- 버전 표기: 표시 버전 `v3.6a`, Windows 숫자 버전 `3.6.1.0`. 문자 접미사는 `build_app._windows_version_parts()`가 다음 숫자 자리로 옮긴다(`a`→1). `v3.6`(3.6.0.0)보다 커야 속성 창에서 구분되고 버전 비교가 성립한다.
- 번들 구성: `Analysis-00.toc` 기준 740개 항목(v3.6은 736개). 토마토 2개가 `resources\images\`로, `app_paths` 모듈이 새로 포함됐다. 폰트 6·Fluent SVG 21·아이콘·라이선스 모두 유지.
- 신규 설치 격리 실행: 별도 임시 `LOCALAPPDATA`와 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`에서 프로세스가 정상 응답했다. 신규 DB는 `user_version=17`, `integrity_check=ok`, FK 위반 0건, `.salt` 32 bytes, 오류 로그 0 bytes였다. 일일 `.cnbak` 1개가 `calendar.db`·`.salt`·`manifest.json` 3개만 담았고 `validate_backup_bundle()`을 통과했으며 manifest의 `app_version`이 `v3.6a`로 기록됐다.
- Windows Defender: 엔진 `1.1.26070.7`, 보안 인텔리전스 `1.457.238.0`(2026-08-19 갱신) 사용자 지정 검사에서 탐지 0건.

### 남은 확인

- **KVM 본체 전환 실기 확인이 남아 있다.** 화면 변경 시 크기 재계산은 자동 테스트(`tests/test_ui_screen_change.py` 4건)로만 검증했다. 실제 가로/세로 듀얼 모니터 + KVM 환경에서 전환 후 창이 세로 모니터에 맞게 들어오는지 육안 확인이 필요하다.
- **모니터 식별이 여전히 인덱스 기반이다.** `SETTING_TARGET_SCREEN`은 `QApplication.screens()`의 순번이라, 재연결 후 열거 순서가 바뀌면 크기는 맞아도 엉뚱한 모니터에 자리 잡을 수 있다. 미조사·미수정.
- v3.6에서 확인된 UPX 미적용 문서 불일치와 임시 `-wal`/`-shm` 누적은 그대로 남아 있다(이번 격리 실행에서도 `.backup-validate-*` 짝이 4개 남았다).
- 실제 보이는 창에서 설정 하단 v3.6a 문구 확인, 실제 Win+D 직후 Explorer/브라우저 전환 육안 확인, 2026-08-05 특정 PC 설정/휴지통 멈춤은 여전히 미해결.

## v3.6 Release Verification Snapshot

검증일: **2026-08-18**

- 앱 런타임 코드는 v3.5와 동일하다. v3.5 대비 변경분은 표시 버전(`app_info.py`), 제3자 라이선스 고지, 저장소 정비뿐이며 DB 스키마·암호화·UI 동작은 그대로다. 현재 `user_version=17` 유지.
- 전체 테스트: `518 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재. venv는 `requirements-lock.txt`와 8개 직접 의존성이 모두 일치한다.
- 빌드 산출물: `dist/기후노트_v3.6.exe`, 58,279,798 bytes, SHA-256 `C6763B023DBCDAB26CFA7D2800DADD98277FFE1201A641423F930220A1BAF6FB`. Windows File/Product Version `3.6.0.0`, OriginalFilename `기후노트_v3.6.exe`, Authenticode `NotSigned`.
- 번들 구성: PyInstaller `Analysis-00.toc` 기준 736개 항목, 원본 152.4 MB. 폰트·아이콘·Fluent SVG·토마토 이미지·라이선스가 모두 포함됐고 이번에 추가한 `LGPL-3.0.txt`와 `cryptography-LICENSE{,.APACHE,.BSD}.txt`도 들어갔다.
- 신규 설치 격리 실행: 별도 임시 `LOCALAPPDATA`와 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`에서 프로세스가 정상 응답했다. 신규 DB는 `user_version=17`, `integrity_check=ok`, FK 위반 0건, `.salt` 32 bytes, 검증 통과한 일일 `.cnbak` 1개, 오류 로그 0 bytes였다. `.cnbak`은 `calendar.db`·`.salt`·`manifest.json` 3개만 담았고 manifest의 SHA-256이 실제 페이로드와 일치했다.
- v3.5 데이터 업데이트 시나리오: 일정 3·메모 2·열린 스티키 1·휴지통 스티키 1·D-Day 1·집중 위젯 1·집중 세션 1·바로가기·사용자 설정을 채운 v17 데이터셋에서 EXE를 실행했다. **사용자 테이블 8개의 raw 행 해시가 전부 실행 전과 동일했고 `.salt` bytes도 동일했다.** 복호화 평문 12건(일정·메모·D-Day·집중 목표·집중 세션·바로가기·열린/휴지통 스티키·설정)이 모두 일치했다. `calendar_pre_v35_*.cnbak`과 일일 `.cnbak`이 각각 1개 생성됐고 오류 로그는 0 bytes였다.
- Windows Defender: 엔진 `1.1.26070.7`, 보안 인텔리전스 `1.457.219.0`(2026-08-18 갱신) 사용자 지정 검사에서 신규 탐지 0건.

### 이번 검증에서 확인된 문제

- **UPX가 실제로 적용되지 않는다.** `build.spec`은 `upx=True`이고 `docs/ARCHITECTURE.md`는 "UPX-compressed"라고 적었지만 UPX 실행 파일이 PATH에도 `upx_dir`에도 없어 PyInstaller가 압축을 건너뛴다. 문서와 실제가 어긋난 상태이므로, UPX를 도입하든 문서를 고치든 한쪽으로 맞춘다.
- **EXE 크기가 v3.5보다 3,495,772 bytes 작은 이유를 확정하지 못했다.** 앱 코드가 동일한데 크기가 줄었다. v3.5 EXE가 `dist/`에 남아 있지 않고 당시 빌드 TOC도 덮어써져 직접 비교가 불가능하다. 기능 검증은 모두 통과했으므로 배포를 막지는 않지만, 다음 빌드에서는 이전 산출물과 TOC를 보존해 비교할 수 있게 한다.
- **임시 WAL/SHM 파일이 정리되지 않고 누적된다.** 백업 검증용 `.backup-validate-*.db`와 `.auto-snapshot-*.db`는 삭제되지만 짝인 `-wal`/`-shm`이 남는다. 실제 사용자 폴더에서 2026-08-15 21:00(v3.5 최초 실행)부터 64개·약 1.0 MB가 쌓인 것을 확인했다. 데이터 손상은 없고 정상 파일과 백업 회전은 정상이지만, 사용자가 문제 발생 시 열어보는 폴더가 지저분해진다. v3.5부터 있는 결함이며 v3.6에서도 동일하다. 후속 버전에서 임시 DB 삭제 시 `-wal`/`-shm`을 함께 지우도록 고친다. → **v4.0a(2026-10-15)에서 수정**: 위 v4.0a 항목 참고.

### 남은 수동 확인

- 실제 보이는 창에서 설정 하단 v3.6 문구와 종료·바로가기 동작 확인
- 실제 Win+D 직후 Explorer/브라우저 전환 육안 확인
- 음수 좌표·혼합 DPI 다중 모니터 육안 확인
- 2026-08-05 접수된 특정 PC의 설정/휴지통 멈춤은 여전히 미해결

## v3.5 Release Verification Snapshot

검증일: **2026-08-15** (기술 검증 완료, 배포 진행 결정; 라이선스 정비는 후속 과제로 보류)

- 전체 테스트: `518 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 데이터 보호 전용: `tests/test_data_safety.py` 22개 통과. 정상/누락/손상 salt, 암호화 대상 6개 테이블 전수 검사, DB+salt+manifest 묶음, 당일 정상본 불변, 최근 5일 회전, 정리 실패 격리, 비회전 보호본을 검증했다.
- v3.4 호환: v17 DB에 일정·메모·스티키·D-Day·집중 위젯/세션·바로가기·사용자 설정을 채운 뒤 v3.5 초기화를 두 번 반복해도 모든 사용자 테이블 raw 행, 암호문, ID/sequence와 `.salt` bytes가 완전히 동일했다. `calendar_pre_v35_*.cnbak`은 1개만 생성됐다.
- 시작 실패 안전성: DB/salt/암호문이 일치하지 않으면 최초 보호본·마이그레이션·일일 백업·메인 창 생성을 시작하지 않는다. 이 검사는 DB와 salt를 새로 만들거나 수정하지 않는다.
- 현재 `user_version=17` 유지. v3.5 구현은 테이블/컬럼 추가와 기존 암호문 일괄 재작성을 하지 않는다.
- 빌드 산출물: `dist/기후노트_v3.5.exe`, 61,775,570 bytes, SHA-256 `3D5971E73559AB8C4FE7FE803A41EFAD8C96D36A8A04FBD8549C710D4694BC7D`. Windows File/Product Version `3.5.0.0`, 필수 폰트·아이콘·SVG·토마토 이미지·라이선스 포함, Authenticode `NotSigned`.
- 신규 설치 격리 실행: 별도 임시 `LOCALAPPDATA`와 `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`에서 EXE가 정상 응답했다. 신규 DB는 `user_version=17`, `integrity_check=ok`, FK 위반 0건, `.salt` 32 bytes, 검증 가능한 일일 `.cnbak` 1개, 오류 로그 0 bytes였다.
- v3.4 형식 업데이트 격리 실행: 암호화 대상 7행과 휴지통·바로가기·사용자 설정을 채운 v17 데이터셋에서 `calendar_pre_v35_*.cnbak`과 일일 `.cnbak`이 각각 1개 생성됐고 salt가 유지됐다. 일정·메모·D-Day·집중 위젯/세션·바로가기·설정 raw 행은 동일했다. 열린 스티키는 기존 시작 동작이 동일 HTML을 자동 저장해 Fernet token만 갱신했으며 복호화 본문은 byte-equivalent였고 실행 전 raw 행은 pre-v3.5 묶음에 보존됐다.
- 복구 리허설: 앱 종료 상태의 별도 임시 폴더에 일일 `.cnbak`의 `calendar.db`와 `.salt`만 설치한 뒤 건강 검사와 EXE 재실행을 통과했다. 일정·메모·열린/휴지통 스티키·D-Day·집중 위젯/세션·바로가기·사용자 설정을 모두 복구했고 DB `integrity_check=ok`, FK 위반 0건, 오류 로그 0 bytes였다.
- Windows Defender: 엔진 `1.1.26070.7`, 보안 인텔리전스 `1.457.172.0`(2026-08-15 갱신) 사용자 지정 검사에서 탐지 0건, 종료 코드 0.
- 의존성: `pip check` 충돌 0건. 로컬 배포 메타데이터의 `PySide6-Fluent-Widgets 1.11.1`은 `GPLv3`이다. 사용자는 2026-08-15에 라이선스 정비를 후속 과제로 보류하고 현 산출물 배포를 진행하기로 결정했다. 이는 라이선스 적합성 확인이나 준수 완료 판정이 아니다.
- 남은 수동 확인: 실제 보이는 창에서 설정 v3.5 문구·종료/바로가기 동작을 확인하고, 실제 Win+D 후 Explorer/브라우저 전환과 음수 좌표·혼합 DPI 환경을 육안 점검한다. 배포 후라도 재현 가능한 환경이 마련되면 결과를 이 문서에 추가한다.

## Deferred Release Work: 라이선스·배포 정비 (2026-08-15)

2026-10-09 v3.9a 고지 정비: 버전·기능·데이터 계약을 유지하면서 설정의 구성요소별 오프라인 원문 열람, 앱 GPLv3, HWP 명세 지정 문구, PaddleOCR 원저작권/출처, 누락 Python 구성요소·Qt 모듈 및 공식 하위 고지 원문을 보강했다. 목록 정본은 `licenses/components.json`과 선택형 앱 내부의 목록이다. 실제 pywin32 원문은 구성요소별 BSD 계열, cffi 2.0.0 원문은 MIT No Attribution이므로 메타데이터의 간략 분류와 구분한다. [현재 구현·검증 기록](work/2026-10-09-license-notices-update.md)을 따른다. 전수 SBOM·외부 대응 소스 제공·기관 계약·권리 확인·서명은 별도 보류를 유지한다.

> **상태: HOLD — 후속 버전에서 반드시 재개.** 2026-08-18에 기관 내부 GitLab 소스 공개(GPLv3)와 고지 보강을 진행했으나, 이것만으로 배포 라이선스 검토가 끝난 것은 아니다. **남은 것**: PyInstaller 산출물 기준 전수 SBOM, PySide6/Qt LGPL 경로에서 수령자의 교체·재링크 가능성(one-file 배포) 판단, 기관 법무·저작권 담당 확인, Authenticode 서명. **끝난 것**: 프로젝트 최상위 `LICENSE`(GPLv3) 추가, `licenses/THIRD_PARTY_NOTICES.txt`에 PySide6/Qt·shiboken6·cryptography·pysidesix-frameless-window 항목과 원문 추가, 소스 공개 경로 확보(`origin/main`).

- **QFluentWidgets 경로 확정(둘 중 하나)**
  - GPLv3 경로: 기후노트 소스 공개 권한자를 먼저 확인하고, 앱의 적용 라이선스를 명시한다. 배포 EXE와 정확히 대응하는 전체 소스, `build.spec`/`build_app.py`, 의존성 잠금, 리소스, 빌드 안내, GPLv3 원문과 QFluentWidgets 1.11.1 대응 소스를 수령자가 EXE만큼 쉽게 받을 수 있게 제공한다.
  - 상용 경로: 저작권자로부터 `PySide6-Fluent-Widgets 1.11.1`의 Windows PyInstaller one-file, 대한민국 정부기관 업무용·무상 배포 범위를 포함하는 서면 라이선스를 확보한다. 영구 재배포, 개발자/사용자·기관 범위, 적용 버전과 업데이트, 기존 산출물 적용 여부, 필수 고지사항을 계약서·메일·영수증으로 보존한다. Pro 제품 구매가 상용 재배포권을 자동 포함한다고 가정하지 않는다.
- **PySide6/Qt 별도 확인**: LGPLv3/GPLv3 또는 Qt 상용 조건 중 적용 경로를 기록한다. 오픈소스 경로라면 PySide6/Qt 사용 사실과 라이선스 원문, 실제 사용 라이브러리의 대응 소스 획득 방법, 사용자의 교체·재링크 및 역공학 권리를 제한하지 않는 배포 방식을 문서화한다. 필요하면 one-file 배포의 재링크 가능성을 별도로 검토한다.
- **실제 산출물 기준 전수 조사**: `requirements-lock.txt` 전체가 아니라 PyInstaller `Analysis-00.toc`/최종 EXE에 실제 포함된 Python·PySide6/Qt·암호화·이미지·아이콘·폰트 구성요소로 SBOM을 만들고, 이름/버전/저작권자/라이선스/원문/소스 URL/수정 여부를 기록한다.
- **배포 고지 완성**: 2026-08-18 기준 일부 진행됐다.
  - ✅ 프로젝트 최상위 `LICENSE` — GPLv3 전문 674줄.
  - ✅ `licenses/THIRD_PARTY_NOTICES.txt` — 기존 Pretendard·Font Awesome·PySide6-Fluent-Widgets에 더해 **PySide6 6.10.2 / Qt 6.10.2(shiboken6 포함), cryptography 46.0.4, pysidesix-frameless-window 0.8.0** 항목을 추가했다.
  - ✅ `licenses/LGPL-3.0.txt` — FSF 정본(https://www.gnu.org/licenses/lgpl-3.0.txt), 7,652 bytes, SHA-256 `E3A994D82E644B03A792A930F574002658412F62407F5FEE083F2555C5F23118`. 설치 배포판 동봉 사본과 본문 일치(끝 개행만 차이) 확인.
  - ✅ `licenses/cryptography-LICENSE{,.APACHE,.BSD}.txt` — 설치 배포판 `cryptography-46.0.4.dist-info/licenses/`에서 복사.
  - ✅ 소스 공개 경로 — `origin/main`(기관 내부 GitLab Public). GPLv3 대응 소스 제공 범위가 EXE 배포 범위와 일치한다.
  - ✅ 앱 설정에서 접근 가능한 오픈소스 고지 화면과 번들 원문(2026-10-09, v3.9a 고지 정비; 검증은 위 작업 기록).
  - ⬜ 배포 EXE와 정확히 대응하는 소스 묶음(`기후노트_v3.5_소스코드.zip`) 생성 여부 결정. 소스가 GitLab에 공개되어 있으므로 별도 zip이 필요한지 함께 판단한다.
- **증빙 보존 및 완료 조건**: EXE·소스 묶음·SBOM·라이선스 문서·상용 계약(해당 시)의 SHA-256과 배포 게시 위치를 기록한다. 기관 법무/저작권 담당 확인이 필요한 배포 범위(동일 기관 내부인지, 타 기관까지 전달되는지)를 남긴다. 위 항목이 모두 충족되기 전에는 이 과제를 완료 처리하지 않는다.
- **별도 후속 항목**: 현재 EXE는 Authenticode `NotSigned`다. 기관 정책이 요구하면 코드 서명을 적용하고 서명 상태·인증서 주체·타임스탬프를 기록한다. 이는 라이선스 정비와 별개다.

## v3.4 Release Verification Snapshot

검증일: **2026-08-04**, 정식 산출물 갱신: **2026-08-06**

- 전체 테스트: `467 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 추가 검사: 변경 핵심 Python 파일 `py_compile` 통과, `pip check` 의존성 충돌 0건, `git diff --check` 통과.
- 격리 실행: `CLIMATENOTE_SKIP_STARTUP_REFRESH=1`과 별도 임시 `LOCALAPPDATA`에서 8월 4일 실제 UI 창을, 8월 6일 최종 빌드의 프로세스 응답 상태를 확인했다. 신규 DB는 `user_version=17`, `quick_check=ok`, FK 위반 0건, 오류 로그 0 bytes였다.
- Windows 네이티브: 실제 바탕화면 아이콘 호스트가 `Progman`의 `SHELLDLL_DefView`임을 확인했다. 임시 Qt 창 실측에서 기후노트 역할 창은 데스크톱 바로 위 rank 1, 일반 창은 rank 319로 더 위였고, 기후노트 역할 창은 non-topmost였다. 실제 Win+D 키 입력은 사용자 화면을 방해하지 않도록 자동 전송하지 않았다.
- 검증 산출물: `dist/기후노트_v3.4.exe`, 61,757,130 bytes, SHA-256 `582090BFA381C08AAA9339E4ADC360BCEFF616F2D1BB20ECCEC3366062ADD25B`. Windows File/Product Version `3.4.0.0`, 필수 폰트·이미지·라이선스와 변경 모듈 포함, Windows Defender(서명 `1.457.27.0`, 2026-08-06 갱신) 탐지 0건.
- 사용설명서: `manual.qmd`를 v3.4 기준으로 갱신하고 `output/pdf/기후노트_v3.4_사용설명서.pdf` 5페이지를 전 페이지 렌더링 확인했다. PDF 221,956 bytes, SHA-256 `D8C1CF65453BF2FCA6E2948CCAB8CEE70EA4838AEDB37E4000D2BB018A1C187E`.
- 모니터 환경: 실제 1920×1080 모니터 2대가 모두 100% 배율, 양의 좌표 `(0,0)`/`(1920,0)`로 인식됐다. 음수 좌표·150%/200% 혼합 DPI는 자동 테스트만 통과했으며 실제 장비 육안 확인은 남아 있다.
- 외부 게시 전 운영 확인: 산출물은 Authenticode `NotSigned`. PySide6-Fluent-Widgets 1.11.1의 GPLv3 준수 방식 또는 별도 상용 라이선스를 확정하고, 실제 Win+D 직후 Explorer/브라우저 전환과 혼합 DPI 다중 모니터를 육안 확인한다.
- 산출물 보존 상태: 2026-08-06 현재 `dist`에는 최종 v3.4 EXE만 있으며 아래 v3.3 EXE의 크기·해시는 역사적 검증 기록이다.

## v3.3 Release Verification Snapshot

> 이 스냅샷은 v3.4 변경 전 v3.3 릴리스 후보의 역사적 검증 기록이다. v3.4 배포 근거로 간주하지 않는다.

검증일: **2026-07-23**

- 전체 테스트: `461 passed`, 실패 0건. 외부 QFluentWidgets의 SciPy deprecated import 경고 1건만 존재.
- 추가 검사: 핵심 Python 파일 `py_compile` 통과, `pip check` 의존성 충돌 0건, 150%/200% DPI 관련 테스트 각각 통과.
- 데이터 보존: 실사용 v16 DB를 읽기 전용 확인했을 때 `quick_check=ok`, FK 위반 0건. SQLite 온라인 snapshot 복제본을 빌드 EXE로 v17까지 올린 뒤 사용자 테이블 raw 행과 기존 설정의 SHA-256이 사전 백업과 동일했다. 새로 생긴 행은 `schedule_color_1/2/3`과 `calendar_position_mode`뿐이다.
- Windows 네이티브: 메인+스티키+D-Day+집중 5개 창의 Win+D 생존과 pulse 후 non-topmost 복귀를 확인했고, Win+M 10회 반복 실패 0건, native hook 해제 성공.
- 검증 산출물: `dist/기후노트_v3.3.exe`, 61,754,273 bytes, SHA-256 `C95E9982C99ABF9A7482E585A5A3F6908CBEC9C834EDBB93D3F6788747907892`. Windows File/Product Version `3.3.0.0`, 필수 폰트·이미지·라이선스 포함, Windows Defender 탐지 0건.
- 배포 보류 항목: 산출물은 Authenticode `NotSigned`. PySide6-Fluent-Widgets 1.11.1 메타데이터는 GPLv3이므로 외부 배포 전에 GPLv3 준수 방식 또는 별도 상용 라이선스를 확정한다. `dist/소스코드`는 현재 비어 있다.
- 마지막 수동 게이트: 실제 듀얼/트리플 모니터(음수 좌표·혼합 DPI 포함)에서 드래그→재시작→크기 변경→모니터 분리, Win+D 직후 Explorer/브라우저 전환을 육안 확인한다.
