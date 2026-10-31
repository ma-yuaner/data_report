"""M01 offline verifier: prepare read-only Hive SQL and check exported aggregates.

No database connection, credentials, third-party dependencies or AI calls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/sql/gds-m01-readonly-check.sql"
TZ = timezone(timedelta(hours=8))
DIMENSIONS = (
    "pcc_code", "ota_code", "ota_site_code", "data_source", "api_method", "apimethod",
    "source_api_group", "channel_alias_raw", "mpisflag_raw", "ndcflag_raw", "gdsreal_raw",
    "hitcacheflag", "adultnum", "childnum", "infantnum", "flightway",
)
COUNTS = (
    "records", "success_records", "failure_records", "unknown_success_records",
    "invalid_subcount_records", "traceid_present_records", "referenceid_present_records",
)
ALIASES = {"ota_code": ("ota_code", "otacode"), "ota_site_code": ("ota_site_code", "otasitecode")}
SOURCE_FIELDS = (
    "dt", "gds_code", "dep_city", "arr_city", "adultnum", "datediffdepart", "datediffroundtrip",
    "pcc_code", "ota_code", "ota_site_code", "data_source", "api_method", "apimethod",
    "source_api_group", "gdschannelalias", "mpisflag", "ndcflag", "gdsreal", "hitcacheflag",
    "childnum", "infantnum", "flightway", "successflag", "apirequestsubcount", "traceid", "referenceid",
)
NULLS = {"", "null", "\\n", "__null__"}


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def fingerprint(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("库名/表名仅允许字母、数字和下划线，且不能以数字开头")
    return value


def schema_columns(path):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("结构文件过大；请只提供Q0 DESCRIBE结果")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    columns = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", "+", "--")):
            continue
        if "|" in line:
            parts = [p.strip() for p in line.strip("|").split("|")]
        elif "\t" in line:
            parts = next(csv.reader([line], delimiter="\t"))
        elif "," in line:
            parts = next(csv.reader([line]))
        else:
            parts = re.split(r"\s+", line, maxsplit=2)
        if len(parts) < 2:
            continue
        name, kind = (p.strip().strip('`"') for p in parts[:2])
        if name.lower() in {"col_name", "column_name", "column", "字段名"}:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        # DESCRIBE may repeat partition columns; conflicting types remain errors.
        key = name.lower()
        if key in columns and columns[key]["type"].lower() != kind.lower():
            raise ValueError(f"结构中字段类型冲突：{name}")
        columns[key] = {"name": name, "type": kind}
    mapping, missing = {}, []
    for field in SOURCE_FIELDS:
        candidates = [columns[k] for k in ALIASES.get(field, (field,)) if k in columns]
        if not candidates:
            missing.append(field)
        elif len(candidates) > 1:
            raise ValueError(f"存在多个候选字段，请确认后提供唯一结构：{field}")
        else:
            mapping[field] = candidates[0]["name"]
    return {"columns": columns, "mapping": mapping, "missing": missing, "source": fingerprint(path)}


def prepare(args):
    first = date.fromisoformat(args.date)
    database, table = identifier(args.database), identifier(args.table)
    for value in (args.dep, args.arr):
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("出发/到达城市须为三个大写英文字母")
    if not (0 <= args.depart_min <= args.depart_max <= 366 and 0 <= args.stay_min <= args.stay_max <= 366):
        raise ValueError("去程/停留范围须为0—366内的闭区间")
    if not 1 <= args.adults <= 9:
        raise ValueError("成人数须为1—9")
    if args.expected_records is not None and args.expected_records < 0:
        raise ValueError("预期记录数不能为负")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("输出目录已含文件，请使用新的目录，保留旧核验版本")
    schema = schema_columns(args.schema) if args.schema else None
    qualified = f"{database}.{table}"
    scope = {
        "version": 1, "createdAt": now(), "table": qualified, "date": first.isoformat(),
        "partitionFormat": "yyyyMMdd及其小时/分钟后缀", "gds": "1A", "dep": args.dep, "arr": args.arr,
        "adults": args.adults, "departRange": [args.depart_min, args.depart_max],
        "stayRange": [args.stay_min, args.stay_max], "expectedRecords": args.expected_records,
        "schema": schema, "scopeEvidence": "参数声明；工具不连接Hive，不能独立证明实际执行条件",
        "stage": "schema_required" if schema is None else "schema_missing_fields" if schema["missing"] else "sql_ready",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "Q0_structure.sql").write_text(f"DESCRIBE {qualified};\n", encoding="utf-8")
    if scope["stage"] == "sql_ready":
        template = TEMPLATE.read_text(encoding="utf-8")
        sql = template[template.index("SELECT\n"):]
        sql = sql.replace("lywz.dwd_gds_search_carrierdata_5minute", qualified)
        sql = sql.replace("'20261029'", "'" + first.strftime("%Y%m%d") + "'")
        sql = sql.replace("'20261030'", "'" + (first + timedelta(days=1)).strftime("%Y%m%d") + "'")
        sql = sql.replace("'BKK'", "'" + args.dep + "'").replace("'TYO'", "'" + args.arr + "'")
        sql = sql.replace("adultnum = 1", f"adultnum = {args.adults}")
        sql = sql.replace("BETWEEN 1 AND 179", f"BETWEEN {args.depart_min} AND {args.depart_max}")
        sql = sql.replace("BETWEEN 2 AND 15", f"BETWEEN {args.stay_min} AND {args.stay_max}")
        # Only the two explicitly documented naming variants are mapped.
        for canonical in ("ota_code", "ota_site_code"):
            actual = schema["mapping"][canonical]
            sql = re.sub(r"\b" + canonical + r"\b", actual, sql, flags=re.I)
            sql = sql.replace("    " + actual + ",", "    " + actual + " AS " + canonical + ",", 1)
        if not sql.lstrip().startswith("SELECT") or len(sql.split(";")) != 2:
            raise ValueError("只读模板结构异常，拒绝生成")
        (out / "Q1_aggregate.sql").write_text("-- M01只读；按已提供结构生成，执行前确认dt格式。\n" + sql, encoding="utf-8")
        scope["query"] = fingerprint(out / "Q1_aggregate.sql")
    write_json(out / "scope.json", scope)
    print(json.dumps({"stage": scope["stage"], "output": str(out), "missing": schema["missing"] if schema else []}, ensure_ascii=False))
    return 0 if scope["stage"] == "sql_ready" else 2


def number(raw, field, *, nullable=False):
    text = (raw or "").strip()
    if nullable and text.lower() in NULLS:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field}不是有效整数") from exc
    if not value.is_finite() or value != value.to_integral_value():
        raise ValueError(f"{field}不是有限整数")
    return int(value)


def flag(raw):
    text = raw.strip().lower()
    return "空值" if text in NULLS else text if text in {"true", "false"} else "其他值"


def inspect_results(args):
    scope = json.loads(args.scope.read_text(encoding="utf-8-sig"))
    if scope.get("version") != 1 or scope.get("stage") != "sql_ready" or scope.get("gds") != "1A":
        raise ValueError("需要本工具生成且结构字段齐备的scope.json；先执行prepare --schema")
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("输出目录已含文件，请使用新的目录")
    # Large raw logs are deliberately not accepted as aggregate exports.
    if args.results.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("结果超过256MB，请确认导出的是Q1聚合结果而非原始日志")
    totals = Counter()
    distributions = {k: Counter() for k in (
        "mpisflag_raw", "ndcflag_raw", "gdsreal_raw", "source_api_group", "hitcacheflag", "apimethod", "api_method",
    )}
    matrix, seen, issues = Counter(), set(), Counter()
    nullable_subcount_groups = 0
    with args.results.open(encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        delimiter = "\t" if "\t" in sample.partition("\n")[0] else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        required = set(DIMENSIONS + COUNTS + ("api_subcount_sum",))
        if len(headers) != len(set(headers)) or not required.issubset(headers):
            raise ValueError("Q1结果表头缺失或重复：" + ",".join(sorted(required - set(headers))))
        reader.fieldnames = headers
        for row_no, row in enumerate(reader, 2):
            if row_no > 200001:
                raise ValueError("聚合组超过20万，请缩小范围；未发布部分结果")
            if None in row or any(row[h] is None for h in headers):
                raise ValueError(f"第{row_no}行列数与表头不一致")
            dims = tuple(row[h].strip() for h in DIMENSIONS)
            if dims in seen:
                raise ValueError(f"第{row_no}行聚合维度重复，可能重复拼接导出；不能直接累计")
            seen.add(dims)
            values = {h: number(row[h], h) for h in COUNTS}
            n = values["records"]
            if n <= 0 or any(not 0 <= v <= n for h, v in values.items() if h != "records"):
                raise ValueError(f"第{row_no}行计数超界")
            if sum(values[h] for h in ("success_records", "failure_records", "unknown_success_records")) != n:
                raise ValueError(f"第{row_no}行成功/失败/未知合计不等于records")
            if number(row["adultnum"], "adultnum") != scope["adults"]:
                raise ValueError(f"第{row_no}行成人数与声明范围不一致")
            subcount = number(row["api_subcount_sum"], "api_subcount_sum", nullable=True)
            if subcount is None:
                nullable_subcount_groups += 1
            else:
                totals["api_subcount_sum"] += subcount
                if subcount < 0:
                    issues["negative_subcount_groups"] += 1
            totals.update(values)
            for name in distributions:
                distributions[name][row[name].strip() or "__EMPTY__"] += n
            mpis, ndc = flag(row["mpisflag_raw"]), flag(row["ndcflag_raw"])
            matrix[(row["source_api_group"].strip(), mpis, ndc, row["gdsreal_raw"].strip())] += n
            issues["mpis_" + mpis] += n
            issues["ndc_" + ndc] += n
            if mpis == ndc == "true":
                issues["both_flags_true"] += n
            if row["source_api_group"].strip().upper().endswith("_MPIS") and mpis != "true":
                issues["mpis_group_flag_needs_review"] += n
            child = number(row["childnum"], "childnum", nullable=True)
            infant = number(row["infantnum"], "infantnum", nullable=True)
            if child is None or infant is None:
                issues["passenger_unknown"] += n
            elif child < 0 or infant < 0:
                issues["passenger_invalid"] += n
            elif child or infant:
                issues["mixed_passengers"] += n
            else:
                issues["adult_only"] += n
    warnings = []
    if not seen:
        warnings.append("结果只有表头，没有聚合记录；不能证明源数据完整或当前无业务")
    expected = scope.get("expectedRecords")
    delta = totals["records"] - expected if expected is not None else None
    if delta:
        warnings.append(f"与声明对照数相差{delta}条，先核对过滤条件、源版本、保留期和是否截断，不填平差额")
    for key, message in (
        ("both_flags_true", "MPIS/NDC同时true，需结合别名优先规则和执行语义核对，不互斥分摊"),
        ("mpis_group_flag_needs_review", "MPIS接口组与请求标记不一致，须核查别名映射，不能据此认定数据错误"),
        ("mpis_其他值", "MPIS出现true/false之外的值，字典待确认"),
        ("mpis_空值", "MPIS标记有空值，保留未知，不转成普通MP"),
        ("ndc_其他值", "NDC出现true/false之外的值，字典待确认"),
        ("passenger_invalid", "儿童/婴儿计数出现负值，需核对"),
        ("negative_subcount_groups", "子接口计数出现负合计，需核对源字段与ETL"),
    ):
        if issues[key]:
            warnings.append(message)
    if totals["unknown_success_records"]:
        warnings.append("成功状态存在未知值，按日志记录单列，未默认为失败或成功")
    if nullable_subcount_groups:
        warnings.append("部分聚合组子接口合计为空，已知合计不代表完整子接口量")
    n = totals["records"]
    report = {
        "generatedAt": now(), "scope": scope, "inputs": {"aggregate": fingerprint(args.results), "scope": fingerprint(args.scope)},
        "aggregateGroups": len(seen), "totals": dict(totals), "checks": dict(issues),
        "comparison": {"expectedRecords": expected, "recordsDelta": delta},
        "mpisFlagRecordShare": str(Decimal(issues["mpis_true"]) / n) if n else None,
        "subcountNullGroups": nullable_subcount_groups, "distributions": {k: dict(v) for k, v in distributions.items()},
        "status": "needs_review" if warnings else "aggregate_checks_passed_semantics_pending",
        "warnings": warnings,
        "unavailableMetrics": ["唯一入口查询量", "普通MP实际外呼量", "NDC实际调用量", "MPIS命中/成功采用量及实际替代率"],
        "limitations": [
            "只核对导出的聚合结果，不证明实际查询条件、完整导出或线上ETL版本；须保留执行SQL及取数回执",
            "mpisflag仅为请求标记；总记录减true不等于普通MP调用，未计算资源替代率或航线查定比",
            "traceid/referenceid仅统计非空覆盖，不证明唯一性、跨资源可关联或没有重试",
            "successflag沿当前仓库0成功/1失败字典，待线上版本确认；接口成功不代表可售或被采用",
            "api_subcount_sum可能已经由ETL将空/0映射成1，不能还原原始无效次数或当作计费外呼量",
        ],
        "m01Complete": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "report.json", report)
    with (out / "resource_flag_matrix.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source_api_group", "MPIS标记", "NDC标记", "gdsreal原值", "日志记录数"])
        writer.writerows((*key, count) for key, count in sorted(matrix.items(), key=lambda item: -item[1]))
    text = ["M01聚合数据核验（不是M01业务验收完成）", f"生成时间：{report['generatedAt']}",
            f"日期：{scope['date']}；1A；{scope['dep']}→{scope['arr']}",
            f"聚合组数：{len(seen)}；日志记录数：{n}；对照差额：{delta if delta is not None else '未配置对照数'}",
            f"MPIS true标记记录：{issues['mpis_true']}；标记占比：{report['mpisFlagRecordShare'] or '不可计算'}",
            f"成功：{totals['success_records']}；失败：{totals['failure_records']}；未知：{totals['unknown_success_records']}",
            f"纯成人记录：{issues['adult_only']}；混合旅客：{issues['mixed_passengers']}；旅客数未知：{issues['passenger_unknown']}",
            f"traceid非空：{totals['traceid_present_records']}；referenceid非空：{totals['referenceid_present_records']}",
            "待核对：", *warnings, "仍不可得的指标：", *report["unavailableMetrics"], "限制：", *report["limitations"]]
    (out / "report.txt").write_text("\n".join(text) + "\n", encoding="utf-8-sig")
    print(json.dumps({"status": report["status"], "records": n, "output": str(out), "m01Complete": False}, ensure_ascii=False))
    return 0 if n and not warnings else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="生成Q0；有真实结构时生成Q1和scope")
    prepare_parser.add_argument("--date", default="2026-10-29")
    prepare_parser.add_argument("--database", default="lywz")
    prepare_parser.add_argument("--table", default="dwd_gds_search_carrierdata_5minute")
    prepare_parser.add_argument("--dep", default="BKK")
    prepare_parser.add_argument("--arr", default="TYO")
    prepare_parser.add_argument("--adults", type=int, default=1)
    prepare_parser.add_argument("--depart-min", type=int, default=1)
    prepare_parser.add_argument("--depart-max", type=int, default=179)
    prepare_parser.add_argument("--stay-min", type=int, default=2)
    prepare_parser.add_argument("--stay-max", type=int, default=15)
    prepare_parser.add_argument("--expected-records", type=int)
    prepare_parser.add_argument("--schema", type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)
    prepare_parser.set_defaults(run=prepare)
    check_parser = commands.add_parser("check", help="检查Hive导出的完整Q1 CSV/TSV，不查询数据库")
    check_parser.add_argument("--scope", required=True, type=Path)
    check_parser.add_argument("--results", required=True, type=Path)
    check_parser.add_argument("--output", required=True, type=Path)
    check_parser.set_defaults(run=inspect_results)
    args = parser.parse_args()
    try:
        return args.run(args)
    except (ValueError, OSError, csv.Error, KeyError, TypeError) as exc:
        print(f"M01核验未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
