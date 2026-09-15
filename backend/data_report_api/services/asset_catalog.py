from __future__ import annotations

import logging
import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from .data_source import DataSource, TABLE_SPECS, data_mode, is_live_mode


LOGGER = logging.getLogger(__name__)
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


ASSETS = (
    {"key": "issue", "domain": "出票", "hiveColumnCount": 204, "metrics": ["出票数", "航段数", "出票预估利润"], "condition": "已出票、出票更新完成、排除指定退票状态"},
    {"key": "refund", "domain": "退票", "hiveColumnCount": 135, "metrics": ["退票数", "退票利润"], "condition": "正常退票或售后退票作废，且供应退款操作人不为空"},
    {"key": "change", "domain": "改签", "hiveColumnCount": 89, "metrics": ["改签数", "改签利润"], "condition": "按改签出票时间统计"},
    {"key": "ancillary", "domain": "增值", "hiveColumnCount": 45, "metrics": ["增值数", "增值航段数", "增值利润"], "condition": "增值状态为已购买"},
)

REQUIRED_FIELDS = {
    "issue": {"operator_date", "iss_num", "segment_num", "issue_profit", "order_status", "issue_status", "refund_flag", "refund_issue_flag"},
    "refund": {"apply_datetime", "refund_profit", "business_type_desc", "supplier_refund_operator"},
    "change": {"change_issue_time", "change_profit"},
    "ancillary": {"create_time", "profit", "flight_num", "aux_status"},
}

METRICS = (
    {"name": "总预估利润", "formula": "出票利润 + 退票利润 + 改签利润 + 增值利润", "timeField": "各业务发生时间", "stage": "业务估算", "status": "current"},
    {"name": "出票预估利润", "formula": "sum(issue_profit)", "timeField": "issue_ticket_time", "stage": "业务估算", "status": "current"},
    {"name": "退票利润", "formula": "sum(refund_profit)", "timeField": "apply_datetime", "stage": "业务估算", "status": "current"},
    {"name": "改签利润", "formula": "sum(change_profit)", "timeField": "change_issue_time", "stage": "业务估算", "status": "current"},
    {"name": "增值利润", "formula": "sum(profit)", "timeField": "create_time", "stage": "业务估算", "status": "current"},
    {"name": "增值航段数", "formula": "sum(flight_num)", "timeField": "create_time", "stage": "业务量", "status": "current"},
)

ANALYSIS_DOMAINS = (
    {"domain": "利润与亏损", "taskCount": 19, "maturity": "已接入", "representative": "总利润、平台/航司/政策员利润、亏损订单", "plan": "M1/M2核心能力"},
    {"domain": "出票履约", "taskCount": 7, "maturity": "可接入", "representative": "出票时长、出票方式、出票员、供应商出票", "plan": "M3出票履约"},
    {"domain": "退票改签售后", "taskCount": 22, "maturity": "部分接入", "representative": "ATC退改、航变、退款状态、PCC改签", "plan": "M4售后专题"},
    {"domain": "智能出票与比价", "taskCount": 27, "maturity": "待治理", "representative": "智能参与率、成功失败、降舱、废票、比价", "plan": "统一事件口径后接入"},
    {"domain": "搜索与转化", "taskCount": 10, "maturity": "数据较成熟", "representative": "GDS/OTA搜索、验价、达成率", "plan": "M4流量转化专题"},
    {"domain": "供应商与返点", "taskCount": 8, "maturity": "待确认", "representative": "供应商出票、航司任务、返点录入缺失", "plan": "M3供应履约"},
    {"domain": "政策与任务", "taskCount": 4, "maturity": "待确认", "representative": "政策数量、任务进度、政策阈值", "plan": "政策粒度确认后接入"},
    {"domain": "财务结算与风控", "taskCount": 9, "maturity": "需治理", "representative": "AR/AP、汇率、支付、预警、ADM", "plan": "M5结算利润"},
    {"domain": "增值服务", "taskCount": 3, "maturity": "部分接入", "representative": "增值类型、航司、出票员", "plan": "M4增值专题"},
    {"domain": "部门与客户专项", "taskCount": 20, "maturity": "专项报送", "representative": "部门、客户、区域、航司专项日报周报", "plan": "沉淀公共指标，不逐报表迁移"},
    {"domain": "基础报送与工具", "taskCount": 20, "maturity": "基础能力", "representative": "日报导出、邮件、图片、PCC及数据补充", "plan": "保留为交付与运维能力"},
)


