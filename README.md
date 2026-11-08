<img src="readme/app.png" alt="기후노트 — 늘 보이는 곳에, 오늘 할 일. 모니터 1대에서는 바탕화면에 기본 크기 캘린더와 D-Day·스티키 메모를, 모니터 2대에서는 오른쪽 모니터에 일정·메모·D-Day·집중 모드를 함께 펼친 확장 모드(크게)를 띄운 모습">

<div align="center">
  <br>
  <img src="readme/badge-version.svg" alt="버전 v4.8">
  <img src="readme/badge-windows.svg" alt="Windows 10 · 11">
  <img src="readme/badge-offline.svg" alt="네트워크 오프라인 전용">
  <img src="readme/badge-license.svg" alt="라이선스 GPL-3.0">
  <br><br>
  <a href="https://gitlab.aigov.go.kr/whrhkdrh/climate-note/-/releases"><img src="readme/button-download.svg" alt="최신 버전 받기"></a>
  <a href="https://gonynim22.github.io/climate-note/climate-note-intro/climate-note-intro.html" target="_blank" rel="noopener noreferrer"><img src="readme/button-slides.svg" alt="제품 소개 슬라이드"></a>
  <a href="https://gonynim22.github.io/climate-note/climate-note-intro/climate-note-video.html" target="_blank" rel="noopener noreferrer"><img src="readme/button-video.svg" alt="제품 소개 영상"></a>
  <a href="README_detail.md"><img src="readme/button-detail.svg" alt="상세 안내"></a>
  <br>
  <sub>인터넷이 막힌 PC는 <a href="https://gitlab.aigov.go.kr/whrhkdrh/climate-note/-/raw/main/climate-note-intro/climate-note-intro.html?inline=false">소개 슬라이드 파일</a>을 받아 더블클릭하세요.</sub>
</div>

## <sub><img src="icon/climate_note_style16_continents_final.svg" width="26" height="26" alt=""></sub> 앱의 목적

<table>
  <tr>
    <td>
      <h3><sub><sub><img src="readme/chip-climate.svg" width="56" height="28" alt="기후"></sub></sub> 포스트잇 대신, 바탕화면에</h3>
      모니터 테두리와 책상 위를 덮은 포스트잇에서 시작했습니다. 붙이고, 적고, 또 잊어버리는 종이 메모를 바탕화면으로 옮기면 종이는 줄고 할 일은 늘 눈앞에 남습니다. <mark>종이 한 장이라도 아끼자는 마음</mark>을 담아 이름을 <b>'기후노트'</b>로 지었습니다.
      <h3><sub><sub><img src="readme/chip-time.svg" width="56" height="28" alt="시간"></sub></sub> 공공기관의 시간은 국민의 시간</h3>
      공공기관 직원의 시간은 <mark>국민 모두의 시간</mark>이기도 합니다. 일정과 자주 쓰는 업무 도구를 한곳에 모아, 찾고 옮겨 적느라 흘려보내는 시간을 줄이고 싶었습니다.
    </td>
  </tr>
</table>

## <sub><img src="readme/icon-features.svg" width="26" height="26" alt=""></sub> 주요 기능

- **캘린더** — 기본 · 중간 · 크게 세 가지 크기, 공휴일 · 음력 내장, 공휴일 테마
- **일정** — 시작 시각 · 알림 · 반복 · 여러 날 기간, 반복 일정의 이 날만 수정
- **위젯** — 스티키 노트, D-Day, 집중 모드(포모도로)
- **바탕화면** — <kbd>Win</kbd> + <kbd>D</kbd>에도 남는 고정, 바로가기 사이드바, 트레이 상주
- **검색** — 일정 · 메모 전체 검색, AI 법령정보 검색
- **보안** — 이 PC에만 암호화 저장, PIN 잠금, 인터넷 접속 기본 꺼짐
- **미니앱** — <sub><sub><img src="resources/icons/mini_apps/unit_converter.svg" width="22" height="22" alt=""></sub></sub> 단위 환산 &nbsp; <sub><sub><img src="resources/icons/mini_apps/date_time.svg" width="22" height="22" alt=""></sub></sub> 날짜/시간 계산 &nbsp; <sub><sub><img src="resources/icons/mini_apps/money_notation.svg" width="22" height="22" alt=""></sub></sub> 금액 표기 &nbsp; <sub><sub><img src="resources/icons/mini_apps/document_converter.svg" width="22" height="22" alt=""></sub></sub> 파일 변환 &nbsp; <sub><sub><img src="screen_text/icon.svg" width="22" height="22" alt=""></sub></sub> 화면 글자 따기

