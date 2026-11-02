-- 国家/城市范围投放增量；目标 sibebid，MySQL 5.7+/8.0。
-- 先执行本脚本，再部署应用。旧记录默认LEGACY，不重写旧规则或历史命中。
-- 重复执行前核对information_schema.columns；每个字段仅在不存在时新增。
USE `sibebid`;

SET @sp_ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_task' AND column_name='departure_type'), 'SELECT 1', 'ALTER TABLE smart_placement_task ADD COLUMN departure_type VARCHAR(16) NOT NULL DEFAULT ''LEGACY'' COMMENT ''出发地类型：LEGACY/AIRPORT/CITY/COUNTRY''');
PREPARE sp_location_stmt FROM @sp_ddl;
EXECUTE sp_location_stmt;
DEALLOCATE PREPARE sp_location_stmt;
SET @sp_ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_task' AND column_name='arrival_type'), 'SELECT 1', 'ALTER TABLE smart_placement_task ADD COLUMN arrival_type VARCHAR(16) NOT NULL DEFAULT ''LEGACY'' COMMENT ''目的地类型：LEGACY/AIRPORT/CITY/COUNTRY''');
PREPARE sp_location_stmt FROM @sp_ddl;
EXECUTE sp_location_stmt;
DEALLOCATE PREPARE sp_location_stmt;
SET @sp_ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_execution' AND column_name='departure_type'), 'SELECT 1', 'ALTER TABLE smart_placement_execution ADD COLUMN departure_type VARCHAR(16) NOT NULL DEFAULT ''LEGACY'' COMMENT ''实际出发地类型：LEGACY/AIRPORT/CITY/COUNTRY''');
PREPARE sp_location_stmt FROM @sp_ddl;
EXECUTE sp_location_stmt;
DEALLOCATE PREPARE sp_location_stmt;
SET @sp_ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='smart_placement_execution' AND column_name='arrival_type'), 'SELECT 1', 'ALTER TABLE smart_placement_execution ADD COLUMN arrival_type VARCHAR(16) NOT NULL DEFAULT ''LEGACY'' COMMENT ''实际目的地类型：LEGACY/AIRPORT/CITY/COUNTRY''');
PREPARE sp_location_stmt FROM @sp_ddl;
EXECUTE sp_location_stmt;
DEALLOCATE PREPARE sp_location_stmt;

-- 本版本不改sibedb基础表、不自动授予权限、不重跑ETL。
-- 应用账号需具备sibedb.base_airport的SELECT权限；机场字段已在监控模板初始化脚本中提供。
