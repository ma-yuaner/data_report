# GDS/OTA资源治理 V1 实现说明

- 更新时间：2026-10-14
- 当前状态：资源总览、OTA/GDS分层、趋势、维度连续下钻和日汇总已接入正式项目
- GDS页面：`/resource-governance/gds`
- OTA页面：`/resource-governance/ota`
- GDS API：`GET /api/v1/resource-governance/gds/overview`
- OTA API：`GET /api/v1/resource-governance/ota/overview`
- MySQL来源：`sibebid.bi_ota_gds_request_day`

## 数据粒度

页面只使用一张统一日汇总事实表：

```text
日期 + data_source + 平台 + 站点 + GDS + PCC + 接口分组
```

`data_source=0`为OTA渠道层，`data_source=1`为GDS资源层。虽然复用同一事实表和查询服务，但前端菜单、路由、权限、指标口径完全分开，两个层级不能相加。

## 指标口径

只有GDS资源层计算查定比：

```text
GDS查定比 = SUM(search_request_count_all) / SUM(seg_num)
```

用户于2026-10-14确认，“定”使用`seg_num`航段数。`pnr_num`与`order_request_success`均不参与正式查定比。`seg_num`字段不存在、所选范围全部未同步或仅部分记录同步时，页面显示“—”并停止计算查定比和超额查询，避免用不完整分母产生错误结论；查询量大于0且完整同步后的航段数为0时显示“∞”。OTA渠道层不展示航段查定比、目标值与超额查询。

GDS目标按资源分别配置。首版通过`RESOURCE_GOVERNANCE_GDS_TARGETS`配置，格式如`1A:4000,1G:3000`；默认只配置`1A:4000`。汇总多个GDS时不套用统一目标，筛选具体GDS或查看GDS维度行时才判断达标并计算超额查询。

OTA成功率目标按平台配置，通过`RESOURCE_GOVERNANCE_OTA_SUCCESS_TARGETS`提供JSON，例如`{"携程":{"search":99,"verify":98,"order":95}}`。未配置的平台只展示实际值，不擅自判定达标或异常。

## 页面能力

- GDS资源治理与OTA渠道质量是两个独立菜单，均默认查看本月；
- 支持今日、近7天、本月和自定义日期；
- 支持平台、站点、GDS、PCC和接口分组筛选；
- GDS层展示查询量、航段数、查定比、超额查询和接口成功率；
- OTA层展示查询、验价、生单的请求量、成功量与成功率；
- 展示查询/验价缓存命中率、平均耗时及验价/生单变价率；
- 查询、验价、生单属于独立接口统计，不伪装成同一批请求的转化漏斗；
- GDS趋势按日重新汇总分子分母，不平均源表比率；
- GDS层支持GDS、PCC、平台、站点和接口分组对比；
- OTA层支持平台、站点和接口分组对比；
- “分析此项”会保留日期和已选条件，在右侧工作区继续按GDS、PCC、平台、站点、接口组逐层定位，并可随时切换查看当前条件的日汇总。

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

当前已完成“日规则→异常事件→责任人→观察/处理→逾期升级→通知”的处理闭环。自动限流/下线工单、技术执行回执与月度治理复盘仍属于后续版本。
