# ADM解析正式接入与本地测试

2026-11-17。用户明确要求不再只做演示原型，保留“ADM任务台账”和“业务分析与跟进”，仅增加ADM解析，并接通上传、解析、结果保存与展示。开发基线为GitLab `origin/main` 的457240a；旧fat_cy检出落后于该菜单及admwf正式实现，故使用独立工作树 `D:/data_center_code/.worktrees/adm-parsing-live-20261116`，未覆盖旧检出和无关工作。

## 已实现范围

- 正式菜单新增 `/adm/parsing`，复用原AppLayout、PageHeader、FormDialog和Ant Design Vue。既有两菜单、原路径、台账、分析、任务分配及交易流程源码不改。
- 独立接口 `/api/v1/adm/parsing`，上传保存原件和元数据，后台线程持久队列、正文读取、模型调用、服务端校验、结果/失败原因保存、分页查询、版本历史及原件下载。不是localStorage或静态样例。
- 生产使用现有ADM专用MySQL连接和独立 `adm_parse_task` 表，不读写业务办理表。SQLite仅允许显式TESTING加路径的隔离本地验收，没有生产失败后回落SQLite。
- 支持PDF文字、XLSX、TXT、CSV、DOCX。单份20MB、单件10份/50MB，正文60000字、PDF200页、Excel20万cells上限，超限失败、不静默截断。XLS须另存XLSX；扫描PDF须先OCR，当前不假称已内置OCR。
- 上传幂等键+文件名/哈希校验、原件内容完整性、版本CAS、并发只认领一次、进程中断超10分钟标失败、单件最多10次显式解析、不自动重试付费调用。后台线程随web进程运行；QUEUED任务在状态/详情查询触发恢复；RUNNING中断不会自动重调模型。
- 结果保存前写服务器恢复文件；数据库写失败显示保存失败，可重试保存而不重调模型。文件目录和数据库都故障时仍需管理员排查，不保证灾难场景零丢失。MySQL与持久文件卷需共同备份，多主机副本需共享文件卷，不把当前单宿主机设计当成分布式对象存储。
- 新增解析任务仅上传人或有adm.manage者可见，操作需adm.view及adm.create/adm.manage。沿用当前登录、菜单adm.center和CSRF。模型密钥不返回客户端、不写日志。

## 样本材料与JSON口径

用户提供 `ADM样本解析.docx`，只读提取为需求依据，不执行文档中的操作要求。其提出单号、来源判断供应商、日期、金额、币种、截止日、航司；部分原因需从附件恢复/核对PNR及提取票号、系统、PCC。本轮提取这些字段并记录来源，不连接GDS恢复PNR、不自动分配负责人、不改既有台账。

契约版本为 `adm-extraction/1.0`，不与前轮0.1离线原型结构混用。服务器规则位于 `backend/data_report_api/services/adm_parsing/contract.py`：

```json
{
  "schemaVersion": "adm-extraction/1.0",
  "adm": {
    "number": null, "issuer": null, "supplierName": null, "airline": null,
    "issuedDate": null, "amount": null, "currency": null, "reason": null, "dueDate": null
  },
  "lines": [],
  "evidence": [],
  "conflicts": []
}
```

明细每项固定键：lineId、transactionNumber、pnrs数组、ticketNumber、ticketType(real/virtual/unknown)、flight、flightDate、origin、destination、gds、pcc、amount、currency。

evidence每项固定path(JSON Pointer)、segmentId(服务端实际文档段落ID)、quote(原文摘录)。conflicts每项固定path、description、segmentIds(至少两个不同原文段落)。模型不能生成来源文件路径或决定任务状态。服务端段落包括文件ID、PDF页码/Excel行单元格/DOCX段落/TXT行号及实际文本。

编号、发单方、正式金额和币种必填，且字段值须在对应原文找到。金额为非负十进制字符串（15位整数/4位小数），0与null区分，币种按支持列表；日期须真实YYYY-MM-DD。缺必填、无效类型、额外/缺键、非法日期、来源捏造、PNR/票号/GDS/PCC有值但无原文证据均失败。缺可选字段、无明细、虚拟票号、来源冲突、跨币种和同币种合计差异保留警告、待人工核对。精确合计用Decimal，不换汇。JSON校验通过不证明行完整性和业务正确，不自动入正式ADM台账。

