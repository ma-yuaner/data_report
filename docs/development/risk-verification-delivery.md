# 风控核对首版交付与验收

## 最简部署方式

无需另传脚本。部署人在247现有`data_report`仓库根目录执行下面这一条命令：

```bash
if ! git diff --quiet || ! git diff --cached --quiet; then echo '已跟踪代码有改动，停止部署。'; else git pull --ff-only origin main && bash scripts/deploy_risk_verification.sh; fi
```

预期显示5个步骤并最后输出“部署和健康检查完成”，再以管理员访问现有1818端口的`/risk-verification`。仓库/分支不符、拉取、配置、备份、构建或健康检查失败时会停止；保留错误信息，不清库删卷、不反复运行模型。若提示ERP或AI配置未齐，按下方配置段在服务器私密`.env`补齐后重新执行，不把密钥发送聊天。脚本不会自动填写凭据，也不会查询订单或调用模型。

若已完成镜像重建和容器启动，只在第5步健康检查失败，可更新脚本后只验收，不重复构建/重启/权限修复/备份：

```bash
git pull --ff-only origin main && bash scripts/deploy_risk_verification.sh --verify-only
```

验收模式输出的Checkout commit只是当前仓库提交，不将它冒充运行镜像版本。

2026-11-04，Asia/Shanghai。任务RISK-VERIFY-20261104；申请人马远尔。范围见[产品契约](../product/risk-verification-v1.md)。本机实现和隔离验证已完成；真实ERP、DeepSeek、浏览器、服务器部署及业务验收未完成，不能混报上线。

## Launch

沿用1818/5160，管理员打开`/risk-verification`，或现有风控利润/订单页标题区“风控核对”。不重排旧菜单。服务端限定管理员，记录和知识按登录人隔离，首版不是多人共享审核权限模型。

使用明确的ERP配置，必须显式填写`ERP_MYSQL_HOST/DATABASE/USER/PASSWORD`，端口/字符集沿用已有ERP配置。数据库名由部署人核验，不猜历史拼写。风控独立检查显式配置标记，不能回落主MYSQL凭据；建议使用仅SELECT权限账号。配置存在不等于实库已验证。

模型复用知序的DeepSeek协议方式，在中台重新实现，使用本项目独立服务端配置，不读取/复制知序真实key。由部署人在现有私密`.env`编辑，空值表示未配置，不是可直接使用的示例密钥：

```dotenv
RISK_AI_ENABLED=false
RISK_AI_URL=https://api.deepseek.com/chat/completions
RISK_AI_MODEL=
RISK_AI_KEY=
RISK_AI_TIMEOUT_SECONDS=60
RISK_AI_MAX_INPUT_CHARS=18000
RISK_AI_MAX_OUTPUT_TOKENS=2000
RISK_AI_DAILY_CALL_LIMIT=40
```

模型标识核对知序当前实际值后填写；密钥只在服务器私密配置填写，不发送聊天或打印`.env`。确认白名单可发送后设`RISK_AI_ENABLED=true`并重建API，首次用获准脱敏案例。缺配置返回明确失败，无模拟结果兜底、无自动重试；每个证据版本失败3次后停止，失败占每日调用预算，未知usage保持null。

独立`risk_verification_data`卷保存SQLite，仅当前单主机实例使用，不放共享文件系统或扩成多副本。快照含公司订单资料，按受控业务数据保管，不进Git或MYE。

## Drive

