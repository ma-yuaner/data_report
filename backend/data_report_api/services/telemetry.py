"""Authenticated product-usage telemetry and administrator reporting."""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .comprehensive_analysis import parse_period
from .data_source import DataSource


VISIT_TABLE = "sys_user_page_visit"
EVENT_TABLE = "sys_user_behavior_event"
ID_RE = re.compile(r"^[a-f0-9]{32}$")
CODE_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,100}$")
EVENT_TYPES = frozenset({
    "element_click", "filter_apply", "period_change", "dimension_change",
    "sort_change", "tab_change", "query_success", "query_failed",
    "empty_result", "drilldown_open", "detail_open", "export",
    "frontend_error",
})
ACTION_EVENTS = frozenset({
    "element_click", "filter_apply", "period_change", "dimension_change",
    "sort_change", "tab_change", "drilldown_open", "detail_open", "export",
})
EXIT_TYPES = frozenset({"route_change", "page_hidden", "unload", "logout", "expired"})
RESULT_STATUSES = frozenset({"success", "failed", "cancelled", "empty", "unknown"})
CONTEXT_KEYS = frozenset({
    "dateRangeDays", "filterKeys", "groupBy", "sortBy", "resultCount",
    "page", "pageSize", "businessType", "statusCode", "method", "apiPath",
})
MAX_BATCH = 50
MAX_CONTEXT_BYTES = 4096


class TelemetryUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _text(value: Any, name: str, maximum: int, *, required: bool = False) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{name}不能为空")
    if len(result) > maximum:
        raise ValueError(f"{name}不能超过{maximum}个字符")
    return result


def _code(value: Any, name: str, *, required: bool = False) -> str:
    result = _text(value, name, 100, required=required)
    if result and not CODE_RE.fullmatch(result):
        raise ValueError(f"{name}格式不合法")
    return result


def _bounded_int(value: Any, name: str, maximum: int, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name}必须为整数") from error
    if result < 0 or result > maximum:
        raise ValueError(f"{name}超出允许范围")
    return result


def _occurred_at(value: Any, now: datetime) -> datetime:
    if not value:
        return now
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError as error:
        raise ValueError("occurredAt必须为ISO日期时间") from error
    if abs((parsed - now).total_seconds()) > 86_400:
        raise ValueError("occurredAt与服务器时间偏差过大")
    return parsed


def _clean_context(value: Any) -> str | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("context必须为对象")
    cleaned = {}
    for key, item in value.items():
        if key not in CONTEXT_KEYS:
            continue
        if isinstance(item, list):
            cleaned[key] = [str(entry)[:100] for entry in item[:20]]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            cleaned[key] = str(item)[:500] if isinstance(item, str) else item
    encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("context内容过大")
    return encoded if cleaned else None


def _is_missing_table(error: Exception) -> bool:
    return bool(getattr(error, "args", ())) and error.args[0] == 1146