class AssetCatalogService:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def catalog(self) -> dict[str, Any]:
        mode = data_mode(self.config)
        source = DataSource(self.config) if is_live_mode(mode) else None
        cache_key = (mode, source.database if source else str(self.config.get("MYSQL_DATABASE", "sibebid")))
        ttl = max(int(self.config.get("PROFIT_CACHE_TTL", 300)) * 2, 300)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                result = deepcopy(cached[1])
                result["cacheHit"] = True
                return result
        result = self._live_catalog(source) if source else self._base_catalog("mock", None)
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
        return result

    def _base_catalog(self, mode: str, source: DataSource | None) -> dict[str, Any]:
        source_mode = source.mode if source else "mysql"
        database = source.database if source else str(self.config.get("MYSQL_DATABASE", "sibebid"))
        assets = []
        for definition in ASSETS:
            item = deepcopy(definition)
            spec = TABLE_SPECS[source_mode][definition["key"]]
            item.pop("hiveColumnCount", None)
            item.update({
                "database": database,
                "table": spec.table,
                "timeField": spec.time_field,
                "columnCount": definition["hiveColumnCount"] if source_mode == "hive" else None,
                "state": "configured" if mode == "mock" else "ready",
                "latestDataTime": None,
                "error": None,
            })
            assets.append(item)
        metrics = deepcopy(METRICS)
        for metric in metrics:
            if metric["name"] == "出票预估利润":
                metric["timeField"] = TABLE_SPECS[source_mode]["issue"].time_field
        return {"mode": mode, "source": source.label if source else "配置清单", "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "cacheHit": False, "assets": assets, "metrics": metrics, "analyses": deepcopy(ANALYSIS_DOMAINS), "analysisTaskCount": sum(item["taskCount"] for item in ANALYSIS_DOMAINS)}

    def _live_catalog(self, source: DataSource) -> dict[str, Any]:
        result = self._base_catalog("live", source)
        try:
            connection = source.connect()
        except Exception:
            LOGGER.exception("Asset catalog %s connection failed", source.engine_label)
            for item in result["assets"]:
                item.update({"state": "error", "error": f"{source.engine_label}连接失败"})
            return result
        try:
            for item in result["assets"]:
                cursor = connection.cursor()
                try:
                    missing_fields: list[str] = []
                    cursor.execute(f"SELECT max({item['timeField']}) FROM {source.database}.{item['table']}")
                    row = cursor.fetchone()
                    item["latestDataTime"] = str(row[0]) if row and row[0] else None
                    if source.mode == "mysql":
                        cursor.execute(f"SHOW COLUMNS FROM {source.database}.{item['table']}")
                        columns = {str(column[0]) for column in cursor.fetchall()}
                        item["columnCount"] = len(columns)
                        missing_fields = sorted(REQUIRED_FIELDS[item["key"]] - columns)
                    if not item["latestDataTime"]:
                        item["state"] = "empty"
                    else:
                        try:
                            latest = datetime.fromisoformat(item["latestDataTime"][:19])
                        except ValueError:
                            item.update({"state": "warning", "error": "最新业务时间格式异常"})
                        else:
                            if latest > datetime.now() + timedelta(days=1):
                                item.update({"state": "warning", "error": f"{item['timeField']}存在未来日期，请检查源数据"})
                            else:
                                item["state"] = "ready"
                    if missing_fields:
                        item.update({"state": "warning", "error": f"缺少看板必要字段：{', '.join(missing_fields)}"})
                except Exception:
                    LOGGER.exception("Asset status query failed: %s", item["key"])
                    item.update({"state": "error", "error": "更新状态查询失败"})
                finally:
                    cursor.close()
        finally:
            connection.close()
        return result