1. 按订单创建日期查询1至31天。规则为`profit_reason_type`非NULL、非空串且去ASCII空格后非空；R001也命中，不自行排除。命中只表示待核查。
2. 查看本单出票金额、币种及出票/销售/财务汇率；按需读取日志、状态历史、退改/航变/增值索引。金额保留十进制字符串，内部ID保留字符串。未读、无记录、失败、截断、未接入分别表示。
3. 新建时服务端重新取证，保存不可变快照/指纹/规则版本。取证是顺序读取，不宣称原子快照；子业务索引不是完整明细。
4. 预览AI外发白名单，只有分类、结构化金额/币种/汇率、证据ID及本人已发布匹配知识。姓名、订单号、票号、自由日志及人工理由原文不外发。日志仍供受权人员在中台核对。
5. 显式触发AI审核。校验JSON结构、证据/知识引用及模型完成状态，记录真实回执和用量。汇率公式未知时即使模型声称支持，有效建议仍强制“证据不足”。
6. 人工填写依据并确认；支持/矛盾结论记录override及未核公式警示，不当成程序已完成计算。确认后才能分析。重审保留旧确认历史，清空当前确认；过期版本拒绝覆盖。中断满180秒后可显式恢复，不自动重试。
7. 整理通用知识草稿，填写来源/适用范围，人工发布后才检索。仅本人有效已发布版本参与词面检索；来源确认变化或被清空后不再检索。知识发布不自动成为公式，不是训练模型。

首个“汇率亏损”是用户假设，公式/基准/阈值未确认，不宣称已判断其金额正确。原始报价、动态业务/售后说明、差异页签、自动出票日志及部分子业务完整明细待增量接入，界面明确显示。不会写回ERP、锁单、自动归责或执行交易处理。

## Evidence

基线HEAD `902bd5697b269bcfd1e7949cc8e5a0cd40996efe`，测试对象为其上本轮功能工作区。开始已有RuntimeError修复、AGENTS、财务skill/SQL、证据文档等改动，均保留、不混入本轮业务提交。环境Python3.12.14、现有Node，实际Vite7.3.6。

工作目录`D:/data_center_code/data_report`。完整命令/精确时间/退出码在Git忽略目录`.test-artifacts/evidence/risk-workflow-20261104/`的各`*-record.json`，原始输出在同名`.log`。实际统一入口如下，将最后一项分别设为`python`、`http`、`ui-state`、`type`、`lint`、`components`、`build`；每项均已执行，非仅列期望命令：

```powershell
& C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe .test-artifacts/evidence/risk-workflow-20261104/checks.py python
```

| 对象 | 真实输出 / 进程耗时 / 退出码 | 范围与限制 |
|---|---|---|
| 后端/数据/API定向测试 | `53 passed in 9.66s`，12:23:44—12:23:55；11.163秒；0 | 合成SQLite实际执行非空规则SQL，含NULL/空串/空格/R001；权限/CSRF、分页、串单拒绝、精度、并发恢复、AI结构/引用、知识发布失效；无skip/排除 |
| 真实回环HTTP全链路 | `passed=true`，18请求步骤、3次合成模型调用，12:21:05—12:21:07；4.166秒；0 | 真实Flask登录/路由及模型HTTP协议；ERP与模型为合成替身、usage为夹具，不代表DeepSeek质量或费用 |
| 实际Vue setup状态 | `2 component state scenarios passed`；最新1.153秒；0 | 编译执行真实组件，验证新建/切换清除前单结论及知识草稿，不是浏览器点击 |
| Vue/TS类型 | 无诊断，12:23:46—12:24:12；26.155秒；0 | 静态约束，不代表业务效果 |
| 本轮ESLint | 无诊断；5.109秒；0 | 静态规范 |
| AntD登记 | `组件注册检查通过：71 个页面组件`；0.185秒；0 | 补Popconfirm真实注册及映射，未删断言 |
| 正式构建 | `built in 31.86s`；最新33.490秒；0 | 补案例切换失败清理及页面样式后复验，产物已生成，保留大chunk警告，不代表部署 |
| README清单 | `48 menu entries; 203 HTTP method/path entries`；0 | 新增14个方法/路径，旧菜单不重排 |

失败保留：Decimal科学计数法修为固定小数；系统pytest Temp权限失败改本任务合成目录；Popconfirm漏登记补真实注册；HTTP发现金额白名单遗漏16位小数，扩大受限数值精度并补回归；构建系统Temp权限失败，仅在本次构建子进程设置任务内TEMP/TMP/TMPDIR后通过。原始失败留`python-initial-failure.log`、`http-initial-failure.log`、`build-initial-failure.log`。复验均有新修改或失败依据，没有跑无关全量测试或生产试验。

