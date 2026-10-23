# 目标管理 V1

> 页面职责已经拆分为“目标配置”和“目标进度”：配置页只维护目标与责任归属；进度页只读展示月度完成、利润、亏损与趋势。

平台进度仍以 `sibelog.sibe_ota` 的全量有效平台为底表，目标与ETL结果均采用左关联，以保留平台完整性检查能力。页面默认只展示已配置目标的平台；打开“显示未配置平台”后才展示全部有效平台，未配置项明确标记“未配置”。该开关不影响GDS与政策员场景，后两者在尚无完整业务主数据表前仍以已启用目标作为展示范围。

亏损指标目录通过 `docs/sql/target-management-metrics-v2.sql` 幂等补充。该脚本只增加口径元数据，不产生任何完成数据；ETL未写入时，页面必须显示“待ETL”，不得当作0。

- 更新日期：2026-10-22
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
| `biz_target_item` | 保存平台、GDS、部门或政策员组合的具体目标值；政策员场景保存部门与组长，不重复保存组合成员 |
| `biz_target_policy_member` | 只保存政策员组合的多选成员；成员名单不在目标明细中重复维护 |
| `biz_target_change_log` | 平台、GDS和政策员共用的配置变更日志；按一次保存操作记录修改前后快照、操作人、时间及原因，只追加不覆盖 |
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
平台、GDS和部门/政策员场景的归属部门均由用户从真实组织资料中下拉选择，不依赖花名册当前尚未完善的人员部门关系。部门/政策员场景由用户从真实启用花名册中多选政策员，并从已选政策员中单选组长。人员下拉仅展示姓名及已配置的企业微信ID；政策员的1A、1G、1E、1S目标必须同时展示所选指标口径，不能只显示GDS代码和数值。
部门/政策员目标详情同时展示目标航段合计和1A、1G、1E、1S四项明细；明细直接读取目标配置返回的`gdsBreakdown`，不根据合计平均拆分，也不现场计算实际完成量。
平台、GDS和部门/政策员三个配置列表均展示目标月份，并在每条记录提供“复制”。复制默认带出原责任人、部门、指标、目标值、状态和说明，将目标月份预填为下一个月；保存时创建新月份配置，不复用原明细ID。目标月份已经存在相同业务对象与指标时拒绝覆盖，用户应编辑原配置。

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
- `GET /api/v1/business-configuration/targets/options`：平台读取ERP`sibelog.sibe_ota`；责任人及企业微信身份通过独立花名册连接读取`sibedb.system_user`，归属部门读取`sibedb.base_organization`并通过`sibedb.system_user_department`关联到人员。该库中`system_user.enabled=0`表示启用、`1`表示禁用；启用人员即使尚未关联部门也可用于政策员组合，同一员工存在多条部门关系时使用关联表最大`id`对应的最新记录；
- `POST /api/v1/business-configuration/targets`：事务性新建或更新目标计划与明细，并在同一事务写入通用变更日志；修改已有配置时必须填写本次修改原因。
- `GET /api/v1/business-configuration/target-progress`：按场景、月份和关键词读取只读进度看板；平台场景始终以ERP全量有效平台为底表，并支持`includeUnconfigured=true|false`控制是否展示未配置平台，默认`false`。关键词只在当前开关确定的展示范围内过滤。平台汇总分别返回有效平台总数、已配置数和当前显示数，避免把完整性底表数量与页面行数混为一谈。
- `POST /api/v1/business-configuration/target-progress/refresh`：拥有“管理业务目标”权限的账号可提交一次后台立即更新；接口只排队，不在HTTP请求中同步执行ETL。
- `GET /api/v1/business-configuration/target-progress/refresh/status`：读取最近一次立即更新的排队、运行、成功或失败状态及真实处理行数。

当`ads_target_progress_day`没有对应快照时，接口对完成量、利润、完成率和正常进度返回`null`，页面显示“待ETL产出”，不将缺数解释为0。

花名册是目标责任人、部门和后续企业微信`@`的唯一来源，不回退为数据中心登录账号。应用数据库账号需要至少拥有以下只读权限：

```sql
GRANT SELECT (`id`, `cname`, `wechat_id`, `enabled`)
ON `sibedb`.`system_user` TO 'app_user'@'%';
GRANT SELECT (`id`, `user_id`, `department_id`)
ON `sibedb`.`system_user_department` TO 'app_user'@'%';
GRANT SELECT (`id`, `org_code`, `org_cname`)
ON `sibedb`.`base_organization` TO 'app_user'@'%';
GRANT SELECT (`ota_code`, `ota_cname`, `ota_full_cname`, `status`, `start_time`, `end_time`, `sort_seq`)
ON `sibelog`.`sibe_ota` TO 'app_user'@'%';
```

## 4. 独立ETL实现

已新增独立任务`backend/data_report_api/target_management_daily.py`，不修改、引用或停止现有的
`Platform_KPI.py`、`1A_KPI.py`、`1E_KPI.py`、`1G_KPI.py`和`erp_daily_data.py`。源库`sibedb`只读，
只向目标库`sibebid`的DWS/ADS表写入幂等结果。

