-- 企业数据中心本地账号认证表。目标库：sibebid。
-- 应用默认可自动执行同等DDL；MySQL应用账号无建表权限时手工执行本文件。
USE `sibebid`;

-- 账号主数据直接复用既有sys_user；本表只补充登录安全状态，不改sys_user结构。
CREATE TABLE IF NOT EXISTS `auth_user_security` (
  `user_id` int NOT NULL,
  `must_change_password` tinyint(1) NOT NULL DEFAULT 0,
  `failed_attempts` int NOT NULL DEFAULT 0,
  `locked_until` datetime NULL,
  `password_changed_at` datetime NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`user_id`),
  KEY `idx_auth_user_security_lock` (`locked_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='sys_user登录安全扩展';

CREATE TABLE IF NOT EXISTS `auth_session` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `token_hash` char(64) NOT NULL,
  `csrf_token_hash` char(64) NOT NULL,
  `created_at` datetime NOT NULL,
  `last_seen_at` datetime NOT NULL,
  `absolute_expires_at` datetime NOT NULL,
  `revoked_at` datetime NULL,
  `ip_address` varchar(64) NULL,
  `user_agent` varchar(500) NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_auth_session_token` (`token_hash`),
  KEY `idx_auth_session_user_active` (`user_id`,`revoked_at`),
  KEY `idx_auth_session_expiry` (`absolute_expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据中心服务端登录会话';

CREATE TABLE IF NOT EXISTS `auth_audit_log` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NULL,
  `username` varchar(64) NULL,
  `action` varchar(64) NOT NULL,
  `success` tinyint(1) NOT NULL,
  `ip_address` varchar(64) NULL,
  `user_agent` varchar(500) NULL,
  `detail_json` text NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_auth_audit_created` (`created_at`),
  KEY `idx_auth_audit_user` (`user_id`,`created_at`),
  KEY `idx_auth_audit_action` (`action`,`success`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据中心认证审计日志';