class TelemetryService:
    def __init__(self, config: dict[str, Any], source: DataSource | None = None):
        self.source = source or DataSource({**config, "DATA_MODE": "mysql"})

    @staticmethod
    def _identity(user: dict[str, Any], session: dict[str, Any]) -> tuple[int, int | None, str]:
        user_id = int(user.get("id") or 0)
        session_id = int(session["session_id"]) if session.get("session_id") is not None else None
        role = "admin" if bool(user.get("is_admin")) else "user"
        return user_id, session_id, role

    def start_visit(self, user: dict[str, Any], session: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        visit_id = _text(values.get("visitId"), "visitId", 32, required=True).lower()
        if not ID_RE.fullmatch(visit_id):
            raise ValueError("visitId格式不合法")
        page_code = _code(values.get("pageCode"), "pageCode", required=True)
        module_code = _code(values.get("moduleCode"), "moduleCode")
        route_path = _text(values.get("routePath"), "routePath", 255, required=True)
        if not route_path.startswith("/") or "?" in route_path or "#" in route_path:
            raise ValueError("routePath必须是不含参数的站内路径")
        referrer = _code(values.get("referrerPageCode"), "referrerPageCode") or None
        device_type = _text(values.get("deviceType"), "deviceType", 20) or "desktop"
        if device_type not in {"desktop", "tablet", "mobile"}:
            raise ValueError("deviceType不合法")
        now = _now()
        user_id, session_id, role = self._identity(user, session)
        params = (
            visit_id, user_id, session_id, role, module_code or None, page_code,
            route_path, _text(values.get("pageTitle"), "pageTitle", 100) or page_code,
            referrer, now, now, _bounded_int(values.get("loadDurationMs"), "loadDurationMs", 600_000),
            _bounded_int(values.get("viewportWidth"), "viewportWidth", 20_000),
            _bounded_int(values.get("viewportHeight"), "viewportHeight", 20_000),
            device_type, _text(values.get("appVersion"), "appVersion", 64) or None,
            now, now,
        )
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO {self.source.database}.{VISIT_TABLE} (
                    visit_id, user_id, session_id, user_role_snapshot, module_code,
                    page_code, route_path, page_title, referrer_page_code,
                    entered_at, last_active_at, load_duration_ms, viewport_width,
                    viewport_height, device_type, app_version, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    last_active_at = VALUES(last_active_at), updated_at = VALUES(updated_at)
                """,
                params,
            )
            return {"visitId": visit_id}
        except Exception as error:
            logging.getLogger(__name__).exception("Telemetry visit start failed")
            if _is_missing_table(error):
                raise TelemetryUnavailable("用户行为埋点表尚未创建") from error
            raise TelemetryUnavailable("用户行为记录暂不可用") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def update_visit(self, user: dict[str, Any], visit_id: str, values: dict[str, Any]) -> dict[str, Any]:
        visit_id = visit_id.strip().lower()
        if not ID_RE.fullmatch(visit_id):
            raise ValueError("visitId格式不合法")
        duration = _bounded_int(values.get("activeDurationMs"), "activeDurationMs", 86_400_000)
        exit_type = _text(values.get("exitType"), "exitType", 32) or None
        if exit_type and exit_type not in EXIT_TYPES:
            raise ValueError("exitType不合法")
        now = _now()
        user_id = int(user.get("id") or 0)
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(
                f"""
                UPDATE {self.source.database}.{VISIT_TABLE}
                SET last_active_at = %s,
                    active_duration_ms = GREATEST(active_duration_ms, %s),
                    left_at = CASE WHEN %s IS NULL THEN left_at ELSE %s END,
                    exit_type = COALESCE(%s, exit_type), updated_at = %s
                WHERE visit_id = %s AND user_id = %s
                """,
                (now, duration, exit_type, now, exit_type, now, visit_id, user_id),
            )
            return {"updated": int(cursor.rowcount or 0) > 0}
        except Exception as error:
            logging.getLogger(__name__).exception("Telemetry visit update failed")
            if _is_missing_table(error):
                raise TelemetryUnavailable("用户行为埋点表尚未创建") from error
            raise TelemetryUnavailable("用户行为记录暂不可用") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    def record_events(self, user: dict[str, Any], session: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        events = values.get("events")
        if not isinstance(events, list) or not events or len(events) > MAX_BATCH:
            raise ValueError(f"events必须包含1至{MAX_BATCH}条记录")
        user_id, session_id, role = self._identity(user, session)
        now = _now()
        cleaned = []
        for item in events:
            if not isinstance(item, dict):
                raise ValueError("事件必须为对象")
            event_id = _text(item.get("eventId"), "eventId", 32, required=True).lower()
            visit_id = _text(item.get("visitId"), "visitId", 32, required=True).lower()
            if not ID_RE.fullmatch(event_id) or not ID_RE.fullmatch(visit_id):
                raise ValueError("事件ID格式不合法")
            event_type = _code(item.get("eventType"), "eventType", required=True)
            if event_type not in EVENT_TYPES:
                raise ValueError("eventType不支持")
            result_status = _text(item.get("resultStatus"), "resultStatus", 20) or "unknown"
            if result_status not in RESULT_STATUSES:
                raise ValueError("resultStatus不合法")
            route_path = _text(item.get("routePath"), "routePath", 255, required=True)
            if not route_path.startswith("/") or "?" in route_path or "#" in route_path:
                raise ValueError("routePath必须是不含参数的站内路径")
            cleaned.append((
                event_id, visit_id, user_id, session_id, role,
                _code(item.get("moduleCode"), "moduleCode") or None,
                _code(item.get("pageCode"), "pageCode", required=True), route_path,
                event_type, _code(item.get("elementCode"), "elementCode") or None,
                _text(item.get("elementName"), "elementName", 100) or None,
                result_status,
                None if item.get("durationMs") in (None, "") else _bounded_int(item.get("durationMs"), "durationMs", 3_600_000),
                _code(item.get("errorCode"), "errorCode") or None,
                _text(item.get("requestId"), "requestId", 64) or None,
                _clean_context(item.get("context")),
                _bounded_int(item.get("eventVersion"), "eventVersion", 100, 1) or 1,
                _occurred_at(item.get("occurredAt"), now), now,
                _text(item.get("appVersion"), "appVersion", 64) or None,
            ))

        connection = cursor = None
        inserted = 0
        action_counts: dict[str, int] = defaultdict(int)
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            for row in cleaned:
                cursor.execute(
                    f"""
                    INSERT IGNORE INTO {self.source.database}.{EVENT_TABLE} (
                        event_id, visit_id, user_id, session_id, user_role_snapshot,
                        module_code, page_code, route_path, event_type, element_code,
                        element_name, result_status, duration_ms, error_code, request_id,
                        context_json, event_version, occurred_at, received_at, app_version
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    row,
                )
                if int(cursor.rowcount or 0) > 0:
                    inserted += 1
                    if row[8] in ACTION_EVENTS:
                        action_counts[row[1]] += 1
            for visit_id, count in action_counts.items():
                cursor.execute(
                    f"""
                    UPDATE {self.source.database}.{VISIT_TABLE}
                    SET action_count = action_count + %s, updated_at = %s
                    WHERE visit_id = %s AND user_id = %s
                    """,
                    (count, now, visit_id, user_id),
                )
            return {"accepted": inserted}
        except Exception as error:
            logging.getLogger(__name__).exception("Telemetry event batch failed")
            if _is_missing_table(error):
                raise TelemetryUnavailable("用户行为埋点表尚未创建") from error
            raise TelemetryUnavailable("用户行为记录暂不可用") from error
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    @staticmethod
    def _empty_dashboard(first: date, last: date, error: str = "") -> dict[str, Any]:
        return {
            "available": not bool(error), "error": error,
            "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
            "summary": {
                "visits": 0, "users": 0, "pages": 0, "averageActiveDurationMs": 0,
                "averageLoadDurationMs": 0, "queryFailureRate": 0, "emptyResultRate": 0,
            },
            "trend": [], "pages": [], "users": [], "paths": [], "recentEvents": [],
        }

    def dashboard(self, actor: dict[str, Any], start_value=None, end_value=None) -> dict[str, Any]:
        if not bool(actor.get("is_admin")):
            raise PermissionError("只有管理员可以查看用户行为监控")
        first, last = parse_period(start_value, end_value)
        start_utc = datetime.combine(first, time.min) - timedelta(hours=8)
        end_utc = datetime.combine(last + timedelta(days=1), time.min) - timedelta(hours=8)
        response = self._empty_dashboard(first, last)
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT COUNT(1), COUNT(DISTINCT user_id), COUNT(DISTINCT page_code),
                       COALESCE(AVG(active_duration_ms), 0), COALESCE(AVG(load_duration_ms), 0)
                FROM {self.source.database}.{VISIT_TABLE}
                WHERE entered_at >= %s AND entered_at < %s
                """,
                (start_utc, end_utc),
            )
            summary_row = cursor.fetchone() or (0, 0, 0, 0, 0)
            cursor.execute(
                f"""
                SELECT page_code, MAX(page_title), MAX(module_code), COUNT(1),
                       COUNT(DISTINCT user_id), COALESCE(AVG(active_duration_ms), 0),
                       COALESCE(AVG(load_duration_ms), 0), COALESCE(SUM(action_count), 0),
                       SUM(CASE WHEN active_duration_ms < 10000 AND action_count = 0 THEN 1 ELSE 0 END)
                FROM {self.source.database}.{VISIT_TABLE}
                WHERE entered_at >= %s AND entered_at < %s
                GROUP BY page_code ORDER BY COUNT(1) DESC, page_code LIMIT 200
                """,
                (start_utc, end_utc),
            )
            page_rows = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT page_code,
                       SUM(event_type = 'query_success'), SUM(event_type = 'query_failed'),
                       SUM(event_type = 'empty_result')
                FROM {self.source.database}.{EVENT_TABLE}
                WHERE occurred_at >= %s AND occurred_at < %s
                GROUP BY page_code
                """,
                (start_utc, end_utc),
            )
            event_by_page = {row[0]: row[1:] for row in cursor.fetchall()}
            cursor.execute(
                f"""
                SELECT DATE(DATE_ADD(entered_at, INTERVAL 8 HOUR)), COUNT(1),
                       COUNT(DISTINCT user_id), COALESCE(AVG(active_duration_ms), 0)
                FROM {self.source.database}.{VISIT_TABLE}
                WHERE entered_at >= %s AND entered_at < %s
                GROUP BY DATE(DATE_ADD(entered_at, INTERVAL 8 HOUR)) ORDER BY 1
                """,
                (start_utc, end_utc),
            )
            trend_rows = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT referrer_page_code, page_code, MAX(page_title), COUNT(1)
                FROM {self.source.database}.{VISIT_TABLE}
                WHERE entered_at >= %s AND entered_at < %s
                  AND referrer_page_code IS NOT NULL AND referrer_page_code <> page_code
                GROUP BY referrer_page_code, page_code ORDER BY COUNT(1) DESC LIMIT 30
                """,
                (start_utc, end_utc),
            )
            path_rows = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT v.user_id, COALESCE(NULLIF(u.full_name, ''), u.username, CONCAT('用户#', v.user_id)),
                       MAX(v.user_role_snapshot), v.page_code, MAX(v.page_title), COUNT(1),
                       COALESCE(SUM(v.active_duration_ms), 0)
                FROM {self.source.database}.{VISIT_TABLE} v
                LEFT JOIN {self.source.database}.sys_user u ON u.id = v.user_id
                WHERE v.entered_at >= %s AND v.entered_at < %s
                GROUP BY v.user_id, u.full_name, u.username, v.page_code
                ORDER BY v.user_id, COUNT(1) DESC LIMIT 2000
                """,
                (start_utc, end_utc),
            )
            user_page_rows = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT DATE_ADD(e.occurred_at, INTERVAL 8 HOUR), e.user_id,
                       COALESCE(NULLIF(u.full_name, ''), u.username, CONCAT('用户#', e.user_id)),
                       e.page_code, e.event_type, e.element_name, e.result_status, e.duration_ms
                FROM {self.source.database}.{EVENT_TABLE} e
                LEFT JOIN {self.source.database}.sys_user u ON u.id = e.user_id
                WHERE e.occurred_at >= %s AND e.occurred_at < %s
                ORDER BY e.occurred_at DESC LIMIT 100
                """,
                (start_utc, end_utc),
            )
            recent_rows = cursor.fetchall()

            pages = []
            total_success = total_failed = total_empty = 0
            for row in page_rows:
                success, failed, empty = (int(value or 0) for value in event_by_page.get(row[0], (0, 0, 0)))
                total_success += success
                total_failed += failed
                total_empty += empty
                pages.append({
                    "pageCode": row[0], "pageTitle": row[1] or row[0], "moduleCode": row[2] or "",
                    "visits": int(row[3] or 0), "users": int(row[4] or 0),
                    "averageActiveDurationMs": int(row[5] or 0), "averageLoadDurationMs": int(row[6] or 0),
                    "actions": int(row[7] or 0), "quickExits": int(row[8] or 0),
                    "querySuccess": success, "queryFailed": failed, "emptyResults": empty,
                    "queryFailureRate": round(failed * 100 / (success + failed), 2) if success + failed else 0,
                    "emptyResultRate": round(empty * 100 / success, 2) if success else 0,
                })

            grouped_users: dict[int, dict[str, Any]] = {}
            for row in user_page_rows:
                current = grouped_users.setdefault(int(row[0]), {
                    "userId": int(row[0]), "displayName": row[1], "role": row[2],
                    "visits": 0, "activeDurationMs": 0, "pageCount": 0,
                    "primaryPageCode": "", "primaryPageTitle": "", "primaryPageVisits": -1,
                })
                visits = int(row[5] or 0)
                current["visits"] += visits
                current["activeDurationMs"] += int(row[6] or 0)
                current["pageCount"] += 1
                if visits > current["primaryPageVisits"]:
                    current["primaryPageVisits"] = visits
                    current["primaryPageCode"] = row[3]
                    current["primaryPageTitle"] = row[4] or row[3]
            users = sorted(grouped_users.values(), key=lambda item: (-item["visits"], item["displayName"]))
            for item in users:
                item.pop("primaryPageVisits", None)

            response.update({
                "available": True,
                "summary": {
                    "visits": int(summary_row[0] or 0), "users": int(summary_row[1] or 0),
                    "pages": int(summary_row[2] or 0), "averageActiveDurationMs": int(summary_row[3] or 0),
                    "averageLoadDurationMs": int(summary_row[4] or 0),
                    "queryFailureRate": round(total_failed * 100 / (total_success + total_failed), 2) if total_success + total_failed else 0,
                    "emptyResultRate": round(total_empty * 100 / total_success, 2) if total_success else 0,
                },
                "pages": pages,
                "trend": [{"date": str(row[0]), "visits": int(row[1]), "users": int(row[2]), "averageActiveDurationMs": int(row[3] or 0)} for row in trend_rows],
                "paths": [{"fromPageCode": row[0], "toPageCode": row[1], "toPageTitle": row[2] or row[1], "visits": int(row[3])} for row in path_rows],
                "users": users,
                "recentEvents": [{
                    "occurredAt": row[0].isoformat(timespec="seconds") if isinstance(row[0], datetime) else str(row[0]),
                    "userId": int(row[1]), "displayName": row[2], "pageCode": row[3],
                    "eventType": row[4], "elementName": row[5] or "", "resultStatus": row[6],
                    "durationMs": int(row[7]) if row[7] is not None else None,
                } for row in recent_rows],
            })
            return response
        except Exception as error:
            logging.getLogger(__name__).exception("Telemetry dashboard query failed")
            message = "用户行为埋点表尚未创建，请先执行建表SQL。" if _is_missing_table(error) else "用户行为监控查询失败，请检查MySQL连接和表结构。"
            return self._empty_dashboard(first, last, message)
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
