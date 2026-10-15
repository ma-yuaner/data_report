-- GDS/OTA资源治理部署验收脚本（只读，不修改任何业务数据）
-- 目标库：sibebid

USE `sibebid`;

-- 1. 必需表。所有结果都应为EXISTS。
SELECT required.table_name,
       IF(actual.table_name IS NULL,'MISSING','EXISTS') AS check_status
FROM (
  SELECT 'bi_ota_gds_request_day' table_name
  UNION ALL SELECT 'monitor_rule_template'
  UNION ALL SELECT 'monitor_rule_template_field'
  UNION ALL SELECT 'monitor_rule'
  UNION ALL SELECT 'monitor_rule_version'
  UNION ALL SELECT 'monitor_rule_condition'
  UNION ALL SELECT 'monitor_rule_operation_log'
  UNION ALL SELECT 'monitor_alert_event'
  UNION ALL SELECT 'monitor_event_operation_log'
  UNION ALL SELECT 'monitor_event_lifecycle_policy'
  UNION ALL SELECT 'monitor_resource_action_order'
  UNION ALL SELECT 'monitor_resource_action_operation_log'
  UNION ALL SELECT 'monitor_notify_outbox'
  UNION ALL SELECT 'monitor_notify_endpoint'
  UNION ALL SELECT 'monitor_rule_run_stat'
  UNION ALL SELECT 'monitor_run_log'
) required
LEFT JOIN information_schema.TABLES actual
  ON actual.TABLE_SCHEMA=DATABASE() AND actual.TABLE_NAME=required.table_name
ORDER BY required.table_name;

-- 2. 日事实表必需字段。所有结果都应为EXISTS。
SELECT required.column_name,
       IF(actual.column_name IS NULL,'MISSING','EXISTS') AS check_status,
       actual.column_type
FROM (
  SELECT 'operator_date' column_name
  UNION ALL SELECT 'data_source'
  UNION ALL SELECT 'ota_code'
  UNION ALL SELECT 'ota_site_code'
  UNION ALL SELECT 'gds_code'
  UNION ALL SELECT 'pcc_code'
  UNION ALL SELECT 'source_api_group'
  UNION ALL SELECT 'search_request_count_all'
  UNION ALL SELECT 'search_request_success'
  UNION ALL SELECT 'verify_request_count_all'
  UNION ALL SELECT 'verify_request_success'
  UNION ALL SELECT 'order_request_count_all'
  UNION ALL SELECT 'order_request_success'
  UNION ALL SELECT 'seg_num'
) required
LEFT JOIN information_schema.COLUMNS actual
  ON actual.TABLE_SCHEMA=DATABASE()
 AND actual.TABLE_NAME='bi_ota_gds_request_day'
 AND actual.COLUMN_NAME=required.column_name
ORDER BY required.column_name;

-- 3. 规则模板与正式查定比字段。
SELECT t.template_code,t.template_name,t.status,
       SUM(f.field_code='query_to_segment_ratio' AND f.status='ACTIVE') AS segment_ratio_field_count,
       SUM(f.field_code='analysis_grain' AND f.status='ACTIVE') AS analysis_grain_field_count,
       SUM(f.field_code='query_to_pnr_ratio' AND f.status='ACTIVE') AS legacy_ratio_field_count
FROM monitor_rule_template t
LEFT JOIN monitor_rule_template_field f ON f.template_id=t.id
WHERE t.template_code IN ('GDS_QUERY_RATIO_DAILY','OTA_SUCCESS_RATE_DAILY')
GROUP BY t.id,t.template_code,t.template_name,t.status
ORDER BY t.template_code;

-- 4. 生命周期与阶梯处置策略。RESOURCE_GOVERNANCE应返回P0/P1/P2三行。
SELECT business_type,severity,initial_due_minutes,escalation_intervals_json,
       action_durations_json,permanent_after_count,max_observe_hours,status
FROM monitor_event_lifecycle_policy
WHERE business_type='RESOURCE_GOVERNANCE'
ORDER BY severity;

-- 5. 当前规则、事件与技术工单规模。
SELECT status,COUNT(1) rule_count
FROM monitor_rule
WHERE template_code IN ('GDS_QUERY_RATIO_DAILY','OTA_SUCCESS_RATE_DAILY')
GROUP BY status;

SELECT event_status,COUNT(1) event_count
FROM monitor_alert_event
WHERE business_type='RESOURCE_GOVERNANCE'
GROUP BY event_status;

SELECT action_status,COUNT(1) action_order_count
FROM monitor_resource_action_order
GROUP BY action_status;

-- 6. 权限。技术角色至少需要同时拥有view与manage。
SELECT r.id role_id,r.role_name,p.permission_code
FROM sys_role r
JOIN sys_role_permission p ON p.role_id=r.id
WHERE p.permission_code IN ('monitor.action.view','monitor.action.manage')
ORDER BY r.id,p.permission_code;

-- 7. 最近调度。RESOURCE_DAILY和RESOURCE_LIFECYCLE应持续出现SUCCESS。
SELECT job_type,status,source_code,rows_read,rows_written,rules_checked,
       events_created,started_at,finished_at,error_message
FROM monitor_run_log
WHERE job_type IN ('RESOURCE_DAILY','RESOURCE_LIFECYCLE','NOTIFY')
ORDER BY id DESC
LIMIT 30;

-- 8. 数据完整性问题。正常情况下以下三组计数都应为0。
SELECT 'event_action_order_missing' issue_type,COUNT(1) issue_count
FROM monitor_alert_event e
LEFT JOIN monitor_resource_action_order a ON a.id=e.action_order_id
WHERE e.business_type='RESOURCE_GOVERNANCE'
  AND e.action_order_id IS NOT NULL AND a.id IS NULL
UNION ALL
SELECT 'action_event_missing',COUNT(1)
FROM monitor_resource_action_order a
LEFT JOIN monitor_alert_event e ON e.id=a.event_id
WHERE e.id IS NULL
UNION ALL
SELECT 'legacy_query_to_pnr_condition',COUNT(1)
FROM monitor_rule_condition c
JOIN monitor_rule_version v ON v.id=c.rule_version_id
JOIN monitor_rule r ON r.id=v.rule_id
WHERE r.template_code='GDS_QUERY_RATIO_DAILY'
  AND c.field_code='query_to_pnr_ratio';
