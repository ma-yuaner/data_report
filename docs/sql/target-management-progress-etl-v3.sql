-- 目标进度ETL V3：缺失数据必须保存为NULL，不得借用0占位。
-- 目标库：sibebid。脚本幂等，可重复执行。

ALTER TABLE dws_target_metric_day
    MODIFY actual_value DECIMAL(20,4) NULL
        COMMENT '真实指标值；源数据缺失时为NULL，不得写0';

ALTER TABLE ads_target_progress_day
    MODIFY actual_today DECIMAL(20,4) NULL
        COMMENT '当日真实完成；待ETL时为NULL',
    MODIFY actual_cumulative DECIMAL(20,4) NULL
        COMMENT '累计真实完成；待ETL时为NULL',
    MODIFY remaining_value DECIMAL(20,4) NULL
        COMMENT '剩余目标；完成数缺失时为NULL';
