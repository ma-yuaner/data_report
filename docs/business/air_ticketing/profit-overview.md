# 经营总览：出退改增利润口径

更新时间：2026-09-11  
来源：用户在数据中心开发任务中明确提供的 Hive SQL 规则  
状态：当前看板实现口径；尚未确认为财务已结算口径

## 页面目标

第一版经营总览只回答一个问题：指定业务发生期间内，出票、退票、改签和增值服务分别产生多少业务估算利润，四项合计是多少。

```text
总预估利润 = 出票预估利润 + 退票利润 + 改签利润 + 增值利润
```

只有四项查询都成功时才计算总预估利润。查询失败或数据缺失不能按 0 元参与合计。

## Hive 数据口径

| 业务 | Hive 表 | 时间字段 | 数量 | 利润 | 过滤条件 |
|---|---|---|---|---|---|
| 出票 | `lywz.dwd_order_issue_wide_year` | `issue_ticket_time` | `count(1)`；航段为 `sum(segment_num)` | `sum(issue_profit)` | `order_status='TICKETED'`、`issue_status='I_UPDATED'`、`refund_flag<>3`、`refund_issue_flag='否'` |
| 退票 | `lywz.dwd_refund_issue_year` | `apply_datetime` | `count(1)` | `sum(refund_profit)` | `supplier_refund_status_desc='待处理'` |
| 改签 | `lywz.dwd_change_issue_year` | `change_issue_time` | `count(1)` | `sum(change_profit)` | 暂无其他过滤条件 |
| 增值 | `lywz.dwd_aux_pur_year` | `create_time` | `count(1)`；航段为 `sum(flight_segment)` | `sum(profit)` | `aux_status='已购买'` |

页面提供今日、昨日、本月、本年和自定义日期快捷切换。日期为闭区间，SQL 实现为开始日 `00:00:00`（含）至结束日次日 `00:00:00`（不含）。经营总览默认查询本年截至今天，单次不超过 366 天。

## 当前限制

- 利润字段当前按业务宽表直接汇总，属于业务估算利润，不代表财务已结算利润；
- 金额单位暂按元展示，币种、含税方式、冲销和负数语义仍待财务确认；
- 退票只取供应退款状态“待处理”，代表当前用户指定范围，不等同于全部退票利润；
- 四张表可能具有不同事实粒度，数量指标不能彼此直接相加；
- 后续数据源切换为 MySQL `log.sibebid` 时，应保持本页面 API 输出结构和上述业务过滤口径稳定。
