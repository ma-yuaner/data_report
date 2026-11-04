-- Deployment operator executes this DDL explicitly on sibebid (MySQL 5.7/8).
-- Application startup and the migration CLI never create or alter these tables.
-- CREATE IF NOT EXISTS does not validate an existing schema: review SHOW CREATE TABLE.
USE sibebid;

CREATE TABLE IF NOT EXISTS bi_risk_auto_jobs (
    seq BIGINT NOT NULL AUTO_INCREMENT,
    id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    owner VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    updated DOUBLE NOT NULL,
    body LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    active_owner VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin
        GENERATED ALWAYS AS (CASE WHEN status IN ('queued','running') THEN owner ELSE NULL END) STORED,
    PRIMARY KEY (seq),
    UNIQUE KEY uq_risk_auto_job_id (id),
    UNIQUE KEY uq_risk_auto_active_owner (active_owner),
    KEY ix_risk_auto_job_owner_seq (owner,seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS bi_risk_auto_results (
    seq BIGINT NOT NULL AUTO_INCREMENT,
    id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    owner VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    order_id VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created DOUBLE NOT NULL,
    body LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (seq),
    UNIQUE KEY uq_risk_auto_result_id (id),
    KEY ix_risk_auto_result_owner_order_seq (owner,order_id,seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS bi_risk_auto_samples (
    seq BIGINT NOT NULL AUTO_INCREMENT,
    id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    owner VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    result_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    body LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (seq),
    UNIQUE KEY uq_risk_auto_sample_id (id),
    KEY ix_risk_auto_sample_owner_result_seq (owner,result_id,seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- Migration sequence (stop ALL old API/workers before apply; keep stopped until cutover):
-- 1. Take operational backup, execute/review DDL above; do not deploy new writers yet.
-- 2. From backend, with the existing application environment loaded:
--    python -m data_report_api.services.risk_auto_migrate --preview
--    python -m data_report_api.services.risk_auto_migrate --apply --source-stopped
-- 3. Check safe count output, then deploy the application and verify as operator.
-- Only auto_jobs/auto_results/auto_samples migrate. Original manual workflow records
-- remain in workflow.sqlite3; neither source rows nor manual history are deleted.
-- Apply creates an online SQLite backup in RISK_VERIFICATION_ROOT/backups on the
-- source volume, then reads that backup. queued/running become failed with an
-- explanation in JSON; they never resume. Existing matching IDs are compared field
-- by field and skipped; any mismatch aborts/rolls back the whole MySQL transaction.
-- Preserve the original file and backup; rollback/cutback requires operators to
-- reconcile any new MySQL writes. Do not restart an old writer alongside new code.
