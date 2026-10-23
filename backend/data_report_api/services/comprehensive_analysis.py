"""Read the MySQL ADS mirror, never the four raw facts or demonstration data."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import BoundedSemaphore
from time import perf_counter
from typing import Any, Iterable

from ..shared.periods import parse_analysis_period

from .data_source import DataSource

BUSINESSES = ("issue", "refund", "change", "ancillary")
DIMENSIONS = {
    "platform": ("ota_code", "ota_cname"),
    "site": ("ota_code", "ota_site_code", "ota_site_cname"),
    "airline": ("airline_code",),
    "product": ("ota_code", "ota_cname", "ticket_product_raw"),
    "policy": ("policy_operator",),
    "supplier": ("supplier_name",),
    "gds": ("gds_code",),
}
COLUMNS = (
    "row_key", "dt", "business_date", "row_type", "business_type", "ota_code", "ota_cname",
    "ota_site_code", "ota_site_cname", "airline_code", "ticket_product_raw", "business_count",
    "segment_count", "segment_missing_count", "known_profit_cny", "estimated_profit_cny",
    "profit_missing_count", "source_row_count", "metric_version", "etl_run_id", "etl_updated_at",
    "policy_operator",
    "supplier_name", "gds_code",
)
SORT_FIELDS = ("segments", "profit")
MAX_ROWS = 1_000_000
FETCH_BATCH_SIZE = 2_000
QUERY_BUDGET_SECONDS = 45
# Per worker, not a distributed lock. Fail fast instead of queuing heavy requests.
QUERY_SLOTS = BoundedSemaphore(2)
TABLE_NAME = "bi_business_profit_dimension_day"
NOTES = [
    "粒度：业务日 × 业务类型 × 平台 × 站点 × 政策员 × 源业务航司 × 机票产品原值 × 实际供应商 × 最终出票GDS；部门暂不纳入。",
    "GDS：出票/退票取issue_gds_channel，改签取新issue_gds_code；增值源无GDS字段，保留未知，不按订单猜配。",
    "时间：出票时间、退票申请时间、改签出票时间、增值创建时间；结束日包含当天。",
    "金额：沿用源字段的CNY业务估算口径与正负号，不代表已结算利润；不并入风控核对区利润。",
    "数量：四类业务的business_count分别按票展示，不合计为总票数或据此计算退票率。",
    "航段：出票航段数取ADS的segment_count已知值汇总；segment_missing_count单独提示，不将缺失航段当作0。",
    "单段利润：仅出票按完整出票利润除以完整出票航段数计算；利润或航段缺失、航段为0时不计算。",
    "产品：保留平台内原值，不推定正式分类；未关联产品的业务保留在待补充产品中。",
    "航司：出票取marketing_airline，退票取marketing_airline_s，改签取新航司air_line，增值取air_line；多航司原值不拆分。",
    "返点、后返、汇率、实际结算、ADM及增值退款完整性尚未确认；无缺失利润字段不等于财务数据完整。",
    "本中间层不含订单编号、亏损原因和风险标签，不自动认定亏损原因或高风险收益可持续。",
]


def dimension_value(row: dict, key: str) -> str:
    return json.dumps([row.get(field) for field in DIMENSIONS[key]], ensure_ascii=False, separators=(",", ":"))


def dimension_label(row: dict, key: str) -> str:
    platform = row.get("ota_cname") or "未知平台"
    if key == "platform":
        return str(platform)
    if key == "site":
        return f"{row.get('ota_site_cname') or row.get('ota_site_code') or '未知站点'} · {platform}"
    if key == "airline":
        return str(row.get("airline_code") or "未知航司")
    if key == "policy":
        return str(row.get("policy_operator") or "未知政策员")
    if key == "supplier":
        return str(row.get("supplier_name") or "未知供应商")
    if key == "gds":
        return str(row.get("gds_code") or "未知最终出票GDS")
    return f"{row.get('ticket_product_raw') or '待补充产品'} · {platform}"


def aggregate(rows: list[dict], available: bool = True) -> dict:
    result = {}
    for business in BUSINESSES:
        selected = [row for row in rows if row["business_type"] == business]
        quantity = sum(int(row["business_count"]) for row in selected)
        missing = sum(int(row["profit_missing_count"]) for row in selected)
        segment_values = [int(row["segment_count"]) for row in selected if row["segment_count"] is not None]
        segment_count = sum(segment_values) if segment_values else (0 if not selected else None)
        segment_missing = sum(int(row["segment_missing_count"] or 0) for row in selected)
        amounts = [Decimal(str(row["known_profit_cny"])) for row in selected if row["known_profit_cny"] is not None]
        known = sum(amounts, Decimal(0)) if amounts or not selected else None
        profit = known if available and missing == 0 else None
        per_segment_profit = (
            profit / Decimal(segment_count)
            if business == "issue"
            and profit is not None
            and segment_count is not None
            and segment_count > 0
            and segment_missing == 0
            else None
        )
        result[business] = {
            "count": quantity if available else None,
            "segmentCount": segment_count if available else None,
            "segmentMissingCount": segment_missing if available else 0,
            "profit": str(profit) if profit is not None else None,
            "perSegmentProfit": str(per_segment_profit) if per_segment_profit is not None else None,
            "knownProfit": str(known) if available and known is not None else None,
            "profitMissingCount": missing if available else 0,
            "productMissingCount": sum(int(row["business_count"]) for row in selected if not row.get("ticket_product_raw")) if available else 0,
        }
    return result


def total_profit(metrics: dict) -> str | None:
    if any(metrics[key]["profit"] is None for key in BUSINESSES):
        return None
    return str(sum((Decimal(metrics[key]["profit"]) for key in BUSINESSES), Decimal(0)))


def metric_changes(current: dict, previous: dict, available: bool) -> dict:
    changes = {}
    for business in BUSINESSES:
        current_metric = current[business]
        previous_metric = previous[business]
        count_change = None
        profit_change = None
        if available and current_metric["count"] is not None and previous_metric["count"] is not None:
            count_change = int(current_metric["count"]) - int(previous_metric["count"])
        if available and current_metric["profit"] is not None and previous_metric["profit"] is not None:
            profit_change = str(Decimal(current_metric["profit"]) - Decimal(previous_metric["profit"]))
        changes[business] = {"count": count_change, "profit": profit_change}
    return changes


def check_snapshot(rows: Iterable[dict], days: list[str]) -> dict:
    # Keep exact keys/counters, not a second copy of all ADS rows.
    by_day = {}
    day_set = set(days)
    updated_at = ''
    for row in rows:
        if row["dt"] not in day_set or row["business_date"] != row["dt"]:
            raise RuntimeError("中间层业务日期与dt不一致，请重新同步")
        if row["metric_version"] not in ("v1", "v2", "v3") or not row["etl_run_id"] or row["business_type"] not in BUSINESSES:
            raise RuntimeError("中间层版本或业务运行标记异常，请重新清洗")
        if row["row_type"] not in ("data", "coverage"):
            raise RuntimeError("中间层行类型异常")
        day = row['dt']
        partition = by_day.setdefault(day, {'runs': set(), 'versions': set(), 'businesses': {}})
        partition['runs'].add(row['etl_run_id'])
        partition['versions'].add(row['metric_version'])
        state = partition['businesses'].setdefault(row['business_type'], {'markers': [], 'keys': set(), 'count': 0, 'missing': 0})
        updated_at = max(updated_at, str(row['etl_updated_at'] or ''))
        if row['row_type'] == 'coverage':
            state['markers'].append((row['source_row_count'], row['profit_missing_count']))
            if len(state['markers']) > 1:
                raise RuntimeError(f"{day}的{row['business_type']}完整性标记缺失或重复，请重跑该日")
            continue
        key = row['row_key']
        if not key or key in state['keys']:
            raise RuntimeError(f"{day}中间层主键重复或缺失")
        state['keys'].add(key)
        if row['business_count'] is None or row['profit_missing_count'] is None:
            raise RuntimeError(f"{day}业务计数缺失")
        count, missing = int(row['business_count']), int(row['profit_missing_count'])
        if count <= 0 or not 0 <= missing <= count:
            raise RuntimeError(f"{day}业务计数异常")
        known, estimated = row['known_profit_cny'], row['estimated_profit_cny']
        if count > missing and known is None or missing == count and known is not None:
            raise RuntimeError(f"{day}已知利润与缺失计数不一致")
        if missing == 0 and (estimated is None or Decimal(str(estimated)) != Decimal(str(known))):
            raise RuntimeError(f"{day}完整利润与已知利润不一致")
        if missing > 0 and estimated is not None:
            raise RuntimeError(f"{day}缺失利润被错误填充，请重新清洗")
        state['count'] += count
        state['missing'] += missing
    missing_days = []
    for day in days:
        partition = by_day.get(day)
        if not partition:
            missing_days.append(day)
            continue
        if len(partition['runs']) != 1:
            raise RuntimeError(f"{day}存在混合清洗批次，请重跑该日")
        if len(partition['versions']) != 1:
            raise RuntimeError(f"{day}存在混合指标版本，请重新同步")
        for business in BUSINESSES:
            state = partition['businesses'].get(business, {'markers': []})
            markers = state['markers']
            if len(markers) != 1:
                raise RuntimeError(f"{day}的{business}完整性标记缺失或重复，请重跑该日")
            marker = markers[0]
            if marker[0] is None or marker[1] is None:
                raise RuntimeError(f"{day}完整性计数缺失")
            if state['count'] != int(marker[0]):
                raise RuntimeError(f"{day}的{business}数量不一致，请重新清洗")
            if state['missing'] != int(marker[1]):
                raise RuntimeError(f"{day}的{business}缺失利润计数不一致")
    return {
        "missingDays": missing_days,
        "availableDays": [day for day in days if day not in missing_days],
        "updatedAt": updated_at,
    }


class MetricAccumulator:
    """At most eight compact rows; reuse the original Decimal/NULL formulas."""
    def __init__(self):
        self.rows = {}

    def add(self, row):
        key = (row['business_type'], bool(row.get('ticket_product_raw')))
        if key not in self.rows:
            self.rows[key] = {field: row[field] for field in (
                'business_type', 'business_count', 'profit_missing_count', 'segment_count',
                'segment_missing_count', 'known_profit_cny', 'ticket_product_raw')}
            for field in ('business_count', 'profit_missing_count', 'segment_count', 'segment_missing_count'):
                if self.rows[key][field] is not None:
                    self.rows[key][field] = int(self.rows[key][field])
            if self.rows[key]['known_profit_cny'] is not None:
                self.rows[key]['known_profit_cny'] = Decimal(str(self.rows[key]['known_profit_cny']))
            return
        target = self.rows[key]
        for field in ('business_count', 'profit_missing_count', 'segment_missing_count'):
            target[field] = int(target[field] or 0) + int(row[field] or 0)
        for field in ('segment_count', 'known_profit_cny'):
            value = row[field]
            if value is not None:
                value = Decimal(str(value)) if field == 'known_profit_cny' else int(value)
                target[field] = (target[field] or 0) + value

    def metrics(self):
        return aggregate(list(self.rows.values()))


class ComprehensiveAnalysisService:
    def __init__(self, config: dict[str, Any]):
        # This dataset is MySQL-only; switching it must not mutate other modules' global mode.
        self.source = DataSource({**config, "DATA_MODE": "mysql"})
        self.max_rows = max(1, min(MAX_ROWS, int(config.get('COMPREHENSIVE_MAX_ROWS', MAX_ROWS))))

    def analysis(self, start_value=None, end_value=None, group="platform", filters=None, sort="segments"):
        first, last = parse_analysis_period(start_value, end_value)
        if group not in DIMENSIONS:
            raise ValueError("不支持的分组维度")
        if sort not in SORT_FIELDS:
            raise ValueError("不支持的排序方式")
        filters = filters or {}
        for key in DIMENSIONS:
            token = filters.get(key)
            if not token:
                continue
            try:
                values = json.loads(token)
                if not isinstance(values, list) or len(values) != len(DIMENSIONS[key]):
                    raise ValueError
                if any(value is not None and (not isinstance(value, str) or len(value) > 1000) for value in values):
                    raise ValueError
                filters[key] = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
            except (ValueError, TypeError):
                raise ValueError(f"{key}筛选值不合法") from None
        days = [(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)]
        response = {
            "source": f"MySQL · {self.source.database}.{TABLE_NAME}",
            "available": False, "error": "", "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
            "coverage": {"missingDays": [], "availableDays": [], "updatedAt": ""},
            "extendedFiltersReady": False,
            "metrics": aggregate([], False), "totalProfit": None, "trend": [], "comparison": [],
            "options": {key: [] for key in DIMENSIONS},
            "notes": [*NOTES, f'本次最多读取{self.max_rows:,}条ADS汇总行（含完整性标记），不是订单条数；超限不展示截取总额。'],
        }
        if not QUERY_SLOTS.acquire(blocking=False):
            response['error'] = '综合分析查询繁忙，请等待当前查询结束后重试；未返回部分统计。'
            return response
        connection = cursor = None
        started, row_count = perf_counter(), 0
        extended_ready = True
        try:
            from pymysql.cursors import SSCursor
            connection = self.source.connect()
            cursor = connection.cursor(SSCursor)
            # A single date-bounded ADS query keeps data + coverage in one snapshot.
            # The explicit guard rejects oversized responses rather than publishing Top N totals.
            cursor.execute(
                f"SELECT {', '.join(COLUMNS)} FROM {self.source.database}.{TABLE_NAME} "
                f"WHERE dt >= %s AND dt <= %s LIMIT {self.max_rows + 1}",
                (first.isoformat(), last.isoformat()),
            )
            overall = MetricAccumulator()
            trend = defaultdict(MetricAccumulator)
            comparison = {}
            options = {key: {} for key in DIMENSIONS}

            def rows():
                nonlocal row_count, extended_ready
                while True:
                    batch = cursor.fetchmany(FETCH_BATCH_SIZE)
                    if perf_counter() - started > QUERY_BUDGET_SECONDS:
                        raise RuntimeError('综合分析处理超过45秒预算，请缩小范围后重试；未返回部分统计。')
                    if not batch:
                        break
                    for raw in batch:
                        row_count += 1
                        if row_count > self.max_rows:
                            raise RuntimeError(f'所选范围超过{self.max_rows:,}条ADS汇总行，请缩小时间范围；未截取部分数据冒充总额。')
                        row = dict(zip(COLUMNS, raw))
                        if row.get('metric_version') != 'v3':
                            extended_ready = False
                        # Validator consumes the row before it is accumulated below.
                        yield row
                        if row['row_type'] != 'data':
                            continue
                        tokens = {}
                        for key, fields in DIMENSIONS.items():
                            values = tuple(row.get(field) for field in fields)
                            if values not in options[key]:
                                options[key][values] = {'value': dimension_value(row, key), 'label': dimension_label(row, key)}
                            tokens[key] = options[key][values]['value']
                        if any(filters.get(key) and tokens[key] != filters[key] for key in DIMENSIONS):
                            continue
                        overall.add(row)
                        trend[row['dt']].add(row)
                        token = tokens[group]
                        if token not in comparison:
                            comparison[token] = (dimension_label(row, group), MetricAccumulator())
                        comparison[token][1].add(row)
                    if len(batch) < FETCH_BATCH_SIZE:
                        break

            coverage = check_snapshot(rows(), days)
            response['coverage'] = coverage
            response['extendedFiltersReady'] = extended_ready
            missing = response["coverage"]["missingDays"]
            if missing:
                response["error"] = f"所选期间有{len(missing)}天尚未生成中间层（如{missing[0]}）。请先回补这些日期，或缩小统计范围；未生成不等于零业务。"
                return response
            if not extended_ready and (group in ('supplier', 'gds') or filters.get('supplier') or filters.get('gds')):
                raise RuntimeError('供应商/GDS筛选需要完整V3数据，请先升级字段并重跑同步所选日期；未返回部分统计。')
            for key in DIMENSIONS:
                if not extended_ready and key in ('supplier', 'gds'):
                    continue
                response['options'][key] = sorted(options[key].values(), key=lambda item: (item['label'], item['value']))
            response["metrics"] = overall.metrics()
            response["totalProfit"] = total_profit(response["metrics"])
            # Emit zero for genuinely covered days without selected business; missing days never reach here.
            for day in days:
                metrics = trend[day].metrics()
                response['trend'].append({'period': day, 'metrics': metrics, 'totalProfit': total_profit(metrics)})
            for token, (label, accumulator) in comparison.items():
                metrics = accumulator.metrics()
                response["comparison"].append({"key": token, "value": token, "name": label, "metrics": metrics, "totalProfit": total_profit(metrics)})
            def comparison_sort_key(row):
                issue = row["metrics"]["issue"]
                segments = issue["segmentCount"]
                profit = issue["profit"]
                if sort == "profit":
                    return (
                        profit is None,
                        -(Decimal(profit) if profit is not None else Decimal(0)),
                        segments is None,
                        -(segments or 0),
                        row["name"],
                    )
                return (
                    segments is None,
                    -(segments or 0),
                    profit is None,
                    -(Decimal(profit) if profit is not None else Decimal(0)),
                    row["name"],
                )

            response["comparison"].sort(key=comparison_sort_key)
            if perf_counter() - started > QUERY_BUDGET_SECONDS:
                raise RuntimeError('综合分析处理超过45秒预算，请缩小范围后重试；未返回部分统计。')
            response["available"] = True
            return response
        except Exception as error:
            logging.getLogger(__name__).exception("MySQL ADS comprehensive analysis failed")
            # Do not expose connection details, SQL diagnostics, or credentials to the browser.
            response.update(available=False, metrics=aggregate([], False), totalProfit=None, trend=[], comparison=[],
                            options={key: [] for key in DIMENSIONS}, extendedFiltersReady=False)
            response["error"] = str(error) if isinstance(error, RuntimeError) else (
                '综合分析查询超时或连接中断，请缩小范围后重试；未返回部分统计。'
                if getattr(error, 'args', ()) and error.args[0] in (2006, 2013, 3024)
                else "综合分析MySQL ADS查询失败，请检查MySQL连接、表结构与同步批次。")
            return response
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            except Exception:
                logging.getLogger(__name__).warning('ADS cursor cleanup failed')
            finally:
                try:
                    if connection is not None:
                        connection.close()
                except Exception:
                    logging.getLogger(__name__).warning('ADS connection cleanup failed')
                finally:
                    QUERY_SLOTS.release()
                    logging.getLogger(__name__).info('ADS comprehensive query rows=%s limit=%s elapsed=%.3fs available=%s',
                        row_count, self.max_rows, perf_counter() - started, response['available'])

    def diagnosis(self, start_value=None, end_value=None, group="platform", filters=None):
        first, last = parse_analysis_period(start_value, end_value)
        filters = dict(filters or {})
        current = self.analysis(first.isoformat(), last.isoformat(), group, dict(filters))
        day_count = (last - first).days + 1
        previous_end = first - timedelta(days=1)
        previous_start = previous_end - timedelta(days=day_count - 1)
        previous_period = {"startDate": previous_start.isoformat(), "endDate": previous_end.isoformat()}
        unavailable_metrics = aggregate([], False)
        previous = {
            "available": False,
            "error": "本期数据尚未就绪，未查询上期对比。" if not current["available"] else "",
            "period": previous_period,
            "coverage": {"missingDays": [], "availableDays": [], "updatedAt": ""},
            "metrics": unavailable_metrics,
            "totalProfit": None,
        }
        if current["available"]:
            previous_result = self.analysis(
                previous_start.isoformat(), previous_end.isoformat(), group, dict(filters)
            )
            previous = {
                key: previous_result[key]
                for key in ("available", "error", "period", "coverage", "metrics", "totalProfit")
            }
        comparable = current["available"] and previous["available"]
        total_change = None
        if comparable and current["totalProfit"] is not None and previous["totalProfit"] is not None:
            total_change = str(Decimal(current["totalProfit"]) - Decimal(previous["totalProfit"]))
        return {
            "source": current["source"],
            "available": current["available"],
            "error": current["error"],
            "current": current,
            "previous": previous,
            "changes": {
                "totalProfit": total_change,
                "metrics": metric_changes(current["metrics"], previous["metrics"], comparable),
            },
            "notes": [
                "上期采用紧邻本期之前的等长自然日范围；上期覆盖不完整时不计算变化金额。",
                "变化只说明业务结果差异，不自动认定原因、责任或财务结算结果。",
            ],
        }
