-- 日内累计航段监控：在既有监控中心及消息模板/路由迁移之后执行。
-- 只创建中台对象，不连接或修改ERP，不创建规则、不自动绑定通知群。
USE `sibebid`;

CREATE TABLE IF NOT EXISTS monitor_daily_segment_snapshot (
  business_date DATE NOT NULL,
  rule_id BIGINT UNSIGNED NOT NULL,
  business_line VARCHAR(32) NOT NULL,
  segment_total BIGINT UNSIGNED NOT NULL,
  threshold_value BIGINT UNSIGNED NOT NULL,
  reference_limit BIGINT UNSIGNED DEFAULT NULL COMMENT '仅展示，不触发第二档或停卖',
  site_counts_json TEXT NOT NULL,
  source_as_of DATETIME NOT NULL COMMENT 'ERP一致性读开始时间，不是同步完成时间',
  source_duration_ms BIGINT UNSIGNED NOT NULL,
  batch_id VARCHAR(40) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (business_date,rule_id),
  KEY idx_daily_segment_rule (rule_id,business_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO monitor_rule_template
 (template_code,template_name,category,data_source_code,entity_type,execution_mode,default_schedule_seconds,description,status)
VALUES ('DAILY_SEGMENT_THRESHOLD','携程单日累计航段','METRIC','ERP_DAILY_SEGMENT','METRIC','SCHEDULED',300,
 '北京时间出票日；按业务线三个站点合计，每日首次达到阈值提醒。参考上限仅展示。复用总航段报表有效出票关联航段口径。','ACTIVE')
ON DUPLICATE KEY UPDATE template_name=VALUES(template_name),description=VALUES(description);

INSERT INTO monitor_rule_template_field
 (template_id,field_code,field_name,value_type,allowed_operators,required_flag,sort_no,status)
SELECT t.id,f.code,f.name,f.kind,f.operators,f.required_flag,f.sort_no,'ACTIVE'
FROM monitor_rule_template t JOIN (
 SELECT 'business_line' code,'业务线' name,'STRING' kind,'EQ' operators,1 required_flag,10 sort_no
 UNION ALL SELECT 'segment_total','当日累计航段提醒值','NUMBER','GTE',1,20
 UNION ALL SELECT 'reference_limit','参考上限（不触发提醒）','NUMBER','EQ',0,30
) f ON t.template_code='DAILY_SEGMENT_THRESHOLD'
ON DUPLICATE KEY UPDATE field_name=VALUES(field_name),allowed_operators=VALUES(allowed_operators),required_flag=VALUES(required_flag);

INSERT INTO monitor_message_template
 (template_code,template_name,event_code,channel,title_template,body_template,field_schema_json,status)
VALUES ('DAILY_SEGMENT_WECOM','携程单日航段销量提醒','DAILY_SEGMENT_THRESHOLD_ALERT','WECOM',
 '携程渠道单日总航段销量提醒',
 '业务日期：{businessDate}\n业务线：{businessLine}\n累计销量：{segmentCount} 段\n提醒阈值：{threshold} 段\n参考上限：{referenceLimit}（仅参考）\n数据截至：{sourceAsOf}\n负责人：{ownerName}\n事件：{eventNo}\n请进入企业数据中台监控中心查看。',
 '{"allowedFields":["businessDate","businessLine","segmentCount","threshold","referenceLimit","sourceAsOf","ownerName","eventNo"],"fieldLabels":{"businessDate":"业务日期","businessLine":"业务线","segmentCount":"累计航段","threshold":"提醒阈值","referenceLimit":"参考上限","sourceAsOf":"数据截至","ownerName":"负责人","eventNo":"事件编号"}}',
 'ACTIVE')
ON DUPLICATE KEY UPDATE field_schema_json=VALUES(field_schema_json);
