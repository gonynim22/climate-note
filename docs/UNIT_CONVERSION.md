# 단위 환산기 정의와 검증 기준

v3.8의 개발자 제공 미니앱이다. 정본 구현은 `unit_converter.py`, UI는 `ui_unit_converter.py`다.
네트워크·DB·설정 저장 없이 25개 분류, 178개 항목을 지원한다. 미래의 계수 변경에도
사용자 일정·메모·설정·DB v17·Export v2·salt를 변경하지 않는다.

## 채택 범위

| 그룹 | 분류 (항목 수) |
|---|---|
| 기본 | 길이 14, 무게 11, 부피 11, 넓이 9, 온도 4, 속도 5, 시간 9, 데이터 10 |
| 물리 | 압력 9, 에너지 9, 전력 8, 각도 6, 힘 5, 주파수 5 |
| 환경 | 탄소 3, 기체 농도 7, 질량비 9, 수질 농도 7, 유량 8, 미세먼지 4, 방사선 6, 조도 4, 음압 4 |
| 생활 | 요리 계량 7, 연비 4 |

나무·자동차·항공·전기·휘발유·소고기 배출량 비교, 담배 개비, 촬영/비행/자연방사선 횟수,
신발 치수, 마지기, 마하, 일반 밥숟가락은 포함하지 않는다. 탄소는 이미 산정된 CO₂e의
질량 단위, 미세먼지는 질량 농도, 방사선은 Sv/rem 계열의 선량 단위만 변환한다.

## 정의와 출처

출처 확인일: 기존 정의 2026-09-20, 환경 추가 정의 2026-09-21. `Unit.source`는 아래의 근거를 가리킨다. 출처 확인은 개발 단계에서만
수행하며 앱에서는 웹페이지·외부 스크립트·폰트를 읽지 않는다.

