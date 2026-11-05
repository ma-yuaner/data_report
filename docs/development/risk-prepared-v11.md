# 风控批量清洗与证据不足自查 V11

2026-11-05，用户授权将慢且反复出现证据不足的“更新并核实”抽离为清洗，由Agent批量归因迭代，不再等用户逐单报错。本轮主会话磐石/星桥/明鉴执行，未委派；使用chief-of-staff、frontend-design。更换的是取证/发布架构，RLA013和RLA040业务公式、真实缺失仍阻断、管理员及账号结果隔离保持。

## 实现与生效范围

1. 独立清洗入口 `etl_scripts/automation/risk_verification_prepared_etl.py` 复用原日目录ETL的日期索引门禁、只读一致快照、MySQL命名锁、公共get_connect/raw_connection、字典及逐日事务发布。新增批量订单/携程关联闭包/出票/年龄/航段/机场取证，查询按500个ID分块，拒绝源全表/全索引扫描；不逐票往返ERP。每个源表须InnoDB；公开配置不改，不输出凭据/旅客资料。
2. 历史配置按变更区间缓存，完整旧日志采用创建基线＋修改计数＋唯一时间＋字段新旧链校验后还原，支持JSON、平台/航司/供应商/PCC/地域/舱位及有效期；日志版本恒0不单独当成缺失。未知字段、断链、时间冲突等保留不足。独立状态动作只有新状态，没有旧状态时不得臆造历史启用状态；仅有可靠异平台/航司证明才能排除。
3. 新表 `bi_risk_prepared_order` 保存核实结果/证据哈希，`bi_risk_prepared_day` 保存成功日覆盖/诊断；临时表risk_prepared_stage分批准备，不把整日结果堆在内存。目录、正式核实结果、诊断在原publish_day同一InnoDB事务切换，失败保留旧日成功数据；零日明确发布成功覆盖。单日独立发布，不假称31天同一快照。
4. 页面按钮改为“加载清洗结果”，只读sibebid并为当前账号保存结果视图，不连接ERP。所选各日必须有与目录同批次、当前V11规则和相同运行时SHA的完整结果；目录源版本/原因不一致、缺日期、旧版本、超2000单等明确失败，不使用部分结果，也不退回在线逐单扫描。核实时间保留清洗计算时间，加载时间另存；旧结果和抽查不删除。
5. 核实规则仍以应用源码为正式入口，通过 `scripts/export_risk_cleaning_runtime.py` 离线导出标准库运行时到ETL，生成清单及两端匹配的SHA。纯导出文件不可手改；更新规则后必须重导出、--check并重跑对应日期清洗。ETL不依赖Flask、应用部署目录或API进程；preview在Python -S下通过。
6. 每批清洗自动输出状态数、证据不足分类、有限样本内部ID、涉及规则、耗时、源业务SQL次数，成功批次入日诊断表。`--audit-only`是可重复的纯只读全日期自查，不建表/写目录/写结果；先检查源字段/快照引擎及执行计划。解析待审、历史账本缺失、历史状态缺修改前值、金额/乘机人/范围不足分别列示。运行报告含内部ID，仅留忽略目录var/risk-cleaning，不进Git。

## 验证证据

- 同一2026-11-01至05范围，初轮58个已接规则入口单（携程关联后60个订单），无截断；原逻辑24满足/2问题/32证据不足，32项均落在历史解析。
- 自主聚类检查发现5条主要历史候选，补齐完整旧账本的地域/PCC/有效期及相关规则阈值还原后，55满足/2问题/1不足。剩余1单为规则120在出票后挂起、缺修改前状态，不臆造；错误说明已改为“历史配置状态无法还原”，不再仅说版本断档。
- 缓存后的同范围单批源取证8次业务SQL，提取0.187秒、取证计算合计0.453秒；同机逐单20单1.359秒，逐项结果一致。两个数量不同，不给虚构的同比提升率。这里不含源目录全日扫描、目标正式写入或页面网络，不冒充216/247服务端端到端性能。
- 最终独立运行时audit-only已真实只读逐日覆盖全部58个入口单：11-01为12满足/1问题，11-02为5满足/1不足，11-03为14满足/1问题，11-04为10满足，11-05为14满足；逐日约0.515/0.578/0.781/0.875/0.516秒。包含源字段/InnoDB/EXPLAIN检查，无正式发布。
- 118项本地定向测试通过（最终回执见本轮验证）；包括新批量内存重放、拒绝意外SQL回退、行对象隔离、源计划门禁、目录/结果/诊断同事务回滚、零日与未准备日区别、旧版本/运行时漂移/源批次不一致、账号隔离、加载事务部分失败回滚以及原业务回归。原2项“页面在线扫描ERP”的旧架构测试保留在本地但被新“页面绝不连ERP”测试替代，不计通过。新增测试只在本地忽略目录。
- 前端类型及相关ESLint通过；运行时--check和标准库-only preview通过。未执行真实目标DDL/DML、未安装调度、未登录216/247、未部署或业务验收；浏览器禁用未重试。目标事务证据是隔离游标，不冒充实库验证。

