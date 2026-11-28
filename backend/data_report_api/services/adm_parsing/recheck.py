"""Deterministic source-bound compatibility repair. Never calls a model or invents evidence."""
import copy
import re
from datetime import datetime
from decimal import Decimal

from .contract import ADM_LIST_FIELDS, ARC_MEMO, CURRENCIES, GDS_PNR_ROLE_LABEL, LINE_FIELDS, MONEY, VERSION, virtual_ticket_text
from .table_sources import bind_sources

VALIDATION_VERSION = "adm-validation/2.8"
REMOVED = {"/adm/issuer", "/adm/supplierName", "/adm/airline"}
CELL_GAP = r"[^\S\r\n]+"
AMOUNT_CELL = MONEY.pattern.removesuffix(r"\Z")
BSP_TOTAL = re.compile(
    r"^Agent Input" + CELL_GAP + r"Airline Input" + CELL_GAP + r"Difference[^\S\r\n]*\r?\n"
    + "".join(label + (CELL_GAP + AMOUNT_CELL) * 3 + r"[^\S\r\n]*\r?\n" for label in (
        "Fare", "Tax, Fees and Charges", "Commission", "Tax on Commission",
    ))
    + r"(?:Cancellation Penalty" + (CELL_GAP + AMOUNT_CELL) * 3 + r"[^\S\r\n]*\r?\n)?"
    + r"(?P<quote>Total,[^\S\r\n]+(?P<currency>[A-Z]{3})"
    + CELL_GAP + r"(?P<agent>" + AMOUNT_CELL + ")"
    + CELL_GAP + r"(?P<airline>" + AMOUNT_CELL + ")"
    + CELL_GAP + r"(?P<difference>" + AMOUNT_CELL + r"))[^\S\r\n]*\r?$",
    re.I | re.M,
)


def normal(value):
    return re.sub(r"\s+", "", str(value)).replace(",", "").casefold()


def bsp_row(adm, sources):
    """Identify the BSP main row by ADM number, not a date from an attachment."""
    number = adm.get("number")
    if not isinstance(number, str) or not re.fullmatch(r"[0-9]{10}", number):
        return None
    pattern = re.compile(
        r"^[ \t]*" + number + r"[ \t]+(?:Issued|Dispute[ \t]+Rejected)[ \t]+[^\r\n]*?[ \t]+(?P<kind>Issue|Refund)"
        r"[ \t]+(?P<date>[0-9]{2}/[0-9]{2}/[0-9]{4})[ \t]+[^\r\n]+\r?\n"
        r"[ \t]*" + CELL_GAP.join("ADM Number Status BSP Name Agent Code ADMA for Issue Date Amount,".split())
        + r"[^\r\n]+",
        re.I | re.M,
    )
    hits = [(s, m) for s in sources.values() for m in pattern.finditer(s["text"])]
    return hits[0] if len(hits) == 1 else None


def prefer_bsp_dates(adm, evidence, row):
    if not row:
        return []
    source, match = row
    try:
        issued = datetime.strptime(match["date"], "%d/%m/%Y").date()
    except ValueError:
        return []
    changes = []
    rebound = False
    for index, item in enumerate(evidence):
        if (not isinstance(item, dict) or item.get("path") != "/adm/issuedDate"
                or item.get("segmentId") != source["id"] or not isinstance(item.get("quote"), str)
                or not item["quote"].strip() or adm.get("issuedDate") != issued.isoformat()):
            continue
        quote = item["quote"]
        if (normal(quote) in normal(source["text"]) and match["date"] in quote
                and re.search(r"\bIssue Date\b", quote, re.I) and "RTDN" not in quote.upper()):
            continue
        evidence[index] = {**item, "quote": match[0]}
        rebound = True
    if rebound:
        changes.append({"code": "BSP_ISSUED_EVIDENCE", "path": "/adm/issuedDate", "segmentId": source["id"],
                        "message": "补全同一 BSP 主单数据行与 Issue Date 表头"})
    if issued.day <= 12:
        return changes
    path = "/adm/reportingDate"
    labels = re.findall(r"Reporting Date[^\S\r\n]*\r?\n[^\S\r\n]*[0-9]{7}[ \t]+([0-9]{2}/[0-9]{2}/[0-9]{4})", source["text"], re.I)
    if len(labels) != 1:
        return changes
    raw = labels[0]
    try:
        original = datetime.strptime(raw, "%m/%d/%Y").date()
        corrected = datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        return changes
    if original == corrected or adm.get("reportingDate") != original.isoformat():
        return changes
    if any(isinstance(item, dict) and item.get("path") == path and item.get("segmentId") == source["id"]
           and isinstance(item.get("quote"), str) and raw in item["quote"]
           and "reporting date" in item["quote"].casefold()
           and normal(item["quote"]) in normal(source["text"]) for item in evidence):
        adm["reportingDate"] = corrected.isoformat()
        changes.append({"code": "BSP_REPORTING_DATE_ORDER", "path": path, "segmentId": source["id"],
                        "message": "同一 BSP 主单开具日期已证实日/月/年；按报表日期原文纠正日月颠倒"})
    return changes


