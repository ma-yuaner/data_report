-- ADM normalized storage for a new/unreleased installation.
-- Creates only new middle-platform tables in sibebid; does not read/write ERP tables.
-- adm_case_document is intentionally not used by the application after this DDL.
USE sibebid;

CREATE TABLE IF NOT EXISTS adm_case (
  id VARCHAR(36) NOT NULL,
  version BIGINT UNSIGNED NOT NULL,
  idempotency_key VARCHAR(200) NULL,
  internal_no VARCHAR(50) NOT NULL,
  adm_no VARCHAR(100) NOT NULL,
  supplier_code VARCHAR(200) NULL,
  supplier_name VARCHAR(300) NULL,
  supplier_type VARCHAR(32) NULL,
  status VARCHAR(32) NOT NULL,
  business_category VARCHAR(8) NULL,
  issued_date VARCHAR(10) NULL,
  deadline VARCHAR(40) NULL,
  updated_at VARCHAR(40) NOT NULL,
  voided TINYINT(1) NOT NULL DEFAULT 0,
  open_remediation TINYINT(1) NOT NULL DEFAULT 0,
  payload JSON NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_adm_case_idempotency (idempotency_key),
  UNIQUE KEY uk_adm_case_internal_no (internal_no),
  KEY idx_adm_case_adm_no (adm_no),
  KEY idx_adm_case_status_update (status,updated_at),
  KEY idx_adm_case_supplier_date (supplier_code,issued_date),
  KEY idx_adm_case_category_update (business_category,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM normalized main case';

CREATE TABLE IF NOT EXISTS adm_case_line (
  id VARCHAR(36) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_internal_no VARCHAR(80) NOT NULL,
  line_order INT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL,
  order_no VARCHAR(200) NULL,
  owner_id VARCHAR(100) NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_adm_line_internal_no (line_internal_no),
  UNIQUE KEY uk_adm_line_case_order (case_id,line_order),
  KEY idx_adm_line_case_status (case_id,status),
  KEY idx_adm_line_order_no (order_no),
  KEY idx_adm_line_owner_status (owner_id,status),
  CONSTRAINT fk_adm_line_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM order lines';

CREATE TABLE IF NOT EXISTS adm_case_attachment (
  id VARCHAR(36) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_id VARCHAR(36) NULL,
  category VARCHAR(32) NULL,
  created_at VARCHAR(40) NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (id),
  KEY idx_adm_attachment_case_line (case_id,line_id),
  CONSTRAINT fk_adm_attachment_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM attachment metadata';

CREATE TABLE IF NOT EXISTS adm_case_event (
  id VARCHAR(36) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_id VARCHAR(36) NULL,
  action VARCHAR(64) NULL,
  occurred_at VARCHAR(40) NULL,
  event_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (id),
  KEY idx_adm_event_case_order (case_id,event_order),
  KEY idx_adm_event_line_time (line_id,occurred_at),
  CONSTRAINT fk_adm_event_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM immutable business timeline';

CREATE TABLE IF NOT EXISTS adm_case_assignment (
  record_key VARCHAR(200) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  record_kind VARCHAR(20) NOT NULL,
  record_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (record_key),
  KEY idx_adm_assignment_case_kind (case_id,record_kind,record_order),
  CONSTRAINT fk_adm_assignment_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM assignment and handover history';

CREATE TABLE IF NOT EXISTS adm_case_appeal (
  record_key VARCHAR(200) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_id VARCHAR(36) NOT NULL,
  record_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (record_key),
  KEY idx_adm_appeal_line_order (line_id,record_order),
  CONSTRAINT fk_adm_appeal_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM appeal records';

CREATE TABLE IF NOT EXISTS adm_case_recovery (
  record_key VARCHAR(200) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_id VARCHAR(36) NOT NULL,
  record_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (record_key),
  KEY idx_adm_recovery_line_order (line_id,record_order),
  CONSTRAINT fk_adm_recovery_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM recovery history';

CREATE TABLE IF NOT EXISTS adm_case_collection (
  record_key VARCHAR(200) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_id VARCHAR(36) NOT NULL,
  record_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (record_key),
  KEY idx_adm_collection_line_order (line_id,record_order),
  CONSTRAINT fk_adm_collection_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM collection receipts';

CREATE TABLE IF NOT EXISTS adm_case_review (
  record_key VARCHAR(200) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  line_id VARCHAR(36) NOT NULL,
  record_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (record_key),
  KEY idx_adm_review_line_order (line_id,record_order),
  CONSTRAINT fk_adm_review_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM review records';

CREATE TABLE IF NOT EXISTS adm_case_fx_snapshot (
  record_key VARCHAR(200) NOT NULL,
  case_id VARCHAR(36) NOT NULL,
  record_kind VARCHAR(20) NOT NULL,
  record_order INT UNSIGNED NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (record_key),
  KEY idx_adm_fx_case_kind (case_id,record_kind,record_order),
  CONSTRAINT fk_adm_fx_case FOREIGN KEY (case_id) REFERENCES adm_case(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADM immutable FX snapshots';
