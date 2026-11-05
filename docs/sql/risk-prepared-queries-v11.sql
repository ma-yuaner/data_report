-- RISK-ETL-005：MySQL；所有%s均DBAPI绑定，不拼接实际号码。
-- IN示例为单ID形态，生产按每批ID个数生成占位符（最多500），不是只读取一个ID。
-- 业务字段不含姓名、证件、联系方式；配置及日志读取复用RISK-CHECK-001。

SELECT id,ota_code,ota_site_code,product_type,manual_flag,issue_way,dep_city,arr_city,ota_order_no,relation_ota_order_no,profit_reason_type,update_time FROM order_info WHERE id IN (%s);

SELECT id,ota_code,ota_site_code,product_type,manual_flag,issue_way,dep_city,arr_city,ota_order_no,relation_ota_order_no,profit_reason_type,update_time FROM order_info WHERE ota_code=%s AND ota_site_code <=> %s AND (ota_order_no IN (%s) OR relation_ota_order_no IN (%s)) ORDER BY id LIMIT 10001;

SELECT id,order_id,passenger_id,issue_profit,sale_commission_amount,sale_currency,issue_ticket_time,supplier_code,marketing_airline,issue_gds_channel,issue_office_no,issue_ticketing_office_no FROM order_info_issue WHERE order_id IN (%s) ORDER BY id LIMIT 100001;

SELECT i.id,i.order_id,p.age_type FROM order_info_issue i LEFT JOIN order_info_passenger p ON p.id=i.passenger_id AND p.order_id=i.order_id WHERE i.order_id IN (%s) ORDER BY i.id LIMIT 100001;

SELECT i.issue_id,i.segment_id,s.id,s.order_id,s.airlift_flag,s.cabin,s.cabin_grade,s.flight_number,s.dep_airport,s.arr_airport,s.journey_sequence,s.segment_sequence FROM order_info_issue_segment i LEFT JOIN order_info_segment s ON s.id=i.segment_id WHERE i.issue_id IN (%s) ORDER BY i.issue_id,s.id LIMIT 100001;

SELECT airport_code,city_code,country_code,zone_code,area_code,update_time FROM base_airport WHERE airport_code IN (%s) AND status=1 LIMIT 2001;

-- 清洗目标临时阶段，只写目标连接；正式表DDL由部署人单独执行。
CREATE TEMPORARY TABLE risk_prepared_stage LIKE bi_risk_prepared_order;
DELETE FROM risk_prepared_stage;
INSERT INTO risk_prepared_stage (issue_date,order_id,reason_code,source_updated_at,etl_run_id,rule_version,engine_hash,evidence_hash,result_json,prepared_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
-- 以下须与原目录publish_day处在同一事务内；任何一步失败均回滚当日旧结果。
DELETE FROM bi_risk_prepared_order WHERE issue_date=%s;
INSERT INTO bi_risk_prepared_order (issue_date,order_id,reason_code,source_updated_at,etl_run_id,rule_version,engine_hash,evidence_hash,result_json,prepared_at)
SELECT issue_date,order_id,reason_code,source_updated_at,etl_run_id,rule_version,engine_hash,evidence_hash,result_json,prepared_at FROM risk_prepared_stage;
SELECT COUNT(*) AS n FROM bi_risk_prepared_order WHERE issue_date=%s;
INSERT INTO bi_risk_prepared_day (issue_date,etl_run_id,rule_version,engine_hash,row_count,diagnostics_json,prepared_at) VALUES (%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE etl_run_id=VALUES(etl_run_id),rule_version=VALUES(rule_version),engine_hash=VALUES(engine_hash),row_count=VALUES(row_count),diagnostics_json=VALUES(diagnostics_json),prepared_at=VALUES(prepared_at);

-- 页面只读取sibebid；先验证所选每一日有相同目录批次、规则版本和运行时哈希。
SELECT p.issue_date,p.etl_run_id,p.rule_version,p.engine_hash,p.row_count,p.diagnostics_json
FROM bi_risk_prepared_day p JOIN bi_risk_sync_day d ON d.issue_date=p.issue_date AND d.etl_run_id=p.etl_run_id
WHERE p.issue_date >= %s AND p.issue_date <= %s;

SELECT COUNT(*) AS n FROM bi_risk_order_day o WHERE o.issue_date>=%s AND o.issue_date<=%s AND o.profit_reason_type IN (%s,%s) AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer WHERE newer.order_id=o.order_id AND newer.issue_date>o.issue_date AND newer.issue_date<=%s);

SELECT o.order_id,o.profit_reason_type,o.update_time,o.etl_run_id,o.issue_date,p.evidence_hash,p.result_json,p.prepared_at FROM bi_risk_order_day o JOIN bi_risk_prepared_order p ON p.issue_date=o.issue_date AND p.order_id=o.order_id AND p.etl_run_id=o.etl_run_id AND p.reason_code=o.profit_reason_type AND p.source_updated_at <=> o.update_time AND p.rule_version=%s AND p.engine_hash=%s WHERE o.issue_date>=%s AND o.issue_date<=%s AND o.profit_reason_type IN (%s,%s) AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer WHERE newer.order_id=o.order_id AND newer.issue_date>o.issue_date AND newer.issue_date<=%s) ORDER BY o.order_id LIMIT 2001;

-- 部署只读门禁；在切换服务前确认当前规则/哈希存在同目录批次的成功日。
SELECT issue_date,order_id FROM bi_risk_prepared_order LIMIT 0;
SELECT COUNT(*) AS n FROM bi_risk_prepared_day p JOIN bi_risk_sync_day d ON d.issue_date=p.issue_date AND d.etl_run_id=p.etl_run_id WHERE p.rule_version=%s AND p.engine_hash=%s;
-- audit-only按源日期索引稳定游标扫描；续页参数为起止、上页时间两次、上页ID、页大小。
SELECT id,order_id,issue_ticket_time FROM order_info_issue WHERE issue_ticket_time >= %s AND issue_ticket_time < %s ORDER BY issue_ticket_time,id LIMIT %s;
SELECT id,order_id,issue_ticket_time FROM order_info_issue WHERE issue_ticket_time >= %s AND issue_ticket_time < %s AND (issue_ticket_time > %s OR (issue_ticket_time = %s AND id > %s)) ORDER BY issue_ticket_time,id LIMIT %s;
SELECT id,profit_reason_type FROM order_info WHERE id IN (%s);
SELECT order_id,profit_reason_type,update_time FROM risk_order_day_stage WHERE profit_reason_type IN (%s,%s) AND order_id>%s ORDER BY order_id LIMIT %s;
-- 元数据/普通计划门禁，不执行EXPLAIN ANALYZE；表名固定在源码白名单。
SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (%s);
SHOW INDEX FROM order_info_issue;
-- 以上源业务SELECT执行前由代码对实际绑定参数执行普通EXPLAIN；拒绝ALL/全索引扫描。
