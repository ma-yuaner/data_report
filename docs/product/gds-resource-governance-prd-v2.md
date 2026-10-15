# GDS/OTA资源治理与技术上下线协同 PRD V2

- 文档状态：开发与后续变更基线
- 更新日期：2026-10-15
- 产品：企业数据中台
- 业务负责人：数据部马远尔
- 数据库：`sibebid`
- 关联页面：GDS资源治理、OTA渠道质量、监控中心、技术工单

## 1. 建设目标

通过统一数据、可配置规则和技术执行工单，持续降低GDS无效查询，监控OTA接口质量，并形成可审计的异常处置流程。

系统需要回答：

1. 哪个GDS、PCC、平台或接口发生异常；
2. 实际指标是多少，违反了哪条规则；
3. 谁负责确认，是否需要观察、限流或下线；
4. 技术是否已经执行，什么时候执行和恢复；
5. 同一资源重复发生异常时，是否需要延长下线或长期关闭。

## 2. 产品边界

### 2.1 数据中台负责

- 汇总并展示GDS与OTA指标；
- 提供规则配置；
- 自动识别异常并保存证据；
- 分派责任人、催办和升级；
- 生成技术控制指令；
- 接收技术执行结果；
- 记录完整操作日志；
- 生成后续治理分析所需的数据。

### 2.2 技术系统负责

- 读取数据中台输出的控制指令；
- 根据GDS、PCC、平台等对象执行限流、下线、延长下线或恢复；
- 保证同一个工单不会重复执行；
- 将成功、失败、执行时间、恢复时间和技术回执号返回数据中台。

### 2.3 明确不做

- 数据中台不直接修改生产交易系统权限；
- 技术系统不重新计算查定比或判断是否异常；
- 技术系统不读取数据中台内部规则表决定是否下线；
- 业务事实表不存放规则、责任人和流程状态。

## 3. 数据来源

### 3.1 原始数据

接口日志通过Kafka进入Hive ODS：

| 来源 | 查询日志 | 验价/生单日志 | 保存周期 |
|---|---|---|---|
| GDS | `ods_gdssearch_log_inc` | `ods_gds_verify_order_log_inc` | 1天 |
| OTA | `ods_otasearch_log_inc` | `ods_ota_verify_order_pay_log_inc` | 1天 |

### 3.2 标准明细

ODS清洗为5分钟DWD列式明细：

| 来源 | 查询明细 | 验价/生单明细 | 保存周期 |
|---|---|---|---|
| GDS | `dwd_gds_search_carrierdata_5minute` | `dwd_gds_verify_carrierdata_5minute` | 3天 |
| OTA | `dwd_ota_search_carrierdata_5minute` | `dwd_ota_verify_carrierdata_5minute` | 3天 |

DWD负责JSON拆列、去重、状态统一和短期明细追溯。

### 3.3 页面与监控事实表

OTA接口指标同步到：

```text
sibebid.bi_ota_gds_request_day
```

GDS请求与航段先分别汇总，再形成：

```text
sibebid.bi_gds_resource_metric_day
```

GDS服务表包含`MP_TOTAL`与`API_GROUP`两类记录，避免接口分组与航段表直接关联造成分母重复。完整契约见`gds-resource-metric-table-contract.md`。

原请求表：

- `data_source=0`：OTA渠道层；
- OTA与GDS不能混合汇总；
- 航线等高基数明细不常驻MySQL，需要时按短时间范围查询Hive。

核心字段：

| 类型 | 字段 |
|---|---|
| 日期 | `operator_date` |
| 维度 | `data_source`、`ota_code`、`ota_site_code`、`gds_code`、`pcc_code`、`source_api_group` |
| 查询 | `search_request_count_all`、`search_request_success` |
| 验价 | `verify_request_count_all`、`verify_request_success` |
| 生单 | `order_request_count_all`、`order_request_success` |
| GDS正式分母 | 来自`bi_issue_segment_pnr_year.seg_num`，落入GDS服务表`MP_TOTAL`记录 |

## 4. 指标口径

### 4.1 GDS查定比

```text
GDS查定比 = SUM(非MPIS查询量) / SUM(seg_num)
```

