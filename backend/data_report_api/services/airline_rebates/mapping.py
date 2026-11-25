"""Data capabilities supported by the HKG26003 wide-table adapter."""
from datetime import date, datetime
from decimal import Decimal

CATALOG_VERSION = 1

# Ordered projection of hive_trial.sql. A projection change must update this contract.
FIELDS = (
    ("order_id", (str, int)), ("issue_ticket_no", (str,)),
    ("segment_airport", (str,)), ("first_dep_time", (str, date, datetime)),
    ("segment_real_cabin", (str,)), ("issue_ticket_price", (Decimal, int)),
    ("issue_currency", (str,)), ("dep_airport", (str,)), ("arr_airport", (str,)),
    ("real_age_type_desc", (str,)), ("refund_flag_desc", (str,)),
    ("issue_ticket_no_status", (str, int)), ("refund_issue_flag", (str,)),
    ("issue_price_type_desc", (str,)), ("segment_dep_time", (str,)),
    ("segment_marketing_airline", (str,)), ("flt_status", (str,)),
)
HIVE_TYPES = {
    str: {"STRING_TYPE", "CHAR_TYPE", "VARCHAR_TYPE"},
    int: {"TINYINT_TYPE", "SMALLINT_TYPE", "INT_TYPE", "BIGINT_TYPE"},
    Decimal: {"DECIMAL_TYPE"},
    date: {"DATE_TYPE"},
    datetime: {"TIMESTAMP_TYPE"},
}
REQUIRED_COVERAGE = {
    "order_id", "issue_ticket_no", "segment_airport", "segment_real_cabin",
    "issue_ticket_price", "issue_currency", "segment_dep_time", "segment_marketing_airline",
}
ROUTE_FIELDS = ("segment_airport", "dep_airport", "arr_airport", "airport_code", "country_code")
CABIN_FIELDS = ("segment_real_cabin",)
AMOUNT_FIELDS = ("issue_ticket_price", "issue_currency")
TRIAL_MAPPING = {
    "period": ("segment_dep_time",), "agency": ("supplier_code",),
    "scope": ROUTE_FIELDS, "carrier": ("segment_marketing_airline",),
    "excluded": CABIN_FIELDS, "charter": ("issue_price_type_desc",),
    "infant": ("real_age_type_desc",), "domestic": ROUTE_FIELDS,
    "measure_only": CABIN_FIELDS, "measure_clients": ("issue_price_type_desc",),
    "origin": ("refund_issue_flag", "issue_ticket_no_status"),
    "regional_scope": ROUTE_FIELDS, "long": ROUTE_FIELDS, "short": ROUTE_FIELDS,
    "hkg_non": ROUTE_FIELDS, "mfm_non": ROUTE_FIELDS, "hkg_designated": ROUTE_FIELDS,
    "other_origin": (*ROUTE_FIELDS, "segment_marketing_airline"),
    "group_a": CABIN_FIELDS, "group_b": CABIN_FIELDS,
    "minimum": AMOUNT_FIELDS, "maximum": AMOUNT_FIELDS,
    "iata": ("supplier_code",), "revenue": AMOUNT_FIELDS,
}
EXACT_MAPPING = {
    "stock": ("issue_ticket_no",),
    "issue_complete": ("order_status", "issue_status"),
    "refund_void": ("issue_ticket_no_status", "flt_status", "refund_flag_desc"),
}
CONSTANTS = {"issue_date", "basis"}
FILTER_FIELDS = {"supplier_code", "order_status", "issue_status"}


def capability(group, key):
    if key in CONSTANTS or (group.startswith("tier-") and key in {"group_a", "group_b"}):
        return "constant", ()
    if key in EXACT_MAPPING:
        return "exact", EXACT_MAPPING[key]
    if key in TRIAL_MAPPING:
        return "trial", TRIAL_MAPPING[key]
    return "unmapped", ()


class MappingValidationError(ValueError):
    """A field contract message safe to show on the policy review page."""


def validate_projection(description):
    names = tuple(column[0].rsplit(".", 1)[-1].lower() for column in description)
    if names != tuple(name for name, _ in FIELDS):
        raise MappingValidationError("Hive 返回的字段或字段顺序与数据字典不一致")
    incompatible = [
        name for (name, allowed), column in zip(FIELDS, description)
        if not any(column[1] in HIVE_TYPES[value_type] for value_type in allowed)
    ]
    if incompatible:
        raise MappingValidationError("Hive 列类型不符合数据字典：" + "、".join(incompatible))


def validate_facts(records, airports):
    fields = {}
    if not records or any(len(row) != len(FIELDS) for row in records):
        raise ValueError("Hive 试算投影与字段字典不一致或无样本")
    for index, (name, types) in enumerate(FIELDS):
        values = [row[index] for row in records if row[index] is not None and row[index] != ""]
        invalid = sum(type(value) not in types or (
            isinstance(value, Decimal) and not value.is_finite()
        ) for value in values)
        fields[name] = {
            "expected": " / ".join(item.__name__ for item in types),
            "present": len(values), "invalid": invalid,
            "passed": invalid == 0 and (bool(values) or name not in REQUIRED_COVERAGE),
        }
    for name in ("airport_code", "country_code"):
        fields[name] = {"expected": "str", "passed": bool(airports)}
    return {"rows": len(records), "fields": fields}


REMOVABLE_RULES = {("eligibility", "agency")}


