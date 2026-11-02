-- Deploy before api/web. Run against the configured collaboration database (normally sibebid).
-- Additive migration only. Existing business matches, outcomes, profits and attribution are unchanged.
CREATE TABLE IF NOT EXISTS `smart_placement_order_exclusion` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform_name` VARCHAR(100) NOT NULL COMMENT '与收单匹配表相同的平台名称',
  `ota_order_no` VARCHAR(150) NOT NULL COMMENT 'OTA订单号，同平台订单整体分类',
  `is_excluded` TINYINT NOT NULL DEFAULT 0 COMMENT '1异常不计考核，0正常；不影响业务原始数据',
  `reason_code` VARCHAR(32) DEFAULT NULL COMMENT 'AFTER_SALES/DATA_ERROR/OTHER',
  `reason_note` VARCHAR(1000) DEFAULT NULL COMMENT '本次异常或恢复说明，历史保留于操作日志',
  `source_match_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '操作入口匹配记录ID',
  `version` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '分类乐观锁版本',
  `created_by_id` BIGINT NOT NULL,
  `created_by_name` VARCHAR(100) NOT NULL,
  `updated_by_id` BIGINT NOT NULL,
  `updated_by_name` VARCHAR(100) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_spoe_platform_order` (`platform_name`,`ota_order_no`),
  KEY `idx_spoe_excluded_updated` (`is_excluded`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能收单考核分类，原业务数据完整保留';
