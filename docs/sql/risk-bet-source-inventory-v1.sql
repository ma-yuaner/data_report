-- 只读元数据与原因覆盖盘点；不是对赌亏损判定规则，不写ERP。
-- MySQL驱动绑定参数；不直接整文件执行。
SELECT det_code, det_cname
FROM system_com_type_det WHERE parent_code = %s;
-- 参数：PRODUCT_PROFIT_REASON_TYPE。八类当前编码：
-- K位 RLA068 / NDC对赌 RLA047 / 国内行程 RLA50 / 辅营 RLA046
-- 退改 RLA045 / 私有 RLA069 / 青年票 RLA070 / 降舱 RLA067
-- RLA044为历史“降舱/K位”合并原因，不擅自归入上述独立原因。

SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND (TABLE_NAME LIKE %s OR TABLE_COMMENT LIKE %s);
-- 参数：%bet%、%对赌%。没有匹配表不表示其他业务表没有对赌证据。

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_COMMENT FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (TABLE_NAME IN ('order_info','order_info_issue','order_info_segment') OR COLUMN_COMMENT LIKE %s);
-- 参数：%对赌%。只证明字段定义，不证明选因成立。

-- 复用目录ETL日期索引游标；每页执行EXPLAIN并要求日期索引安全。
SELECT id, order_id, issue_ticket_time FROM order_info_issue
WHERE issue_ticket_time >= %s AND issue_ticket_time < %s
ORDER BY issue_ticket_time, id LIMIT %s;
-- 参数：Asia/Shanghai当日零点、次日零点、500。
SELECT id, order_id, issue_ticket_time FROM order_info_issue
WHERE issue_ticket_time >= %s AND issue_ticket_time < %s
  AND (issue_ticket_time > %s OR (issue_ticket_time = %s AND id > %s))
ORDER BY issue_ticket_time, id LIMIT %s;
-- 续页参数：起点、终点、上一页末时间、上一页末时间、上一页末id、500。

SELECT id, profit_reason_type FROM order_info WHERE id IN ({marks});
-- marks由本页去重order_id数量生成%s，不接收客户端SQL。
-- 应用按当前八类编码过滤、每日按order_id去重；跨日不合并成全局唯一订单数。
