-- 只读核验，不代表本次已经执行；目标sibebid。期望2表、30列全部带中文注释。
SELECT TABLE_NAME,ENGINE,TABLE_COLLATION,TABLE_COMMENT FROM information_schema.TABLES
WHERE TABLE_SCHEMA='sibebid' AND TABLE_NAME IN ('bi_risk_analytics_snapshot','bi_risk_analytics_bucket');
SELECT TABLE_NAME,ORDINAL_POSITION,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT
FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='sibebid'
AND TABLE_NAME IN ('bi_risk_analytics_snapshot','bi_risk_analytics_bucket') ORDER BY TABLE_NAME,ORDINAL_POSITION;
SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA='sibebid' AND TABLE_NAME IN ('bi_risk_analytics_snapshot','bi_risk_analytics_bucket') ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;
-- 发布和排队状态。NULL不是0，错误保留旧快照；核对时不读取逐单敏感信息。
SELECT end_date,schema_version,snapshot_id,source_cutoff,generated_at,checked_at,request_generation,processed_generation,retry_after,last_error_code,order_count
FROM sibebid.bi_risk_analytics_snapshot ORDER BY end_date DESC LIMIT 32;
SELECT end_date,COUNT(DISTINCT snapshot_id) AS generations,COUNT(*) AS buckets FROM sibebid.bi_risk_analytics_bucket GROUP BY end_date;
