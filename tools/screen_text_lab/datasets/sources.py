"""이번 실험에 직접 작성한 공개 가능한 합성 문구. 실제 기관 문서가 아니다.

줄 수와 독립 템플릿 수를 혼동하지 않는다. 같은 업무 서식/문장 구조는
template_family_id로 묶으며 새 문장을 숫자 치환으로 대량 생산하지 않는다.
"""

SOURCES = {
    "train": {
        "body": [
            ("notice", "본 안내는 화면 인식 시험을 위해 작성한 가상 행정 문서입니다."),
            ("notice", "참석 대상자는 안내 내용을 확인한 뒤 소속 부서의 담당자에게 문의하시기 바랍니다."),
            ("notice", "회신 서식에 필수 항목이 빠져 있는 경우 해당 내용을 보완하여 다시 제출해 주십시오."),
            ("notice", "우천으로 현장 방문이 어려우면 실내 교육으로 전환하며 변경 사항은 별도로 안내합니다."),
            ("records", "회의 결과는 결정 사항과 후속 조치를 구분하여 기록하고 참석자 확인을 받아 보관합니다."),
            ("records", "첨부한 자료의 출처와 작성 기준일을 함께 확인하여 중복 제출이 발생하지 않도록 협조 바랍니다."),
            ("records", "자료를 정정할 때에는 변경 사유와 수정한 부분을 표시하여 이전 문서와 구분해 주십시오."),
            ("records", "확인되지 않은 수치는 추정값으로 표시하고 최종 측정값이 확보되면 담당 부서에 알려 주십시오."),
            ("inspection", "현장 점검은 사전 안전 교육을 마친 인원이 실시하며 출입 제한 구역에는 들어가지 않습니다."),
            ("inspection", "장비를 사용하기 전에 보호 덮개와 연결 상태를 살펴보고 이상이 있으면 담당자에게 알립니다."),
            ("inspection", "시료 용기에는 채취 장소와 시각을 적고 운반 중 내용물이 섞이지 않도록 밀봉합니다."),
            ("inspection", "조사 지점의 접근이 불가능한 경우 임의로 대체하지 말고 변경 필요 사유를 기록해 주십시오."),
            ("approval", "검토 의견이 서로 다른 항목은 쟁점을 정리하여 책임자의 확인을 받은 뒤 처리합니다."),
            ("approval", "사업 일정에 영향을 주는 변경은 관련 부서와 협의하고 승인 결과를 문서에 남겨야 합니다."),
            ("approval", "제출된 증빙 자료는 지출 내역과 대조한 뒤 누락 여부를 확인하여 검토란에 표시합니다."),
            ("approval", "예산 집행 계획은 사업 목적과 산출 근거가 연결되도록 작성하며 남은 금액을 별도로 적습니다."),
            ("environment", "하천 주변 정비 활동에서는 서식지를 훼손하지 않도록 이동 경로와 작업 범위를 확인합니다."),
            ("environment", "비산먼지가 발생하는 작업은 현장 여건을 고려하여 실시하고 주변 통행로를 안전하게 확보합니다."),
            ("environment", "물품을 재사용할 수 있는지 먼저 확인하고 폐기 대상은 재질별로 나누어 지정 장소에 둡니다."),
            ("environment", "측정 결과의 단위가 서로 다르면 원본 표기를 보존한 상태에서 비교 기준을 별도로 제시합니다."),
            ("communication", "문의 사항은 담당자에게 전달하되 개인을 식별할 수 있는 정보는 시험 자료에 입력하지 않습니다."),
            ("communication", "신청인이 이해하기 어려운 용어는 쉬운 설명을 덧붙이고 처리 절차를 순서대로 안내합니다."),
            ("communication", "휴무일에 접수된 요청은 다음 근무일에 확인하며 긴급한 현장 상황은 별도 연락망을 사용합니다."),
            ("communication", "안내문을 게시하기 전에 날짜와 연락처를 다시 확인하고 오래된 안내는 새 문서로 교체합니다."),
            ("rare_words", "갠 하늘 아래 숲길을 살피며 젖은 흙과 얕은 물웅덩이의 위치를 시험 기록에 남겼습니다."),
            ("rare_words", "덧붙인 설명에는 얽힌 절차를 쉽게 풀어 쓰고 낯선 용어에는 짧은 풀이를 함께 적었습니다."),
            ("rare_words", "넓은 뜰의 묽은 흙탕물을 살핀 뒤 닳은 장갑과 젖은 천을 따로 모아 두었습니다."),
            ("rare_words", "볕이 드는 창가에 놓인 얇은 안내책자의 겉면과 펼친 쪽의 인쇄 상태를 비교합니다."),
        ],
        "table": [
            ("progress_cells", "검토 항목: 추진 일정의 적정성"),
            ("progress_cells", "담당 부서: 가상 환경기획팀"),
            ("progress_cells", "조치 상태: 보완 자료 접수 대기"),
            ("progress_cells", "확인 결과: 계획에 따라 정상 진행"),
            ("inventory_cells", "품명 | 규격 | 수량 | 보관 위치"),
            ("inventory_cells", "휴대용 측정기 / 대여 가능 / 점검 완료"),
            ("inventory_cells", "보호 안경 12개, 방진 마스크 36개"),
            ("inventory_cells", "반납 예정: 교육 종료 후 관리실 인계"),
            ("sampling_cells", "조사 구간: 상류 합류부에서 교량 아래까지"),
            ("sampling_cells", "기상 상태: 흐림, 약한 바람"),
            ("sampling_cells", "채취 방법: 표층 시료를 용기에 분리 보관"),
            ("sampling_cells", "현장 특이사항: 주변 정비 작업 없음"),
            ("receipt_cells", "접수 번호 | 신청 구분 | 처리 기한"),
            ("receipt_cells", "처리 결과: 보완 요청 사항 안내 완료"),
            ("receipt_cells", "구비 서류: 신청서 및 확인 자료 각 1부"),
            ("receipt_cells", "발송 방식: 담당 부서의 문서함으로 전달"),
            ("budget_cells", "세부 사업명: 가상 수질 조사 지원"),
            ("budget_cells", "편성액 3,250,000원 / 집행액 2,180,000원"),
            ("budget_cells", "잔액 1,070,000원, 집행률 67.08%"),
            ("budget_cells", "산출 근거: 측정 소모품 단가 × 소요 수량"),
            ("water_cells", "용존산소 8.4 mg/L, 수온 18.2 ℃"),
            ("water_cells", "부유물질 12.5 ㎎/L, 탁도 3.8 NTU"),
            ("water_cells", "전기전도도 245 μS/cm, 산도 pH 7.2"),
            ("water_cells", "검출 한계 미만은 정량값과 구분하여 표시"),
            ("legal_cells", "상호: ㈜가상누리환경"),
            ("legal_cells", "대상 면적 125.4 ㎡ / 시설 용적 376.2 ㎥"),
            ("legal_cells", "사업장 구분: 교육용 가상 시설"),
            ("legal_cells", "검토 근거: 해당 시험 계획의 세부 항목"),
        ],
        "numeric": [
            ("payment", "지급 예정액: 금일백이십삼만사천오백원정"),
            ("payment", "총 청구액 ₩2,468,000 (부가세 포함)"),
            ("payment", "단가 18,750원 × 24개 = 450,000원"),
            ("payment", "정산 차액 −12,500원, 환급 예정 12,500원"),
            ("deadlines", "제출 기간: 2026. 10. 12. ~ 2026. 10. 23."),
            ("deadlines", "교육 시작 09:30, 실습 종료 11:05, 휴게시간 10분 포함"),
            ("deadlines", "완료 예정일: 2027년 2월 28일 일요일"),
            ("deadlines", "관측 일시 2026-11-06 14:07:32"),
            ("measurement", "측정기 교정점 0.001·1.000·99.999 mg/L (분해능 0.005)"),
            ("measurement", "평균 농도 35.6 μg/m³, 상대 습도 62.5%"),
            ("measurement", "기준 온도 20 ℃, 허용 범위 18~22 ℃"),
            ("measurement", "유량 3.25 ㎥/s, 저수 용량 1,250 ㎥"),
            ("dimensions", "도면 축척 1:2,500 / 경계 길이 0.85 km"),
            ("dimensions", "시료 질량 0.025 ㎏, 용액 부피 250 ㎖"),
            ("dimensions", "필터 지름 47 ㎜, 유효 면적 13.8 ㎠"),
            ("dimensions", "시험 토지 면적 2.4 ㏊, 길이 180 m"),
            ("thresholds", "허용 기준 ≤ 0.05 / 관측값 0.047 / 판정 적합"),
            ("thresholds", "증감률 +3.25%, 전년 대비 0.8%p 상승"),
            ("thresholds", "소음 57 ㏈, 전력 2.2 ㎾, 주파수 60 ㎐"),
            ("thresholds", "전압 220 V / 전류 10 ㎃ / 검토 순서 ① ② ③"),
        ],
        "memo": [
            ("reminders", "서류 원본 확인 후 반환"),
            ("reminders", "다음 회의에서 보완 사항 공유"),
            ("reminders", "시험 문서 — 외부 제출 금지"),
            ("reminders", "분리 보관한 장비 점검"),
        ],
    },
    "selection": {
        "body": [
            ("public_hearing", "설명회에서는 제안 내용과 예상되는 영향을 소개한 후 참석자의 의견을 차례로 듣습니다."),
            ("public_hearing", "제시된 의견은 찬반 여부만으로 분류하지 않고 이유와 개선 제안을 함께 정리해 공개합니다."),
            ("archive_transfer", "보존 기간이 끝나지 않은 기록물을 다른 부서로 이관할 때에는 목록과 수량을 함께 대조합니다."),
            ("archive_transfer", "문서철의 묶음이 느슨해진 경우 쪽 순서를 확인하고 빠진 자료가 없는지 살핀 뒤 인계합니다."),
            ("accessibility", "자료의 그림에는 내용을 설명하는 문장을 붙여 화면을 보기 어려운 이용자도 이해할 수 있게 합니다."),
            ("accessibility", "작은 글씨로 표시한 주석은 본문과 충분히 구분하고 인쇄했을 때에도 알아볼 수 있도록 작성합니다."),
            ("training_attendance", "교육 수료 여부는 출석 기록과 실습 수행 내역을 바탕으로 확인하며 누락된 기록은 별도로 검토합니다."),
        ],
        "table": [
            ("consultation_cells", "상담 유형: 시설 이용 절차 문의"),
            ("consultation_cells", "답변 요지: 예약 가능 시간과 이용 수칙 설명"),
            ("consultation_cells", "후속 연락: 신청인의 요청에 따라 서면 회신"),
            ("maintenance_cells", "점검 부위 / 결함 종류 / 긴급 보수 여부"),
            ("maintenance_cells", "배수로 낙엽 제거, 안내 표지 고정 상태 양호"),
            ("maintenance_cells", "교체 부품: 연결 밴드 8개, 고정 나사 16개"),
            ("training_cells", "교과목: 환경 자료 읽기와 측정 단위 이해"),
        ],
        "numeric": [
            ("procurement_numbers", "계약 보증금 875,400원; 납품 수량 117개"),
            ("procurement_numbers", "견적 비교: ㈜가상솔빛 ₩7,621,300"),
            ("weather_numbers", "최저 −3.7 ℃ / 최고 11.6 ℃ / 강수 2.8 ㎜"),
            ("sensor_numbers", "센서 표시 0.0085 ppm; 경보 설정 ≥ 0.0100 ppm"),
            ("reservation_numbers", "예약 번호 20261019-083 / 이용 13:40~16:15"),
        ],
        "memo": [("handover", "인계 목록과 실제 물품 대조")],
    },
}


def sources_for(split):
    """작성 순서를 고정하고 문서/템플릿 가족을 파생 전에 배정한다."""
    if split not in SOURCES:
        raise ValueError("이번 생성기는 train/selection만 만들며 final은 만들지 않습니다")
    rows = []
    for category, texts in SOURCES[split].items():
        for index, (family, text) in enumerate(texts, 1):
            source_id = f"{split}-{category}-{index:03d}"
            critical = []
            if any(char.isdigit() for char in text):
                critical.append("numbers")
            if "원" in text and category in {"table", "numeric"} or "₩" in text:
                critical.append("money")
            if family in {"deadlines", "reservation_numbers"}:
                critical.append("date")
            if family in {"water_cells", "measurement", "dimensions", "thresholds", "weather_numbers", "sensor_numbers"}:
                critical.append("units")
            rows.append({"source_id": source_id, "source_group_id": source_id,
                         "document_id": f"written-{family}", "template_family_id": family,
                         "split": split, "category": category, "text": text,
                         "critical_tags": critical})
    return rows
