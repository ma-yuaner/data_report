-- 企业微信站外通知 V1：可配置群机器人、默认@人员，并自动接入智能投放收单。
-- 执行库：sibebid。Webhook属于凭据，禁止复制到日志、文档或前端明文响应。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `monitor_notify_endpoint` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `endpoint_code` VARCHAR(64) NOT NULL COMMENT '通知端点唯一编码',
  `endpoint_name` VARCHAR(100) NOT NULL COMMENT '通知群名称',
  `channel` VARCHAR(32) NOT NULL DEFAULT 'WECOM' COMMENT '通知渠道',
  `webhook_url` VARCHAR(1024) NOT NULL COMMENT '企业微信群机器人Webhook；接口查询只返回掩码',
  `mentioned_user_ids` LONGTEXT DEFAULT NULL COMMENT '默认@企业微信用户ID JSON数组',
  `mentioned_mobiles` LONGTEXT DEFAULT NULL COMMENT '默认@手机号 JSON数组',
  `smart_placement_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否自动用于智能投放收单通知',
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/DISABLED',
  `created_by_id` BIGINT DEFAULT NULL,
  `created_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by_id` BIGINT DEFAULT NULL,
  `updated_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_notify_endpoint_code` (`endpoint_code`),
  KEY `idx_monitor_notify_endpoint_runtime` (`channel`, `status`, `smart_placement_enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控外部通知群配置';
