# M01只读数据核验工具

日期：2026-10-31。已获用户选择M01工具开发；范围为生成只读SQL和核对本地导出，不连接生产、不修改ETL/配置、不开发新页面。只使用Python标准库，不装依赖、不调用AI。

入口：`scripts/gds_m01_check.py`。业务依据为[固定规则V1.2](../business/air_ticketing/gds-mpis-governance-rules.md)及[M01契约](../product/modules/resource-governance/m01-metric-contract-v1.md)。工具可用不代表M01真实数据或业务语义已验收。

## 最短操作流程

在应用仓库根目录执行；`python`可替换为已有Python 3.12解释器。以下输入均由用户现有Hive工具只读导出，输出留在已忽略目录，不提交Git。

```powershell
# 1. 生成结构查询。退出码2表示还需要结构，不是脚本崩溃。
python scripts/gds_m01_check.py prepare --output .test-artifacts/gds-m01/structure
```

在Hive运行生成的`Q0_structure.sql`，把完整DESCRIBE结果保存为UTF-8 CSV、TSV或纯文本（字段名、类型）。支持Beeline边框；需要字段缺失时不生成Q1，不因仓库DDL存在而冒充真实结构已验证。

```powershell
# 2. 根据真实结构生成Q1。每轮用新目录，旧证据不会覆盖。
python scripts/gds_m01_check.py prepare --schema .test-artifacts/gds-m01/describe.tsv --expected-records 33078 --output .test-artifacts/gds-m01/query-v1
```

默认条件：2026-10-29、1A、BKK→TYO、成人1、去程间隔1—179、停留2—15。保留混合旅客，不擅自增加纯1ADT过滤。库/表、日期、城市、成人及范围可通过`--help`中的参数调整；若改变条件，原33078不再是默认有效对照，不要机械沿用。工具只支持1A本轮口径。

实际结构中的`otacode`/`ota_code`、`otasitecode`/`ota_site_code`两组已明确别名可映射，导出仍统一规范表头；同组同时存在两个候选时拒绝猜选。其他字段缺失必须先核对。生成只表示列名齐备，不证明字段语义、类型、分区格式或线上ETL版本均正确；执行前仍检查`dt`是yyyyMMdd及其小时/分钟后缀。

在Hive执行生成的`Q1_aggregate.sql`，完整导出UTF-8 CSV/TSV，有表头，不截Top N、不拼接重复导出、不混入CLI运行日志。保留执行SQL、范围、执行时间及是否更改条件的回执。工具不能独立验证人工实际运行的SQL与scope声明是否一致。

```powershell
# 3. 核验聚合导出。
python scripts/gds_m01_check.py check --scope .test-artifacts/gds-m01/query-v1/scope.json --results .test-artifacts/gds-m01/aggregate.csv --output .test-artifacts/gds-m01/check-v1
```

交付文件：`report.txt`先看结论/限制；`report.json`保留输入指纹、条件、计数和完整分布；`resource_flag_matrix.csv`横向看接口组、MPIS/NDC标记、gdsreal原值及加权日志记录数。不输出traceid/referenceid明文或完整请求体。

## 核验内容及边界

- 每组成功＋失败＋未知必须等于records；非空覆盖及其他计数不能超过records；聚合维度重复、非法整数、范围不符成人数、缺列、截断行格式直接拒绝，不发布半份统计。
- 按records加权汇总，而非数聚合行；MPIS/NDC true、false、NULL、其他值分别展示。同时true及接口组/标记不一致列为核对线索，不自动认定业务错误，别名优先规则仍需技术确认。
- 分开展示纯成人、混合旅客、旅客数未知/无效；成功字典沿仓库0成功/1失败，未知值单列。阶段按apimethod/api_method原值分布，不把所有记录称为唯一查询需求。
- traceid/referenceid只统计非空量，不去重、不证明关联成功。`apiRequestSubCount`只是ETL处理后候选计数，不能称实际外呼/计费量。
- 总量有差异就保留差额，不按33078填平；即便总数一致也不能证明未截断。没有对照数时明确未对照。真实0和NULL分开，空结果不算完整性通过。
- 普通MP实际调用量、NDC实际调用量、唯一入口量和MPIS实际替代率继续不可得；`m01Complete=false`始终保留，待技术执行/关联语义及真实同范围数据补齐。
- 结果文件最多256MB、20万聚合组；超限拒绝，不能拿部分结果冒充全量。结构文件限2MB。统计只写用户指定的新输出目录，不改输入文件。

退出码：0表示聚合算术检查通过但语义仍待核实；2表示缺结构、缺字段或有待复核项；1表示输入/执行错误。退出码0不代表业务验收、生产部署或M01完成。原例子仅针对一日一条航线，不扩展成自动关闭、阈值或缓存配置动作。