def prefer_bsp_total(adm, evidence, sources, row):
    amount, currency = adm.get("amount"), adm.get("currency")
    if not isinstance(amount, str) or not MONEY.fullmatch(amount) or not isinstance(currency, str) or currency not in CURRENCIES:
        return None
    totals = [(source["id"], match) for source in sources.values() for match in BSP_TOTAL.finditer(source["text"])]
    if len(totals) != 1:
        return None
    segment_id, total = totals[0]
    if row and sources[segment_id].get("fileId") != row[0].get("fileId"):
        return None
    difference = Decimal(total["difference"])
    delta = Decimal(total["airline"]) - Decimal(total["agent"])
    if row and row[1]["kind"].casefold() == "refund":
        delta = abs(delta)
    if (total["currency"].upper() != currency or difference != Decimal(amount)
            or delta != difference
            or normal(amount) not in normal(total["quote"])):
        return None
    path = "/adm/amount"
    preferred = {"path": path, "segmentId": segment_id, "quote": total["quote"]}
    if preferred in evidence:
        return None
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or item.get("path") != path:
            continue
        quote, source_id = item.get("quote"), item.get("segmentId")
        if (item.keys() != preferred.keys() or not isinstance(quote, str) or not isinstance(source_id, str)
                or source_id not in sources or normal(amount) not in normal(quote)
                or normal(quote) not in normal(sources[source_id]["text"])):
            continue
        evidence[index] = preferred
        return {"code": "ADM_TOTAL_EVIDENCE_FROM_SOURCE", "path": path, "segmentId": segment_id,
                "message": "优先引用与候选金额和币种一致的唯一 BSP 正式总额行；未修改模型字段值"}
    return None


