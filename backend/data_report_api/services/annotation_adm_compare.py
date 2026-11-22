"""Compare confirmed ADM evidence with an existing stored parse candidate."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation


def normalized(key, value):
    value = " ".join(str(value).split())
    if key == "issuedDate":
        match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value)
        if match:
            day, month, year = map(int, match.groups())
            if day <= 12:
                return value
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return value
    if key == "amount":
        if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
            return value
        try:
            result = Decimal(value.replace(",", ""))
            return result if result.is_finite() else value
        except InvalidOperation:
            return value
    if key in ("airlineCode", "currency", "pnrs"):
        return value.upper()
    return value


def actual_values(candidate, key):
    if key in ("ticketNumber", "pnrs"):
        values = []
        lines = candidate.get("lines")
        for line in lines if isinstance(lines, list) else []:
            if not isinstance(line, dict):
                continue
            if key == "ticketNumber":
                values.append(line.get(key))
            else:
                for column in ("pnrs", "airlinePnrs", "gdsPnrs"):
                    codes = line.get(column)
                    if isinstance(codes, list):
                        values.extend(codes)
    else:
        adm = candidate.get("adm") or {}
        values = [adm.get(key)] if isinstance(adm, dict) else []
    return list(dict.fromkeys(str(value).strip() for value in values if isinstance(value, (str, int, float))
                              and str(value).strip()))


def compare_candidate(sample, candidate):
    labels = {label["id"]: label for label in sample["labels"] if label.get("admField")}
    fields = []
    for mark in sample["marks"]:
        label = labels.get(mark["labelId"])
        if not label:
            continue
        key, expected = label["admField"], mark["quote"]
        actual = actual_values(candidate, key)
        target = normalized(key, expected)
        matches = any(target.casefold() in normalized(key, result).casefold() if key == "reason"
                      else normalized(key, result) == target for result in actual)
        fields.append({"label": label["name"], "expected": expected, "actual": actual,
                       "status": "match" if matches else "different" if actual else "missing"})
    return fields
