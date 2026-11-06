-- Dedicated team review tables. Deploy explicitly to approved sibebid; no ERP changes.
-- Preserve all existing automatic results, samples and legacy cases.
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_followup_cases (
 id CHAR(32) NOT NULL PRIMARY KEY,
 version INT NOT NULL,
 conclusion VARCHAR(20) NOT NULL,
 disposition VARCHAR(20) NOT NULL,
 state VARCHAR(20) NOT NULL,
 assignee VARCHAR(80) NOT NULL,
 next_at VARCHAR(40) NULL,
 first_seen TINYINT NOT NULL DEFAULT 0,
 special TINYINT NOT NULL DEFAULT 0,
 body LONGTEXT NOT NULL,
 updated_at VARCHAR(40) NOT NULL,
 KEY ix_risk_case_pool (conclusion,disposition,state),
 KEY ix_risk_case_follow (assignee,state,next_at),
 KEY ix_risk_case_updated (updated_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bi_risk_order_reviews (
 order_id VARCHAR(40) NOT NULL,
 issue_date DATE NOT NULL,
 version INT NOT NULL,
 case_id CHAR(32) NULL,
 body LONGTEXT NOT NULL,
 PRIMARY KEY (order_id,issue_date),
 KEY ix_risk_review_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bi_risk_followup_events (
 seq BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 id CHAR(32) NOT NULL UNIQUE,
 case_id CHAR(32) NULL,
 order_id VARCHAR(40) NULL,
 issue_date DATE NULL,
 body LONGTEXT NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY ix_risk_event_case (case_id,seq),
 KEY ix_risk_event_order (order_id,issue_date,seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bi_risk_review_policies (
 id CHAR(32) NOT NULL PRIMARY KEY,
 body LONGTEXT NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bi_risk_followup_requests (
 id VARCHAR(80) NOT NULL PRIMARY KEY,
 actor VARCHAR(80) NOT NULL,
 digest CHAR(64) NOT NULL,
 response LONGTEXT NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
