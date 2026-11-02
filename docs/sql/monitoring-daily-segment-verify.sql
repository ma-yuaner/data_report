-- 携程每日总航段核对（MySQL 5.7+/8.0，在ERP连接中运行）
-- 仅查询业务表；SET只设置当前会话变量，不创建表、不修改数据、不发通知。
-- 默认最近7天，含今天；今天只统计至 @as_of，其余日期统计完整出票日。
-- 注意：历史结果使用当前订单/退改状态重算，不是当时提醒时的历史快照。
-- 与执行器相同：COUNT(DISTINCT 出票ID,航段ID)，不乘人数，不使用trip_count。
-- 任一业务线映射未完整匹配时，“完整业务线航段”返回NULL；已匹配站点航段仅供核对。

SET SESSION time_zone = '+08:00';
SET @as_of = NOW();
SET @days = 7; -- 支持1—31天
SET @start_date = DATE_SUB(DATE(@as_of), INTERVAL (@days - 1) DAY);

-- 结果1：先核对六个预期站点，每站必须恰好对应一条有效编码。
SELECT
    e.business_line AS `业务线`,
    e.site_name AS `预期站点`,
    COUNT(s.ota_site_code) AS `匹配记录数`,
    GROUP_CONCAT(s.ota_site_code ORDER BY s.ota_site_code SEPARATOR ',') AS `站点编码`,
    CASE WHEN COUNT(s.ota_site_code) = 1
              AND COUNT(DISTINCT NULLIF(s.ota_site_code, '')) = 1
         THEN '已匹配' ELSE '缺失或不唯一' END AS `映射状态`
FROM (
    SELECT '乐游1部' AS business_line, '乐游携程一部' AS site_name
    UNION ALL SELECT '乐游1部', '乐游携程一部公布'
    UNION ALL SELECT '乐游1部', '乐游携程一部特惠'
    UNION ALL SELECT '香港1部', '香港携程一部'
    UNION ALL SELECT '香港1部', '香港携程公布'
    UNION ALL SELECT '香港1部', '香港携程一部特惠'
) e
LEFT JOIN sibe_ota_site s
  ON s.ota_code = 'CTRIP' AND s.ota_site_cname = e.site_name
GROUP BY e.business_line, e.site_name
ORDER BY e.business_line, e.site_name;

-- 结果2：每天两条业务线；无有效出票为0，映射不完整的完整总量为NULL。
-- 10秒查询预算；如果超时，应缩短@days并检查索引，不取消日期范围扫描全表。
SELECT /*+ MAX_EXECUTION_TIME(10000) */
    calendar.business_date AS `出票日期`,
    business_groups.business_line AS `业务线`,
    COALESCE(mapping.site_count, 0) AS `已匹配站点数`,
    3 AS `应匹配站点数`,
    CASE WHEN mapping.site_count = 3 AND mapping.mapping_rows = 3 AND mapping.code_count = 3
         THEN '完整' ELSE '映射不完整或不唯一' END AS `数据状态`,
    COALESCE(sales.segment_total, 0) AS `已匹配站点航段`,
    CASE WHEN mapping.site_count = 3 AND mapping.mapping_rows = 3 AND mapping.code_count = 3
         THEN COALESCE(sales.segment_total, 0) ELSE NULL END AS `完整业务线航段`,
    business_groups.threshold_value AS `提醒阈值`,
    CASE WHEN mapping.site_count = 3 AND mapping.mapping_rows = 3 AND mapping.code_count = 3
         THEN CASE WHEN COALESCE(sales.segment_total, 0) >= business_groups.threshold_value
                   THEN '达到提醒值' ELSE '未达到' END
         ELSE '不判定，先补映射' END AS `阈值判断`,
    @as_of AS `本次核对截至时间`
FROM (
    SELECT DATE_ADD(@start_date, INTERVAL (ones.n + tens.n * 10) DAY) AS business_date
    FROM (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
          UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) ones
    CROSS JOIN (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3) tens
    WHERE @days BETWEEN 1 AND 31 AND ones.n + tens.n * 10 < @days
) calendar
CROSS JOIN (
    SELECT '乐游1部' AS business_line, 2500 AS threshold_value
    UNION ALL SELECT '香港1部', 5500
) business_groups
LEFT JOIN (
    SELECT
        CASE WHEN ota_site_cname IN ('乐游携程一部','乐游携程一部公布','乐游携程一部特惠')
             THEN '乐游1部' ELSE '香港1部' END AS business_line,
        COUNT(DISTINCT ota_site_cname) AS site_count,
        COUNT(*) AS mapping_rows,
        COUNT(DISTINCT NULLIF(ota_site_code, '')) AS code_count
    FROM sibe_ota_site
    WHERE ota_code = 'CTRIP'
      AND ota_site_cname IN ('乐游携程一部','乐游携程一部公布','乐游携程一部特惠',
                            '香港携程一部','香港携程公布','香港携程一部特惠')
    GROUP BY business_line
) mapping ON mapping.business_line = business_groups.business_line
LEFT JOIN (
    SELECT STRAIGHT_JOIN
        DATE(oii.issue_ticket_time) AS business_date,
        CASE WHEN sos.ota_site_cname IN ('乐游携程一部','乐游携程一部公布','乐游携程一部特惠')
             THEN '乐游1部' ELSE '香港1部' END AS business_line,
        COUNT(DISTINCT oii.id, os.id) AS segment_total
    FROM order_info_issue oii
    JOIN order_info oi ON oi.id = oii.order_id
    JOIN order_info_issue_segment ois ON ois.issue_id = oii.id
    JOIN order_info_segment os ON os.id = ois.segment_id AND os.order_id = oi.id
    JOIN sibe_ota_site sos ON sos.ota_code = oi.ota_code AND sos.ota_site_code = oi.ota_site_code
    WHERE oii.issue_ticket_time >= @start_date
      AND oii.issue_ticket_time < @as_of
      AND oi.ota_code = 'CTRIP'
      AND sos.ota_site_cname IN ('乐游携程一部','乐游携程一部公布','乐游携程一部特惠',
                               '香港携程一部','香港携程公布','香港携程一部特惠')
      AND oi.order_status = 'TICKETED'
      AND oii.refund_issue_flag = 0
      AND oii.refund_flag <> 3
      AND os.airlift_flag = 1
    GROUP BY DATE(oii.issue_ticket_time), business_line
) sales ON sales.business_date = calendar.business_date AND sales.business_line = business_groups.business_line
ORDER BY calendar.business_date DESC, business_groups.business_line;
