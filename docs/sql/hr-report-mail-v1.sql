-- Execute manually after backup in the actual MYSQL_DATABASE (default sibebid).
-- No production DDL is executed by the API. HR payloads are sensitive business data.
USE sibebid;
CREATE TABLE IF NOT EXISTS hr_mail_upload (
 id CHAR(32) NOT NULL PRIMARY KEY,
 owner_id VARCHAR(32) NOT NULL,
 payload JSON NOT NULL,
 KEY idx_hr_upload_owner(owner_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Private HR upload metadata; no mail credentials';
CREATE TABLE IF NOT EXISTS hr_mail_batch (
 id CHAR(32) NOT NULL PRIMARY KEY,
 owner_id VARCHAR(32) NOT NULL,
 version BIGINT UNSIGNED NOT NULL,
 status VARCHAR(24) NOT NULL,
 created_at VARCHAR(40) NOT NULL,
 request_key VARCHAR(80) NOT NULL,
 payload JSON NOT NULL,
 UNIQUE KEY uk_hr_batch_request(request_key),
 KEY idx_hr_batch_owner_time(owner_id,created_at),
 KEY idx_hr_batch_status_time(status,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Frozen HR mail batches, per-mail outcomes and audit events';
CREATE TABLE IF NOT EXISTS hr_mail_preview (
 batch_id CHAR(32) NOT NULL,
 item_id CHAR(32) NOT NULL,
 viewer_id VARCHAR(32) NOT NULL,
 receipt VARCHAR(100) NOT NULL,
 PRIMARY KEY(batch_id,item_id,viewer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Authenticated department preview receipts; no SMTP credentials';
