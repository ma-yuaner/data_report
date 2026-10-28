-- 收单状态与智能明细时效分离。先在中台业务库执行，再更新API和生命周期worker。
-- 仅增加可空列，不改历史状态/金额；可重复执行。
USE sibebid;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_order_outcome' AND column_name='status_source_table')=0, 'ALTER TABLE smart_placement_order_outcome ADD COLUMN `status_source_table` VARCHAR(128) DEFAULT NULL COMMENT ''当前订单状态来源，与智能明细来源独立''', 'SELECT 1');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_order_outcome' AND column_name='status_source_updated_at')=0, 'ALTER TABLE smart_placement_order_outcome ADD COLUMN `status_source_updated_at` DATETIME DEFAULT NULL', 'SELECT 1');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_order_outcome' AND column_name='status_freshness_status')=0, 'ALTER TABLE smart_placement_order_outcome ADD COLUMN `status_freshness_status` VARCHAR(20) DEFAULT NULL COMMENT ''状态来源FRESH/STALE/MISSING''', 'SELECT 1');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SELECT column_name,column_type FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_order_outcome' AND column_name IN ('status_source_table','status_source_updated_at','status_freshness_status');
