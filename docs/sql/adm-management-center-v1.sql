-- Execute manually on the data platform MySQL business database; the API never runs this DDL.
-- Requires MySQL 5.7+ JSON support; production compatibility and privileges need DBA verification.
-- One aggregate contains lines, attachment metadata, immutable events and closure snapshots.
-- CAS version update makes each business mutation and its audit event atomic.
-- Back up this table AND the ADM attachment directory as one recovery unit.
CREATE TABLE IF NOT EXISTS adm_case_document (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(200) NULL,
    payload JSON NOT NULL,
    UNIQUE KEY uk_adm_create_idempotency (idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM V1 atomic business aggregates; no source ERP writes';
