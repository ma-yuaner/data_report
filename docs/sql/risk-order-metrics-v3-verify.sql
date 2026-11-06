-- 风控V3部署后只读核验。不建表、不改数据；先执行risk-order-metrics-v3.sql。
USE sibebid;
SELECT DATABASE() AS current_database;

-- 预期2张新表、InnoDB，并有中文表注释。
SELECT TABLE_NAME,ENGINE,TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('bi_risk_order_metric_day','bi_risk_order_metric_day_ready')
ORDER BY TABLE_NAME;

-- 预期11列；利润decimal(28,4)，时间datetime(6)，利润/段数可NULL，每列中文含义可回读。
SELECT TABLE_NAME,ORDINAL_POSITION,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('bi_risk_order_metric_day','bi_risk_order_metric_day_ready')
ORDER BY TABLE_NAME,ORDINAL_POSITION;

-- 核对联合主键和利润排序索引；已有同名表时CREATE IF NOT EXISTS不会修正不兼容结构。
SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('bi_risk_order_metric_day','bi_risk_order_metric_day_ready')
ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;

-- 新指标ETL的部门映射前置：至少存在一个以order_no为首列的索引。
SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='bi_order_issue_profit_reconcile_year'
 AND SEQ_IN_INDEX=1 AND COLUMN_NAME='order_no';

-- 基础前置检查：结果均应为ready；missing仅表示缺表，存在不代表列/索引/数据版本正确。
SELECT expected.table_name,CASE WHEN actual.TABLE_NAME IS NULL THEN 'missing' ELSE 'ready' END AS table_status
FROM (
 SELECT 'bi_risk_order_day' AS table_name UNION ALL SELECT 'bi_risk_sync_day'
 UNION ALL SELECT 'bi_risk_reason_dict' UNION ALL SELECT 'bi_risk_prepared_order'
 UNION ALL SELECT 'bi_risk_prepared_day' UNION ALL SELECT 'bi_risk_prepared_order_history'
 UNION ALL SELECT 'bi_risk_followup_cases' UNION ALL SELECT 'bi_risk_order_reviews'
 UNION ALL SELECT 'bi_risk_followup_events' UNION ALL SELECT 'bi_risk_followup_requests'
 UNION ALL SELECT 'bi_risk_review_policies' UNION ALL SELECT 'bi_risk_config_evidence'
 UNION ALL SELECT 'bi_risk_config_observations' UNION ALL SELECT 'bi_risk_auto_jobs'
 UNION ALL SELECT 'bi_risk_auto_results' UNION ALL SELECT 'bi_risk_auto_samples'
 UNION ALL SELECT 'bi_order_issue_profit_reconcile_year'
) expected
LEFT JOIN information_schema.TABLES actual ON actual.TABLE_SCHEMA=DATABASE() AND actual.TABLE_NAME=expected.table_name
ORDER BY expected.table_name;