def supplement_labeled_fields(result, segments, bsp, changes):
    adm, evidence = result["adm"], result["evidence"]
    patterns = (
        ("noticeTypes", r"^Memo Reason:[ \t]*(?P<value>[^\r\n]+)"),
        ("attachmentReferences", r"^[ \t]*(?P<value>(?P<filename>[\w.-]+\.(?:zip|pdf|xlsx?|csv|txt|docx))(?:[ \t]+|[ \t]*\r?\n[ \t]*)[0-9]+(?:\.[0-9]+)?[ \t]+(?:B|KB|MB)\b)"),
    )
    if bsp:
        patterns += (
            ("noticeTypes", r"^Primary Reason Sub Reason[ \t]*\r?\n[ \t]*Booking[ \t]+(?P<value>Churning)[ \t]*$"),
            ("noticeTypes", r"^Primary Reason Sub Reason[ \t]*\r?\n[ \t]*(?P<value>Commission)[ \t]+Incorrect Commissions[ \t]*$"),
            ("noticeTypes", r"^[ \t]*Issue Reason[ \t]*\r?\n[ \t]*(?P<value>Churning Violation)[ \t]*$"),
        )
        if bsp[1]["kind"].casefold() == "refund":
            patterns += (("noticeTypes", r"^[ \t]*" + adm["number"] +
                          r"[ \t]+Issued[^\r\n]+[ \t]+(?P<value>Refund)[ \t]+[0-9/]+[ \t]+[^\r\n]+"),)
    for key, pattern in patterns:
        values = adm.get(key)
        if not isinstance(values, list):
            continue
        matches = [(part, match) for part in segments for match in re.finditer(pattern, part["text"], re.M | re.I)]
        attachment_values = {}
        if key == "attachmentReferences":
            for _, match in matches:
                attachment_values.setdefault(match["filename"].casefold(), set()).add(normal(match["value"]))
        for part, match in matches:
            quote = match["value"].strip()
            value = " ".join(quote.split())
            if key == "attachmentReferences":
                for index, existing in enumerate(values):
                    if not isinstance(existing, str) or normal(existing) == normal(value):
                        continue
                    path = f"/adm/{key}/{index}"
                    filename = match["filename"].casefold()
                    if existing.strip().casefold() == filename and len(attachment_values[filename]) == 1 and any(
                        isinstance(item, dict) and item.get("path") == path and item.get("segmentId") == part["id"]
                        and isinstance(item.get("quote"), str) and normal(value) in normal(item["quote"])
                        and normal(item["quote"]) in normal(part["text"]) for item in evidence
                    ):
                        values[index] = value
                        changes.append({"code": "ATTACHMENT_SIZE_FROM_EXISTING_PROOF", "path": path,
                                        "segmentId": part["id"], "message": "原引文已包含同一附件的明确大小，原位补全，不重复追加"})
                        continue
                    unwrapped = re.sub(r"\s*\(([0-9]+(?:\.[0-9]+)?\s+(?:B|KB|MB))\)\s*$",
                                       r" \1", existing, flags=re.I)
                    if normal(unwrapped) != normal(value):
                        continue
                    values[index] = value
                    evidence[:] = [item for item in evidence if not isinstance(item, dict) or item.get("path") != path]
                    evidence.append({"path": path, "segmentId": part["id"], "quote": quote})
                    changes.append({"code": "ATTACHMENT_REFERENCE_REBOUND", "path": path, "segmentId": part["id"],
                                    "message": "附件名和大小与原件一致，按原文去除模型添加的括号并复用原字段"})
            if len(values) >= 100 or len(value) > 500 or not value or value.casefold() in {x.casefold() for x in values if isinstance(x, str)}:
                continue
            path = f"/adm/{key}/{len(values)}"
            values.append(value)
            evidence.append({"path": path, "segmentId": part["id"], "quote": match[0].strip()})
            changes.append({"code": "LABELED_FIELD_FROM_SOURCE", "path": path, "segmentId": part["id"],
                            "message": "从明确的原文标签或附件文件名和大小补充可选字段"})


