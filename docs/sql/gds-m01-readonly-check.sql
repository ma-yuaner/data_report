-- M01：只读口径核对。尚未在真实Hive执行，不是数据修改或调度脚本。
-- 先单独运行Q0确认列存在及含义；库名lywz按实际确认。
-- 若结构不同，回传结构后调整Q1，不直接运行缺列查询。
-- 推荐scripts/gds_m01_check.py prepare --schema按真实DESCRIBE导出映射列名。
-- 下方Q1为规范字段模板；实际平台列可能为otacode/otasitecode，勿把模板字段直接当生产结构。

-- Q0：源表结构。
DESCRIBE lywz.dwd_gds_search_carrierdata_5minute;

-- Q1：与既有2026-10-29 BKK-TYO明细相同基础筛选。
-- 保留混合旅客、不同接口及原始标记，供分类核对，不预判为普通MP。
-- 日期范围覆盖yyyyMMdd及其后附小时/分钟的字符串分区；实际dt格式由Q0/现有查询确认。
-- records为日志记录，api_subcount_sum仅为候选子接口计数，不称实际外呼。
-- 整份结果导出，不能只导出前若干行；汇总记录数可与33078核对，差异不强行填平。
SELECT
    pcc_code,
    ota_code,
    ota_site_code,
    data_source,
    api_method,
    apimethod,
    source_api_group,
    COALESCE(CAST(gdschannelalias AS STRING), '__NULL__') AS channel_alias_raw,
    COALESCE(CAST(mpisflag AS STRING), '__NULL__') AS mpisflag_raw,
    COALESCE(CAST(ndcflag AS STRING), '__NULL__') AS ndcflag_raw,
    COALESCE(CAST(gdsreal AS STRING), '__NULL__') AS gdsreal_raw,
    hitcacheflag,
    adultnum,
    childnum,
    infantnum,
    flightway,
    COUNT(*) AS records,
    SUM(CASE WHEN successflag = 0 THEN 1 ELSE 0 END) AS success_records,
    SUM(CASE WHEN successflag = 1 THEN 1 ELSE 0 END) AS failure_records,
    SUM(CASE WHEN successflag IS NULL OR successflag NOT IN (0, 1) THEN 1 ELSE 0 END) AS unknown_success_records,
    SUM(apiRequestSubCount) AS api_subcount_sum,
    SUM(CASE WHEN apiRequestSubCount IS NULL OR apiRequestSubCount <= 0 THEN 1 ELSE 0 END) AS invalid_subcount_records,
    SUM(CASE WHEN traceid IS NOT NULL AND LENGTH(TRIM(traceid)) > 0 THEN 1 ELSE 0 END) AS traceid_present_records,
    SUM(CASE WHEN referenceid IS NOT NULL AND LENGTH(TRIM(referenceid)) > 0 THEN 1 ELSE 0 END) AS referenceid_present_records
FROM lywz.dwd_gds_search_carrierdata_5minute
WHERE dt >= '20261029'
  AND dt < '20261030'
  AND gds_code = '1A'
  AND dep_city = 'BKK'
  AND arr_city = 'TYO'
  AND adultnum = 1
  AND datediffdepart BETWEEN 1 AND 179
  AND datediffroundtrip BETWEEN 2 AND 15
GROUP BY
    pcc_code, ota_code, ota_site_code, data_source, api_method, apimethod,
    source_api_group, gdschannelalias, mpisflag, ndcflag, gdsreal,
    hitcacheflag, adultnum, childnum, infantnum, flightway
ORDER BY records DESC;
