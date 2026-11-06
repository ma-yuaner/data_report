-- RISK-NORMAL-CLOSURE-20261106 / V14
-- 只读核验：复用 RiskVerificationCatalog.reason_labels 的实际查询。
-- 将原 parent_code 参数具名展开；无DDL/DML，不读取订单或个人明细。
SELECT det_code, det_cname, etl_run_id
FROM bi_risk_reason_dict
WHERE parent_code = 'PRODUCT_PROFIT_REASON_TYPE'
LIMIT 5001;
-- 完整性检查在原服务执行：重复码/空名/超5000/多批次拒绝。
-- 2026-11-07真实只读130行，R001、RPA000均为“正常业务”。
-- 本查询支撑编码核实，不是正式经营指标，不代表V14清洗已落地。
