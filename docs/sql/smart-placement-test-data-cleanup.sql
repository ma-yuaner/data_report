-- 智能投放测试数据清理脚本
-- 目标库：sibebid
-- 用途：上线正式使用前，清空测试期间产生的投放政策、审核/执行记录、收单结果、监控规则及运行痕迹。
-- 警告：TRUNCATE 会立即提交且不可回滚。请先确认当前连接指向需要清理的环境，并按需备份。
-- 保留内容：账号/角色/菜单、ERP花名册绑定、通知群、通知模板、通知路由、监控规则模板、智能SLA配置。
-- 同样保留：rt_order_monitor_feature（分钟级订单特征缓存），避免清理后重新回放全部宽表。

USE `sibebid`;

SET FOREIGN_KEY_CHECKS = 0;

-- 通知发送结果与监控命中事件
TRUNCATE TABLE `monitor_notify_outbox`;
TRUNCATE TABLE `monitor_event_operation_log`;
TRUNCATE TABLE `monitor_alert_event`;

-- 智能收单结果和业务操作日志
TRUNCATE TABLE `smart_placement_operation_log`;
TRUNCATE TABLE `smart_placement_order_match`;

-- 智能投放流程数据
TRUNCATE TABLE `smart_placement_execution`;
TRUNCATE TABLE `smart_placement_review`;
TRUNCATE TABLE `smart_placement_task`;

-- 监控规则及运行痕迹；规则模板、字段模板和通知配置不清理
TRUNCATE TABLE `monitor_rule_run_stat`;
TRUNCATE TABLE `monitor_run_log`;
TRUNCATE TABLE `monitor_data_cursor`;
TRUNCATE TABLE `monitor_rule_operation_log`;
TRUNCATE TABLE `monitor_rule_condition`;
TRUNCATE TABLE `monitor_rule_version`;
TRUNCATE TABLE `monitor_rule`;

SET FOREIGN_KEY_CHECKS = 1;

-- 清理结果核对：以下计数均应为0
SELECT
  (SELECT COUNT(*) FROM `smart_placement_task`) AS placement_tasks,
  (SELECT COUNT(*) FROM `smart_placement_order_match`) AS placement_matches,
  (SELECT COUNT(*) FROM `monitor_rule`) AS monitor_rules,
  (SELECT COUNT(*) FROM `monitor_alert_event`) AS monitor_events,
  (SELECT COUNT(*) FROM `monitor_notify_outbox`) AS notify_outbox;
