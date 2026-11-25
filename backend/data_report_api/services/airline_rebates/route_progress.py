"""Read eligible tickets from an existing trial snapshot."""
from decimal import Decimal
from io import BytesIO
import json

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell


def eligible_route_rows(rows, category):
    return [row for row in rows if row.get("category") == category
            and row.get("eligibleAmount") is not None and not row.get("reviewBucket")
            and not row.get("result", "").startswith(("待核", "排除"))]


def route_days(db, run_id, category, day=None):
    statement = "SELECT day, details FROM rebate_days WHERE run_id=?"
    params = (run_id,)
    if day is not None:
        statement += " AND day=?"
        params += (day,)
    for record in db.execute(statement + " ORDER BY day DESC", params):
        rows = eligible_route_rows(json.loads(record["details"]), category)
        yield {
            "id": run_id + "_" + record["day"],
            "date": record["day"],
            "records": len(rows),
            "measuredAmount": str(sum((Decimal(row["eligibleAmount"]) for row in rows), Decimal(0))),
            "estimatedReward": str(sum((Decimal(row["estimatedReward"] or 0) for row in rows), Decimal(0))),
        }, rows


def route_workbook(days, label, currency):
    workbook = Workbook(write_only=True)
    daily = workbook.create_sheet("逐日汇总")
    detail = workbook.create_sheet("客票明细")
    daily.append(["计量归属日", "航线类型", "计量记录数", "币种", "当日计量", "预计后返（本批费率）"])
    detail.append(["计量归属日", "航线类型", "订单号", "票号", "航程", "航段计划起飞日", "实际舱位",
                   "销售航司", "航段判定", "币种", "整票票面价", "计量金额", "批次费率（%）",
                   "本票预计后返", "订单已算后返小计（全批）", "匹配结果"])

    def append_ticket(point, row):
        segments = row.get("segmentDecisions") or []
        values = [point["date"], label, row.get("orderNo"), row.get("ticketNo"), row.get("route")]
        values.extend(" / ".join(str(segment.get(key) or "—") for segment in segments)
                      for key in ("date", "cabin", "marketingAirline", "result"))
        values.append(row.get("currency") or currency)
        for key in ("ticketFare", "eligibleAmount", "ratePercent", "estimatedReward", "orderEstimatedReward"):
            value = row.get(key)
            values.append(None if value is None else Decimal(value))
        values.append(row.get("result"))
        cells = []
        for value in values:
            cell = WriteOnlyCell(detail, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
            cells.append(cell)
        detail.append(cells)

    for point, rows in days:
        daily.append([point["date"], label, point["records"], currency,
                      Decimal(point["measuredAmount"]), Decimal(point["estimatedReward"])])
        for row in rows:
            append_ticket(point, row)
    content = BytesIO()
    workbook.save(content)
    content.seek(0)
    return content
