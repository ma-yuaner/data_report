"""Read the Hive ADS snapshot, never the four raw facts or demonstration data."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .data_source import DataSource

BUSINESSES = ("issue", "refund", "change", "ancillary")
DIMENSIONS = {
    "platform": ("ota_code", "ota_cname"),
    "site": ("ota_code", "ota_site_code", "ota_site_cname"),
    "airline": ("airline_code",),
    "product": ("ota_code", "ota_cname", "ticket_product_raw"),
}
COLUMNS = (
    "row_key", "dt", "business_date", "row_type", "business_type", "ota_code", "ota_cname",
    "ota_site_code", "ota_site_cname", "airline_code", "ticket_product_raw", "business_count",
    "known_profit_cny", "estimated_profit_cny", "profit_missing_count", "source_row_count",
    "metric_version", "etl_run_id", "etl_updated_at",
)
MAX_ROWS = 100_000
NOTES = [
    "粒度：业务日 × 业务类型 × 平台 × 站点 × 源业务航司 × 机票产品原值；部门暂不纳入。",
    "时间：出票时间、退票申请时间、改签出票时间、增值创建时间；结束日包含当天。",
    "金额：沿用源字段的CNY业务估算口径与正负号，不代表已结算利润；不并入风控核对区利润。",
    "数量：四类业务为各自源记录数，分别展示，不合计为总票数或据此计算退票率。",
    "产品：保留平台内原值，不推定正式分类；未关联产品的业务保留在待补充产品中。",
    "航司：出票取marketing_airline，退票取marketing_airline_s，改签取新航司air_line，增值取air_line；多航司原值不拆分。",
    "返点、后返、汇率、实际结算、ADM及增值退款完整性尚未确认；无缺失利润字段不等于财务数据完整。",
    "本中间层不含订单编号、亏损原因和风险标签，不自动认定亏损原因或高风险收益可持续。",
]


def parse_period(start: str | None, end: str | None) -> tuple[date, date]:
    today = datetime.now(timezone(timedelta(hours=8))).date()
    try:
        first = date.fromisoformat(start or today.isoformat())
        last = date.fromisoformat(end or first.isoformat())
        if start and first.isoformat() != start or end and last.isoformat() != end:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("日期必须为YYYY-MM-DD格式") from None
    if last < first or (last - first).days > 365:
        raise ValueError("结束日期不能早于开始日期，单次范围不能超过366天")
    return first, last


def dimension_value(row: dict, key: str) -> str:
    return json.dumps([row.get(field) for field in DIMENSIONS[key]], ensure_ascii=False, separators=(",", ":"))


def dimension_label(row: dict, key: str) -> str:
    platform = row.get("ota_cname") or row.get("ota_code") or "未知平台"
    if key == "platform":
        return str(platform) + (f" · {row['ota_code']}" if row.get("ota_code") else "")
    if key == "site":
        return f"{row.get('ota_site_cname') or row.get('ota_site_code') or '未知站点'} · {platform}"
    if key == "airline":
        return str(row.get("airline_code") or "未知航司")
    return f"{row.get('ticket_product_raw') or '待补充产品'} · {platform}" + (f" ({row['ota_code']})" if row.get("ota_code") else "")


def aggregate(rows: list[dict], available: bool = True) -> dict:
    result = {}
    for business in BUSINESSES:
        selected = [row for row in rows if row["business_type"] == business]
        quantity = sum(int(row["business_count"]) for row in selected)
        missing = sum(int(row["profit_missing_count"]) for row in selected)
        amounts = [Decimal(str(row["known_profit_cny"])) for row in selected if row["known_profit_cny"] is not None]
        known = sum(amounts, Decimal(0)) if amounts or not selected else None
        result[business] = {
            "count": quantity if available else None,
            "profit": str(known) if available and missing == 0 else None,
            "knownProfit": str(known) if available and known is not None else None,
            "profitMissingCount": missing if available else 0,
            "productMissingCount": sum(int(row["business_count"]) for row in selected if not row.get("ticket_product_raw")) if available else 0,
        }
    return result


def total_profit(metrics: dict) -> str | None:
    if any(metrics[key]["profit"] is None for key in BUSINESSES):
        return None
    return str(sum((Decimal(metrics[key]["profit"]) for key in BUSINESSES), Decimal(0)))


def check_snapshot(rows: list[dict], days: list[str]) -> dict:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["dt"] not in days or row["business_date"] != row["dt"]:
            raise RuntimeError("中间层业务日期与分区不一致，请重新清洗")
        if row["metric_version"] != "v1" or not row["etl_run_id"] or row["business_type"] not in BUSINESSES:
            raise RuntimeError("中间层版本或业务运行标记异常，请重新清洗")
        if row["row_type"] not in ("data", "coverage"):
            raise RuntimeError("中间层行类型异常")
        by_day[row["dt"]].append(row)
    missing_days = []
    for day in days:
        partition = by_day[day]
        if not partition:
            missing_days.append(day)
            continue
        if len({row["etl_run_id"] for row in partition}) != 1:
            raise RuntimeError(f"{day}存在混合清洗批次，请重跑该日")
        for business in BUSINESSES:
            markers = [row for row in partition if row["row_type"] == "coverage" and row["business_type"] == business]
            if len(markers) != 1:
                raise RuntimeError(f"{day}的{business}完整性标记缺失或重复，请重跑该日")
            data = [row for row in partition if row["row_type"] == "data" and row["business_type"] == business]
            marker = markers[0]
            if marker["source_row_count"] is None or marker["profit_missing_count"] is None:
                raise RuntimeError(f"{day}完整性计数缺失")
            keys = [row["row_key"] for row in data]
            if len(set(keys)) != len(keys) or any(not key for key in keys):
                raise RuntimeError(f"{day}中间层主键重复或缺失")
            for row in data:
                if row["business_count"] is None or row["profit_missing_count"] is None:
                    raise RuntimeError(f"{day}业务计数缺失")
                count, missing = int(row["business_count"]), int(row["profit_missing_count"])
                if count <= 0 or not 0 <= missing <= count:
                    raise RuntimeError(f"{day}业务计数异常")
                known, estimated = row["known_profit_cny"], row["estimated_profit_cny"]
                if count > missing and known is None or missing == count and known is not None:
                    raise RuntimeError(f"{day}已知利润与缺失计数不一致")
                if missing == 0 and (estimated is None or Decimal(str(estimated)) != Decimal(str(known))):
                    raise RuntimeError(f"{day}完整利润与已知利润不一致")
                if missing > 0 and estimated is not None:
                    raise RuntimeError(f"{day}缺失利润被错误填充，请重新清洗")
            if sum(int(row["business_count"]) for row in data) != int(marker["source_row_count"]):
                raise RuntimeError(f"{day}的{business}数量不一致，请重新清洗")
            if sum(int(row["profit_missing_count"]) for row in data) != int(marker["profit_missing_count"]):
                raise RuntimeError(f"{day}的{business}缺失利润计数不一致")
    return {
        "missingDays": missing_days,
        "availableDays": [day for day in days if day not in missing_days],
        "updatedAt": max((str(row["etl_updated_at"] or "") for row in rows), default=""),
    }


class ComprehensiveAnalysisService:
    def __init__(self, config: dict[str, Any]):
        # This dataset is Hive-only for now, without switching the other modules.
        self.source = DataSource({**config, "DATA_MODE": "hive"})

    def analysis(self, start_value=None, end_value=None, group="platform", filters=None):
        first, last = parse_period(start_value, end_value)
        if group not in DIMENSIONS:
            raise ValueError("不支持的分组维度")
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
            "source": f"Hive · {self.source.database}.ads_business_profit_dimension_day",
            "available": False, "error": "", "period": {"startDate": first.isoformat(), "endDate": last.isoformat()},
            "coverage": {"missingDays": [], "availableDays": [], "updatedAt": ""},
            "metrics": aggregate([], False), "totalProfit": None, "trend": [], "comparison": [],
            "options": {key: [] for key in DIMENSIONS}, "notes": NOTES,
        }
        connection = cursor = None
        try:
            connection = self.source.connect()
            cursor = connection.cursor()
            # A single partition-pruned ADS query keeps data + coverage in one snapshot.
            # The explicit guard rejects oversized responses rather than publishing Top N totals.
            cursor.execute(
                f"SELECT {', '.join(COLUMNS)} FROM {self.source.database}.ads_business_profit_dimension_day "
                f"WHERE dt >= %s AND dt <= %s LIMIT {MAX_ROWS + 1}",
                (first.isoformat(), last.isoformat()),
            )
            raw = cursor.fetchmany(MAX_ROWS + 1)
            if len(raw) > MAX_ROWS:
                response["error"] = "所选范围超过10万条ADS汇总行，请缩小时间范围；未截取部分数据冒充总额。"
                return response
            rows = [dict(zip(COLUMNS, row)) for row in raw]
            response["coverage"] = check_snapshot(rows, days)
            missing = response["coverage"]["missingDays"]
            if missing:
                response["error"] = f"所选期间有{len(missing)}天尚未生成中间层（如{missing[0]}）。请先回补这些日期，或缩小统计范围；未生成不等于零业务。"
                return response
            data = [row for row in rows if row["row_type"] == "data"]
            for key in DIMENSIONS:
                options = {dimension_value(row, key): dimension_label(row, key) for row in data}
                response["options"][key] = [{"value": token, "label": label} for token, label in sorted(options.items(), key=lambda item: (item[1], item[0]))]
            selected = [row for row in data if all(not filters.get(key) or dimension_value(row, key) == filters[key] for key in DIMENSIONS)]
            response["metrics"] = aggregate(selected)
            response["totalProfit"] = total_profit(response["metrics"])
            # Emit zero for genuinely covered days without selected business; missing days never reach here.
            trend_rows = defaultdict(list)
            for row in selected:
                trend_rows[row["dt"]].append(row)
            response["trend"] = [{"period": day, "metrics": aggregate(trend_rows[day]), "totalProfit": total_profit(aggregate(trend_rows[day]))} for day in days]
            comparison = defaultdict(list)
            for row in selected:
                comparison[dimension_value(row, group)].append(row)
            for token, grouped in comparison.items():
                metrics = aggregate(grouped)
                response["comparison"].append({"key": token, "value": token, "name": dimension_label(grouped[0], group), "metrics": metrics, "totalProfit": total_profit(metrics)})
            response["comparison"].sort(key=lambda row: (row["totalProfit"] is None, -(Decimal(row["totalProfit"]) if row["totalProfit"] is not None else Decimal(0)), row["name"]))
            response["available"] = True
            return response
        except Exception as error:
            logging.getLogger(__name__).exception("Hive ADS comprehensive analysis failed")
            # Do not expose connection details, SQL diagnostics, or credentials to the browser.
            response["error"] = str(error) if isinstance(error, RuntimeError) else "综合分析Hive ADS查询失败，请检查Hive连接、表结构与清洗批次。"
            return response
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
