"""Read-only MP combination ranking; never infer routes or booking attribution."""

import json

FIELDS = ("gds_code", "pcc_code", "ota_code", "ota_site_code")
KEYS = ("gds", "pcc", "platform", "site")
LIMIT = 500


def parse_targets(raw):
    values = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("组合目标须为最多100项的JSON列表")
    result = {}
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("组合目标项格式错误")
        key = tuple(str(item.get(k) or "").strip().upper() for k in KEYS)
        ratio = item.get("targetRatio")
        if not all(key) or any(len(v) > 128 for v in key) or type(ratio) is not int or ratio <= 0:
            raise ValueError("组合目标须有完整四维编码及正整数targetRatio")
        if key in result:
            raise ValueError("组合目标编码重复")
        result[key] = ratio
    return result


def ranking(cursor, table, where, params, gds_targets, overrides, metric, breach_only):
    cases, target_params = [], []
    for key, ratio in overrides.items():
        cases.append("WHEN " + " AND ".join(f"UPPER({f}) = %s" for f in FIELDS) + " THEN %s")
        target_params.extend([*key, ratio])
    for gds, ratio in gds_targets.items():
        cases.append("WHEN UPPER(gds_code) = %s THEN %s")
        target_params.extend([gds, ratio])
    target_sql = "CASE " + " ".join(cases) + " ELSE NULL END" if cases else "NULL"
    # The derived table applies each row's target before ranking or the 500-row cap.
    aggregate = ", ".join(FIELDS)
    sql = f"""SELECT * FROM (
SELECT {aggregate}, {metric["aliased"]}, {target_sql} AS effective_target
FROM {table} WHERE {where} GROUP BY {aggregate}
) combos"""
    eligible = "effective_target IS NOT NULL AND missing_rows=0 AND segments IS NOT NULL AND searches > effective_target*segments"
    if breach_only:
        sql += " WHERE " + eligible
    sql += """ ORDER BY
CASE WHEN effective_target IS NULL OR missing_rows>0 OR segments IS NULL THEN 1 ELSE 0 END,
GREATEST(searches-effective_target*segments,0) DESC,
searches DESC, gds_code, pcc_code, ota_code, ota_site_code LIMIT 501"""
    cursor.execute(sql, tuple([*target_params, *params]))
    raw = cursor.fetchall()
    rows = []
    for row in raw[:LIMIT]:
        key = tuple("" if v is None else str(v).strip() for v in row[:4])
        target = None if row[-1] is None else int(row[-1])
        values = metric["build"](tuple(row[4:-1]), True, target, True)
        rows.append(
            {
                "value": json.dumps(key, ensure_ascii=False),
                "name": " / ".join(v or "未知编码" for v in key),
                **dict(zip(KEYS, key)),
                **values,
                "targetSource": "组合专属"
                if tuple(v.upper() for v in key) in overrides
                else "GDS默认"
                if target is not None
                else "未配置",
                "preciseScope": all(key),
            }
        )
    return rows, len(raw) > LIMIT
