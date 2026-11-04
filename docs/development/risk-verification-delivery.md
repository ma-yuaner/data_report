# 风控核对首版交付与验收

## 最简部署方式

无需另传脚本。部署人在247现有`data_report`仓库根目录执行下面这一条命令：

```bash
if [ -n "$(git status --porcelain)" ]; then echo '存在本地改动，请先保留并核对，未执行更新或部署。'; else git pull --ff-only origin main && bash scripts/deploy_risk_verification.sh; fi
```

预期显示5个步骤并最后输出“部署和健康检查完成”，再以管理员访问现有1818端口的`/risk-verification`。仓库/分支不符、拉取、配置、备份、构建或健康检查失败时会停止；保留错误信息，不清库删卷、不反复运行模型。若提示ERP或AI配置未齐，按下方配置段在服务器私密`.env`补齐后重新执行，不把密钥发送聊天。脚本不会自动填写凭据，也不会查询订单或调用模型。

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
