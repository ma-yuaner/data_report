# ADM责任流转与管理观察 V2

2026-10-25，开发契约。用户授权复用现有能力开发；业务会议尚未确认SLA、权重和公开范围，不启用正式绩效、自动群发或虚构历史排名。

## 复用及范围

复用adm_case_document及version CAS、账号/受管成员、FormDialog/FormGrid/DateField、附件/导出。新共享AccountSelect只消费业务传入的授权选项，不自行查询全员。监控发件箱依赖监控事件，不伪造事件接入；本轮提供持久业务状态驱动的站内待办，站外自动提醒后续对接。

旧ETL的adm_dashboard_process_snapshot按旧adm_records.id及日志推断当前流程；adm_dashboard_result按供应下发日及旧状态聚合，均不能直接当新多明细模型的正式人员绩效。保留旧表/ETL不改写，待新旧映射及快照粒度确认后复用读模型。ads_target_progress_day当前供目标管理消费，不改造成ADM业务表。本轮不执行线上查询、DDL或ETL。

## API契约

现有case/line详情增加：case.coordinatorId/coordinatorName；新单不再以createdBy永久授权，旧单缺协调字段时保留创建者协调并明确legacyCoordination=true。主单动作coordinator需adm.assign及完整范围，body含coordinatorId,reason。协调人变更不会改创建审计。

config增加people={handle,review,finance,coordinate}，每项[{id,name}]，由已有账号目录按菜单与对应功能授权过滤；仅返回必要字段。已有assignees兼容。

line.workflow={reviewerId,reviewerName,financeOwnerId,financeOwnerName,acceptanceDueAt,processingDueAt,reviewDueAt,financeDueAt,waitingFor,waitingReason,nextFollowUpAt}。line.assignmentSegments保留每段ownerId/ownerName/assignedAt/acceptedAt/endedAt/round；不重置主单外部截止。line.handover为当前/最近交接，handoverHistory保留历史。

所有新动作复用POST /cases/:caseId/lines/:lineId/actions，version强制CAS，成功返回AdmCase。新增：

- plan：完整范围+adm.assign；body含reason及上述workflow人员/截止字段，未传不覆盖，空串清除。已完成任务禁止变更，审核/财务进行中禁止换人清空以逃避责任。
- follow_up：当前持锁承办人；body含waitingFor,waitingReason,nextFollowUpAt,reason。等待需有原因及下次跟进时间；不暂停外部期限，不将任意改备注当推进。
- transfer_request：当前承办人或完整范围分配者；body含ownerId,reason,summary。只允许待接单/处理中，不能自转，不能重复有待确认交接。
- transfer_accept / transfer_reject：仅待接收账号；reject需reason。接受前原责任和状态保留、接收者只读；接受后接收者PROCESSING并持锁，旧段结束，新段开始，原截止不重置。
- transfer_cancel：原承办人或完整范围分配者；需reason。
- assign兼容：首次分配仍PENDING_ACCEPT；已有人分配转为transfer_request，不再静默覆盖owner。批量结果逐项可查。

审核/财务配置了账号时仅该人（或管理员）执行；未配置仍保留旧获权角色处理，工作台明确显示待指定，不宣称已经有完整路由。处理人与审核人相同默认拒绝，只有显式ADM_ALLOW_SELF_REVIEW=true可例外，默认false。

GET /v1/adm/workflow/overview?scope=mine|team|all&page=1&pageSize=20&kind=...：返回{generatedAt,businessDate,scope,summary,people,items,pagination,limitations}。服务端从获授权主单/明细生成待办，非从前端人员参数授权；不展示金额/隐藏主单资料。默认mine只返本人的承办、交接、审核/财务任务及本人协调待办。items包含{id,caseId,lineId?,admNo,kind,label,ownerId,ownerName,status,dueAt,overdue,paused,version,url}；kind为ASSIGN/ACCEPT/PROCESS/TRANSFER/REVIEW/FINANCE/FOLLOW_UP。已结案/历史/作废不生成任务，暂停保留风险标记。summary含tasks,overdue,unassigned,missingDeadline,waiting；people按当前任务owner汇总tasks/overdue/missingDeadline，按姓名稳定排序，非绩效排名。分页前汇总整个权限范围，非当前页。待办来源旧规则缺人员时仅协调/全量可见“待指定”，不向任意员工广播。

本轮不支持历史日期回溯、综合评分、自动公开日报、外部发送成功声明；观察页必须明显披露这些限制。无任务不代表已达标；缺期限单列，不算未超时。

最终补充：unassigned包括承办、审核、财务待指定人员，不只统计未分配明细；needsAssignee显式标识。管理团队可见受管协调人的待指定协调摘要（coordinationOnly=true、无明细链接），不因此扩大订单/附件权限。默认读取最多5000张活跃主单，超限明确拒绝而非截断报数；不承诺大规模容量。新单不自动生成恢复+48小时期限，旧期限不改。审核/财务可按指定节点上传对应材料，完整可见权不替代功能权限。

## 实现归属与检查

主代理：后端、API及文档/隔离测试。唯一前端实现代理：frontend/src/components/AccountSelect.vue、frontend/src/features/adm/WorkflowPanel.vue、api.ts、AdmCenterView.vue、AdmDetailView.vue。不派生、不改其他文件，不重复扫仓；只跑相关前端检查。后端验证交接竞争/越权/截止保留/队列隔离/原件权限/缺期限统计。无生产操作、真实群消息或部署。
