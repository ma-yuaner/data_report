-- 用户手工执行：将已建的旧覆盖索引替换为纯日期索引，应用不会自动执行。
-- 来源：2026-09-17用户明确要求移除索引中的 ticket_num / estimated_profit_cny。
-- 同日只读核验：以下三表确实存在 idx_reconcile_date_sum，列序为时间、票数、利润。
-- 只替换索引，不删除表字段，不删除票数/利润数据，也不改变 SUM 指标查询。
-- 低峰逐表执行；仍有索引重建成本和短暂元数据锁。
-- 执行前确认旧索引存在且新索引 idx_reconcile_date 不存在；执行后不要重复运行。
-- 如果旧索引已自行修改，请先 SHOW INDEX 检查，不要直接执行此迁移。
-- 语法依据：https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/alter-table.html

ALTER TABLE sibebid.bi_order_issue_profit_reconcile_year
  DROP INDEX idx_reconcile_date_sum,
  ADD INDEX idx_reconcile_date (business_date),
  ALGORITHM=INPLACE, LOCK=NONE;

ALTER TABLE sibebid.bi_order_refund_profit_reconcile_year
  DROP INDEX idx_reconcile_date_sum,
  ADD INDEX idx_reconcile_date (business_date),
  ALGORITHM=INPLACE, LOCK=NONE;

ALTER TABLE sibebid.bi_order_change_profit_reconcile_year
  DROP INDEX idx_reconcile_date_sum,
  ADD INDEX idx_reconcile_date (stat_date),
  ALGORITHM=INPLACE, LOCK=NONE;
