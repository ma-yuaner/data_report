"""Read only a fully published profit-volume batch from the application's MySQL."""
import logging
from contextlib import closing
from datetime import date
from decimal import Decimal

from pymysql import MySQLError

from .comprehensive_analysis import DIMENSIONS
from .data_source import DataSource
from .profit_volume import Issuance, IssuanceSnapshot, MAX_RECORDS, SnapshotUnavailable

logger = logging.getLogger(__name__)
DIMENSION_COLUMNS = tuple(dict.fromkeys(column for columns in DIMENSIONS.values() for column in columns))


class ProfitVolumeMySQLSource:
    def __init__(self, config, allowed_users):
        options = {**config, "DATA_MODE": "mysql"}
        if config.get("PROFIT_VOLUME_MYSQL_DATABASE"):
            options["MYSQL_DATABASE"] = config["PROFIT_VOLUME_MYSQL_DATABASE"]
        self.source = DataSource(options)
        self.allowed_users = frozenset(allowed_users)

    def __call__(self, start, end, dimensions, principal, version, target):
        if not principal or (not principal.get("is_admin") and principal.get("username") not in self.allowed_users):
            raise PermissionError
        try:
            with closing(self.source.connect()) as conn, closing(conn.cursor()) as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
                cursor.execute(
                    "SELECT source_ads_run_id FROM bi_issue_profit_volume_sync "
                    "WHERE row_type='coverage' GROUP BY source_ads_run_id LIMIT 2"
                )
                batches = cursor.fetchall()
                if not batches:
                    raise SnapshotUnavailable("盈/冲尚无已发布的 MySQL 同步批次。")
                if len(batches) != 1 or not batches[0][0]:
                    raise SnapshotUnavailable("盈/冲 MySQL 覆盖记录的同步批次不一致。")
                batch = batches[0][0]
                if version and batch != version:
                    raise SnapshotUnavailable("结果版本已变化，请重新查询日报。")
                cursor.execute(
                    "SELECT business_date, COUNT(*), MIN(source_row_count) "
                    "FROM bi_issue_profit_volume_sync WHERE source_ads_run_id=%s "
                    "AND row_type='coverage' AND business_date BETWEEN %s AND %s "
                    "GROUP BY business_date",
                    (batch, start, end),
                )
                coverage = cursor.fetchall()
                if any(count != 1 or expected is None or expected < 0 for _, count, expected in coverage):
                    raise SnapshotUnavailable("盈/冲 MySQL 日期覆盖记录异常。")
                covered = frozenset(date.fromisoformat(str(day)) for day, _, _ in coverage)
                if len(covered) != (end - start).days + 1:
                    return IssuanceSnapshot(batch, covered, ())
                conditions = ["source_ads_run_id=%s", "row_type='data'", "business_date BETWEEN %s AND %s"]
                params = [batch, target or start, target or end]
                dimension_conditions = []
                dimension_params = []
                for dimension, values in dimensions.items():
                    for column, value in zip(DIMENSIONS[dimension], values):
                        dimension_conditions.append(f"BINARY {column} <=> %s")
                        dimension_params.append(value)
                cursor.execute(
                    "SELECT business_date, issue_id, order_reference, segments, issue_profit_raw, ticket_no, ticket_no_raw, "
                    + ", ".join(DIMENSION_COLUMNS) + " "
                    "FROM bi_issue_profit_volume_sync WHERE " + " AND ".join(conditions + dimension_conditions)
                    + " ORDER BY business_date, BINARY issue_id LIMIT %s",
                    [*params, *dimension_params, MAX_RECORDS + 1],
                )
                rows = cursor.fetchall()
                if len(rows) > MAX_RECORDS:
                    raise SnapshotUnavailable("明细量超过查询上限，请缩小日期或筛选范围。")
                if not dimensions:
                    expected = {date.fromisoformat(str(day)): count for day, _, count in coverage}
                    actual = dict.fromkeys((day for day in covered if target is None or day == target), 0)
                    for day, *_ in rows:
                        actual[date.fromisoformat(str(day))] += 1
                    if any(count != expected[day] for day, count in actual.items()):
                        raise SnapshotUnavailable("盈/冲 MySQL 明细行数与日期覆盖记录不一致。")
                return IssuanceSnapshot(batch, covered, tuple(
                    Issuance(date.fromisoformat(str(day)), key, order, segments,
                             Decimal(amount) if amount is not None else None,
                             dict(zip(DIMENSION_COLUMNS, values)), ticket, raw)
                    for day, key, order, segments, amount, ticket, raw, *values in rows
                ))
        except (MySQLError, RuntimeError, ValueError, ArithmeticError):
            logger.warning("Profit-volume MySQL read failed", exc_info=True)
            raise SnapshotUnavailable("盈/冲 MySQL 数据不可用，请检查同步状态后重试。") from None
