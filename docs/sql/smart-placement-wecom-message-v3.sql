-- 智能投放企业微信明细通知 V3（增量升级）
-- 目标库：sibebid；先执行本脚本，再发布V3 ETL与通知发送器。
-- Webhook属于敏感信息，请在“监控中心 → 智能通知”页面录入，不要写入本文件。

USE `sibebid`;

DROP PROCEDURE IF EXISTS `sp_upgrade_smart_wecom_v3`;
DELIMITER $$
CREATE PROCEDURE `sp_upgrade_smart_wecom_v3`()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='policy_operator') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `policy_operator` VARCHAR(100) NULL COMMENT '政策组长' AFTER `estimated_profit_cny`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='policy_operator_group_name') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `policy_operator_group_name` VARCHAR(100) NULL COMMENT '政策组员' AFTER `policy_operator`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='policy_name') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `policy_name` VARCHAR(200) NULL COMMENT '政策员展示名称' AFTER `policy_operator_group_name`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='ticket_no') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `ticket_no` VARCHAR(200) NULL COMMENT '出票票号' AFTER `policy_name`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='ticket_time') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `ticket_time` DATETIME NULL COMMENT '出票时间' AFTER `ticket_no`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='ota_latest_ticket_time') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `ota_latest_ticket_time` DATETIME NULL COMMENT 'OTA最晚出票时间' AFTER `ticket_time`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='smart_type') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `smart_type` VARCHAR(100) NULL COMMENT '智能类型' AFTER `ota_latest_ticket_time`;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature' AND COLUMN_NAME='placement_diff_cny') THEN
    ALTER TABLE `rt_order_monitor_feature` ADD COLUMN `placement_diff_cny` DECIMAL(20,8) NULL COMMENT '投放/销售差价' AFTER `smart_type`;
  END IF;
END$$
DELIMITER ;

CALL `sp_upgrade_smart_wecom_v3`();
DROP PROCEDURE IF EXISTS `sp_upgrade_smart_wecom_v3`;

INSERT IGNORE INTO `monitor_message_template` (
  `template_code`,`template_name`,`event_code`,`channel`,`title_template`,
  `body_template`,`field_schema_json`,`version_no`,`status`,
  `created_by_name`,`updated_by_name`
) VALUES (
  'SMART_ORDER_MATCHED_WECOM','智能收单命中通知','SMART_ORDER_MATCHED','WECOM',
  '🚨 智能规则命中订单实时通知',
  '【OTA订单号】：{otaOrderNo}\n【政策员】：{policyOperators}\n【航司】：{airline}\n【平台】：{platform}\n【航线】：{route}\n【舱位】：{cabinCodes}\n【产品类型】：{productType}\n【投放差价】：{placementDiff}\n【智能类型】：{smartType}\n【预估利润】：{estimatedProfit}\n【进单时间】：{orderTime}\n【出票时间】：{ticketTime}\n【OTA最晚出票时间】：{otaLatestTicketTime}\n【可留单时间】：{holdTimeResult}\n【规则ID】：{ruleCode}\n【政策ID】：{externalPolicyId}\n【备注】：{remark}',
  '{"allowedFields":["otaOrderNo","policyOperators","airline","platform","route","cabinCodes","productType","placementDiff","smartType","estimatedProfit","orderTime","ticketTime","otaLatestTicketTime","holdTimeResult","ruleCode","externalPolicyId","remark"],"fieldLabels":{"otaOrderNo":"OTA订单号","policyOperators":"政策员","airline":"航司","platform":"平台","route":"航线","cabinCodes":"舱位","productType":"产品类型","placementDiff":"投放差价","smartType":"智能类型","estimatedProfit":"预估利润","orderTime":"进单时间","ticketTime":"出票时间","otaLatestTicketTime":"OTA最晚出票时间","holdTimeResult":"可留单时间","ruleCode":"规则ID","externalPolicyId":"政策ID","remark":"备注"}}',
  1,'ACTIVE','SYSTEM_MIGRATION','SYSTEM_MIGRATION'
);

