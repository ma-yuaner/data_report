# 目标管理 V1

- 更新日期：2026-10-16
- 用户确认：目标管理采用统一模型，覆盖平台、GDS、部门与政策员目标；原有日报脚本暂不修改，新建独立ETL落库。
- 建表脚本：[`docs/sql/target-management-v1.sql`](../../sql/target-management-v1.sql)
- 前端页面：`/business-configuration/targets`

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

“业务配置 → 目标管理”包含：

1. 平台目标；
2. GDS目标；
3. 部门/政策员目标。

配置页可以只读展示完成量、完成率、正常进度、剩余量和数据时间，但只允许编辑目标、归属与周期。实际完成量只能由ETL写入。

部门目标默认由政策员明细汇总；只有业务明确下达独立部门目标时，才创建`DEPARTMENT`场景目标。预警阈值仍由预警规则管理，Webhook及发送对象仍由通知配置管理。

已接入的真实数据接口为：

- `GET /api/v1/business-configuration/targets`：按场景、月份、状态和关键词查询目标与最新进度；
- `GET /api/v1/business-configuration/targets/metrics`：读取已启用指标口径；
- `GET /api/v1/business-configuration/targets/options`：从现有资源指标表、系统用户和已配置目标中读取平台、GDS、责任人和部门选项；
- `POST /api/v1/business-configuration/targets`：事务性新建或更新目标计划与明细。

当`ads_target_progress_day`没有对应快照时，接口对完成量、利润、完成率和正常进度返回`null`，页面显示“待ETL产出”，不将缺数解释为0。

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
