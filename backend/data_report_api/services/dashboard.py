from __future__ import annotations

from copy import deepcopy
from datetime import datetime


MOCK_OVERVIEW = {
    "mode": "mock",
    "status": {
        "label": "演示数据",
        "freshness": "模拟更新时间",
        "metricState": "口径待确认",
    },
    "kpis": [
        {"key": "orders", "label": "订单量", "value": "12,860", "unit": "单", "change": 8.2, "tone": "neutral"},
        {"key": "tickets", "label": "出票量", "value": "18,420", "unit": "张", "change": 5.6, "tone": "neutral"},
        {"key": "profit", "label": "业务估算利润", "value": "待接入", "unit": "", "change": None, "tone": "pending"},
        {"key": "adm", "label": "ADM待处理", "value": "1,286", "unit": "单", "change": -3.1, "tone": "risk"},
    ],
    "trend": {
        "dates": ["09-05", "09-06", "09-07", "09-08", "09-09", "09-10", "09-11"],
        "orders": [1560, 1720, 1650, 1910, 1830, 2140, 2050],
        "tickets": [2200, 2460, 2380, 2710, 2620, 3050, 3000],
    },
    "lifecycle": [
        {"stage": "售前政策", "value": 84, "state": "建设中"},
        {"stage": "出票履约", "value": 96, "state": "演示"},
        {"stage": "售后退改", "value": 68, "state": "部分接入"},
        {"stage": "结算资金", "value": 32, "state": "待接入"},
        {"stage": "ADM风险", "value": 78, "state": "演示"},
    ],
    "focus": [
        {"title": "业务估算利润与财务利润尚未完成映射", "type": "数据", "level": "P0", "action": "确认利润桥"},
        {"title": "ADM转单后未接单存在积压", "type": "风险", "level": "P1", "action": "进入异常工作台"},
        {"title": "供应报价快照缺失，暂无法还原历史比价", "type": "履约", "level": "P1", "action": "查看数据覆盖"},
    ],
}


MOCK_ISSUES = [
    {"id": "ISSUE-001", "category": "风险异常", "object": "ADM20260911018", "title": "转单后未接单", "impact": "待核算", "owner": "ADM负责人", "status": "待处理", "level": "P0"},
    {"id": "ISSUE-002", "category": "数据异常", "object": "后返数据", "title": "ERP后返字段存在缺失", "impact": "利润可能低估", "owner": "政策/财务", "status": "待确认", "level": "P0"},
    {"id": "ISSUE-003", "category": "履约异常", "object": "供应报价", "title": "缺少出票时点候选供应快照", "impact": "无法评价比价机会", "owner": "票务/技术", "status": "来源缺失", "level": "P1"},
    {"id": "ISSUE-004", "category": "口径异常", "object": "留钱", "title": "收入与投放让利含义混用", "impact": "利润方向可能算反", "owner": "政策/财务", "status": "待确认", "level": "P0"},
]


MOCK_COVERAGE = [
    {"domain": "售前政策", "state": "building", "label": "建设中", "coverage": 45, "canAnswer": "政策投放范围与基础配置"},
    {"domain": "订单收单", "state": "ready", "label": "可接入", "coverage": 90, "canAnswer": "平台订单规模与结构"},
    {"domain": "出票履约", "state": "partial", "label": "部分具备", "coverage": 72, "canAnswer": "出票量、时效与最终供应"},
    {"domain": "供应报价", "state": "missing", "label": "来源缺失", "coverage": 18, "canAnswer": "仅有最终供应，缺少历史候选报价"},
    {"domain": "售后退改", "state": "partial", "label": "部分具备", "coverage": 58, "canAnswer": "退改申请与部分处理结果"},
    {"domain": "结算利润", "state": "pending", "label": "口径待确认", "coverage": 30, "canAnswer": "ERP估算，尚未对齐财务结果"},
    {"domain": "ADM风险", "state": "ready", "label": "可接入", "coverage": 86, "canAnswer": "ADM状态、负责人、转单和差异进度"},
    {"domain": "增值服务", "state": "pending", "label": "待盘点", "coverage": 12, "canAnswer": "尚未确认统一数据来源"},
]


class DashboardService:
    def overview(self) -> dict:
        result = deepcopy(MOCK_OVERVIEW)
        result["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        return result

    def issues(self) -> dict:
        return {"mode": "mock", "items": deepcopy(MOCK_ISSUES), "total": len(MOCK_ISSUES)}

    def asset_coverage(self) -> dict:
        return {"mode": "mock", "items": deepcopy(MOCK_COVERAGE), "total": len(MOCK_COVERAGE)}

