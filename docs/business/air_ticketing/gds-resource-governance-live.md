# GDS/OTA资源治理 V1 实现说明

- 更新时间：2026-10-14
- 当前状态：资源总览、OTA/GDS分层、趋势、维度连续下钻和日汇总已接入正式项目
- GDS页面：`/resource-governance/gds`
- OTA页面：`/resource-governance/ota`
- GDS API：`GET /api/v1/resource-governance/gds/overview`
- OTA API：`GET /api/v1/resource-governance/ota/overview`
- OTA来源：`sibebid.bi_ota_gds_request_day`
- GDS来源：`sibebid.bi_gds_resource_metric_day`

## 数据粒度

OTA继续使用接口日汇总表；GDS使用由请求事实与航段事实生成的指标服务表：

```text
MP_TOTAL：日期 + 平台 + 站点 + GDS + PCC
API_GROUP：日期 + 平台 + 站点 + GDS + PCC + 接口分组
```

`bi_ota_gds_request_day.data_source=0`为OTA渠道层。GDS服务表的`MP_TOTAL`用于正式查定比，`API_GROUP`用于接口组质量；两个层级不能相加。

## 指标口径

只有GDS资源层计算查定比：

```text
GDS查定比 = SUM(MP查询量) / SUM(seg_num)
```

用户于2026-10-15确认，MP查询量包含`1A`、`1A_NDC`等非`*_MPIS`接口组，分母使用`bi_issue_segment_pnr_year.seg_num`。`pnr_num`与`order_request_success`均不参与正式查定比。航段未同步或部分缺失时页面显示“—”并停止计算；查询量大于0且完整同步后的航段数为0时显示“∞”。OTA渠道层不展示航段查定比。

GDS目标按资源分别配置。首版通过`RESOURCE_GOVERNANCE_GDS_TARGETS`配置，格式如`1A:4000,1G:3000`；默认只配置`1A:4000`。汇总多个GDS时不套用统一目标，筛选具体GDS或查看GDS维度行时才判断达标并计算超额查询。

OTA成功率目标按平台配置，通过`RESOURCE_GOVERNANCE_OTA_SUCCESS_TARGETS`提供JSON，例如`{"携程":{"search":99,"verify":98,"order":95}}`。未配置的平台只展示实际值，不擅自判定达标或异常。

## 页面能力

- GDS资源治理与OTA渠道质量是两个独立菜单，均默认查看本月；
- 支持今日、近7天、本月和自定义日期；
- 支持平台、站点、GDS、PCC和接口分组筛选；
- GDS层展示查询量、航段数、查定比、超额查询和接口成功率；
- GDS层独立展示各`source_api_group`的查询、验价、生单请求量、成功量、失败量和成功率；
- OTA层展示查询、验价、生单的请求量、成功量与成功率；
- 展示查询/验价缓存命中率、平均耗时及验价/生单变价率；
- 查询、验价、生单属于独立接口统计，不伪装成同一批请求的转化漏斗；
- GDS趋势按日重新汇总分子分母，不平均源表比率；
- GDS层支持GDS、PCC、平台、站点和接口分组对比；
- OTA层支持平台、站点和接口分组对比；
- “分析此项”会保留日期和已选条件，在右侧工作区继续按GDS、PCC、平台、站点、接口组逐层定位，并可随时切换查看当前条件的日汇总。
- “导出汇报”按当前日期、筛选条件和分析维度生成Excel，包含管理摘要、日趋势、维度对比；GDS额外包含接口分组质量，可直接作为日常汇报附件。

GDS服务表字段与ETL约束见[GDS资源指标服务表数据契约](gds-resource-metric-table-contract.md)。当前页面和API已经按该契约开发；正式数据出现前需由数据团队完成建表与同步。

## 日异常闭环 V1

首版异常按日检查，复用“监控中心”现有规则、事件、处理状态、运行日志和企业微信通知，不在资源分析页复制一套流程：

- GDS规则按GDS及可选PCC、平台、站点、接口组设置最小查询量和查定比上限；
- OTA规则按平台及可选站点、接口组设置查询、验价或生单成功率下限；
- 每天ADS与航段数同步完成后，由一份调度脚本检查全部规则；
- GDS的`seg_num`存在未同步行时记录运行诊断但不产生异常，防止误报；
- 命中后生成待处理事件并按规则负责人自动分派，可在监控中心确认、延后观察、解决、忽略或关闭，并保留审计日志；
- P0/P1/P2按生命周期策略生成处理期限，逾期任务自动升级、再次通知并显示当前升级等级；
- 选择企业微信群后，异常先可靠写入发件箱，再由通知任务发送，失败不丢事件且可以重试；
- 同一规则、同一业务日和同一范围只生成一个事件，重复运行只刷新证据，不重复轰炸。

部署前依次执行[resource-governance-daily-monitor-v1.sql](../../sql/resource-governance-daily-monitor-v1.sql)、[resource-governance-analysis-grain-v2.sql](../../sql/resource-governance-analysis-grain-v2.sql)、[resource-governance-segment-denominator-v3.sql](../../sql/resource-governance-segment-denominator-v3.sql)和[resource-governance-event-lifecycle-v4.sql](../../sql/resource-governance-event-lifecycle-v4.sql)，调度说明见`data-team-repo/etl_scripts/automation/monitoring/README.md`。

当前已完成“日规则→异常事件→责任人→观察/处理→逾期升级→限流/下线工单→技术回执→到期待恢复→通知”的执行闭环。系统只生成控制指令和记录回执，不直接操作生产交易系统。业务恢复申请审批、治理前后效果快照与月度治理复盘仍属于后续版本。

技术工单部署需执行[resource-governance-action-work-order-v5.sql](../../sql/resource-governance-action-work-order-v5.sql)。数据部从事件生成工单，技术人员在“监控中心→技术工单”接单并回写变更单号和结果；同一事件存在未结束工单时禁止重复创建。

完整部署顺序、库表字典、页面操作、自动打标口径、技术系统消费协议和验收清单见[GDS/OTA资源治理上线、使用与技术对接说明](gds-resource-governance-operation-guide.md)。部署后可执行[资源治理部署验收脚本](../../sql/resource-governance-deployment-acceptance.sql)进行只读核查。
