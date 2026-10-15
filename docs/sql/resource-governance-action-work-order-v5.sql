-- GDS/OTA资源治理技术执行工单闭环 V5
-- 目标库：sibebid；执行前需完成resource-governance-event-lifecycle-v4.sql。
-- 可重复执行。该表只记录控制指令与技术回执，不直接修改生产交易系统。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `monitor_resource_action_order` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `action_no` VARCHAR(40) NOT NULL COMMENT '技术工单编号',
  `event_id` BIGINT UNSIGNED NOT NULL COMMENT '来源异常事件ID',
  `rule_id` BIGINT UNSIGNED NOT NULL COMMENT '来源规则ID',
  `rule_code` VARCHAR(64) NOT NULL COMMENT '来源规则编码快照',
  `resource_type` VARCHAR(16) NOT NULL COMMENT 'GDS/OTA',
  `target_key` VARCHAR(200) NOT NULL COMMENT '资源对象稳定键',
  `target_snapshot_json` LONGTEXT NULL COMMENT '创建时资源范围及指标快照',
  `action_type` VARCHAR(32) NOT NULL COMMENT 'RATE_LIMIT/DISABLE/EXTEND_DISABLE/RESTORE',
  `occurrence_no` INT NOT NULL DEFAULT 1 COMMENT '同一资源历史处置次数',
  `permanent_flag` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1长期关闭，0临时处置',
  `request_note` VARCHAR(1000) NOT NULL COMMENT '数据部执行要求',
  `requested_by_id` BIGINT UNSIGNED NOT NULL,
  `requested_by_name` VARCHAR(100) NOT NULL,
  `assignee_user_id` BIGINT UNSIGNED NOT NULL COMMENT '技术执行账号',
  `assignee_user_name` VARCHAR(100) NOT NULL COMMENT '技术执行人快照',
  `action_status` VARCHAR(32) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/ACCEPTED/EXECUTING/SUCCEEDED/FAILED/CANCELLED/RECOVERY_PENDING/RECOVERED',
  `planned_start_at` DATETIME NOT NULL COMMENT '计划执行时间',
  `planned_end_at` DATETIME NULL COMMENT '临时控制计划结束时间；长期关闭为空',
  `accepted_at` DATETIME NULL,
  `executed_at` DATETIME NULL,
  `recovered_at` DATETIME NULL,
  `execution_reference` VARCHAR(200) NULL COMMENT '技术系统回执号或变更单号',
  `execution_note` VARCHAR(1000) NULL COMMENT '技术执行结果',
  `failure_reason` VARCHAR(1000) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_action_no` (`action_no`),
  KEY `idx_monitor_action_event` (`event_id`,`created_at`),
  KEY `idx_monitor_action_assignee` (`assignee_user_id`,`action_status`,`planned_start_at`),
  KEY `idx_monitor_action_recovery` (`action_status`,`planned_end_at`),
  KEY `idx_monitor_action_target` (`resource_type`,`target_key`,`action_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资源治理技术限流下线恢复工单';

CREATE TABLE IF NOT EXISTS `monitor_resource_action_operation_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `action_order_id` BIGINT UNSIGNED NOT NULL,
  `action_code` VARCHAR(32) NOT NULL COMMENT 'CREATE/ACCEPT/START/SUCCESS/FAIL/CANCEL/RECOVERY_DUE/RECOVER',
  `from_status` VARCHAR(32) NULL,
  `to_status` VARCHAR(32) NOT NULL,
  `operator_id` BIGINT UNSIGNED NULL,
  `operator_name` VARCHAR(100) NOT NULL,
  `operation_note` VARCHAR(1000) NULL,
  `operation_detail_json` LONGTEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_monitor_action_log` (`action_order_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资源治理技术工单审计日志';

SET @db = DATABASE();

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='action_order_id'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `action_order_id` BIGINT UNSIGNED NULL COMMENT ''当前关联技术工单ID'' AFTER `resolution_code`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND INDEX_NAME='idx_monitor_event_action_order'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD KEY `idx_monitor_event_action_order` (`action_order_id`)'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_event_lifecycle_policy' AND COLUMN_NAME='action_durations_json'),
  'SELECT 1',
  'ALTER TABLE `monitor_event_lifecycle_policy` ADD COLUMN `action_durations_json` VARCHAR(500) NOT NULL DEFAULT ''[60,240,1440]'' COMMENT ''各次临时控制时长分钟JSON'' AFTER `escalation_intervals_json`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_event_lifecycle_policy' AND COLUMN_NAME='permanent_after_count'),
  'SELECT 1',
  'ALTER TABLE `monitor_event_lifecycle_policy` ADD COLUMN `permanent_after_count` INT NOT NULL DEFAULT 4 COMMENT ''达到该次处置后转长期关闭'' AFTER `action_durations_json`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE `monitor_event_lifecycle_policy`
SET `action_durations_json`='[60,240,1440]',`permanent_after_count`=4
WHERE `business_type`='RESOURCE_GOVERNANCE';

-- 已具备事件查看权限的角色自动获得工单查看权限；技术执行权限需在角色管理中明确授予。
INSERT IGNORE INTO `sys_role_permission` (`role_id`,`permission_code`)
SELECT `role_id`,'monitor.action.view'
FROM `sys_role_permission`
WHERE `permission_code`='monitor.event.view';

-- 验收查询。
SELECT business_type,severity,action_durations_json,permanent_after_count,status
FROM `monitor_event_lifecycle_policy`
WHERE business_type='RESOURCE_GOVERNANCE'
ORDER BY severity;

SELECT action_status,COUNT(1) order_count
FROM `monitor_resource_action_order`
GROUP BY action_status;
