# 按日核实事实与更新策略 V1

用户2026-11-05确认采用首次历史回补、近窗口定时刷新、旧单变更追补及结果历史留存；随后明确窗口为最近一个月，替代此前近三天建议。实现按最近30个出票日（含今天）处理，五分钟是DolphinScheduler触发频率，不冒充所有历史更改五分钟内完成的SLA。首次回补命令起点按用户同意的示例2026-01-01，仍为可修改显式参数，Agent不执行生产回补或DDL。

## 本次页面问题及修复

此前页面统计依赖当前账号的auto_results快照，并将加载请求视作源刷新请求；一个跨多日加载因缺日失败后仍可能使已存在结论过期。每次ETL重跑换目录批次，又会使旧账号快照失效。因此仅扩大筛选范围就出现“全部待核实/过期”，不代表已成功结果从数据库消失。

实库只读核对：11月3—5日已有当前V12准备结果；11月1/2日仅有目录、没有当前准备结果。修复后1—5日直接读取日事实，能显示已有201问题/54通过/3不足，仅另98条已接规则待核实，缺日明确提示；3—5日显示201/54/3，无待核实。这些是读取时观测，不作为将来固定数量断言。

`risk_prepared_facts.py`统一校验每日目录/结果/诊断批次、原因、源时间、规则版本、运行时SHA及结果JSON；事实不是账号加载缓存。概览/列表/详情读同一目标库的成功日结果，部分缺日不阻断其他日；完全无目录仍显示未同步，不冒充零业务。查询仍最多31天，跨日按订单ID取期间最后出票日去重，不要求所有日期源版本相同；历史日期正常长期保留。

单据详情带明确issueDate，避免从所选旧日跳到该订单另一个新出票日。只读查询不创建账号任务或写核实结果；同证据重跑的稳定结果ID由日期、订单、规则、引擎、证据哈希生成，不随批次号改变。个人抽查按owner读取；保存时在同一目标事务锁定实际事实并核对结果ID，源证据/规则变化后旧抽查不移植到新事实。原账号快照只作历史回退，不能冒充当前事实。

页面“查询最新清洗结果”直接刷新日事实，不再要求先把整个范围加载到账号；每分钟只读刷新已生效范围，隐藏页面、正在查询或打开详情时暂停，保留未提交表单。缺失日期及每日报告直接来自当前日批次，历史加载任务失败不污染当前页面。

## 更新与存储契约

1. 历史回补：显式起点分批、成功空日有覆盖、目标持久状态续跑；不依赖随机Worker本地文件。
2. 最近30日：每次调度逐日全量准备/原子发布，覆盖窗口内父表和子表修改、删除与出票日期迁移。日期迁移到窗口外由变更追补或历史轮巡补偿，不能只覆盖新日期而遗留旧日。
3. 窗口外：order_info.update_time有索引，按固定上界及重叠时间分批识别；旧/新出票日和相关核算根依赖持久入队，再推进水位。出票、航段、乘机人无更新时间索引，关联表无时间字段，不能全表轮询伪称实时；以持久旧日轮巡补偿，报告待办与范围。配置变动可大范围入队；更早子表/硬删除/机场变动的延迟取决于轮巡，不作五分钟承诺。
4. 历史：当前结果与变化版本分开保存；未变化的重复检查记录批次，避免每五分钟重复存整份JSON；变化、回退、退出核实范围和首次旧结果基线均留痕，不自动删除。历史与当前日结果、诊断及队列确认同事务提交，失败不写成功历史。

新增持久表的DDL由用户在实际ETL目标库执行，生产调度新入口需替换旧节点，不并行运行两种发布任务。应用按日读取修复兼容当前两张prepared表，可先部署API/Web恢复查询，不必等待历史回补完成。新增历史/队列功能需新DDL及新入口后才生效；不把源码存在称为已经存储全历史。

## 验证及接续

主会话先核对适用AGENTS、元数据与用户日志；独立预期由`/root/risk_permission_review`在读实现前提出。主会话实现应用，`/root/risk_lifecycle_etl`实施ETL且不写应用/MYE；项目限制任一时刻仅一位活动子代理，ETL完成后再终审。源码/模拟/实库只读/服务器写入/页面验收分别记录，当前服务器新策略未部署。

本地证据位于忽略目录`.test-artifacts/risk-lifecycle-20261105/`，包括源元数据、1—5/3—5目标只读核对、窗口回放及新事实测试。SQL见`docs/sql/risk-prepared-facts-v1.sql`，同步归档RISK-CHECK-009；ETL新DDL及队列SQL另按实际产物归档。完成后更新本节最终测试、独立审查及发布回执；MYE仅合并刷新契约、证据身份及覆盖状态的通用经验。

## 最终集成回执

