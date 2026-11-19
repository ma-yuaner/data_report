# ADM解析案例字段与规则升级

2026-11-19。用户明确授权依据PDF、TXT、XLSX及两张截图完善正式解析。主会话实施和验证，无子代理。沿用较新主线工作树content-theme-20261118，未改旧data_report检出。

## 字段契约

契约adm-extraction/1.1，提示词adm-parse-1.1。原件、段落、候选及历史仍存现有独立解析任务payload；不改SQL、DDL或正式业务表。旧1.0候选原样回读，页面标记编码来源未区分，重解析生成新版，旧结果留历史。不将旧字段静默转换成有明确来源的编码。

| 字段 | 含义与规则 |
| --- | --- |
| adm.number/issuer/supplierName/airline | 单号/发单方/有原文依据的供应商候选/航司；供应商候选不冒充中台字典匹配 |
| adm.amount/currency | 正式ADM总额/明确币种；必填并有来源，非负十进制字符串，0不等于缺失，不换汇 |
| adm.issuedDate/reportingDate/dueDate | ADM开具日/报表日/明确截止日，分开；日期值及对应标签必须有引用，未知null |
| lines.airlinePnrs | 明确的航司记录号；本次附件RLOC列 |
| lines.gdsPnrs | 明确的GDS编码；GDS_RLOC、带系统标识的Booking Ref |
| lines.pnrs | 来源未明PNR/PNRRef；不猜归属，不用于自动恢复 |
| lines.ticketNumber/ticketType | 13位票号及real/virtual/unknown；材料声明虚拟时不能标真实，不把UNTICKETED补成票号 |
| lines.transactionDate/action/flightDate | 操作日期、原文动作、航班日分开；保留重复PNR的多次Booking/Cancel及多航段，不按编码合并明细 |
| lines.gds/pcc | 保留原文系统和Office/PseudoCC；不把原文1A替换成没有引用的AMADEUS |
| lines.amount/currency/amountPurpose | 明细金额、币种、用途admCharge/unitPenalty/ticketTotal/other/unknown；仅完整同币种admCharge参与正式总额校验 |
| lines.amountText | 原始金额文字，保留$、负号、计价单位；无明确币种不猜USD，结构金额及币种留null |
| lines.commissionRate/commissionAmount/commissionCurrency | 佣金百分数0至100（3%存3）、佣金金额及币种；不替代罚单金额，不擅自对负值取绝对值 |

数组未知[]，标量未知null，拒绝额外/缺键。已分类编码须引用角色标识；编码、票号、GDS、PCC、金额及佣金有值须引用原文。金额用途仍依赖模型识别与人工核对，来源校验不能保证业务分类绝对准确。全量明细完整性及文档跨页字段绑定仍需真实样本验收。

## 原因和部门

classification.py按用户截图转录原因映射，服务端产生待核对建议，未匹配不猜，多匹配保留候选。业务部、票务部、客服部分开；Inactive Segments按图优先业务部。本版不自动分派人员，不自动恢复PNR、建单或发起申诉。截图第2张的佣金字段可提取，但当前上传不支持图片，需正文文件；OCR另行实施。

## 防误用与验收

多个明确ADMA Document Number拒绝合并；附件未标识单号时仍依赖模型及人工判断，不以文件名作为唯一业务真相。虚拟票号声明对整件保守阻断真实票号标记，混合真实/虚拟票据需拆分核对。

本次使用三种真实样本验证正文读取，并以PDF人工标准答案验证主单金额、开具日和报表日；不是调用供应商模型得到的提取结果。新增14项规则及真实材料检查、原23项接口/权限/CSRF/幂等/并发/持久化/保存恢复回归通过。原登录夹具已适配验证码，不改认证业务。前端强制类型及改动ESLint通过；Windows标准压缩构建因esbuild临时文件删除拒绝失败；独立目录的非压缩esnext构建退出0（16.78秒），不当标准压缩构建通过。证据本机.test-artifacts/adm-parsing-rules-20261119，不提交测试及真实材料。

## 上传测试与发布

入口/adm/parsing。按一张ADM一件上传，先PDF、再同单PDF加TXT/CSV/XLSX。每件10份/50MB，单份20MB；文字PDF及XLSX/TXT/CSV/DOCX，扫描PDF须先OCR。服务器仍需现有独立表、ADM连接、持久卷及真实AI配置；已有环境无需为本次升级新建表。更新api/web后先核对状态再上传。

本次未连接服务器/MySQL或调用真实供应商模型；浏览器Work禁用，真实点击、视觉与业务验收未执行。不自动部署或发外部消息，无SQL变更。真实API准确率/字段完整性、实际费用及测试服务器是否已升级待核实。


## 交付回执

另6项真实Vue状态/模板检查通过（非浏览器）。本地功能提交bab97a7。公司GitLab独立分支feat/adm-parsing-rules-20261119首次推送因网络不可达失败；申请沙箱外推送被自动审批拒绝，理由为本轮未明确授权向远程GitLab发送私有代码。未绕过、未推送GitHub、未部署或发送消息。需要用户明确批准此公司仓库与分支的推送后再继续；部署另行授权。源码位于本工作树，不在旧data_report检出。

复盘：本次复用原解析服务、持久化、权限及前端组件；原有登录测试夹具因新增验证码失效，已按真实验证码流程适配；零金额夹具补全明确总额标签，并新增每段费率不可冒充总额的反例。金额来源与PNR角色校验改善误用防护，但完整性和模型字段绑定仍需真实AI和人工标准答案检验。本次不修改个人技能库。
