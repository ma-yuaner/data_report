"""Deterministic source-bound compatibility repair. Never calls a model or invents evidence."""
import copy
import re
from .contract import VERSION, virtual_ticket_text
from .table_sources import bind_sources

VALIDATION_VERSION = "adm-validation/1.5"
REMOVED = {"/adm/issuer", "/adm/supplierName", "/adm/airline"}


def normal(value):
    return re.sub(r"\s+", "", str(value)).replace(",", "").casefold()


def related_documents(segments):
    """Only numbers directly adjacent to the Related Document Number label."""
    items, seen = [], set()
    number = r"[0-9]{3}[- ]?[0-9]{10}"
    patterns = (
        re.compile(r"Related\s+Document\s+Numbers?\s*[:：]?\s*(?P<number>" + number + r")(?![0-9])", re.I),
        re.compile(r"(?<![0-9])(?P<number>" + number + r")\s+Related\s+Document\s+Numbers?\b", re.I),
    )
    for segment in segments:
        text = segment["text"]
        virtual = virtual_ticket_text(text)
        for pattern in patterns:
            for match in pattern.finditer(text):
                value = re.sub(r"[- ]", "", match.group("number"))
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
    if result.get("schemaVersion") not in ("adm-extraction/1.1", VERSION):
        return result, changes
    adm = result.get("adm")
    if not isinstance(adm, dict):
        return result, changes
    if result["schemaVersion"] == "adm-extraction/1.1":
        for key in ("issuer", "supplierName", "airline"):
            adm.pop(key, None)
        adm.setdefault("airlineCode", None)
        result["schemaVersion"] = VERSION
        changes.append({"code": "CONTRACT_MIGRATED", "path": "/adm", "message": "按已确认口径移除发单方/供应商候选，航司改为原件编码"})
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
    if len(numbers) == 1 and isinstance(lines, list) and len(lines) == 1 and isinstance(lines[0], dict) and lines[0].get("ticketNumber") is None:
        item = documents[0]
        lines[0]["ticketNumber"] = item["number"]
        # Never infer that a labelled document is a real ticket simply from its shape.
        if item["ticketType"] == "virtual":
            lines[0]["ticketType"] = "virtual"
        result["evidence"].append({"path": "/lines/0/ticketNumber", "segmentId": item["segmentId"], "quote": item["quote"]})
        changes.append({"code": "RELATED_TICKET_FROM_SOURCE", "path": "/lines/0/ticketNumber", "segmentId": item["segmentId"], "message": "从唯一Related Document Number提取关联票号；虚拟号保留原号，不用于真实出票匹配"})
    return result, changes
