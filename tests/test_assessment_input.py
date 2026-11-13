"""Only filtered case signals and general HR rules may leave the assessment boundary."""

import json

import pytest

from app.services.assessment_input import UnsafeAssessmentPolicy, prepare_input


def case_data():
    return {
        "name": "Nguyễn Văn An",
        "employee_id": "MP00123",
        "code": "CASE-456",
        "department": "Khoa Tim Mạch",
        "explanation": (
            "Nguyễn Văn An MP00123 tại Khoa Tim Mạch: máy lỗi không ghi nhận. "
            "Liên hệ test@example.invalid, 0912345678, https://internal.invalid/CASE-456."
        ),
        "shift": "Ca riêng 08:00-17:00",
        "punch": "Vào",
        "date": "2026-11-14",
    }


def test_input_contains_no_case_identifiers_ocr_or_history():
    data = case_data()
    data.update(ocr_text="private OCR", history={"employee": "private history"})
    payload = prepare_input(data, {"DEVICE_ERROR": {"description": "Máy lỗi không ghi nhận."}}, 2)
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    for private in (
        "nguyễn",
        "nguyen",
        "mp00123",
        "case-456",
        "tim mach",
        "test@example",
        "0912345678",
        "internal.invalid",
        "08:00",
        "2026-11-14",
        "private ocr",
        "private history",
    ):
        assert private not in serialized
    assert "may loi khong ghi nhan" in payload["case"]["explanation_signals"]
    assert payload["case"]["evidence"] == [{"evidence_ref": 1}, {"evidence_ref": 2}]
    assert payload["case"]["has_shift"] is True


@pytest.mark.parametrize("description", ["Chọn cho MP00123", "Nhân viên Nguyễn Văn An", "Gửi test@example.invalid"])
def test_identifying_rule_text_is_blocked(description):
    with pytest.raises(UnsafeAssessmentPolicy):
        prepare_input(case_data(), {"DEVICE_ERROR": {"description": description}}, 1)
