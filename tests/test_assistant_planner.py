import pytest

from app.assistant.errors import InputError
from app.assistant.schema.planning import Plan
from app.assistant.services.planner import validate_plan


def test_plan_cannot_invent_constant_or_map_a_nonexistent_column():
    items = [{"id": "p1", "text": "Kính gửi {{name}}"}]
    records = [{"values": {"Name": "Alice"}, "source": {"row": 2}}]
    with pytest.raises(InputError, match="Hằng số"):
        validate_plan(Plan(constants={"name": "Invented person"}), "Điền theo dữ liệu.", items, records)
    with pytest.raises(InputError, match="cột không tồn tại"):
        validate_plan(Plan(mapping={"name": "Not in source"}), "Điền theo dữ liệu.", items, records)


def test_plain_template_rewrite_must_keep_fixed_wording():
    from app.assistant.schema.planning import Rewrite

    items = [{"id": "p1", "text": "Kính gửi [Name]"}]
    records = [{"values": {"Name": "Alice"}}]
    with pytest.raises(InputError, match="câu chữ cố định"):
        validate_plan(
            Plan(mapping={"Name": "Name"}, rewrites=[Rewrite(paragraph_id="p1", text="Quyết định sa thải {{Name}}")]),
            "Điền theo dữ liệu.",
            items,
            records,
        )


def test_negative_skip_instruction_is_not_treated_as_permission():
    from app.assistant.services.planner import rule_plan

    items = [{"text": "{{Name}}"}]
    records = [{"values": {"Name": "Alice"}}]
    assert not rule_plan("Không được bỏ qua hồ sơ thiếu dữ liệu.", items, records).skip_incomplete
    assert rule_plan("Bỏ qua hồ sơ thiếu dữ liệu.", items, records).skip_incomplete
