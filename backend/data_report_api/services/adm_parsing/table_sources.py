"""Exact saved XLSX cell/header binding; no fuzzy text or cross-file inference."""
import re
from .contract import CURRENCIES, MONEY


def normal(value):
    return re.sub(r"\s+", "", str(value)).replace(",", "").casefold()


def table_rows(segments):
    rows = {}
    for source in segments:
        loc = re.fullmatch(r"(.+)!第([1-9][0-9]*)行", source.get("locator", ""))
        if not loc or not source.get("fileId"):
            continue
        sheet, row = loc.group(1), int(loc.group(2))
        cells, valid = {}, True
        for part in re.split(r"\s+\|\s+(?=[A-Z]{1,3}[1-9][0-9]*:)", source["text"]):
            match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*):\s*(.*)", part.strip(), re.S)
            if not match or int(match.group(2)) != row or match.group(1) in cells:
                valid = False
                break
            cells[match.group(1)] = {"value": match.group(3), "quote": part.strip(), "address": match.group(1) + match.group(2)}
        if valid and cells:
            rows[source["id"]] = {"source": source, "sheet": sheet, "row": row, "cells": cells,
                                  "header": any(c["value"].strip().upper() in {"RLOC", "GDS_RLOC", "OFFICE", "ADM FEE $"} for c in cells.values())}
    return rows