执行者：主代理`/root`负责取证/API/前端/集成验收；实现代理`/root/risk_flow_backend`负责两个新增流程/模型模块及本地测试，交回后主代理接管；只读审查`/root/risk_final_review`指出串单表单、失效知识、ERP默认回落3项P2，主代理修复并补覆盖，代理复核关闭。前轮`/root/risk_source_contract`只读核对Java来源。任一时刻最多一活动子代理，未派生，沿用主会话配置，底层token未知。

实际技能：chief-of-staff协调/复核；frontend-design复用企业系统AntD样式。MYE仅沉淀通用提示词。未启动浏览器（Work禁用未解除），未查真实ERP、未调用真实DeepSeek。主代理验收：本地隔离流程通过，可以进入获准服务器环境验收；未知公式及未接入证据仍保留缺口。

## 发布、用户操作与失败处理

本机没有已确认的SSH别名/远程部署通道，未猜账户或目录。部署人到测试247现有 **data_report仓库根目录** 操作，不在知序目录。先执行：

```bash
pwd
git remote get-url origin
git status --short
git rev-parse HEAD
```

预期origin为数据中台仓库、工作区干净；不符停止，不reset覆盖。核对/编辑私密配置后：

```bash
git pull --ff-only origin main
bash scripts/deploy_risk_verification.sh
```

脚本含仓库/分支/脏文件检查、Compose静态校验、已有风控SQLite在线一致性备份、只重建api/web及5160健康检查。本机已通过Git附带Bash的`-n`语法检查，未执行脚本部署，不能报告服务器成功。预期退出0、api/web正常、健康成功，再管理员访问1818的`/risk-verification`。健康成功不是业务验收。

任一步失败停止，保留提交号及脱敏错误；不执行down -v/清库/卷删除，不盲目重试模型。回退前保留数据库和备份，应用回退保留新卷，不能自动用旧库覆盖新记录。真实规则样本、公式及业务结论由用户验收。

## Cleanup

本地场景已关闭本轮回环服务及线程；合成SQLite/测试/日志仅在忽略目录保留。无生产清理。服务器备份保留受控卷内，不下载到聊天或复制MYE。本轮未改公共DataSource及Java项目。提交、两端推送、通知与部署的实际回执在本文件后续追加。

## 发布与脚本增强记录（2026-11-04）

风控功能提交`8746657`已推送数据中台GitLab、GitHub；MYE通用提示词`1b6e197`已推送其GitHub，均有真实退出0回执。247尚未部署，本机没有已确认远程登录入口。

本次仅增强部署脚本及本说明：中文5步骤/失败停止、Docker Compose预检、前后配置检查、api/web健康检查；只报告配置是否存在、不打印配置值。语法检查通过；本地替身命令测试7场景（正常、工作区有改动、仓库不符、拉取失败、Compose配置失败、备份失败、健康失败）均符合预期，前置失败不进入构建。真实输出：`7 isolated deployment scenarios passed; Bash and embedded Python syntax passed; no real Docker/network/production operations`。测试及日志在忽略目录`.test-artifacts/evidence/risk-workflow-20261104/`的`test_deploy_script.py`、`deploy-tests.json`与`deploy-*.log`。不重复业务53项测试/前端构建，业务源码未改；没有执行服务器脚本或生产操作。

## 2026-11-04后续：配置、存储与首条确定性规则

用户报告通用503且尚未配置`.env`。未取得247异常栈，不能认定全部错误均由配置导致。源码另确认镜像漏建专用风控目录，可能使首次卷属主不匹配应用UID1000；已补镜像目录，并在部署脚本中仅修固定`/app/var/risk-verification`及四个已知SQLite文件的属主/权限，拒绝符号链接、不改数据库内容。真实容器修复未执行，本地使用替身验证。

页面初次加载改为独立取得配置/记录/知识状态，记录存储失败不再遮蔽ERP就绪提示；存储初始化错误返回明确的数据卷检查提示。支持业务/OTA订单号参数化解析，匹配多笔拒绝，取证补平台/佣金配置及销售佣金原字段。自动出票真实单票利润仍未定位，不能以出票利润替代。