## <sub><img src="readme/icon-download.svg" width="26" height="26" alt=""></sub> 시작하기

1. [**Releases**](https://gitlab.aigov.go.kr/whrhkdrh/climate-note/-/releases)에서 EXE 파일 하나를 받아 실행합니다. 설치는 필요 없습니다.
2. SmartScreen 경고가 뜨면 <kbd>추가 정보</kbd> → <kbd>실행</kbd>을 누르세요. 코드 서명이 없어서 나오는 경고입니다.
3. 받은 파일은 릴리스 설명의 SHA-256과 비교할 수 있습니다: `Get-FileHash <파일명> -Algorithm SHA256`

## <sub><img src="readme/icon-update.svg" width="26" height="26" alt=""></sub> 업데이트

트레이에서 기후노트를 **완전히 종료**한 뒤 새 EXE를 실행하면 됩니다. 데이터는 `%LOCALAPPDATA%\MyDesktopCalendar\`에 그대로 남아 초기화나 가져오기가 필요 없습니다.

<details>
<summary>다른 PC로 옮기기</summary>

데이터는 이 PC와 Windows 계정에 묶여 있습니다. 설정의 **내보내기 / 가져오기**로 옮기세요.

</details>

<details>
<summary>예전 버전에서 올릴 때</summary>

v4.5 이상을 쓰고 있다면 EXE만 바꾸면 됩니다. 그보다 예전 버전이면 **지금 버전보다 높은 줄**을 확인하세요.

| 바뀐 버전 | 이 버전을 넘어 올릴 때 알아둘 점 |
|:--|:--|
| **v4.1** | 처음 실행하면 데이터가 새 형식(DB v18)으로 바뀌고 '기후노트 업데이트 안내' 창이 한 번 뜹니다. 그 뒤로는 v4.0a 이하 EXE가 데이터를 바꾸지 않고 실행을 멈춥니다. |
| **v4.3** | PIN 잠금을 쓰던 경우 PIN이 검증값으로 저장되어 v4.3 이상에서만 풀 수 있습니다. 새 내보내기는 12자 이상 암호를 씁니다(예전 4자리 PIN 파일도 가져올 수 있음). |
| **v4.5** | 처음 실행하면 데이터가 새 형식(DB v19)으로 바뀝니다. 그 뒤로는 v4.4b 이하 EXE가 데이터를 바꾸지 않고 실행을 멈추고, 새로 내보낸 파일도 읽지 못합니다. |

되돌릴 때 쓰는 보호본은 [상세 안내](README_detail.md), 버전별 새 기능은 [Releases](https://gitlab.aigov.go.kr/whrhkdrh/climate-note/-/releases)에 있습니다.

</details>

## <sub><img src="readme/icon-shield.svg" width="26" height="26" alt=""></sub> 요구 환경 · 라이선스

- Windows 10 이상(Windows 11 권장), Windows 전용
- GNU GPL v3.0 — [LICENSE](LICENSE) · 제3자 구성요소 고지 [licenses/](licenses/) · [기본 목록](licenses/components.json) · [소스 제공 안내](licenses/APP-NOTICE.txt)
- 설정 → 라이선스에서 구성요소별 원문과 출처를 오프라인으로 열람 · 복사할 수 있습니다.

<sub>본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다. 한글·HWPX 변환기는 별도 설치 제품으로 해당 사용권이 적용됩니다.</sub>

---

<div align="center">
  <sub>기능 상세 · 버전별 변경 · 소스 실행 · 테스트 · 빌드는 <a href="README_detail.md"><b>README_detail.md</b></a>, 개발 규칙은 <a href="AGENTS.md">AGENTS.md</a>에 있습니다.</sub>
  <br>
  <sub>만든이: 기후에너지환경부 보문산불주먹</sub>
</div>
