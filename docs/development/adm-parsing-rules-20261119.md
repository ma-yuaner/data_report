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

2026-11-19后续授权回执：用户明确批准公司GitLab analytics/data_report仓库及feat/adm-parsing-rules-20261119分支。推送成功，ls-remote核对远端96ed71942708a3e5733e1dcbe0a12756e836f31c与本地一致。此前审批阻碍已解除；未合并main、未部署、未推送GitHub。最终源码非压缩构建复验退出0（10.03秒）。


## 解析进度补丁

用户T43实测已完成模型合成调用与字段校验，手工建表后上传、刷新留存及下载原件通过（用户回执，主会话未操作服务器）。随后反馈只有“解析中”，无法判断阶段。原因是原文/模型结果原先在终态统一保存；现改为READING→MODEL→VALIDATING→FINISHED，各阶段通过原CAS版本持久化，模型调用前已保存正文。API提供本次耗时，页面展示阶段、最近获取状态时间，明确模型等待无法提供百分比。区分任务记录已保存与处理结果已保存，避免把上传保存误当解析结果保存。重解析清空开始时间，旧任务缺阶段明确说明，不猜历史进度。

37项后端既有检查、1项阶段及提前正文可见/重解析重置专项、6项Vue状态及模板检查、完整类型与改动lint通过。非压缩esnext构建通过；标准压缩构建沿用Windows临时文件权限受限记录。浏览器/真实模型及T43补丁部署未验。无SQL/DDL、无真实业务数据入Git。保留远端main 25f59cb；T43清单同步本补丁以及既有main投放登记编辑的启动边界复核，不冒充该功能业务重新验收。


## 真实PDF超时诊断与模型模式补丁

用户T43计时回执：120.2秒，底层TimeoutError，任务FAILED且保存SAVED。确认本次等待超时，不证明服务端具体耗时原因。官方深度思考文档 https://help.aliyun.com/en/model-studio/deep-thinking 明确qwen3.8-flash默认开启思考；当前请求未显式设置。针对精确模型名及官方.aliyuncs.com接口，HTTP请求顶层增加enable_thinking=false；其他模型/代理保持原协议。提示词版本adm-parse-1.2：引用最短必要证据，不反复整页复制；原因PNR集合无逐笔交易时保留一条摘要，不推造交易行；已有逐笔附件仍逐条保留。保留8000输出预算及原文，不靠截断降低耗时。TimeoutError/URLError超时原因返回PARSE_AI_TIMEOUT及实际等待秒数；其他网络失败仍PARSE_AI_CONNECTION，不输出原始异常或密钥。

4项请求体/模型及地址隔离/直接和包装超时检查、23项接口与持久化等回归通过。未改前端及SQL，不重复前端构建。真实T43禁用思考后的质量/耗时未验证，不能认定已解决或将默认思考当已证明根因。下一步更新T43，仅重试原来件一次，确认SUCCEEDED/SAVED及标准字段，再回读刷新留存。重复超时问题的通用回流建议：固定区分配置就绪/合成调用/代表材料/业务验收，参数默认模式与输出体量纳入调用前核对，分别报告阶段和准确错误；真实修复验收前保留MYE回流待办，企业材料不迁出。