规则与用户给定案例复算见[业务规则V1](../business/air_ticketing/risk-commission-click-loss-v1.md)。这里只确认公式，不启用不完整来源的实单自动判断。66项组合隔离测试：`66 passed in 12.40s`，进程14.844秒、退出0；配置/存储与订单号回归、规则边界均覆盖。Vue setup状态测试3场景通过；类型检查24.445秒、退出0；ESLint6.270秒、退出0；生产构建结果见本地`build-record.json`。部署替身测试更新为8场景，允许未跟踪文件保留、仍阻止跟踪代码改动，退出0；原7场景记录为历史。没有查询真实订单或发送日志给模型。

服务器现有`.evn`/`env`/探测配置等未跟踪文件不删除、不改名；Git若更新会覆盖未跟踪文件会自行拒绝。不要将这些文件内容粘贴聊天。

配置操作在247现有中台仓库根目录完成，保留现有主库/认证等设置，不用完整模板覆盖：

```bash
test -f .env || (umask 077; touch .env)
chmod 600 .env
vi .env
```

只补本次实际ERP的`ERP_MYSQL_HOST`、`ERP_MYSQL_PORT`、`ERP_MYSQL_DATABASE`、`ERP_MYSQL_USER`、`ERP_MYSQL_PASSWORD`，由部署人填写真实只读连接，库名不能照猜；先保持`RISK_AI_ENABLED=false`。现有`.env.example`已有字段说明及模型配置模板，但不含可用密钥。保存后按上方最简命令更新及重建，查看页面配置就绪状态，再验收取证。此步骤不自动跑生产订单或模型；未配置不能声称实单闭环通过。

后续输入歧义已修：纯数字内部ID与OTA号必须可明确区分，页面提供标识类型；候选列表强制按内部ID读取。最新组合回归`68 passed in 8.97s`、进程10.209秒、退出0；类型检查41.294秒、构建`built in 52.53s`/进程54.683秒、ESLint4.203秒均退出0。此前66/67项为增补过程中的历史结果。

### V2口径与TTY部署修复

用户最新确认调整后利润≥负止损值才符合（含等号），替代V1的≤比较。规则标识升级为`qunar-commission-loss-v2`；-44.41与-50均符合，-51不符合。最新定向结果`69 passed in 10.11s`，进程11.591秒、退出0；日志在`.test-artifacts/evidence/risk-commission-20261104/pytest.log`，精确命令/时间在`pytest-record.json`。无配置修改/真实数据查询，不重跑未变前端构建。

用户在247执行时，第3步出现`the input device is not a TTY`；修正权限初始化的`docker compose run`为`run -T`以支持heredoc，补部署替身断言。孤立`hr-mail-worker`仅警告，不加`--remove-orphans`。此次脚本失败发生在重建前，旧API容器找不到新诊断模块属预期版本不一致；须完整部署成功后再运行诊断，不在旧镜像重复尝试。真实247复验待用户执行。

后续用户提供247输出（非Agent服务器实测）：提交`2ccfa20`第3步权限初始化成功、无已有风控库无需备份；第4步api/web构建完成，API Healthy、Web已启动但当时health仍starting；第5步因旧curl不支持`--retry-connrefused`退出。不能据此说构建失败，也不能说整个健康验收已通过。修复为Bash限次循环调用基础curl参数，并新增`--verify-only`。本地10个替身部署场景通过，含首次连接失败后恢复、6次失败停止、验收模式不更新代码/构建/改卷权限；Bash及内嵌Python语法通过，未运行真实Docker/网络。此次仅脚本与说明变化，不重跑未变业务69项及前端构建。247仍需执行只验收模式取得最终结果。

新增单订单只读取证摘要入口，在ERP配置核对正确且获准读取该单后，部署人可在项目目录执行（将示例替换为获准订单号）：

```bash
docker compose exec -T api python -m data_report_api.services.risk_case_diagnostic --order-no '替换为获准核查的订单号'
```

