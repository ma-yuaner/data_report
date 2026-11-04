-- 风控核对查询层 V1。由部署人在确认目标库、备份及权限后手工执行。
-- 不连接ERP，不修改ERP索引，不覆盖已有核查SQLite；不包含凭据。
USE sibebid;

CREATE TABLE IF NOT EXISTS bi_risk_order_day (
    issue_date DATE NOT NULL COMMENT '出票业务日，Asia/Shanghai',
    order_id BIGINT NOT NULL COMMENT 'ERP内部订单ID，同日多票只存一单',
    order_no VARCHAR(128) NULL,
    ota_order_no VARCHAR(128) NULL,
    ota_code VARCHAR(64) NULL,
    profit_reason_type VARCHAR(120) NOT NULL COMMENT '源盈亏原因原值，不推断规则结论',
    create_time DATETIME(6) NULL COMMENT '源订单创建时间，保留源小数秒',
    update_time DATETIME(6) NULL COMMENT '源订单更新时间；不是子表完整版本',
    etl_run_id CHAR(32) NOT NULL,
    PRIMARY KEY (issue_date, order_id),
    KEY idx_date_reason_order (issue_date, profit_reason_type, order_id),
    KEY idx_order_date (order_id, issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控核对出票日订单查询索引V1，不含利润或日志';

CREATE TABLE IF NOT EXISTS bi_risk_sync_day (
    issue_date DATE NOT NULL,
    etl_run_id CHAR(32) NOT NULL,
    row_count BIGINT NOT NULL COMMENT '成功日去重后的非空盈亏原因订单数，0也须留痕',
    synced_at DATETIME NOT NULL COMMENT '成功切换时间，Asia/Shanghai',
    PRIMARY KEY (issue_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控日同步成功覆盖；与该日数据同事务更新';

CREATE TABLE IF NOT EXISTS bi_risk_sync_run (
    etl_run_id CHAR(32) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(16) NOT NULL COMMENT 'running/success/failed；异常中断可能保留running',
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    row_count BIGINT NOT NULL DEFAULT 0 COMMENT '本批已成功发布的逐日行数之和',
    error_code VARCHAR(64) NULL COMMENT '安全错误码，不存SQL/配置/订单原文',
    PRIMARY KEY (etl_run_id),
    KEY idx_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控同步执行留痕；部分日成功不冒充全范围成功';
