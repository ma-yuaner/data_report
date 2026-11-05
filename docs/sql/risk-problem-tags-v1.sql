-- Explicit deployment only. Shared among existing administrators; no ERP writes.
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_problem_types (
 id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 name VARCHAR(60) NOT NULL,
 name_key VARCHAR(120) COLLATE utf8mb4_bin NOT NULL,
 created_by VARCHAR(19) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(id), UNIQUE KEY uq_risk_problem_type_name(name_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS bi_risk_order_problem_tags (
 id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 order_id VARCHAR(19) NOT NULL,
 type_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 type_name VARCHAR(60) NOT NULL,
 reason VARCHAR(2000) NOT NULL,
 created_by VARCHAR(19) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 source_snapshot LONGTEXT NOT NULL,
 PRIMARY KEY(id), KEY ix_risk_order_problem_tags(order_id,created_at),
 KEY ix_risk_problem_tag_type(type_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
