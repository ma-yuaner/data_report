# ADM V1 实现契约

以下文件归属保留本轮早期已完成并行工作的记录；后续遵循用户最新规则：主代理先实施，最多一个活动子代理，不再派生、不重复扫仓或争写文件，仅补直接相关验证。

状态：2026-10-24开发契约，承接[PRD](adm-management-center-prd-v1.md)。本轮目标为可运行的首版管理闭环；外部订单、财务、ASD接入未配置时明确未接入，禁止伪造结果。主代理负责集成和验收，文件只有一个写入者。

## 归属

- backend子代理：`backend/data_report_api/services/adm/`（其中attachments.py、exchange.py保留主代理）、`backend/data_report_api/api/adm.py`、`docs/sql/adm-management-center-v1.sql`。
- frontend子代理：`frontend/src/features/adm/`、`frontend/src/router/index.ts`、`frontend/src/layouts/AppLayout.vue`。
- QA子代理：仅`.test-artifacts/adm/`内验收脚本及报告，不修改业务代码。
- 主代理：附件存储/预览与Excel交换、权限目录/配置/注册、项目文档/目录生成及最终集成；未经协调不改子代理文件。

## JSON/API

独立接管增量：CASE_FIELDS新增supplierCode/airline/ticketCount/originalAmountCny/businessCategory；LINE_FIELDS新增platformCode/airline/ticketCount/amountCny/businessCategory/actualOwner/actualHandler/recoveryDeadline/resolution。金额可空、精确非负最多4位小数，数量为非负整数；归档保留原值，不能映射时先报错。实际处理/责任字段不授予账号权限，持锁/当前处理人/审核仍由授权动作维护。

- POST `/cases/:id/lines/bulk-assign`：`{version,lineIds:[1—100个不同ID],ownerId,reason}`，adm.assign+完整主单范围；逐项CAS留痕，返回items/successCount/failedCount，并发冲突停止后续并标未执行，不冒充整批原子成功。
- 原imports/preview新增管理员ERP JSON数组入口；原commit只读归档模式以ERP旧id全局幂等，同来源变化409；HISTORICAL原状态只作未核验历史，不继承账号/旧锁/当前审核或财务。普通XLSX仍为新单创建，不覆盖已有单；历史原件可由管理员补传但业务字段不可改。
- config新增assignees，只有adm.assign人员取得已启用且有ADM菜单/查看/处理权限的人员ID和显示名；实际分配继续服务端核对。storage错误细分固定码，不返回原异常或连接信息。
- cases新增businessCategory/supplierCode/activeOnly筛选，全部范围SQL分页；本人/团队原权限路径保留。工作台排除CLOSED/HISTORICAL，台账可查历史。导出冻结相同筛选、版本和权限，仍用全局队列，新增历史原始字段sheet。

2026-10-24独立接管补充：目标为sibebid新表，中台独立运行，旧Java仅作规则/迁移来源。create可传`lines:[lineFields]`与主单原子保存；复制新建也接受本次显式填写的lines，不复制来源旧订单/附件/完成状态。金额可空、不自动平分，初始订单均待分配；人员、持锁、审核和完成不能由建档输入提升。完整字段与迁移顺序见[接管清单](adm-independent-takeover-v1.md)。

统一响应`{success,message,data}`。API前缀`/api/v1/adm`。金额均十进制字符串或null，不用JS浮点金额。ID字符串；所有修改含主单`version`，冲突409。主单/明细状态枚举由config返回；用户操作可见性以服务端allowedActions和禁用原因为准。

