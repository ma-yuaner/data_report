# 经营总览：出退改增利润口径

更新时间：2026-09-17
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

经营总览底部独立展示出票、退票、改签利润核对表的票数与预估利润。默认从 MySQL `sibebid` 查询，跟随 `DATA_MODE` 手工切换到 Hive；不会在 MySQL 查询失败时自动补读 Hive。该区域复用页面时间筛选，但不改变原经营总览，也不参与原“出、退、改、增”总预估利润合计，避免重复计算同一业务。

| 业务 | MySQL 默认表 | Hive 保留表 | 时间字段 | 票数 | 预估利润 |
|---|---|---|---|---|---|
| 出票 | `sibebid.bi_order_issue_profit_reconcile_year` | `lywz.dwd_order_issue_profit_reconcile_year` | `business_date` | `sum(ticket_num)` | `sum(estimated_profit_cny)` |
| 退票 | `sibebid.bi_order_refund_profit_reconcile_year` | `lywz.dwd_order_refund_profit_reconcile_year` | `business_date` | `sum(ticket_num)` | `sum(estimated_profit_cny)` |
| 改签 | `sibebid.bi_order_change_profit_reconcile_year` | `lywz.dwd_order_change_profit_reconcile_year` | `stat_date` | `sum(ticket_num)` | `sum(estimated_profit_cny)` |

按所选闭区间汇总，并显示所跨月份；金额字段为 CNY 预估利润，不是财务已结算利润；汇总粒度为源表票数之和，不以行数替代票数。暂不进行原因归因、实际利润推算或月度趋势拆分。核对查询失败只影响本区域，不影响原经营总览。

来源：用户于 2026-09-17 明确要求切换到 `sibebid` 三张 `bi_order_*_profit_reconcile_year` 表；状态：已确认数据源映射与保持现有指标口径；更新日期：2026-09-17。同步完整性及财务确认阶段不因切换而被默认确认。

## 核对区当前筛选：仅时间（2026-09-17）

来源：用户于2026-09-17明确要求经营总览中的风控利润核对仅保留时间筛选，与上方估算利润筛选器一致；状态：已确认页面需求；更新日期：2026-09-17。

核对区提供今日、昨日、本月、本年和自定义起止日期，默认今日，与上方共用同一统计期间。任一区域的日期快捷选择或查询均刷新上下区域。经营总览不再展示或提交平台、站点、业务部门、航司、供应商及盈亏状态筛选，也不请求维度名称建议。核对表、时间字段、票数与利润汇总口径不变，核对利润仍不纳入上方总预估利润。

## 核对区维度筛选历史方案（2026-09-17，经营总览已移除）

以下为此前实现记录。维度筛选接口和索引参考保留，但不再作为经营总览页面的当前筛选规则。

来源：用户于2026-09-17要求增加核对筛选及索引语句；字段映射来自同日对 `sibebid` 三表字段注释的只读核验。
状态：筛选能力与指标时间口径沿用用户确认规则；首批维度选择为实现方案，不代表新的归因或责任规则。

| 筛选项 | API参数 | 三表共有物理字段 | 语义 |
|---|---|---|---|
| OTA平台 | `platform` | `ota_cname` | 完整名称精确匹配 |
| 站点 | `site` | `ota_site_cname` | 完整名称精确匹配 |
| 业务部门 | `department` | `org_cname` | 完整名称精确匹配 |
| 航司 | `airline` | `marketing_airline` | 源字段文本精确匹配，不拆分多航司字符串 |
| 供应商 | `supplier` | `supplier_cname` | 完整名称精确匹配 |
| 盈亏状态 | `profitStatus` | `estimated_profit_cny` | `all`全部、`loss`小于0、`profit`大于0、`zero`等于0 |

空维度表示全部，多个维度以 AND 组合；盈亏判断发生在源记录汇总之前，不把某维度净亏损作为记录筛选标准。零利润筛选不会把 NULL 利润当成0。名称文本及枚举作为DB-API参数绑定，列名严格白名单。

筛选只作用于底部核对三表，上方原经营总览不受影响；核对区有独立查询和重置按钮，全局日期查询同时刷新上下区域。返回结果明确显示已应用条件，避免把输入中未提交的条件误认为已生效。

输入框可选择当前期间的数据建议或直接输入完整名称。建议按需请求、按名称前缀搜索，每个维度最多显示50项；超过时明确提示继续输入。其他已输入维度会约束建议，当前编辑维度不会约束自身。原始字段值用于匹配，不以分析推断回填缺失部门、平台或航司。

