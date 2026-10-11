-- 智能投放受控纠错权限增量升级
-- 目标库：sibebid；只补充新权限，不覆盖现有角色、菜单或其他权限配置。

USE `sibebid`;

INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.withdraw'
FROM `sys_role`
WHERE `role_code` = 'DATA_ENTRY';

INSERT IGNORE INTO `sys_role_permission` (`role_id`, `permission_code`)
SELECT `id`, 'smart_placement.cancel'
FROM `sys_role`
WHERE `role_code` = 'DATA_MANAGER';

SELECT r.`role_code`, r.`role_name`, rp.`permission_code`
FROM `sys_role` r
JOIN `sys_role_permission` rp ON rp.`role_id` = r.`id`
WHERE rp.`permission_code` IN ('smart_placement.withdraw', 'smart_placement.cancel')
ORDER BY r.`role_code`, rp.`permission_code`;
