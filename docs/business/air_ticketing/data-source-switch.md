# MySQL / Hive 数据源切换

更新时间：2026-09-14
来源：用户在数据中心开发任务中的明确说明
状态：切换机制已实现；MySQL 数据仍在同步，待用户同步完成后验证

## 当前规则

- 看板默认读取 MySQL，库名为 `sibebid`；
- Hive 连接和查询能力保留，可作为临时人工切换的数据源；
- Hive 数据是当前业务数据的最终解释来源，MySQL 是为高频看板同步的字段子集；
- MySQL 缺少后续分析所需字段时，应补充同步字段或建设 ADS，不得凭字段名猜测，也不得把缺失值当作 0；
- 单次 API 请求只能读取一个数据源，不允许 MySQL 查询失败后自动、静默地用 Hive 补齐，避免同一总利润混合不同刷新时点的数据。

## 表与时间字段映射

| 业务 | MySQL 默认表 | MySQL 时间字段 | Hive 权威表 | Hive 时间字段 |
|---|---|---|---|---|
| 出票 | `sibebid.bi_order_issue_year` | `operator_date` | `lywz.dwd_order_issue_wide_year` | `issue_ticket_time` |
| 退票 | `sibebid.bi_refund_issue_year` | `apply_datetime` | `lywz.dwd_refund_issue_year` | `apply_datetime` |
| 改签 | `sibebid.bi_change_issue_year` | `change_issue_time` | `lywz.dwd_change_issue_year` | `change_issue_time` |
| 增值 | `sibebid.bi_aux_pur_year` | `create_time` | `lywz.dwd_aux_pur_year` | `create_time` |
| 综合分析日汇总 | `sibebid.bi_business_profit_dimension_day` | `dt` | `lywz.ads_business_profit_dimension_day` | `dt` |

除出票时间字段外，首版暂按用户说明复用 Hive 已确认的利润字段和业务过滤条件。由于 MySQL 内容尚未完全同步，这些字段在 MySQL 中的存在性、类型、数据量和结果一致性均标记为“待验证”。

## 当前功能字段契约

经营总览能够工作的最小字段集：

- 出票：`operator_date`、`iss_num`、`segment_num`、`issue_profit`、`order_status`、`issue_status`、`refund_flag`、`refund_issue_flag`；MySQL 出票数为 `sum(iss_num)`；
- 退票：`apply_datetime`、`refund_profit`、`business_type_desc`、`supplier_refund_operator`；
- 改签：`change_issue_time`、`change_profit`；
- 增值：`create_time`、`profit`、`flight_num`、`aux_status`。

出票分析还会使用 `order_id`、平台/站点、航司、供应商、组织、出票员、政策员、PCC、出发到达城市和出票方式等维度字段。问题中心还会使用各业务的事件编号、订单号、票号、平台、供应商、航司和操作人字段。若这些扩展字段尚未同步，对应分析模块应显示不可用；经营总览的已具备指标不受影响。

MySQL 出票分析已确认使用以下物理字段映射：`marketing_airline → air_line`、`issue_supplier_cname → supplier_name`、`issue_ticketing_office_no → pcc_code`、`dep_city → dep_city_code`、`arr_city → arr_city_code`。Hive 仍使用左侧原字段。

2026-09-14 首次本地只读结构检查时，`sibebid.bi_order_issue_year` 尚未包含 `issue_profit`。用户随后明确说明字段已经添加；再次检查确认字段为可空的 `decimal(18,4)`，经营总览查询链路已通过，字段业务数据仍待用户调度写入。不能擅自用收入减成本推导替代该权威利润字段。当前 MySQL 版本不支持窗口函数，问题中心已采用兼容的“汇总查询 + Top 明细查询”。

## 操作方式

默认 MySQL：

```dotenv
DATA_MODE=mysql
MYSQL_DATABASE=sibebid
```

临时切回 Hive：

```dotenv
DATA_MODE=hive
HIVE_DATABASE=lywz
```

修改部署环境的 `.env` 后重启 API 或执行 `docker compose up -d`。健康检查 `/api/health` 返回当前 `dataMode`，业务 API 的 `source` 返回具体引擎和数据库。

综合分析页面固定读取 MySQL 镜像 `sibebid.bi_business_profit_dimension_day`。MySQL 不可用时页面直接提示错误，不静默回退 Hive；Hive 表继续作为同步来源及最终口径核对依据。

## 验证边界

本次开发只验证代码映射、SQL 方言和 API 契约，不对尚未同步完成的 MySQL 数据下业务结论。数据同步完成后，应按同一日期范围对四类数量、航段数和利润逐项进行 MySQL / Hive 对账；存在差异时以 Hive 结果追查同步字段和过滤逻辑。
