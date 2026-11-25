"""Read-only HKG26003 flight-date and face-value trial."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import re

from ..data_source import DataSource
from .mapping import FIELDS, MappingValidationError, validate_facts, validate_projection

MAX_ROWS = 50_000
SOURCE_SQL = Path(__file__).with_name("hive_trial.sql")
CATEGORIES = {
    "longHaul": "国际远程",
    "shortHaul": "国际非远程",
    "regionalNonDesignated": "地区非指定",
    "regionalDesignated": "地区指定",
    "otherOrigin": "异地始发（SOTO）",
}
FIXED_RATE = Decimal("0.01")


def fetch_facts(config, policy):
    source = DataSource({**config, "DATA_MODE": "hive"})
    if source.database != "lywz":
        raise ValueError("HKG26003 试点只支持 lywz 宽表")
    start = date.fromisoformat(policy["flownStart"])
    end = date.fromisoformat(policy["flownEnd"])
    months = sorted({(start + timedelta(days=i)).strftime("%Y-%m") for i in range((end - start).days + 1)})
    month_pattern = "(" + "|".join(months) + ")-[0-9]{2}"
    dimension, extract = SOURCE_SQL.read_text(encoding="utf-8-sig").strip().rstrip(";").split(";")
    airports = defaultdict(set)
    with closing(source.connect()) as connection, closing(connection.cursor()) as cursor:
        cursor.execute(dimension.strip())
        for airport, country in cursor:
            airports[airport.strip()].add(country.strip())
        cursor.execute(extract.strip(), (
            policy["ticketPrefix"], start.isoformat(), (end + timedelta(days=1)).isoformat(), month_pattern,
        ))
        validate_projection(cursor.description)
        records = cursor.fetchmany(MAX_ROWS + 1)
    if not records or len(records) > MAX_ROWS:
        raise ValueError("宽表无数据或超出试点容量，未生成结果")
    return records, airports


def route_category(policy, origin, destination, segments, airports):
    points = {part for segment in segments for part in segment.split("-")}
    if origin not in points or any(len(airports.get(point, ())) != 1 for point in points):
        return None
    countries = {next(iter(airports[point])) for point in points - {origin}}
    if airports[origin] == {"CN"} and countries == {"CN"}:
        return "domestic"
    if origin not in ("HKG", "MFM"):
        return "otherOrigin"
    if countries.intersection(policy["longHaul"]):
        return "longHaul"
    if countries.intersection(policy["shortHaul"]):
        return "shortHaul"
    if countries == {"CN"}:
        return next((kind for kind in ("regionalDesignated", "regionalNonDesignated")
                     if destination in policy[kind].get(origin, ())), None)
    return None


def split_values(value):
    return [part.strip().upper() for part in str(value or "").split(",")]


def in_flown_period(policy, day):
    return policy["flownStart"] <= day <= policy["flownEnd"]


def departure_examples(policy, row):
    segments = split_values(row[2])
    departures = split_values(row[14])
    if len(segments) != len(departures):
        return []
    examples = []
    for segment, value in zip(segments, departures):
        if not re.fullmatch(r"[A-Z]{3}-[A-Z]{3}", segment):
            return []
        try:
            day = date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return []
        examples.append({
            "route": segment, "raw": value[:60], "day": day,
            "inPeriod": in_flown_period(policy, day),
        })
    return examples


def mapping_example(policy, records):
    """Use one real candidate row, with only fields needed for policy review."""
    chosen = records[0]
    departures = []
    for row in records:
        departures = departure_examples(policy, row)
        if departures:
            chosen = row
            break
    fields = {
        "issue_ticket_no": str(chosen[1] or "")[:3] or None,
        **{FIELDS[index][0]: None if chosen[index] is None else str(chosen[index])[:240]
           for index in (2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)},
    }
    return {"fields": fields, "departures": departures[:12], "segmentCount": len(departures)}


def classify(policy, row, airports, duplicates):
    (order, ticket, route, first, cabin_text, fare, currency, origin, destination, age, refund, status,
     reissue, fare_type, departure_text, marketing_text, flight_status) = row
    segments = split_values(route)
    departures = split_values(departure_text)
    cabins = split_values(cabin_text)
    marketing = split_values(marketing_text)
    dates = [value[:10] for value in departures]
    decisions = []
    result = {
        "orderNo": str(order or "—"), "ticketNo": str(ticket or "—"), "route": route or "—",
        "ticketFare": None if fare is None else str(fare), "currency": currency,
        "segmentDecisions": decisions, "category": None, "cabinGroup": None,
        "eligibleAmount": None, "estimatedReward": None, "ratePercent": None,
    }

    def finish(reason):
        result["result"] = reason
        return result

    if not order or not ticket or (order, ticket) in duplicates:
        return finish("待核：票号缺失或订单票号重复")
    if not str(ticket).startswith(policy["ticketPrefix"]):
        return finish("排除：票证不符")
    if str(status) in ("2", "3") or flight_status in ("R", "V") or refund in ("已退票", "废票", "已作废"):
        return finish("排除：退票或废票")
    if str(status) == "4" or reissue != "否" or refund == "退票中":
        return finish("待核：改签或退票处理中，核对票联归属及新旧票去重")
    if age in ("婴儿", "INF") or any(item in (fare_type or "") for item in ("包机", "包收入")):
        return finish("排除：婴儿或包机")
    if not (len(segments) == len(dates) == len(cabins) == len(marketing)) or any(
        not re.fullmatch(r"[A-Z]{3}-[A-Z]{3}", segment) for segment in segments
    ) or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) for day in dates):
        return finish("待核：航段、计划日期、舱位或航司无法逐段对应")
    category = route_category(policy, origin, destination, segments, airports)
    result["category"] = category
    if category == "domestic":
        return finish("排除：纯内地客票")
    excluded = set(policy["excludedCabins"])
    measure_only = set(policy["measureOnlyCabins"])
    groups = dict(zip(("groupA", "groupB"), map(set, policy["cabinGroups"])))
    selected = []
    for segment, day, cabin, carrier in zip(segments, dates, cabins, marketing):
        flag = "期外"
        group = None
        if in_flown_period(policy, day):
            if cabin in excluded:
                flag = "不计量不计奖"
            elif carrier not in policy["carriers"]:
                flag = "实际承运待核"
            elif cabin in measure_only or "集团" in (fare_type or ""):
                flag = "仅计量"
            else:
                group = next((key for key, values in groups.items() if cabin in values), None)
                flag = "计量计奖候选" if group else "舱位待核"
            if flag in ("仅计量", "计量计奖候选"):
                selected.append((day, group))
        decisions.append({"route": segment, "date": day, "cabin": cabin, "marketingAirline": carrier, "result": flag})
    if all(item["result"] in ("期外", "不计量不计奖") for item in decisions):
        return finish("排除：各航段均期外或不计量不计奖")
    if not category:
        return finish("待核：航线分类")
    if len(selected) != len(segments):
        return finish("待核：部分航段符合，缺可分配的航段票面价或承运证据")
    if fare is None or fare < 0 or currency != policy["currency"]:
        return finish("待核：金额或币种")
    group_set = {group for _, group in selected}
    if len(group_set) != 1 and (category != "otherOrigin" or None in group_set):
        return finish("待核：混舱计奖比例不同，缺航段票面价")
    group = next(iter(group_set)) if len(group_set) == 1 else "groupA"
    result.update(eligibleAmount=str(fare), cabinGroup=group, calculationDate=max(d for d, _ in selected))
    return finish("计量计奖候选" if group else "仅计量")


def simulate(config, policy):
    records, airports = fetch_facts(config, policy)
    validation = validate_facts(records, airports)
    if not all(item["passed"] for item in validation["fields"].values()):
        failed = [name for name, item in validation["fields"].items() if not item["passed"]]
        raise MappingValidationError("候选明细的类型或有效值校验失败：" + "、".join(failed))
    counts = Counter((row[0], row[1]) for row in records)
    duplicates = {key for key, count in counts.items() if count > 1}
    details = defaultdict(list)
    pending = Counter()
    measured = defaultdict(Decimal)
    weighted = defaultdict(lambda: defaultdict(Decimal))
    category_counts = Counter()
    measured_by_category = defaultdict(Decimal)
    for index, row in enumerate(records, 1):
        item = classify(policy, row, airports, duplicates)
        item["id"] = str(index)
        day = item.get("calculationDate") or max(
            (entry["date"] for entry in item["segmentDecisions"]
             if policy["flownStart"] <= entry["date"] <= policy["flownEnd"]),
            default=None,
        ) or str(row[3] or "")[:10]
        if not policy["flownStart"] <= day <= policy["flownEnd"]:
            day = policy["flownEnd"]
            item["reviewBucket"] = True
        details[day].append(item)
        if item["result"].startswith("待核："):
            pending[item["result"].split("：", 1)[1]] += 1
        if item["eligibleAmount"] is not None:
            category, group = item["category"], item["cabinGroup"]
            amount = Decimal(item["eligibleAmount"])
            category_counts[category] += 1
            measured_by_category[category] += amount
            measured[day] += amount
            if group:
                weighted[day][category, group] += amount

    tiers = sorted(policy["tiers"], key=lambda item: item["lowerExclusive"])
    threshold = tiers[0]["lowerExclusive"]

    def rate_for(tier, category, group):
        if category == "otherOrigin":
            return FIXED_RATE
        if tier is None:
            return None
        return Decimal(tier["ratesPercent"][group][policy["routeCategories"].index(category)]) / 100

    cumulative = Decimal(0)
    bases = defaultdict(Decimal)
    timeline = []
    for day in sorted(details):
        cumulative += measured[day]
        for key, amount in weighted[day].items():
            bases[key] += amount
        tier = next((item for item in tiers if cumulative > item["lowerExclusive"]
                     and (item["upperInclusive"] is None or cumulative <= item["upperInclusive"])), None)
        by_category = defaultdict(Decimal)
        for (category, group), amount in bases.items():
            rate = rate_for(tier, category, group)
            if rate is not None:
                by_category[category] += amount * rate
        timeline.append({
            "id": day, "date": day, "version": 1, "actual": str(cumulative),
            "completionRate": str(cumulative * 100 / threshold), "detailCount": len(details[day]),
            "tier": None if tier is None else f"T{tiers.index(tier) + 1}",
            "estimatedReward": str(sum(by_category.values(), Decimal(0))),
            "otherOriginReward": str(by_category["otherOrigin"]),
        })
    orders = defaultdict(Decimal)
    for items in details.values():
        for item in items:
            if item["eligibleAmount"] is None:
                continue
            group, category = item["cabinGroup"], item["category"]
            rate = rate_for(tier, category, group) if group else Decimal(0)
            if rate is not None:
                item["ratePercent"] = str(rate * 100)
                reward = Decimal(item["eligibleAmount"]) * rate
                item["estimatedReward"] = str(reward)
                orders[item["orderNo"]] += reward
    for items in details.values():
        for item in items:
            if item["orderNo"] in orders:
                item["orderEstimatedReward"] = str(orders[item["orderNo"]])

    last = timeline[-1]
    categories = [{
        "id": category, "name": label, "records": category_counts[category],
        "measuredAmount": str(measured_by_category[category]), "estimatedReward": str(by_category[category]),
    } for category, label in CATEGORIES.items()]
    return ({
        "status": "ready", "target": threshold, "actual": last["actual"],
        "completionRate": last["completionRate"], "dataAsOf": last["date"], "version": 1,
        "estimatedReward": last["estimatedReward"], "otherOriginReward": last["otherOriginReward"],
        "tier": last["tier"], "daily": timeline[::-1], "sourceRows": len(records),
        "pendingCount": sum(pending.values()), "pendingReasons": dict(pending), "categories": categories,
        "dataNote": "按 Hive 各段计划起飞日及 HKD 票面价试算。仅整票各段均符合且金额可归属时纳入。符合计量条件的票面价累计冲档，异地始发固定按 1%。明细费率使用截至本批的档位。实际承运和正式结算待核。",
    }, details)