当前V1计算规则：

- 平台“有效出票承运航段”沿用`Platform_KPI.py`：出票日、`TICKETED`、未作废、只计`airlift_flag=1`并按出票ID关联航段去重；
- GDS完成量分别沿用`1A_KPI.py`、`1G_KPI.py`和`1E_KPI.py`：先按脚本配置的平台范围归属到部门和责任人，再限定对应GDS、`reward_flag=1`、订单存在非婴儿乘机人、有效出票及`airlift_flag=1`承运航段；不使用全公司GDS总量，也不使用`reward_trip_count`代替承运航段数；
- 政策员完成量沿用`erp_daily_data.py`及其SQL：按目标配置的组长匹配`order_info.policy_operator`，分别汇总1A、1G、1E、1S的`reward_trip_count`并合计；组合成员只用于页面展示，不改变实际数据按组长归集的规则；
- 政策员利润沿用`erp_daily_data.py`：在相同部门、组长、出票日和有效出票过滤范围内汇总全部GDS的`order_info_issue.issue_profit`；政策员单段利润分母为同范围全部GDS的`trip_count`，不以有奖完成量为分母；
- 平台利润按平台脚本对应的有效出票范围汇总`order_info_issue.issue_profit`；GDS利润为目标进度页扩展指标，按该GDS完成量的同一考核记录范围汇总`issue_profit`，不冒充原GDS日报已有指标；
- 任一票利润缺失时该范围标记`PARTIAL`并保存`NULL`；
- 正常进度为“本月已过自然日数（含今天）÷本月总自然日数”，不使用星期权重；今日需完成为`max(月度目标 × 今日正常进度 − 截至昨日完成量, 0)`，当天不会随今日实时完成量变化；今日尚需为`max(今日需完成 − 今日实时完成量, 0)`；
- 源日数据未产出时标记`MISSING`并保存`NULL`，页面显示“待ETL”。

建议每日在ERP出票数据稳定后运行，处理顺序为：

1. 读取已发布且覆盖处理日期的目标计划、目标明细及有效责任归属；
2. 一次读取目标周期内所需的ERP出票、承运航段、乘客、平台、GDS和政策员字段；
3. 按指标版本分别计算有效出票承运航段、有奖航段、1A考核有效航段及对应利润；
4. 按“业务日期 + 指标 + 稳定维度键”幂等写入`dws_target_metric_day`；
5. 汇总周期累计实际值，结合计划进度曲线计算完成率、进度差、剩余航段和每日需完成；
6. 幂等写入`ads_target_progress_day`；
7. 记录源数据最大时间、ETL批次和数据状态，缺数时写`PARTIAL/MISSING`，不能将缺数当0。

脚本支持`--biz-date`日跑、`--start-date/--end-date`补数和`--dry-run`核对：

```bash
docker compose run --rm api python -m data_report_api.target_management_daily --biz-date 2026-10-18 --dry-run
docker compose run --rm api python -m data_report_api.target_management_daily --biz-date 2026-10-18
docker compose run --rm api python -m data_report_api.target_management_daily --start-date 2026-10-01 --end-date 2026-10-18
```

Docker Compose 中的独立 `target-etl` 服务默认每15分钟执行一次增量检查（通过
`TARGET_ETL_INTERVAL_SECONDS`调整，最小60秒）。每轮都会刷新当天截至执行时刻的ERP数据；发现新建或修改的
目标后，会根据ADS快照缺口和配置更新时间自动补算目标周期开始日至当天。页面每60秒从目标库刷新一次，并展示
具体统计截止时间。保存目标的请求本身不直接查询ERP，避免长事务和业务库压力；计算完成前继续显示“待ETL”，
不使用假数据或0代替缺失值。

进度页同时提供“立即更新”：后台复用上述增量补算逻辑，并通过MySQL命名锁与15分钟自动任务互斥，避免重复压库；
运行状态写入`target_etl_run`（建表脚本：`docs/sql/target-management-refresh-v1.sql`）。默认手动触发冷却120秒，
等待自动任务释放锁最长30秒。页面轮询真实运行状态，成功后自动读取新快照；失败时保留上一版快照并显示原因。

2026-10-22本地真实数据核对：对2026-10-01至2026-10-21期间18个已配置平台目标和15个已配置GDS目标逐项按参考脚本重算，平台航段/利润及GDS完成量均无差异；补算2026-10-01至2026-10-22后写入12144条DWS和3190条ADS。政策员示例“李思纬”2026-10-21按参考脚本核对为有奖完成935、全部有效出票利润-1713.0982、全部有效出票`trip_count`945、单段利润约-1.8128。该证据证明本地代码连接的真实数据与参考脚本口径对齐，不代表服务器已经部署或业务已经验收。

当前自动任务提供15分钟级的当日快照、补数与迟到数据刷新；当天数值是截至页面所示时间的实时快照，不能视为日终定稿。平台和GDS利润均为出票预估利润而非财务结算利润，其中GDS利润不是原GDS日报脚本既有字段，是否长期展示仍由业务确认。
