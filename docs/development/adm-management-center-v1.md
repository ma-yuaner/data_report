# ADM 管理中心首版交接

2026-10-24。需求以[完整PRD](../product/adm-management-center-prd-v1.md)为准，开发接口以[实现契约](../product/adm-implementation-contract-v1.md)为准。本页区分本轮代码、未对接能力和部署前置。

## 已实现的代码范围

独立接管最新版以[建表、部署和人工验收](adm-independent-acceptance.md)为准：新增正式业务字段和模板、批量分配、历史JSON只读归档与补传原件、全量台账SQL分页及存储错误分型。已有中台表需升级生成列/索引，未建表用新建DDL，二选一；本页下方首轮交付的旧缺口描述按新指南更新，原生产迁移/容量/接口未验边界仍有效。

- 2026-10-24接管补充：正式目标为sibebid独立新表、中台替代Java；新建底部＋多订单分别说明/计划，创建复用现有原子接口，引用新建也只接受本次新填订单。完整字段与历史迁移仍按[独立接管清单](../product/adm-independent-takeover-v1.md)推进；旧Java字段不删，source快照不等于全部映射。

- Vue入口：`/adm/workbench`、`/adm/cases`、`/adm/cases/:caseId`及明细深链接；主单建档/引用，多平台出退改明细，独立标签查看、服务端版本冲突和草稿比较。
- 主单/明细描述与六项结构化分析，历史版本、归因、分类和备注；分配、接单、恢复新编码版本、多对象多轮申诉、差异人工声明、审核退回和财务凭证人工确认。
- 结案检查覆盖原件、证据完整性、必需字段/分析、明细审核/财务和原币分摊；已结案只读，授权重开保留快照。不得把差异人工声明当成财务完成。
- 持久附件上传/版本/明细引用；PDF实际解析、图片解码校验，在线PDF/图片、XLSX/CSV只读预览及文本展示，有权下载；关闭弹窗释放blob URL。
- 中台两sheet模板、Java44/Python38空模板及旧格式新单摄入，来源字段快照留存；预览/公式和孤立明细拒绝，按主单原子建档，幂等重试，不覆盖既有单或复制旧完成状态。
- ADM导出使用中台既有全局队列、本人任务抽屉、取消及临时文件清理。服务器冻结对象/版本/可见明细，执行和下载重验权限；原件不受导出清理影响。
- `adm.center`菜单与独立功能权限；本人/团队/全量由服务端裁剪，账号管理可分别配置ADM受管成员；部分可见主单隐藏总金额、私密分析/备注、源快照及未授权附件。

## 尚未交付为真实接入的能力

接口配置返回`orders=false, finance=false, notifications=false`。目前没有伪造订单自动匹配、财务库核验或自动提醒。人工核实和凭证流程可运行，但不等于外部系统已写入、已付款或真实损失已核定。

本轮旧38/44格式导入是“新单建档”，保留原始字段但不按旧状态直接结案；尚未完成旧Python黄色业务回传到ERP最新底稿的全部转换规则、覆盖既有人工备注、历史ERP/SQLite迁移和冲突归组。批量分配/解锁等批处理、ASD系统上传、定时预警/企业微信、完整归档材料打包及独立统计复盘尚待后续。不能报告整个PRD或两套系统全量迁移完成。

实际页面操作、生产MySQL兼容/容量、Docker运行/恢复、外部接入和真实业务验收另验；类型/构建和合成测试不替代这些结论。

## 数据与部署

正式存储为MySQL `adm_case_document`，聚合JSON保存主单、明细、任务、事件和快照；每次写以version CAS事务提交业务和审计。此为首版原子性取舍，尚未对大规模主单/历史做索引和容量优化，不承诺百万级性能。

1. 由DBA在确认的中台业务库执行[DDL](../sql/adm-management-center-v1.sql)，要求MySQL JSON支持，API不会启动自动创建生产表。
2. 默认复用平台MYSQL连接；可在私密环境设置`ADM_MYSQL_HOST/PORT/DATABASE/USER/PASSWORD`。不修改公共ERP连接，不将配置值入Git。
3. Compose已声明独立`adm_data`持久卷，挂载`/app/var/adm`，附件位于`attachments`、导入预览位于`imports`；备份数据库与正式附件作为同一恢复单元。
4. 重建API/web使用新增pypdf/Pillow依赖；保持5160/1818端口。代码和Compose修改不代表本次执行了服务更新。
5. 管理员初次进入可用全部功能；普通账号在账号管理配置ADM菜单及明确功能，团队另配ADM受管成员。不存在默认给所有人全量数据的授权。
6. 对照PRD执行迁移演练和旧写入口保护后才能切换；当前旧系统继续服务，不从中台直接写ERP或财务库。

SQLite仅在`TESTING=True`且显式指定`ADM_STORAGE_MODE=sqlite`、独立`ADM_SQLITE_PATH`时初始化，供本机合成验收，生产不允许静默回退。

## 本机验收入口和范围

验收脚本保留在忽略的`.test-artifacts/adm/`，不随Git交付。使用项目虚拟环境、合成账号/订单和临时SQLite/文件，不读取真实.env，不连接生产。

```powershell
.\.venv\Scripts\python.exe -m pytest .test-artifacts/adm/test_service_contract.py .test-artifacts/adm/test_http_contract.py .test-artifacts/adm/test_attachment_contract.py .test-artifacts/adm/test_exchange_contract.py -q -p no:cacheprovider
npm --prefix frontend run type-check
npm --prefix frontend run check:components
```

首轮服务/HTTP15项通过（7.85秒），附件/导入/导出新增11项通过（1.04秒）。状态机测试使用明确标识的合成证据校验stub；真实附件和HTTP文件丢失/篡改阻断单独验证，不能混称真实供应材料验收。本机pypdf6.10.0/Pillow12.3.0来自官方桌面运行包的离线同Python3.12依赖，满足requirements声明；线上按依赖文件安装，不依赖桌面路径。

后续以最终增量验证和工作流记录为准；修复特定风险后只补相关回归，不机械扩大整库测试。

最终增量：解锁权限/结案复制3项通过（0.69秒）；解锁后不允许继续编辑、提交或上传明细证据，原处理人需重新持锁。修复详情页两处多语句内联事件编译问题，相关ESLint通过。生产构建（含vue-tsc）通过，Vite14.31秒，保留现有大包警告；Compose以.env.example配置解析通过，未启动服务。未执行浏览器验收、生产DDL、迁移或部署。