- GET `/config`：`{storageMode,available,capabilities:{orders,finance,notifications},caseStatuses,lineStatuses,businessTypes,attachmentCategories}`，未部署表应503，不静默回退演示。
- GET `/cases`：`{items:[caseSummary],pagination:{page,pageSize,total},summary:{cases,lines,open,overdue}}`，参数search/status/scope=mine|team|all/page/pageSize；mine为默认；无权限all禁止。
- POST `/cases`：`{admNo,supplierName,supplierType,currency,originalAmount,issuedDate,deadline,description,remark,idempotencyKey?}`。
- GET/PATCH `/cases/:caseId`：caseDetail/允许字段修改。
- POST `/cases/:caseId/copy`：引用新建，原状态和附件完成事实不复制。
- POST `/cases/:caseId/lines` 与 PATCH `/cases/:caseId/lines/:lineId`：`{version,...lineFields}`。
- POST `/cases/:caseId/actions`：`{version,action:publish|pause|resume|void|close|reopen,...}`；close必执行closure-check。
- POST `/cases/:caseId/lines/:lineId/actions`：`{version,action:assign|claim|lock|unlock|submit|approve|return|finance_confirm|recovery|appeal|difference,...}`，分别检查权限、身份、持锁和状态；解锁撤销处理写权限，原处理人重新持锁后才能继续。
- GET `/cases/:caseId/closure-check`：`{canClose,checks:[{code,label,passed,lineId?}],blockers:[string],amounts:{currency,originalAmount,allocatedAmount,gap}}`。
- GET `/cases/:caseId/timeline`：事件列表。
- GET/POST `/cases/:caseId/attachments`：metadata列表/multipart上传`file,version,category,lineId?`。
- GET `/cases/:caseId/attachments/:attachmentId/preview|download`：每次鉴权，图片/PDF内联，XLSX预览返回JSON分页，其他下载。

caseSummary：`id,admNo,supplierName,supplierType,currency,originalAmount,issuedDate,deadline,status,version,description,remark,createdAt,updatedAt,lineCount,completedCount,attachmentCount,partial,allowedActions`。

caseDetail附加：`lines,attachments,analysis,timeline,closureCheck`。受限用户只见本人的明细，partial=true时隐藏原总额及主单私密备注/材料；全量结案等动作禁止。

lineFields：`id,businessType:ISSUE|REFUND|CHANGE|UNKNOWN,platform,shop,site,orderNo,ticketNo,pnr,system,pcc,currency,amount,description,differenceDescription,diffType,diffSecondType,remark,ownerId,ownerName,status,matchStatus:UNVERIFIED|OURS|NOT_OURS,analysis:{facts,dispute,cause,proposal,conclusion,prevention},appeals:[],recoveries:[],difference:{declaration,verification,reference,evidence},finance:{required,status,reference,amount,currency},attribution,attachments:[]`。

主单状态：DRAFT/PENDING_ASSIGN/PROCESSING/PENDING_REVIEW/WAITING_FINANCE/CLOSED，暂停/作废独立字段。明细：PENDING_ASSIGN/PENDING_ACCEPT/PROCESSING/PENDING_REVIEW/WAITING_FINANCE/COMPLETED。

## 后端公共服务约定

包公开导出`AdmService,AdmError`；`AdmError`含message/status/code。HTTP适配仅依赖公开接口，所有权限/金额/状态在服务校验。`AdmService(config)`以mysql为正式持久化，不自动建生产表；明确配置sqlite只用于隔离本机验收，不当正式MySQL上线。

公开方法统一`user`首参数：`config_info, list_cases(user,filters), create_case(user,body), case_detail(user,id), update_case(user,id,body), copy_case(user,id,body), add_line(user,id,body), update_line(user,id,line_id,body), case_action(user,id,body), line_action(user,id,line_id,body), closure_check(user,id), timeline(user,id)`。

附件接入公共方法：`add_attachment(user,case_id,body)`，body含`version,attachment:{id,name,category,lineId,mime,size,sha256,storageKey,createdAt}`；写库前验证角色、范围、对象、版本。`attachment(user,case_id,attachment_id)`鉴权后返回内部metadata（含storageKey，仅供附件服务，HTTP返回不得泄露storageKey）。无附件元数据HTTP直写入口。

数据范围基于登录用户ID及显式permission；管理员全部。`adm.scope.all`允许全量，`adm.scope.team`只在可信managed_user_ids存在时展开，缺失fail-closed；不能相信前端人员ID。`adm.view/create/edit/assign/handle/review/finance.confirm/close/reopen/unlock.force/import/export/notify`独立功能权限，默认管理员。

每次写都要版本CAS/事务，日志和业务一致。已结案只读，重开保留快照。审核不可无证据跨到已完成；财务人工凭证确认标记来源，核验未接入不假成功。附件原件/必要分析/金额核平是结案条件。

## 验证与交付

只用隔离本机SQLite/合成数据验收；不得默认连接生产，不执行生产DDL、不发送群消息、不部署。所有新增test仅在忽略目录。源Java/Python仅定向读取，不修改。子代理不commit/push；主代理检查后统一交付。GitHub本轮无新增目的地授权，不重试上轮被拒的推送。
