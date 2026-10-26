# ADM未完成能力补齐 V3

2026-10-25。用户授权继续开发上一轮未完成项。只开发可配置和可验收机制，不擅自执行生产DDL/迁移、真实发送或把未确认业务口径当正式绩效。复用既有业务聚合、控件、账号/团队、附件、监控端点与人员绑定。

## 实现分工

主代理：后端、worker、DDL、迁移CLI、文档和隔离测试。唯一前端代理：新`CompletionPanel.vue`、新`CollaborationPanel.vue`、现有`api.ts/WorkflowPanel.vue/AdmCenterView.vue/AdmDetailView.vue`；需要时改AttachmentPanel，禁止改后端、提交或再派生。公共控件沿用AccountSelect/FormDialog/FormGrid/DateField/FilterPanel。

## 协办、整改、责任认定与共享

复用现有line actions和version CAS，成功返回AdmCase。line.collaborations每项{id,kind:COLLABORATION|REMEDIATION,title,description,ownerId,ownerName,requestedBy,requestedByName,dueAt,required,round,status:PENDING_ACCEPT|PROCESSING|PENDING_REVIEW|COMPLETED|CANCELLED,result,evidence:[],reviews:[],allowedActions:[]}。

- collaboration_create：完整范围+adm.assign，或当前持锁承办人；body={ownerId,title,description,dueAt?,required:boolean,kind?}。整改默认非结案前置，不因结案消失。
- collaboration_accept/submit：指定协办人，body={taskId,result?,evidence?}；submit必须结果和有效证据。
- collaboration_review/cancel：主承办/完整范围分配者，不能自审协办；body={taskId,approved:boolean,reason}；退回PROCESSING，取消须原因。已办结只读，不反复计功。
- 必需协办未完成阻断明细提交和主单结案；非必需整改可结案后继续accept/submit/review，不能借此修改已结案核心事实。
- responsibility_propose：当前持锁承办或完整范围分配者；{type:PERSON|SYSTEM|SUPPLIER|AIRLINE|PLATFORM|UNDETERMINED,responsibleUserId?,subject?,reason,evidence}。PERSON需有效账号，外部主体填subject；仅提案，不自动扩大被归因人权限。
- responsibility_review：指定审核人或完整范围且adm.review，非提案人；{approved,reason}；保留责任版本和复核依据。line.responsibility={id,status:PENDING_REVIEW|CONFIRMED|REJECTED,type,responsibleUserId?,responsibleName?,subject,reason,evidence,proposedBy,proposedAt,reviewedBy?,reviewedAt?,reviewReason?}，历史另存responsibilityHistory，不自动处罚/扣分。
- 主单动作attachment_share：完整范围+adm.edit；{attachmentId,lineIds:[],redactedFromId?,acknowledgeFullFile:true,reason}。空数组撤销。显式授权整份文件；如需脱敏，先上传实际脱敏副本，再关联原件，不假装系统自动脱敏。共享不授予无关订单权限，随明细访问权限逐次校验。

line.allowedActions增加create/propose/review相关动作；具体协办accept/submit/review/cancel从task.allowedActions消费（值仍为上述完整action名）。负责人账号目录复用config.people.handle；责任主体PERSON先复用该目录，仅接收已配置ADM的活跃账号，不自动匹配旧姓名。

## 后台运营接口

新运营表`adm_operation_document`保存策略、持久通知和不可变日报快照，不向旧看板表伪造数据。生产仅提供DDL不自动执行；表未安装时运营页明确503，普通ADM不依赖该表启动。配置/发送管理须系统管理员，其他人仅访问本人收件箱和获准范围的已发布日报。

- GET `/v1/adm/operations/config` -> {version,notificationsEnabled:false,endpointIds:[],leadMinutes:null,repeatMinutes:null,escalationMinutes:null,snapshotsEnabled:false,snapshotAt:'',rankingEnabled:false,minimumSamples:null,approvalNote:'',endpointOptions:[{id,name}],endpointAvailable:boolean,externalDeliveryEnabled:boolean}。端点复用监控中心，不接受页面输入Webhook。
- PUT同路径：以上可编辑字段+version。开启/改策略必须approvalNote；SLA/频率不默认猜测。rankingEnabled需要minimumSamples为正数；snapshotAt为北京时间HH:mm。首次版本0。
- POST `/operations/preview` -> {enabled,externalDeliveryEnabled,tasks,wouldCreate,missingConfig:[],warnings:[]}；只预览不发消息。
- GET `/operations/inbox` -> {items:[{id,version,title,body,createdAt,readAt,caseId?,lineId?,url?,status}],unread}，只本人且当前仍有关联/任务有效，不带隐藏主单/金额。
- POST `/operations/inbox/:id/read`，{version}，只本人。
- GET `/operations/deliveries` -> {items:[{id,version,channel,recipientId,status,attempts,createdAt,nextAttemptAt,errorCode}], ...}；管理员，屏蔽Webhook/企业微信身份/正文中的个人资料。

worker默认不发送。策略开启才生成去重通知；站内消息持久化，站外还需ADM_EXTERNAL_DELIVERY_ENABLED显式部署开关。发件前重验策略批准者、账号启用/菜单/当前任务/对象权限及端点版本。网络结果未知/进程中断标UNKNOWN不自动重发；明确拒绝可有限重试，成功留回执。任务失效/转交/权限撤销取消旧通知；不向群发业务明细。复用已有端点/账号花名册绑定进行动态提醒，无映射不冒充已提醒本人。过期升级只发给有权的当前协调人。

## 日报与试运行分项榜

- GET `/v1/adm/reports?date=YYYY-MM-DD` -> {items:[{id,version,businessDate,generatedAt,revision,published,ruleVersion,quality}],...}。
- POST `/reports/capture`（管理员）{reason}，只捕获当前时点，不伪造过去午夜快照；返回完整report。
- GET `/reports/:id?scope=mine|team|all` -> {id,version,businessDate,generatedAt,revision,published,ruleVersion,quality,summary,people,limitations}。非管理员只看已发布且本人/受管成员；sources原始ID版本仅全量权限可见。
- POST `/reports/:id/publish`（管理员）{version,reason}，人工核对发布；原指标内容不可编辑，更正需新修订，留发布时间/人/原因。

report.people每项{ownerId,ownerName,role,businessType,openTasks,overdue,missingDeadline,firstReviewed,firstPassed,firstPassRate:string|null,completedTasks,eligible:boolean,rank:number|null}，firstPassRate为百分数十进制字符串（不含%）。按主单/line_id/轮次去重首次审核，审核人活动与承办质量分开；只使用带当时责任和业务类型的可信事件，不按当前负责人回写历史，来源不足列quality缺口。排名仅配置批准后对同businessType的承办首次审核通过率生成试运行分项榜，低于minimumSamples不排名、同分并列，无综合分/处罚。日报包含当前风险快照，不把查询时点冒充全天已发生的全部工作；无旧事件不补零。

## 迁移与对接边界

提供离线迁移预检CLI：显式ERP JSON/旧Python SQLite（只读）/日志JSON/附件受控目录及映射清单，预览冲突/缺映射/文件hash后再显式apply到只读历史档案；不抓旧URL、不猜同ADM号归并、不把恢复/旧日志当新审批。真实来源未提供时只完成工具和合成演练。

现有订单/财务接口需提供真实契约才能接入；人工凭证流程继续有效，但不将开发开关改成“外部核验成功”。生产表结构/新鲜度核验及正式切换需获准连接与业务验收，不能在此轮假报已执行。
