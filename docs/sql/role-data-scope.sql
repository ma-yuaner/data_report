-- 角色数据范围与经理管理成员关系。
-- 目标库：sibebid；兼容 MySQL 5.7+/8.0；可重复执行。
-- 功能权限决定“能做什么”，本脚本的数据范围决定“能看谁的数据”。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `sys_role_data_scope` (
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_role.id',
  `resource_code` VARCHAR(100) NOT NULL COMMENT '数据资源：smart_placement.task/smart_placement.order',
  `scope_type` VARCHAR(20) NOT NULL COMMENT 'SELF/WORKFLOW/MANAGED/ALL',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`role_id`, `resource_code`),
  KEY `idx_role_data_scope_resource` (`resource_code`, `scope_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色数据范围';

CREATE TABLE IF NOT EXISTS `sys_user_manager_relation` (
  `manager_user_id` BIGINT UNSIGNED NOT NULL COMMENT '管理者sys_user.id',
  `member_user_id` BIGINT UNSIGNED NOT NULL COMMENT '被管理成员sys_user.id',
  `resource_code` VARCHAR(100) NOT NULL DEFAULT 'smart_placement' COMMENT '管理关系适用资源',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `assigned_by` BIGINT UNSIGNED DEFAULT NULL COMMENT '配置人sys_user.id',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`manager_user_id`, `member_user_id`, `resource_code`),
  KEY `idx_user_manager_member` (`member_user_id`, `resource_code`, `is_active`),
  KEY `idx_user_manager_manager` (`manager_user_id`, `resource_code`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='业务管理者与成员关系';

-- 默认口径：录入/执行人员看本人；数据运营经理看全部；业务经理看流程相关及管理成员。
INSERT INTO `sys_role_data_scope` (`role_id`, `resource_code`, `scope_type`)
SELECT r.id, x.resource_code,
       CASE r.role_code
         WHEN 'DATA_MANAGER' THEN 'ALL'
         WHEN 'POLICY_MANAGER' THEN 'MANAGED'
         ELSE 'SELF'
       END
FROM `sys_role` r
JOIN (
  SELECT 'smart_placement.task' AS resource_code
  UNION ALL SELECT 'smart_placement.order'
) x
WHERE r.role_code IN ('DATA_ENTRY', 'DATA_MANAGER', 'POLICY_MANAGER', 'POLICY_OPERATOR')
ON DUPLICATE KEY UPDATE `role_id`=VALUES(`role_id`);
-- 已经手工配置过的数据范围不会被重复执行脚本覆盖。

-- scope_type说明：
-- SELF：本人创建、本人认领或本人负责的数据。
-- WORKFLOW：SELF + 当前待本人处理、本人历史处理过的数据。
-- MANAGED：WORKFLOW + sys_user_manager_relation中本人管理成员的数据。
-- ALL：该资源的全部数据。