def bind_arc_optional_fields(result, segments, changes):
    adm, evidence = result["adm"], result["evidence"]
    conflicts = result.get("conflicts")
    conflicts = conflicts if isinstance(conflicts, list) else []
    memo = [part for part in segments if "arc memo manager" in part["text"].casefold()
            and ARC_MEMO.findall(part["text"]) == [adm.get("number")]]
    if len(memo) != 1:
        return
    part = memo[0]
    candidates = {}
    types = list(re.finditer(r"^Memo Reason:[ \t]*(?P<value>[^\r\n]+)", part["text"], re.M | re.I))
    if len(types) == 1:
        candidates["noticeTypes"] = [(part, types[0]["value"].strip(), types[0][0].strip())]
    for source in segments:
        if source.get("fileId") != part.get("fileId"):
            continue
        area = re.search(r"^Attachments[ \t]*\r?\n(?P<rows>[^\r\n]+(?:\r?\n[^\r\n]+)*?)"
                         r"\r?\nMemo Financial Details\b", source["text"], re.M | re.I)
        if not area:
            continue
        rows = [re.fullmatch(
            r"[ \t]*(?P<value>[\w.-]+\.(?:pdf|zip|xlsx?|csv|txt|docx)[ \t]+"
            r"[0-9]+(?:\.[0-9]+)?[ \t]+(?:B|KB|MB))(?:[ \t]+\d{1,2}/\d{1,2}/\d{4})?[ \t]*",
            row, re.I) for row in area["rows"].splitlines() if row.strip()]
        if rows and all(rows) and "attachmentReferences" not in candidates:
            candidates["attachmentReferences"] = [(source, m["value"], m[0].strip()) for m in rows]
        elif "attachmentReferences" in candidates:
            return
    for key, entries in candidates.items():
        parent = f"/adm/{key}"
        values = [" ".join(value.split()) for _, value, _ in entries]
        refs = [dict(path=f"{parent}/{i}", segmentId=source["id"], quote=quote)
                for i, (source, _, quote) in enumerate(entries)]
        if any(isinstance(item, dict) and isinstance(item.get("path"), str)
               and (item["path"] == parent or item["path"].startswith(parent + "/"))
               for item in conflicts):
            continue
        if adm.get(key) == values and all(
            any(isinstance(item, dict) and item.get("path") == ref["path"]
                and item.get("segmentId") == ref["segmentId"] and isinstance(item.get("quote"), str)
                and normal(value) in normal(item["quote"]) and normal(item["quote"]) in normal(source["text"])
                for item in evidence)
            for ref, value, (source, _, _) in zip(refs, values, entries)
        ):
            continue
        adm[key] = values
        evidence[:] = [item for item in evidence if not isinstance(item, dict) or not isinstance(item.get("path"), str)
                       or not (item["path"] == parent or item["path"].startswith(parent + "/"))]
        evidence.extend(refs)
        changes.append({"code": "ARC_OPTIONAL_SOURCE_BOUND", "path": parent, "segmentId": entries[0][0]["id"],
                        "message": "按同一 ARC Memo 原文的明确标签与附件区重绑字段及逐项引用"})


CHURN_TABLE = re.compile(
    r"^Churn AddPNR CxlPNR AddDate[ \t]+CxlDate[^\r\n]*\r?\n[ \t]*RBD[ \t]+PCC[^\r\n]*\r?\n"
    r"(?P<rows>(?:[ \t]*[0-9]+[ \t]+[A-Z0-9]{6}[ \t]+[A-Z0-9]{6}[ \t]+"
    r"[0-9-]{10}[ \t]+[0-9-]{10}[^\r\n]*\r?\n[ \t]+[A-Z0-9]+[ \t]*(?:\r?\n|$))+)",
    re.M,
)
CHURN_ROW = re.compile(
    r"^[ \t]*[0-9]+[ \t]+(?P<add>[A-Z0-9]{6})[ \t]+(?P<cancel>[A-Z0-9]{6})[ \t]+"
    r"[0-9-]{10}[ \t]+[0-9-]{10}[^\r\n]*\r?\n[ \t]+(?P<pcc>[A-Z0-9]+)[ \t]*$",
    re.M,
)


def churn_gds_code_only(item, path, codes, source):
    """Accept only an exact source quote proving the code, with no GDS role label."""
    target = item["path"]
    if target == path:
        expected = codes
    else:
        index = target.removeprefix(path + "/")
        if not re.fullmatch(r"0|[1-9][0-9]{0,3}", index) or int(index) >= len(codes):
            return False
        expected = [codes[int(index)]]
    quote = item.get("quote")
    return (
        item.get("segmentId") == source["id"] and isinstance(quote, str) and bool(normal(quote))
        and normal(quote) in normal(source["text"])
        and all(normal(code) in normal(quote) for code in expected)
        and not re.search(GDS_PNR_ROLE_LABEL, quote, re.I)
    )


