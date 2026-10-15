-- GDS/OTA资源治理日异常通知模板 V1
-- 目标库：sibebid；依赖 smart-placement-lifecycle-notification-v2.sql 已创建通用模板与路由表。
-- 本脚本只注册可编辑模板，不绑定既有规则；通知群和路由后续均可在监控中心页面调整。

USE `sibebid`;

INSERT INTO `monitor_message_template` (
  `template_code`,`template_name`,`event_code`,`channel`,
  `title_template`,`body_template`,`field_schema_json`,`status`,
  `created_by_name`,`updated_by_name`
) VALUES (
  'RESOURCE_GOVERNANCE_DAILY_WECOM',
  'GDS/OTA资源日异常通知',
  'RESOURCE_GOVERNANCE_DAILY_ALERT',
  'WECOM',
  '🚨 资源治理日异常通知',
  '【事件编号】：{eventNo}\n【业务日期】：{businessDate}\n【资源类型】：{resourceType}\n【异常范围】：{scope}\n【查询量】：{searchRequests}\n【航段数】：{segmentCount}\n【查定比】：{queryToSegmentRatio}\n【查询成功率】：{searchSuccessRate}\n【验价成功率】：{verifySuccessRate}\n【生单成功率】：{orderSuccessRate}\n【监控规则】：{ruleCode}\n【异常事项】：{title}\n【处理要求】：请进入企业数据中台确认、观察或发起技术工单。',
  '{"allowedFields":["eventNo","businessDate","resourceType","scope","searchRequests","segmentCount","queryToSegmentRatio","searchSuccessRate","verifySuccessRate","orderSuccessRate","ruleCode","title"],"fieldLabels":{"eventNo":"事件编号","businessDate":"业务日期","resourceType":"资源类型","scope":"异常范围","searchRequests":"查询量","segmentCount":"航段数","queryToSegmentRatio":"查定比","searchSuccessRate":"查询成功率","verifySuccessRate":"验价成功率","orderSuccessRate":"生单成功率","ruleCode":"监控规则","title":"异常事项"}}',
  'ACTIVE','SYSTEM_MIGRATION','SYSTEM_MIGRATION'
)
ON DUPLICATE KEY UPDATE
  `template_name`=VALUES(`template_name`),
  `event_code`=VALUES(`event_code`),
  `channel`=VALUES(`channel`),
  `field_schema_json`=VALUES(`field_schema_json`),
  `status`='ACTIVE',
  `updated_by_name`='SYSTEM_MIGRATION',
  `updated_at`=CURRENT_TIMESTAMP;

SELECT `id`,`template_code`,`template_name`,`event_code`,`version_no`,`status`
FROM `monitor_message_template`
WHERE `template_code`='RESOURCE_GOVERNANCE_DAILY_WECOM';

