-- V14 分析快照规则版本门禁的实际读取SQL。
-- 应用RiskAutoStore的参数方言为?，须由应用绑定end_date；非直接MySQL控制台脚本。
-- 在隔离SQLite事务适配中执行验证，未对真实MySQL执行本查询。
SELECT snapshot_id, schema_version, checked_at, last_error_code, body
FROM bi_risk_analytics_snapshot
WHERE end_date = ?;
-- body的ruleVersion与engineHash由服务和当前运行时比对，旧规则不能短路返回ready。
-- 仅读取发布元数据，无DDL/DML；完整处理见risk_analytics_snapshot.py。