它只查这一单，输出原因原值、平台代码、出票佣金/汇率/利润候选及止损日志结构化片段，不输出姓名、票号或日志原文，不调用模型、不写库。预期给出摘要；配置缺失或多匹配则退出非0并提示。`issue_profit`不等于已确认的自动出票单票利润，摘要不是业务结论。该入口在合成源中测试，尚未对247真实数据执行；真实结果后续由授权人核对。

## 出票日期总览与多类型下钻交付（2026-11-04）

用户确认出票日期及问题口径后，本轮增加 overview/orders 服务端接口，订单去重、全范围原因汇总、分页下钻；页面沿用综合分析结构，保留单订单流程于抽屉。人工确认后刷新同一日期/类型/状态范围。本人最新人工结论计数，不把AI建议或亏损本身认作问题；未知类型不套用现有规则。仅检测原因及订单更新时间变更，不能保证发现子表/日志的每次更新。

实际派活顺序：`/root/risk_overview_backend` 实现总览服务、Flow最小状态读取及15项本地测试，完成后停止写入；`/root` 复核SQL与状态语义，完成API、页面、集成测试和文档；随后 `/root/risk_final_review` 只读复核，发现嵌入抽屉可跨订单的P2，主代理增加读取/创建/选案例三处订单绑定及两项状态验证。复核代理再次确认P2关闭，无剩余阻断。代理未查库、调用外部模型或派生代理，同时最多一个子代理执行。

证据根：`.test-artifacts/evidence/risk-overview-20261104/`（忽略目录，本地留存）。完整命令：在仓库根使用 `C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe .test-artifacts/evidence/risk-overview-20261104/checks.py <mode>`，mode分别为 python、ui-state、case-state、http、type、lint、build、components。脚本与各 `<mode>-record.json` 保存底层完整命令、工作目录、时间、耗时和退出码；原始输出在 `<mode>.log`。前端最终绑定修复后重跑受影响的类型、ESLint与构建；后端未再改动，不重复87项回归。

真实输出与判断：

- python：`87 passed in 17.38s`，进程18.678秒、退出0。覆盖出票日期边界、同单多票去重、多类型、超过200案例、分页/状态/本人隔离、权限拒绝及人工确认反馈。合成10单佣金案例覆盖2问题/3符合/1证据不足/1审核中/3未核查，确认更改后2问题变1问题，列表与汇总一致；这是合成验收数据，不是247统计。
- ui-state：7个总览组件状态场景通过，包括失效响应、失败清空、筛选继承、草稿关闭保护与保存后刷新。
- case-state：`5 component state scenarios passed: case reset, readiness failure handling, embedded order read/create binding; no browser or network`。
- http：`passed: true`，2.416秒，本地真实Flask HTTP/认证/CSRF及模拟模型协议，共3次本地替身调用；新增总览/下钻及重复票验证通过。`realERP: false, realDeepSeek: false, productionOperations: false`。
- lint：退出0、5.050秒；build：`built in 28.76s`，进程30.278秒、退出0，保留既有大于500kB分块警告。
- components：72页检查通过；README入口刷新：`48 menu entries; 205 HTTP method/path entries`；`git diff --check`退出0。

类型检查最后结果见type-record.json。浏览器受工作设置禁用，未冒充真实点击验收。未连接真实ERP、未外发公司资料、未启用真实AI、未在247重建/重启。本轮不改月度接口等其他已有脏文件，不修改MYE，不新建权限或团队共享口径。

部署人仍在247现有项目目录执行 `git pull --ff-only origin main && bash scripts/deploy_risk_verification.sh`，此次业务代码改变需要完整构建，不能只用verify-only。预期脚本退出0后，管理员进入1818的 `/risk-verification`，选获准的出票日期，验证类型总数/状态下钻一致、同单多票只算一单、人工确认后刷新。失败保存脱敏输出并停止，不清卷或重复请求模型。健康、实际取证、真实AI及业务结论须分别验收，当前业务验收未完成。

