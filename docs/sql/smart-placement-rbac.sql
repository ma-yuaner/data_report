-- 智能投放岗位权限与存量任务升级
-- 目标库：sibebid；MySQL 5.7+/8.0。
-- 新环境和已经执行过 smart-placement-schema.sql 的环境均可执行。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `sys_role` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '角色ID',
  `role_code` VARCHAR(64) NOT NULL COMMENT '角色编码',
  `role_name` VARCHAR(100) NOT NULL COMMENT '角色名称',
  `description` VARCHAR(500) DEFAULT NULL COMMENT '角色说明',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sys_role_code` (`role_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据中心业务角色';

CREATE TABLE IF NOT EXISTS `sys_role_permission` (
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
  `permission_code` VARCHAR(100) NOT NULL COMMENT '权限编码',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`role_id`, `permission_code`),
  KEY `idx_srp_permission` (`permission_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='业务角色权限';

CREATE TABLE IF NOT EXISTS `sys_user_role` (
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_user.id',
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_role.id',
  `assigned_by` BIGINT UNSIGNED DEFAULT NULL COMMENT '分配人sys_user.id',
  `assigned_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '分配时间',
  PRIMARY KEY (`user_id`, `role_id`),
  KEY `idx_sur_role_user` (`role_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户业务角色';

CREATE TABLE IF NOT EXISTS `sys_role_menu` (
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_role.id',
  `menu_code` VARCHAR(64) NOT NULL COMMENT '菜单编码',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`role_id`, `menu_code`),
  KEY `idx_sys_role_menu_code` (`menu_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色菜单权限';

INSERT INTO `sys_role` (`role_code`, `role_name`, `description`, `is_active`)
VALUES
  ('DATA_ENTRY', '数据录入员', '录入、编辑并提交智能投放机会', 1),
  ('DATA_MANAGER', '数据运营经理', '审核数据口径、样本和预估价值', 1),
  ('POLICY_MANAGER', '政策经理', '审核政策可执行性与风险', 1),
  ('POLICY_OPERATOR', '智能政策员', '认领任务并登记投放结果', 1)
ON DUPLICATE KEY UPDATE
  `role_name` = VALUES(`role_name`),
  `description` = VALUES(`description`),
  `is_active` = VALUES(`is_active`);

INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.create' FROM `sys_role` WHERE `role_code` = 'DATA_ENTRY';
INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.review_data' FROM `sys_role` WHERE `role_code` = 'DATA_MANAGER';
INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.review_policy' FROM `sys_role` WHERE `role_code` = 'POLICY_MANAGER';
INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.claim' FROM `sys_role` WHERE `role_code` = 'POLICY_OPERATOR';
INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.execute' FROM `sys_role` WHERE `role_code` = 'POLICY_OPERATOR';

INSERT IGNORE INTO `sys_role_menu` (`role_id`, `menu_code`)
SELECT `id`, 'smart' FROM `sys_role`
WHERE `role_code` IN ('DATA_ENTRY', 'DATA_MANAGER', 'POLICY_MANAGER', 'POLICY_OPERATOR');

SET @resume_stage_ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'smart_placement_task'
      AND COLUMN_NAME = 'resume_review_stage'
  ),
  'SELECT 1',
  'ALTER TABLE `smart_placement_task` ADD COLUMN `resume_review_stage` VARCHAR(32) DEFAULT NULL COMMENT ''退回修改后重新提交的审核环节：DATA_MANAGER/POLICY_MANAGER'' AFTER `status`'
);
PREPARE resume_stage_statement FROM @resume_stage_ddl;
EXECUTE resume_stage_statement;
DEALLOCATE PREPARE resume_stage_statement;

-- 角色分配由“系统管理 → 账号管理”页面完成，不需要手工维护此表。
