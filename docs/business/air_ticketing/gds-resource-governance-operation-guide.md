# GDS/OTA资源治理上线、使用与技术对接说明

- 更新日期：2026-10-15
- 页面：`/resource-governance/gds`、`/resource-governance/ota`、`/monitoring`
- OTA业务事实表：`sibebid.bi_ota_gds_request_day`
- GDS指标服务表：`sibebid.bi_gds_resource_metric_day`
- 适用版本：资源治理日规则 V1 至技术工单 V5

## 1. 当前是否已经闭环

当前已经完成的是“数据识别与技术工单管理闭环”，不是“数据中台直接操作生产系统”的全自动闭环。

| 环节 | 当前状态 | 说明 |
|---|---|---|
| OTA/GDS经营分析 | 已完成 | OTA读取接口日事实，GDS读取MP总体/API分组指标服务表 |
| 规则页面配置 | 已完成 | 可配置GDS查定比、OTA接口成功率、范围、粒度、负责人和通知 |
| 日级自动检查 | 已完成 | 调度读取全部启用规则，不需要一条规则写一份ETL |
| 异常打标与派单 | 已完成 | 命中后生成异常事件，保存条件、实际值、范围和责任人 |
| 逾期催办升级 | 已完成 | 按P0/P1/P2策略自动升级并通知 |
| 限流/下线工单 | 已完成 | 数据部从异常事件创建技术工单，支持阶梯时长和长期关闭 |
| 技术执行回执 | 已完成 | 技术人员可在页面接单、执行、失败、恢复并填写回执 |
| 到期恢复待办 | 已完成 | 临时控制到期后自动转为待恢复并通知技术人员 |
| 直接调用生产系统上下线 | 未接入 | 数据中台不直接修改生产权限，需要技术系统消费工单并执行 |
| 技术系统自动回调 | 未接入 | 当前支持页面回填；机器回调还需要服务账号或签名接口 |
| 长期关闭恢复申请 | 后续版本 | 永久关闭没有自动到期，需增加业务申请和数据部审批 |
| 治理前后效果复盘 | 后续版本 | 需补执行前后快照、压降量和复发率报表 |

所以，第一版可以正式用于“发现异常、配置规则、生成标签、派技术工单、追踪执行、到期恢复”；要实现无人值守自动上下线，还需技术部接入第7节的工单协议。

## 2. 页面业务数据如何分层

OTA页面继续使用`bi_ota_gds_request_day`。GDS页面不能直接把按接口组拆分的请求事实与航段事实关联，因此使用`bi_gds_resource_metric_day`作为统一消费层。规则、异常、流程和通知仍存放在独立监控表中。

必须保证事实表稳定提供：

| 分类 | 字段 |
|---|---|
| 日期与层级 | `operator_date`、`data_source` |
| 分析维度 | `ota_code`、`ota_site_code`、`gds_code`、`pcc_code`、`source_api_group` |
| 查询 | `search_request_count_all`、`search_request_success` |
| 验价 | `verify_request_count_all`、`verify_request_success` |
| 生单 | `order_request_count_all`、`order_request_success` |
| GDS查定比分母 | `bi_gds_resource_metric_day`中`metric_scope='MP_TOTAL'`的`seg_num` |

口径固定为：

```text
GDS查定比 = SUM(非MPIS查询量) / SUM(seg_num)
```

`API_GROUP`记录只分析各接口组的请求、成功、失败和成功率，不携带航段。`pnr_num`、`iss_num`和`order_num`只作为辅助指标，不参与正式查定比。详细契约见[GDS资源指标服务表数据契约](gds-resource-metric-table-contract.md)。

## 3. 数据库表用途

### 3.1 规则配置

| 表 | 作用 | 谁维护 |
|---|---|---|
| `monitor_rule_template` | 定义GDS查定比、OTA成功率等规则类型 | 系统SQL注册 |
| `monitor_rule_template_field` | 定义每种模板允许配置的字段、运算符与选项 | 系统SQL注册 |
| `monitor_rule` | 一条可运行规则的主记录、生效期、等级、负责人、通知策略 | 数据部页面配置 |
| `monitor_rule_version` | 保存每次修改后的规则版本和条件快照 | 系统自动生成 |
| `monitor_rule_condition` | 保存GDS、PCC、平台、阈值等具体条件 | 系统自动生成 |
| `monitor_rule_operation_log` | 记录规则创建、启用、暂停、停用和版本变更 | 系统自动记录 |

### 3.2 异常与责任人

