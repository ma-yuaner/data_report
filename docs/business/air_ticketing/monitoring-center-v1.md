# 通用监控中心 V1

- 更新日期：2026-10-12
- 目标库：`sibebid`
- 页面路由：`/monitoring`
- 状态：代码与表结构已完成，生产库建表和 DolphinScheduler 调度待执行

## 1. 设计边界

监控中心将业务配置和运行计算拆开：页面只管理模板、规则、事件及运行状态；调度只维护统一订单特征、匹配规则和发送通知。新增规则不会新增一份 ETL，只有出现新的数据粒度或新来源时才增加采集器。

智能投放成功是首个接入场景。成功登记和规则生成使用同一个 MySQL 事务，任一步失败都会整体回滚；草稿、审核、认领和失败投放不会生成生效规则。

手工配置当前只开放“订单航段阈值”，因为它使用已经接入的分钟订单特征。经营指标和状态超时模板先登记在模板目录中，待对应数据采集器上线后再开放创建，避免创建无法运行的假规则。

## 2. 运行链路

```text
订单宽表增量
  → rt_order_monitor_feature（分钟级标准特征）
  → monitor_rule / monitor_rule_version / monitor_rule_condition
  → monitor_alert_event（幂等事件）
  → smart_placement_order_match（智能投放业务处理）
  → monitor_notify_outbox（可靠通知、失败重试）
  → 站内通知 / monitor_notify_endpoint（企业微信群机器人与默认@人员）
```

调度水位记录在 `monitor_data_cursor`，三类任务的执行量、耗时和异常记录在 `monitor_run_log`。规则级检查量和失败字段汇总写入 `monitor_rule_run_stat`；“匹配诊断”按需对单个订单逐项计算，不把所有订单×规则明细永久落库。事件处理写入 `monitor_event_operation_log`，规则状态调整写入 `monitor_rule_operation_log`。

标准时间契约固定为：`order_create_time` 是业务进单时间，`create_time` 是宽表同步时间。平台和站点按中文名称匹配，避免不同系统编码体系不一致；`manual_flag` 映射为 `order_source`，允许“平台手工订单”“直连订单”，任务未选择时表示不限。源宽表`flight_way`映射为`trip_type`（单程/往返/多程），`journey_type`单独作为航段类型并兼容“直达/直飞”和“中转”；`advance_sale_days`由首段起飞日期与订单日期计算。完整航程不再作为智能投放规则条件。

## 3. 部署顺序

1. 新环境在 `sibebid` 执行 [monitoring-center-schema.sql](../../sql/monitoring-center-schema.sql)；已部署监控中心的环境执行 [monitoring-wecom-notification-v1.sql](../../sql/monitoring-wecom-notification-v1.sql)，并依次确认 [monitoring-order-source-v2.sql](../../sql/monitoring-order-source-v2.sql) 与 [smart-placement-business-fields-v3.sql](../../sql/smart-placement-business-fields-v3.sql) 已执行。
2. 发布 `data_report`，并在角色管理中分配 `monitor.center` 菜单和需要的查看/管理权限。
3. 发布 `data-team-repo` 中 `etl_scripts/automation/monitoring/`。
4. 手工串行执行特征采集、规则匹配、通知发送各一次。
5. 核实 `monitor_run_log` 三类任务均成功后，再建立一分钟串行调度。
6. 新链路稳定前保留旧表和旧脚本；迁移完成后关闭旧通知任务，避免群消息重复。

## 4. 上线前必须确认

- 新订单源表必须包含未出票订单，不能继续使用只筛选 `issue_ticket_time IS NOT NULL` 的旧口径；
- 确认稳定订单键、真实进单时间和可单调推进的更新时间字段；
- 生产消息默认写站内事件；管理员在“监控中心→通知群”保存真实Webhook并勾选“自动用于智能投放收单”后，已有与新建智能投放规则都会增加企业微信通知；
- Webhook只在数据库保存，接口和页面只显示掩码；企业微信真实@人员必须填写企业微信用户ID或手机号，群名称本身不能完成@；
- 企业微信和站内通知共用`monitor_notify_outbox`，网络失败按指数退避重试，规则匹配事务不直接调用外部网络；
- 三段任务必须串行，不允许并行，也不要每条规则分别建立调度；
- 首次默认只回看 24 小时。历史回补必须单独执行并记录范围。
- 新激活规则首次运行自动回看近24小时已采集特征；之后仍只走全局增量水位。

调度脚本的具体命令和参数见 `data-team-repo/etl_scripts/automation/monitoring/README.md`。