- 主会话应用事实与权限31项通过；原规则217项通过、2项旧在线worker夹具排除（已被离线架构替代，不计通过）。ETL最终35项通过。Python本地3.12.14；服务器既有日志3.11.9仅证明旧入口，新的四模块按3.11语法契约检查。
- 实现者`/root/risk_lifecycle_etl`完成初版；`/root/risk_permission_review`独立需求预期、源码审查与定向返工复核；主会话实现应用、集成修复、执行验证和发布。复核发现结构门禁、变更续接、提交事实收尾漏报；主会话另修历史分块、近期优先、失败回补不堵塞。报告写/连接清理/锁释放失败不再覆盖已提交日期。
- 代表30日只读取证3893条日订单、167次业务证据SQL、239.672秒，未发布；不含目录/目标写入，不能称五分钟SLA已验。此前生产旧入口成功日志为3日258条日订单核实，与新30日策略分开记录。
- 新SQL按RISK-CHECK-009/RISK-DDL-010/RISK-ETL-011归档到工作区SQL指标资产库；无凭据或订单明细迁入MYE。
- 原始本地索引：应用`.test-artifacts/risk-lifecycle-20261105/`、ETL`var/risk-cleaning/test_lifecycle*.py`、源回放`rolling30-audit.local.json`。记录命令、工作目录、退出码与关键观察，测试及日志不推送。
- 尚未覆盖：目标库新五表正式执行、生命周期MySQL真实写事务、随机Worker续接、真实调度整轮时延、新版API/Web服务器部署、浏览器与业务验收。浏览器被宿主关闭，未绕过设置。

### 部署顺序

1. 应用API/Web可先按现有普通发布流程更新；只读日事实兼容已存在两张prepared表，不必等待历史回补。部署后选择1—5与3—5，已有成功日期结论应保持一致，1/2缺日独立提示。
2. ETL拉取新发布后，由部署人在既有目标库执行`data_pipelines/src/ddl/risk-lifecycle-v1.sql`五表DDL。现有目录/结果不清空，DDL不等于已回补。
3. 按ETL`docs/business/air_ticketing/risk-lifecycle-v1.md`先运行绝对路径`--check-schema`，成功退出0后，把原DolphinScheduler节点替换为新lifecycle入口，每5分钟调度，历史起点显式按实际需要填写。不要并列运行新旧发布节点。
4. 验证报告status/exitcode、publishedDays包含窗口日、pendingDays与oldestPendingAt趋势，抽查历史发生变化才新增版本、不变只更新检查时间；失败旧成功事实保留。五分钟是触发间隔，整轮性能需Worker实测。

独立终审已确认作业级上下文覆盖阻断关闭；本轮仅源码定向复核，未重跑生产。MYE迁移经独立审查允许合并，仅含通用方法；发布顺序表述按项目依赖与授权保留，未迁移公司实现。

### 验证命令与退出码

本轮实际目录为应用工作树`D:/data_center_code/data_report_ui_20261105`及ETL工作树`D:/data_center_code/.worktrees/risk-catalog-etl-20261104`；Python为`C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`，不是服务器解释器。命令原文及输出在`final-manifest.local.json`和各`*.receipt.json`，不进入Git。

| 目录 | 实际命令（PY/NODE为上述捆绑运行器） | 退出码/观察 |
|---|---|---|
| 应用 | PY -B .test-artifacts/risk-lifecycle-20261105/run_tests.py | 0，31通过 |
| 应用 | PY -B .test-artifacts/risk-bet-20261105/run_bet_tests.py | 0，217通过，2排除 |
| ETL | PY -B -c 导入pytest运行var/risk-cleaning/test_lifecycle.py及test_lifecycle_integration.py | 0，35通过，完整argv保留本地回执 |
| 应用 | PY -B scripts/export_risk_cleaning_runtime.py --target-repo D:/data_center_code/.worktrees/risk-catalog-etl-20261104 --check | 0，V12/SHA未漂移 |
| 应用 | PY -B scripts/check_readme.py | 0，49菜单/214路由 |
| frontend | NODE node_modules/vue-tsc/bin/vue-tsc.js -b --pretty false | 0 |
| frontend | NODE node_modules/eslint/bin/eslint.js src/views/RiskVerificationView.vue src/components/RiskAutomaticDetail.vue src/api/riskVerification.ts --max-warnings=0 | 0 |
| frontend | NODE node_modules/vite/bin/vite.js build | 1，4053模块已转换，esbuild-transpile删除临时文件Access is denied；默认/工作区临时目录及提升执行均复现，未改依赖或绕过文件权限 |
| ETL | PY -B etl_scripts/automation/risk_verification_lifecycle_etl.py --history-start-date 2026-01-01 --preview | 0，未查源/未写目标 |

本地构建产物未交付，服务器需按既有环境重建并验证；源码推送可取得不等于构建包已验。浏览器关闭、Worker新策略与生产目标写入未验事项不由以上通过项抵消。
