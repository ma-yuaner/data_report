-- 综合分析V2 -> V3；只交付，不由应用自动执行。
-- 先备份并核对字段是否已存在，避免重复ADD；不DROP、不删除业务数据。
-- 本文件仅在MySQL连接执行。Hive升级见ETL仓库：
-- data_pipelines/src/ddl/ADS/upgrade_business_profit_dimension_v3.sql
-- policy_operator须已按V2存在。
USE sibebid;
ALTER TABLE bi_business_profit_dimension_day
  ADD COLUMN supplier_name VARCHAR(255) NULL COMMENT '业务实际供应商',
  ADD COLUMN gds_code VARCHAR(100) NULL COMMENT '最终出票GDS；不是原预定GDS';

-- 宽表统一消费字段。由Hive现有产品视图新增列同步填充，不靠空字段启用。
ALTER TABLE bi_order_issue_year ADD COLUMN analysis_gds_code VARCHAR(100) NULL COMMENT '源issue_gds_channel';
ALTER TABLE bi_refund_issue_year ADD COLUMN analysis_gds_code VARCHAR(100) NULL COMMENT '源issue_gds_channel';
ALTER TABLE bi_change_issue_year ADD COLUMN analysis_gds_code VARCHAR(100) NULL COMMENT '源新issue_gds_code，禁止old_issue_gds_code';
ALTER TABLE bi_aux_pur_year ADD COLUMN analysis_gds_code VARCHAR(100) NULL COMMENT '源无GDS，明确NULL，不关联订单推测';

-- 升级后完整重跑原ADS任务，metric_version=v3；按新row_key全量替换MySQL镜像，
-- 不得只UPSERT新行而遗留V2旧键。同步supplier_name/gds_code和analysis_gds_code后再更新应用。
-- DataX等实际调度配置不在仓库，本文件不伪造或直接更改服务器任务。
