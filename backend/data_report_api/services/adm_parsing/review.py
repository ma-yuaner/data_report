"""Human confirmation and source-backed locator presentation."""
import copy
import re
from decimal import Decimal

from ..admwf.policy import AdmError
from .contract import validate
from .recheck import BSP_TOTAL, CHURN_ROW, CHURN_TABLE

REQUIRED = ("number", "airlineCode", "issuedDate", "amount", "currency")


def source_quote(segments, item):
    if not isinstance(item, dict):
        return False
    quote = item.get("quote")
    return isinstance(quote, str) and bool(quote.strip()) and any(
        segment["id"] == item.get("segmentId")
        and " ".join(quote.split()) in " ".join(segment["text"].split())
        for segment in segments
    )


def locator_groups(candidate, segments, issues=()):
    candidate = candidate or {}
    invalid = {issue["path"] for issue in issues if issue["level"] == "error"}
    groups = {}
    lines = candidate.get("lines")
    for index, line in enumerate(lines if isinstance(lines, list) else []):
        if not isinstance(line, dict):
            continue
        prefix = f"/lines/{index}/"

        def evidence(field, value, parent=None):
            if not isinstance(value, str) or not value or prefix + field in invalid or (parent and prefix + parent in invalid):
                return []
            return [
                item for item in candidate.get("evidence") or []
                if isinstance(item, dict) and item.get("path") in {prefix + field, prefix + parent if parent else ""}
                and source_quote(segments, item)
                and re.search(r"(?<![A-Z0-9])" + re.escape(value) + r"(?![A-Z0-9])", item["quote"], re.I)
            ]

        # Retain table-scope references for review without assigning them to a row.
        context = evidence("gds", line.get("gds"))
        for field, role in (("pnrs", "UNKNOWN"), ("airlinePnrs", "AIRLINE"), ("gdsPnrs", "GDS")):
            values = line.get(field)
            for position, pnr in enumerate(values if isinstance(values, list) else []):
                refs = evidence(f"{field}/{position}", pnr, field)
                if not refs:
                    continue
                row_refs = {(item["segmentId"], " ".join(item["quote"].split())) for item in refs}

                def same_row(item):
                    return (item["segmentId"], " ".join(item["quote"].split())) in row_refs

                gds_refs = [item for item in context if same_row(item)]
                pcc_refs = [item for item in evidence("pcc", line.get("pcc")) if same_row(item)]
                gds = line.get("gds") if gds_refs else None
                pcc = line.get("pcc") if pcc_refs else None
                # Incomplete groups have insufficient identity for automatic deduplication.
                key = (gds, pcc, pnr) if gds and pcc else (index, field, position)
                group = groups.setdefault(key, {"gds": gds, "pcc": pcc, "pnr": pnr, "role": role, "evidence": []})
                if group["role"] != role:
                    group["role"] = "UNKNOWN"
                for item in refs + context + pcc_refs:
                    if item not in group["evidence"]:
                        group["evidence"].append(item)
    # Recover omissions from a structurally recognized rebooking table. The table
    # header is only context and does not establish per-row system membership.
    for segment in segments:
        for table in CHURN_TABLE.finditer(segment["text"]):
            context = re.findall(r"^[ \t]*GDS/CRS System:[^\r\n]+", segment["text"][:table.start()], re.M | re.I)
            for row in CHURN_ROW.finditer(table["rows"]):
                quote = row[0].strip()
                for pnr in dict.fromkeys((row["add"], row["cancel"])):
                    if any(group["pnr"] == pnr and group["pcc"] == row["pcc"] and any(
                        item["segmentId"] == segment["id"] and " ".join(item["quote"].split()) == " ".join(quote.split())
                        for item in group["evidence"]
                    ) for group in groups.values()):
                        continue
                    ref = {"path": "/lines", "segmentId": segment["id"], "quote": quote}
                    refs = [ref]
                    if len(context) == 1:
                        refs.append({**ref, "quote": context[0].strip()})
                    key = (segment["id"], table.start() + row.start(), pnr)
                    groups[key] = {"gds": None, "pcc": row["pcc"], "pnr": pnr, "role": "UNKNOWN", "evidence": refs}
    return list(groups.values())


def apply_confirmation(task, edits, actor, at):
    if not isinstance(edits, dict) or set(edits) - set(REQUIRED):
        raise AdmError("只可修正待登记关键字段", 422, "PARSE_REVIEW_FIELDS")
    candidate = copy.deepcopy(task["candidate"])
    if not isinstance(candidate.get("evidence"), list) or not all(isinstance(item, dict) for item in candidate["evidence"]):
        raise AdmError("当前解析结果缺少有效证据结构，请重新解析", 422, "PARSE_REVIEW_EVIDENCE")
    changes = []
    for field, edit in edits.items():
        value = edit.get("value") if isinstance(edit, dict) else None
        if not isinstance(value, str) or not value.strip() or len(value) > 2000 or not source_quote(task["segments"], edit):
            raise AdmError("修正须填写字段值，并引用上传材料中实际存在的原文", 422, "PARSE_REVIEW_EVIDENCE")
        path = f"/adm/{field}"
        original = candidate["adm"].get(field)
        candidate["adm"][field] = value.strip()
        candidate["evidence"] = [item for item in candidate["evidence"] if item.get("path") != path]
        citation = {"path": path, "segmentId": edit["segmentId"], "quote": edit["quote"]}
        candidate["evidence"].append(citation)
        changes.append({"field": field, "original": original, "value": value.strip(), "evidence": citation})
    issues = validate(candidate, task["segments"])
    required_paths = {f"/adm/{field}" for field in REQUIRED}
    missing = [field for field in REQUIRED if not candidate["adm"].get(field)]
    evidenced = {item["path"] for item in candidate["evidence"] if source_quote(task["segments"], item)}
    blocking = [
        issue for issue in issues if issue["level"] == "error" and (
            issue["path"] in required_paths | {"", "/adm", "/schemaVersion", "/evidence", "/conflicts", "/lines"}
            or issue["code"] in {"INVALID_TYPE", "INVALID_KEYS"}
        )
        and issue["code"] != "TABLE_TRANSACTION_MISSING"
    ]
    if missing or required_paths - evidenced or blocking:
        raise AdmError("ADM号、航司、开具日期、正式金额和币种须通过原文校验", 422, "PARSE_REVIEW_REQUIRED")
    adm = candidate["adm"]
    amount = Decimal(adm["amount"])
    amount_quotes = [item["quote"] for item in candidate["evidence"]
                     if item["path"] == "/adm/amount" and source_quote(task["segments"], item)]
    totals = [(Decimal(match["difference"]), match["currency"].upper())
              for segment in task["segments"] if segment.get("fileId") == task.get("primaryFileId")
              for match in BSP_TOTAL.finditer(segment["text"])]
    if (not any(amount == Decimal(value.replace(",", "")) for quote in amount_quotes
                for value in re.findall(r"(?<![\w.,+-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.,])", quote))
            or totals and set(totals) != {(amount, adm["currency"])}):
        raise AdmError("正式罚单金额或币种与原文总额不一致", 422, "PARSE_REVIEW_AMOUNT")
    task["candidate"] = candidate
    task["issues"] = issues
    if task.get("review"):
        task.setdefault("reviewHistory", []).append(task["review"])
    task["review"] = {"actorId": actor, "at": at, "changes": changes}
