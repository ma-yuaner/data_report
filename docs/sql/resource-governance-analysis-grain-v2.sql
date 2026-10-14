-- GDS/OTA资源治理「异常分析粒度」V2
-- 目标库：sibebid；执行前必须已执行 monitoring-center-schema.sql 与 resource-governance-daily-monitor-v1.sql。
-- 本脚本为 GDS 查定比与 OTA 成功率模板注册 analysis_grain（异常分析粒度）字段，可重复执行。
--
-- 设计约定：
-- 1. 粒度值存放在 monitor_rule_version.condition_snapshot_json 的 groupDimensions 数组，例如 ["pcc_code"]；
--    它参与 rule_hash 计算，因此修改粒度会产生新规则版本，历史事件不会被污染。
-- 2. analysis_grain 不写入 monitor_rule_condition：它是规则版本级配置，不是数值条件，
--    这样既避免把粒度误当成指标参与阈值判断，也不会为技术侧旧脚本留下未知条件。
-- 3. 粒度只支持“数据范围维度”：GDS 规则为 gds_code、pcc_code；OTA 规则为 ota_code、ota_site_code、source_api_group。
--    未配置粒度时保持 V1 行为，整条规则只产生一个汇总事件。

USE `sibebid`;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT t.id, 'analysis_grain', '异常分析粒度', 'ANALYSIS_GRAIN', 'EQ',
       0, 'RESOURCE_GOVERNANCE_GRAIN:gds_code,pcc_code', 80, 'ACTIVE'
FROM `monitor_rule_template` t
WHERE t.template_code='GDS_QUERY_RATIO_DAILY'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), required_flag=VALUES(required_flag),
  option_source=VALUES(option_source), sort_no=VALUES(sort_no), status='ACTIVE',
  updated_at=CURRENT_TIMESTAMP;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT t.id, 'analysis_grain', '异常分析粒度', 'ANALYSIS_GRAIN', 'EQ',
       0, 'RESOURCE_GOVERNANCE_GRAIN:ota_code,ota_site_code,source_api_group', 100, 'ACTIVE'
FROM `monitor_rule_template` t
WHERE t.template_code='OTA_SUCCESS_RATE_DAILY'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), required_flag=VALUES(required_flag),
  option_source=VALUES(option_source), sort_no=VALUES(sort_no), status='ACTIVE',
  updated_at=CURRENT_TIMESTAMP;

-- 校验：两个模板都应存在 analysis_grain 字段，且不允许把粒度写成必填。
SELECT t.template_code, f.field_code, f.value_type, f.required_flag, f.option_source, f.status
FROM `monitor_rule_template` t
JOIN `monitor_rule_template_field` f ON f.template_id=t.id
WHERE t.template_code IN ('GDS_QUERY_RATIO_DAILY','OTA_SUCCESS_RATE_DAILY')
  AND f.field_code='analysis_grain';

-- 校验：已配置粒度的规则版本，其快照必须包含 groupDimensions；返回 0 行才是正常状态。
SELECT v.rule_id, v.version_no, v.condition_snapshot_json
FROM `monitor_rule_version` v
WHERE v.condition_snapshot_json LIKE '%analysis_grain%'
  AND v.condition_snapshot_json NOT LIKE '%groupDimensions%';
