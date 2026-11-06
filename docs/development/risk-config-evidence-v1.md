# 出票盈亏配置搜索与原核对证据留存 V1

任务：RISK-CONFIG-EVIDENCE-20261106；输入基线a94bd48；用户要求实现并验收，独立验收者在阅读实现前写预期。公司材料仅留中台，MYE只接收先审查后的通用回执。实现者：主会话；独立验收：/root/config_evidence_acceptance。

## 数据来源、接口与行为

- 当前候选配置：ERP只读base_issue_match_rule，字典system_com_type_det的SYS_RULE_GROUP_TYPE_ISSUE/出票盈亏配置，业务RB01、启用且当前有效；类型RB01003002为亏损阈值，RB01003001仅盈利配置展示。平台/航司编码按现有逗号/分号/斜杠/竖线分界匹配，包含空范围通用规则，不当成逐票实际命中。
- GET /v1/risk-verification/rule-configs：ruleId精确正整数标识（字符串保留长ID），platform/airline编码可组合AND；group固定出票盈亏配置；page从1开始，pageSize最大100。保留最多1000候选的完整性门槛，超限拒绝而非截断后分页。按原优先级对完整集排序后分页，返回total/page/pageSize；规则ID绝不搜索rule_name。
- 页面先应用筛选再请求；变更搜索或清空全部条件回第1页；翻页使用已生效条件，不混入未提交输入；请求进行时禁改页/再次提交，失败清空旧结果并明确错误。每页数量改变回第1页。
- 原核对：sibebid已成功发布日事实，复用订单ID/出票日、稳定结果ID、规则ID、版本/快照/哈希、asOf/historyReferences/basis/historyProof、逐票航段和stopLoss/status，不请求ERP重算。
- GET /configuration-evidence/<orderId>?issueDate=...：只读已保存原证据及观察，缺两表报未就绪，未保存返回null；不把读取失败当未保存。
- POST同路径：明确保存当前核对，提交issueDate/resultId，事务锁定日事实并校验；首份原结果完整保存（最大4MiB，超限拒绝而非截断）。同订单/出票日再次保存返回旧证据，不覆盖；不能补回首次保存之前已丢失的旧核对。
- POST同路径/observe：显式观察原关联规则的当前值，不重新挑选别的规则。复用已有单票1至4段/超4段公式，只生成提醒；requestId幂等，重复请求先读原回执、不再读ERP；观察源时间早于已入库最新观察则拒绝，失败保留上次。
- 下表固定原单票止损、原结论与采用依据；另列最新单票止损（仅提醒），并记录原/上次/本次值、源版本、源更新时间、观察时刻、当前配置登记有效期和生效时间未证实说明。当前清洗事实另用于人工重新核实，不用固定原证据冒充当前事实。
- 当前值不等于出票时有效；历史证明缺失逐票明确标未证实。未观察/无法取得/0/未变分别显示。规则停用或过期不当成有效适用；不存在、规则类型变化、非法或截断不补0。中间未观察版本不补造。

金额按既有元/CNY、Decimal精度；本次未修改ETL、规则公式、ERP、旧止损或旧结论。配置整体变更和金额变化分别记录，同值不同版本可提醒配置变化；完整比较依据未知时不能标为已确认无变化。

## 表结构与执行

新增两张专用表，复用原配置关联与历史取证能力，不另造匹配引擎。见[两表中文用途与逐字段字典](risk-config-evidence-schema-v1.md)、[DDL](../sql/risk-config-evidence-v1.sql)。需部署人显式执行，普通发布仅只读检查主键、唯一性、InnoDB等后切服务；原五张跟进表、ETL历史/队列继续保留，无DROP或ALTER旧表。

## 验收预期与证据

需求先验在`.test-artifacts/risk-config-evidence-20261106/independent-expectations.md`，先于实现阅读。主会话每项结果见run-receipt.json（完整命令/cwd/版本SHA/退出码/逐项结果）及pytest.final.log；前后对照before-after.synthetic.json包含固定同批3票A→B→C，原阈值和原结论、原快照哈希保持不变，最新提醒按分段更新。

真实只读证据：real-readonly.receipt.json及raw.local.json。3单、1个原规则，精确ID搜索1条，原值/原结论不变，最新值计算取得；两次源快照未变化，不称生产配置修改A→B→C已验。期间未改ERP配置、未写目标两表。首轮只读脚本出现游标列描述复用KeyError，固定原始行列映射后同范围重跑通过；失败和返工在attempts索引保留，不将夹具错误当产品缺陷。

独立复核发现并关闭两项：缺历史证明却用确定历史措辞、查询在途分页使页码与内容不符。复核命令/输入SHA/原始输出/退出码/返工见independent-index.json、independent-review.md及Python/UI回执。Vue setup状态/SSR不冒充真实浏览器。

| 层级 | 状态 |
|---|---|
| 实现 | 接口/搜索/原证据不可覆盖/追加最新提醒/前端已接通 |
| 主会话定向测试 | 21项通过，内存SQLite适配真实生产SQL与Flask相关权限逻辑 |
| 独立审查 | 10项Python、3组Vue状态/SSR通过，两项返工已复核 |
| 真实只读 | 3单/1规则，源未变，无数据库写入 |
| TS/Lint/组件/部署脚本语法 | 按frontend-manifest.json记录，最终回执另核对 |
| 提交推送 | 应用核心0583bd8已正常快进至GitLab/GitHub main并核验；MYE通用回执f152242已推至其GitHub main，非服务器部署 |
| 两表DDL及真实MySQL事务/并发 | 未执行/未验；由部署人执行 |
| 生产构建 | 复用已知Windows esbuild临时文件权限限制，不重复无效重试；未取得本版本生产构建成功证据 |
| 部署/真实页面/业务验收 | 未执行/未验；浏览器仍为宿主禁用，不绕过 |

本机命令统一使用既有捆绑Python/Node；Python仅在进程内追加主仓库venv包。测试/原始公司数据留本项目Git忽略目录，不提交。

SQL同步归档到工作区SQL指标资产库：RISK-DDL-016、RISK-CHECK-017，均不作为已正式落地指标。

重复观察未变时仍保留“与原值不同”提醒；本次变更与相对原值差异独立，不能因最新观察未变而消除原值差异提示。

分页查询各自读取当前源快照，跨请求源配置可能变化；当前页为空但total仍大于0时单列当前页空态，重新查询回到第一页，不将其解释为整个范围无配置。

SQL同步归档到工作区SQL指标资产库：RISK-DDL-016、RISK-CHECK-017，均不作为已正式落地指标。