最终类型检查：2026-11-04 14:59:12+08:00启动，25.256秒、退出0；最终复核全部通过。本段仅记录本地工程验收，不能替代247业务验收。

## RISK-CATALOG-20261104：直查超时整改交付

对象基线为e28822e。用户提供247日志：单日overview于15:11:03收到Nginx upstream timeout/504；15:11:12后端MySQL2013 timed out；最终请求132479.4ms、认证102.9ms、状态503。确认原版性能验收失败，未取得具体SQL计划，不宣称唯一是缺索引。用户随后明确批准建表SQL放sibebid、ETL放独立清洗仓库。

实现：新RiskVerificationCatalog仅连接中台MYSQL_DATABASE=sibebid，覆盖、分类及分页只读查询，不回退ERP；原ERP详情取证保留。独立ETL按日期分批读取、临时表去重、逐日事务切换和覆盖记录、命名锁、源日期索引/EXPLAIN及目标结构/类型门禁，失败保留旧数据。三张表只提供DDL，不自动建表；当前核查状态仍SQLite个人隔离，不双写迁移。首版按日重跑，不冒充修改时间水位增量、CDC或页级续跑。完整契约及操作顺序见docs/product/risk-verification-catalog-v1.md及ETL仓库docs/business/air_ticketing/risk-verification-etl.md。

实际执行者：/root负责应用API/目录读取、UI、集成及验收；/root/risk_catalog_etl独立实现上述ETL、DDL及ETL说明和本地测试，完成后停止写入；随后/root/risk_final_review只读审查，发现跨日不同源版本被日期排序覆盖的P2。主代理增加同事务版本冲突拒绝及4项回归，复核确认P2关闭。任一时刻仅一个活动子代理，未派生、查库或联网。技能为chief-of-staff与frontend-design。其他已有脏文件保留，公共DataSource/配置和MYE未改。

本地证据目录：.test-artifacts/evidence/risk-catalog-20261104/。精确命令及工作目录、时间、耗时、退出码保存在各*-record.json，原始输出为同名.log；checks.py保存复现入口。使用bundled Python，复用项目依赖，不启动已知损坏venv/Ruff入口。

完整复现命令：仓库根运行 C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe .test-artifacts/evidence/risk-catalog-20261104/checks.py <mode>，mode为python、catalog、http、ui-state、type、lint、build；ETL独立测试完整pytest命令在etl-tests-record.json；容量脚本同目录benchmark.py。均为本地合成数据，不连接真实ERP、MySQL或DeepSeek。

真实输出：

- 初轮目录12项加69项既有流程组合：81 passed in 5.72s，进程6.412秒、退出0。随后目录冲突修复仅重跑直接受影响16项：16 passed in 2.28s，15:34:10+08:00启动、进程3.185秒、退出0；69项未变流程复用该初轮证据，不重复运行。首次夹具将列表SELECT误计为状态批读导致1 failed/11 passed，已细化查询匹配；首次失败见本会话真实工具输出，catalog.log为最终通过结果。
- ETL：25 passed in 0.12s，15:29:44+08:00、进程0.609秒、退出0；模拟源/目标连接覆盖重复票分页、事务失败旧日、空日、锁、日期/索引/类型门禁。离线preview退出0，AST语法通过。没有运行真实MySQL语法或事务。
- 最终真实本地HTTP：passed=true，15:34:12至15:34:15+08:00，2.658秒；Flask认证/CSRF、目录统计/列表、取证、人工确认及知识流程通过，3次本地替身模型协议调用。realERP=false、realDeepSeek=false、productionOperations=false。
- Vue setup：7项原总览状态场景及新增同步批次不一致拒绝，共8场景通过；最终15:32:45+08:00启动、1.287秒、退出0。非浏览器点击。
- 最终类型检查18.210秒、ESLint3.429秒均退出0；构建built in 21.02s，进程22.418秒、退出0，保留既有大分块警告。页面补运行中/失败同步提示后进行类型、lint及状态补验；后端随后变化不重复前端构建。未新增Ant组件，复用72页组件登记证据。
- 最终本地容量：101000日行、100000去重订单、1000案例匹配，汇总215.348ms、首屏283.738ms，passed=true。冲突门禁变化使原120.096/148.837ms基准失效，因此补验；benchmark.json为新结果。只证明合成SQLite容量/SQL逻辑，不证明247 MySQL延迟。
- README检查：48 menu entries;205 HTTP method/path entries，退出0；差异空白检查通过。

