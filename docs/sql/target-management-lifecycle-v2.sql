-- 目标配置生命周期升级：软删除、恢复和简化计划状态。
-- 执行前请先备份 sibebid.biz_target_item / biz_target_plan。
-- MySQL 5.7+/8.0；该脚本只升级结构和状态，不物理删除任何业务数据。
-- 每项 DDL 执行前都会检查 information_schema，可在中断后安全重跑。

USE `sibebid`;

SET @target_lifecycle_ddl = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_target_item' AND COLUMN_NAME = 'deleted_at'
    ),
    'SELECT 1',
    'ALTER TABLE `biz_target_item` ADD COLUMN `deleted_at` DATETIME NULL COMMENT ''软删除时间；为空表示未删除'' AFTER `remark`'
);
PREPARE target_lifecycle_stmt FROM @target_lifecycle_ddl;
EXECUTE target_lifecycle_stmt;
DEALLOCATE PREPARE target_lifecycle_stmt;

SET @target_lifecycle_ddl = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_target_item' AND COLUMN_NAME = 'deleted_by_user_id'
    ),
    'SELECT 1',
    'ALTER TABLE `biz_target_item` ADD COLUMN `deleted_by_user_id` BIGINT UNSIGNED NULL COMMENT ''软删除操作人用户ID'' AFTER `deleted_at`'
);
PREPARE target_lifecycle_stmt FROM @target_lifecycle_ddl;
EXECUTE target_lifecycle_stmt;
DEALLOCATE PREPARE target_lifecycle_stmt;

SET @target_lifecycle_ddl = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_target_item' AND COLUMN_NAME = 'deleted_by_name_snapshot'
    ),
    'SELECT 1',
    'ALTER TABLE `biz_target_item` ADD COLUMN `deleted_by_name_snapshot` VARCHAR(100) NOT NULL DEFAULT '''' COMMENT ''软删除操作人姓名快照'' AFTER `deleted_by_user_id`'
);
PREPARE target_lifecycle_stmt FROM @target_lifecycle_ddl;
EXECUTE target_lifecycle_stmt;
DEALLOCATE PREPARE target_lifecycle_stmt;

SET @target_lifecycle_ddl = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_target_item' AND COLUMN_NAME = 'delete_reason'
    ),
    'SELECT 1',
    'ALTER TABLE `biz_target_item` ADD COLUMN `delete_reason` VARCHAR(1000) NOT NULL DEFAULT '''' COMMENT ''删除原因'' AFTER `deleted_by_name_snapshot`'
);
PREPARE target_lifecycle_stmt FROM @target_lifecycle_ddl;
EXECUTE target_lifecycle_stmt;
DEALLOCATE PREPARE target_lifecycle_stmt;

SET @target_lifecycle_ddl = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_target_item' AND INDEX_NAME = 'idx_target_item_lifecycle'
    ),
    'SELECT 1',
    'ALTER TABLE `biz_target_item` ADD KEY `idx_target_item_lifecycle` (`plan_id`, `deleted_at`, `enabled`)'
);
PREPARE target_lifecycle_stmt FROM @target_lifecycle_ddl;
EXECUTE target_lifecycle_stmt;
DEALLOCATE PREPARE target_lifecycle_stmt;

-- 旧版 PUBLISHED 与当前 ACTIVE 均表示参与 ETL；统一为 ACTIVE，避免双重状态语义。
UPDATE `biz_target_plan`
SET status = 'ACTIVE'
WHERE status = 'PUBLISHED';

-- 验证：第一条应返回 4 个字段，第二条应返回索引的 3 个字段，第三条应返回 0。
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'biz_target_item'
  AND COLUMN_NAME IN ('deleted_at', 'deleted_by_user_id', 'deleted_by_name_snapshot', 'delete_reason')
ORDER BY ORDINAL_POSITION;

SELECT INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'biz_target_item'
  AND INDEX_NAME = 'idx_target_item_lifecycle'
ORDER BY SEQ_IN_INDEX;

SELECT COUNT(*) AS published_plan_count
FROM `biz_target_plan`
WHERE status = 'PUBLISHED';
