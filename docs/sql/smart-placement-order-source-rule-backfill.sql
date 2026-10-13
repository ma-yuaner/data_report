-- 智能投放存量监控规则补充订单来源条件。
-- 目标库：sibebid。
-- 适用场景：任务/执行记录已经保存order_source，但升级前生成的当前规则版本没有order_source条件。
-- 处理原则：不修改旧版本；复制生成一个新版本、追加订单来源条件，再切换规则当前版本。
-- 没有选择订单来源的任务保持“不限”，不会补条件。脚本可重复执行。

USE `sibebid`;

DROP TEMPORARY TABLE IF EXISTS `tmp_smart_order_source_rule_backfill`;
CREATE TEMPORARY TABLE `tmp_smart_order_source_rule_backfill` AS
SELECT
  r.id AS rule_id,
  r.current_version_id AS old_version_id,
  r.current_version_no + 1 AS new_version_no,
  COALESCE(NULLIF(TRIM(e.order_source), ''), NULLIF(TRIM(t.order_source), '')) AS order_source
FROM monitor_rule r
JOIN monitor_rule_version v ON v.id = r.current_version_id AND v.rule_id = r.id
JOIN smart_placement_execution e
  ON e.id = r.source_business_id AND e.execution_result = 'SUCCESS'
JOIN smart_placement_task t ON t.id = r.source_parent_id AND t.is_deleted = 0
WHERE r.source_business_type = 'SMART_PLACEMENT_EXECUTION'
  AND COALESCE(NULLIF(TRIM(e.order_source), ''), NULLIF(TRIM(t.order_source), '')) IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM monitor_rule_condition c
    WHERE c.rule_version_id = r.current_version_id
      AND c.field_code = 'order_source'
  );

START TRANSACTION;

INSERT INTO monitor_rule_version (
  rule_id, version_no, rule_hash, effective_start_at, effective_end_at,
  condition_relation, condition_snapshot_json, change_reason, status,
  created_by_id, created_by_name, created_at
)
SELECT
  b.rule_id,
  b.new_version_no,
  SHA2(CONCAT(v.rule_hash, '|order_source|', b.order_source, '|', b.new_version_no), 256),
  v.effective_start_at,
  v.effective_end_at,
  v.condition_relation,
  JSON_SET(
    v.condition_snapshot_json,
    '$.conditions',
    JSON_ARRAY_APPEND(
      COALESCE(JSON_EXTRACT(v.condition_snapshot_json, '$.conditions'), JSON_ARRAY()),
      '$',
      JSON_OBJECT(
        'groupNo', 1,
        'sortNo', COALESCE((
          SELECT MAX(c.sort_no) + 1
          FROM monitor_rule_condition c
          WHERE c.rule_version_id = b.old_version_id
        ), 1),
        'fieldCode', 'order_source',
        'operatorCode', 'EQ',
        'valueType', 'STRING',
        'value', b.order_source,
        'conditionRole', 'INCLUDE'
      )
    )
  ),
  '存量规则补充订单来源条件',
  'ACTIVE',
  NULL,
  'SYSTEM_MIGRATION',
  NOW()
FROM tmp_smart_order_source_rule_backfill b
JOIN monitor_rule_version v ON v.id = b.old_version_id;

INSERT INTO monitor_rule_condition (
  rule_version_id, group_no, sort_no, field_code,
  operator_code, value_type, value_json, condition_role, created_at
)
SELECT
  nv.id, c.group_no, c.sort_no, c.field_code,
  c.operator_code, c.value_type, c.value_json, c.condition_role, NOW()
FROM tmp_smart_order_source_rule_backfill b
JOIN monitor_rule_version nv
  ON nv.rule_id = b.rule_id AND nv.version_no = b.new_version_no
JOIN monitor_rule_condition c ON c.rule_version_id = b.old_version_id;

INSERT INTO monitor_rule_condition (
  rule_version_id, group_no, sort_no, field_code,
  operator_code, value_type, value_json, condition_role, created_at
)
SELECT
  nv.id,
  1,
  COALESCE(MAX(c.sort_no), 0) + 1,
  'order_source',
  'EQ',
  'STRING',
  JSON_QUOTE(b.order_source),
  'INCLUDE',
  NOW()
FROM tmp_smart_order_source_rule_backfill b
JOIN monitor_rule_version nv
  ON nv.rule_id = b.rule_id AND nv.version_no = b.new_version_no
LEFT JOIN monitor_rule_condition c ON c.rule_version_id = nv.id
GROUP BY nv.id, b.order_source;

UPDATE monitor_rule_version ov
JOIN tmp_smart_order_source_rule_backfill b ON b.old_version_id = ov.id
SET ov.status = 'SUPERSEDED';

UPDATE monitor_rule r
JOIN tmp_smart_order_source_rule_backfill b ON b.rule_id = r.id
JOIN monitor_rule_version nv
  ON nv.rule_id = b.rule_id AND nv.version_no = b.new_version_no
SET r.current_version_id = nv.id,
    r.current_version_no = b.new_version_no,
    r.updated_by_id = NULL,
    r.updated_by_name = 'SYSTEM_MIGRATION',
    r.updated_at = NOW();

INSERT INTO monitor_rule_operation_log (
  rule_id, rule_version_id, action_code, from_status, to_status,
  operator_id, operator_name, operation_note, detail_json, created_at
)
SELECT
  b.rule_id,
  nv.id,
  'VERSION',
  r.status,
  r.status,
  NULL,
  'SYSTEM_MIGRATION',
  '存量规则补充订单来源条件',
  JSON_OBJECT('fieldCode', 'order_source', 'operatorCode', 'EQ', 'value', b.order_source),
  NOW()
FROM tmp_smart_order_source_rule_backfill b
JOIN monitor_rule r ON r.id = b.rule_id
JOIN monitor_rule_version nv
  ON nv.rule_id = b.rule_id AND nv.version_no = b.new_version_no;

COMMIT;

-- 验证：返回0行表示所有已选择订单来源的当前规则都已包含该条件。
SELECT
  r.rule_code,
  r.current_version_no,
  COALESCE(NULLIF(TRIM(e.order_source), ''), NULLIF(TRIM(t.order_source), '')) AS expected_order_source
FROM monitor_rule r
JOIN smart_placement_execution e ON e.id = r.source_business_id
JOIN smart_placement_task t ON t.id = r.source_parent_id
WHERE r.source_business_type = 'SMART_PLACEMENT_EXECUTION'
  AND COALESCE(NULLIF(TRIM(e.order_source), ''), NULLIF(TRIM(t.order_source), '')) IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM monitor_rule_condition c
    WHERE c.rule_version_id = r.current_version_id
      AND c.field_code = 'order_source'
  );

DROP TEMPORARY TABLE IF EXISTS `tmp_smart_order_source_rule_backfill`;

