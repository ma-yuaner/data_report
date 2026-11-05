-- RISK-CHECK-009：按日成功事实读取，与账号加载任务解耦。只读源为sibebid。
-- 所有%s均驱动绑定；例示日期形态不内嵌真实订单或账号。原因仍限已确认十类。
-- Python再校验日/目录/明细批次、源版本、规则/运行时哈希及JSON状态；不只凭有行通过。
-- 日期范围按内部订单ID取范围内最后出票日，避免跨日重复。

SELECT o.order_id,o.profit_reason_type,o.update_time,o.etl_run_id AS catalog_run_id,o.issue_date,
 p.etl_run_id AS prepared_run_id,p.rule_version,p.engine_hash,p.source_updated_at,p.reason_code,
 p.evidence_hash,JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.status')) AS published_status,JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.ruleVersion')) AS body_version,JSON_UNQUOTE(JSON_EXTRACT(p.result_json,'$.engineHash')) AS body_hash,p.prepared_at,d.etl_run_id AS ready_run_id,
 d.rule_version AS ready_version,d.engine_hash AS ready_hash FROM bi_risk_order_day o
 LEFT JOIN bi_risk_prepared_order p ON p.issue_date=o.issue_date AND p.order_id=o.order_id
 LEFT JOIN bi_risk_prepared_day d ON d.issue_date=o.issue_date WHERE o.issue_date >= %s AND o.issue_date <= %s
                 AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer
                     WHERE newer.order_id=o.order_id AND newer.issue_date>o.issue_date
                       AND newer.issue_date<=%s) AND o.profit_reason_type IN (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) LIMIT 20001;

-- 上句参数为起止日期、去重终点日期、十个原因编码。超20000单拒绝而不截断统计。
SELECT o.order_id,o.profit_reason_type,o.update_time,o.etl_run_id AS catalog_run_id,o.issue_date,
 p.etl_run_id AS prepared_run_id,p.rule_version,p.engine_hash,p.source_updated_at,p.reason_code,
 p.evidence_hash,p.result_json,p.prepared_at,d.etl_run_id AS ready_run_id,
 d.rule_version AS ready_version,d.engine_hash AS ready_hash FROM bi_risk_order_day o
 LEFT JOIN bi_risk_prepared_order p ON p.issue_date=o.issue_date AND p.order_id=o.order_id
 LEFT JOIN bi_risk_prepared_day d ON d.issue_date=o.issue_date WHERE o.order_id=%s AND o.issue_date=%s ORDER BY o.issue_date DESC LIMIT 1;

-- 人工抽查在同一目标事务内锁定本次实际事实，校验稳定结果ID及owner后写抽查。
SELECT o.order_id,o.profit_reason_type,o.update_time,o.etl_run_id AS catalog_run_id,o.issue_date,
 p.etl_run_id AS prepared_run_id,p.rule_version,p.engine_hash,p.source_updated_at,p.reason_code,
 p.evidence_hash,p.result_json,p.prepared_at,d.etl_run_id AS ready_run_id,
 d.rule_version AS ready_version,d.engine_hash AS ready_hash FROM bi_risk_order_day o
 LEFT JOIN bi_risk_prepared_order p ON p.issue_date=o.issue_date AND p.order_id=o.order_id
 LEFT JOIN bi_risk_prepared_day d ON d.issue_date=o.issue_date WHERE o.order_id=%s AND o.issue_date=%s ORDER BY o.issue_date DESC LIMIT 1 FOR UPDATE;
INSERT INTO bi_risk_auto_samples (id,owner,result_id,body) VALUES (%s,%s,%s,%s);
SELECT body FROM bi_risk_auto_samples WHERE owner=%s AND result_id=%s ORDER BY seq DESC;

-- 按日检查覆盖，部分缺日不使其他成功日失效。
SELECT p.issue_date,p.diagnostics_json FROM bi_risk_prepared_day p
JOIN bi_risk_sync_day c ON c.issue_date=p.issue_date AND c.etl_run_id=p.etl_run_id
WHERE p.issue_date>=%s AND p.issue_date<=%s AND p.rule_version=%s AND p.engine_hash=%s;
-- 缺日作为missingDays显式返回，不用账号加载历史推导本批次结果。