# Exact business concepts only. In particular, actual carriage date never maps to planned departure.
BUSINESS_FIELDS = {
    "航段计划起飞日期": ("segment_dep_time",), "航段计划起飞时间": ("segment_dep_time",),
    "航段实际承运航司": ("segment_operating_airline", "operating_airline"),
    "实际承运航司": ("segment_operating_airline", "operating_airline"),
    "航段实际舱位": ("segment_real_cabin",), "实际舱位": ("segment_real_cabin",),
    "票证前三位": ("issue_ticket_no",), "出票代理iata号": ("issuing_iata",),
    "出票日期": ("issue_ticket_time",), "始发机场": ("dep_airport",), "到达机场": ("arr_airport",),
    "航段起降机场": ("segment_airport",), "出票票面价": ("issue_ticket_price",),
    "币种": ("issue_currency",), "出票币种": ("issue_currency",),
}


REVIEW_FIELDS = {
    "segment_dep_time": ("航段计划起飞时间", (str,), "航段", "计划日期"),
    "segment_operating_airline": ("航段实际承运航司", (str,), "航段", "承运航司"),
    "operating_airline": ("实际承运航司", (str,), "宽表记录", "承运航司，逐段关系需人工核实"),
    "segment_real_cabin": ("航段实际舱位", (str,), "航段", "舱位条件"),
    "issue_ticket_no": ("票号", (str,), "客票", "票证前缀"),
    "issuing_iata": ("出票代理 IATA 号", (str,), "客票", "出票代理"),
    "issue_ticket_time": ("出票时间", (str, date, datetime), "客票", "出票日期"),
    "dep_airport": ("始发机场", (str,), "客票", "旅程始发"),
    "arr_airport": ("到达机场", (str,), "客票", "旅程到达"),
    "segment_airport": ("各航段起降机场", (str,), "航段", "航段航程"),
    "issue_ticket_price": ("出票票面价", (int, Decimal), "客票", "整票票面金额"),
    "issue_currency": ("出票币种", (str,), "客票", "出票金额币种"),
}


def review_field_metadata(name, hive_type):
    definition = REVIEW_FIELDS.get(name)
    if definition is None:
        return {}
    label, accepted, grain, scope = definition
    return {
        "label": label, "grain": grain, "scope": scope,
        "typeMatches": any(hive_type in HIVE_TYPES[kind] for kind in accepted),
    }


def model_fields(rule, available):
    label = "".join((rule.get("fieldLabel") or "").lower().split())
    concept = "".join((rule.get("businessConcept") or "").lower().split())
    candidates = BUSINESS_FIELDS.get(label) or BUSINESS_FIELDS.get(concept, ())
    if label in BUSINESS_FIELDS and concept in BUSINESS_FIELDS and BUSINESS_FIELDS[label] != BUSINESS_FIELDS[concept]:
        return ()
    if "实际" in label and any(word in label for word in ("日期", "时间", "乘机日")):
        return ()
    if any(word in label for word in ("净承运收入", "净收入", "结算收入")):
        return ()
    return tuple(field for field in candidates if available.get(field, {}).get("typeMatches") is True)


def review_cards(cards, profile):
    review = profile.get("mappingReview", {})
    validation = profile.get("mappingValidation", {})
    checked = validation.get("catalogVersion") == CATALOG_VERSION
    evidence = validation.get("fields", {}) if checked else {}
    available = {item["name"]: item for item in profile.get("mappingReference", {}).get("columns", [])}
    is_model = profile.get("source") == "model"
    for group in cards:
        for rule in group["conditions"]:
            kind, fields = capability(group["id"], rule["id"])
            if is_model:
                kind, fields = "unmapped", model_fields(rule, available)
            decision = review.get(f"{group['id']}/{rule['id']}", {})
            if decision.get("state") == "removed":
                status = "removed"
            elif decision.get("state") == "confirmed" and decision.get("field") and decision["field"] not in fields:
                status = "pending_registration"
            elif decision.get("state") == "missing":
                status = "missing"
            elif decision.get("state") == "found":
                status = "pending_registration"
            elif is_model and decision.get("state") == "confirmed":
                status = "pending_registration"
            elif is_model and len(fields) == 1:
                status = "unchecked"
            elif kind in {"constant", "unmapped"}:
                status = kind
            elif any(field in evidence and not evidence[field]["passed"] for field in fields):
                status = "failed"
            elif not checked or not validation.get("rows"):
                status = "unchecked"
            else:
                status = kind
            rule["dataMapping"] = {
                "status": status, "kind": kind, "fields": fields, "decision": decision,
                "removable": bool(rule.get("optionalReview")) if is_model else (group["id"], rule["id"]) in REMOVABLE_RULES,
                "checks": {field: evidence[field] for field in fields if field in evidence},
                "filterFields": [field for field in fields if field in FILTER_FIELDS],
            }
    return cards


def trial_ready(profile):
    validation = profile.get("mappingValidation", {})
    return (
        profile.get("source") != "model"
        and validation.get("catalogVersion") == CATALOG_VERSION
        and validation.get("rows", 0) > 0
        and all(field["passed"] for field in validation["fields"].values())
        and not blocked_trial_rules(profile)
    )


def blocked_trial_rules(profile):
    return any(
        (decision["state"] in {"missing", "found"} and capability(*key.split("/"))[1])
        or (decision["state"] == "confirmed" and decision.get("field")
            and decision["field"] not in capability(*key.split("/"))[1])
        for key, decision in profile.get("mappingReview", {}).items()
    )