## 上线顺序（部署人执行，不能只更新API）

1. 保留216/247各自本地改动，确认216的sibebid_config与247应用MYSQL配置指向同一已批准目标，不只核对库名。目标必须sibebid，源ERP与目标不得同库同连接。
2. 先由数据库部署人执行 `data_pipelines/src/ddl/risk-prepared-v11.sql`（应用相同副本docs/sql/risk-prepared-v11.sql），只创建两张专用正式表；ETL/应用均不自动建表。旧表不ALTER、不清库、不删卷。执行后check-schema验证主键、类型、长度和InnoDB，CREATE IF NOT EXISTS不是兼容性证明。
3. 216原ETL仓库更新main，按以下绝对入口先预览，再检查，再执行显式日期；不要使用系统python3.6，也不升级系统依赖。

```bash
cd /home/lywz/data-team-repo
git pull --ff-only origin main
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_prepared_etl.py --start-date 2026-11-01 --end-date 2026-11-05 --preview
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_prepared_etl.py --start-date 2026-11-01 --end-date 2026-11-05 --check-schema
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_prepared_etl.py --start-date 2026-11-01 --end-date 2026-11-05 --report /home/lywz/data-team-repo/var/risk-cleaning/first-run.json
```

首次其他日期用对应显式范围重跑，1–31天，默认每批250/单日最多10万已接规则单，原源出票上限200万、关联上限保留。发布日志published只表示任务发布成功，须查看diagnostics分类，不能等同业务无问题。

4. 247原应用根目录更新main后 `bash scripts/deploy_risk_verification.sh`，普通无参数不执行新DDL；API/Web均更新。端口1818/5160保留。打开页面选已清洗日期，查询后“加载清洗结果”；核实版本V11、清洗时间、日报告以及原2问题/1真实不足。新表/批次未就绪应明确报错，不能回退ERP。
5. 后续用新独立入口替换旧的“仅目录”清洗入口；不能继续只跑旧目录脚本，否则目录批次改变而准备结果没变，页面将正确拒绝加载。新脚本可接既有调度，日期参数按实际覆盖窗口配置；本轮未修改crontab/生产调度，未擅定频率或默默回灌更早历史。暂停旧入口或回退须保留新表、准备结果与人工抽查；回退应用需与数据版本一致，不清数据修复。

## 后续自查与迭代任务约定

每次相关开发/发版，Agent先读取清洗诊断/审计报告，按原因与规则聚类，批量重放所有已接规则样本，自主定位取证漏接/解析遗漏/版本链问题；先复核源源码和日志，再修复及加反例回归，不让用户充当逐单测试员。只有真正新增业务口径、无法证明的源事实或生产权限需要用户决定。不能为清零不足而跳过未知、补0、改断言或猜状态。

```bash
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_prepared_etl.py --start-date 2026-11-01 --end-date 2026-11-05 --audit-only --report /home/lywz/data-team-repo/var/risk-cleaning/audit.json
```

这是运行时自动归因与项目持久任务约定，不是已启用的后台模型自改代码/自动部署服务；本地审计证据在应用忽略目录.test-artifacts/risk-types-20261105/。完整SQL归档为工作区SQL指标资产库RISK-ETL-005、RISK-DDL-006；前者源读已验证、目标写未实库，后者仅保存未执行。

部署脚本新增只读准备就绪门禁：构建后、切换api/web前校验两张新表及当前V11/运行时哈希与目录同批次至少一个成功日，未就绪抛PREPARED_BATCH_NOT_READY并保留原服务；不自动建表。Bash -n及内嵌Python解析通过，隔离验证0批次拒绝/有批次放行，不冒充服务器健康检查通过。

权限：清洗账号需新表SELECT/INSERT/DELETE/UPDATE及CREATE TEMPORARY TABLES，应用账号需新表SELECT和原账号结果存储权限；不会自动GRANT。正式目标写入与247加载端到端耗时未实测，不能以源只读0.453秒宣称页面已达到同样时延。
