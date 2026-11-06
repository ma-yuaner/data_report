# 风控分析 V4：15分钟快照（2026-11-07）

用户确认：每15分钟刷新；分析不要求逐次实时计算。

**执行位置已更正为216独立ETL**：后续用户明确要求统一生产调度，替代最初247容器方案。旧shell入口现明确退出2，不再启动Docker；下文为当前交接。主会话实现与自检，无独立代理验收。

## 行为与口径

页面不再读取逐单目录计算分析，因此不受原HTTP的20000单上限影响。日期范围仍限制1至31天。后台只读取sibebid已发布目录、自动核查、整单利润、人工记录和案例；不连接ERP，不重算核心核查规则，不替代原清洗任务。

每份快照以查询结束日为键，先在结束日前30日至结束日内为每单选择最后出票日，再按该日期/类型/部门分桶。查询起日仅汇总预生成桶；不能简单相加独立日订单数，否则跨日订单重复。总利润继续按整单出票issue_profit合计，CNY、不加佣金；利润缺失的组输出空值。多部门分别归属，不可相加冒充总量或责任认定。

当日每轮刷新；其他结束日由查询POST排队并持续按周期核对来源版本。新请求不触发HTTP逐单扫描。默认每轮最多32个结束日、每批1000单、最多50000维度桶；不是订单数上限。历史请求较多/执行耗时/失败时不保证15分钟内完成。来源签名未变只更新最近核对时间。目录日覆盖不完整会提示；完全未同步不显示零订单。

源读取和页面读取使用独立一致性事务；发布删除旧桶、插入新桶、更新清单同事务。请求代次防止刷新中新增请求丢失。命名锁阻止并发调度。失败保留最近成功结果并退避15分钟，日志仅安全错误码；提交已确认但清理失败单独报告，不冒充回滚。页面显示源截止/最近核对/目录同步时间，超过30分钟提示；人工核实和案例记录仍即时保存，统计在下次成功刷新体现。

订单明细筛选区沿用Ant Design Vue；按钮容器与输入框底部对齐，不改筛选含义。浏览器按项目规定禁用，未作实际屏幕验收。

## 部署交接（未执行）

新表仅存分析汇总和请求，不复用逐单事实表；与事实表逻辑关联，无数据库外键，发布事务和快照代次保证读一致。每个结束日覆盖旧成功版本，不保存历代；历史结束日清理策略暂未制定，不自动删除。新增结束日会增加存储和调度成本，应监控队列/执行时间及日志，运维按现有方式轮转日志。

目标MySQL、InnoDB、utf8mb4；实际服务器版本/排序规则未回读。先在隔离MySQL验证DDL及只读核验脚本，现有同名旧表需比对，CREATE IF NOT EXISTS不迁移不兼容列。部署次序：建表并核验→发布api/web→手动首轮→安装15分钟cron。未建表不回退ERP，接口报未就绪。失败可暂停该cron并保留表和旧快照；不提供自动删表回滚。

在216 DolphinScheduler以lywz、现有Python3.11.9配置独立Shell：

```bash
set -eu
export TZ=Asia/Shanghai
/opt/module/miniconda3/envs/python3.11/bin/python -B \
/home/lywz/data-team-repo/etl_scripts/automation/risk_verification_analytics_etl.py
```

每15分钟一次，不再安装247 cron或依赖Docker。首次先分别加`--preview`、`--check-schema`；目标仍是sibebid的同两张分析表。原V4 DDL若已执行不用重复建表，先核验，不兼容结构不可依赖IF NOT EXISTS修复。应用保持只读快照，现有生命周期/订单指标清洗保持独立。

216需更新ETL入口与risk_analytics_runtime全目录；详细部署/锁冲突诊断见ETL仓库docs/business/air_ticketing/risk-analytics-216.md。应用规则变更时按原流程导出清洗runtime，再执行`scripts/export_risk_analytics_runtime.py --target-repo <ETL仓库>`及`--check`，防止规则/事实身份漂移。分析runtime为应用权威源生成，ETL连接适配使用公共sibebid_config.get_connect/raw_connection，禁止另建凭据URL。

原247任务如曾配置须停用，避免两种入口并列。上述新216任务/DDL均未在服务器执行。

## 验证证据

本机隔离SQLite/合成数据：21项快照测试通过，覆盖25001单、跨日起止去重、请求代次、失败保留、读取与发布一致性、权限/CSRF、目录批次、NULL/零、版本及精确金额、提交后清理失败。25001单约2秒且HTTP仅两次汇总查询，仅为本机模拟，不代表MySQL生产性能。其他回归和前端结果见任务台账。临时测试保留忽略目录.test-artifacts/risk-analytics-v4，不提交Git。真实MySQL事务/索引性能、元数据注释、服务器Docker/cron、浏览器和部署均未验。

## 中文字段字典

所有列无显式DEFAULT；必填列由服务明确写入，NULL列默认NULL；0仅表示已知零，不能表示未生成。时间统一Asia/Shanghai无时区DATETIME(6)。表/列注释已写入DDL，未回读实库。

### bi_risk_analytics_snapshot

