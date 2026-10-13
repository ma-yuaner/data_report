-- 通用监控中心 V1 表结构
-- 目标库：sibebid；兼容 MySQL 5.7+/8.0；字符集 utf8mb4。
-- 本脚本只创建新表，不修改旧预警表和旧智能投放命中表，可重复执行。
-- 应用不会自动创建这些业务表。部署后端前请先执行本脚本。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `monitor_rule_template` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `template_code` VARCHAR(64) NOT NULL COMMENT '模板唯一编码',
  `template_name` VARCHAR(100) NOT NULL COMMENT '模板名称',
  `category` VARCHAR(32) NOT NULL COMMENT 'ORDER_EVENT/METRIC/STATE_TIMEOUT/DATA_QUALITY',
  `data_source_code` VARCHAR(64) NOT NULL COMMENT '数据源编码',
  `entity_type` VARCHAR(32) NOT NULL COMMENT 'ORDER/METRIC/TASK/JOB',
  `execution_mode` VARCHAR(32) NOT NULL COMMENT 'INCREMENTAL_BATCH/SCHEDULED',
  `default_schedule_seconds` INT NOT NULL DEFAULT 60 COMMENT '默认执行间隔秒数',
  `field_schema_json` LONGTEXT DEFAULT NULL COMMENT '模板字段快照，前端展示和审计使用',
  `description` VARCHAR(1000) DEFAULT NULL COMMENT '模板说明',
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/DISABLED',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_template_code` (`template_code`),
  KEY `idx_monitor_template_category_status` (`category`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通用监控规则模板';

CREATE TABLE IF NOT EXISTS `monitor_rule_template_field` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `template_id` BIGINT UNSIGNED NOT NULL COMMENT '模板ID',
  `field_code` VARCHAR(64) NOT NULL COMMENT '标准字段编码',
  `field_name` VARCHAR(100) NOT NULL COMMENT '字段中文名',
  `value_type` VARCHAR(20) NOT NULL COMMENT 'STRING/NUMBER/DATE/DATETIME/STRING_SET',
  `allowed_operators` VARCHAR(300) NOT NULL COMMENT '允许的运算符，英文逗号分隔',
  `required_flag` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '模板是否必填',
  `option_source` VARCHAR(200) DEFAULT NULL COMMENT '选项来源编码',
  `sort_no` INT NOT NULL DEFAULT 0,
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_template_field` (`template_id`, `field_code`),
  KEY `idx_monitor_template_field_status` (`template_id`, `status`, `sort_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='规则模板可配置字段白名单';

CREATE TABLE IF NOT EXISTS `monitor_rule` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `rule_code` VARCHAR(64) NOT NULL COMMENT '规则唯一编码',
  `rule_name` VARCHAR(200) NOT NULL COMMENT '规则名称',
  `template_id` BIGINT UNSIGNED NOT NULL COMMENT '模板ID',
  `template_code` VARCHAR(64) NOT NULL COMMENT '模板编码快照',
  `business_type` VARCHAR(32) NOT NULL COMMENT 'SMART_PLACEMENT/ORDER_RISK等业务类型',
  `source_business_type` VARCHAR(64) DEFAULT NULL COMMENT '来源业务对象类型',
  `source_business_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '来源业务对象ID，例如投放执行ID',
  `source_parent_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '来源父对象ID，例如投放任务ID',
  `owner_user_id` BIGINT DEFAULT NULL COMMENT '规则负责人用户ID',
  `owner_user_name` VARCHAR(100) DEFAULT NULL COMMENT '负责人姓名快照',
  `severity` VARCHAR(16) NOT NULL DEFAULT 'P2' COMMENT 'P0/P1/P2/P3',
  `status` VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED' COMMENT 'SCHEDULED/ACTIVE/PAUSED/EXPIRED/DISABLED',
  `effective_start_at` DATETIME DEFAULT NULL COMMENT '生效时间',
  `effective_end_at` DATETIME DEFAULT NULL COMMENT '失效时间',
  `schedule_seconds` INT NOT NULL DEFAULT 60 COMMENT '执行间隔秒数',
  `notify_policy_json` LONGTEXT DEFAULT NULL COMMENT '通知对象及渠道配置',
  `current_version_no` INT NOT NULL DEFAULT 1,
  `current_version_id` BIGINT UNSIGNED DEFAULT NULL,
  `last_run_at` DATETIME DEFAULT NULL,
  `last_hit_at` DATETIME DEFAULT NULL,
  `created_by_id` BIGINT DEFAULT NULL,
  `created_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_by_id` BIGINT DEFAULT NULL,
  `updated_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_rule_code` (`rule_code`),
  UNIQUE KEY `uk_monitor_rule_source` (`source_business_type`, `source_business_id`),
  KEY `idx_monitor_rule_runtime` (`status`, `effective_start_at`, `effective_end_at`),
  KEY `idx_monitor_rule_template_status` (`template_code`, `status`),
  KEY `idx_monitor_rule_owner_status` (`owner_user_id`, `status`),
  KEY `idx_monitor_rule_parent` (`source_business_type`, `source_parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通用监控规则主表';

CREATE TABLE IF NOT EXISTS `monitor_rule_version` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `rule_id` BIGINT UNSIGNED NOT NULL COMMENT '规则ID',
  `version_no` INT NOT NULL COMMENT '版本号',
  `rule_hash` CHAR(64) NOT NULL COMMENT '规则内容SHA256',
  `effective_start_at` DATETIME DEFAULT NULL,
  `effective_end_at` DATETIME DEFAULT NULL,
  `condition_relation` VARCHAR(8) NOT NULL DEFAULT 'AND' COMMENT '条件组关系AND/OR',
  `condition_snapshot_json` LONGTEXT NOT NULL COMMENT '完整条件快照',
  `change_reason` VARCHAR(500) DEFAULT NULL,
  `status` VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/SUPERSEDED/DISABLED',
  `created_by_id` BIGINT DEFAULT NULL,
  `created_by_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_rule_version` (`rule_id`, `version_no`),
  KEY `idx_monitor_rule_version_status` (`rule_id`, `status`),
  KEY `idx_monitor_rule_version_hash` (`rule_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控规则不可变版本';

CREATE TABLE IF NOT EXISTS `monitor_rule_condition` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `rule_version_id` BIGINT UNSIGNED NOT NULL COMMENT '规则版本ID',
  `group_no` INT NOT NULL DEFAULT 1 COMMENT '同组AND，不同组按版本关系组合',
  `sort_no` INT NOT NULL DEFAULT 0,
  `field_code` VARCHAR(64) NOT NULL COMMENT '标准特征字段',
  `operator_code` VARCHAR(32) NOT NULL COMMENT 'EQ/IN/BETWEEN/OVERLAP/CONTAINS_ALL/DISJOINT/GTE等',
  `value_type` VARCHAR(20) NOT NULL COMMENT 'STRING/NUMBER/DATE/DATETIME/STRING_SET',
  `value_json` LONGTEXT NOT NULL COMMENT '结构化条件值',
  `condition_role` VARCHAR(16) NOT NULL DEFAULT 'INCLUDE' COMMENT 'INCLUDE/EXCLUDE',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_rule_condition_order` (`rule_version_id`, `group_no`, `sort_no`),
  KEY `idx_monitor_rule_condition_field` (`rule_version_id`, `field_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控规则结构化条件';

CREATE TABLE IF NOT EXISTS `monitor_rule_operation_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `rule_id` BIGINT UNSIGNED NOT NULL,
  `rule_version_id` BIGINT UNSIGNED DEFAULT NULL,
  `action_code` VARCHAR(32) NOT NULL COMMENT 'CREATE/ENABLE/PAUSE/DISABLE/EXPIRE/VERSION',
  `from_status` VARCHAR(16) DEFAULT NULL,
  `to_status` VARCHAR(16) DEFAULT NULL,
  `operator_id` BIGINT DEFAULT NULL,
  `operator_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `operation_note` VARCHAR(1000) DEFAULT NULL,
  `detail_json` LONGTEXT DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_monitor_rule_operation` (`rule_id`, `created_at`),
  KEY `idx_monitor_rule_operator` (`operator_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控规则操作审计日志';

CREATE TABLE IF NOT EXISTS `rt_order_monitor_feature` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `source_system` VARCHAR(32) NOT NULL COMMENT '来源系统编码',
  `feature_key` VARCHAR(128) NOT NULL COMMENT '来源内稳定订单特征键',
  `source_order_id` VARCHAR(100) DEFAULT NULL COMMENT '源订单内部ID',
  `ota_order_no` VARCHAR(150) DEFAULT NULL,
  `order_time` DATETIME NOT NULL COMMENT '进单时间',
  `source_updated_at` DATETIME NOT NULL COMMENT '源订单最后更新时间',
  `order_source` VARCHAR(32) DEFAULT NULL COMMENT '订单来源：平台手工订单/直连订单',
  `platform_code` VARCHAR(64) DEFAULT NULL,
  `platform_name` VARCHAR(100) DEFAULT NULL,
  `site_code` VARCHAR(64) DEFAULT NULL,
  `site_name` VARCHAR(150) DEFAULT NULL,
  `airline_code` VARCHAR(32) DEFAULT NULL,
  `departure_airport` VARCHAR(32) DEFAULT NULL,
  `departure_city` VARCHAR(32) DEFAULT NULL,
  `departure_country` VARCHAR(32) DEFAULT NULL,
  `departure_zone` VARCHAR(32) DEFAULT NULL,
  `departure_location_codes` VARCHAR(500) DEFAULT NULL COMMENT '机场、城市、国家、大区标准码集合',
  `arrival_airport` VARCHAR(32) DEFAULT NULL,
  `arrival_city` VARCHAR(32) DEFAULT NULL,
  `arrival_country` VARCHAR(32) DEFAULT NULL,
  `arrival_zone` VARCHAR(32) DEFAULT NULL,
  `arrival_location_codes` VARCHAR(500) DEFAULT NULL COMMENT '机场、城市、国家、大区标准码集合',
  `route_text` VARCHAR(500) DEFAULT NULL,
  `flight_nos` VARCHAR(1000) DEFAULT NULL,
  `cabin_codes` VARCHAR(1000) DEFAULT NULL,
  `product_type` VARCHAR(150) DEFAULT NULL,
  `trip_type` VARCHAR(32) DEFAULT NULL COMMENT '航程类型：单程/往返/多程',
  `journey_type` VARCHAR(32) DEFAULT NULL COMMENT '航段类型：直达/直飞/中转',
  `advance_sale_days` INT DEFAULT NULL COMMENT '订单时间至首段起飞时间的提前天数',
  `first_departure_time` DATETIME DEFAULT NULL,
  `order_status` VARCHAR(64) DEFAULT NULL,
  `ticket_count` BIGINT DEFAULT NULL,
  `segment_count` BIGINT DEFAULT NULL,
  `estimated_profit_cny` DECIMAL(20,8) DEFAULT NULL,
  `batch_id` VARCHAR(40) NOT NULL COMMENT '本次增量批次号',
  `feature_hash` CHAR(64) NOT NULL COMMENT '参与匹配字段SHA256',
  `source_table` VARCHAR(128) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rt_order_feature` (`source_system`, `feature_key`),
  KEY `idx_rt_order_source_watermark` (`source_updated_at`, `source_order_id`),
  KEY `idx_rt_order_batch` (`batch_id`, `id`),
  KEY `idx_rt_order_candidate` (`platform_name`, `site_name`, `airline_code`),
  KEY `idx_rt_order_source` (`order_source`, `order_time`),
  KEY `idx_rt_order_time` (`order_time`),
  KEY `idx_rt_order_hash` (`feature_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分钟级订单监控匹配特征表';

CREATE TABLE IF NOT EXISTS `monitor_data_cursor` (
  `source_code` VARCHAR(64) NOT NULL COMMENT '数据采集源编码',
  `cursor_time` DATETIME DEFAULT NULL COMMENT '更新时间水位',
  `cursor_tie_breaker` VARCHAR(128) DEFAULT NULL COMMENT '同时间排序键',
  `last_batch_id` VARCHAR(40) DEFAULT NULL,
  `version_no` INT NOT NULL DEFAULT 0 COMMENT '乐观锁版本',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`source_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控数据增量水位';

CREATE TABLE IF NOT EXISTS `monitor_run_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `run_no` VARCHAR(40) NOT NULL,
  `job_type` VARCHAR(32) NOT NULL COMMENT 'FEATURE_ETL/RULE_MATCH/NOTIFY',
  `source_code` VARCHAR(64) DEFAULT NULL,
  `batch_id` VARCHAR(40) DEFAULT NULL,
  `status` VARCHAR(16) NOT NULL COMMENT 'RUNNING/SUCCESS/FAILED/SKIPPED',
  `watermark_before` VARCHAR(300) DEFAULT NULL,
  `watermark_after` VARCHAR(300) DEFAULT NULL,
  `rows_read` BIGINT NOT NULL DEFAULT 0,
  `rows_written` BIGINT NOT NULL DEFAULT 0,
  `rules_checked` BIGINT NOT NULL DEFAULT 0,
  `events_created` BIGINT NOT NULL DEFAULT 0,
  `error_message` VARCHAR(2000) DEFAULT NULL,
  `started_at` DATETIME NOT NULL,
  `finished_at` DATETIME DEFAULT NULL,
  `duration_ms` BIGINT DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_run_no` (`run_no`),
  KEY `idx_monitor_run_job_time` (`job_type`, `started_at`),
  KEY `idx_monitor_run_status_time` (`status`, `started_at`),
  KEY `idx_monitor_run_batch` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控采集、匹配和通知运行日志';

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

CREATE TABLE IF NOT EXISTS `monitor_alert_event` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `event_no` VARCHAR(40) NOT NULL,
  `rule_id` BIGINT UNSIGNED NOT NULL,
  `rule_version_id` BIGINT UNSIGNED NOT NULL,
  `rule_code` VARCHAR(64) NOT NULL,
  `template_code` VARCHAR(64) NOT NULL,
  `business_type` VARCHAR(32) NOT NULL,
  `entity_type` VARCHAR(32) NOT NULL,
  `entity_key` VARCHAR(200) NOT NULL,
  `severity` VARCHAR(16) NOT NULL,
  `event_title` VARCHAR(300) NOT NULL,
  `event_detail` LONGTEXT DEFAULT NULL,
  `match_snapshot_json` LONGTEXT NOT NULL,
  `source_batch_id` VARCHAR(40) DEFAULT NULL,
  `business_ref_type` VARCHAR(64) DEFAULT NULL COMMENT '业务处理表类型',
  `business_ref_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '业务处理表ID',
  `dedupe_key` CHAR(64) NOT NULL COMMENT '规则版本+实体+特征哈希',
  `event_status` VARCHAR(20) NOT NULL DEFAULT 'OPEN' COMMENT 'OPEN/ACKNOWLEDGED/RESOLVED/IGNORED/CLOSED',
  `hit_count` INT NOT NULL DEFAULT 1,
  `occurred_at` DATETIME NOT NULL,
  `first_seen_at` DATETIME NOT NULL,
  `last_seen_at` DATETIME NOT NULL,
  `resolved_at` DATETIME DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_event_no` (`event_no`),
  UNIQUE KEY `uk_monitor_event_dedupe` (`dedupe_key`),
  KEY `idx_monitor_event_status_time` (`event_status`, `occurred_at`),
  KEY `idx_monitor_event_rule_time` (`rule_id`, `occurred_at`),
  KEY `idx_monitor_event_entity` (`entity_type`, `entity_key`),
  KEY `idx_monitor_event_business_ref` (`business_ref_type`, `business_ref_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通用监控命中事件';

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

CREATE TABLE IF NOT EXISTS `monitor_notify_outbox` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `event_id` BIGINT UNSIGNED NOT NULL,
  `channel` VARCHAR(32) NOT NULL COMMENT 'WECOM/IN_APP/EMAIL',
  `target_type` VARCHAR(32) NOT NULL COMMENT 'WEBHOOK/USER/GROUP',
  `target_id` VARCHAR(300) NOT NULL,
  `target_name` VARCHAR(100) DEFAULT NULL,
  `payload_json` LONGTEXT NOT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/SENDING/SENT/FAILED/DEAD',
  `attempt_count` INT NOT NULL DEFAULT 0,
  `max_attempts` INT NOT NULL DEFAULT 5,
  `next_retry_at` DATETIME DEFAULT NULL,
  `locked_at` DATETIME DEFAULT NULL,
  `locked_by` VARCHAR(100) DEFAULT NULL,
  `sent_at` DATETIME DEFAULT NULL,
  `external_message_id` VARCHAR(200) DEFAULT NULL,
  `error_message` VARCHAR(1000) DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_monitor_notify_target` (`event_id`, `channel`, `target_id`),
  KEY `idx_monitor_notify_dispatch` (`status`, `next_retry_at`, `id`),
  KEY `idx_monitor_notify_event` (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控通知事务发件箱';

CREATE TABLE IF NOT EXISTS `monitor_event_operation_log` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `event_id` BIGINT UNSIGNED NOT NULL,
  `from_status` VARCHAR(20) DEFAULT NULL,
  `to_status` VARCHAR(20) NOT NULL,
  `operator_id` BIGINT DEFAULT NULL,
  `operator_name` VARCHAR(100) NOT NULL DEFAULT 'SYSTEM',
  `operation_note` VARCHAR(1000) DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_monitor_event_operation` (`event_id`, `created_at`),
  KEY `idx_monitor_event_operator` (`operator_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='监控事件处理审计日志';

INSERT INTO `monitor_rule_template` (
  template_code, template_name, category, data_source_code, entity_type,
  execution_mode, default_schedule_seconds, description, status
) VALUES
  ('SMART_PLACEMENT_ORDER', '智能投放收单匹配', 'ORDER_EVENT', 'RT_ORDER_FEATURE', 'ORDER', 'INCREMENTAL_BATCH', 60, '投放成功后按平台、站点、航司、航程、舱位、产品和时间匹配订单', 'ACTIVE'),
  ('ORDER_SEGMENT_THRESHOLD', '订单航段阈值监控', 'ORDER_EVENT', 'RT_ORDER_FEATURE', 'ORDER', 'INCREMENTAL_BATCH', 60, '识别单个订单航段数超过阈值的订单', 'ACTIVE'),
  ('METRIC_THRESHOLD', '经营指标阈值监控', 'METRIC', 'METRIC_SNAPSHOT', 'METRIC', 'SCHEDULED', 300, '按时间窗口判断聚合指标是否超过阈值', 'ACTIVE'),
  ('STATE_TIMEOUT', '业务状态超时监控', 'STATE_TIMEOUT', 'BUSINESS_STATE', 'TASK', 'SCHEDULED', 60, '识别审核、认领、关注和处理超时', 'ACTIVE')
ON DUPLICATE KEY UPDATE
  template_name=VALUES(template_name), category=VALUES(category),
  data_source_code=VALUES(data_source_code), entity_type=VALUES(entity_type),
  execution_mode=VALUES(execution_mode), description=VALUES(description),
  updated_at=CURRENT_TIMESTAMP;

INSERT INTO `monitor_rule_template_field` (
  template_id, field_code, field_name, value_type, allowed_operators,
  required_flag, option_source, sort_no, status
)
SELECT t.id, f.field_code, f.field_name, f.value_type, f.allowed_operators,
       f.required_flag, f.option_source, f.sort_no, 'ACTIVE'
FROM `monitor_rule_template` t
JOIN (
  SELECT 'platform_code' field_code, '平台编码' field_name, 'STRING' value_type, 'EQ,IN' allowed_operators, 0 required_flag, 'SMART_PLACEMENT_DIMENSION' option_source, 10 sort_no
  UNION ALL SELECT 'platform_name','平台名称','STRING','EQ,IN',0,'SMART_PLACEMENT_DIMENSION',20
  UNION ALL SELECT 'site_code','站点编码','STRING','EQ,IN',0,'SMART_PLACEMENT_DIMENSION',30
  UNION ALL SELECT 'site_name','站点名称','STRING','EQ,IN',0,'SMART_PLACEMENT_DIMENSION',40
  UNION ALL SELECT 'airline_code','航司','STRING_SET','IN',1,'SMART_PLACEMENT_DIMENSION',50
  UNION ALL SELECT 'departure_location_codes','出发地','STRING_SET','OVERLAP',0,NULL,55
  UNION ALL SELECT 'departure_airport','出发机场','STRING_SET','IN',0,NULL,60
  UNION ALL SELECT 'departure_city','出发城市','STRING_SET','IN',0,NULL,70
  UNION ALL SELECT 'departure_country','出发国家','STRING_SET','IN',0,NULL,80
  UNION ALL SELECT 'departure_zone','出发大区','STRING_SET','IN',0,NULL,90
  UNION ALL SELECT 'arrival_location_codes','到达地','STRING_SET','OVERLAP',0,NULL,95
  UNION ALL SELECT 'arrival_airport','到达机场','STRING_SET','IN',0,NULL,100
  UNION ALL SELECT 'arrival_city','到达城市','STRING_SET','IN',0,NULL,110
  UNION ALL SELECT 'arrival_country','到达国家','STRING_SET','IN',0,NULL,120
  UNION ALL SELECT 'arrival_zone','到达大区','STRING_SET','IN',0,NULL,130
  UNION ALL SELECT 'flight_nos','航班号','STRING_SET','OVERLAP',0,NULL,150
  UNION ALL SELECT 'cabin_codes','适用/排除舱位','STRING_SET','SUBSET_OF,DISJOINT',0,NULL,160
  UNION ALL SELECT 'product_type','产品类型','STRING_SET','IN',0,'SMART_PLACEMENT_DIMENSION',170
  UNION ALL SELECT 'order_source','订单来源','STRING','EQ,IN',0,NULL,172
  UNION ALL SELECT 'trip_type','航程类型','STRING_SET','IN',0,NULL,173
  UNION ALL SELECT 'journey_type','航段类型','STRING_SET','EQ,IN',0,NULL,175
  UNION ALL SELECT 'order_time','订单时间','DATETIME','BETWEEN',0,NULL,180
  UNION ALL SELECT 'first_departure_time','首段起飞时间','DATETIME','BETWEEN',0,NULL,190
  UNION ALL SELECT 'advance_sale_days','提前销售天数','NUMBER','GTE',0,NULL,195
  UNION ALL SELECT 'estimated_profit_cny','预估利润','NUMBER','GTE,LTE',0,NULL,197
  UNION ALL SELECT 'segment_count','航段数','NUMBER','GT,GTE,LT,LTE,EQ',0,NULL,200
) f ON t.template_code='SMART_PLACEMENT_ORDER'
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
  SELECT 'platform_name' field_code, '平台名称' field_name, 'STRING' value_type, 'EQ,IN' allowed_operators, 0 required_flag, 'SMART_PLACEMENT_DIMENSION' option_source, 10 sort_no
  UNION ALL SELECT 'site_name','站点名称','STRING','EQ,IN',0,'SMART_PLACEMENT_DIMENSION',20
  UNION ALL SELECT 'airline_code','航司','STRING_SET','IN',0,'SMART_PLACEMENT_DIMENSION',30
  UNION ALL SELECT 'product_type','产品类型','STRING_SET','IN',0,'SMART_PLACEMENT_DIMENSION',40
  UNION ALL SELECT 'segment_count','航段数','NUMBER','GT,GTE,LT,LTE,EQ',1,NULL,50
  UNION ALL SELECT 'order_time','订单时间','DATETIME','BETWEEN',0,NULL,60
) f ON t.template_code='ORDER_SEGMENT_THRESHOLD'
ON DUPLICATE KEY UPDATE
  field_name=VALUES(field_name), value_type=VALUES(value_type),
  allowed_operators=VALUES(allowed_operators), required_flag=VALUES(required_flag),
  option_source=VALUES(option_source), sort_no=VALUES(sort_no), status='ACTIVE',
  updated_at=CURRENT_TIMESTAMP;