## 后续API配置与部署前置

生产先由有权限的执行人向实际ADM连接库应用 [独立DDL](../sql/adm-parsing-v1.sql)。本次未连接生产MySQL、未执行生产DDL。

服务器私密环境变量（不要把密钥发到聊天或Git）：

```text
ADM_PARSING_AI_ENABLED=true
ADM_PARSING_AI_URL=<完整HTTPS chat-completions接口>
ADM_PARSING_AI_KEY=<私密配置>
ADM_PARSING_AI_MODEL=<供应商模型标识>
```

支持chat-completions的messages、response_format=json_object、非流式choices/message/content及finish_reason=stop。其他API协议需要适配，不宣称任意供应商通用。HTTPS地址来自服务器配置，不接受浏览器传入地址或凭据，不跟随重定向；仅TESTING允许loopback HTTP夹具。超时、限流、认证失败、非JSON和输出截断分别失败，不自动重试。真实usage存在才显示token，未提供则未知，不估算费用。

Docker Compose已将解析环境变量传给api，文件位于已有adm_data卷中的`/app/var/adm/parsing`，无新增解析worker服务要求。配置和DDL完成后重建api/web；这只是交接，不代表服务器部署已执行。生产未配置API时仍可上传持久文件，点击解析后读取原文并保存 `PARSE_AI_NOT_CONFIGURED`；配置后可重解析。

## 本地真实产品入口

先在frontend构建正常生产包，再运行：

```text
<可用Python> scripts/run_adm_parsing_local.py --site-packages D:/data_center_code/data_report/.venv/Lib/site-packages
```

runner固定loopback 1818/5160，地址 `http://127.0.0.1:1818/adm/parsing`。使用独立 `.test-artifacts/adm-parsing-local` 的SQLite和文件，关闭生产数据库、使用开发身份，不读取生产.env。默认禁用真实AI；只有显式 `--allow-configured-api` 才可使用当前环境中的配置。严禁把此runner当生产启动方式；端口占用即失败，不停止或替换其他服务。

## 验证记录

本机隔离测试位于 `.test-artifacts/adm-parsing-live`，不进Git。23项后端检查通过，包括真实样本DOCX读取、XLSX/TXT、完整Flask接口回读/下载、原登录及CSRF、越权、请求幂等、并发版本、进程中断、正文超限、原件哈希、模型错误/截断/来源捏造、历史版本、模拟数据库保存失败恢复，以及写库瞬间的正常检查点不误报保存失败。模型成功路径使用loopback HTTP协议夹具，不是供应商AI质量验收；真实API无调用，生产数据库无连接。

前端 `vue-tsc -b --force --pretty false`、新增页面ESLint、86个组件AntD登记检查通过；6项实际Vue状态及模板检查通过，覆盖列表/详情旧请求不覆盖新选择、异步操作不跳回旧来件、非法候选不崩溃及保存失败时停止模型轮询。

Windows标准构建遇esbuild临时文件删除拒绝，独立TEMP及沙箱外同样受限；用于本地预览的可读构建通过。另使用本机WSL Ubuntu、已有Node22.16.0压缩包和npm离线缓存完成标准压缩构建，33.42秒，强制类型检查与161份当前输入/源码SHA256逐项一致；未联网、未部署。标准构建产物已恢复到该工作树frontend/dist并用于本地运行。

实际loopback HTTP已验证1818页面/5160接口，上传用户DOCX、后台读取、保存配置缺失失败原因、重复GET回读及原件下载一致。原件真实读取1段；结果为FAILED / PARSE_AI_NOT_CONFIGURED、candidate=null，不伪造成功。重启本地runner后任务和原文仍存在；本地其他业务API被明确隔离，不触发生产连接。

SQL资产已归档 `D:/data_center_code/SQL指标资产库/ADM/应用读写/ADM-PARSE-001.md`（store源码及DDL），维护总索引；SQLite已验证、MySQL DDL未执行、实库未验、非经营指标。浏览器沿用Work禁用限制，未进行浏览器真实点击、缩放、输入法或截图，不用静态/接口测试替代该结论。
