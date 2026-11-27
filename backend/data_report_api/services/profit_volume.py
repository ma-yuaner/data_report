"""Shared aggregation and detail over a versioned, authorized issuance source."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Iterable, Mapping

from .comprehensive_analysis import DIMENSIONS
from .comprehensive_detail import parse_detail_filters

GROUPS = {"gain": "盈利", "loss": "冲量", "total": "整体"}
MAX_RECORDS = 100_000
COLUMNS = [
    {"key": "issueDate", "title": "出票日期", "valueType": "date", "width": 118},
    {"key": "ticketNumber", "title": "客票号", "valueType": "text", "width": 155},
    {"key": "orderReference", "title": "订单号", "valueType": "text", "width": 200},
    {"key": "segmentCount", "title": "航段数", "valueType": "count", "width": 106},
    {"key": "presaleProfit", "title": "售前利润（元）", "valueType": "text", "width": 155},
]


@dataclass(frozen=True)
class Issuance:
    day: date
    key: str
    order_reference: str
    segments: int | None
    profit: Decimal | None
    dimensions: Mapping[str, str | None] = field(default_factory=dict)
    ticket_number: str | None = None
    ticket_raw: str | None = None

    @property
    def group(self):
        if self.profit is None or self.profit == 0:
            return None
        return "gain" if self.profit > 0 else "loss"


@dataclass(frozen=True)
class IssuanceSnapshot:
    version: str
    covered_days: frozenset[date]
    records: Iterable[Issuance]
    ads_daily: Mapping[date, tuple] | None = None


class SnapshotUnavailable(Exception):
    """The requested immutable dataset or dimension mapping is unavailable."""


@dataclass
class Totals:
    segments: int = 0
    profit: Decimal = Decimal(0)
    ads_projected_profit: Decimal = Decimal(0)
    segment_missing: int = 0
    profit_missing: int = 0
    records: int = 0
    tickets: set[str] = field(default_factory=set)
    unrecognized_tickets: int = 0

    def add(self, row):
        self.records += 1
        if row.ticket_number:
            self.tickets.add(row.ticket_number)
        else:
            self.unrecognized_tickets += 1
        if row.segments is None:
            self.segment_missing += 1
        else:
            self.segments += row.segments
        if row.profit is None:
            self.profit_missing += 1
        else:
            self.profit += row.profit
            self.ads_projected_profit += row.profit.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def payload(self):
        return {
            "segmentCount": None if self.segment_missing else self.segments,
            "profit": None if self.profit_missing else format(self.profit, "f"),
            "adsProjectedKnownProfit": format(self.ads_projected_profit, "f"),
            "knownProfitProjectionDifference": format(self.profit - self.ads_projected_profit, "f"),
            "perSegmentProfit": format(self.profit / self.segments, "f")
            if self.segments and not self.profit_missing and not self.segment_missing else None,
            "recordCount": self.records,
            "ticketCount": len(self.tickets),
            "unrecognizedTicketRecords": self.unrecognized_tickets,
            "segmentMissingCount": self.segment_missing,
            "profitMissingCount": self.profit_missing,
        }


class ProfitVolumeService:
    def __init__(self, source):
        self.source = source

    def query(self, args: Mapping[str, str], principal, *, detail=False):
        try:
            start = date.fromisoformat(args.get("startDate", ""))
            end = date.fromisoformat(args.get("endDate", ""))
        except ValueError as error:
            raise ValueError("请选择有效的出票日期。") from error
        if not 0 <= (end - start).days <= 365:
            raise ValueError("出票日期区间须在 366 天以内。")
        dimensions = parse_detail_filters({key: args.get(key) for key in DIMENSIONS})
        target = None
        group = version = None
        group_by = args.get("dimension")
        if group_by and (detail or group_by not in DIMENSIONS):
            raise ValueError("出票分析维度无效。")
        page, page_size = 1, 50
        if detail or group_by:
            try:
                target = date.fromisoformat(args.get("issueDate", ""))
                page = int(args.get("page", "1"))
                page_size = int(args.get("pageSize", "50"))
            except ValueError as error:
                raise ValueError("出票日期或分页参数无效。") from error
            group, version = args.get("group"), args.get("snapshotVersion")
            if not (start <= target <= end and group in GROUPS and version and 1 <= page and 1 <= page_size <= 100):
                raise ValueError("明细日期、分组、版本或分页参数无效。")
        if self.source is None:
            return {"available": False, "error": "售前利润数据源尚未接入，当前无法查询盈/冲。"}
        try:
            # The adapter must authorize principal and apply all dimensions before
            # yielding uniquely keyed rows sorted by (day, key). Detail pins version.
            snapshot = self.source(start, end, dimensions, principal, version, target)
            if not snapshot.version or (version and version != snapshot.version):
                raise SnapshotUnavailable("结果版本已变化，请重新查询日报。")
            days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            missing = [day.isoformat() for day in days if day not in snapshot.covered_days]
            if missing:
                return {"available": False, "error": "所选范围存在未同步日期。", "missingDays": missing}
            if detail:
                return self.details(snapshot, target, group, page, page_size)
            with localcontext() as context:
                context.prec = 48
                if group_by:
                    return self.by_dimension(snapshot, target, group, group_by)
                return self.summary(snapshot, days)
        except SnapshotUnavailable as error:
            return {"available": False, "error": str(error)}

    @staticmethod
    def checked_records(snapshot, first, last):
        previous = None
        for index, row in enumerate(snapshot.records):
            key = (row.day, row.key)
            if index >= MAX_RECORDS:
                raise SnapshotUnavailable("明细量超过查询上限，请缩小日期或筛选范围。")
            if (
                not row.key or not first <= row.day <= last
                or (previous is not None and key <= previous)
                or (row.segments is not None and row.segments < 0)
                or (row.profit is not None and not row.profit.is_finite())
            ):
                raise SnapshotUnavailable("出票数据存在无效值、重复归属或排序异常。")
            previous = key
            yield row

    def summary(self, snapshot, days):
        labels = (*GROUPS, "unclassified")
        daily = {day: {key: Totals() for key in labels} for day in days}
        combined = {key: Totals() for key in labels}
        for row in self.checked_records(snapshot, days[0], days[-1]):
            group = row.group or "unclassified"
            for result in (daily[row.day], combined):
                result[group].add(row)
                result["total"].add(row)
        differences = []
        if snapshot.ads_daily is not None:
            for day, groups in daily.items():
                total = groups["total"]
                observed = (total.records, total.segments, total.segment_missing,
                            total.profit_missing, total.ads_projected_profit)
                if observed != snapshot.ads_daily.get(day, (0, 0, 0, 0, Decimal(0))):
                    differences.append(day.isoformat())
        return {
            "available": True,
            "snapshotVersion": snapshot.version,
            "rows": [{"date": day.isoformat(), **{key: item.payload() for key, item in groups.items()}}
                     for day, groups in daily.items()],
            "summary": {key: item.payload() for key, item in combined.items()},
            "adsReconciliation": "unavailable" if snapshot.ads_daily is None else (
                "different" if differences else "matched"
            ),
            "adsDifferenceDays": differences,
        }

    def details(self, snapshot, target, group, page, page_size):
        rows = []
        total = 0
        tickets = set()
        unknown = 0
        offset = (page - 1) * page_size
        for row in self.checked_records(snapshot, target, target):
            if group != "total" and row.group != group:
                continue
            if row.ticket_number:
                tickets.add(row.ticket_number)
            else:
                unknown += 1
            if offset <= total < offset + page_size:
                rows.append({
                    "recordKey": row.key, "issueDate": row.day.isoformat(),
                    "ticketNumber": row.ticket_number, "ticketRaw": row.ticket_raw,
                    "orderReference": row.order_reference, "segmentCount": row.segments,
                    "presaleProfit": None if row.profit is None else format(row.profit, "f"),
                    **row.dimensions,
                })
            total += 1
        return {
            "available": True, "error": "", "source": snapshot.version,
            "period": {"startDate": target.isoformat(), "endDate": target.isoformat()},
            "business": {"key": "issue", "label": "出票"},
            "columns": COLUMNS, "rows": rows, "total": total, "ticketCount": len(tickets),
            "unrecognizedTicketRecords": unknown, "page": page, "pageSize": page_size,
        }

    def by_dimension(self, snapshot, target, group, dimension):
        import json

        totals = Totals()
        grouped = {}
        for row in self.checked_records(snapshot, target, target):
            if group != "total" and row.group != group:
                continue
            key = tuple(row.dimensions.get(column) for column in DIMENSIONS[dimension])
            grouped.setdefault(key, Totals()).add(row)
            totals.add(row)
        return {"available": True, "total": totals.payload(), "rows": [
            {"value": json.dumps(key, ensure_ascii=False), "label": " / ".join(dict.fromkeys(filter(None, key))) or "未知",
             **metric.payload()} for key, metric in grouped.items()
        ]}
