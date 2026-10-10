-- 角色统一授权：账号只分配角色，角色决定菜单和功能权限。
-- 目标库：sibebid；可重复执行。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `sys_role_menu` (
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_role.id',
  `menu_code` VARCHAR(64) NOT NULL COMMENT '菜单编码',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`role_id`, `menu_code`),
  KEY `idx_sys_role_menu_code` (`menu_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色菜单权限';

-- 现有智能投放四个角色默认继承“智能分析”菜单。
INSERT IGNORE INTO `sys_role_menu` (`role_id`, `menu_code`)
SELECT `id`, 'smart'
FROM `sys_role`
WHERE `role_code` IN ('DATA_ENTRY', 'DATA_MANAGER', 'POLICY_MANAGER', 'POLICY_OPERATOR');

-- sys_user_menu仅保留兼容历史账号；新配置由sys_user_role -> sys_role_menu继承。
