# 出票利润分析与字段齐全度

更新时间：2026-09-15
来源：`lywz.dwd_order_issue_wide_year` Hive 表结构及聚合验证；`sibebid.bi_order_issue_year` MySQL 只读结构检查
状态：Hive 分析字段已验证；MySQL 核心汇总字段具备，扩展分析字段待同步或确认映射；利润仍属于业务估算口径

## 第一版分析范围

出票利润分析与经营总览共用以下过滤条件：

```sql
order_status = 'TICKETED'
and issue_status = 'I_UPDATED'
and refund_flag <> 3
and refund_issue_flag = '否'
```

Hive 时间使用 `issue_ticket_time`，MySQL 时间使用 `operator_date`；页面支持今日、昨日、本月、本年和自定义闭区间。

第一版回答：出票利润和业务量如何随时间变化，利润主要集中在哪些销售平台、航司、出票供应商和组织，以及这些分析所需字段的非空覆盖情况。

## 首批关键字段

| 分析目的 | 字段 |
|---|---|
| 订单下钻 | `order_id` |
| 销售平台与站点 | `ota_cname`、`ota_site_cname` |
| 航司与航线 | `marketing_airline`、`dep_city`、`arr_city` |
| 供应归因 | `issue_supplier_cname` |
| 组织与人员 | `org_cname`、`issue_operator`、`policy_operator` |
| PCC / Office | `issue_ticketing_office_no` |
| 出票方式 | `issue_way_desc` |
| 利润 | `issue_profit` |

2026-09-01 至 2026-09-12 的探索性聚合中，上述 12 项字段非空率均为 100%。这只说明当前样本能够按这些字段分组，不代表字段取值、历史映射、人员归属或财务利润口径已经确认。

## 页面判断阈值

- 非空率大于等于 95%：齐全；
- 非空率大于等于 80% 且小于 95%：可用但需补；
- 非空率小于 80%：缺失严重。

后续仍需检查“未知”“其他”等占位值、维度编码与名称的一致性、同一主体多名称、组织和人员历史变更，以及订单粒度是否存在重复。

## MySQL 当前字段差异

2026-09-14 只读结构检查确认，经营总览所需的 `operator_date`、`segment_num`、`issue_profit`、出票状态及退票标记字段已经具备，因此出票核心数量和利润汇总能够查询。

首次检查时，出票分析缺少以下 11 个 Hive 同名分析字段：

`order_id`、`ota_site_cname`、`marketing_airline`、`issue_supplier_cname`、`org_cname`、`issue_operator`、`policy_operator`、`issue_ticketing_office_no`、`dep_city`、`arr_city`、`issue_way_desc`。

用户随后说明上述字段已补充。2026-09-14 再次检查当前 MySQL 表的 51 个字段，确认 `order_id`、`ota_site_cname`、`org_cname`、`issue_operator`、`policy_operator`、`issue_way_desc` 已按同名字段增加，另外 5 个字段由用户明确确认使用 MySQL 物理字段映射：

| 业务逻辑字段 | MySQL 物理字段 |
|---|---|
| `marketing_airline` | `air_line` |
| `issue_supplier_cname` | `supplier_name` |
| `issue_ticketing_office_no` | `pcc_code` |
| `dep_city` | `dep_city_code` |
| `arr_city` | `arr_city_code` |

API 对外仍使用统一业务含义，只有 MySQL 查询层转换为上述物理字段；Hive 保持原字段不变。

## MySQL 聚合粒度

用户于 2026-09-15 明确确认 `bi_order_issue_year` 已按分析维度聚合，一行不等于一张票。MySQL 出票数统一使用 `sum(iss_num)`；亏损、盈利和零利润出票数也按对应聚合行的 `iss_num` 求和，保证利润率分子分母粒度一致。Hive 明细宽表仍使用 `count(1)`。

字段完整率用于检查聚合结果字段是否有值，其分母继续使用 MySQL 聚合记录行数，而不是 `sum(iss_num)`，避免一条聚合记录按出票量重复放大。
