-- CANCELLED LEGACY PATCH: DO NOT RUN FOR THE NEW NORMALIZED ADM RELEASE.
-- The application now uses adm_case and its child tables from adm-normalized-v1.sql.
-- Adds the human-readable main number used by UI, Excel and FI fallback matching.
-- Existing rows with NULL/missing internalNo are allowed; new rows are unique.
USE sibebid;
ALTER TABLE adm_case_document
 ADD COLUMN internal_no VARCHAR(50)
   GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.internalNo'))) STORED,
 ADD UNIQUE KEY uk_adm_internal_no (internal_no);
