-- 智能投放闭环与通知模型 V2（增量脚本）
-- 目标库：sibebid；兼容 MySQL 5.7+/8.0。
-- 依赖：smart-placement-schema.sql、monitoring-center-schema.sql。
-- 本脚本只新增表和默认配置，不删除、不覆盖现有业务数据。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `sys_user_employee_binding` (
  `sys_user_id` BIGINT UNSIGNED NOT NULL COMMENT '数据中台sys_user.id',
  `employee_id` BIGINT UNSIGNED NOT NULL COMMENT 'ERP sibebd.system_user.id',
  `employee_name_snapshot` VARCHAR(100) NOT NULL COMMENT '员工姓名快照',
  `work_number_snapshot` VARCHAR(100) DEFAULT NULL COMMENT '工号快照',
  `wechat_id_snapshot` VARCHAR(100) DEFAULT NULL COMMENT '企业微信ID快照，仅用于排查；发送时读取ERP最新值',
  `mobile_snapshot` VARCHAR(32) DEFAULT NULL COMMENT '手机号快照，仅用于排查；发送时读取ERP最新值',
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/DISABLED',
  `bound_by` BIGINT UNSIGNED DEFAULT NULL COMMENT '绑定操作人sys_user.id',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`sys_user_id`),
  UNIQUE KEY `uk_user_employee_binding_employee` (`employee_id`),
  KEY `idx_user_employee_binding_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据中台账号与ERP花名册员工映射';

CREATE TABLE IF NOT EXISTS `monitor_message_template` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `template_code` VARCHAR(64) NOT NULL COMMENT '消息模板编码',
  `template_name` VARCHAR(100) NOT NULL,
  `event_code` VARCHAR(64) NOT NULL COMMENT '业务事件编码',
  `channel` VARCHAR(32) NOT NULL DEFAULT 'WECOM',
  `title_template` VARCHAR(300) NOT NULL,
  `body_template` TEXT NOT NULL COMMENT '仅允许白名单变量的文本模板',
  `field_schema_json` TEXT DEFAULT NULL COMMENT '可用变量及显示说明',
  `version_no` INT NOT NULL DEFAULT 1,
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/DISABLED',
  `created_by_id` BIGINT DEFAULT NULL,
  `created_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by_id` BIGINT DEFAULT NULL,
  `updated_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_message_template_code` (`template_code`),
  KEY `idx_monitor_message_template_event` (`event_code`, `channel`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控消息模板';

CREATE TABLE IF NOT EXISTS `monitor_notify_route` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `route_code` VARCHAR(64) NOT NULL,
  `route_name` VARCHAR(100) NOT NULL,
  `event_code` VARCHAR(64) NOT NULL,
  `channel` VARCHAR(32) NOT NULL DEFAULT 'WECOM',
  `endpoint_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '指定通知群；为空时展开全部智能投放默认群',
  `template_id` BIGINT UNSIGNED NOT NULL,
  `recipient_strategy` VARCHAR(32) NOT NULL DEFAULT 'TASK_ASSIGNEE' COMMENT 'TASK_ASSIGNEE/ATTENTION_OWNER/RULE_OWNER/NONE',
  `use_smart_default_endpoints` TINYINT(1) NOT NULL DEFAULT 0,
  `priority_no` INT NOT NULL DEFAULT 100,
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  `created_by_id` BIGINT DEFAULT NULL,
  `created_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by_id` BIGINT DEFAULT NULL,
  `updated_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_notify_route_code` (`route_code`),
  KEY `idx_monitor_notify_route_event` (`event_code`, `status`, `priority_no`),
  KEY `idx_monitor_notify_route_endpoint` (`endpoint_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='业务事件通知路由';

CREATE TABLE IF NOT EXISTS `monitor_notify_delivery_context` (
  `outbox_id` BIGINT UNSIGNED NOT NULL,
  `event_code` VARCHAR(64) NOT NULL,
  `route_id` BIGINT UNSIGNED DEFAULT NULL,
  `template_id` BIGINT UNSIGNED DEFAULT NULL,
  `template_version` INT DEFAULT NULL,
  `recipient_user_ids_json` TEXT DEFAULT NULL COMMENT '内部sys_user.id数组',
  `resolved_wecom_ids_json` TEXT DEFAULT NULL,
  `resolved_mobiles_json` TEXT DEFAULT NULL,
  `rendered_payload_json` LONGTEXT DEFAULT NULL COMMENT '实际发送内容快照',
  `resolution_warning` VARCHAR(1000) DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`outbox_id`),
  KEY `idx_monitor_delivery_event` (`event_code`, `created_at`),
  KEY `idx_monitor_delivery_route` (`route_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通知模板、动态收件人与发送结果快照';

CREATE TABLE IF NOT EXISTS `smart_placement_order_outcome` (
  `match_id` BIGINT UNSIGNED NOT NULL COMMENT 'smart_placement_order_match.id',
  `outcome_status` VARCHAR(20) NOT NULL DEFAULT 'WAITING_SYNC' COMMENT 'WAITING_SYNC/PENDING/TICKETED/CANCELLED/REFUNDED/UNKNOWN',
  `data_freshness_status` VARCHAR(20) NOT NULL DEFAULT 'MISSING' COMMENT 'FRESH/STALE/MISSING',
  `source_table` VARCHAR(128) DEFAULT NULL,
  `source_updated_at` DATETIME DEFAULT NULL,
  `ticket_no` TEXT DEFAULT NULL,
  `passenger_name` TEXT DEFAULT NULL,
  `ticket_time` DATETIME DEFAULT NULL,
  `ticket_count` BIGINT DEFAULT NULL,
  `segment_count` BIGINT DEFAULT NULL,
  `estimated_profit_cny` DECIMAL(20,8) DEFAULT NULL,
  `order_status` VARCHAR(64) DEFAULT NULL,
  `issue_status` VARCHAR(64) DEFAULT NULL,
  `smart_confirm` VARCHAR(100) DEFAULT NULL,
  `smart_participated` TINYINT(1) DEFAULT NULL,
  `smart_succeeded` TINYINT(1) DEFAULT NULL,
  `smart_used` TINYINT(1) DEFAULT NULL,
  `last_checked_at` DATETIME NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`match_id`),
  KEY `idx_smart_outcome_status` (`outcome_status`, `last_checked_at`),
  KEY `idx_smart_outcome_freshness` (`data_freshness_status`, `source_updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能收单命中后的当前订单与出票结果';

CREATE TABLE IF NOT EXISTS `smart_placement_match_attribution` (
  `match_id` BIGINT UNSIGNED NOT NULL,
  `order_identity` VARCHAR(220) NOT NULL COMMENT '标准订单归属键',
  `attribution_type` VARCHAR(16) NOT NULL COMMENT 'PRIMARY/SECONDARY',
  `primary_match_id` BIGINT UNSIGNED NOT NULL,
  `matched_policy_count` INT NOT NULL DEFAULT 1,
  `attribution_note` VARCHAR(500) DEFAULT NULL,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`match_id`),
  KEY `idx_smart_attribution_order` (`order_identity`, `attribution_type`),
  KEY `idx_smart_attribution_primary` (`primary_match_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='同一订单命中多个政策时的主次归属';

CREATE TABLE IF NOT EXISTS `smart_placement_sla_policy` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `policy_code` VARCHAR(64) NOT NULL,
  `policy_name` VARCHAR(100) NOT NULL,
  `attention_pending_minutes` INT NOT NULL DEFAULT 10 COMMENT '首次催办分钟数',
  `escalation_minutes` INT NOT NULL DEFAULT 20 COMMENT '升级分钟数',
  `repeat_reminder_minutes` INT NOT NULL DEFAULT 30 COMMENT '升级后重复催办间隔',
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_smart_sla_policy_code` (`policy_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能收单关注时效策略';

CREATE TABLE IF NOT EXISTS `smart_placement_effect_review` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `task_id` BIGINT UNSIGNED NOT NULL,
  `review_result` VARCHAR(32) NOT NULL COMMENT 'CONTINUE/ADJUST/STOP/COMPLETED',
  `review_conclusion` TEXT NOT NULL,
  `next_action` TEXT DEFAULT NULL,
  `reviewer_id` BIGINT NOT NULL,
  `reviewer_name` VARCHAR(100) NOT NULL,
  `metric_snapshot_json` LONGTEXT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_smart_effect_review_task` (`task_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能投放效果复盘记录';

INSERT INTO `smart_placement_sla_policy`
  (`policy_code`,`policy_name`,`attention_pending_minutes`,`escalation_minutes`,`repeat_reminder_minutes`,`status`)
VALUES ('SMART_ORDER_DEFAULT','智能收单默认关注时效',10,20,30,'ACTIVE')
ON DUPLICATE KEY UPDATE `policy_name`=VALUES(`policy_name`),`updated_at`=CURRENT_TIMESTAMP;

INSERT INTO `monitor_message_template`
  (`template_code`,`template_name`,`event_code`,`channel`,`title_template`,`body_template`,`field_schema_json`,`status`)
VALUES
  ('SMART_ORDER_MATCHED_WECOM','智能收单命中通知','SMART_ORDER_MATCHED','WECOM',
   '🚨 智能规则命中订单实时通知',
   '【OTA订单号】：{otaOrderNo}\n【政策员】：{policyOperators}\n【航司】：{airline}\n【平台】：{platform}\n【航线】：{route}\n【舱位】：{cabinCodes}\n【产品类型】：{productType}\n【投放差价】：{placementDiff}\n【智能类型】：{smartType}\n【预估利润】：{estimatedProfit}\n【进单时间】：{orderTime}\n【出票时间】：{ticketTime}\n【OTA最晚出票时间】：{otaLatestTicketTime}\n【可留单时间】：{holdTimeResult}\n【规则ID】：{ruleCode}\n【政策ID】：{externalPolicyId}\n【备注】：{remark}',
   '{"allowedFields":["otaOrderNo","policyOperators","airline","platform","route","cabinCodes","productType","placementDiff","smartType","estimatedProfit","orderTime","ticketTime","otaLatestTicketTime","holdTimeResult","ruleCode","externalPolicyId","remark"],"fieldLabels":{"otaOrderNo":"OTA订单号","policyOperators":"政策员","airline":"航司","platform":"平台","route":"航线","cabinCodes":"舱位","productType":"产品类型","placementDiff":"投放差价","smartType":"智能类型","estimatedProfit":"预估利润","orderTime":"进单时间","ticketTime":"出票时间","otaLatestTicketTime":"OTA最晚出票时间","holdTimeResult":"可留单时间","ruleCode":"规则ID","externalPolicyId":"政策ID","remark":"备注"}}','ACTIVE'),
  ('SMART_ATTENTION_REMINDER_WECOM','智能收单首次催办','SMART_ATTENTION_REMINDER','WECOM',
   '【智能收单催办】存在尚未关注的命中订单',
   '存在超过关注时效的智能收单命中，请进入企业数据中台查看并处理。',
   '{"allowedFields":[]}','ACTIVE'),
  ('SMART_ATTENTION_ESCALATED_WECOM','智能收单升级提醒','SMART_ATTENTION_ESCALATED','WECOM',
   '【智能收单升级】存在关注超时订单',
   '存在已升级的智能收单关注任务，请立即进入企业数据中台处理。',
   '{"allowedFields":[]}','ACTIVE'),
  ('SMART_POLICY_EXPIRED_WECOM','智能政策到期通知','SMART_POLICY_EXPIRED','WECOM',
   '【智能政策到期】监控任务已自动停止',
   '有智能投放政策到期，监控已自动停止。请进入企业数据中台查看效果并完成复盘。',
   '{"allowedFields":[]}','ACTIVE')
ON DUPLICATE KEY UPDATE
  `template_name`=VALUES(`template_name`),`event_code`=VALUES(`event_code`),
  `field_schema_json`=VALUES(`field_schema_json`),`updated_at`=CURRENT_TIMESTAMP;

INSERT INTO `monitor_notify_route`
  (`route_code`,`route_name`,`event_code`,`channel`,`endpoint_id`,`template_id`,`recipient_strategy`,`use_smart_default_endpoints`,`priority_no`,`status`)
SELECT seed.route_code,seed.route_name,seed.event_code,'WECOM',NULL,t.id,
       'TASK_ASSIGNEE',1,seed.priority_no,'ACTIVE'
FROM (
  SELECT 'SMART_ORDER_MATCHED_DEFAULT' route_code,'智能收单命中默认路由' route_name,'SMART_ORDER_MATCHED' event_code,'SMART_ORDER_MATCHED_WECOM' template_code,10 priority_no
  UNION ALL SELECT 'SMART_ATTENTION_REMINDER_DEFAULT','智能收单催办默认路由','SMART_ATTENTION_REMINDER','SMART_ATTENTION_REMINDER_WECOM',20
  UNION ALL SELECT 'SMART_ATTENTION_ESCALATED_DEFAULT','智能收单升级默认路由','SMART_ATTENTION_ESCALATED','SMART_ATTENTION_ESCALATED_WECOM',30
  UNION ALL SELECT 'SMART_POLICY_EXPIRED_DEFAULT','智能政策到期默认路由','SMART_POLICY_EXPIRED','SMART_POLICY_EXPIRED_WECOM',40
) seed
JOIN `monitor_message_template` t ON t.template_code=seed.template_code
ON DUPLICATE KEY UPDATE
  `route_name`=VALUES(`route_name`),`template_id`=VALUES(`template_id`),
  `use_smart_default_endpoints`=VALUES(`use_smart_default_endpoints`),`updated_at`=CURRENT_TIMESTAMP;

-- 数据运营经理默认可停止监控和登记效果复盘；系统管理员不依赖此角色权限。
INSERT IGNORE INTO `sys_role_permission` (`role_id`,`permission_code`)
SELECT `id`,'smart_placement.stop' FROM `sys_role` WHERE `role_code`='DATA_MANAGER';

INSERT IGNORE INTO `sys_role_permission` (`role_id`,`permission_code`)
SELECT `id`,'smart_placement.effect_review' FROM `sys_role` WHERE `role_code`='DATA_MANAGER';

-- 应用账号还需要ERP花名册只读权限（请由DBA将app_user替换成真实账号后执行）：
-- GRANT SELECT (`id`,`user_name`,`wechat_id`,`mobilephone`,`cname`,`work_number`,`status`,`enabled`,`start_time`,`end_time`,`update_time`)
-- ON `sibebd`.`system_user` TO 'app_user'@'%';
