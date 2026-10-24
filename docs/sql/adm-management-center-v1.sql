-- NEW installation only. Execute manually; never alter ERP adm_records.
-- Existing adm_case_document: use adm-management-center-upgrade-v2.sql instead.
-- Requires MySQL 5.7+ JSON support; production compatibility and privileges need DBA verification.
-- One aggregate contains lines, attachment metadata, immutable events and closure snapshots.
-- CAS version update makes each business mutation and its audit event atomic.
-- Back up this table AND the ADM attachment directory as one recovery unit.
USE sibebid;
CREATE TABLE IF NOT EXISTS adm_case_document (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    version BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(200) NULL,
    payload JSON NOT NULL,
    adm_no VARCHAR(100) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.admNo'))) STORED,
    supplier_code VARCHAR(200) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.supplierCode'))) STORED,
    case_status VARCHAR(32) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.status'))) STORED,
    business_category VARCHAR(8) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.businessCategory'))) STORED,
    issued_date VARCHAR(10) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.issuedDate'))) STORED,
    updated_at VARCHAR(40) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updatedAt'))) STORED,
    UNIQUE KEY uk_adm_create_idempotency (idempotency_key),
    KEY idx_adm_no (adm_no),
    KEY idx_adm_status_update (case_status,updated_at),
    KEY idx_adm_supplier_date (supplier_code,issued_date),
    KEY idx_adm_category_update (business_category,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM V1 atomic business aggregates; no source ERP writes';
