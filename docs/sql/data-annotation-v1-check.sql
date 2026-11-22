-- 执行位置：中台 MYSQL_DATABASE 对应的 MySQL 库。
-- 只读回读，五表均应存在，所有列都有中文注释，唯一键和外键可追溯。
SELECT TABLE_NAME, ENGINE, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('annotation_project','annotation_member','annotation_sample','annotation_revision','annotation_dataset')
ORDER BY TABLE_NAME;

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('annotation_project','annotation_member','annotation_sample','annotation_revision','annotation_dataset')
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('annotation_project','annotation_member','annotation_sample','annotation_revision','annotation_dataset')
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