| 表 | 作用 | 谁维护 |
|---|---|---|
| `monitor_alert_event` | 命中规则后形成的异常标签、证据、责任人、截止时间和当前状态 | 日检查任务与页面 |
| `monitor_event_operation_log` | 记录确认、观察、升级、解决、忽略、关闭等动作 | 系统自动记录 |
| `monitor_event_lifecycle_policy` | 配置处理时限、升级间隔、各次控制时长及永久关闭次数 | 管理员配置 |
| `monitor_rule_run_stat` | 保存每条规则每次运行的检查量和异常诊断 | 日检查任务 |
| `monitor_run_log` | 保存调度成功、失败、读取量和写入量 | 所有调度任务 |

### 3.3 上下线与技术回执

| 表 | 作用 | 谁维护 |
|---|---|---|
| `monitor_resource_action_order` | 技术执行队列；记录限流、下线、延长下线、时长、对象和回执 | 数据部创建，技术处理 |
| `monitor_resource_action_operation_log` | 技术工单全过程审计日志 | 系统自动记录 |
| `monitor_notify_outbox` | 站内与企业微信可靠发件箱，失败可重试 | 调度自动维护 |
| `monitor_notify_endpoint` | 企业微信群Webhook端点 | 管理员页面配置 |

## 4. 规则如何配置

### 4.1 GDS查定比规则

在“监控中心 → 新增规则”选择“GDS查定比日异常”，配置：

1. GDS：必选，例如`1A`；
2. PCC、平台、站点、接口组：按需要限制范围；
3. 最小查询量：避免小样本误报；
4. 查定比上限：例如`4000`；
5. 异常分析粒度：可选择按GDS或PCC分别产生事件；
6. 等级、负责人、生效时间、通知方式。

规则含义示例：`1A`当日查询量达到最小样本，且`查询量/航段数 > 4000`时，按PCC分别生成异常事件。

### 4.2 OTA成功率规则

选择“OTA接口成功率日异常”，配置平台、可选站点/API组、最小样本和查询/验价/生单成功率下限。OTA规则不允许配置查定比。

### 4.3 通知独立配置

资源检测规则只决定“检查什么”，不再要求创建时永久绑定通知群。执行
`resource-governance-notification-v1.sql`注册资源通知模板后，可在“监控中心 → 智能通知”中独立编辑
`GDS/OTA资源日异常通知`模板，并新增`GDS/OTA资源日异常`路由，随时调整通知群和动态负责人。
修改通知路由不会重建规则，也不会影响历史事件；下一条新异常直接使用最新启用配置。

### 4.3 阶梯处置

`monitor_event_lifecycle_policy`中的默认策略为：

```text
第1次：60分钟
第2次：240分钟
第3次：1440分钟
第4次及以后：长期关闭
```

同一资源通过稳定对象键累计次数，不因业务日期变化而从第一次重新计算。调整该策略只改配置表，无需修改Python代码。

## 5. 自动打标是怎么形成的

1. `monitor_resource_governance_daily.py`按业务日读取OTA事实表或GDS服务表；
2. 一次性加载全部启用规则；
3. 按规则范围和分析粒度重新汇总分子、分母；
4. 命中后写入`monitor_alert_event`；
5. `match_snapshot_json`保存业务日、GDS/PCC/平台范围、实际指标、期望阈值和逐项判断结果；
6. 相同规则版本、业务日、异常对象使用幂等键，只刷新证据，不重复生成事件；
7. 数据部确认需要控制时，在事件上创建`monitor_resource_action_order`，此记录就是技术系统需要消费的控制标签。

事件只是“发现异常”标签，技术工单才是“需要执行限流/下线”的正式指令。技术部不能只根据异常事件直接拉黑。

## 6. 页面使用流程

```text
配置规则
  → 日汇总同步完成
  → 执行资源日检查
  → 监控中心查看异常
  → 数据部确认或延后观察
  → 确认需要控制后创建技术工单
  → 技术接单并执行
  → 技术填写执行回执
  → 临时控制到期自动进入待恢复
  → 技术恢复并回填
  → 事件关闭
```

关键权限：

- 数据部：`monitor.rule.manage`、`monitor.event.manage`；
- 技术查看：`monitor.action.view`；
- 技术处理：`monitor.action.manage`；
- 页面菜单：`monitor.center`。

## 7. 技术系统如何消费工单

### 7.1 当前可直接使用的方式

技术人员登录数据中台“监控中心 → 技术工单”，按以下状态流转：

```text
PENDING 待接单
  → ACCEPTED 已接单
  → EXECUTING 执行中
  → SUCCEEDED 控制已生效
  → RECOVERY_PENDING 待恢复
  → RECOVERED 已恢复
```

失败使用`FAILED`，未执行前取消使用`CANCELLED`。成功、失败、取消和恢复必须填写说明；执行成功建议填写技术变更单号或系统回执号。

### 7.2 技术系统自动接入方式

