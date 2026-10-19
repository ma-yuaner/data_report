"""Target-management daily ETL.

The job reads operational ERP ticket data through the independent read-only
connection and writes only the target-management DWS/ADS tables in sibebid.
It intentionally does not import or modify the legacy report scripts.
"""
from __future__ import annotations

import argparse
import calendar
import json
import logging
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from .config import Config
from .services.data_source import DataSource
from .time_utils import business_now


LOGGER = logging.getLogger(__name__)
ZERO = Decimal("0")
TARGET_ETL_RUN_LOCK = "datareport_target_management_etl"
WEEKDAY_WEIGHTS = {
    0: Decimal("0.1429"),
    1: Decimal("0.1622"),
    2: Decimal("0.1592"),
    3: Decimal("0.1535"),
    4: Decimal("0.1485"),
    5: Decimal("0.1221"),
    6: Decimal("0.1116"),
}
SEGMENT_METRICS = {
    "ISSUED_AIRLIFT_SEGMENT",
    "REWARD_SEGMENT",
    "GDS_1A_ELIGIBLE_SEGMENT",
}
SUPPORT_METRICS = (
    "ISSUE_PROFIT",
    "LOSS_AMOUNT",
    "LOSS_TICKET_COUNT",
    "LOSS_SEGMENT_COUNT",
)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _sum_nullable(values: Iterable[Any]) -> Decimal | None:
    converted = [_decimal(value) for value in values]
    present = [value for value in converted if value is not None]
    return sum(present, ZERO) if present else None


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _month_bounds(value: date) -> tuple[date, date]:
    return value.replace(day=1), value.replace(day=calendar.monthrange(value.year, value.month)[1])


def weekday_progress_rate(period_start: date, period_end: date, through_date: date) -> Decimal:
    """Return the normalized cumulative weekday-weight curve as a 0..1 rate."""
    if through_date < period_start:
        return ZERO
    through_date = min(through_date, period_end)
    weights: list[tuple[date, Decimal]] = []
    current = period_start
    while current <= period_end:
        weights.append((current, WEEKDAY_WEIGHTS[current.weekday()]))
        current += timedelta(days=1)
    total = sum((weight for _, weight in weights), ZERO)
    elapsed = sum((weight for day, weight in weights if day <= through_date), ZERO)
    return elapsed / total if total else ZERO