| source | 근거 | 적용 |
|---|---|---|
| `nist` | [NIST SP 811 Appendix B.9](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b9), [Appendix B.8](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8) | SI 배율·일반 환산 정의·표준중력·온도·열량 구분. 복합 단위는 정의식에서 유도 |
| `kriss` | [한국표준과학연구원 단위와 환산](https://www.kriss.re.kr/menu.es?mid=a10302070000) | 자·척관법 리·평·근·관·돈·되·말의 기준 |
| `codata` | [NIST CODATA 2022 전체 상수](https://physics.nist.gov/cuu/Constants/Table/allascii.txt) | 전자볼트의 현행 정의 상수 |
| `iau` | [IAU Measuring the Universe](https://iauarchive.eso.org/public/themes/measuring/) | 진공의 빛과 율리우스년으로 정의한 광년 |
| `keei` | [에너지경제연구원 2018 에너지통계연보](https://www.keei.re.kr/keei/download/YES2018.pdf) | 석유환산톤의 에너지 정의 |
| `fda` | [FDA 가정용 계량단위 안내](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/guidance-industry-guidelines-determining-metric-equivalents-household-measures) | 240mL 컵·15mL 큰술·5mL 작은술의 명시 용량 |
| `fixed` | 앱에서 이름에 명시한 고정 기간/용량 | 30일 개월, 365일 년, 200mL 계량컵. 달력 기간/일반 용기 크기를 추정하지 않음 |
| `nist_fraction` | [NIST SP 811 §7.10](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-7-rules-and-style-conventions-expressing-values) | 몰분율·질량분율 구분, 명시적인 비율 단위. ppm·ppb·ppt는 사용 편의를 위한 관용 표기로 제공하며 SI 공식 기호로 주장하지 않음 |

## 환경 농도와 유량 (2026-09-21 추가)

- **기체 농도**는 몰분율이다. ppm=10⁻⁶ mol/mol, ppb=10⁻⁹ mol/mol, ppt=10⁻¹² mol/mol,
  %=10⁻² mol/mol이며 µmol/mol·nmol/mol도 함께 제공한다. 예: 400 ppm=0.04%=400,000 ppb.
  질량분율이나 체적분율로 무조건 치환하지 않는다.
- **질량비**는 전체 혼합물 질량에 대한 질량분율이다. ppm=mg/kg, ppb=µg/kg, ppt=ng/kg이며
  %=10 g/kg이다. 기체 농도와 단위명이 같아도 다른 분류/최근 기록으로 유지한다.
- ppt는 이 앱에서 **1조분의 1**로 고정하고 목록에 10⁻¹²를 표시한다. 천분율이나 염분 PSU를 뜻하지 않는다.
- **수질 농도**는 질량/부피다. 1 mg/L=1 g/m³=1,000 µg/L, 1 g/L=1 kg/m³=1 mg/mL.
  [NIST 접두어](https://www.nist.gov/pml/owm/metric-si-prefixes)와
  [리터·시간 정의](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-5-units-outside-si)로 유도한다.
  ppm과 mg/L 사이에는 밀도가 필요하므로 고정 등식으로 연결하지 않는다.
  [USGS 농도 환산 지침](https://water.usgs.gov/water-resources/memos/memo.php?id=992)은 밀도 조건과 보정을 설명한다.
- **유량**은 실제 부피/시간의 크기다. 1 L/s=3.6 m³/h, 24 m³/d=1 m³/h.
  온도·압력 조건이 없는 Nm³/Sm³, 질량유량으로 환산하지 않는다.
- 기체 ppm ↔ mg/m³ 환산은 분자량·온도·압력 조건을 받는 별도 계산이 필요하므로 이번 범위에 포함하지 않는다.
  [NIOSH 분석 방법의 조건식](https://stacks.cdc.gov/view/cdc/181057/cdc_181057_DS1.pdf)을 참고했으며 해당 근사 상수를 앱 계수로 도입하지 않았다.
- 새 4분류의 기준 설명은 툴팁뿐 아니라 입력 카드 위에 항상 표시한다.

척관법은 위 KRISS 정의를 사용한다. 자는 10/33 m, 평은 400/121 m², 되의 리터 값은
2401/1331이며 말은 10되다. 질량은 관 3.75kg, 근 600g, 돈 3.75g이다.
**리(척관법·36정)**는 12,960자이며 일반적인 한국 거리 표현의 ‘리’로 단정하지 않는다.
원본 시안의 `392.727 m`는 이 정의와 다르므로 사용하지 않는다.

일반 단위는 다음 기준을 고정한다.

- 국제 인치·피트·마일, 상용질량 파운드/온스, 국제피트 에이커를 사용한다. US survey foot와 혼합하지 않는다.
- 갤런/쿼트/파인트/액량온스는 US liquid, 배럴은 석유용 42 US gal이다. 연비만 US/UK 갤런을 모두 제공한다.
- 칼로리/kcal는 열화학, BTU는 IT, 마력은 영국 hp와 미터법 PS를 구별한다. toe는 41.868 GJ다.
- 광년은 진공 광속 × 율리우스년 365.25일이다. 시간 분류의 ‘년(365일 고정)’과 정의가 다르므로 이름에 밝힌다.
- 데이터의 십진/이진 접두어를 구별한다. [NIST 이진 배수 안내](https://physics.nist.gov/cuu/Units/binary.html)를 따른다.
- 음압은 `dB SPL = 20 log10(p / 20µPa)`이고 비율은 기준 음압에 대한 비율이다. [NIST SP 811 §8.7](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-8)의 기준값 표시를 따른다. dBA·전력 dB·체감 크기와 혼합하지 않는다.
- 요리 계량은 표시한 용량의 도구를 전제로 한다. FDA 영양표시의 반올림 fl oz를 일반 US fl oz 정의로 대체하지 않는다. 앱의 US fl oz는 부피 분류와 같은 정의다.

## 계산·입력 계약

- 입력은 ASCII 숫자, 부호, 소수점, 지수, 올바른 3자리 쉼표 그룹을 허용한다. 96자 제한,
  문자열 전체 검증을 적용한다. `12abc`나 `1,23`을 숫자 접두사로 해석하지 않는다.
- 빈 값과 작성 중인 부호·소수점·지수는 입력 중으로 유지한다. 비유한 값과 표현 범위 미만의
  비영 숫자는 오류이며 정상적인 0으로 바꾸지 않는다.
- 온도는 절대영도 이상, 연비는 양수, 음압/비율은 양수다. dB의 음수는 허용한다.
- 새 농도·유량은 0 이상이고 몰/질량분율은 100% 이하다. 순수 물질(100%)의 단위 왕복에서 생기는
  float 오차만 상대 2e-15 이내에서 허용한다. 서로 다른 농도 기준의 단위를 섞으면 오류다.
- 계산은 Python float의 정밀도로 수행하며 단위 교환에 표시 반올림을 적용하지 않는다.
  결과는 6자리 유효숫자이며 아주 크거나 작은 수는 지수 표기한다. 전체 값은 결과 툴팁에 둔다.
- 최근 기록은 유효한 입력창 Enter 때만 최대 12개 저장한다. 중복 키는 분류/두 단위/입력값이다.
  기록에는 입력 원문을 보존하며 표시 라벨을 계산 원본으로 쓰지 않는다.
- X/Esc로 숨겨도 실행 중 상태를 보존한다. 앱 종료와 데이터 초기화 성공 때만 폐기한다.
  저장·보호백업·초기화 실패 시 미리 지우지 않는다.

## 검증

`tests/test_unit_converter.py`는 모든 채택 단위의 독립 기준값(분류별 GOLDEN), 모든 단위 쌍의
왕복, 정확 정의 대표값, 입력/범위/표시/기록/반복 교환을 검사한다. 기준값 비교 허용오차는
유효숫자에 맞춰 상대 5e-10, 대표 정의는 상대 2e-14 및 온도 경계 절대 1e-12다.
계수 구현에서 기대값을 읽거나 왕복 성공만으로 정확성을 판단하지 않는다.

UI·기존 데이터 보존·실제 렌더·EXE 검증은 [검증 지침](TESTING.md)과
[현재 확대·환경 단위 기록](work/2026-09-21-mini-app-environment.md)을 따른다.
최초 21분류·147항목의 검증은 [v3.8 최초 구현 기록](work/2026-09-20-v3.8-unit-converter.md)에 보존한다.
