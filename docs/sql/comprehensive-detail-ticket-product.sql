-- 综合分析宽表产品下钻：MySQL承接表字段与索引。
-- 目标库：sibebid。执行前确认字段尚不存在；历史数据回补完成后再开放产品下钻。
USE `sibebid`;

ALTER TABLE `bi_order_issue_year`
  ADD COLUMN `ticket_product_raw` VARCHAR(150) NULL COMMENT '统一机票产品原始值；Hive出票product_type' AFTER `policy_operator`,
  ADD COLUMN `product_status` VARCHAR(30) NULL COMMENT 'source/missing/conflict' AFTER `ticket_product_raw`;

ALTER TABLE `bi_refund_issue_year`
  ADD COLUMN `ticket_product_raw` VARCHAR(150) NULL COMMENT '统一机票产品原始值；按issue_id+ota_code关联出票' AFTER `policy_operator`,
  ADD COLUMN `product_status` VARCHAR(30) NULL COMMENT 'linked_issue/missing/conflict' AFTER `ticket_product_raw`;

ALTER TABLE `bi_change_issue_year`
  ADD COLUMN `ticket_product_raw` VARCHAR(150) NULL COMMENT '统一机票产品原始值；按issue_id+ota_code关联出票' AFTER `policy_operator`,
  ADD COLUMN `product_status` VARCHAR(30) NULL COMMENT 'linked_issue/missing/conflict' AFTER `ticket_product_raw`;

ALTER TABLE `bi_aux_pur_year`
  ADD COLUMN `ticket_product_raw` VARCHAR(150) NULL COMMENT '统一机票产品原始值；按order_id+ota_code关联出票' AFTER `policy_operator`,
  ADD COLUMN `product_status` VARCHAR(30) NULL COMMENT 'linked_order/missing/conflict' AFTER `ticket_product_raw`;

-- 索引放在历史数据回补后创建，避免回补时反复维护二级索引。
CREATE INDEX `idx_issue_ticket_product_time`
  ON `bi_order_issue_year` (`ota_code`, `ticket_product_raw`, `operator_date`);
CREATE INDEX `idx_refund_ticket_product_time`
  ON `bi_refund_issue_year` (`ota_code`, `ticket_product_raw`, `apply_datetime`);
CREATE INDEX `idx_change_ticket_product_time`
  ON `bi_change_issue_year` (`ota_code`, `ticket_product_raw`, `change_issue_time`);
CREATE INDEX `idx_aux_ticket_product_time`
  ON `bi_aux_pur_year` (`ota_code`, `ticket_product_raw`, `create_time`);
