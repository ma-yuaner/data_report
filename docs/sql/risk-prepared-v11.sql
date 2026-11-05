-- 显式部署人执行；应用/ETL均不自动建表。目标sibebid，不修改ERP。
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_prepared_order (
 issue_date DATE NOT NULL,
 order_id BIGINT NOT NULL,
 reason_code VARCHAR(120) NOT NULL,
 source_updated_at DATETIME(6) NULL,
 etl_run_id VARCHAR(64) NOT NULL,
 rule_version VARCHAR(120) NOT NULL,
 engine_hash CHAR(64) NOT NULL,
 evidence_hash CHAR(64) NOT NULL,
 result_json LONGTEXT NOT NULL,
 prepared_at DATETIME(6) NOT NULL,
 PRIMARY KEY(issue_date,order_id),
 KEY idx_prepared_order(order_id,issue_date),
 KEY idx_prepared_run(etl_run_id,issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bi_risk_prepared_day (
 issue_date DATE NOT NULL,
 etl_run_id VARCHAR(64) NOT NULL,
 rule_version VARCHAR(120) NOT NULL,
 engine_hash CHAR(64) NOT NULL,
 row_count BIGINT NOT NULL,
 diagnostics_json LONGTEXT NOT NULL,
 prepared_at DATETIME(6) NOT NULL,
 PRIMARY KEY(issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
