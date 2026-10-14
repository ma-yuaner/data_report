-- GDS资源治理查定比分母迁移：有效PNR -> 航段数seg_num。
-- 目标库：sibebid；可重复执行。

USE `sibebid`;

-- 已部署环境把模板字段与历史规则条件切换为新字段编码。
-- 若新字段已经存在，先删除旧模板字段，避免唯一键冲突。
DELETE old_field
FROM `monitor_rule_template_field` old_field
JOIN `monitor_rule_template` t ON t.id=old_field.template_id
WHERE t.template_code='GDS_QUERY_RATIO_DAILY'
  AND old_field.field_code='query_to_pnr_ratio'
  AND EXISTS (
    SELECT 1 FROM `monitor_rule_template_field` new_field
    WHERE new_field.template_id=old_field.template_id
      AND new_field.field_code='query_to_segment_ratio'
  );

UPDATE `monitor_rule_template_field` f
JOIN `monitor_rule_template` t ON t.id=f.template_id
SET f.field_code='query_to_segment_ratio',
    f.field_name='查定比上限',
    f.updated_at=CURRENT_TIMESTAMP
WHERE t.template_code='GDS_QUERY_RATIO_DAILY'
  AND f.field_code='query_to_pnr_ratio';

UPDATE `monitor_rule_condition` c
JOIN `monitor_rule_version` v ON v.id=c.rule_version_id
JOIN `monitor_rule` r ON r.id=v.rule_id
SET c.field_code='query_to_segment_ratio'
WHERE r.template_code='GDS_QUERY_RATIO_DAILY'
  AND c.field_code='query_to_pnr_ratio';

-- 校验：正式模板和规则条件均不应继续使用旧字段编码。
SELECT t.template_code,f.field_code,f.field_name,f.status
FROM `monitor_rule_template` t
JOIN `monitor_rule_template_field` f ON f.template_id=t.id
WHERE t.template_code='GDS_QUERY_RATIO_DAILY'
  AND f.field_code IN ('query_to_segment_ratio','query_to_pnr_ratio');

SELECT COUNT(1) AS legacy_condition_count
FROM `monitor_rule_condition` c
JOIN `monitor_rule_version` v ON v.id=c.rule_version_id
JOIN `monitor_rule` r ON r.id=v.rule_id
WHERE r.template_code='GDS_QUERY_RATIO_DAILY'
  AND c.field_code='query_to_pnr_ratio';
