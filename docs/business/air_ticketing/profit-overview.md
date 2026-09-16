# 经营总览：出退改增利润口径

更新时间：2026-09-16
来源：用户在数据中心开发任务中明确提供的 Hive SQL 规则、MySQL 表映射及三张利润核对表
状态：当前看板实现口径；MySQL 数据待同步验证；尚未确认为财务已结算口径

## 页面目标

第一版经营总览只回答一个问题：指定业务发生期间内，出票、退票、改签和增值服务分别产生多少业务估算利润，四项合计是多少。

```text
总预估利润 = 出票预估利润 + 退票利润 + 改签利润 + 增值利润
```

只有四项查询都成功时才计算总预估利润。查询失败或数据缺失不能按 0 元参与合计。

## 业务口径与数据源映射

| 业务 | MySQL 默认表 / 时间 | Hive 权威表 / 时间 | 数量 | 利润 | 过滤条件 |
|---|---|---|---|---|---|
| 出票 | `sibebid.bi_order_issue_year` / `operator_date` | `lywz.dwd_order_issue_wide_year` / `issue_ticket_time` | MySQL 为 `sum(iss_num)`；Hive 为 `count(1)`；航段为 `sum(segment_num)` | `sum(issue_profit)` | `order_status='TICKETED'`、`issue_status='I_UPDATED'`、`refund_flag<>3`、`refund_issue_flag='否'` |
| 退票 | `sibebid.bi_refund_issue_year` / `apply_datetime` | `lywz.dwd_refund_issue_year` / `apply_datetime` | `count(1)` | `sum(refund_profit)` | `business_type_desc in ('正常退票（退票）','售后退票作废（退票）')`；`supplier_refund_operator is not null` 且去除首尾空格后不为空 |
| 改签 | `sibebid.bi_change_issue_year` / `change_issue_time` | `lywz.dwd_change_issue_year` / `change_issue_time` | `count(1)` | `sum(change_profit)` | 暂无其他过滤条件 |
| 增值 | `sibebid.bi_aux_pur_year` / `create_time` | `lywz.dwd_aux_pur_year` / `create_time` | `count(1)`；航段为 `sum(flight_num)` | `sum(profit)` | `aux_status='已购买'` |

页面提供今日、昨日、本月、本年和自定义日期快捷切换。日期为闭区间，SQL 实现为开始日 `00:00:00`（含）至结束日次日 `00:00:00`（不含）。经营总览和各业务分析页默认查询今日，单次不超过 366 天。

## 风控利润核对区

经营总览底部独立展示三张 Hive 利润核对表的票数与预估利润。该区域复用页面时间筛选，但不改变原经营总览，也不参与原“出、退、改、增”总预估利润合计，避免重复计算同一业务。

| 业务 | Hive 表 | 时间字段 | 票数 | 预估利润 |
|---|---|---|---|---|
| 出票 | `lywz.dwd_order_issue_profit_reconcile_year` | `business_date` | `sum(ticket_num)` | `sum(estimated_profit_cny)` |
| 退票 | `lywz.dwd_order_refund_profit_reconcile_year` | `business_date` | `sum(ticket_num)` | `sum(estimated_profit_cny)` |
| 改签 | `lywz.dwd_order_change_profit_reconcile_year` | `stat_date` | `sum(ticket_num)` | `sum(estimated_profit_cny)` |

第一版按所选闭区间汇总，并显示所跨月份；暂不进行原因归因、实际利润推算或月度趋势拆分。Hive 查询失败只影响本区域，不影响原 MySQL 经营总览。

## 当前限制

- 利润字段当前按业务宽表直接汇总，属于业务估算利润，不代表财务已结算利润；
- 金额单位暂按元展示，币种、含税方式、冲销和负数语义仍待财务确认；
- 退票只取业务类型为“正常退票（退票）”或“售后退票作废（退票）”，且供应退款操作人有值的记录，不等同于全部退票申请；
- 四张表可能具有不同事实粒度，数量指标不能彼此直接相加；
- MySQL 当前只同步看板有用字段，字段存在性、类型和结果一致性待同步完成后验证；缺字段不能按 0 处理；
- 默认查询 MySQL，Hive 数据保留最终解释权。切换为人工整体切换，禁止单项失败后静默从 Hive 补数。

## 变更记录

- 2026-09-16：根据用户明确提供的三张 Hive 利润核对表及 SQL，在经营总览底部增加独立的出票、退票、改签票数和预估利润汇总；复用时间筛选但不纳入原总预估利润。
- 2026-09-15：用户确认 MySQL 出票表为聚合表，出票数由 `count(1)` 调整为 `sum(iss_num)`；Hive 明细宽表仍使用 `count(1)`。
- 2026-09-14：用户确认 MySQL 出票表已增加 `issue_profit`；结构检查为 `decimal(18,4)`，经营总览查询通过，业务数据待调度写入。
- 2026-09-14：默认数据源切换为 MySQL `sibebid` 的四张 `bi_*` 表；出票时间映射为 `operator_date`，Hive 查询保留并作为最终解释来源。
- 2026-09-12：根据用户最新明确规则，退票口径增加两个允许的业务类型；Hive 实际字段核对后使用中文描述字段 `business_type_desc`，同时用于经营总览与退票分析。
- 2026-09-12：根据用户最新要求，经营总览和各业务分析页默认时间由本年改为今日，降低首次查询数据量。
