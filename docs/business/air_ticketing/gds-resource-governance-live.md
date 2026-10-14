# GDS/OTA资源治理 V1 实现说明

- 更新时间：2026-10-14
- 当前状态：资源总览、OTA/GDS分层、趋势、维度对比和日汇总下钻已接入正式项目
- 页面：`/resource-governance`
- API：`GET /api/v1/resource-governance/overview`
- MySQL来源：`sibebid.bi_ota_gds_request_day`

## 数据粒度

页面只使用一张统一日汇总事实表：

```text
日期 + data_source + 平台 + 站点 + GDS + PCC + 接口分组
```

`data_source=0`为OTA渠道层，`data_source=1`为GDS资源层。两个层级独立分析，不能相加形成公司总查定比。

## 指标口径

```text
查定比 = SUM(search_request_count_all) / SUM(pnr_count)
```

`order_request_success`是直连生单接口成功量，只用于接口链路分析，不得替代实际有效PNR。`pnr_count`字段不存在或所选范围尚未同步时，页面显示“—”并给出数据接入提示；查询量大于0且实际有效PNR为0时显示“∞”。

## 页面能力

- 默认查看本月GDS资源层，可切换OTA渠道层；
- 支持今日、近7天、本月和自定义日期；
- 支持平台、站点、GDS、PCC和接口分组筛选；
- 展示查询量、有效PNR、查定比、超额查询、查询/验价/生单成功率；
- 趋势按日重新汇总分子分母，不平均源表比率；
- GDS层支持GDS、PCC、平台、站点和接口分组对比；
- OTA层支持平台、站点和接口分组对比；
- “分析此项”在右侧工作区展示该资源每日数据。

异常事件、规则评分、责任人、上下线工单和治理复盘不属于本次V1分析页面，后续使用独立配置与流程表建设。
