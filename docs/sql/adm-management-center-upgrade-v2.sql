-- Existing V1 aggregate table ONLY. Back up before execution. Run once.
-- If some columns already exist, compare SHOW CREATE TABLE and apply only missing clauses.
-- No DROP/TRUNCATE/UPDATE of existing business data; no changes to ERP adm_records.
USE sibebid;
ALTER TABLE adm_case_document
 ADD COLUMN adm_no VARCHAR(100) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.admNo'))) STORED,
 ADD COLUMN supplier_code VARCHAR(200) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.supplierCode'))) STORED,
 ADD COLUMN case_status VARCHAR(32) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.status'))) STORED,
 ADD COLUMN business_category VARCHAR(8) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.businessCategory'))) STORED,
 ADD COLUMN issued_date VARCHAR(10) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.issuedDate'))) STORED,
 ADD COLUMN updated_at VARCHAR(40) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updatedAt'))) STORED,
 ADD KEY idx_adm_no (adm_no),
 ADD KEY idx_adm_status_update (case_status,updated_at),
 ADD KEY idx_adm_supplier_date (supplier_code,issued_date),
 ADD KEY idx_adm_category_update (business_category,updated_at);
