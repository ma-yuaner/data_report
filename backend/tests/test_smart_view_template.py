from datetime import datetime

import pytest

from data_report_api.services.smart_view_template import SmartViewTemplateService


def test_template_payload_accepts_private_or_public_json_config():
    name, encoded, is_public = SmartViewTemplateService._payload({
        "name": " 航司平台利润 ",
        "value": {"groups": ["airline", "platform"]},
        "isPublic": True,
    })

    assert name == "航司平台利润"
    assert encoded == '{"groups":["airline","platform"]}'
    assert is_public is True


def test_template_payload_rejects_invalid_scope_and_config():
    with pytest.raises(ValueError, match="模板类型"):
        SmartViewTemplateService._scope("unknown")
    with pytest.raises(ValueError, match="模板配置"):
        SmartViewTemplateService._payload({"name": "模板", "value": ["field"]})


def test_public_template_marks_owner_and_visibility():
    row = {
        "id": 7, "scope_code": "detail-fields", "template_name": "公共明细",
        "config_json": '{"fields":["issueId","otaOrderNo"]}',
        "owner_user_id": 18, "owner_name_snapshot": "张三", "is_public": 1,
        "updated_at": datetime(2026, 10, 19, 17, 0),
    }

    public = SmartViewTemplateService._public(row, user_id=20)

    assert public["value"]["fields"] == ["issueId", "otaOrderNo"]
    assert public["isPublic"] is True
    assert public["isOwner"] is False
    assert public["ownerName"] == "张三"
