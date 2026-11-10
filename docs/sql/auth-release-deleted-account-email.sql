-- 目标环境应用库。先通过授权渠道核对被删账号 ID 和邮箱字段约束。
-- 修改下方 NULL 为已核对的单个账号 ID。默认不处理任何记录。
SET @deleted_account_id = NULL;

START TRANSACTION;

UPDATE sys_user AS u
JOIN auth_deleted_account AS d ON d.user_id = u.id
LEFT JOIN sys_user AS occupied
  ON occupied.email = CONCAT('account-', u.id, '@deleted-account.invalid')
 AND occupied.id <> u.id
SET u.email = CONCAT('account-', u.id, '@deleted-account.invalid')
WHERE u.id = @deleted_account_id
  AND u.is_active = 0
  AND COALESCE(u.role, '') <> 'admin'
  AND u.email IS NOT NULL
  AND u.email <> CONCAT('account-', u.id, '@deleted-account.invalid')
  AND occupied.id IS NULL;

SELECT ROW_COUNT() AS released_email_count;

-- 在同一连接核对结果。首次预期为 1，重复执行预期为 0。
-- 确认后执行 COMMIT；结果不符执行 ROLLBACK。
