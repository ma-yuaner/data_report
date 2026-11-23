import re
from contextlib import suppress
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


POLICY_COLUMNS = (
    ("task_no", "任务编号"), ("opportunity_name", "机会名称"),
    ("status", "状态"), ("priority", "优先级"), ("expected_complete_at", "截止时间"),
    ("opportunity_source", "机会来源"), ("analysis_rule_code", "分析规则编号"),
    ("analysis_start_date", "分析开始日期"), ("analysis_end_date", "分析结束日期"),
    ("historical_ticket_count", "历史票数"), ("historical_profit_cny", "历史利润（CNY）"),
    ("estimated_month_ticket_count", "预估月票数"), ("estimated_month_profit_cny", "预估月利润（CNY）"),
    ("created_by_name", "创建人"), ("analysis_conclusion", "分析结论"), ("risk_note", "风险提示"),
    ("placement_method", "建议投放方式"),
    ("loss_threshold_min", "亏损阈值下限（CNY）"), ("loss_threshold_max", "亏损阈值上限（CNY）"),
    ("suggested_effective_start", "建议生效时间"), ("suggested_effective_end", "建议失效时间"),
    ("long_term_flag", "是否长期有效"),
    ("order_start_date", "销售开始日期"), ("order_end_date", "销售结束日期"),
    ("advance_sale_days", "提前销售天数"),
    ("travel_start_date", "去程旅行开始日期"), ("travel_end_date", "去程旅行结束日期"),
    ("current_assignee_name", "当前负责人"),
    ("platform_name", "平台名称"), ("platform_code", "平台编码"),
    ("product_type", "产品类型"), ("order_source", "订单来源"),
    ("site_name", "站点名称"), ("site_code", "站点编码"), ("airline_code", "航司"),
    ("departure_type", "出发地类型"), ("departure_code", "出发地编码"),
    ("arrival_type", "目的地类型"), ("arrival_code", "目的地编码"), ("route_text", "航线"),
    ("journey_type", "航程类型"), ("segment_type", "航段类型"), ("flight_nos", "航班号"),
    ("include_cabins", "包含舱位"), ("exclude_cabins", "排除舱位"),
)

LOCATION_LABELS = {"AIRPORT": "机场", "CITY": "城市", "COUNTRY": "国家", "LEGACY": "历史地点"}
LABELS = {
    "status": {
        "DRAFT": "草稿", "PENDING_DATA_REVIEW": "待数据审核", "PENDING_POLICY_REVIEW": "待政策审核",
        "CLAIMABLE": "待认领", "IN_PROGRESS": "执行中", "MONITORING": "监控中",
        "FAILED": "投放失败", "REJECTED": "已驳回", "CLOSED": "已关闭", "ENDED": "已结束",
    },
    "priority": {"HIGH": "高", "MEDIUM": "中", "LOW": "低"},
    "opportunity_source": {"AUTO_ANALYSIS": "数据分析规则识别", "MANUAL": "人工发现", "MEETING": "会议要求"},
    "journey_type": {"ONE_WAY": "单程", "ROUND_TRIP": "往返", "MULTI_CITY": "多程"},
    "departure_type": LOCATION_LABELS,
    "arrival_type": LOCATION_LABELS,
}
EMPTY_LABELS = {
    "risk_note": "无", "current_assignee_name": "尚未认领", "product_type": "不限",
    "site_name": "全部站点", "journey_type": "不限",
    "segment_type": "不限", "flight_nos": "不限", "include_cabins": "不限", "exclude_cabins": "无",
}


def _location(row, direction):
    code = row.get(f"{direction}_code")
    if not code:
        return "不限"
    location_type = row.get(f"{direction}_type") or "LEGACY"
    return f"{LOCATION_LABELS.get(location_type, '地点')}：{code}"


def _value(row, key):
    value = row.get(key)
    long_term = row.get("long_term_flag") in (1, "1")
    if key == "long_term_flag":
        return "是" if long_term else "否"
    if key == "suggested_effective_end" and long_term:
        return None
    if key == "route_text":
        if not row.get("departure_code") and not row.get("arrival_code"):
            return "不限航程"
        return f"{_location(row, 'departure')} → {_location(row, 'arrival')}"
    if key == "order_source":
        sources = {item.strip() for item in re.split(r"[,，;；]+", value or "")}
        return "、".join(source for source in ("平台手工订单", "直连订单") if source in sources) or "全部订单来源"
    if value is None or value == "":
        return EMPTY_LABELS.get(key)
    return LABELS.get(key, {}).get(value, value)


def write_policy_workbook(rows, output_path, check_cancel, progress, limit):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("投放政策")
    sheet.freeze_panes = "C2"
    headers = []
    for index, (_, label) in enumerate(POLICY_COLUMNS, 1):
        sheet.column_dimensions[get_column_letter(index)].width = 32 if label in {"机会名称", "分析结论", "风险提示", "建议投放方式"} else 23
        cell = WriteOnlyCell(sheet, value=label)
        cell.font = Font(bold=True)
        headers.append(cell)
    sheet.append(headers)
    processed = 0
    try:
        for row in rows:
            if processed % 500 == 0:
                check_cancel()
                progress(processed)
            if processed == limit:
                raise ValueError(f"投放任务超过 {limit:,} 条，请缩小筛选范围")
            cells = []
            for key, _ in POLICY_COLUMNS:
                value = _value(row, key)
                cell = WriteOnlyCell(sheet, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"
                elif isinstance(value, datetime):
                    cell.number_format = "yyyy-mm-dd hh:mm:ss"
                elif isinstance(value, date):
                    cell.number_format = "yyyy-mm-dd"
                cells.append(cell)
            sheet.append(cells)
            processed += 1
        check_cancel()
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(POLICY_COLUMNS))}{processed + 1}"
        workbook.save(output_path)
        return processed
    except Exception:
        if not sheet.closed:
            sheet.close()
        # Openpyxl removes the temporary worksheet XML only after writing it to a workbook.
        with suppress(FileNotFoundError):
            sheet._writer.cleanup()
        raise
