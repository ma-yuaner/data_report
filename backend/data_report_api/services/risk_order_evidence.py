"""Read-only ERP evidence for the first risk-verification rule; no AI calls."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from .data_source import DataSource

LOGGER = logging.getLogger(__name__)
LIMIT = 200
RULE_VERSION = "profit-reason-present-v1"
# Fixed projections only: no document numbers, phone numbers, payment cards or SQL from clients.
BLOCKS = {
    "segments": ("航段", "order_info_segment", "id,order_id,journey_sequence,segment_sequence,flight_number,dep_airport,arr_airport,cabin,real_cabin,dep_time,arr_time"),
    "passengers": ("乘客", "order_info_passenger", "id,order_id,passenger_name,age_type"),
    "issues": ("出票", "order_info_issue", "id,order_id,passenger_id,issue_ticket_no,policy_currency,policy_ticket_price,policy_tax,policy_exchange_rate,sale_currency,sale_exchange_rate,sale_commission_amount,sale_total_amount,sale_total_amount_cny,issue_currency,issue_exchange_rate,issue_total_amount,issue_total_amount_cny,finance_currency,finance_exchange_rate,finance_total_amount,finance_total_amount_cny,issue_cost_amount_cny,issue_profit,issue_ticket_time"),
    "changes": ("改签关联单", "order_change", "id,order_id,order_no,create_time"),
    "refunds": ("退票关联单", "order_refund", "id,order_id,order_no,create_time"),
    "flightChanges": ("航变关联单", "order_info_flight_change", "id,order_id,order_no,create_time"),
    "ancillaries": ("增值服务关联单", "order_auxiliary", "id,order_id,order_no,create_time"),
    "operatorLogs": ("操作及手工日志", "order_info_operator_log", "id,order_id,business_obj,business_obj_id,operator_type,operator_datetime,operator_name,operator_content,manual_flag"),
    "statusHistory": ("状态历史", "order_info_status_history", "id,order_id,order_status,old_order_status,issue_status,old_issue_status,operator,remark,create_time"),
}
DEFERRED = {
    "autoIssueInfo": "自动出票单票利润的准确来源与单票关联待核实，不以出票利润或智能定位利润替代",
    "issueSegments": "出票与航段关联明细待接入",
    "autoIssueLogs": "自动出票日志按业务对象关联待接入",
    "quotes": "原始精度报价及乘客报价明细待接入",
    "instructions": "当前匹配业务/售后说明待接入，不能以当前规则替代历史快照",
    "differences": "差异信息与旧页面的字段映射待接入",
}
ORDER_FIELDS = "id,order_no,ota_order_no,ota_code,commission_type,commission_order_flag,order_status,issue_status,profit_reason_type,profit_remark,create_time,update_time"


class EvidenceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def order_id(value):
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,18}", text) or int(text) > 9223372036854775807:
        raise EvidenceError("请输入有效的ERP内部订单ID")
    return int(text)


def _json_value(value, key=""):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, int) and (key == "id" or key.endswith("_id")):
        return str(value)
    return value


def _rows(cursor):
    names = [item[0] for item in cursor.description]
    return [{key: _json_value(value, key) for key, value in (row.items() if isinstance(row, dict) else zip(names, row))}
            for row in cursor.fetchall()]


class RiskOrderEvidenceService:
    def __init__(self, config, source=None):
        self.config = config
        self._source = source

    def _connect(self):
        if self._source is None:
            if self.config.get("RISK_VERIFICATION_ERP_EXPLICIT") is not True or not all(self.config.get(f"ERP_MYSQL_{key}") for key in ("HOST", "DATABASE", "USER", "PASSWORD")):
                raise EvidenceError("ERP只读数据源未配置，请由管理员核对已有ERP_MYSQL配置", 503)
            values = {**self.config, "DATA_MODE": "mysql"}
            for key in ("HOST", "PORT", "DATABASE", "USER", "PASSWORD", "CHARSET", "CONNECT_TIMEOUT", "READ_TIMEOUT", "WRITE_TIMEOUT", "POOL_SIZE", "POOL_MIN_CACHED"):
                if self.config.get(f"ERP_MYSQL_{key}") not in (None, ""):
                    values[f"MYSQL_{key}"] = self.config[f"ERP_MYSQL_{key}"]
            self._source = DataSource(values)
        return self._source.connect()

    @staticmethod
    def _close(cursor, connection):
        for resource in (cursor, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    LOGGER.exception("Risk evidence resource cleanup failed")

    def candidates(self, start, end, before=None):
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except (ValueError, TypeError):
            raise EvidenceError("请提供YYYY-MM-DD格式的起止日期") from None
        if first > last or (last - first).days > 30:
            raise EvidenceError("待核查查询范围须为1至31天，按订单创建时间筛选")
        boundary = order_id(before) if before is not None else None
        connection = cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            # This first rule intentionally includes every nonblank code, including R001.
            sql = f"SELECT {ORDER_FIELDS} FROM order_info WHERE create_time >= %s AND create_time < %s AND profit_reason_type IS NOT NULL AND TRIM(profit_reason_type) <> ''"
            parameters = [first.isoformat(), (last + timedelta(days=1)).isoformat()]
            if boundary is not None:
                sql += " AND id < %s"
                parameters.append(boundary)
            cursor.execute(sql + " ORDER BY id DESC LIMIT %s", (*parameters, LIMIT + 1))
            rows = _rows(cursor)
            return {"ruleVersion": RULE_VERSION, "dateBasis": "order_info.create_time", "items": rows[:LIMIT],
                    "hasMore": len(rows) > LIMIT, "nextBefore": rows[LIMIT - 1]["id"] if len(rows) > LIMIT else None,
                    "aiInvoked": False, "notice": "命中仅表示待核查，不代表订单有错；查询步骤不调用AI"}
        except EvidenceError:
            raise
        except Exception:
            LOGGER.exception("Risk candidate query failed")
            raise EvidenceError("待核查订单读取失败，请检查ERP读取权限与字段", 503) from None
        finally:
            self._close(cursor, connection)

    def evidence(self, value, requested=None, identifier_type="auto"):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise EvidenceError("请输入有效的ERP内部订单ID或订单号")
        if not isinstance(identifier_type, str) or identifier_type not in {"auto", "id", "orderNo"}:
            raise EvidenceError("不支持的订单标识类型")
        identifier = order_id(value) if identifier_type == "id" or identifier_type == "auto" and str(value).isdigit() else None
        if identifier is None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", str(value)):
            raise EvidenceError("请输入有效的ERP内部订单ID或订单号")
        selected = list(dict.fromkeys(requested if requested is not None else ("segments", "passengers", "issues")))
        if any(key not in BLOCKS for key in selected):
            raise EvidenceError("不支持的证据类型")
        connection = cursor = None
        try:
            connection = self._connect()
            cursor = connection.cursor()
            if identifier is not None:
                cursor.execute(f"SELECT {ORDER_FIELDS} FROM order_info WHERE id=%s LIMIT 1", (identifier,))
            else:
                cursor.execute(f"SELECT {ORDER_FIELDS} FROM order_info WHERE order_no=%s OR ota_order_no=%s LIMIT 2", (str(value), str(value)))
            rows = _rows(cursor)
            if not rows:
                raise EvidenceError("ERP订单不存在", 404)
            if len(rows) > 1:
                raise EvidenceError("订单号匹配多个内部订单，请使用明确的ERP内部ID", 409)
            if identifier is None:
                identifier = order_id(rows[0]["id"])
            if str(rows[0]["id"]) != str(identifier):
                raise EvidenceError("订单证据身份不匹配", 503)
            blocks = {key: {"label": spec[0], "status": "not_requested", "records": [], "complete": False}
                      for key, spec in BLOCKS.items()}
            for key in selected:
                label, table, fields = BLOCKS[key]
                try:
                    cursor.execute(f"SELECT {fields} FROM {table} WHERE order_id=%s ORDER BY id LIMIT %s", (identifier, LIMIT + 1))
                    records = _rows(cursor)
                    if any(str(row["order_id"]) != str(identifier) for row in records):
                        raise EvidenceError("证据关联不匹配", 503)
                    blocks[key] = {"label": label, "source": table, "status": "truncated" if len(records) > LIMIT else "ready" if records else "empty",
                                   "records": records[:LIMIT], "complete": len(records) <= LIMIT}
                except Exception:
                    LOGGER.exception("Risk evidence block failed: %s", key)
                    blocks[key] = {"label": label, "status": "failed", "records": [], "complete": False,
                                   "error": "该证据读取失败，请核对ERP字段及读取权限"}
            blocks.update({key: {"label": label, "status": "not_integrated", "records": [], "complete": False}
                           for key, label in DEFERRED.items()})
            return {"erpOrderId": str(identifier), "order": rows[0], "blocks": blocks,
                    "fetchedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                    "consistency": "sequential_reads_not_atomic_snapshot", "aiInvoked": False,
                    "ruleVersion": RULE_VERSION, "candidate": rows[0].get("profit_reason_type") is not None and bool(str(rows[0]["profit_reason_type"]).strip(" ")),
                    "complete": False, "notice": "当前为分块取证预览，关联单仅索引，尚非完整审核证据包；取证步骤不调用AI"}
        except EvidenceError:
            raise
        except Exception:
            LOGGER.exception("Risk order evidence query failed")
            raise EvidenceError("订单证据读取失败，请检查ERP读取权限与字段", 503) from None
        finally:
            self._close(cursor, connection)
