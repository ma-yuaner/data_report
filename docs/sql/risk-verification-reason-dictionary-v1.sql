-- 风控目录V1增量：只新增字典表，不修改已有三表或核查记录。
USE sibebid;
CREATE TABLE IF NOT EXISTS bi_risk_reason_dict (
    parent_code VARCHAR(120) NOT NULL,
    type_code VARCHAR(120) NOT NULL,
    det_code VARCHAR(120) NOT NULL,
    det_cname VARCHAR(500) NOT NULL,
    source_updated_at DATETIME(6) NULL,
    etl_run_id CHAR(32) NOT NULL,
    synced_at DATETIME NOT NULL,
    PRIMARY KEY (parent_code, det_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='ERP盈亏原因字典当前名称；不推断风控规则，不删除历史订单';
