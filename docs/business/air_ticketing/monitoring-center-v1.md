# 通用监控中心 V1

- 更新日期：2026-10-20
- 目标库：`sibebid`
- 页面路由：`/monitoring/*`
- 状态：代码与表结构已完成，生产库建表和 DolphinScheduler 调度待执行

## 1. 设计边界

监控中心将业务配置和运行计算拆开：页面只管理模板、规则、事件及运行状态；调度只维护统一订单特征、匹配规则和发送通知。新增规则不会新增一份 ETL，只有出现新的数据粒度或新来源时才增加采集器。

智能投放成功是首个接入场景。成功登记和规则生成使用同一个 MySQL 事务，任一步失败都会整体回滚；草稿、审核、认领和失败投放不会生成生效规则。

手工配置已开放“订单航段阈值”“GDS查定比日异常”“OTA接口成功率日异常”。订单规则使用分钟级特征；OTA资源规则读取`bi_ota_gds_request_day`，GDS规则读取`bi_gds_resource_metric_day`的MP总体或API分组记录并按业务日检查，不为每条规则新增ETL。其他经营指标和状态超时模板仍只登记目录，待数据采集器上线后再开放创建。

### 1.1 页面信息架构（第一阶段）

监控中心作为统一入口，侧栏拆为八个二级菜单：监控总览、监控任务、预警中心、技术工单、规则模板、运行状态、通知管理和诊断工具。各页面继续复用现有权限、接口和数据表，不迁移、不合并、不删除已有监控规则、事件、通知配置或目标配置。

- “监控任务”承载原“监控规则”列表与新建入口；智能投放成功后仍由原事务自动登记监控任务，人工规则仍使用原创建接口。
- “规则模板”第一阶段只读展示现有`monitor_rule_template`及字段白名单。一套模板代表一类监控ETL和条件协议，可被多条任务复用；模板编辑仍由版本化SQL和服务发布流程维护。
- “预警中心”承载原命中事件；技术工单、通知管理和诊断工具保留原权限及处理链路。
- 旧`/monitoring`入口继续可用并跳转总览；旧`?tab=rules|events|actions|runs|notifications|diagnostic`链接映射到对应二级页面。
- 本阶段已接入的业务自动同步仍只有智能投放等现有链路。后续业务模块接入必须显式实现规则登记事务和来源标识，不能仅凭页面存在宣称“全部业务规则已同步”。

### 1.2 监控驾驶舱与配置边界（2026-10-20确认）

- 监控总览是监控驾驶舱，不再重复展示二级菜单入口。顶部规则、事件、运行异常和待发通知卡片均可跳转到对应页面并携带筛选；下方展示各类监控链路最近运行状态、待优先处理事件和当日高频命中规则。
- “监控运行”用于证明采集、规则匹配、生命周期和通知任务本身持续工作。业务没有预警但运行链路失败时，不能解释为业务正常。
- “问题诊断”用于回答业务对象为何未命中规则或未生成事件；当前订单类规则按规则和OTA订单号逐项核对，后续业务模板需提供各自稳定业务键，不能把所有诊断都强制成OTA订单号。
- 人工新建监控分为“从规则模板创建”和“自定义配置”。自定义配置仍必须选择已经接入的数据集/执行器，因为页面配置不能自动产生新的采集ETL；一次性规则不会自动写成模板。只有字段、粒度、执行器和复用范围均稳定后，才通过版本化发布增加模板。
- 原有“订单航段、GDS查定比（日）、OTA成功率（日）”三个新建入口必须保留；模板目录缺行属于部署不完整，应执行既有幂等模板迁移修复，不能通过隐藏入口改变已有产品能力。
- 一个采集器或公共ETL可以服务多个模板和多条监控任务。模板定义数据协议、允许字段、运算符和执行方式；任务只保存业务范围、阈值、有效期、负责人和通知策略。不得为每条规则创建独立ETL。
- 智能投放继续使用后台系统模板完成自动规则登记，但不在人工规则模板目录或新建入口展示；不得删除其数据库模板或破坏原事务链路。
- 通知管理拆为“通知群、消息模板、通知路由”三个Tab；发送队列和失败记录属于监控运行结果，不属于通知配置。
- 消息模板支持从已注册事件模板复制新增：事件编码、通知渠道和授权字段协议继承自基础模板，用户只能修改模板名称、标题、正文和状态。任意事件编码、任意变量仍禁止创建；新模板通过通知路由选择后才参与发送。

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

资源治理使用并行的日链路：

```text
bi_ota_gds_request_day（OTA接口日事实）
bi_gds_resource_metric_day（GDS MP总体/API分组服务表）
  → monitor_resource_governance_daily.py（每天统一检查全部资源规则）
  → monitor_alert_event / monitor_rule_run_stat
  → monitor_resource_event_lifecycle.py（每10分钟检查处理期限并升级）
  → monitor_notify_outbox
  → 站内事件 / 企业微信
```

调度水位记录在 `monitor_data_cursor`，三类任务的执行量、耗时和异常记录在 `monitor_run_log`。规则级检查量和失败字段汇总写入 `monitor_rule_run_stat`；“匹配诊断”按需对单个订单逐项计算，不把所有订单×规则明细永久落库。事件处理写入 `monitor_event_operation_log`，规则状态调整写入 `monitor_rule_operation_log`。

