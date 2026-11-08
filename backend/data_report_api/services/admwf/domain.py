"""Pure ADM input validation and money calculation."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .policy import AdmError


TWO_PLACES = Decimal("0.01")
ISSUER_TYPES = frozenset({"SUPPLIER", "PLATFORM", "AIRLINE"})
OPTIONAL_LINE_TEXT = (
    "otaCode", "otaName", "otaOrderNo", "supplierCode", "supplierName",
    "airlineCode", "airlineName", "ticketNo", "pnr", "investigationNote",
)


def text(value, field, maximum, required=True):
    result = str(value or "").strip()
    if required and not result:
        raise AdmError(f"{field}不能为空")
    if len(result) > maximum:
        raise AdmError(f"{field}不能超过{maximum}个字符")
    return result or None


def money(value, field):
    try:
        result = Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise AdmError(f"{field}格式无效") from None
    if result < 0:
        raise AdmError(f"{field}不能为负数")
    return result


def allocate_cny_amounts(amounts, rate):
    """Convert allocated original amounts and put the cent residual on the last non-zero line."""
    values = [Decimal(str(value)) for value in amounts]
    fx_rate = Decimal(str(rate))
    target = (sum(values, Decimal("0.00")) * fx_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    converted = [(value * fx_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) for value in values]
    if converted:
        residual_index = next((index for index in range(len(values) - 1, -1, -1) if values[index] > 0), len(values) - 1)
        converted[residual_index] += target - sum(converted, Decimal("0.00"))
    return target, converted


def business_date(value, field):
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise AdmError(f"{field}格式应为YYYY-MM-DD") from None


def business_datetime(value, field):
    raw = str(value or "").strip().replace("T", " ")
    try:
        result = datetime.fromisoformat(raw)
    except ValueError:
        raise AdmError(f"{field}格式无效") from None
    if result.tzinfo is not None:
        raise AdmError(f"{field}不接受带时区的值")
    return result.replace(microsecond=0)


def normalize_line(raw, rate, position=1):
    if not isinstance(raw, dict):
        raise AdmError(f"第{position}条明细格式无效")
    try:
        fx_rate = Decimal(str(rate))
    except (InvalidOperation, TypeError, ValueError):
        raise AdmError("冻结汇率无效") from None
    if fx_rate <= 0:
        raise AdmError("冻结汇率必须大于0")
    amount = money(raw.get("originalAmount"), f"第{position}条明细原币金额")
    line = {
        "originalAmount": amount,
        "cnyAmount": (amount * fx_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
        "departmentCode": text(raw.get("departmentCode"), f"第{position}条业务部门编码", 64),
        "departmentName": text(raw.get("departmentName"), f"第{position}条业务部门名称", 200),
        "leaderId": raw.get("leaderId"),
        "leaderName": text(raw.get("leaderName"), f"第{position}条负责组长", 100),
        "diffTypeCode": text(raw.get("diffTypeCode"), f"第{position}条差异类型编码", 64),
        "diffTypeName": text(raw.get("diffTypeName"), f"第{position}条差异类型名称", 200),
        "differenceReason": text(raw.get("differenceReason"), f"第{position}条细分差异原因", 1000),
    }
    try:
        line["leaderId"] = int(line["leaderId"])
    except (TypeError, ValueError):
        raise AdmError(f"第{position}条负责组长无效") from None
    limits = {"otaCode": 64, "otaName": 200, "otaOrderNo": 300, "supplierCode": 64,
              "supplierName": 200, "airlineCode": 32, "airlineName": 100,
              "ticketNo": 500, "pnr": 500, "investigationNote": 10000}
    for key in OPTIONAL_LINE_TEXT:
        line[key] = text(raw.get(key), f"第{position}条{key}", limits[key], required=False)
    return line


def normalize_create(body, rate):
    if not isinstance(body, dict):
        raise AdmError("请求内容格式无效")
    issuer_type = text(body.get("issuerType"), "下发方类型", 32)
    if issuer_type not in ISSUER_TYPES:
        raise AdmError("下发方类型必须为供应商、平台或航司")
    currency = text(body.get("currency"), "主单原币币种", 3).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise AdmError("主单原币币种须为3位字母编码")
    original_amount = money(body.get("originalAmount"), "主单原币总金额")
    try:
        fx_rate = Decimal(str(rate))
    except (InvalidOperation, TypeError, ValueError):
        raise AdmError("冻结汇率无效") from None
    if fx_rate <= 0:
        raise AdmError("冻结汇率必须大于0")
    raw_lines = body.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise AdmError("主单至少需要一条明细")
    lines = [normalize_line(raw, fx_rate, position) for position, raw in enumerate(raw_lines, 1)]
    if sum((line["originalAmount"] for line in lines), Decimal("0.00")) != original_amount:
        raise AdmError("全部明细原币金额之和必须等于主单原币总金额")
    cny_amount, allocated_cny = allocate_cny_amounts(
        [line["originalAmount"] for line in lines], fx_rate,
    )
    for line, line_cny in zip(lines, allocated_cny):
        line["cnyAmount"] = line_cny
    return {
        "admNo": text(body.get("admNo"), "ADM单号", 100),
        "issuerType": issuer_type,
        "issuerCode": text(body.get("issuerCode"), "下发方编码", 64, required=False),
        "issuerName": text(body.get("issuerName"), "下发方名称", 200),
        "currency": currency,
        "originalAmount": original_amount,
        "cnyAmount": cny_amount,
        "issuedDate": business_date(body.get("issuedDate"), "下发日期"),
        "replyDeadline": business_datetime(body.get("replyDeadline"), "主单回复截止时间"),
        "remark": text(body.get("remark"), "主单备注", 1000, required=False),
        "lines": lines,
    }
