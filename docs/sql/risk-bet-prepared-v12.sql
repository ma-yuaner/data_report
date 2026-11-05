-- V12增量，MySQL绑定参数；复用RISK-ETL-005其余源证据与同日事务发布SQL。
-- 已接十类：RLA013,RLA040,RLA068,RLA047,RLA50,RLA046,RLA045,RLA069,RLA070,RLA067。
-- 历史合并RLA044不在本次范围。无新表/DDL。

-- 目标临时目录按主键游标选取全部十类；后两个参数为上一order_id、batch_size。
SELECT order_id,profit_reason_type,update_time FROM risk_order_day_stage
WHERE profit_reason_type IN (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
  AND order_id>%s ORDER BY order_id LIMIT %s;

-- 实际源逐票关联校验；参数为当前order_id、issue_id。
-- 正常非空运段不算航空段，但必须同单、存在、标记明确且不重复。
SELECT COUNT(*) AS link_count,
       COUNT(DISTINCT CASE WHEN s.airlift_flag IN (0,1) THEN s.id END) AS matched_segment_count,
       COUNT(DISTINCT CASE WHEN s.airlift_flag=1 THEN s.id END) AS segment_count
FROM order_info_issue_segment i LEFT JOIN order_info_segment s
  ON s.id=i.segment_id AND s.order_id=%s WHERE i.issue_id=%s;
-- 只有link_count=matched_segment_count且segment_count>0时才使用航空段数。
-- 批量取证用RISK-ETL-005航段原始关联查询，内存重放遵循同一条件。

-- 页面待核实/规则未接入筛选，沿用原日期去重scope和绑定顺序。
SELECT COUNT(*) AS order_count FROM bi_risk_order_day o
WHERE o.issue_date>=%s AND o.issue_date<=%s
  AND NOT EXISTS (SELECT 1 FROM bi_risk_order_day newer WHERE newer.order_id=o.order_id
                  AND newer.issue_date>o.issue_date AND newer.issue_date<=%s)
  AND o.profit_reason_type IN (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
-- 日期参数后绑定十个原因；待核实还须排除已有当前核实结果，源码按ID绑定排除。
-- 规则未接入使用同一模板NOT IN十类；不是证据不足。

-- 逐票业务判定由Decimal执行，不在SQL中四舍五入或补NULL为0：
-- order_info_issue.issue_profit >= -出票时通用配置的单票止损值（含等号）。
-- 不加佣金/预期收益，不按订单平均；一票突破即有问题。
