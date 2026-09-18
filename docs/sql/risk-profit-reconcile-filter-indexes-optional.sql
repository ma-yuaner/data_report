-- 可选：高频等值维度 + 日期范围索引。
-- 不要整份全部创建；先建基础日期索引，再按 EXPLAIN / 慢查询选择常用维度的对应三条。
-- 五组分别对应 OTA平台、站点、业务部门、航司、供应商；应用支持这些维度组合筛选。
-- 当前维度/日期均为 VARCHAR(150)。日期用10字符前缀，兼容5.7较小索引长度配置。
-- WHERE 仍对完整日期字段比较，前缀索引不替代最终过滤，也不是完整覆盖索引。
-- 原值要求规范的 YYYY-MM-DD（可带后续时间），不得只存“1月11日”/不补零的日期。
-- 如日期以后改为 DATE/DATETIME，需移除索引定义中的 (10)。
-- 执行前 SHOW INDEX 排除重复索引；低峰逐表执行，索引会增加同步写入与存储成本。
-- 文档依据：https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/multiple-column-indexes.html
-- 前缀语法：https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/create-index.html

-- 1. OTA平台 + 日期
CREATE INDEX idx_reconcile_platform_date
ON sibebid.bi_order_issue_profit_reconcile_year (ota_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_platform_date
ON sibebid.bi_order_refund_profit_reconcile_year (ota_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_platform_date
ON sibebid.bi_order_change_profit_reconcile_year (ota_cname, stat_date(10))
ALGORITHM=INPLACE LOCK=NONE;

-- 2. 站点 + 日期（不要求同时选择平台）
CREATE INDEX idx_reconcile_site_date
ON sibebid.bi_order_issue_profit_reconcile_year (ota_site_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_site_date
ON sibebid.bi_order_refund_profit_reconcile_year (ota_site_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_site_date
ON sibebid.bi_order_change_profit_reconcile_year (ota_site_cname, stat_date(10))
ALGORITHM=INPLACE LOCK=NONE;

-- 3. 业务部门 + 日期
CREATE INDEX idx_reconcile_dept_date
ON sibebid.bi_order_issue_profit_reconcile_year (org_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_dept_date
ON sibebid.bi_order_refund_profit_reconcile_year (org_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_dept_date
ON sibebid.bi_order_change_profit_reconcile_year (org_cname, stat_date(10))
ALGORITHM=INPLACE LOCK=NONE;

-- 4. 航司 + 日期
CREATE INDEX idx_reconcile_airline_date
ON sibebid.bi_order_issue_profit_reconcile_year (marketing_airline, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_airline_date
ON sibebid.bi_order_refund_profit_reconcile_year (marketing_airline, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_airline_date
ON sibebid.bi_order_change_profit_reconcile_year (marketing_airline, stat_date(10))
ALGORITHM=INPLACE LOCK=NONE;

-- 5. 供应商 + 日期
CREATE INDEX idx_reconcile_supplier_date
ON sibebid.bi_order_issue_profit_reconcile_year (supplier_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_supplier_date
ON sibebid.bi_order_refund_profit_reconcile_year (supplier_cname, business_date(10))
ALGORITHM=INPLACE LOCK=NONE;
CREATE INDEX idx_reconcile_supplier_date
ON sibebid.bi_order_change_profit_reconcile_year (supplier_cname, stat_date(10))
ALGORITHM=INPLACE LOCK=NONE;

-- 可复制以下只读示例验证“部门 + 时间”查询计划：
-- EXPLAIN SELECT SUM(ticket_num), SUM(estimated_profit_cny)
-- FROM sibebid.bi_order_issue_profit_reconcile_year
-- WHERE business_date >= '2026-08-01' AND business_date < '2026-09-01'
--   AND org_cname = '机票业务1部' AND estimated_profit_cny < 0;
-- 看 key / type / rows；同样方法检查退票和改签，改签时间字段为 stat_date。
