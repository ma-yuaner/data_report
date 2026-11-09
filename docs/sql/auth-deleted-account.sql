CREATE TABLE IF NOT EXISTS auth_deleted_account (
    user_id BIGINT UNSIGNED NOT NULL COMMENT '已删除的中台账号ID，对应sys_user.id',
    deleted_by BIGINT UNSIGNED NOT NULL COMMENT '执行删除的中台账号ID，对应sys_user.id',
    deleted_at DATETIME NOT NULL COMMENT '删除生效时间，业务时区北京时间',
    PRIMARY KEY (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中台账号逻辑删除标记，保留历史业务关联';
