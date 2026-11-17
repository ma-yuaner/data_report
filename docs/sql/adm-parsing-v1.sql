-- Independent ADM parsing tables; apply manually to the configured ADM_MYSQL_DATABASE.
-- Does not alter admwf_case, admwf_case_line or existing analysis tables.
CREATE TABLE IF NOT EXISTS adm_parse_task (
  id CHAR(32) NOT NULL COMMENT 'Server allocated parsing task ID',
  owner_id VARCHAR(32) NOT NULL COMMENT 'Uploading account ID; server-authorized visibility',
  version_no INT NOT NULL COMMENT 'Optimistic concurrency version',
  state VARCHAR(20) NOT NULL COMMENT 'UPLOADED,QUEUED,RUNNING,SUCCEEDED,FAILED',
  updated_at DATETIME NOT NULL COMMENT 'Asia/Shanghai business time',
  request_key VARCHAR(100) NOT NULL COMMENT 'Stable key for retrying one upload request',
  request_hash CHAR(64) NOT NULL COMMENT 'SHA256 of ordered file names and content hashes',
  payload LONGTEXT NOT NULL COMMENT 'Versioned original file metadata, extracted segments, candidate JSON, issues and history; no API secrets',
  PRIMARY KEY (id),
  UNIQUE KEY uk_adm_parse_owner_request (owner_id, request_key),
  KEY idx_adm_parse_owner (owner_id, updated_at),
  KEY idx_adm_parse_state (state, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Independent ADM material parsing tasks, no automatic business acceptance';
