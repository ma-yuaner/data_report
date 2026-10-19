-- 目标进度看板补充指标目录（幂等）。
-- 这里只登记指标定义，不写入任何业务结果；实际数值由后续统一ETL写入 dws_target_metric_day。

INSERT INTO target_metric_definition (
    metric_code, metric_name, metric_version, unit_code, date_basis,
    source_system, measure_code, supported_scenes, definition, filter_description, status
) VALUES
    ('LOSS_AMOUNT', '单独亏损金额', 'V1', 'CNY', 'ISSUE_DATE', 'ERP',
     'loss_amount', 'DASHBOARD_PLATFORM,DASHBOARD_GDS,DASHBOARD_POLICY',
     '按出票日汇总出票预估利润小于0的记录之亏损金额绝对值。',
     '属于业务估算亏损，不代表财务结算；必须与航段目标使用相同有效出票范围。', 'ACTIVE'),
    ('LOSS_TICKET_COUNT', '亏损票数', 'V1', 'TICKET', 'ISSUE_DATE', 'ERP',
     'loss_ticket_count', 'DASHBOARD_PLATFORM,DASHBOARD_GDS,DASHBOARD_POLICY',
     '按出票日统计出票预估利润小于0的票数。',
     '明细源按有效票记录计数；聚合源必须汇总iss_num，不得按聚合结果行数计数。', 'ACTIVE'),
    ('LOSS_SEGMENT_COUNT', '亏损航段数', 'V1', 'SEGMENT', 'ISSUE_DATE', 'ERP',
     'loss_segment_count', 'DASHBOARD_PLATFORM,DASHBOARD_GDS,DASHBOARD_POLICY',
     '按出票日汇总出票预估利润小于0的有效承运航段数。',
     '沿用目标航段的有效出票、退废、婴儿及承运航段过滤口径。', 'ACTIVE')
ON DUPLICATE KEY UPDATE
    metric_name = VALUES(metric_name),
    unit_code = VALUES(unit_code),
    date_basis = VALUES(date_basis),
    source_system = VALUES(source_system),
    measure_code = VALUES(measure_code),
    supported_scenes = VALUES(supported_scenes),
    definition = VALUES(definition),
    filter_description = VALUES(filter_description),
    status = VALUES(status),
    updated_at = CURRENT_TIMESTAMP;
