-- 执行位置：已获授权的 sibebid MySQL 5.7 实例。仅新增订单号查部门索引。
-- 不修改业务记录、金额、列定义或历史结果；首次执行DDL须按生产授权。
-- 已有任意完整order_no首列索引则跳过，避免重复添加。
SET @risk_department_order_index_exists = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA='sibebid'
      AND TABLE_NAME='bi_order_issue_profit_reconcile_year'
      AND SEQ_IN_INDEX=1 AND COLUMN_NAME='order_no' AND SUB_PART IS NULL
);
SET @risk_department_order_index_sql = IF(
    @risk_department_order_index_exists>0,
    'SELECT ''ORDER_LOOKUP_INDEX_ALREADY_EXISTS'' AS status',
    'ALTER TABLE sibebid.bi_order_issue_profit_reconcile_year ADD INDEX idx_risk_reconcile_order_no (order_no) COMMENT ''风控按内部订单号读取业务归属部门'', ALGORITHM=INPLACE, LOCK=NONE'
);
PREPARE risk_department_order_index_statement FROM @risk_department_order_index_sql;
EXECUTE risk_department_order_index_statement;
DEALLOCATE PREPARE risk_department_order_index_statement;
-- 回读：应有order_no首列、SUB_PART为NULL。无在线DDL能力时明确失败，不自动退回锁表方式。
SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,INDEX_COMMENT
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA='sibebid'
  AND TABLE_NAME='bi_order_issue_profit_reconcile_year'
  AND SEQ_IN_INDEX=1 AND COLUMN_NAME='order_no' AND SUB_PART IS NULL;
-- 普通EXPLAIN，不执行查询，不读取真实订单明细。
EXPLAIN SELECT order_no,org_cname
FROM sibebid.bi_order_issue_profit_reconcile_year
WHERE order_no IN ('SYNTH-ORDER-001')
GROUP BY order_no,org_cname LIMIT 100001;
