CREATE TABLE IF NOT EXISTS sibebid.bi_change_sla_rule_revision (
    revision BIGINT UNSIGNED NOT NULL COMMENT '规则修订号，0 为事务锁行，正数为整版配置',
    records JSON NOT NULL COMMENT 'T43 展示及编辑所需的完整平台配置快照',
    rules JSON NOT NULL COMMENT '216 读取的平台与四类时限快照',
    effective_from_ms BIGINT UNSIGNED NOT NULL COMMENT '规则生效时点，UTC Unix 毫秒，锁行填0',
    updated_by VARCHAR(255) NOT NULL COMMENT '保存或导入此修订的 T43 操作者标识',
    PRIMARY KEY (revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='改签 SLA 共享规则修订台账，每行保存一版完整配置';

INSERT INTO sibebid.bi_change_sla_rule_revision (revision, records, rules, effective_from_ms, updated_by)
VALUES (0, JSON_ARRAY(), JSON_ARRAY(), 0, '')
ON DUPLICATE KEY UPDATE revision=0;
