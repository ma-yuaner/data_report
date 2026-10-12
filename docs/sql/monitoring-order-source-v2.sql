-- 智能投放分钟监控 V2 增量升级（现有环境执行一次）
-- 目标库：sibebid；执行前请先确认当前连接。

USE `sibebid`;

ALTER TABLE `rt_order_monitor_feature`
  ADD COLUMN `order_source` VARCHAR(32) DEFAULT NULL COMMENT '订单来源：平台手工订单/直连订单' AFTER `source_updated_at`,
  ADD KEY `idx_rt_order_source` (`order_source`, `order_time`);

ALTER TABLE `smart_placement_task`
  ADD COLUMN `order_source` VARCHAR(32) DEFAULT NULL COMMENT '订单来源：平台手工订单/直连订单' AFTER `product_type`;

ALTER TABLE `smart_placement_execution`
  ADD COLUMN `order_source` VARCHAR(32) DEFAULT NULL COMMENT '实际订单来源：平台手工订单/直连订单' AFTER `product_type`;

ALTER TABLE `smart_placement_order_match`
  ADD COLUMN `order_source` VARCHAR(32) DEFAULT NULL COMMENT '订单来源：平台手工订单/直连订单' AFTER `site_name`;

CREATE TABLE IF NOT EXISTS `monitor_rule_run_stat` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `run_no` VARCHAR(40) NOT NULL COMMENT '对应monitor_run_log.run_no',
  `rule_id` BIGINT UNSIGNED NOT NULL,
  `rule_code` VARCHAR(64) NOT NULL,
  `execution_type` VARCHAR(16) NOT NULL COMMENT 'INCREMENTAL/REPLAY',
  `features_considered` BIGINT NOT NULL DEFAULT 0,
  `condition_checks` BIGINT NOT NULL DEFAULT 0,
  `matched_count` BIGINT NOT NULL DEFAULT 0,
  `failure_summary_json` LONGTEXT DEFAULT NULL COMMENT '未通过字段及次数JSON',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_rule_run_stat` (`run_no`, `rule_id`, `execution_type`),
  KEY `idx_monitor_rule_stat_rule` (`rule_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每次匹配运行的规则级诊断统计';

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT id, 'order_source', '订单来源', 'STRING', 'EQ,IN', 0, NULL, 172, 'ACTIVE'
FROM `monitor_rule_template`
WHERE template_code='SMART_PLACEMENT_ORDER'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), sort_no=VALUES(sort_no),
  status='ACTIVE', updated_at=CURRENT_TIMESTAMP;
