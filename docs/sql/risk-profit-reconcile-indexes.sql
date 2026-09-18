-- 利润核对基础索引（用户手工执行，应用不会自动执行DDL）
-- 来源：2026-09-17用户要求增加核对筛选；已只读核验 MySQL 5.7.44 / InnoDB。
-- 当前时间字段是 VARCHAR(150)，查询要求值为 YYYY-MM-DD 或以此开头的时间文本。
-- 2026-09-17按用户最新要求：基础索引仅保留日期，不包含票数或利润汇总列。
-- 若已创建上一版 idx_reconcile_date_sum，请改用 risk-profit-reconcile-remove-metric-index-columns.sql。
-- 执行前 SHOW INDEX 检查是否已有同名或等价索引；MySQL 5.7 不支持这里的 IF NOT EXISTS。
-- 建索引会消耗I/O、CPU和额外空间，也仍有短暂元数据锁；请在低峰逐表执行。
-- 如果调度使用 DROP/CREATE 或 CREATE TABLE AS 重建表，须把索引保留到目标表建表流程。

CREATE INDEX idx_reconcile_date
ON sibebid.bi_order_issue_profit_reconcile_year (business_date)
ALGORITHM=INPLACE LOCK=NONE;

CREATE INDEX idx_reconcile_date
ON sibebid.bi_order_refund_profit_reconcile_year (business_date)
ALGORITHM=INPLACE LOCK=NONE;

CREATE INDEX idx_reconcile_date
ON sibebid.bi_order_change_profit_reconcile_year (stat_date)
ALGORITHM=INPLACE LOCK=NONE;

-- 创建后可按部署流程更新统计信息，再用 EXPLAIN 验证实际查询。
-- 不保证本年/大比例数据扫描必定走索引；不要为了强制走索引而加 FORCE INDEX。
-- 维度组合索引见 risk-profit-reconcile-filter-indexes-optional.sql，按常用筛选选1~2组即可。
