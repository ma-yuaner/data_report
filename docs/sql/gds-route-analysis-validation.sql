-- GDS航线诊断数据验证（Hive SQL）
-- 页面日期2026-10-18对应分区dt='20261018'；不要按operator_date='2026-10-18'过滤。
-- 页面首次进入只加载筛选项，选择GDS/PCC/平台/站点/通道/接口组/航线之一后才扫描航线数据。

USE lywz;

-- 1. 验证当天是否有GDS航线数据，以及真实日期格式。
SELECT
    dt,
    MIN(operator_date) AS min_operator_date,
    MAX(operator_date) AS max_operator_date,
    COUNT(1) AS row_count,
    SUM(api_request_count_all) AS request_count
FROM dws_gds_airroute_day
WHERE dt = '20261018'
  AND (TRIM(data_source) = '1' OR UPPER(TRIM(data_source)) = 'GDS')
GROUP BY dt;

-- 2. 页面下拉选项来源。此SQL有结果时，GDS/PCC/平台/站点/接口组下拉应有值。
SELECT DISTINCT
    TRIM(gds_code) AS gds_code,
    TRIM(pcc_code) AS pcc_code,
    TRIM(ota_code) AS ota_code,
    TRIM(ota_site_code) AS ota_site_code,
    TRIM(source_api_group) AS source_api_group
FROM dws_gds_airroute_day
WHERE dt = '20261018'
  AND (TRIM(data_source) = '1' OR UPPER(TRIM(data_source)) = 'GDS')
LIMIT 2000;

-- 3. 模拟页面选择GDS=1A后的航线查询。
SELECT
    airroute_code,
    dep_city,
    arr_city,
    gds_code,
    pcc_code,
    ota_code,
    ota_site_code,
    source_api_group,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) = 'search'
        THEN api_request_count_all ELSE 0 END) AS search_requests,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) = 'search'
        THEN api_request_success ELSE 0 END) AS search_success,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) = 'search'
        THEN api_request_error ELSE 0 END) AS search_error,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) = 'verify'
        THEN api_request_count_all ELSE 0 END) AS verify_requests,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) = 'verify'
        THEN api_request_success ELSE 0 END) AS verify_success,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) IN ('ordercreate', 'order')
        THEN api_request_count_all ELSE 0 END) AS order_requests,
    SUM(CASE WHEN LOWER(TRIM(COALESCE(api_method, ''))) IN ('ordercreate', 'order')
        THEN api_request_success ELSE 0 END) AS order_success,
    MAX(operator_mintes_max) AS source_updated_at
FROM dws_gds_airroute_day
WHERE dt = '20261018'
  AND (TRIM(data_source) = '1' OR UPPER(TRIM(data_source)) = 'GDS')
  AND COALESCE(TRIM(airroute_code), '') <> ''
  AND TRIM(gds_code) = '1A'
GROUP BY
    airroute_code,
    dep_city,
    arr_city,
    gds_code,
    pcc_code,
    ota_code,
    ota_site_code,
    source_api_group
ORDER BY search_requests DESC
LIMIT 100;