一行代表一个查询结束日期的当前快照及刷新队列；主键end_date，重试索引用于调度候选。

| 字段 | 中文含义 | 类型 | 可空/约束/来源与样例 |
|---|---|---|---|
| end_date | 查询结束日期；每份支持结束日前30日至当天任意起日 | DATE | NOT NULL；目录日期/查询参数，如2026-11-06 |
| snapshot_id | 成功发布快照代次；NULL表示尚未生成，不得显示为0 | CHAR(32) CHARACTER SET ascii | NULL；服务UUID hex32，与桶逻辑关联 |
| schema_version | 聚合契约版本，V4与旧版本不混读 | VARCHAR(40) CHARACTER SET ascii | NOT NULL；服务常量risk-analytics-v4 |
| source_signature | 目录/核查/指标批次及人工记录版本签名，未变化不重复计算 | CHAR(64) CHARACTER SET ascii | NULL；元数据SHA256 hex64 |
| source_cutoff | 一致性读取开始时刻，Asia/Shanghai；不是ERP实时核查时刻 | DATETIME(6) | NULL；服务上海时间，如2026-11-06 12:00:00.000000 |
| generated_at | 本份汇总生成完成时刻，Asia/Shanghai | DATETIME(6) | NULL；服务上海时间，如2026-11-06 12:00:00.000000 |
| checked_at | 调度最近成功核对来源签名时刻，未变时不改生成时间 | DATETIME(6) | NULL；服务上海时间，如2026-11-06 12:00:00.000000 |
| requested_at | 最近查询请求或当日定时刷新请求时刻 | DATETIME(6) | NOT NULL；服务上海时间，如2026-11-06 12:00:00.000000 |
| request_generation | 请求代次递增，防止处理过程中到达的新请求丢失 | BIGINT | NOT NULL；服务队列递增代次，如1 |
| processed_generation | 本次已完成请求代次；小于请求代次表示待刷新 | BIGINT | NOT NULL；服务队列递增代次，如1 |
| retry_after | 失败退避后允许重试时刻，Asia/Shanghai | DATETIME(6) | NOT NULL；服务上海时间，如2026-11-06 12:00:00.000000 |
| last_error_code | 最近刷新安全错误码；保留旧快照，不存原始数据库错误 | VARCHAR(100) CHARACTER SET ascii | NULL；服务生成/维护 |
| order_count | 31日窗口去重订单数；NULL未生成，0为已生成空结果 | BIGINT | NULL；事实计数，单位单，如0/1 |
| body | 快照JSON：窗口、源日覆盖及规则/字典版本，不含逐单或乘客明细 | LONGTEXT | NULL；来源元数据JSON，version/catalogDays等，无乘客明细 |
### bi_risk_analytics_bucket

一行代表结束日/最后出票日/维度/维度值；复合主键去重，读取索引按结束日/代次/日期筛选；每份清单对应多桶。

| 字段 | 中文含义 | 类型 | 可空/约束/来源与样例 |
|---|---|---|---|
| end_date | 所属查询结束日期，与快照清单关联 | DATE | NOT NULL；目录日期/查询参数，如2026-11-06 |
| issue_date | 该结束日下每个订单的最后出票日，跨日订单只落一个分桶 | DATE | NOT NULL；目录日期/查询参数，如2026-11-06 |
| dimension | total总量、category原因分类、department业务部门 | VARCHAR(16) CHARACTER SET ascii | NOT NULL；服务固定枚举total/category/department |
| group_hash | 维度原值SHA256，与日期/维度构成主键 | CHAR(64) CHARACTER SET ascii | NOT NULL；group_key的SHA256 hex64 |
| group_key | 真实分类编码或部门原值，总量为total，不拼接用户SQL | VARCHAR(200) | NOT NULL；目录字典/指标部门，如合成部门A |
| group_label | 该快照的分类或部门显示名称，不代表责任认定 | VARCHAR(500) | NOT NULL；目录字典/指标部门，如合成部门A |
| snapshot_id | 发布代次，必须等于对应清单，避免读取混合版本 | CHAR(32) CHARACTER SET ascii | NOT NULL；服务UUID hex32，与桶逻辑关联 |
| orders | 该分桶去重订单数；部门多归属行不可相加为总量 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| auto_passed | 当前有效自动通过订单数 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| auto_concluded | 自动通过加疑似问题订单数，不含证据不足 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| human_reviewed | 当前有效人工无问题或有问题订单数 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| human_problems | 当前有效人工有问题订单数 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| included_errors | 当前有效人工问题且案例计入差错订单数 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| profit_missing | 利润缺失或指标批次未就绪订单数；大于0则该组正式合计为空 | BIGINT | NOT NULL；事实计数，单位单，如0/1 |
| known_profit | 已知整单出票利润之和，CNY；存在缺失不得冒充完整合计 | DECIMAL(38,4) | NOT NULL；整单出票利润累加，CNY，如-12.5000，不舍入 |
| known_loss | 已知负利润订单利润之和，CNY，保留负号 | DECIMAL(38,4) | NOT NULL；整单出票利润累加，CNY，如-12.5000，不舍入 |
