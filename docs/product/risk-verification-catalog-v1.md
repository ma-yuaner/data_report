# 风控核对中台目录与ETL V1

2026-11-04用户批准开发；状态：本地实现/验收中，DDL、实际同步、247部署和真实性能未验收。本方案替代此前请求内实时扫描ERP的汇总方式，不改变已确认规则、管理员权限或个人核查记录归属。

## 依据和范围

用户反馈e28822e在247查询单日超时，提供的日志显示Nginx504、MySQL2013读取超时，后端请求132479.4ms、认证102.9ms，最终503。未取得具体慢SQL执行计划，不能认定唯一原因。新方案参考BillMapper本地查询投影、幂等和成功批次保留方法，不继承其数据库、权限、外部服务或财务规则。

数据链路：ERP只读 → 独立清洗脚本按日分批 → sibebid目录及成功覆盖 → 页面汇总/分页 → 点击订单读取ERP详情 → 原核查流程及证据快照。

本轮不新增AI自动判断、生产调度、全历史回灌、ERP索引变更、子表CDC、团队共享结果或新的公共连接配置。现有SQLite核查结果继续使用，避免更换存储时丢失既有确认。目录同步不执行风控公式，不能把盈亏原因非空直接判错。

## 数据契约

DDL：[risk-verification-catalog-v1.sql](../sql/risk-verification-catalog-v1.sql)，明确USE sibebid，只建三张新表，不自动执行。

| 表/主键 | 字段及用途 |
|---|---|
| bi_risk_order_day：issue_date,order_id | 业务/OTA订单号、平台、原因原值、源创建/更新时间、etl_run_id；不存乘客、票号、金额或整单日志 |
| bi_risk_sync_day：issue_date | 最后成功run、日行数、同步时间，成功空日也留痕 |
| bi_risk_sync_run：etl_run_id | 起止日期、running/success/failed、开始/结束、已成功行数、安全错误码 |

出票时间取order_info_issue.issue_ticket_time，业务时区Asia/Shanghai，日范围左闭右开；按order_id关联order_info.id。目录存储同日订单去重，跨日保留关联。API跨日按order_id再去重，同一订单取所选范围内最晚出票日目录记录；不是把日行数相加。原因字段和源订单状态是取数时点值，不是历史出票时点还原。

日期/订单主键、日期/原因/订单索引、订单/日期索引服务查询与跨日去重。源时间DATETIME(6)避免丢微秒。后续分类仍保存原码，只有已核对的RLA013展示业务名称；新增具体公式须独立确认，不从一个案例推广。

核查结果按当前账号最新案例，与目录原因和源update_time比对；变化则未核查。目录不是实时源状态，且update_time不保证覆盖所有子表/日志修改。详情重新取证可能比目录更新，需显式重跑对应日期刷新。原有最新案例匹配上限20000，超限明确拒绝，不截断统计；本轮未迁移为团队结果表。

## 同步与失败

脚本位置：独立data-team-repo的etl_scripts/automation/risk_verification_order_day_etl.py，细节及操作见该仓库docs/business/air_ticketing/risk-verification-etl.md。复用erp_config和sibebid_config，不改公共配置/工具。

首版为显式1至31天的逐日完整替换，可重复执行；不是修改时间水位增量或页级断点续跑。源日期索引及普通EXPLAIN不满足门禁则拒绝读取，不擅改ERP。临时表分批去重，整日完成后事务切换该日目录、coverage和run累计数量，失败保留旧日。全局命名锁防同脚本并发；多日任务允许部分日成功，页面显示各日实际版本与最近失败/未完成提示。

API汇总与订单请求只连接MYSQL_DATABASE=sibebid，使用只读repeatable-read事务，缺日期coverage返回409，不回退ERP、不把未同步当零。缺表/数据库异常返回安全503。局部连接/读写socket等待上限8秒，不延长网关超时；该限制不是端到端性能保证。页面对比汇总与列表的每日批次版本，不一致要求重新查询，避免同步期间展示不同批次数字。

## 发布与验收顺序