def source_daily_sql(database: str) -> str:
    """ERP query matching the supplied legacy Platform/1A/daily-report rules."""
    return f"""
        SELECT ticket.business_date, ticket.platform_code, ticket.gds_code,
               ticket.policy_operator_id, ticket.policy_operator_name,
               sum(ticket.segment_count) AS issued_segments,
               count(*) AS issued_ticket_count,
               count(ticket.issue_profit) AS issued_profit_count,
               sum(ticket.issue_profit) AS issued_profit,
               sum(CASE WHEN ticket.issue_profit < 0 THEN -ticket.issue_profit ELSE 0 END) AS loss_amount,
               sum(CASE WHEN ticket.issue_profit < 0 THEN 1 ELSE 0 END) AS loss_ticket_count,
               sum(CASE WHEN ticket.issue_profit < 0 THEN ticket.segment_count ELSE 0 END) AS loss_segment_count,
               sum(ticket.reward_trip_count) AS reward_segments,
               sum(CASE WHEN ticket.reward_trip_count > 0 THEN 1 ELSE 0 END) AS reward_ticket_count,
               count(CASE WHEN ticket.reward_trip_count > 0 THEN ticket.issue_profit END) AS reward_profit_count,
               sum(CASE WHEN ticket.reward_trip_count > 0 THEN ticket.issue_profit END) AS reward_profit,
               sum(CASE WHEN ticket.reward_trip_count > 0 AND ticket.issue_profit < 0
                        THEN -ticket.issue_profit ELSE 0 END) AS reward_loss_amount,
               sum(CASE WHEN ticket.reward_trip_count > 0 AND ticket.issue_profit < 0 THEN 1 ELSE 0 END) AS reward_loss_ticket_count,
               sum(CASE WHEN ticket.reward_trip_count > 0 AND ticket.issue_profit < 0
                        THEN ticket.segment_count ELSE 0 END) AS reward_loss_segment_count,
               sum(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                        THEN ticket.segment_count ELSE 0 END) AS eligible_1a_segments,
               sum(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                        THEN 1 ELSE 0 END) AS eligible_1a_ticket_count,
               count(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                          THEN ticket.issue_profit END) AS eligible_1a_profit_count,
               sum(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                        THEN ticket.issue_profit END) AS eligible_1a_profit,
               sum(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                             AND ticket.issue_profit < 0 THEN -ticket.issue_profit ELSE 0 END) AS eligible_1a_loss_amount,
               sum(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                             AND ticket.issue_profit < 0 THEN 1 ELSE 0 END) AS eligible_1a_loss_ticket_count,
               sum(CASE WHEN ticket.gds_code='1A' AND ticket.reward_flag=1 AND ticket.has_non_infant=1
                             AND ticket.issue_profit < 0 THEN ticket.segment_count ELSE 0 END) AS eligible_1a_loss_segment_count,
               max(ticket.source_max_time) AS source_max_time
        FROM (
            SELECT DATE(oi.issue_ticket_time) AS business_date,
                   coalesce(o.ota_code, '') AS platform_code,
                   coalesce(oi.issue_gds_channel, '') AS gds_code,
                   o.policy_operator_id,
                   coalesce(o.policy_operator, '') AS policy_operator_name,
                   oi.id AS issue_id,
                   oi.issue_profit,
                   coalesce(oi.reward_trip_count, 0) AS reward_trip_count,
                   oi.reward_flag,
                   EXISTS (SELECT 1 FROM {database}.order_info_passenger adult
                           WHERE adult.order_id=o.id AND adult.age_type<>'INF') AS has_non_infant,
                   count(DISTINCT segment.id) AS segment_count,
                   max(coalesce(oi.update_time, oi.create_time)) AS source_max_time
            FROM {database}.order_info_issue oi
            JOIN {database}.order_info o ON o.id=oi.order_id
            JOIN {database}.order_info_issue_segment link ON link.issue_id=oi.id
            JOIN {database}.order_info_segment segment ON segment.id=link.segment_id
                                                        AND segment.airlift_flag=1
            WHERE oi.issue_ticket_time >= %s
              AND oi.issue_ticket_time < %s
              AND o.order_status='TICKETED'
              AND oi.refund_flag<>3
            GROUP BY DATE(oi.issue_ticket_time), o.ota_code, oi.issue_gds_channel,
                     o.policy_operator_id, o.policy_operator, oi.id, oi.issue_profit,
                     oi.reward_trip_count, oi.reward_flag, o.id
        ) ticket
        GROUP BY ticket.business_date, ticket.platform_code, ticket.gds_code,
                 ticket.policy_operator_id, ticket.policy_operator_name
    """


@dataclass(frozen=True)
class Scope:
    scene: str
    dimension_key: str
    metric_code: str
    platform_code: str = ""
    platform_name: str = ""
    gds_code: str = ""
    policy_group_code: str = ""
    policy_group_name: str = ""
    department_code: str = ""
    department_name: str = ""
    policy_leader_user_id: int | None = None
    policy_leader_name: str = ""
    member_user_ids: tuple[int, ...] = ()
    target_item_id: int | None = None
    plan_id: int | None = None
    target_value: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    progress_curve_code: str = "WEEKDAY_WEIGHT"


