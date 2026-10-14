-- GDS/OTA资源治理日异常监控模板 V1
-- 目标库：sibebid；执行前必须已执行 monitoring-center-schema.sql。
-- 本脚本仅注册模板和字段白名单，不创建重复的规则、事件或通知表，可重复执行。

USE `sibebid`;

INSERT INTO `monitor_rule_template` (
  template_code, template_name, category, data_source_code, entity_type,
  execution_mode, default_schedule_seconds, description, status
) VALUES
  ('GDS_QUERY_RATIO_DAILY', 'GDS查定比日异常', 'METRIC', 'BI_OTA_GDS_REQUEST_DAY', 'METRIC',
   'SCHEDULED', 86400, '按业务日、GDS及可选PCC/平台/站点/API分组检查查询量与航段查定比', 'ACTIVE'),
  ('OTA_SUCCESS_RATE_DAILY', 'OTA接口成功率日异常', 'METRIC', 'BI_OTA_GDS_REQUEST_DAY', 'METRIC',
   'SCHEDULED', 86400, '按业务日、OTA及可选站点/API分组检查查询、验价或生单接口成功率', 'ACTIVE')
ON DUPLICATE KEY UPDATE
  template_name=VALUES(template_name), category=VALUES(category),
  data_source_code=VALUES(data_source_code), entity_type=VALUES(entity_type),
  execution_mode=VALUES(execution_mode), default_schedule_seconds=VALUES(default_schedule_seconds),
  description=VALUES(description), status='ACTIVE', updated_at=CURRENT_TIMESTAMP;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT t.id, f.field_code, f.field_name, f.value_type, f.allowed_operators,
       f.required_flag, f.option_source, f.sort_no, 'ACTIVE'
FROM `monitor_rule_template` t
JOIN (
  SELECT 'gds_code' field_code, 'GDS' field_name, 'STRING' value_type, 'EQ' allowed_operators, 1 required_flag, 'RESOURCE_GOVERNANCE_DIMENSION' option_source, 10 sort_no
  UNION ALL SELECT 'pcc_code','PCC','STRING','EQ',0,'RESOURCE_GOVERNANCE_DIMENSION',20
  UNION ALL SELECT 'ota_code','平台编码','STRING','EQ',0,'RESOURCE_GOVERNANCE_DIMENSION',30
  UNION ALL SELECT 'ota_site_code','站点编码','STRING','EQ',0,'RESOURCE_GOVERNANCE_DIMENSION',40
  UNION ALL SELECT 'source_api_group','接口分组','STRING','EQ',0,'RESOURCE_GOVERNANCE_DIMENSION',50
  UNION ALL SELECT 'search_request_count_all','最小查询量','NUMBER','GTE',1,NULL,60
  UNION ALL SELECT 'query_to_segment_ratio','查定比上限','NUMBER','GT,GTE',1,NULL,70
) f ON t.template_code='GDS_QUERY_RATIO_DAILY'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), required_flag=VALUES(required_flag),
  option_source=VALUES(option_source), sort_no=VALUES(sort_no), status='ACTIVE',
  updated_at=CURRENT_TIMESTAMP;
INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT t.id, f.field_code, f.field_name, f.value_type, f.allowed_operators,
       f.required_flag, f.option_source, f.sort_no, 'ACTIVE'
FROM `monitor_rule_template` t
JOIN (
  SELECT 'ota_code' field_code, '平台编码' field_name, 'STRING' value_type, 'EQ' allowed_operators, 1 required_flag, 'RESOURCE_GOVERNANCE_DIMENSION' option_source, 10 sort_no
  UNION ALL SELECT 'ota_site_code','站点编码','STRING','EQ',0,'RESOURCE_GOVERNANCE_DIMENSION',20
  UNION ALL SELECT 'source_api_group','接口分组','STRING','EQ',0,'RESOURCE_GOVERNANCE_DIMENSION',30
  UNION ALL SELECT 'search_request_count_all','查询最小请求量','NUMBER','GTE',0,NULL,40
  UNION ALL SELECT 'search_success_rate','查询成功率下限(%)','NUMBER','LT,LTE',0,NULL,50
  UNION ALL SELECT 'verify_request_count_all','验价最小请求量','NUMBER','GTE',0,NULL,60
  UNION ALL SELECT 'verify_success_rate','验价成功率下限(%)','NUMBER','LT,LTE',0,NULL,70
  UNION ALL SELECT 'order_request_count_all','生单最小请求量','NUMBER','GTE',0,NULL,80
  UNION ALL SELECT 'order_success_rate','生单成功率下限(%)','NUMBER','LT,LTE',0,NULL,90
) f ON t.template_code='OTA_SUCCESS_RATE_DAILY'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), required_flag=VALUES(required_flag),
  option_source=VALUES(option_source), sort_no=VALUES(sort_no), status='ACTIVE',
  updated_at=CURRENT_TIMESTAMP;
