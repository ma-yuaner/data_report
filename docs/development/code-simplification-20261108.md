# 数据中台代码精简交付

2026-11-08。任务CODE-SIMPLIFY-20261108，用户已授权按只读审计方案实施。初检为应用fat_cy 3df5b36及ETL原检出50329d4；最终交付重放到应用最新main 82b1e3d与ETL最新main 299056f，并重新验证。主会话执行与自检，无独立代理审查。L4按跨模块风险保留事务、权限、版本和行为等价验证，裁剪独立委派。原有未提交文档、KPI、清洗脚本和缓存改动保留。

## 已实现

- 风控查询日期、分页参数和指标投影收敛到services/risk_query_contract.py；复核编码、时间、版本校验收敛到risk_review_contract.py。旧总览和跟进模块保留必要导入兼容。解除自动核实与总览、分析与快照、跟进与工作流三组循环。
- ADM响应适配进入现有api/common.py；通知有效性校验进入adm/workflow.py，收件箱和Worker共用。解除两条ADM循环路径及跨HTTP领域依赖。
- 监控通知端点、模板和路由进入monitoring_notifications.py，共用解析和数据源支持进入monitoring_support.py。MonitoringService保持原入口并继承通知能力，规则编译和投放同事务调用保持现有路径。主文件从2374行缩为1619行。
- 投放政策页两套表单共用composables/usePlacementDimensions.ts。保留历史选项、平台编码回填、失效站点/产品清空及两套表单的独立状态。
- 资源治理路由、首页预加载和评审原型直接使用领域页面，移除7行转发视图，并同步契约生成器。
- 独立ETL三个利润报表共用profit_report_io.py的FI取数和图片/文件发送。保留三个脚本入口、业务查询、Excel结构、水印及原上传/重试策略。航司发送超时1200秒，平台/政策600秒。

最新main上本次涉及源码及新增模块合计6474→6658行，显式导入兼容、职责拆分和导出适配增加184行；三份报表加共享模块合计5253→5129行，减少124行。行数反映结构变化，不作为性能或正确性证明。

## 验证

| 检查 | 实际结果 |
|---|---|
| 最新main的监控/投放/ADM、风控快照/人工工作流/订单分页、提取等价及报表离线回归 | 156 passed，19.24秒 |
| 最新配置观察与Flask隔离读取验证 | 23项通过，退出0 |
| 监控方法AST、原SQL投影和日期边界对照 | 9 passed，1.74秒 |
| 三报表离线对照、600/1200秒参数、HTTP失败/拒绝/异常、连接释放、业务函数AST | 17 passed，3.80秒 |
| 资源治理既有交互测试 | 6 passed |
| 投放维度联动反例 | 6场景通过 |
| 应用及ADM评审原型类型检查、修改文件ESLint、README目录核对 | 退出0 |
| 前端生产构建 | 最新main退出0，24.88秒；使用本轮已成功的工作区TEMP/TMP与Vite runner；保留大分包警告 |
| Python/前端架构扫描 | 5条循环→0，跨HTTP依赖→0；前端检查通过。25处存量跨模块私有导入仍使总检查退出1 |
| Ant组件登记检查 | 存量AdmDetailView的a-typography-text映射未登记，退出1；该文件与审计基线逐字节相同 |
| 风控清洗与分析运行时导出check | 最新main两套检查均退出0；分析导出器适配新契约位置，6份生成输出与82b1e3d基线逐字节一致，无须改生成副本 |
| Git空白检查 | 本次代码通过 |

最新main合入保留NORMAL_REASONS与所有后续规则、增量和配置观察变更，工作流冲突按最新main全部内容追加本次记录解决。分析导出器从新契约位置提取，保留独立运行时原有_period名称和输出字节。原检出早于这些发布，其清洗导出漂移由对齐最新main后复验消除。

第一次监控回归暴露迁移遗漏的DAILY_SEGMENT_EVENT导入，订单分页回归暴露METRIC_PROFIT导入遗漏，均已补齐并在上述最终结果中通过。新增未定义符号扫描无发现，旧STRUCT-001的两处未定义名称仍保留基线。首次构建受系统TEMP文件删除权限阻碍，原检出构建改用项目约定的工作区TEMP/TMP后通过；最新main工作树的新TEMP仍受限，复用本轮已成功的原检出TEMP后构建通过。浏览器沿用Work禁用限制，真实数据库、外部消息、服务器、业务验收与实际负载未验。

本地证据位于.test-artifacts/code-simplification-20261108/，含源码基线、离线用例、构建与架构日志及verification-summary.json。测试文件仅本地忽略保存。

可复验入口为项目既有backend/tests/test_monitoring.py、test_smart_placement.py、test_adm_v05.py，已有本地risk-analytics-v4/test_snapshot.py及risk-workflow-v3/test_workflow.py、test_orders.py。按AGENTS确认的bundled Python在进程内加入.venv/Lib/site-packages运行pytest，禁用cacheprovider；前端用node调用vue-tsc、ESLint及scripts/resource-governance.test.mjs。构建通过bundled Python subprocess在frontend运行node node_modules/vite/bin/vite.js build --configLoader runner，并将TEMP/TMP指向上述证据目录的esbuild-temp。

## SQL与发布

本次SQL文本、口径和表结构未改。已迁移的查询源码同步归档工作区SQL指标资产库，编号RISK-CHECK-036和MONITOR-SQL-001；索引、来源、SHA-256及未实库状态已保存。归档源码依赖应用包，不作为独立执行脚本。

应用先在当前fat_cy记录本次改动，再将该提交重放到已核对的两端main共同版本82b1e3d上复验后交付。ETL报表交付提交13b8587在299056f基础上只包含本次5个文件。ETL原检出与远端main有2/47提交分叉，交付通过干净工作树将本次报表提交单独接到已核对远端main，避免纳入原检出的另外两条提交及未提交改动。最终提交与推送结果见本轮Git历史及交付消息。本次没有服务器部署或正式清洗执行。通知申请人按项目约定另待本次确认，未确认时仅完成其他交付。
