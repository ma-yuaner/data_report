-- 智能投放业务字段 V3 增量升级（现有环境执行一次）
-- 目标库：sibebid；MySQL 5.7+/8.0。
-- 先执行本脚本，再发布使用新字段的前后端版本。

USE `sibebid`;

ALTER TABLE `smart_placement_task`
  ADD COLUMN `segment_type` VARCHAR(32) DEFAULT NULL COMMENT '航段类型：直达/中转' AFTER `journey_type`,
  ADD COLUMN `advance_sale_days` INT DEFAULT NULL COMMENT '最少提前销售天数' AFTER `order_end_date`,
  ADD COLUMN `loss_threshold_min` DECIMAL(18,4) DEFAULT NULL COMMENT '可接受亏损阈值下限CNY，按亏损绝对值填写' AFTER `placement_method`,
  ADD COLUMN `loss_threshold_max` DECIMAL(18,4) DEFAULT NULL COMMENT '可接受亏损阈值上限CNY，按亏损绝对值填写' AFTER `loss_threshold_min`,
  ADD COLUMN `long_term_flag` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否长期有效：1是0否' AFTER `loss_threshold_max`;

ALTER TABLE `smart_placement_execution`
  ADD COLUMN `segment_type` VARCHAR(32) DEFAULT NULL COMMENT '实际航段类型：直达/中转' AFTER `route_text`,
  ADD COLUMN `loss_threshold_min` DECIMAL(18,4) DEFAULT NULL COMMENT '实际亏损阈值下限CNY' AFTER `order_source`,
  ADD COLUMN `loss_threshold_max` DECIMAL(18,4) DEFAULT NULL COMMENT '实际亏损阈值上限CNY' AFTER `loss_threshold_min`,
  ADD COLUMN `long_term_flag` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否长期有效：1是0否' AFTER `loss_threshold_max`;

ALTER TABLE `rt_order_monitor_feature`
  ADD COLUMN `trip_type` VARCHAR(32) DEFAULT NULL COMMENT '航程类型：单程/往返/多程' AFTER `product_type`,
  ADD COLUMN `advance_sale_days` INT DEFAULT NULL COMMENT '订单时间至首段起飞时间的提前天数' AFTER `journey_type`;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT id, 'advance_sale_days', '提前销售天数', 'NUMBER', 'GTE', 0, NULL, 195, 'ACTIVE'
FROM `monitor_rule_template`
WHERE template_code='SMART_PLACEMENT_ORDER'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), sort_no=VALUES(sort_no),
  status='ACTIVE', updated_at=CURRENT_TIMESTAMP;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT id, 'estimated_profit_cny', '预估利润', 'NUMBER', 'GTE,LTE', 0, NULL, 197, 'ACTIVE'
FROM `monitor_rule_template`
WHERE template_code='SMART_PLACEMENT_ORDER'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), sort_no=VALUES(sort_no),
  status='ACTIVE', updated_at=CURRENT_TIMESTAMP;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT id, 'trip_type', '航程类型', 'STRING_SET', 'IN', 0, NULL, 173, 'ACTIVE'
FROM `monitor_rule_template`
WHERE template_code='SMART_PLACEMENT_ORDER'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), sort_no=VALUES(sort_no),
  status='ACTIVE', updated_at=CURRENT_TIMESTAMP;

UPDATE `monitor_rule_template_field` f
JOIN `monitor_rule_template` t ON t.id=f.template_id
SET f.field_name='航段类型', f.value_type='STRING_SET',
    f.allowed_operators='EQ,IN', f.status='ACTIVE', f.updated_at=CURRENT_TIMESTAMP
WHERE t.template_code='SMART_PLACEMENT_ORDER' AND f.field_code='journey_type';

-- 完整航程仍保留在宽表及历史业务记录中，但不再作为智能投放新规则条件。
UPDATE `monitor_rule_template_field` f
JOIN `monitor_rule_template` t ON t.id=f.template_id
SET f.status='DISABLED', f.updated_at=CURRENT_TIMESTAMP
WHERE t.template_code='SMART_PLACEMENT_ORDER' AND f.field_code='route_text';

