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

CREATE TABLE IF NOT EXISTS `sys_role_permission` (
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_role.id',
  `permission_code` VARCHAR(100) NOT NULL COMMENT '权限编码',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`role_id`, `permission_code`),
  KEY `idx_srp_permission` (`permission_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='业务角色权限';

CREATE TABLE IF NOT EXISTS `sys_user_permission` (
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT 'sys_user.id',
  `permission_code` VARCHAR(100) NOT NULL COMMENT '权限编码',
  `effect` VARCHAR(8) NOT NULL COMMENT 'ALLOW额外开启；DENY单独关闭',
  `assigned_by` BIGINT UNSIGNED DEFAULT NULL COMMENT '配置人sys_user.id',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`, `permission_code`),
  KEY `idx_sup_permission` (`permission_code`, `effect`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户功能权限例外配置';

-- 菜单按页面授权；功能权限必须依附于对应页面。
INSERT IGNORE INTO `sys_role_menu` (`role_id`, `menu_code`)
SELECT `id`, 'smart.placement.policies'
FROM `sys_role`
WHERE `role_code` IN ('DATA_ENTRY', 'DATA_MANAGER', 'POLICY_MANAGER', 'POLICY_OPERATOR');

INSERT IGNORE INTO `sys_role_menu` (`role_id`, `menu_code`)
SELECT `id`, 'smart.placement.orders'
FROM `sys_role`
WHERE `role_code` = 'POLICY_OPERATOR';

DELETE rm FROM `sys_role_menu` rm
JOIN `sys_role` r ON r.`id` = rm.`role_id`
WHERE r.`role_code` IN ('DATA_ENTRY', 'DATA_MANAGER', 'POLICY_MANAGER', 'POLICY_OPERATOR')
  AND rm.`menu_code` = 'smart';

INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.edit' FROM `sys_role` WHERE `role_code` = 'DATA_ENTRY';
INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.delete' FROM `sys_role` WHERE `role_code` = 'DATA_ENTRY';
INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.orders.attention' FROM `sys_role` WHERE `role_code` = 'POLICY_OPERATOR';

UPDATE `sys_role`
SET `role_name`='业务经理',
    `description`='数据运营审核通过后，任一业务经理可审核政策可执行性与风险'
WHERE `role_code`='POLICY_MANAGER' AND `role_name`='政策经理';

UPDATE `sys_role`
SET `role_name`='智能业务执行员',
    `description`='认领已审核任务并登记投放结果'
WHERE `role_code`='POLICY_OPERATOR' AND `role_name`='智能政策员';

-- 页面菜单编码示例：analysis.comprehensive、risk.upload、smart.placement.policies。
-- sys_user_menu仅保留兼容历史账号；新配置由sys_user_role -> sys_role_menu继承。
-- 有效功能权限 = 角色固定权限 + sys_user_permission.ALLOW - sys_user_permission.DENY。
