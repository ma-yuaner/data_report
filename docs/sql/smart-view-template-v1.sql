-- 智能分析视图模板：维度分析与出票明细共用。
-- 私人模板仅创建者可见；公共模板所有有权访问智能分析的账号可用。
CREATE TABLE IF NOT EXISTS `smart_view_template` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '模板主键',
  `scope_code` VARCHAR(40) NOT NULL COMMENT 'dimension-analysis或detail-fields',
  `template_name` VARCHAR(60) NOT NULL COMMENT '模板名称',
  `config_json` JSON NOT NULL COMMENT '维度、指标、排序或明细字段配置',
  `owner_user_id` BIGINT UNSIGNED NOT NULL COMMENT '创建人数据中台用户ID',
  `owner_name_snapshot` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '创建人名称快照',
  `is_public` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1公共、0私人',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_smart_view_template_owner_name` (`scope_code`,`owner_user_id`,`template_name`),
  KEY `idx_smart_view_template_visible` (`scope_code`,`is_public`,`updated_at`),
  KEY `idx_smart_view_template_owner` (`owner_user_id`,`scope_code`,`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='智能分析私人及公共字段/维度模板';