- “定”固定使用航段数`seg_num`；
- `source_api_group`不以`_MPIS`结尾的查询计入MP查询量；
- `pnr_num`、`iss_num`、`order_num`不作为正式分母；
- 航段数为空时不告警，防止同步不完整造成误判；
- 航段数为0且查询量大于0时记为无穷大；
- 汇总时重新计算分子/分母，不能平均源表比例。

### 4.2 OTA接口质量

OTA不计算查定比，分别计算：

```text
查询成功率 = 查询成功量 / 查询请求量
验价成功率 = 验价成功量 / 验价请求量
生单成功率 = 生单成功量 / 生单请求量
```

## 5. 用户角色

| 角色 | 主要职责 |
|---|---|
| 数据运营经理 | 配置规则、确认异常、创建技术工单、查看全部流程 |
| 数据分析人员 | 查看指标和异常证据、提交处理建议 |
| 业务部门经理 | 查看分配给自己的异常、说明原因、申请观察 |
| 技术执行人员 | 接收控制指令、执行、回传结果、恢复上线 |
| 公司管理层 | 查看趋势、异常规模和治理结果 |

## 6. 功能清单

### 6.1 GDS资源治理页面

| 功能 | 描述 |
|---|---|
| 总览 | 展示查询量、航段数、查定比、超额查询和接口成功率 |
| 趋势 | 按日查看查定比与查询量变化 |
| 维度对比 | 按GDS、PCC、平台、站点、接口组比较 |
| 分析此项 | 携带当前条件继续缩小问题范围 |
| 日汇总 | 查看当前筛选条件每天的指标 |

### 6.2 OTA渠道质量页面

| 功能 | 描述 |
|---|---|
| 总览 | 展示查询、验价、生单请求量与成功率 |
| 趋势 | 按日查看各接口成功率变化 |
| 维度对比 | 按平台、站点、接口组比较 |
| 分析此项 | 保留条件继续下钻 |
| 日汇总 | 查看每天接口质量 |

### 6.3 规则配置

| 功能 | 描述 |
|---|---|
| GDS查定比规则 | 配置GDS、PCC、平台、站点、接口组、最小查询量和查定比上限 |
| OTA成功率规则 | 配置平台、站点、接口组、最小样本和成功率下限 |
| 分析粒度 | 决定按GDS、PCC、站点或接口组分别产生异常 |
| 生效范围 | 配置开始时间、结束时间、状态和严重等级 |
| 责任人 | 规则命中后自动分派给指定人员 |
| 通知 | 配置站内通知与企业微信群 |
| 版本记录 | 每次修改产生新版本，历史异常保留原口径 |

### 6.4 异常事件

| 功能 | 描述 |
|---|---|
| 自动打标 | 日调度命中规则后生成异常事件 |
| 证据快照 | 保存范围、实际值、阈值和每项条件判断 |
| 幂等 | 相同规则版本、日期、对象不重复建事件 |
| 确认关注 | 责任人确认正在处理 |
| 延后观察 | 填写原因并设置观察截止时间 |
| 逾期升级 | 超过处理时限自动升级并再次通知 |
| 处理结论 | 记录已整改、预期测试、业务接受、误判等结论 |

### 6.5 技术工单

| 功能 | 描述 |
|---|---|
| 创建工单 | 数据部从已确认异常生成正式控制指令 |
| 动作类型 | 限流、临时下线、延长下线、恢复 |
| 阶梯处罚 | 同一对象按历史次数自动延长处置时间 |
| 长期关闭 | 达到配置次数后不再设置自动恢复时间 |
| 技术回执 | 记录接单、执行、成功、失败、回执号和说明 |
| 到期恢复 | 临时控制到期后自动进入待恢复 |
| 审计日志 | 所有状态变化保存操作人、时间和前后状态 |

### 6.6 运行与通知

| 功能 | 描述 |
|---|---|
| 运行日志 | 查看每次调度读取量、规则数、事件数和失败原因 |
| 规则统计 | 查看每条规则的检查结果和缺失字段 |
| 可靠发件箱 | 通知失败后重试，不因企业微信故障丢失事件 |
| 通知群管理 | 配置Webhook、启停群和默认通知对象 |

