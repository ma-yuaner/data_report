-- Operator reviewed execution only, against the configured ADM database (normally sibebid).
-- Do not replace/alter old dashboard or target tables.
CREATE TABLE IF NOT EXISTS adm_operation_document (
    id VARCHAR(120) NOT NULL PRIMARY KEY,
    kind VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL,
    payload JSON NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    INDEX idx_adm_operation_kind_time (kind, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