def bind_bsp_churn_rows(result, segments, changes):
    lines = result.get("lines")
    if not isinstance(lines, list) or not lines:
        return
    tables = [(part, match) for part in segments for match in CHURN_TABLE.finditer(part["text"])]
    if len(tables) != 1:
        return
    part, table = tables[0]
    prefix = part["text"][:table.start()]
    section = re.search(r"^[-=]{3,}[ \t]*Churn Details[ \t]*[-=]{3,}[^\r\n]*$", prefix, re.M | re.I)
    systems = list(re.finditer(r"^[ \t]*GDS/CRS System:[ \t]*([A-Z0-9]{2,12})[ \t]*$", prefix, re.M | re.I))
    if not section or len(systems) != 1 or systems[0].start() < section.end():
        return
    system = systems[0]
    rows = list(CHURN_ROW.finditer(table["rows"]))
    evidence = result["evidence"]
    if len(lines) == 1 and isinstance(lines[0], dict) and len(rows) > 1:
        summary = lines[0]
        codes = summary.get("gdsPnrs")
        row_codes = [{row["add"], row["cancel"]} for row in rows]
        paths = ("/lines/0/gdsPnrs", "/lines/0/pnrs")
        has_refs = any(isinstance(item, dict) and isinstance(item.get("path"), str)
                       and any(item["path"] == p or item["path"].startswith(p + "/") for p in paths)
                       for item in evidence + (result["conflicts"] if isinstance(result.get("conflicts"), list) else []))
        if (isinstance(codes, list) and all(isinstance(code, str) for code in codes)
                and set(codes) == set().union(*row_codes) and sum(map(len, row_codes)) == len(set(codes))
                and summary.get("pnrs") == summary.get("airlinePnrs") == []
                and summary.get("gds") in (None, system[1]) and not has_refs):
            summary["gdsPnrs"] = []
            used = {summary.get("lineId")}
            for row in rows:
                new_line = dict.fromkeys(LINE_FIELDS)
                index = 1
                while f"L{index}" in used:
                    index += 1
                used.add(f"L{index}")
                new_line.update(lineId=f"L{index}", pnrs=list(dict.fromkeys((row["add"], row["cancel"]))),
                                airlinePnrs=[], gdsPnrs=[], ticketType="unknown")
                lines.append(new_line)
            changes.append({"code": "BSP_CHURN_PNR_REBOUND", "path": "/lines", "segmentId": part["id"],
                            "message": "按完整且唯一匹配的重订表拆分来源未明 PNR，不推定为 GDS 编码"})
    if len(lines) < 2:
        return
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            continue
        codes = {v for key in ("pnrs", "airlinePnrs", "gdsPnrs") for v in (line.get(key) if isinstance(line.get(key), list) else [])
                 if isinstance(v, str)}
        matching = [row for row in rows if codes and codes <= {row["add"], row["cancel"]}]
        if len(matching) != 1:
            continue
        row = matching[0]
        gds_pnrs, pnrs = line.get("gdsPnrs"), line.get("pnrs")
        gds_path = f"/lines/{i}/gdsPnrs"
        def targets_gds_pnr(item):
            return isinstance(item, dict) and isinstance(item.get("path"), str) and (
                item["path"] == gds_path or item["path"].startswith(gds_path + "/"))

        references = [item for item in evidence if targets_gds_pnr(item)]
        conflicts = result.get("conflicts")
        if (isinstance(gds_pnrs, list) and gds_pnrs and isinstance(pnrs, list)
                and all(isinstance(code, str) for code in gds_pnrs + pnrs)
                and line.get("gds") in (None, system[1])
                and not any(targets_gds_pnr(item) for item in (conflicts if isinstance(conflicts, list) else []))
                and all(churn_gds_code_only(item, gds_path, gds_pnrs, part) for item in references)):
            line["pnrs"] = list(dict.fromkeys(pnrs + gds_pnrs))
            line["gdsPnrs"] = []
            evidence[:] = [item for item in evidence if not targets_gds_pnr(item)]
            changes.append({"code": "BSP_CHURN_PNR_ROLE_FROM_ROW", "path": gds_path, "segmentId": part["id"],
                            "message": "唯一重订行证明编码，缺少 GDS 归属证据时保留为来源未明 PNR"})
        pnrs = line.get("pnrs")
        if isinstance(pnrs, list):
            for index, code in enumerate(pnrs):
                if not isinstance(code, str) or code not in {row["add"], row["cancel"]}:
                    continue
                parent = f"/lines/{i}/pnrs"
                path = f"{parent}/{index}"
                if any(isinstance(item, dict) and item.get("path") in (parent, path)
                       and item.get("segmentId") == part["id"] and isinstance(item.get("quote"), str)
                       and normal(code) in normal(item["quote"]) and normal(item["quote"]) in normal(part["text"])
                       for item in evidence):
                    continue
                evidence.append({"path": path, "segmentId": part["id"], "quote": row[0].strip()})
                changes.append({"code": "BSP_CHURN_PNR_ROW_EVIDENCE", "path": path, "segmentId": part["id"],
                                "message": "按唯一重订明细行补充 PNR 原文引用；保留原归属"})
        # The platform at table scope is context until per-row inheritance is agreed.
        gds_path = f"/lines/{i}/gds"
        if line.get("gds") == system[1] and not any(
            isinstance(item, dict) and item.get("path") == gds_path
            and item.get("segmentId") == part["id"] and isinstance(item.get("quote"), str)
            and normal(system[1]) in normal(item["quote"]) and normal(item["quote"]) in normal(row[0])
            for item in evidence
        ):
            line["gds"] = None
            evidence[:] = [item for item in evidence if not isinstance(item, dict) or item.get("path") != gds_path]
        path, value, quote = f"/lines/{i}/pcc", row["pcc"], row[0].strip()
        if line.get("pcc") not in (None, value):
            continue
        if any(isinstance(item, dict) and item.get("path") == path and item.get("segmentId") == part["id"]
               and isinstance(item.get("quote"), str) and normal(value) in normal(item["quote"])
               and normal(item["quote"]) in normal(quote) for item in evidence):
            continue
        line["pcc"] = value
        evidence.append({"path": path, "segmentId": part["id"], "quote": quote})
        changes.append({"code": "BSP_CHURN_ROW_SOURCE", "path": path, "segmentId": part["id"],
                        "message": "按唯一 PNR 行补充 PCC 原文引用"})