def bindings(candidate, segments):
    if not isinstance(candidate, dict) or not isinstance(candidate.get("evidence"), list):
        return {}
    rows = table_rows(segments)
    referenced = {}
    for item in candidate["evidence"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        path = re.match(r"/lines/([0-9]+)/", item["path"])
        row = rows.get(item.get("segmentId")) if isinstance(item.get("segmentId"), str) else None
        quote = item.get("quote")
        if path and row and not row["header"] and isinstance(quote, str) and quote.strip() and normal(quote) in normal(row["source"]["text"]):
            referenced.setdefault(int(path.group(1)), set()).add(row["source"]["id"])
    result = {}
    for index, ids in referenced.items():
        if len(ids) != 1:
            continue
        row = rows[next(iter(ids))]
        headers = [h for h in rows.values() if h["header"] and h["source"]["fileId"] == row["source"]["fileId"] and h["sheet"] == row["sheet"] and h["row"] < row["row"]]
        if not headers:
            continue
        nearest = max(h["row"] for h in headers)
        headers = [h for h in headers if h["row"] == nearest]
        if len(headers) == 1:
            result[index] = {"row": row, "header": headers[0]}
    return result


def missing_transaction_rows(lines, segments, bound):
    """Check known transaction tables independently of the model's evidence list."""
    headers = {}
    represented = {}
    for index, binding in bound.items():
        if index < len(lines) and isinstance(lines[index], dict):
            represented.setdefault(binding["row"]["source"]["id"], []).append(lines[index])

    rows = sorted(table_rows(segments).values(), key=lambda row: (
        row["source"]["fileId"], row["sheet"], row["row"],
    ))
    for row in rows:
        source = row["source"]
        group = source["fileId"], row["sheet"]
        if row["header"]:
            labels = [cell["value"].strip().upper() for cell in row["cells"].values()]
            headers[group] = {
                label: col for col, label in zip(row["cells"], labels)
                if label in ("RLOC", "GDS_RLOC") and labels.count(label) == 1
            }
            if len(headers[group]) != 2:
                headers[group] = {}
            continue
        expected = {}
        for label, field in (("RLOC", "airlinePnrs"), ("GDS_RLOC", "gdsPnrs")):
            column = headers.get(group, {}).get(label)
            if column in row["cells"]:
                codes = re.split(r"[,;/\s]+", row["cells"][column]["value"].strip())
                if all(re.fullmatch(r"[A-Z0-9]{6}", code) for code in codes):
                    expected[field] = codes
        if expected and not any(
            all(line.get(key) == codes for key, codes in expected.items())
            for line in represented.get(source["id"], [])
        ):
            yield source["id"]


def fee_from_binding(binding):
    header, row = binding["header"], binding["row"]
    fees = [(col, c) for col, c in header["cells"].items() if re.fullmatch(r"ADM\s+(?:FEE|CHARGE)(?:\s+.*)?", c["value"].strip(), re.I)]
    if len(fees) != 1:
        return None
    col, label = fees[0]
    value = row["cells"].get(col)
    if not value or not MONEY.fullmatch(value["value"]):
        return None
    codes = set(re.findall(r"\b(?:" + "|".join(sorted(CURRENCIES)) + r")\b", label["value"].upper()))
    explicit_label = re.fullmatch(r"ADM\s+(?:FEE|CHARGE)\s+[\[(]?([A-Z]{3})[\])]?$", label["value"].strip().upper())
    if explicit_label:
        codes.add(explicit_label.group(1))
    currency_source, currency_quote = header["source"], label["quote"]
    currency_columns = [c for c, cell in header["cells"].items() if cell["value"].strip().upper() in {"CURRENCY", "CCY"}]
    if len(currency_columns) == 1 and currency_columns[0] in row["cells"]:
        currency_cell = row["cells"][currency_columns[0]]
        token = currency_cell["value"].strip().upper()
        if re.fullmatch(r"[A-Z]{3}", token):
            codes.add(token)
            currency_source, currency_quote = row["source"], currency_cell["quote"]
    return {"amount": value["value"], "label": label["value"], "text": label["value"] + " " + value["value"],
            "currency": next(iter(codes)) if len(codes) == 1 else None, "currencySource": currency_source, "currencyQuote": currency_quote,
            "headerSource": header["source"], "rowSource": row["source"], "headerQuote": label["quote"], "rowQuote": value["quote"]}


def fee_text_proven(path, value, fee, evidence):
    if value != fee["text"]:
        return False
    for source_key, quote_key in (("headerSource", "headerQuote"), ("rowSource", "rowQuote")):
        source, expected = fee[source_key], fee[quote_key]
        if not any(isinstance(e, dict) and e.get("path") == path and e.get("segmentId") == source["id"] and isinstance(e.get("quote"), str)
                   and normal(expected) in normal(e["quote"]) and normal(e["quote"]) in normal(source["text"]) for e in evidence):
            return False
    return True


def bind_sources(candidate, segments):
    changes = []
    if not isinstance(candidate.get("lines"), list):
        return changes
    evidence = candidate["evidence"]
    def add(path, source, quote):
        item = {"path": path, "segmentId": source["id"], "quote": quote}
        if item not in evidence:
            evidence.append(item)
    for index, binding in bindings(candidate, segments).items():
        if index >= len(candidate["lines"]) or not isinstance(candidate["lines"][index], dict):
            continue
        line, prefix = candidate["lines"][index], f"/lines/{index}"
        header, row = binding["header"], binding["row"]
        for key, name in (("airlinePnrs", "RLOC"), ("gdsPnrs", "GDS_RLOC")):
            cols = [col for col, c in header["cells"].items() if c["value"].strip().upper() == name]
            if len(cols) != 1 or cols[0] not in row["cells"]:
                continue
            cell = row["cells"][cols[0]]
            values = re.split(r"[,;/\s]+", cell["value"].strip())
            if isinstance(line.get(key), list) and line[key] and line[key] == values and all(re.fullmatch(r"[A-Z0-9]{6}", v) for v in values):
                add(prefix + "/" + key, header["source"], header["cells"][cols[0]]["quote"])
                add(prefix + "/" + key, row["source"], cell["quote"])
                changes.append({"code": "TABLE_HEADER_BOUND", "path": prefix + "/" + key, "message": "按同文件同工作表同列绑定表头和数据单元格"})
        fee = fee_from_binding(binding)
        if fee is None:
            continue
        # Preserve the exact fee and label; dollar sign alone never determines ISO currency.
        line["amountText"] = fee["text"]
        line["amount"] = fee["amount"] if fee["currency"] else None
        line["currency"] = fee["currency"]
        if fee["currency"] is None:
            line["amountPurpose"] = "other"
        replaced = {prefix + "/" + key for key in ("amount", "currency", "amountText")}
        evidence[:] = [e for e in evidence if not isinstance(e, dict) or not isinstance(e.get("path"), str) or e.get("path") not in replaced]
        add(prefix + "/amountText", fee["headerSource"], fee["headerQuote"])
        add(prefix + "/amountText", fee["rowSource"], fee["rowQuote"])
        if fee["currency"]:
            add(prefix + "/amount", fee["rowSource"], fee["rowQuote"])
            add(prefix + "/currency", fee["currencySource"], fee["currencyQuote"])
        changes.append({"code": "TABLE_FEE_BOUND" if fee["currency"] else "TABLE_FEE_CURRENCY_UNKNOWN", "path": prefix + "/amountText",
                        "message": "从费用列和单元格保留原始费用；币种仅认明确ISO代码，不根据$推测"})
    return changes


def fee_details(candidate, segments):
    result = []
    for index, binding in bindings(candidate, segments).items():
        fee = fee_from_binding(binding)
        if fee:
            result.append({"lineIndex": index, "amount": fee["amount"], "currency": fee["currency"], "label": fee["label"],
                           "headerSegmentId": fee["headerSource"]["id"], "rowSegmentId": fee["rowSource"]["id"],
                           "headerLocator": fee["headerSource"]["locator"], "rowLocator": fee["rowSource"]["locator"]})
    return result