标准时间契约固定为：`order_create_time` 是业务进单时间，`create_time` 是宽表同步时间。平台和站点按中文名称匹配，避免不同系统编码体系不一致；`manual_flag` 映射为 `order_source`，允许“平台手工订单”“直连订单”，任务未选择时表示不限。源宽表`flight_way`映射为`trip_type`（单程/往返/多程），`journey_type`单独作为航段类型并兼容“直达/直飞”和“中转”；`advance_sale_days`由首段起飞日期与订单日期计算。完整航程不再作为智能投放规则条件。

## 3. 部署顺序

1. 新环境在 `sibebid` 执行 [monitoring-center-schema.sql](../../sql/monitoring-center-schema.sql)；已部署监控中心的环境执行 [monitoring-wecom-notification-v1.sql](../../sql/monitoring-wecom-notification-v1.sql)，并依次确认 [monitoring-order-source-v2.sql](../../sql/monitoring-order-source-v2.sql)、[smart-placement-business-fields-v3.sql](../../sql/smart-placement-business-fields-v3.sql) 与 [resource-governance-daily-monitor-v1.sql](../../sql/resource-governance-daily-monitor-v1.sql) 已执行。
2. 发布 `data_report`，并在角色管理中分配 `monitor.center` 菜单和需要的查看/管理权限。
3. 发布 `data-team-repo` 中 `etl_scripts/automation/monitoring/`。
4. 手工串行执行特征采集、规则匹配、通知发送各一次。
5. 核实 `monitor_run_log` 三类任务均成功后，再建立一分钟串行调度。
6. 新链路稳定前保留旧表和旧脚本；迁移完成后关闭旧通知任务，避免群消息重复。
7. 资源治理日任务在ADS及航段数同步完成后每天运行一次；另将资源事件生命周期任务设为每10分钟运行，再串行执行通知发送器；页面运行日志分别显示`RESOURCE_DAILY`和`RESOURCE_LIFECYCLE`。
8. 已有环境执行[resource-governance-event-lifecycle-v4.sql](../../sql/resource-governance-event-lifecycle-v4.sql)，补齐责任人、处理时限、观察期、升级级别和通知阶段幂等键。
9. 执行[resource-governance-action-work-order-v5.sql](../../sql/resource-governance-action-work-order-v5.sql)，补齐限流/下线/恢复技术工单、回执审计、阶梯时长与工单权限；原资源生命周期任务继续每10分钟运行，并负责将已到期临时控制转入待恢复。

## 4. 上线前必须确认

- 新订单源表必须包含未出票订单，不能继续使用只筛选 `issue_ticket_time IS NOT NULL` 的旧口径；
- 确认稳定订单键、真实进单时间和可单调推进的更新时间字段；
- 生产消息默认写站内事件；管理员在“监控中心→通知群”保存真实Webhook并勾选“自动用于智能投放收单”后，已有与新建智能投放规则都会增加企业微信通知；
- Webhook只在数据库保存，接口和页面只显示掩码；企业微信真实@人员必须填写企业微信用户ID或手机号，群名称本身不能完成@；
- 企业微信和站内通知共用`monitor_notify_outbox`，网络失败按指数退避重试，规则匹配事务不直接调用外部网络；
- 三段任务必须串行，不允许并行，也不要每条规则分别建立调度；
- 首次默认只回看 24 小时。历史回补必须单独执行并记录范围。
- 新激活规则首次运行自动回看近24小时已采集特征；之后仍只走全局增量水位。

## 5. 资源治理技术工单

资源异常确认需要技术执行时，不再把“待技术执行”当作已解决。数据部在事件中生成工单，系统按同一资源历史处置次数计算本次时长；技术执行人依次接单、开始、成功或失败回执。执行成功后事件进入“控制已生效”，临时控制到期由生命周期任务自动转为“待恢复”，技术确认恢复后事件重新进入复核状态。长期关闭没有自动到期时间，后续需通过恢复申请审批链路处理。

工单权限拆为`monitor.action.view`与`monitor.action.manage`。升级SQL只让已有事件查看角色继承工单查看权限；技术执行角色必须在账号管理中明确授予`monitor.action.manage`，避免数据经理代替技术人员回写执行结果。管理员始终拥有全部权限。

调度脚本的具体命令和参数见 `data-team-repo/etl_scripts/automation/monitoring/README.md`。
## 通知模型与花名册（2026-10-13）

站外通知拆成三层：通知群端点、消息模板、事件路由。路由决定“哪类事件使用哪个模板、发送到哪个群、动态@哪类负责人”；人员身份不在通知群中重复维护，而由`sys_user_employee_binding`把数据中台账号映射到ERP`sibebd.system_user`。ERP可使用独立的`ERP_MYSQL_*`连接；绑定时保存`wechat_id/mobilephone`快照，ERP可用时读取最新身份，临时不可用时使用已绑定快照，避免阻断已生成通知。

企业微信默认模板采用最小必要信息，只提示登录数据中台处理，不包含订单号、乘客、航程、利润等业务明细。实际模板版本、解析后的收件人和发送内容快照写入`monitor_notify_delivery_context`供审计。Webhook只保存在通知端点表，发件箱只保存端点ID。

部署顺序：先执行`smart-placement-lifecycle-notification-v2.sql`，确认应用账号可只读ERP花名册所需字段，再在“监控中心 → 通知群”配置端点、模板与路由。