UPDATE `monitor_message_template`
SET `template_name`='智能收单命中通知',
    `event_code`='SMART_ORDER_MATCHED',
    `channel`='WECOM',
    `title_template`='🚨 智能规则命中订单实时通知',
    `body_template`='【OTA订单号】：{otaOrderNo}\n【政策员】：{policyOperators}\n【航司】：{airline}\n【平台】：{platform}\n【航线】：{route}\n【舱位】：{cabinCodes}\n【产品类型】：{productType}\n【投放差价】：{placementDiff}\n【智能类型】：{smartType}\n【预估利润】：{estimatedProfit}\n【进单时间】：{orderTime}\n【出票时间】：{ticketTime}\n【OTA最晚出票时间】：{otaLatestTicketTime}\n【可留单时间】：{holdTimeResult}\n【规则ID】：{ruleCode}\n【政策ID】：{externalPolicyId}\n【备注】：{remark}',
    `field_schema_json`='{"allowedFields":["otaOrderNo","policyOperators","airline","platform","route","cabinCodes","productType","placementDiff","smartType","estimatedProfit","orderTime","ticketTime","otaLatestTicketTime","holdTimeResult","ruleCode","externalPolicyId","remark"],"fieldLabels":{"otaOrderNo":"OTA订单号","policyOperators":"政策员","airline":"航司","platform":"平台","route":"航线","cabinCodes":"舱位","productType":"产品类型","placementDiff":"投放差价","smartType":"智能类型","estimatedProfit":"预估利润","orderTime":"进单时间","ticketTime":"出票时间","otaLatestTicketTime":"OTA最晚出票时间","holdTimeResult":"可留单时间","ruleCode":"规则ID","externalPolicyId":"政策ID","remark":"备注"}}',
    `version_no`=`version_no`+1,
    `status`='ACTIVE',
    `updated_by_name`='SYSTEM_MIGRATION',
    `updated_at`=CURRENT_TIMESTAMP
WHERE `template_code`='SMART_ORDER_MATCHED_WECOM'
  AND (`title_template`<>'🚨 智能规则命中订单实时通知'
       OR `body_template` NOT LIKE '%{otaOrderNo}%'
       OR `field_schema_json` NOT LIKE '%"externalPolicyId"%');

INSERT INTO `monitor_notify_route` (
  `route_code`,`route_name`,`event_code`,`channel`,`endpoint_id`,`template_id`,
  `recipient_strategy`,`use_smart_default_endpoints`,`priority_no`,`status`,
  `created_by_name`,`updated_by_name`
)
SELECT 'SMART_ORDER_MATCHED_DEFAULT','智能收单命中默认路由','SMART_ORDER_MATCHED','WECOM',
       NULL,t.id,'TASK_ASSIGNEE',1,10,'ACTIVE','SYSTEM_MIGRATION','SYSTEM_MIGRATION'
FROM `monitor_message_template` t
WHERE t.template_code='SMART_ORDER_MATCHED_WECOM'
ON DUPLICATE KEY UPDATE
  `template_id`=VALUES(`template_id`),
  `use_smart_default_endpoints`=1,
  `status`='ACTIVE',
  `updated_by_name`='SYSTEM_MIGRATION',
  `updated_at`=CURRENT_TIMESTAMP;

-- 验证：应返回8个新增特征字段、1个启用模板和1个启用默认路由。
SELECT COUNT(*) AS feature_column_count
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='rt_order_monitor_feature'
  AND COLUMN_NAME IN ('policy_operator','policy_operator_group_name','policy_name','ticket_no',
                      'ticket_time','ota_latest_ticket_time','smart_type','placement_diff_cny');

SELECT `template_code`,`version_no`,`status`
FROM `monitor_message_template`
WHERE `template_code`='SMART_ORDER_MATCHED_WECOM';

SELECT `route_code`,`event_code`,`use_smart_default_endpoints`,`status`
FROM `monitor_notify_route`
WHERE `route_code`='SMART_ORDER_MATCHED_DEFAULT';