技术系统只消费`monitor_resource_action_order`，筛选`action_status='PENDING'`。必须使用`action_no`作为幂等键，不能按查询次数重复执行。

技术侧读取待办的最小查询如下；只允许读取，状态回写应走接口，不能直接更新数据库绕过审计日志：

```sql
SELECT id,action_no,resource_type,target_key,target_snapshot_json,
       action_type,occurrence_no,permanent_flag,
       planned_start_at,planned_end_at,updated_at
FROM sibebid.monitor_resource_action_order
WHERE action_status='PENDING'
ORDER BY planned_start_at,id;
```

动作含义：

| `action_type` | 技术系统动作 |
|---|---|
| `RATE_LIMIT` | 对目标资源执行限流，不完全关闭 |
| `DISABLE` | 在计划窗口内临时下线 |
| `EXTEND_DISABLE` | 对已发生过异常的对象延长下线 |
| `RESTORE` | 恢复上线；当前主要通过待恢复状态触发 |

`permanent_flag=1`表示长期关闭，不设置自动恢复时间；必须经过后续恢复申请审批才能重新上线。

技术系统读取：

- `action_no`：控制指令唯一编号；
- `resource_type`：GDS或OTA；
- `target_key`：稳定资源对象键；
- `target_snapshot_json`：GDS、PCC、平台、站点、接口组及命中证据；
- `action_type`：限流、下线或延长下线；
- `permanent_flag`：是否长期关闭；
- `planned_start_at`、`planned_end_at`：计划控制窗口。

执行后不要直接修改异常事件。优先通过数据中台接口回写工单状态：

- 查询待办：`GET /api/v1/monitoring/action-orders?status=PENDING`；
- 接单：`PATCH /api/v1/monitoring/action-orders/{id}/status`，动作`ACCEPT`；
- 开始：同一接口，动作`START`；
- 成功：动作`SUCCESS`，同时提供回执号和说明；
- 失败：动作`FAIL`并提供失败原因；
- 到期恢复：动作`RECOVER`并提供恢复回执。

当前接口使用登录账号权限。无人值守机器调用前还需要新增技术服务账号或签名鉴权；该项未完成前，不要让脚本复用个人账号密码。

## 8. 调度顺序

日汇总同步完成后运行资源日检查：

```bash
python monitor_resource_governance_daily.py
```

生命周期任务每10分钟运行一次，并在其后串行执行通知发送：

```bash
python monitor_resource_event_lifecycle.py
python monitor_notification_dispatcher.py
```

日检查与生命周期任务不能替代事实表同步；生命周期任务也不会重新扫描ADS。

## 9. SQL部署顺序

SQL不会随代码发布自动执行。新环境或尚未建设监控中心的环境按顺序执行：

1. `monitoring-center-schema.sql`；
2. `monitoring-wecom-notification-v1.sql`；
3. `resource-governance-daily-monitor-v1.sql`；
4. `resource-governance-analysis-grain-v2.sql`；
5. `resource-governance-segment-denominator-v3.sql`；
6. `resource-governance-event-lifecycle-v4.sql`；
7. `resource-governance-action-work-order-v5.sql`。

已有环境可以重复执行V1至V5脚本；脚本按幂等方式设计。执行后再运行`resource-governance-deployment-acceptance.sql`验收。不能仅创建`bi_ota_gds_request_day`就认为流程库已完成。

## 10. 上线验收

至少完成以下测试：

1. 创建一条测试GDS规则，并确认页面显示正确阈值、负责人和分析粒度；
2. 用指定业务日运行日检查，确认`monitor_run_log`为成功；
3. 构造一组超过阈值的数据，确认只生成一条事件，重复运行不重复；
4. 确认事件的范围、实际值、阈值与事实表手工SQL一致；
5. 从事件创建技术工单，确认重复创建被拦截；
6. 用技术账号完成接单、开始、成功，确认事件进入“控制已生效”；
7. 把测试工单结束时间调整到当前时间之前，运行生命周期任务，确认进入“待恢复”；
8. 技术确认恢复后，确认工单、事件和两类操作日志状态一致；
9. 检查站内通知和企业微信通知各只发送一次；
10. 停用测试规则并清理测试数据，不删除正式模板。

## 11. 仍需补齐的下一阶段

要达到真正无人值守自动上下线，还需要：

1. 技术服务账号或签名鉴权；
2. 技术系统消费工单并幂等执行的适配器；
3. 技术系统成功、失败、恢复回调；
4. 长期关闭的业务恢复申请与数据部审批；
5. 执行前后指标快照、压降量、复发率和月度治理复盘。

在这五项完成前，系统已经能用于正式流程管理，但不能宣称已经实现生产系统自动上下线。
