# 目标管理 V1

> 页面职责已经拆分为“目标配置”和“目标进度”：配置页只维护目标与责任归属；进度页只读展示月度完成、利润、亏损与趋势。

平台进度以 `sibelog.sibe_ota` 的全量有效平台为底表，目标与ETL结果均采用左关联。因此未配置目标的平台也会显示，并明确标记“未配置”。GDS与政策员在尚无完整业务主数据表前，以已启用目标作为展示范围。

亏损指标目录通过 `docs/sql/target-management-metrics-v2.sql` 幂等补充。该脚本只增加口径元数据，不产生任何完成数据；ETL未写入时，页面必须显示“待ETL”，不得当作0。

- 更新日期：2026-10-16
- 用户确认：目标管理采用统一模型，覆盖平台、GDS、部门与政策员目标；原有日报脚本暂不修改，新建独立ETL落库。
- 建表脚本：[`docs/sql/target-management-v1.sql`](../../sql/target-management-v1.sql)
- 目标配置页面：`/business-configuration/targets`
- 目标进度页面：`/business-configuration/target-progress`

## 1. 现有报表迁移基线

以下内容来自当前正在发送的脚本，是迁移核对基线，不自动等同于最终正式绩效口径：

| 报表 | 当前目标粒度 | 当前完成量口径 |
|---|---|---|
| `1A_KPI.py` | 部门 + 责任人 | 1A、有奖、非婴儿、有效出票及有效承运航段 |
| `Platform_KPI.py` | 平台 + 责任人 | 有效出票对应的承运航段 |
| `erp_daily_data.py` | 部门 + 政策员 + GDS | 1A/1G/1E/1S有奖航段；总航段另用于单段利润 |

因此目标配置必须引用版本化的`metric_code`，不得只写“航段数”而不注明口径。首批目录为：

- `ISSUED_AIRLIFT_SEGMENT`：有效出票承运航段；
- `REWARD_SEGMENT`：有奖航段；
- `GDS_1A_ELIGIBLE_SEGMENT`：1A考核有效航段；
- `ISSUE_PROFIT`：出票预估利润，作为单段利润辅助指标。

## 2. 数据职责

| 表 | 职责 |
|---|---|
| `target_metric_definition` | 保存指标名称、版本、日期口径及过滤说明 |
| `biz_target_plan` | 保存目标周期、场景、版本和发布状态 |
| `biz_target_item` | 保存平台、GDS、部门或政策员的具体目标值 |
| `biz_target_scope_assignment` | 保存业务对象到部门、第一/第二责任人的有效期映射 |
| `dws_target_metric_day` | 保存ETL产出的每日实际指标，不保存目标值 |
| `ads_target_progress_day` | 保存目标、累计完成、正常进度、差额及每日需完成快照 |

平台、GDS和政策员不分别建目标表。它们使用同一目标计划及明细表，通过稳定编码和`scope_key`区分。平台、人员和部门中文名称只保存快照，不作为ETL关联主键。

## 3. 页面边界

“业务配置 → 目标配置”包含：

1. 平台目标；
2. GDS目标；
3. 部门/政策员目标。

配置页只用于编辑航段数量目标、归属、周期和状态；金额指标不允许作为目标值配置。实际完成量只能由ETL写入。

“业务配置 → 目标进度”按月份集中展示：

1. 目标、累计实际、完成率、正常进度、进度差、剩余量和日均需完成；
2. 累计出票预估利润、单段利润、昨日利润和昨日单段利润；
3. 单独亏损金额、亏损票数、亏损航段数和亏损票占比；
4. 昨日航段、前日航段和日环比；
5. 责任人、归属部门、企业微信身份与数据截止日期。

“单独亏损金额”定义为`issue_profit < 0`记录的出票预估亏损绝对值之和，属于业务估算而非财务结算。MySQL聚合源的亏损票数必须使用`sum(iss_num)`，不得按聚合行数计数；亏损票占比同时保留亏损票数与总票数分母。该定义来源于当前已确认的`bi_order_issue_year`聚合粒度，后续ETL仍须与原平台报表逐项对账。

部门目标默认由政策员明细汇总；只有业务明确下达独立部门目标时，才创建`DEPARTMENT`场景目标。预警阈值仍由预警规则管理，Webhook及发送对象仍由通知配置管理。

已接入的真实数据接口为：

- `GET /api/v1/business-configuration/targets`：按场景、月份、状态和关键词查询目标与最新进度；
- `GET /api/v1/business-configuration/targets/metrics`：读取已启用指标口径；
- `GET /api/v1/business-configuration/targets/options`：平台读取ERP`sibelog.sibe_ota`，责任人及企业微信身份读取`sibebd.rbac_user`，归属部门通过`rbac_user.org_id` 关联`sibebd.rbac_organization`；
- `POST /api/v1/business-configuration/targets`：事务性新建或更新目标计划与明细。
- `GET /api/v1/business-configuration/target-progress`：按场景、月份和关键词读取只读进度看板；平台场景始终以ERP全量有效平台为底表。

当`ads_target_progress_day`没有对应快照时，接口对完成量、利润、完成率和正常进度返回`null`，页面显示“待ETL产出”，不将缺数解释为0。

花名册是目标责任人、部门和后续企业微信`@`的唯一来源，不回退为数据中心登录账号。应用数据库账号需要至少拥有以下只读权限：

```sql
GRANT SELECT (`id`, `cname`, `wechat_id`, `org_id`, `enabled`)
ON `sibebd`.`rbac_user` TO 'app_user'@'%';
GRANT SELECT (`id`, `org_code`, `org_cname`)
ON `sibebd`.`rbac_organization` TO 'app_user'@'%';
GRANT SELECT (`ota_code`, `ota_cname`, `ota_full_cname`, `status`, `start_time`, `end_time`, `sort_seq`)
ON `sibelog`.`sibe_ota` TO 'app_user'@'%';
```

## 4. 独立ETL方案

新增一个独立任务`target_management_daily.py`，不修改、引用或停止现有三份发送脚本。建议每日在ERP出票数据稳定后运行，处理顺序为：

1. 读取已发布且覆盖处理日期的目标计划、目标明细及有效责任归属；
2. 一次读取目标周期内所需的ERP出票、承运航段、乘客、平台、GDS和政策员字段；
3. 按指标版本分别计算有效出票承运航段、有奖航段、1A考核有效航段及对应利润；
4. 按“业务日期 + 指标 + 稳定维度键”幂等写入`dws_target_metric_day`；
5. 汇总周期累计实际值，结合计划进度曲线计算完成率、进度差、剩余航段和每日需完成；
6. 幂等写入`ads_target_progress_day`；
7. 记录源数据最大时间、ETL批次和数据状态，缺数时写`PARTIAL/MISSING`，不能将缺数当0。

脚本应支持`--biz-date`日跑、`--start-date/--end-date`补数和`--dry-run`核对。首轮上线以旧报表为对账对象，分别比较平台、GDS、部门和政策员月累计结果，确认一致后再允许页面使用正式数据。