验收结论：本地工程通过，未执行生产DDL/同步/调度/部署，真实ERP索引、MySQL兼容、网络与247单日3秒目标未验。浏览器禁用状态未变化，不绕过。服务器需先在确认的sibebid执行完整DDL，再在清洗仓库preview/check-schema/显式日期同步，成功后部署API/web并验收；缺日期不能显示成零。不要只更新应用后继续刷新原ERP请求，也不要把健康UP当取证或业务验收。

### 本轮真实Git交付回执

应用实现提交3105bc8已普通推送origin(GitLab)和github，两端均退出0。ETL原本地提交50329d4首次推送因远程有新提交而non-fast-forward失败；未强推、未在有KPI改动的原工作区pull/rebase。获取远程后在D:/data_center_code/.worktrees/risk-catalog-etl-20261104建立隔离分支，基于ff553c3只cherry-pick两个新增文件为e3a17fb。与原已测试两文件diff为空、隔离工作区干净，因此复用同内容25项测试；普通快进推送ETL origin main成功，退出0，远程ff553c3..e3a17fb。原清洗工作区main及已有KPI/缓存改动保留，后续不得在原脏工作区盲目拉取或清理。

本次未修改生产库、未登录247/216、未执行DDL/ETL/调度/部署，也未发送发布群消息。当前阶段是代码与SQL已交付，服务器数据准备和业务/速度验收待执行；不是“全链路已上线”。

### 216运行兼容与后续ETL规范补充（2026-11-04）

用户在216默认python运行时出现future feature annotations is not defined，发生于解析阶段，未连接数据库。主代理对照综合分析清洗源码和说明；其源码也含future annotations，因此不能用源码存在替代确认实际任务解释器。修复风控脚本不需要的延迟注解和date.fromisoformat依赖，兼容旧URL构造入口并沿用综合分析UTF-8可用性保护。未修改公共配置、DDL、API或业务规则。

用户明确要求写入AGENT：独立清洗仓库新增AGENTS.md，中台AGENTS增加入口；后续ETL先参考综合分析结构/参数/配置/日期/日志/失败处理并核实实际环境，不照搬Hive全年覆盖及业务规则，不擅自升级系统Python。此处无独立子代理，由/root执行。

兼容定向验证36 passed in 0.67s，15:52:11+08:00启动、进程2.149秒、退出0；原25项及11项语法/日期/新旧URL协议模拟。最初兼容夹具因本地没有SQLAlchemy而2失败/34通过，已明确改为隔离协议测试并保留失败日志，未安装依赖或用模拟声称真实SQLAlchemy通过。精确命令/输出见.test-artifacts/evidence/risk-catalog-20261104/etl-compat-record.json、etl-compat.log和etl-compat-initial-failure.log。AST的3.6语法模式只证明静态解析，未运行真实旧Python。离线preview退出0；216实际版本、依赖和check-schema仍未验，不要求直接正式同步。不重复未变前端/后端业务检查。

### 公共连接入口全链路重新审查（2026-11-04）

用户要求按公共库及既有清洗规矩重新审查。主代理核对综合分析、GDS、ADM清洗与公共ConnectConfig/MySQLConnect，发现风控手工URL入口与公共get_connect不一致，且ERP配置密码表达式已有quote_plus，存在编码语义不一致风险；没有数据库认证失败回执，不能冒充实库错误已复现。已改回get_connect/raw_connection，复制params限定超时且保留原配置，抑制公共helper原始异常输出，不修改公共库。补资源逐个清理及安全失败码，避免关闭失败跳过其他资源或最终误报success。独立审查/root/risk_final_review因额度限制未完成，本轮由/root接手，不算独立复核通过。