def supplement_bsp_summary(result, segments, changes):
    lines = result.get("lines")
    if not isinstance(lines, list) or len(lines) != 1 or not isinstance(lines[0], dict):
        return
    line = lines[0]
    evidence = result["evidence"]
    if line.get("gds") is None:
        refs = [(part["id"], match) for part in segments for match in re.finditer(
            r"(?:GDS/CRS System:[ \t]*|cancell\s*ed in[ \t]+)(?P<system>AMADEUS|TRAVELPORT|SABRE|[0-9][A-Z])\b",
            part["text"], re.I)]
        names = {match["system"].upper() for _, match in refs}
        if len(names) == 1:
            source, match = refs[0]
            line["gds"] = names.pop()
            evidence.append({"path": "/lines/0/gds", "segmentId": source, "quote": match[0]})
            changes.append({"code": "BSP_GDS_FROM_SOURCE", "path": "/lines/0/gds", "segmentId": source,
                            "message": "在唯一摘要行保留原件明确的系统标识"})
    if line.get("pnrs") != [] or line.get("airlinePnrs") != [] or line.get("gdsPnrs") != []:
        return
    found = [(part, match) for part in segments for match in CHURN_TABLE.finditer(part["text"])]
    if len(found) != 1:
        return
    part, match = found[0]
    line["pnrs"] = list(dict.fromkeys(code for pair in re.findall(
        r"^[ \t]*[0-9]+[ \t]+([A-Z0-9]{6})[ \t]+([A-Z0-9]{6})", match["rows"], re.M) for code in pair))
    evidence.append({"path": "/lines/0/pnrs", "segmentId": part["id"], "quote": match[0]})
    changes.append({"code": "BSP_CHURN_PNR_FROM_SOURCE", "path": "/lines/0/pnrs", "segmentId": part["id"],
                    "message": "保留明确 AddPNR/CxlPNR 清单，未推定编码归属或交易动作"})


