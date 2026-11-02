"""Typed placement endpoints resolved through the existing airport dictionary."""
from __future__ import annotations

import re
from typing import Any

AIRPORT_TABLE = "sibedb.base_airport"
LOCATION_COLUMNS = {"AIRPORT": "airport_code", "CITY": "city_code", "COUNTRY": "country_code"}
ACTIVE_AIRPORT = "status=1 AND (start_time IS NULL OR start_time<=%s) AND (end_time IS NULL OR end_time>%s)"


def location_type(value: Any) -> str:
    result = str(value or "LEGACY").strip().upper()
    if result not in {*LOCATION_COLUMNS, "LEGACY"}:
        raise ValueError("地点类型须为机场、城市或国家")
    return result


def location_fields(values: dict[str, Any], side: str) -> dict[str, Any]:
    kind = location_type(values.get(f"{side}Type"))
    code = str(values.get(f"{side}Code") or "").strip().upper()
    name = "出发地" if side == "departure" else "目的地"
    if kind != "LEGACY" and code and not re.fullmatch(r"[A-Z]{2}" if kind == "COUNTRY" else r"[A-Z]{3}", code):
        raise ValueError(f"{name}须填写{'国家二字码' if kind == 'COUNTRY' else '三字码'}")
    if kind == "LEGACY" and code and not re.fullmatch(r"[A-Za-z0-9._:/-]{1,32}", code):
        raise ValueError(f"{name}编码格式不合法")
    return {f"{side}_code": code or None, f"{side}_type": kind}


def resolve_airports(cursor, kind: str, code: str, now) -> list[str]:
    """No matches must fail closed; never compile an empty unrestricted rule."""
    kind = location_type(kind)
    if kind == "LEGACY" or not code:
        return []
    cursor.execute(
        f"SELECT DISTINCT airport_code FROM {AIRPORT_TABLE} WHERE {LOCATION_COLUMNS[kind]}=%s "
        f"AND {ACTIVE_AIRPORT} ORDER BY airport_code",
        (code, now, now),
    )
    airports = sorted({str(row.get("airport_code") if isinstance(row, dict) else row[0]).strip().upper() for row in cursor.fetchall()})
    if not airports or any(not re.fullmatch(r"[A-Z]{3}", airport) for airport in airports):
        raise ValueError(f"地点{code}没有可用的机场映射，请核对机场基础数据")
    return airports


def resolved_location(task: dict[str, Any], execution: dict[str, Any], side: str) -> dict[str, Any]:
    # A supplied type makes an explicitly cleared code unrestricted. Old clients
    # omit the type and retain the previous code-or-task fallback behavior.
    if execution.get(f"{side}_type"):
        return {f"{side}_type": location_type(execution[f"{side}_type"]), f"{side}_code": execution.get(f"{side}_code")}
    code = execution.get(f"{side}_code") or task.get(f"{side}_code")
    kind = "LEGACY" if execution.get(f"{side}_code") else location_type(task.get(f"{side}_type"))
    return {f"{side}_type": kind, f"{side}_code": code}
