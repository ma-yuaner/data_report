-- GDS/OTA资源异常责任人、观察期与催办升级闭环 V4
-- 目标库：sibebid；执行前需完成 monitoring-center-schema.sql。
-- 可重复执行。所有时间均按应用约定的 Asia/Shanghai 业务时间写入。

USE `sibebid`;

SET @db = DATABASE();

-- 事件处理字段：责任人、处理时限、观察期、升级次数和处理结论。
SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='assignee_user_id'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `assignee_user_id` BIGINT NULL COMMENT ''当前处理责任人账号ID'' AFTER `event_status`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='assignee_user_name'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `assignee_user_name` VARCHAR(100) NULL COMMENT ''责任人姓名快照'' AFTER `assignee_user_id`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='due_at'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `due_at` DATETIME NULL COMMENT ''当前处理截止时间'' AFTER `assignee_user_name`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='observe_until'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `observe_until` DATETIME NULL COMMENT ''延后观察截止时间'' AFTER `due_at`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='escalation_level'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `escalation_level` INT NOT NULL DEFAULT 0 COMMENT ''当前升级级别'' AFTER `observe_until`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='last_escalated_at'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `last_escalated_at` DATETIME NULL COMMENT ''最近一次升级时间'' AFTER `escalation_level`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND COLUMN_NAME='resolution_code'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD COLUMN `resolution_code` VARCHAR(32) NULL COMMENT ''处理结论编码'' AFTER `last_escalated_at`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND INDEX_NAME='idx_monitor_event_assignee_status'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD KEY `idx_monitor_event_assignee_status` (`assignee_user_id`,`event_status`,`due_at`)'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_alert_event' AND INDEX_NAME='idx_monitor_event_due'),
  'SELECT 1',
  'ALTER TABLE `monitor_alert_event` ADD KEY `idx_monitor_event_due` (`business_type`,`event_status`,`due_at`)'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 审计日志补充操作类型和结构化前后值，保留原字段兼容旧代码。
SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_event_operation_log' AND COLUMN_NAME='action_code'),
  'SELECT 1',
  'ALTER TABLE `monitor_event_operation_log` ADD COLUMN `action_code` VARCHAR(32) NOT NULL DEFAULT ''STATUS_CHANGE'' COMMENT ''ASSIGN/ACKNOWLEDGE/OBSERVE/ESCALATE/RESOLVE/IGNORE/CLOSE'' AFTER `event_id`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_event_operation_log' AND COLUMN_NAME='operation_detail_json'),
  'SELECT 1',
  'ALTER TABLE `monitor_event_operation_log` ADD COLUMN `operation_detail_json` LONGTEXT NULL COMMENT ''处理前后值JSON'' AFTER `operation_note`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 同一事件允许初次通知、观察到期和多次升级分别进入可靠发件箱。
SET @sql = IF(
  EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_notify_outbox' AND COLUMN_NAME='notification_key'),
  'SELECT 1',
  'ALTER TABLE `monitor_notify_outbox` ADD COLUMN `notification_key` VARCHAR(100) NOT NULL DEFAULT ''INITIAL'' COMMENT ''同一事件通知阶段幂等键'' AFTER `event_id`'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @old_notify_index = (
  SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_notify_outbox'
    AND INDEX_NAME='uk_monitor_notify_target' AND COLUMN_NAME='notification_key'
);
SET @index_exists = (
  SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_notify_outbox'
    AND INDEX_NAME='uk_monitor_notify_target'
);
SET @sql = IF(@index_exists > 0 AND @old_notify_index = 0,
  'ALTER TABLE `monitor_notify_outbox` DROP INDEX `uk_monitor_notify_target`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @index_exists = (
  SELECT COUNT(1) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA=@db AND TABLE_NAME='monitor_notify_outbox'
    AND INDEX_NAME='uk_monitor_notify_target'
);
SET @sql = IF(@index_exists = 0,
  'ALTER TABLE `monitor_notify_outbox` ADD UNIQUE KEY `uk_monitor_notify_target` (`event_id`,`channel`,`target_id`,`notification_key`)',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 生命周期时限可按业务类型和等级调整，无需修改Python代码。
CREATE TABLE IF NOT EXISTS `monitor_event_lifecycle_policy` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `business_type` VARCHAR(32) NOT NULL,
  `severity` VARCHAR(16) NOT NULL,
  `initial_due_minutes` INT NOT NULL COMMENT '首次处理时限分钟',
  `escalation_intervals_json` VARCHAR(500) NOT NULL COMMENT '每级再次催办间隔分钟JSON数组',
  `max_observe_hours` INT NOT NULL DEFAULT 168 COMMENT '单次允许观察的最大小时数',
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_lifecycle_policy` (`business_type`,`severity`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控事件处理与升级时限策略';

INSERT INTO `monitor_event_lifecycle_policy`
  (`business_type`,`severity`,`initial_due_minutes`,`escalation_intervals_json`,`max_observe_hours`,`status`)
VALUES
  ('RESOURCE_GOVERNANCE','P0',60,'[60,240,720]',72,'ACTIVE'),
  ('RESOURCE_GOVERNANCE','P1',240,'[240,720,1440]',120,'ACTIVE'),
  ('RESOURCE_GOVERNANCE','P2',1440,'[720,1440,2880]',168,'ACTIVE')
ON DUPLICATE KEY UPDATE
  initial_due_minutes=VALUES(initial_due_minutes),
  escalation_intervals_json=VALUES(escalation_intervals_json),
  max_observe_hours=VALUES(max_observe_hours),status='ACTIVE';

-- 历史资源事件默认分配给规则负责人，并按等级补首次时限。
UPDATE `monitor_alert_event` e
JOIN `monitor_rule` r ON r.id=e.rule_id
LEFT JOIN `monitor_event_lifecycle_policy` p
  ON p.business_type=e.business_type AND p.severity=e.severity AND p.status='ACTIVE'
SET e.assignee_user_id=COALESCE(e.assignee_user_id,r.owner_user_id),
    e.assignee_user_name=COALESCE(e.assignee_user_name,r.owner_user_name),
    e.due_at=COALESCE(e.due_at,TIMESTAMPADD(MINUTE,COALESCE(p.initial_due_minutes,1440),e.first_seen_at))
WHERE e.business_type='RESOURCE_GOVERNANCE'
  AND e.event_status IN ('OPEN','ACKNOWLEDGED','OBSERVING','ESCALATED');

-- 验收查询。
SELECT business_type,severity,initial_due_minutes,escalation_intervals_json,max_observe_hours,status
FROM `monitor_event_lifecycle_policy`
ORDER BY business_type,severity;

SELECT event_status,COUNT(1) event_count,
       SUM(CASE WHEN due_at<NOW() THEN 1 ELSE 0 END) overdue_count
FROM `monitor_alert_event`
WHERE business_type='RESOURCE_GOVERNANCE'
GROUP BY event_status;