def omit_unsupported_actions(lines, evidence, sources, changes):
    if not isinstance(lines, list):
        return
    churn_table = any(re.search(r"^Churn AddPNR CxlPNR AddDate[ \t]+CxlDate\b", s["text"], re.M | re.I)
                      for s in sources.values())
    for index, line in enumerate(lines):
        if not isinstance(line, dict) or not isinstance(line.get("action"), str) or not line["action"].strip():
            continue
        path = f"/lines/{index}/action"
        references = [item for item in evidence if isinstance(item, dict) and item.get("path") == path]
        action = re.compile(r"(?<!\w)" + re.escape(line["action"].strip()) + r"(?!\w)", re.I)
        identifiers = [line.get("ticketNumber"), line.get("transactionNumber")]
        for key in ("pnrs", "airlinePnrs", "gdsPnrs"):
            if isinstance(line.get(key), list):
                identifiers.extend(line[key])
        identifiers = [re.compile(r"(?<!\w)" + re.escape(value.strip()) + r"(?!\w)", re.I)
                       for value in identifiers if isinstance(value, str) and value.strip()]
        supported = False
        for item in references:
            quote, segment_id = item.get("quote"), item.get("segmentId")
            if (not isinstance(quote, str) or not isinstance(segment_id, str) or segment_id not in sources
                    or not normal(quote) or normal(quote) not in normal(sources[segment_id]["text"])):
                continue
            if churn_table:
                supported = any(action.search(row) and any(identifier.search(row) for identifier in identifiers)
                                for row in quote.splitlines())
            else:
                supported = bool(action.search(quote))
            if supported:
                break
        if supported:
            continue
        line["action"] = None
        evidence[:] = [item for item in evidence if not isinstance(item, dict) or item.get("path") != path]
        changes.append({"code": "UNSUPPORTED_ACTION_OMITTED", "path": path,
                        "message": "可选明细动作无法与有效原文绑定，保留为空；原始值与引文留存于模型结果"})


def related_documents(segments):
    """Read the labeled number or same-row list of related document numbers."""
    items, seen = [], set()
    number = r"[0-9]{3}[- ]?[0-9]{10}"
    numbers = r"(?P<numbers>" + number + r"(?:[^\S\r\n]+" + number + r")*)(?![0-9])"
    label = r"\bRelated\s+Document\s+Numbers?\b"
    patterns = (
        re.compile(label + r"\s*[:：]?\s*" + numbers, re.I),
        re.compile(r"(?<![0-9])" + numbers + r"\s+" + label, re.I),
    )
    for segment in segments:
        text = segment["text"]
        virtual = virtual_ticket_text(text)
        for pattern in patterns:
            for match in pattern.finditer(text):
                for ticket in re.findall(number, match.group("numbers")):
                    value = re.sub(r"[- ]", "", ticket)
                    key = (value, segment["id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append({"number": value, "segmentId": segment["id"], "locator": segment.get("locator", ""),
                                  "quote": match.group(0), "ticketType": "virtual" if virtual else "unknown"})
    return items