## 7. 业务流程

```text
ODS接口日志
  → DWD五分钟明细
  → Hive日汇总
  → MySQL OTA日事实表 + GDS指标服务表
  → 页面分析
  → 日规则检查
  → 异常事件
  → 责任人确认/观察
  → 数据部创建技术工单
  → 技术系统读取工单
  → 技术执行限流/下线
  → 技术返回执行结果
  → 数据中台更新事件与审计日志
  → 到期恢复/延长控制/长期关闭
```

## 8. 状态流转

### 8.1 异常事件

```text
OPEN 待处理
  → ACKNOWLEDGED 已确认
  → OBSERVING 观察中
  → ESCALATED 已升级
  → ACTION_PENDING 待技术执行/恢复
  → ACTION_IN_PROGRESS 技术执行中
  → ACTION_APPLIED 控制已生效
  → RESOLVED 已解决
```

### 8.2 技术工单

```text
PENDING 待接收
  → ACCEPTED 已接收
  → EXECUTING 执行中
  → SUCCEEDED 已生效
  → RECOVERY_PENDING 待恢复
  → RECOVERED 已恢复
```

异常分支：

- `FAILED`：技术执行失败，可修正后重新生成工单；
- `CANCELLED`：尚未生效前取消；
- 长期关闭：`permanent_flag=1`，不自动进入恢复。

## 9. 阶梯处置规则

默认配置：

| 同一资源发生次数 | 默认动作窗口 |
|---|---:|
| 第1次 | 60分钟 |
| 第2次 | 240分钟 |
| 第3次 | 1440分钟 |
| 第4次及以后 | 长期关闭 |

具体时长来自`monitor_event_lifecycle_policy.action_durations_json`，长期关闭次数来自`permanent_after_count`，允许后续修改配置而不改ETL。

## 10. 技术部表接口

### 10.1 当前控制指令表

技术部只需要读取：

```text
sibebid.monitor_resource_action_order
```

技术部不读取`monitor_rule`、`monitor_rule_condition`和`monitor_alert_event`判断是否应该下线。数据部生成工单后，代表控制指令已经确认。

技术部读取条件：

```sql
WHERE action_status='PENDING'
```

核心字段：

| 字段 | 用途 |
|---|---|
| `id` | 数据中台内部工单ID |
| `action_no` | 技术幂等执行唯一键 |
| `resource_type` | GDS或OTA |
| `target_key` | 稳定资源对象键 |
| `target_snapshot_json` | GDS、PCC、平台、站点、接口组和异常证据 |
| `action_type` | 限流、下线、延长下线或恢复 |
| `occurrence_no` | 同一资源第几次处置 |
| `permanent_flag` | 是否长期关闭 |
| `planned_start_at` | 计划执行时间 |
| `planned_end_at` | 计划恢复时间；长期关闭为空 |

### 10.2 技术回传原则

最终生产模式采用表接口时，必须满足：

1. `action_no`作为幂等键；
2. 技术只处理自己尚未成功执行的工单；
3. 返回接收、执行中、成功、失败、恢复等状态；
4. 返回技术回执号、说明、失败原因和实际时间；
5. 数据中台负责将回执转换成事件状态和审计日志；
6. 技术不能直接修改规则、异常证据或责任人。

当前版本已经支持技术人员通过数据中台页面/API回填。若确定完全使用数据库表交互，下一版本应新增独立回执表`monitor_resource_action_receipt`：技术只读指令表、只写回执表，数据中台调度消费回执并更新内部状态。这样能避免双方同时更新同一行，并保留完整审计链路。

建议回执表至少包含：

| 字段 | 说明 |
|---|---|
| `action_no` | 对应指令唯一键 |
| `receipt_status` | ACCEPTED/EXECUTING/SUCCEEDED/FAILED/RECOVERED |
| `execution_reference` | 技术变更单号或系统流水号 |
| `execution_note` | 执行说明 |
| `failure_reason` | 失败原因 |
| `accepted_at` | 实际接收时间 |
| `executed_at` | 实际执行时间 |
| `recovered_at` | 实际恢复时间 |
| `returned_at` | 回传时间 |

