"""Server-owned shape, money and source validation. Model flags are not trusted."""
import json
import re
from datetime import date
from decimal import Decimal

VERSION = "adm-extraction/1.2"
ADM_FIELDS = ("number", "airlineCode", "issuedDate", "amount", "currency", "reason", "dueDate", "reportingDate")
LINE_FIELDS = ("lineId", "transactionNumber", "pnrs", "ticketNumber", "ticketType", "flight", "flightDate", "origin", "destination", "gds", "pcc", "amount", "currency", "airlinePnrs", "gdsPnrs", "transactionDate", "action", "amountPurpose", "commissionRate", "commissionAmount", "commissionCurrency", "amountText")
CURRENCIES = set("CNY HKD USD EUR GBP JPY SGD AUD CAD KRW THB TWD MYR IDR AED".split())
MONEY = re.compile(r"(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?\Z")


def virtual_ticket_text(text):
    # UNTICKETED plus a fictitious passenger name is not a declaration of a virtual ticket.
    return bool(re.search(
        r"\b(?:TKT|ticket)\s+(?:number\b|no\b\.?|[0-9]{3}[- ]?[0-9]{10}\b).{0,100}\b(?:fictitious|virtual)\b|\bticket\s+is\s+(?:fictitious|virtual)\b|虚拟票号",
        text, re.I | re.S,
    ))


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
            if key in {"pnrs", "airlinePnrs", "gdsPnrs", "ticketType"}:
                if isinstance(v, list):
                    for index, item in enumerate(v):
                        paths[f"{p}/{index}"] = item
                continue
            if key in required and (not isinstance(v, str) or not v.strip()):
                issue("REQUIRED_FIELD", p, "必填字段未提取到")
            elif v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 2000):
                issue("INVALID_VALUE", p, "须为非空字符串或null，且不超过2000字")
            if v is None:
                continue
            if key == "airlineCode" and (not isinstance(v, str) or not re.fullmatch(r"(?:[0-9]{3}|[A-Z0-9]{2})", v)):
                issue("INVALID_AIRLINE_CODE", p, "须为原件Airline Code的三位数字或两位航司编码，不填航司名称")
            if key in {"amount", "commissionAmount", "commissionRate"} and (not isinstance(v, str) or not MONEY.fullmatch(v)):
                issue("INVALID_AMOUNT", p, "金额须为非负十进制字符串，最多15位整数和4位小数")
            if key in {"currency", "commissionCurrency"} and (not isinstance(v, str) or v not in CURRENCIES):
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
    fields(adm, ADM_FIELDS, "/adm", ("number", "amount", "currency"))
    for name in ("lines", "evidence", "conflicts"):
        if not isinstance(value.get(name), list) or len(value[name]) > 2000:
            issue("INVALID_ARRAY", "/" + name, "必须为数组且不超过2000项")
    lines = value.get("lines") if isinstance(value.get("lines"), list) else []
    mixed = []
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
        for pnr_key in ("pnrs", "airlinePnrs", "gdsPnrs"):
            pnrs = line.get(pnr_key)
            if not isinstance(pnrs, list) or any(not isinstance(p, str) or not re.fullmatch(r"[A-Z0-9]{6}", p) for p in pnrs) or len(pnrs) != len(set(p for p in pnrs if isinstance(p, str))):
                issue("INVALID_PNR", path + "/" + pnr_key, "编码须为去重的6位大写字母数字数组")
        if not isinstance(line.get("ticketType"), str) or line["ticketType"] not in {"real", "virtual", "unknown"}:
            issue("INVALID_TICKET_TYPE", path + "/ticketType", "票号类型无效")
        if line.get("ticketType") == "virtual":
            issue("VIRTUAL_TICKET", path, "虚拟票号不能匹配真实出票", "warning")
        if isinstance(adm, dict) and line.get("amountPurpose") == "admCharge" and line.get("currency") and line.get("currency") != adm.get("currency"):
            mixed.append(path)
    if mixed:
        issue("MIXED_CURRENCY", "/lines", f"{len(mixed)}条正式罚单明细与主单币种不同，不合计或换汇", "warning")
    from .table_sources import bindings, fee_from_binding, fee_text_proven
    bound_fees = {i: fee_from_binding(b) for i, b in bindings(value, segments).items()}
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
            issue("INVALID_EVIDENCE", f"/evidence/{i}", "；".join(
                reason for condition, reason in (
                    (not isinstance(path, str) or path not in paths, "字段路径不存在"),
                    (not isinstance(segment_id, str) or segment_id not in sources, "原件段落ID不存在"),
                    (not isinstance(quote, str) or not quote.strip(), "原文摘录为空"),
                ) if condition
            ))
        elif normal(quote) not in normal(sources[segment_id]["text"]):
            issue("QUOTE_NOT_FOUND", path, "来源摘录与实际上传原文不符")
        elif path in {"/adm/number", "/adm/amount", "/adm/currency"} and paths[path] is not None and normal(paths[path]) not in normal(quote):
            issue("VALUE_NOT_IN_SOURCE", path, "必填字段值未在所引原文中找到")
        else:
            proven.add(path)
            proven_quotes.setdefault(path, []).append(quote)
    for path in list(proven):
        match = re.fullmatch(r"(/lines/[0-9]+/(?:pnrs|airlinePnrs|gdsPnrs))/[0-9]+", path)
        if match:
            parent = match[1]
            proven.add(parent)
            proven_quotes.setdefault(parent, []).extend(proven_quotes[path])
    if isinstance(adm, dict) and adm.get("airlineCode"):
        quote = " ".join(proven_quotes.get("/adm/airlineCode", []))
        if "/adm/airlineCode" not in proven or normal(adm["airlineCode"]) not in normal(quote) or not re.search(r"(?:Airline\s+Code(?:\s*/\s*Name)?|航司编码)\s*[:：]?\s*" + re.escape(str(adm["airlineCode"])) + r"(?![A-Z0-9])", quote, re.I):
            issue("AIRLINE_CODE_EVIDENCE", "/adm/airlineCode", "航司编码须引用原件Airline Code及编码原文")
    for key in ("number", "amount", "currency"):
        if "/adm/" + key not in proven:
            issue("REQUIRED_EVIDENCE", "/adm/" + key, "必填字段须引用有效原文")
    for i, line in enumerate(lines[:2000]):
        if not isinstance(line, dict):
            continue
        for key in ("pnrs", "airlinePnrs", "gdsPnrs", "ticketNumber", "gds", "pcc", "amount", "currency", "commissionRate", "commissionAmount", "commissionCurrency", "action", "amountText"):
            v, path = line.get(key), f"/lines/{i}/{key}"
            if not v:
                continue
            values = v if isinstance(v, list) else [v]
            quotes = normal(" ".join(proven_quotes.get(path, [])))
            def sourced(v):
                if not isinstance(v, str):
                    return False
                if key == "amountText" and bound_fees.get(i) and fee_text_proven(path, v, bound_fees[i], evidence):
                    return True
                if normal(v) in quotes:
                    return True
                if key == "ticketNumber" and re.fullmatch(r"[0-9]{13}", v):
                    raw_quote = " ".join(proven_quotes.get(path, []))
                    compact = re.sub(r"[\s-]", "", raw_quote)
                    return v in compact or ("airlinecode" in normal(raw_quote) and "serial" in normal(raw_quote) and v[:3] in quotes and v[3:] in quotes)
                return False
            if path not in proven or any(not sourced(v) for v in values):
                label = {"pnrs": "来源未明PNR", "airlinePnrs": "航司PNR", "gdsPnrs": "GDS编码", "ticketNumber": "票号", "gds": "GDS系统", "pcc": "PCC", "amount": "明细金额", "currency": "明细币种", "amountText": "原始费用", "action": "明细动作", "commissionRate": "佣金比例", "commissionAmount": "佣金金额", "commissionCurrency": "佣金币种"}[key]
                issue("TRANSACTION_EVIDENCE", path, label + "未找到有效原文证据；表格字段须核对同列的表头和单元格")
    conflicts = value.get("conflicts") if isinstance(value.get("conflicts"), list) else []
    for i, item in enumerate(conflicts[:2000]):
        if not keys(item, ("path", "description", "segmentIds"), f"/conflicts/{i}"):
            continue
        if not isinstance(item.get("path"), str) or item["path"] not in paths or not isinstance(item.get("description"), str) or not item["description"].strip() or not isinstance(item.get("segmentIds"), list) or len(set(s for s in item.get("segmentIds", []) if isinstance(s, str))) < 2 or any(not isinstance(s, str) or s not in sources for s in item.get("segmentIds", [])):
            issue("INVALID_CONFLICT", f"/conflicts/{i}", "冲突必须引用两个不同的有效来源段落")
        else:
            issue("SOURCE_CONFLICT", item["path"], item["description"], "warning")
    if isinstance(adm, dict):
        for key in ("airlineCode", "issuedDate", "reason", "dueDate"):
            if adm.get(key) is None:
                issue("OPTIONAL_MISSING", "/adm/" + key, "未提供，待人工核对", "warning")
        if not lines:
            issue("NO_LINES", "/lines", "未提取明细，不代表材料完整", "warning")
        valid_money = lambda x: isinstance(x, str) and MONEY.fullmatch(x)
        if valid_money(adm.get("amount")) and lines and all(isinstance(l, dict) and valid_money(l.get("amount")) and l.get("currency") == adm.get("currency") and l.get("amountPurpose") == "admCharge" for l in lines):
            if sum((Decimal(l["amount"]) for l in lines), Decimal(0)) != Decimal(adm["amount"]):
                issue("TOTAL_MISMATCH", "/adm/amount", "同币种明细合计与正式总额不同", "warning")
    if isinstance(adm, dict):
        for key, labels in (("issuedDate", r"Issue Date|Issued Date|开具日期"), ("reportingDate", r"Reporting Date|报表日期"), ("dueDate", r"Due Date|Deadline|截止日期|到期日")):
            val = adm.get(key)
            if isinstance(val, str) and val:
                qs = proven_quotes.get("/adm/" + key, [])
                if not qs or not any(re.search(labels, q, re.I) for q in qs):
                    issue("DATE_ROLE_EVIDENCE", "/adm/" + key, "日期必须引用对应日期标签原文，不能用报表日或航班日替代")
                else:
                    try:
                        d = date.fromisoformat(val) if isinstance(val, str) else None
                    except ValueError:
                        d = None
                    tokens = {val}
                    if d:
                        tokens.update((d.strftime("%d/%m/%Y"), d.strftime("%d-%m-%Y")))
                    if not any(any(t in q for t in tokens if isinstance(t, str)) for q in qs):
                        issue("DATE_VALUE_EVIDENCE", "/adm/" + key, "日期值与所引原文不符；歧义日期请保留缺失并核对")
        if adm.get("issuedDate") and adm.get("dueDate") and isinstance(adm["issuedDate"], str) and isinstance(adm["dueDate"], str) and adm["dueDate"] < adm["issuedDate"]:
            issue("DATE_ORDER", "/adm/dueDate", "截止早于开具日期，请人工核对", "warning")
        aq = " ".join(proven_quotes.get("/adm/amount", []))
        if aq and not re.search(r"Total|Amount[ ,:]|正式金额|罚单金额", aq, re.I):
            issue("ADM_AMOUNT_ROLE", "/adm/amount", "正式金额必须引用ADM总额上下文，不能使用每段费率、票价或佣金")
    document_numbers = set()
    for segment in segments:
        text = segment["text"]
        if re.search(r"ADMA|ADM Properties", text, re.I):
            document_numbers.update(re.findall(r"Document Number\s+(\d{10})(?!\d)", text, re.I))
    if len(document_numbers) > 1:
        issue("MULTIPLE_ADM", "/adm/number", "材料包含多个ADM单号，请按单拆分来件")
    elif document_numbers and isinstance(adm, dict) and adm.get("number") not in document_numbers:
        issue("ADM_NUMBER_MISMATCH", "/adm/number", "提取单号与ADM原件的Document Number不一致")
    virtual_source = any(virtual_ticket_text(seg["text"]) for seg in segments)
    for i, line in enumerate(lines[:2000]):
        if not isinstance(line, dict):
            continue
        path = f"/lines/{i}"
        if line.get("amountPurpose") not in {None, "admCharge", "unitPenalty", "ticketTotal", "other", "unknown"}:
            issue("AMOUNT_PURPOSE", path + "/amountPurpose", "金额用途无效")
        if line.get("amount") is not None and line.get("amountPurpose") in {None, "unknown"}:
            issue("AMOUNT_PURPOSE_UNKNOWN", path, "明细金额用途待核对，不参与罚单合计", "warning")
        if (line.get("commissionAmount") is None) != (line.get("commissionCurrency") is None):
            issue("COMMISSION_PAIR", path, "佣金金额和币种须同时提供")
        rate = line.get("commissionRate")
        if isinstance(rate, str) and MONEY.fullmatch(rate) and Decimal(rate) > 100:
            issue("COMMISSION_RATE", path + "/commissionRate", "佣金比例按百分数记录，范围0至100")
        if virtual_source and line.get("ticketNumber") and line.get("ticketType") != "virtual":
            issue("VIRTUAL_TICKET_REQUIRED", path + "/ticketType", "材料声明虚拟票号，禁止标为真实票号；混合材料需拆分核对")
        ticket = line.get("ticketNumber")
        if ticket is not None and (not isinstance(ticket, str) or not re.fullmatch(r"\d{13}", ticket)):
            issue("TICKET_FORMAT", path + "/ticketNumber", "票号须为13位数字，缺失不可补造")
        for key, label in (("airlinePnrs", r"(?<![A-Z_])RLOC(?![A-Z_])|airline.{0,12}(?:PNR|record)|航司.*(?:PNR|编码)"), ("gdsPnrs", r"GDS_RLOC|Booking Ref|GDS.{0,12}(?:PNR|record)|GDS编码")):
            if line.get(key) and not re.search(label, " ".join(proven_quotes.get(path + "/" + key, [])), re.I):
                issue("PNR_ROLE_EVIDENCE", path + "/" + key, "已分类编码须引用对应列名或来源标识；无法确定请放入来源未明PNR")
        if line.get("pnrs"):
            issue("PNR_ROLE_UNKNOWN", path + "/pnrs", "来源未明确的PNR单独保留，不用于自动恢复", "warning")
    unknown_fees = [index for index, fee in bound_fees.items() if fee and fee["currency"] is None and index < len(lines)
                    and isinstance(lines[index], dict) and lines[index].get("currency") is None and lines[index].get("amount") is None
                    and fee_text_proven(f"/lines/{index}/amountText", lines[index].get("amountText"), fee, evidence)]
    if unknown_fees:
        issue("ATTACHMENT_FEE_CURRENCY_UNKNOWN", "/lines", f"{len(unknown_fees)}条附件费用已保留原值和列名，但未明确币种；不根据$猜USD、不换汇、不与主单合计", "warning")
    return issues
