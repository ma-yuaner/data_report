"""Contract for the first two Ctrip daily-sales monitoring scopes."""
from decimal import Decimal, InvalidOperation

TEMPLATE = "DAILY_SEGMENT_THRESHOLD"
EVENT = "DAILY_SEGMENT_THRESHOLD_ALERT"
LINES = {
    "LEYOU_1": (1, "乐游1部", ("乐游携程一部", "乐游携程一部公布", "乐游携程一部特惠")),
    "HONGKONG_1": (2, "香港1部", ("香港携程一部", "香港携程公布", "香港携程一部特惠")),
}


def validate_daily_conditions(conditions):
    fields = {}
    for item in conditions:
        code = item["fieldCode"]
        if code in fields or item.get("groupNo", 1) != 1 or item.get("conditionRole", "INCLUDE") != "INCLUDE":
            raise ValueError("日累计条件不可重复、分组或排除")
        fields[code] = item
    if set(fields) - {"business_line", "segment_total", "reference_limit"} or not {"business_line", "segment_total"} <= set(fields):
        raise ValueError("日累计规则必须包含业务线和提醒阈值")
    line = fields["business_line"]
    if line["operatorCode"] != "EQ" or not isinstance(line["value"], str) or line["value"] not in LINES:
        raise ValueError("请选择乐游1部或香港1部")
    for code, operator in (("segment_total", "GTE"), ("reference_limit", "EQ")):
        if code not in fields:
            continue
        item = fields[code]
        try:
            number = Decimal(str(item["value"]))
            valid = not isinstance(item["value"], bool) and number.is_finite() and 1 <= number <= 1_000_000_000 and number == number.to_integral_value()
        except (InvalidOperation, ValueError, TypeError):
            valid = False
        if item["operatorCode"] != operator or not valid:
            raise ValueError("航段阈值必须为1至10亿的整数；提醒使用大于等于")
        item["value"] = int(number)
    if "reference_limit" in fields and fields["reference_limit"]["value"] < fields["segment_total"]["value"]:
        raise ValueError("参考上限不能小于提醒阈值")
    return LINES[line["value"]][0]