该回执表是“纯表方式自动上下线”最后一个尚未开发的接口环节，需在技术部确定返回格式后再建表和开发消费任务。

## 11. 调度流程

### 11.1 每日异常识别

在`bi_ota_gds_request_day`同步完成后运行：

```text
monitor_resource_governance_daily.py
```

默认检查昨天，可指定日期补跑。

### 11.2 生命周期与恢复

每10分钟运行：

```text
monitor_resource_event_lifecycle.py
  → monitor_notification_dispatcher.py
```

生命周期任务负责逾期升级和临时控制到期，不重新读取事实表。

### 11.3 技术回执消费

采用独立回执表后新增：

```text
monitor_resource_action_receipt_sync.py
```

负责幂等读取技术回执、更新工单、事件和操作日志。该任务属于下一阶段开发。

## 12. 数据表职责

| 表 | 职责 |
|---|---|
| `bi_ota_gds_request_day` | OTA接口指标与GDS请求上游事实 |
| `bi_issue_segment_pnr_year` | GDS航段、PNR、出票和订单辅助事实 |
| `bi_gds_resource_metric_day` | GDS页面与规则统一服务表，区分MP_TOTAL/API_GROUP |
| `monitor_rule_template` | 规则模板 |
| `monitor_rule_template_field` | 模板字段白名单 |
| `monitor_rule` | 规则主表 |
| `monitor_rule_version` | 规则版本 |
| `monitor_rule_condition` | 规则条件 |
| `monitor_rule_operation_log` | 规则操作日志 |
| `monitor_alert_event` | 异常事件和自动标签 |
| `monitor_event_operation_log` | 异常处理日志 |
| `monitor_event_lifecycle_policy` | 催办、观察和阶梯处罚策略 |
| `monitor_resource_action_order` | 给技术部的控制指令 |
| `monitor_resource_action_operation_log` | 技术工单内部审计日志 |
| `monitor_notify_outbox` | 通知发件箱 |
| `monitor_run_log` | 调度运行日志 |
| `monitor_rule_run_stat` | 规则运行统计 |
| `monitor_resource_action_receipt` | 技术回执接口表，下一阶段待建 |

## 13. 验收标准

1. GDS和OTA页面能读取正式数据并分别计算；
2. 页面能创建、启用、暂停和停用资源规则；
3. 日任务能识别超阈值数据并生成唯一异常事件；
4. 异常证据与手工SQL结果一致；
5. 责任人能确认、观察和填写处理结论；
6. 逾期事件能自动升级并通知；
7. 数据部能创建限流或下线工单；
8. 同一事件不能同时创建两张未结束工单；
9. 技术能够读取完整目标和动作信息；
10. 执行成功后事件显示控制已生效；
11. 临时控制到期后进入待恢复；
12. 恢复后工单、事件与日志状态一致；
13. 重复调度不会重复建事件、工单或通知；
14. 所有时间按Asia/Shanghai记录和展示。

## 14. 后续需求修改方式

### 14.1 原1A监控日报迁移边界

当前版本先完成MP正式查定比、接口组查询/验价/生单成功失败和基础维度下钻。原`gds_1a_search_rate_monitor.py`中的MPIS规则命中、失败原因TOP、航线及去回程间隔覆盖属于第二层诊断数据，后续通过独立诊断数据集接入，不加入`bi_gds_resource_metric_day`主表，避免高基数数据拖慢总览。

完全替代旧日报的目标页面结构为：资源总览、接口分组质量、MPIS质量、失败原因、航线/时段诊断、统一导出与通知。现阶段前三项中的主指标已具备接口，MPIS质量及后续诊断仍需补数据表。

后续需求统一基于本PRD描述，建议按以下格式提出：

```text
修改模块：规则配置 / 异常事件 / 技术工单 / 技术回执 / 治理分析
当前逻辑：
希望修改：
涉及字段：
状态如何流转：
谁可以操作：
是否影响历史数据：
验收示例：
```

PRD发生变化时，需要同步检查页面、API、数据库、ETL、权限、通知、测试和操作文档，不能只修改其中一层。
