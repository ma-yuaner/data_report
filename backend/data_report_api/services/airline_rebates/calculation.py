"""Read-only Hive and deterministic HKG26003 trial calculations."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import re

from ..data_source import DataSource

MAX_ROWS = 50_000
SOURCE_SQL = Path(__file__).with_name("hive_trial.sql")
CATEGORIES = {
    "longHaul": "国际远程",
    "shortHaul": "国际非远程",
    "regionalNonDesignated": "地区非指定",
    "regionalDesignated": "地区指定",
    "otherOrigin": "非港澳始发",
}


def fetch_facts(config, policy):
    source = DataSource({**config, "DATA_MODE": "hive"})
    if source.database != "lywz":
        raise ValueError("HKG26003 试点只支持 lywz 宽表")
    first = date.fromisoformat(policy["flownStart"])
    end = date.fromisoformat(policy["flownEnd"]) + timedelta(days=1)
    sql = SOURCE_SQL.read_text(encoding="utf-8-sig")
    dimension, extract = (statement.strip() for statement in sql.strip().rstrip(";").split(";"))
    airports = defaultdict(set)
    with closing(source.connect()) as connection, closing(connection.cursor()) as cursor:
        cursor.execute(dimension)
        for airport, country in cursor:
            airports[airport.strip()].add(country.strip())
        cursor.execute(extract, (first.replace(year=first.year - 1).isoformat(), end.isoformat(), first.isoformat(), end.isoformat()))
        records = cursor.fetchmany(MAX_ROWS + 1)
    if not records or len(records) > MAX_ROWS:
        raise ValueError("宽表无数据或超出试点容量，未生成结果")
    return records, airports


def classify(policy, row, airports, duplicates):
    order, ticket, route, _, cabin_text, amount, currency, origin, dest, age, refund, status, reissue, fare_type = row
    order_key = (order, ticket)
    if not order or not ticket or order_key in duplicates:
        return "待核：缺少唯一票号或有重复", None, None, False
    if not str(ticket).startswith(policy["ticketPrefix"]):
        return "排除：票证不符", None, None, False
    if str(status) in ("2", "3") or refund in ("已退票", "废票", "已作废"):
        return "排除：退票或作废", None, None, False
    if reissue != "否" or str(status) == "4" or refund == "退票中":
        return "待核：退票或换开链路", None, None, False
    if age in ("婴儿", "INF") or any(item in (fare_type or "") for item in ("包机", "包收入")):
        return "排除：婴儿或包机", None, None, False
    if amount is None or amount < 0 or currency != policy["currency"]:
        return "待核：金额或币种", None, None, False
    points = set(re.findall(r"[A-Z]{3}", (route or "").upper())) - {origin}
    if not origin or not points or any(len(airports.get(point, ())) != 1 for point in points | {origin}):
        return "待核：航程或机场国家", None, None, False
    countries = {next(iter(airports[point])) for point in points}
    if airports[origin] == {"CN"} and countries == {"CN"}:
        return "排除：纯内地客票", None, None, False
    if origin not in ("HKG", "MFM"):
        category = "otherOrigin"
    elif countries.intersection(policy["longHaul"]):
        category = "longHaul"
    elif countries.intersection(policy["shortHaul"]):
        category = "shortHaul"
    elif countries == {"CN"}:
        category = next((item for item in ("regionalDesignated", "regionalNonDesignated")
                         if dest in policy[item].get(origin, ())), None)
    else:
        category = None
    cabins = set(re.findall(r"[A-Z]", (cabin_text or "").upper()))
    excluded = set(policy["excludedCabins"])
    measure_only = set(policy["measureOnlyCabins"])
    label = CATEGORIES.get(category, "航线待核")
    if cabins and cabins <= excluded:
        return "排除：不计量不计奖舱位", category, None, False
    if not category or not cabins or cabins & excluded:
        return "待核：航线或舱位未能按整票判定", category, None, False
    if cabins <= measure_only or "集团" in (fare_type or ""):
        return label + " · 计量不计奖（代理）", category, None, True
    group = next((key for key, codes in zip(("groupA", "groupB"), policy["cabinGroups"])
                  if cabins <= set(codes)), None)
    if group is None:
        return label + " · 待核：混合舱位票联金额", category, None, True
    return label + " · 可试算", category, group, True


def simulate(config, policy):
    records, airports = fetch_facts(config, policy)
    keys = Counter((row[0], row[1]) for row in records)
    duplicates = {k for k, count in keys.items() if count > 1}
    details, weighted, day_amounts = defaultdict(list), defaultdict(lambda: defaultdict(Decimal)), defaultdict(Decimal)
    pending = Counter()
    for index, row in enumerate(records, 1):
        order, _, route, planned_departure, _, ticket_fare, *_ = row
        day = str(planned_departure)[:10]
        if not policy["flownStart"] <= day <= policy["flownEnd"]:
            raise ValueError("首段起飞日期超出试点范围")
        result, category, group, measured = classify(policy, row, airports, duplicates)
        amount = ticket_fare if measured else None
        if amount is not None:
            day_amounts[day] += amount
        if group:
            weighted[day][category, group] += amount
        if "待核" in result:
            pending[result.split("待核：", 1)[-1]] += 1
        details[day].append({
            "id": str(index), "orderNo": str(order or "—"), "route": route or "—",
            "eligibleAmount": str(amount) if amount is not None else None, "result": result,
        })

    def amounts(tier, rate_bases):
        if tier is None:
            return None, None
        rewards = defaultdict(Decimal)
        for (category, group), amount in rate_bases.items():
            rate = tier["ratesPercent"][group][policy["routeCategories"].index(category)]
            rewards[category] += amount * Decimal(rate) / 100
        return sum(rewards.values(), Decimal(0)), rewards["otherOrigin"]

    cumulative = Decimal(0)
    bases = defaultdict(Decimal)
    timeline = []
    first_tier = min(item["lowerExclusive"] for item in policy["tiers"])
    for day in sorted(details):
        cumulative += day_amounts[day]
        for key, amount in weighted[day].items():
            bases[key] += amount
        tier = next((item for item in policy["tiers"] if cumulative > item["lowerExclusive"]
                     and (item["upperInclusive"] is None or cumulative <= item["upperInclusive"])), None)
        reward, other = amounts(tier, bases)
        timeline.append({
            "id": day, "date": day, "version": 1, "actual": str(cumulative),
            "completionRate": str(cumulative * 100 / first_tier), "detailCount": len(details[day]),
            "tier": None if tier is None else f"T{sorted(item['lowerExclusive'] for item in policy['tiers']).index(tier['lowerExclusive']) + 1}",
            "estimatedReward": None if reward is None else str(reward),
            "otherOriginReward": None if other is None else str(other),
        })
    last = timeline[-1]
    return ({
        "status": "ready", "target": first_tier, "actual": last["actual"],
        "completionRate": last["completionRate"], "dataAsOf": last["date"], "version": 1,
        "estimatedReward": last["estimatedReward"], "otherOriginReward": last["otherOriginReward"],
        "tier": last["tier"], "daily": timeline[::-1], "sourceRows": len(records),
        "pendingCount": sum(pending.values()), "pendingReasons": dict(pending),
        "dataNote": "按首段计划起飞日和 HKD 票面价试算。历史导出范围差异未作额外排除。实际承运、净收入和待核票联由业务复核。",
    }, details)