1. 数据库负责人在既有、已批准的sibebid连接SQL编辑器执行上述完整DDL；先确认目标库及备份。已有同名表不删除，ETL会拒绝结构不兼容，不自行DROP重建。
2. 清洗脚本服务器进入现有data-team-repo根目录，用该项目Python执行下列命令。示例日期为首个案例出票日，变更日期须使用获准范围。

```bash
python -B etl_scripts/automation/risk_verification_order_day_etl.py --start-date 2026-11-01 --end-date 2026-11-01 --preview
python -B etl_scripts/automation/risk_verification_order_day_etl.py --start-date 2026-11-01 --end-date 2026-11-01 --check-schema
python -B etl_scripts/automation/risk_verification_order_day_etl.py --start-date 2026-11-01 --end-date 2026-11-01 --batch-size 500
```

预期依次offline_preview、schema_and_plans_checked、published和success，均退出0。只有preview完全离线；其余由授权人执行。目标账号需表读写和临时表权限，ERP用已批准只读账号。缺源日期索引/不安全执行计划时停止，将安全错误码交数据库负责人评估，不提高超时硬跑。失败不清库或卷，不连续重试。

3. 确认ETL与247应用实际连接同一个sibebid。247现有data_report目录执行：

```bash
git pull --ff-only origin main && bash scripts/deploy_risk_verification.sh
```

预期退出0。脚本不代执行新DDL或ETL；配置存在、健康UP都不代表目录已同步。进入1818的/risk-verification，选2026-11-01；默认今日若未同步应明确提示。要看今日须另外同步今日，不使用演示数据补齐。

4. 247验收记录实际订单量、API汇总/首屏/筛选耗时，常用单日目标3秒内；同单多票去重、类型及状态下钻一致、人工保存后更新、缺批次/同步失败/跨批次切换均需通过。ETL耗时与页面耗时分开记录。不通过则保留安全日志停止，不把本地SQLite容量测试当247 MySQL性能。

回退应用保留新目录和原SQLite卷；不删除表或恢复旧库覆盖新记录。旧版实时ERP汇总已知超时，不能把回退视为性能修复。生产调度在实际索引、首日数据与速度验收后另行安排。

## 盈亏原因字典映射增量（2026-11-04）

用户确认system_com_type_det、parent_code=PRODUCT_PROFIT_REASON_TYPE；源DDL及TypeDetMapper核对det_code→det_cname，type_code=_SYSTEM_PRODUCT_TYPE。新增sibebid.bi_risk_reason_dict，DDL在docs/sql/risk-verification-reason-dictionary-v1.sql，不改原三表。此前仅RLA013命名被本节替代：名称均取中台字典，未知码保留并标字典名称缺失，不丢订单；RLA013规则身份仍按代码识别，不依据名称改变核查结论。

ETL正常运行先同步指定parent/type字典，再处理日期订单。空源/重复码/空名称/超5000条拒绝发布，原子替换失败保留旧字典；不按字典状态剔除历史名称。--dictionary-only仅更新字典和任务记录，保留日目录与覆盖，不读订单明细；仍校验原表结构和计划。字典版本纳入页面汇总/列表一致性检查。页面查询只读中台，无ERP字典查询。

执行顺序：先在sibebid执行增量DDL，再更新216清洗代码，用monitoring解释器检查并只同步字典：

```bash
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_order_day_etl.py --start-date 2026-11-01 --end-date 2026-11-01 --check-schema
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_order_day_etl.py --start-date 2026-11-01 --end-date 2026-11-01 --dictionary-only
```

预期先schema_and_plans_checked，再dictionary_synced、dictionaryRows>0、orderRowsRead=false。失败停止，保留安全错误码，不清表或跨类补名称。随后247更新API/web，验收分类/筛选/列表中文名称与源字典一致，3177单数量不因映射改变。五分钟任务无需改cron命令，新脚本每次会同步字典。此前2026-11-01日目录3177条已获用户真实成功回执，无需为了补名称重读订单；新字典实际同步与页面仍待验。