def prepare(candidate, segments):
    result, changes = copy.deepcopy(candidate), []
    if not isinstance(result, dict):
        return result, changes
    if result.get("schemaVersion") not in ("adm-extraction/1.1", "adm-extraction/1.2", VERSION):
        return result, changes
    adm = result.get("adm")
    if not isinstance(adm, dict):
        return result, changes
    if result["schemaVersion"] == "adm-extraction/1.1":
        for key in ("issuer", "supplierName", "airline"):
            adm.pop(key, None)
        adm.setdefault("airlineCode", None)
        changes.append({"code": "CONTRACT_MIGRATED", "path": "/adm", "message": "按已确认口径移除发单方/供应商候选，航司改为原件编码"})
    if result["schemaVersion"] != VERSION:
        for key in ADM_LIST_FIELDS:
            adm.setdefault(key, [])
        result["schemaVersion"] = VERSION
        changes.append({"code": "OPTIONAL_FIELDS_MIGRATED", "path": "/adm", "message": "历史结果补齐可选数组，不补造内容"})
    evidence = result.get("evidence")
    if not isinstance(evidence, list):
        return result, changes
    sources = {s["id"]: s for s in segments}
    kept = []
    for item in evidence:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        path = item.get("path")
        if isinstance(path, str) and path in REMOVED:
            changes.append({"code": "REMOVED_FIELD_EVIDENCE", "path": path, "message": "已移除字段不再参与校验，原始模型结果保留"})
            continue
        if isinstance(path, str):
            fixed = re.sub(r"^/lines\[(0|[1-9][0-9]*)\]/", r"/lines/\1/", path)
            if fixed != path:
                item["path"] = fixed
                changes.append({"code": "PATH_CANONICALIZED", "path": fixed, "message": "兼容数组方括号路径为JSON Pointer"})
        source = sources.get(item.get("segmentId")) if isinstance(item.get("segmentId"), str) else None
        quote = item.get("quote")
        if source and isinstance(quote, str) and quote.strip() and normal(quote) not in normal(source["text"]):
            fragments = re.split(r"\.{3}|…+", quote)
            if len(fragments) == 1:
                fragments = [line for line in quote.splitlines() if line.strip()]
            if len(fragments) > 1 and all(normal(part) and normal(part) in normal(source["text"]) for part in fragments):
                item["quote"] = source["text"]
                changes.append({"code": "SOURCE_REBOUND", "path": item.get("path"), "segmentId": source["id"], "message": "引用各片段或调序行均存在于同一原文段落，改引该完整原文；未拼造摘录"})
        kept.append(item)
    result["evidence"] = kept
    row = bsp_row(adm, sources)
    changes.extend(prefer_bsp_dates(adm, kept, row))
    supplement_labeled_fields(result, segments, row, changes)
    bind_arc_optional_fields(result, segments, changes)
    if row:
        supplement_bsp_summary(result, segments, changes)
        bind_bsp_churn_rows(result, segments, changes)
    change = prefer_bsp_total(adm, kept, sources, row)
    if change:
        changes.append(change)
    if adm.get("airlineCode") is None:
        hits = []
        for source in segments:
            for hit in re.finditer(r"Airline\s+Code\s*/\s*Name\s+([0-9]{3}|[A-Z0-9]{2})\s*/[^\n]*", source["text"], re.I):
                hits.append((hit.group(1).upper(), source["id"], hit.group(0)))
        if len({h[0] for h in hits}) == 1:
            code, sid, quote = hits[0]
            adm["airlineCode"] = code
            result["evidence"].append({"path": "/adm/airlineCode", "segmentId": sid, "quote": quote})
            changes.append({"code": "AIRLINE_CODE_FROM_SOURCE", "path": "/adm/airlineCode", "segmentId": sid, "message": "从唯一Airline Code / Name标签提取编码，不从航司名称猜测"})
    changes.extend(bind_sources(result, segments))
    documents = related_documents(segments)
    numbers = {item["number"] for item in documents}
    lines = result.get("lines")
    omit_unsupported_actions(lines, kept, sources, changes)
    if row and lines == [] and documents and all(sources[item["segmentId"]].get("fileId") == row[0].get("fileId") for item in documents):
        for number in dict.fromkeys(item["number"] for item in documents):
            item = next(doc for doc in documents if doc["number"] == number)
            summary = dict.fromkeys(LINE_FIELDS)
            summary.update(lineId=f"L{len(lines)+1}", pnrs=[], airlinePnrs=[], gdsPnrs=[],
                           ticketNumber=number, ticketType=item["ticketType"])
            path = f"/lines/{len(lines)}/ticketNumber"
            lines.append(summary)
            kept.append({"path": path, "segmentId": item["segmentId"], "quote": item["quote"]})
            changes.append({"code": "RELATED_TICKET_FROM_SOURCE", "path": path, "segmentId": item["segmentId"],
                            "message": "从明确 Related Document Number 保留原件关联票号，不推定交易动作"})
    if len(numbers) == 1 and isinstance(lines, list) and len(lines) == 1 and isinstance(lines[0], dict) and lines[0].get("ticketNumber") is None:
        item = documents[0]
        lines[0]["ticketNumber"] = item["number"]
        # Never infer that a labelled document is a real ticket simply from its shape.
        if item["ticketType"] == "virtual":
            lines[0]["ticketType"] = "virtual"
        result["evidence"].append({"path": "/lines/0/ticketNumber", "segmentId": item["segmentId"], "quote": item["quote"]})
        changes.append({"code": "RELATED_TICKET_FROM_SOURCE", "path": "/lines/0/ticketNumber", "segmentId": item["segmentId"], "message": "从唯一Related Document Number提取关联票号；虚拟号保留原号，不用于真实出票匹配"})
    return result, changes