汇总与建议缓存均包含数据源、日期和筛选条件，成功查询才缓存；条件不同不能复用同一汇总。Hive手工切换仍使用相同维度、指标和每类业务的时间字段，失败不静默混源。

已只读检查三张 MySQL 表目前均为 InnoDB / Dynamic，名称与时间字段为 VARCHAR(150)。2026-09-17用户已按上一版SQL创建三个 `idx_reconcile_date_sum`，本轮只读核验确认包含日期、票数和利润。根据用户最新明确要求，新基础索引仅保留日期：出票、退票为 `business_date`，改签为 `stat_date`，不包含 `ticket_num` 或 `estimated_profit_cny`。来源：用户当日对话；状态：已确认索引设计，数据库替换由用户手工执行；更新日期：2026-09-17。

新建表使用 [纯日期索引](../../sql/risk-profit-reconcile-indexes.sql)；已建旧索引的表使用 [旧索引替换SQL](../../sql/risk-profit-reconcile-remove-metric-index-columns.sql)，不删除表字段和数据，也不改变原票数或利润汇总口径。高频维度方案仍在 [可选维度索引](../../sql/risk-profit-reconcile-filter-indexes-optional.sql)；应用不创建或删除索引，由用户在低峰手工选择执行并用 EXPLAIN 验证。不要一次性给所有维度都建索引。

索引顺序及前缀语法参照 [MySQL 5.7组合索引](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/multiple-column-indexes.html) 和 [CREATE INDEX](https://docs.oracle.com/cd/E17952_01/mysql-5.7-en/create-index.html)。纯日期索引及各维度索引的实际收益仍需在数据同步后核实；不承诺建索引就能解决全年大范围扫描。旧版额外放入票数和利润是为了覆盖查询，不是日期筛选所必需；移除后可能需要回表读取汇总值，应用仍直接汇总同一源字段。

## 当前限制

- 利润字段当前按业务宽表直接汇总，属于业务估算利润，不代表财务已结算利润；
- 金额单位暂按元展示，币种、含税方式、冲销和负数语义仍待财务确认；
- 退票只取业务类型为“正常退票（退票）”或“售后退票作废（退票）”，且供应退款操作人有值的记录，不等同于全部退票申请；
- 四张表可能具有不同事实粒度，数量指标不能彼此直接相加；
- MySQL 当前只同步看板有用字段，字段存在性、类型和结果一致性待同步完成后验证；缺字段不能按 0 处理；
- 默认查询 MySQL，Hive 数据保留最终解释权。切换为人工整体切换，禁止单项失败后静默从 Hive 补数。

## 变更记录

- 2026-09-17：按用户最新要求，经营总览风控利润核对仅保留时间筛选，与上方共用日期、默认今日；移除该页面的维度与盈亏筛选及名称建议请求，保留后端接口，指标口径不变。
- 2026-09-17：用户确认旧覆盖索引已创建，要求去掉其中票数和利润列；基础SQL改为纯日期索引，提供但不执行旧索引替换语句，查询和业务指标不变。
- 2026-09-17：按用户要求增加核对区维度与盈亏筛选、按期间加载的名称建议、独立查询与重置；提供但不执行MySQL基础与可选维度索引语句。
- 2026-09-17：用户明确要求风控利润核对从 Hive 切换到 MySQL `sibebid` 三张 `bi_order_*_profit_reconcile_year` 表；保留原票数、CNY 预估利润及时间字段，跟随 `DATA_MODE` 手工切回 Hive。
- 2026-09-16：根据用户明确提供的三张 Hive 利润核对表及 SQL，在经营总览底部增加独立的出票、退票、改签票数和预估利润汇总；复用时间筛选但不纳入原总预估利润。
- 2026-09-15：用户确认 MySQL 出票表为聚合表，出票数由 `count(1)` 调整为 `sum(iss_num)`；Hive 明细宽表仍使用 `count(1)`。
- 2026-09-14：用户确认 MySQL 出票表已增加 `issue_profit`；结构检查为 `decimal(18,4)`，经营总览查询通过，业务数据待调度写入。
- 2026-09-14：默认数据源切换为 MySQL `sibebid` 的四张 `bi_*` 表；出票时间映射为 `operator_date`，Hive 查询保留并作为最终解释来源。
- 2026-09-12：根据用户最新明确规则，退票口径增加两个允许的业务类型；Hive 实际字段核对后使用中文描述字段 `business_type_desc`，同时用于经营总览与退票分析。
- 2026-09-12：根据用户最新要求，经营总览和各业务分析页默认时间由本年改为今日，降低首次查询数据量。
