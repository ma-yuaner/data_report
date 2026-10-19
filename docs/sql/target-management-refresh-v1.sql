-- 目标进度“立即更新”运行记录表。
-- 目标库：sibebid。脚本幂等，可重复执行。

CREATE TABLE IF NOT EXISTS target_etl_run (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '运行ID',
    trigger_type VARCHAR(16) NOT NULL DEFAULT 'MANUAL' COMMENT '触发类型：MANUAL',
    status VARCHAR(16) NOT NULL COMMENT 'QUEUED/RUNNING/SUCCEEDED/FAILED',
    requested_by_user_id BIGINT NULL COMMENT '触发账号ID',
    requested_by_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '触发人快照',
    requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提交时间',
    started_at DATETIME NULL COMMENT '开始时间',
    finished_at DATETIME NULL COMMENT '完成时间',
    data_through_date DATE NULL COMMENT '本次刷新数据截止业务日',
    processed_dates INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '处理业务日数量',
    dws_rows INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '写入DWS行数',
    ads_rows INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '写入ADS行数',
    error_message VARCHAR(1000) NULL COMMENT '失败原因',
    PRIMARY KEY (id),
    KEY idx_target_etl_run_status_requested (status, requested_at),
    KEY idx_target_etl_run_requested_at (requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='目标进度ETL手动运行记录';