当前本地回归46 passed in 0.52s，16:07:31+08:00启动，进程1.787秒、退出0；精确命令/目录/源码SHA256在.test-artifacts/evidence/risk-catalog-20261104/public-connector-record.json，日志public-connector.log，复现run_public_review.py。原36项中的旧URL工厂测试随实现变化由公共连接测试替代；运行公共库实际类函数体但engine/配置合成，不代表真实SQLAlchemy驱动、旧Python或216实库连接通过。preview退出0。用户216现场preview也已成功，结构/索引/正式同步未取得回执。DDL/页面未变，复用先前相关证据，不重复前端构建或业务测试。未查库/执行DDL/生产ETL/部署/模型调用；后续先check-schema，再获准日期同步。

### 盈亏原因字典映射交付（2026-11-04）

用户指定system_com_type_det、parent_code=PRODUCT_PROFIT_REASON_TYPE，源码/DDL定位det_code→det_cname，type_code=_SYSTEM_PRODUCT_TYPE。主代理实现新字典表DDL、ETL原子同步和dictionary-only、应用本地映射，移除RLA013中文名硬编码，规则ID仍按代码独立识别。无子代理；主代理复核。公共库/生产配置未改，原订单计数/权限保留。

用户216真实回执：monitoring解释器下check-schema通过，2026-11-01目录published3177条、runId af5b011360ad457fbebef0b472bc292a、success。本轮字典尚未实库执行。新增DDL仅建bi_risk_reason_dict，不重建原表；dictionary-only不读/改订单，更新脚本后的既有五分钟命令自动包含字典同步。

本地最终69 passed in3.71s，16:46:13+08:00启动、进程4.840秒、退出0，覆盖公共库/旧语法/事务/目录，以及字典parent/type隔离、名称变化、未知码不丢单、无效/重复/空字典拒绝、失败回滚及dict-only保留订单。精确命令/时间/SHA在.test-artifacts/evidence/risk-catalog-20261104/dictionary-record.json，日志dictionary.log，入口run_dictionary.py；合成配置/engine，非实库。16:44初轮69通过3.12秒被字典类型门禁补验替代。

真实本地HTTP通过，3.502秒，认证/核查/目录链路无回归，3次本地替身模型调用，无真实模型/ERP。9个Vue setup场景通过，含字典切换期间批次拒绝；类型38.811秒、ESLint5.312秒、构建built in42.28s/进程44.091秒均退出0，保留既有大分块警告。精确记录同目录http/type/lint/build/ui-state-record.json与日志。未增加组件，复用此前登记证据；浏览器禁用未绕过。真实DDL/字典数据/部署/页面验收待执行，不以本地检查冒充。

### 字典筛选按用户指定parent_code修正（2026-11-04）

216真实回执SOURCE_DICTIONARY_EMPTY_OR_TOO_LARGE，旧错误码不能区分0条与超过5000，暂无真实字典行数。主代理复核发现额外type_code=_SYSTEM_PRODUCT_TYPE只依据DDL注释，不能代替用户确认。ETL源读取、目标替换及应用读取均改为仅parent_code=PRODUCT_PROFIT_REASON_TYPE，type_code保留源值作元信息，不过滤；仍检测同父级重复码。新错误分为SOURCE_DICTIONARY_EMPTY和SOURCE_DICTIONARY_LIMIT_EXCEEDED。无DDL/前端/公共库改动，不重跑3177单订单。

真实本地73 passed in3.35s，17:21:49+08:00、进程4.583秒、退出0；精确命令/源码SHA见.test-artifacts/evidence/risk-catalog-20261104/dictionary-parent-only-record.json，输出dictionary-parent-only.log，入口run_dictionary_parent.py。覆盖实际type不同/空值仍映射、父级隔离与0/超限分码。HTTP回环passed=true、3.032秒/进程5.129秒、退出0，未查真实ERP或调用真实模型。前端/DDL未变复用前轮验证。ETL与247后端都须更新；新的dictionary-only成功回执及名称显示待验，不能把修正额外条件报告为实库根因已证实。
