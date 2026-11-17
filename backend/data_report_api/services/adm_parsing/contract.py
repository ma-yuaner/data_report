"""Server-owned shape, money and source validation. Model flags are not trusted."""
import json
import re
from datetime import date
from decimal import Decimal

VERSION = "adm-extraction/1.0"
ADM_FIELDS = ("number", "issuer", "supplierName", "airline", "issuedDate", "amount", "currency", "reason", "dueDate")
LINE_FIELDS = ("lineId", "transactionNumber", "pnrs", "ticketNumber", "ticketType", "flight", "flightDate", "origin", "destination", "gds", "pcc", "amount", "currency")
CURRENCIES = set("CNY HKD USD EUR GBP JPY SGD AUD CAD KRW THB TWD MYR IDR AED".split())
MONEY = re.compile(r"(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?\Z")


def strict_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))


def template():
    return {"schemaVersion": VERSION, "adm": dict.fromkeys(ADM_FIELDS), "lines": [], "evidence": [], "conflicts": []}


def validate(value, segments):
    issues = []

    def issue(code, path, message, level="error"):
        issues.append({"code": code, "path": path, "message": message, "level": level})

    def keys(record, expected, path):
        if not isinstance(record, dict):
            issue("INVALID_TYPE", path, "必须为对象")
            return False
        if set(record) != set(expected):
            issue("INVALID_KEYS", path, "固定JSON键缺失或有额外字段")
        return True

    paths = {}
    def fields(record, names, path, required=()):
        if not keys(record, names, path):
            return
        for key in names:
            v, p = record.get(key), path + "/" + key
            paths[p] = v
            if key in {"pnrs", "ticketType"}:
                continue
            if key in required and (not isinstance(v, str) or not v.strip()):
                issue("REQUIRED_FIELD", p, "必填字段未提取到")
            elif v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 2000):
                issue("INVALID_VALUE", p, "须为非空字符串或null，且不超过2000字")
            if v is None:
                continue
            if key == "amount" and (not isinstance(v, str) or not MONEY.fullmatch(v)):
                issue("INVALID_AMOUNT", p, "金额须为非负十进制字符串，最多15位整数和4位小数")
            if key == "currency" and (not isinstance(v, str) or v not in CURRENCIES):
                issue("INVALID_CURRENCY", p, "币种不在支持字典")
            if key.endswith("Date"):
                try:
                    if not isinstance(v, str) or date.fromisoformat(v).isoformat() != v:
                        raise ValueError()
                except (ValueError, TypeError):
                    issue("INVALID_DATE", p, "须为真实日期YYYY-MM-DD")
        if (record.get("amount") is None) != (record.get("currency") is None):
            issue("AMOUNT_CURRENCY_PAIR", path, "金额与币种须同时存在或同时缺失")

    if not keys(value, ("schemaVersion", "adm", "lines", "evidence", "conflicts"), ""):
        return issues
    if value.get("schemaVersion") != VERSION:
        issue("INVALID_VERSION", "/schemaVersion", "解析契约版本不支持")
    adm = value.get("adm")
    fields(adm, ADM_FIELDS, "/adm", ("number", "issuer", "amount", "currency"))
    for name in ("lines", "evidence", "conflicts"):
        if not isinstance(value.get(name), list) or len(value[name]) > 2000:
            issue("INVALID_ARRAY", "/" + name, "必须为数组且不超过2000项")
    lines = value.get("lines") if isinstance(value.get("lines"), list) else []
    ids = set()
    for i, line in enumerate(lines[:2000]):
        path = f"/lines/{i}"
        fields(line, LINE_FIELDS, path, ("lineId",))
        if not isinstance(line, dict):
            continue
        line_id = line.get("lineId")
        if not isinstance(line_id, str) or line_id in ids:
            issue("DUPLICATE_LINE", path, "明细编号必须为唯一字符串")
        elif isinstance(line_id, str):
            ids.add(line_id)
        pnrs = line.get("pnrs")
        if not isinstance(pnrs, list) or any(not isinstance(p, str) or not re.fullmatch(r"[A-Z0-9]{6}", p) for p in pnrs) or len(pnrs) != len(set(p for p in pnrs if isinstance(p, str))):
            issue("INVALID_PNR", path + "/pnrs", "PNR须为去重的6位大写字母数字数组")
        if not isinstance(line.get("ticketType"), str) or line["ticketType"] not in {"real", "virtual", "unknown"}:
            issue("INVALID_TICKET_TYPE", path + "/ticketType", "票号类型无效")
        if line.get("ticketType") == "virtual":
            issue("VIRTUAL_TICKET", path, "虚拟票号不能匹配真实出票", "warning")
        if isinstance(adm, dict) and line.get("currency") and line.get("currency") != adm.get("currency"):
            issue("MIXED_CURRENCY", path, "明细与正式总额币种不同，不直接合计或换汇", "warning")
    evidence = value.get("evidence") if isinstance(value.get("evidence"), list) else []
    sources = {s["id"]: s for s in segments}
    proven = set()
    proven_quotes = {}
    normal = lambda s: re.sub(r"\s+", "", str(s)).replace(",", "").casefold()
    for i, item in enumerate(evidence[:2000]):
        if not keys(item, ("path", "segmentId", "quote"), f"/evidence/{i}"):
            continue
        path, segment_id, quote = item.get("path"), item.get("segmentId"), item.get("quote")
        if not isinstance(path, str) or not isinstance(segment_id, str) or path not in paths or segment_id not in sources or not isinstance(quote, str) or not quote.strip():
            issue("INVALID_EVIDENCE", f"/evidence/{i}", "字段路径、原件段落或原文摘录无效")
        elif normal(quote) not in normal(sources[segment_id]["text"]):
            issue("QUOTE_NOT_FOUND", path, "来源摘录与实际上传原文不符")
        elif path in {"/adm/number", "/adm/issuer", "/adm/amount", "/adm/currency"} and paths[path] is not None and normal(paths[path]) not in normal(quote):
            issue("VALUE_NOT_IN_SOURCE", path, "必填字段值未在所引原文中找到")
        else:
            proven.add(path)
            proven_quotes.setdefault(path, []).append(quote)
    for key in ("number", "issuer", "amount", "currency"):
        if "/adm/" + key not in proven:
            issue("REQUIRED_EVIDENCE", "/adm/" + key, "必填字段须引用有效原文")
    for i, line in enumerate(lines[:2000]):
        if not isinstance(line, dict):
            continue
        for key in ("pnrs", "ticketNumber", "gds", "pcc"):
            v, path = line.get(key), f"/lines/{i}/{key}"
            if not v:
                continue
            values = v if isinstance(v, list) else [v]
            quotes = normal(" ".join(proven_quotes.get(path, [])))
            if path not in proven or any(not isinstance(v, str) or normal(v) not in quotes for v in values):
                issue("TRANSACTION_EVIDENCE", path, "PNR、票号、系统和PCC有值时必须能在所引原文找到，不能推造交易历史")
    conflicts = value.get("conflicts") if isinstance(value.get("conflicts"), list) else []
    for i, item in enumerate(conflicts[:2000]):
        if not keys(item, ("path", "description", "segmentIds"), f"/conflicts/{i}"):
            continue
        if not isinstance(item.get("path"), str) or item["path"] not in paths or not isinstance(item.get("description"), str) or not item["description"].strip() or not isinstance(item.get("segmentIds"), list) or len(set(s for s in item.get("segmentIds", []) if isinstance(s, str))) < 2 or any(not isinstance(s, str) or s not in sources for s in item.get("segmentIds", [])):
            issue("INVALID_CONFLICT", f"/conflicts/{i}", "冲突必须引用两个不同的有效来源段落")
        else:
            issue("SOURCE_CONFLICT", item["path"], item["description"], "warning")
    if isinstance(adm, dict):
        for key in ("supplierName", "airline", "issuedDate", "reason", "dueDate"):
            if adm.get(key) is None:
                issue("OPTIONAL_MISSING", "/adm/" + key, "未提供，待人工核对", "warning")
        if not lines:
            issue("NO_LINES", "/lines", "未提取明细，不代表材料完整", "warning")
        valid_money = lambda x: isinstance(x, str) and MONEY.fullmatch(x)
        if valid_money(adm.get("amount")) and lines and all(isinstance(l, dict) and valid_money(l.get("amount")) and l.get("currency") == adm.get("currency") for l in lines):
            if sum((Decimal(l["amount"]) for l in lines), Decimal(0)) != Decimal(adm["amount"]):
                issue("TOTAL_MISMATCH", "/adm/amount", "同币种明细合计与正式总额不同", "warning")
    return issues
