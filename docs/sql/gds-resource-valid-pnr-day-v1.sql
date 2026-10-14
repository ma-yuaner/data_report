-- GDS/OTA资源治理 V1：实际有效PNR日汇总表
-- 更新日期：2026-10-14
-- 说明：
-- 1. bi_ota_gds_request_day 继续保存查询、验价和直连生单接口调用指标。
-- 2. order_request_success 仅表示直连生单接口成功次数，不是正式查定比分母。
-- 3. 本表 valid_pnr_count 保存“实际有效PNR”去重数，是正式查定比分母。
-- 4. 规则、责任人、目标值和上下线状态不进入本表，后续使用独立配置/流程表。
-- 5. 任务建议按业务日全量覆盖（DELETE当日后INSERT，或使用临时表原子替换），
--    以便PNR取消、作废或状态变化后可以回算。

USE `sibebid`;

CREATE TABLE IF NOT EXISTS `bi_ota_gds_valid_pnr_day`
(
    `operator_date`        varchar(8)   NOT NULL COMMENT '业务日期，yyyyMMdd；具体按哪个PNR时间字段归属由技术确认',
    `data_source`          tinyint      NOT NULL COMMENT '数据来源：0=OTA，1=GDS；必须与bi_ota_gds_request_day保持一致',
    `ota_code`             varchar(50)  NOT NULL DEFAULT '' COMMENT 'OTA平台编码；无值统一写空字符串',
    `ota_site_code`        varchar(50)  NOT NULL DEFAULT '' COMMENT 'OTA站点编码；无值统一写空字符串',
    `gds_code`             varchar(50)  NOT NULL DEFAULT '' COMMENT 'GDS编码；无值统一写空字符串',
    `pcc_code`             varchar(50)  NOT NULL DEFAULT '' COMMENT 'PCC编码；无值统一写空字符串',
    `source_api_group`     varchar(50)  NOT NULL DEFAULT '' COMMENT '接口分组；源数据无法可靠归属时统一写空字符串',

    `pnr_count_all`        bigint unsigned NOT NULL DEFAULT 0 COMMENT '按PNR唯一键去重后的全部PNR数，仅用于质量核对',
    `valid_pnr_count`      bigint unsigned NOT NULL DEFAULT 0 COMMENT '按正式有效状态过滤并按PNR唯一键去重后的实际有效PNR数，正式查定比分母',
    `invalid_pnr_count`    bigint unsigned NOT NULL DEFAULT 0 COMMENT '无效、取消或作废PNR数，仅用于质量核对',
    `source_row_count`     bigint unsigned NOT NULL DEFAULT 0 COMMENT '去重前源记录数，用于发现重复数据',
    `pnr_key_missing_count` bigint unsigned NOT NULL DEFAULT 0 COMMENT 'PNR唯一键为空的源记录数，不计入有效PNR',

    `source_max_updated_at` datetime     NULL COMMENT '本批源数据最大更新时间，用于判断数据新鲜度',
    `metric_version`       varchar(20)  NOT NULL DEFAULT 'v1' COMMENT '指标口径版本',
    `etl_run_id`           varchar(64)  NULL COMMENT 'ETL运行批次号',
    `create_time`          datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次写入时间',
    `update_time`          datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',

    PRIMARY KEY
        (`operator_date`, `data_source`, `ota_code`, `ota_site_code`, `gds_code`, `pcc_code`, `source_api_group`),
    KEY `idx_valid_pnr_gds`
        (`operator_date`, `data_source`, `gds_code`, `pcc_code`),
    KEY `idx_valid_pnr_ota`
        (`operator_date`, `data_source`, `ota_code`, `ota_site_code`),
    KEY `idx_valid_pnr_api_group`
        (`operator_date`, `data_source`, `source_api_group`)
)
    ENGINE = InnoDB
    DEFAULT CHARSET = utf8mb4
    COLLATE = utf8mb4_unicode_ci
    COMMENT = 'GDS/OTA实际有效PNR日汇总表；查定比正式分母';

-- 正式查定比计算示意（不能直接平均明细行已有比率）：
-- SUM(r.search_request_count_all) / NULLIF(SUM(p.valid_pnr_count), 0)
--
-- 注意：计算某一分析维度时，应先分别聚合请求表和PNR表，再按所选维度关联，
-- 避免因两个事实表粒度不同而发生行数放大。
-- 当查询量>0且有效PNR=0时，API应返回denominator_zero=true，前端显示“∞/无有效PNR”。

-- 技术开发ETL前必须确认以下5项数据契约：
-- A. PNR唯一键：使用哪个字段去重；同一PNR多乘客、多航段不得重复计数。
-- B. 有效状态：哪些状态算有效，取消/作废/失败是否排除，以及历史状态变更如何回算。
-- C. 日期口径：operator_date按PNR创建时间、确认时间还是其他业务时间归属。
-- D. 维度映射：平台/站点/GDS/PCC/API分组从哪些字段取得，无法归属时如何落默认值。
-- E. 数据范围：OTA和GDS是否来自同一订单事实源，是否存在重复PNR或跨来源重复。