class TargetManagementDailyJob:
    def __init__(self, config: dict[str, Any]):
        main_config = dict(config)
        main_config["DATA_MODE"] = "mysql"
        self.main = DataSource(main_config)
        self.target_database = self.main.database
        source_config = dict(main_config)
        source_config.update({
            "MYSQL_HOST": config.get("TARGET_ERP_MYSQL_HOST") or config.get("ERP_ROSTER_MYSQL_HOST") or config.get("MYSQL_HOST"),
            "MYSQL_PORT": config.get("TARGET_ERP_MYSQL_PORT") or config.get("ERP_ROSTER_MYSQL_PORT") or config.get("MYSQL_PORT", 3306),
            "MYSQL_DATABASE": config.get("TARGET_ERP_DATABASE") or config.get("ERP_ROSTER_DATABASE") or "sibedb",
            "MYSQL_USER": config.get("TARGET_ERP_MYSQL_USER") or config.get("ERP_ROSTER_MYSQL_USER") or config.get("MYSQL_USER"),
            "MYSQL_PASSWORD": config.get("TARGET_ERP_MYSQL_PASSWORD") or config.get("ERP_ROSTER_MYSQL_PASSWORD") or config.get("MYSQL_PASSWORD"),
            "MYSQL_CHARSET": config.get("TARGET_ERP_MYSQL_CHARSET") or config.get("ERP_ROSTER_MYSQL_CHARSET") or "utf8mb4",
        })
        self.erp = DataSource(source_config)
        self.erp_database = self.erp.database
        self.platform_database = str(config.get("ERP_PLATFORM_DATABASE", "sibelog"))
        self.platform_table = str(config.get("ERP_PLATFORM_TABLE", "sibe_ota"))
        for value in (self.target_database, self.erp_database, self.platform_database, self.platform_table):
            if not value.replace("_", "a").isalnum() or value[0].isdigit():
                raise RuntimeError("目标进度ETL数据库或表名配置不合法")

    def acquire_run_lock(self, timeout_seconds: int = 0) -> Any | None:
        """Hold a cross-process MySQL advisory lock for one ETL run."""
        connection = self.main.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT GET_LOCK(%s, %s)", (TARGET_ETL_RUN_LOCK, max(0, int(timeout_seconds))))
                row = cursor.fetchone()
                acquired = bool(row and int(row[0]) == 1)
            if acquired:
                return connection
        except Exception:
            connection.close()
            raise
        connection.close()
        return None

    @staticmethod
    def release_run_lock(connection: Any | None) -> None:
        if connection is None:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (TARGET_ETL_RUN_LOCK,))
        finally:
            connection.close()

    def _load_scopes(self, biz_date: date) -> list[Scope]:
        import pymysql

        connection = self.main.connect()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT ota_code, ota_cname
                        FROM {self.platform_database}.{self.platform_table}
                        WHERE status=1
                          AND (start_time IS NULL OR start_time<%s)
                          AND (end_time IS NULL OR end_time>=%s)""",
                    (biz_date + timedelta(days=1), biz_date),
                )
                platforms = [dict(row) for row in cursor.fetchall()]
                cursor.execute(
                    f"""SELECT i.id AS target_item_id, i.plan_id, p.target_scene,
                               p.period_start, p.period_end, p.progress_curve_code,
                               i.metric_code, i.target_value, i.department_code,
                               i.department_name_snapshot, i.platform_code,
                               i.platform_name_snapshot, i.gds_code,
                               i.policy_group_code, i.policy_group_name_snapshot,
                               i.policy_leader_user_id, i.policy_leader_name_snapshot
                        FROM {self.target_database}.biz_target_plan p
                        JOIN {self.target_database}.biz_target_item i ON i.plan_id=p.id
                        WHERE p.status IN ('ACTIVE','PUBLISHED') AND i.enabled=1
                          AND p.period_start<=%s AND p.period_end>=%s
                          AND i.metric_code IN ('ISSUED_AIRLIFT_SEGMENT','REWARD_SEGMENT','GDS_1A_ELIGIBLE_SEGMENT')""",
                    (biz_date, biz_date),
                )
                items = [dict(row) for row in cursor.fetchall()]
                plan_ids = sorted({int(row["plan_id"]) for row in items if row["target_scene"] == "POLICY"})
                members: dict[tuple[int, str], list[int]] = defaultdict(list)
                if plan_ids:
                    placeholders = ",".join(["%s"] * len(plan_ids))
                    cursor.execute(
                        f"""SELECT plan_id, policy_group_code, member_user_id
                            FROM {self.target_database}.biz_target_policy_member
                            WHERE plan_id IN ({placeholders})""",
                        tuple(plan_ids),
                    )
                    for row in cursor.fetchall():
                        members[(int(row["plan_id"]), str(row["policy_group_code"]))].append(int(row["member_user_id"]))
        finally:
            connection.close()

        scopes: list[Scope] = []
        configured_platforms = {str(row["platform_code"]) for row in items if row["target_scene"] == "PLATFORM"}
        for row in platforms:
            code = str(row["ota_code"])
            if code not in configured_platforms:
                scopes.append(Scope(
                    scene="PLATFORM", dimension_key=f"PLATFORM:{code}",
                    metric_code="ISSUED_AIRLIFT_SEGMENT", platform_code=code,
                    platform_name=str(row["ota_cname"] or code),
                ))
        for row in items:
            scene = str(row["target_scene"])
            metric_code = str(row["metric_code"])
            if metric_code == "GDS_1A_ELIGIBLE_SEGMENT" and str(row["gds_code"]).upper() != "1A":
                LOGGER.warning("Skipping invalid 1A metric target item %s for GDS %s", row["target_item_id"], row["gds_code"])
                continue
            group_code = str(row["policy_group_code"] or "")
            if scene == "PLATFORM":
                dimension_key = f"PLATFORM:{row['platform_code']}"
            elif scene == "GDS":
                dimension_key = f"GDS:{row['gds_code']}"
            else:
                dimension_key = f"POLICY:{group_code}:GDS:{row['gds_code']}"
            scopes.append(Scope(
                scene=scene, dimension_key=dimension_key, metric_code=metric_code,
                platform_code=str(row["platform_code"] or ""),
                platform_name=str(row["platform_name_snapshot"] or ""),
                gds_code=str(row["gds_code"] or ""),
                policy_group_code=group_code,
                policy_group_name=str(row["policy_group_name_snapshot"] or ""),
                department_code=str(row["department_code"] or ""),
                department_name=str(row["department_name_snapshot"] or ""),
                policy_leader_user_id=int(row["policy_leader_user_id"]) if row["policy_leader_user_id"] is not None else None,
                policy_leader_name=str(row["policy_leader_name_snapshot"] or ""),
                member_user_ids=tuple(members.get((int(row["plan_id"]), group_code), [])),
                target_item_id=int(row["target_item_id"]), plan_id=int(row["plan_id"]),
                target_value=_decimal(row["target_value"]), period_start=row["period_start"],
                period_end=row["period_end"], progress_curve_code=str(row["progress_curve_code"]),
            ))
        return scopes

    def _read_source(self, biz_date: date) -> list[dict[str, Any]]:
        import pymysql

        connection = self.erp.connect()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(source_daily_sql(self.erp_database), (biz_date, biz_date + timedelta(days=1)))
                return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    @staticmethod
    def _rows_for_scope(scope: Scope, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if scope.scene == "PLATFORM":
            return [row for row in rows if str(row["platform_code"]) == scope.platform_code]
        if scope.scene == "GDS":
            return [row for row in rows if str(row["gds_code"]).upper() == scope.gds_code.upper()]
        members = set(scope.member_user_ids)
        return [row for row in rows if str(row["gds_code"]).upper() == scope.gds_code.upper()
                and row["policy_operator_id"] is not None and int(row["policy_operator_id"]) in members]

    @staticmethod
    def _measure_fields(metric_code: str) -> tuple[str, str, str, str, str, str]:
        if metric_code == "REWARD_SEGMENT":
            return ("reward_segments", "reward_ticket_count", "reward_profit_count",
                    "reward_profit", "reward_loss_amount", "reward_loss_ticket_count")
        if metric_code == "GDS_1A_ELIGIBLE_SEGMENT":
            return ("eligible_1a_segments", "eligible_1a_ticket_count", "eligible_1a_profit_count",
                    "eligible_1a_profit", "eligible_1a_loss_amount", "eligible_1a_loss_ticket_count")
        return ("issued_segments", "issued_ticket_count", "issued_profit_count",
                "issued_profit", "loss_amount", "loss_ticket_count")

    def _records(self, biz_date: date, scopes: list[Scope], rows: list[dict[str, Any]], batch_id: str) -> list[dict[str, Any]]:
        source_ready = bool(rows)
        records: list[dict[str, Any]] = []
        for scope in scopes:
            selected = self._rows_for_scope(scope, rows)
            segment_field, ticket_field, profit_count_field, profit_field, loss_amount_field, loss_ticket_field = self._measure_fields(scope.metric_code)
            segment_value = sum((_decimal(row[segment_field]) or ZERO for row in selected), ZERO) if source_ready else None
            ticket_count = sum((int(row[ticket_field] or 0) for row in selected), 0) if source_ready else None
            profit_count = sum((int(row[profit_count_field] or 0) for row in selected), 0) if source_ready else 0
            profit_complete = source_ready and profit_count == (ticket_count or 0)
            profit_value = (ZERO if not ticket_count else _sum_nullable(row[profit_field] for row in selected)) if profit_complete else None
            loss_amount = sum((_decimal(row[loss_amount_field]) or ZERO for row in selected), ZERO) if profit_complete else None
            loss_tickets = sum((int(row[loss_ticket_field] or 0) for row in selected), 0) if profit_complete else None
            loss_segment_field = {
                "REWARD_SEGMENT": "reward_loss_segment_count",
                "GDS_1A_ELIGIBLE_SEGMENT": "eligible_1a_loss_segment_count",
            }.get(scope.metric_code, "loss_segment_count")
            loss_segments = sum((_decimal(row[loss_segment_field]) or ZERO for row in selected), ZERO) if profit_complete else None
            source_max_time = max((row["source_max_time"] for row in selected if row.get("source_max_time")), default=None)
            common = {
                "business_date": biz_date, "metric_version": "V1", "dimension_key": scope.dimension_key,
                "department_code": scope.department_code, "department_name": scope.department_name,
                "platform_code": scope.platform_code, "platform_name": scope.platform_name,
                "gds_code": scope.gds_code, "policy_group_code": scope.policy_group_code,
                "policy_group_name": scope.policy_group_name,
                "policy_leader_user_id": scope.policy_leader_user_id,
                "policy_leader_name": scope.policy_leader_name,
                "policy_member_user_id": None, "policy_member_name": "",
                "source_system": "ERP", "source_max_time": source_max_time, "etl_batch_id": batch_id,
            }
            records.append({**common, "metric_code": scope.metric_code, "actual_value": segment_value,
                            "issue_profit": profit_value, "ticket_count": ticket_count,
                            "data_status": "READY" if source_ready else "MISSING"})
            status = "READY" if profit_complete else ("PARTIAL" if source_ready else "MISSING")
            for code, value in (("ISSUE_PROFIT", profit_value), ("LOSS_AMOUNT", loss_amount),
                                ("LOSS_TICKET_COUNT", loss_tickets), ("LOSS_SEGMENT_COUNT", loss_segments)):
                records.append({**common, "metric_code": code, "actual_value": value,
                                "issue_profit": None, "ticket_count": None, "data_status": status})
        return records

    def _write_dws(self, connection: Any, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        sql = f"""INSERT INTO {self.target_database}.dws_target_metric_day
            (business_date,metric_code,metric_version,dimension_key,department_code,department_name,
             platform_code,platform_name,gds_code,policy_group_code,policy_group_name,
             policy_leader_user_id,policy_leader_name,policy_member_user_id,policy_member_name,
             actual_value,issue_profit,ticket_count,data_status,source_system,source_max_time,etl_batch_id)
            VALUES (%(business_date)s,%(metric_code)s,%(metric_version)s,%(dimension_key)s,
                    %(department_code)s,%(department_name)s,%(platform_code)s,%(platform_name)s,
                    %(gds_code)s,%(policy_group_code)s,%(policy_group_name)s,
                    %(policy_leader_user_id)s,%(policy_leader_name)s,%(policy_member_user_id)s,
                    %(policy_member_name)s,%(actual_value)s,%(issue_profit)s,%(ticket_count)s,
                    %(data_status)s,%(source_system)s,%(source_max_time)s,%(etl_batch_id)s)
            ON DUPLICATE KEY UPDATE department_code=VALUES(department_code),
              department_name=VALUES(department_name),platform_code=VALUES(platform_code),
              platform_name=VALUES(platform_name),gds_code=VALUES(gds_code),
              policy_group_code=VALUES(policy_group_code),policy_group_name=VALUES(policy_group_name),
              policy_leader_user_id=VALUES(policy_leader_user_id),policy_leader_name=VALUES(policy_leader_name),
              actual_value=VALUES(actual_value),issue_profit=VALUES(issue_profit),ticket_count=VALUES(ticket_count),
              data_status=VALUES(data_status),source_max_time=VALUES(source_max_time),
              etl_batch_id=VALUES(etl_batch_id),etl_updated_at=CURRENT_TIMESTAMP"""
        with connection.cursor() as cursor:
            cursor.executemany(sql, records)

    def _write_ads(self, connection: Any, biz_date: date, scopes: list[Scope], batch_id: str) -> int:
        import pymysql

        item_scopes = [scope for scope in scopes if scope.target_item_id is not None]
        written = 0
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            for scope in item_scopes:
                cursor.execute(
                    f"""SELECT metric_code, count(DISTINCT business_date) AS day_count,
                               sum(actual_value) AS actual_value,
                               sum(CASE WHEN data_status<>'READY' OR actual_value IS NULL THEN 1 ELSE 0 END) AS incomplete_count,
                               max(source_max_time) AS source_max_time
                        FROM {self.target_database}.dws_target_metric_day
                        WHERE dimension_key=%s AND business_date BETWEEN %s AND %s
                          AND metric_code IN (%s,'ISSUE_PROFIT')
                        GROUP BY metric_code""",
                    (scope.dimension_key, scope.period_start, biz_date, scope.metric_code),
                )
                metrics = {str(row["metric_code"]): dict(row) for row in cursor.fetchall()}
                expected_days = (biz_date - scope.period_start).days + 1
                actual_row = metrics.get(scope.metric_code)
                profit_row = metrics.get("ISSUE_PROFIT")
                actual_ready = bool(actual_row and int(actual_row["day_count"]) == expected_days
                                    and int(actual_row["incomplete_count"] or 0) == 0)
                profit_ready = bool(profit_row and int(profit_row["day_count"]) == expected_days
                                    and int(profit_row["incomplete_count"] or 0) == 0)
                cursor.execute(
                    f"""SELECT actual_value FROM {self.target_database}.dws_target_metric_day
                        WHERE business_date=%s AND metric_code=%s AND dimension_key=%s""",
                    (biz_date, scope.metric_code, scope.dimension_key),
                )
                today_row = cursor.fetchone()
                actual_today = _decimal(today_row["actual_value"]) if actual_ready and today_row else None
                actual = _decimal(actual_row["actual_value"]) if actual_ready and actual_row else None
                profit = _decimal(profit_row["actual_value"]) if profit_ready and profit_row else None
                target = scope.target_value or ZERO
                expected_rate = weekday_progress_rate(scope.period_start, scope.period_end, biz_date)
                completion = actual / target if actual is not None and target else None
                remaining = max(target - actual, ZERO) if actual is not None else None
                days_left = max((scope.period_end - biz_date).days, 0)
                required = (remaining / Decimal(days_left)) if remaining is not None and days_left else (ZERO if remaining == ZERO else None)
                status = "READY" if actual_ready else "MISSING"
                source_max_time = actual_row.get("source_max_time") if actual_row else None
                cursor.execute(
                    f"""INSERT INTO {self.target_database}.ads_target_progress_day
                        (plan_id,target_item_id,stat_date,target_value_snapshot,actual_today,actual_cumulative,
                         planned_cumulative_rate,completion_rate,progress_gap_rate,remaining_value,
                         required_daily_value,profit_cumulative,profit_per_segment,data_status,
                         data_through_date,etl_batch_id)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE target_value_snapshot=VALUES(target_value_snapshot),
                          actual_today=VALUES(actual_today),actual_cumulative=VALUES(actual_cumulative),
                          planned_cumulative_rate=VALUES(planned_cumulative_rate),completion_rate=VALUES(completion_rate),
                          progress_gap_rate=VALUES(progress_gap_rate),remaining_value=VALUES(remaining_value),
                          required_daily_value=VALUES(required_daily_value),profit_cumulative=VALUES(profit_cumulative),
                          profit_per_segment=VALUES(profit_per_segment),data_status=VALUES(data_status),
                          data_through_date=VALUES(data_through_date),etl_batch_id=VALUES(etl_batch_id),
                          etl_updated_at=CURRENT_TIMESTAMP""",
                    (scope.plan_id, scope.target_item_id, biz_date, target, actual_today, actual,
                     expected_rate, completion, completion - expected_rate if completion is not None else None,
                     remaining, required, profit, profit / actual if profit is not None and actual else None,
                     status, biz_date if actual_ready else None, batch_id),
                )
                written += 1
        return written

    def run_date(self, biz_date: date, *, dry_run: bool = False) -> dict[str, Any]:
        if biz_date > business_now().date():
            raise ValueError("目标进度不能处理未来业务日")
        scopes = self._load_scopes(biz_date)
        source_rows = self._read_source(biz_date)
        batch_id = f"TARGET_{biz_date:%Y%m%d}_{uuid.uuid4().hex[:12].upper()}"
        records = self._records(biz_date, scopes, source_rows, batch_id)
        result = {
            "businessDate": biz_date.isoformat(), "dryRun": dry_run, "batchId": batch_id,
            "sourceGroups": len(source_rows), "scopeCount": len(scopes), "dwsRows": len(records),
            "adsRows": 0, "dataStatus": "READY" if source_rows else "MISSING",
        }
        if dry_run:
            return result
        connection = self.main.connect()
        try:
            connection.begin()
            self._write_dws(connection, records)
            result["adsRows"] = self._write_ads(connection, biz_date, scopes, batch_id)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def run_range(self, start_date: date, end_date: date, *, dry_run: bool = False) -> list[dict[str, Any]]:
        if end_date < start_date:
            raise ValueError("结束日期不能早于开始日期")
        results = []
        current = start_date
        while current <= end_date:
            results.append(self.run_date(current, dry_run=dry_run))
            current += timedelta(days=1)
        return results

    def pending_dates(self, through_date: date) -> list[date]:
        """Return dates that need an initial build or a rebuild after config changes.

        A target item is considered current only when every applicable business day has
        an ADS snapshot and the newest snapshot was produced after the latest plan,
        item, or policy-membership change.  The caller also refreshes ``through_date``
        every cycle so late-arriving ERP records are picked up.
        """
        import pymysql

        connection = self.main.connect()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    f"""SELECT i.id AS target_item_id, p.period_start, p.period_end,
                               greatest(p.updated_at, i.updated_at,
                                   coalesce(max(pm.updated_at), '1970-01-01')) AS config_updated_at
                        FROM {self.target_database}.biz_target_plan p
                        JOIN {self.target_database}.biz_target_item i ON i.plan_id=p.id
                        LEFT JOIN {self.target_database}.biz_target_policy_member pm
                          ON pm.plan_id=i.plan_id
                         AND pm.policy_group_code=i.policy_group_code
                         AND p.target_scene='POLICY'
                        WHERE p.status IN ('ACTIVE','PUBLISHED') AND i.enabled=1
                          AND p.period_start<=%s
                        GROUP BY i.id, p.period_start, p.period_end, p.updated_at, i.updated_at""",
                    (through_date,),
                )
                items = [dict(row) for row in cursor.fetchall()]
                item_ids = [int(row["target_item_id"]) for row in items]
                snapshots: dict[int, dict[date, datetime]] = defaultdict(dict)
                if item_ids:
                    placeholders = ",".join(["%s"] * len(item_ids))
                    cursor.execute(
                        f"""SELECT target_item_id, stat_date, etl_updated_at
                            FROM {self.target_database}.ads_target_progress_day
                            WHERE target_item_id IN ({placeholders}) AND stat_date<=%s""",
                        (*item_ids, through_date),
                    )
                    for row in cursor.fetchall():
                        snapshots[int(row["target_item_id"])][row["stat_date"]] = row["etl_updated_at"]
        finally:
            connection.close()

        pending: set[date] = {through_date}
        for item in items:
            start = item["period_start"]
            end = min(item["period_end"], through_date)
            if end < start:
                continue
            item_snapshots = snapshots.get(int(item["target_item_id"]), {})
            config_updated_at = _datetime(item["config_updated_at"])
            current = start
            while current <= end:
                snapshot_updated_at = item_snapshots.get(current)
                if snapshot_updated_at is None or _datetime(snapshot_updated_at) < config_updated_at:
                    pending.add(current)
                current += timedelta(days=1)
        return sorted(day for day in pending if day <= business_now().date())

    def run_incremental(self, through_date: date | None = None, *, dry_run: bool = False) -> list[dict[str, Any]]:
        """Refresh the latest complete day and catch up new or changed targets."""
        through_date = through_date or business_now().date()
        return [self.run_date(day, dry_run=dry_run) for day in self.pending_dates(through_date)]


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("日期必须为 YYYY-MM-DD") from error


def _config_dict() -> dict[str, Any]:
    return {name: getattr(Config, name) for name in dir(Config) if name.isupper()}


def main() -> int:
    parser = argparse.ArgumentParser(description="目标管理每日真实数据ETL")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--biz-date", type=_parse_date, help="处理单个业务日 YYYY-MM-DD")
    group.add_argument("--start-date", type=_parse_date, help="补数开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, help="补数结束日期，必须与--start-date一起使用")
    parser.add_argument("--dry-run", action="store_true", help="只读核对，不写目标表")
    args = parser.parse_args()
    today = business_now().date()
    if args.start_date and not args.end_date:
        parser.error("--start-date 必须同时提供 --end-date")
    if args.end_date and not args.start_date:
        parser.error("--end-date 必须同时提供 --start-date")
    start = args.start_date or args.biz_date or today
    end = args.end_date or args.biz_date or today
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    results = TargetManagementDailyJob(_config_dict()).run_range(start, end, dry_run=args.dry_run)
    print(json.dumps({"success": True, "results": results}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
