# GDS/OTA资源治理 V1 实现说明

- 更新时间：2026-10-14
- 当前状态：资源总览、OTA/GDS分层、趋势、维度对比和日汇总下钻已接入正式项目
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
GDS查定比 = SUM(search_request_count_all) / SUM(pnr_count)
```

`order_request_success`是直连生单接口成功量，只用于接口链路分析，不得替代实际有效PNR。`pnr_count`只写入`data_source=1`的GDS行。字段不存在或所选GDS范围尚未同步时，页面显示“—”并给出数据接入提示；查询量大于0且实际有效PNR为0时显示“∞”。OTA渠道层不展示PNR、查定比、目标值与超额查询。

GDS目标按资源分别配置。首版通过`RESOURCE_GOVERNANCE_GDS_TARGETS`配置，格式如`1A:4000,1G:3000`；默认只配置`1A:4000`。汇总多个GDS时不套用统一目标，筛选具体GDS或查看GDS维度行时才判断达标并计算超额查询。

## 页面能力

- GDS资源治理与OTA渠道质量是两个独立菜单，均默认查看本月；
- 支持今日、近7天、本月和自定义日期；
- 支持平台、站点、GDS、PCC和接口分组筛选；
- GDS层展示查询量、有效PNR、查定比、超额查询和接口成功率；
- OTA层展示查询、验价、生单的请求量、成功量与成功率；
- GDS趋势按日重新汇总分子分母，不平均源表比率；
- GDS层支持GDS、PCC、平台、站点和接口分组对比；
- OTA层支持平台、站点和接口分组对比；
- “分析此项”在右侧工作区展示该资源每日数据。

异常事件、规则评分、责任人、上下线工单和治理复盘不属于本次V1分析页面，后续使用独立配置与流程表建设。
