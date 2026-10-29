/** Isolated replacement for @/api/http in the prototype Vite config only. Never performs network I/O. */
import { reactive } from 'vue'
import { workspaceSeed } from '../workspace'
import { cents, cash, id } from '../model'
import { demoPeople, useAuthStore } from './auth'
import { templateWorkbook, readWorkbook } from './workbook'
import { governanceResponse } from '../../resource-review/data'
export type ApiEnvelope<T>={success:boolean;data:T;message?:string}
type F=Record<string,any>
const copy=<T>(value:T):T=>JSON.parse(JSON.stringify(value))
const at=()=>new Date().toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'}).replace(' ','T')
const actor=()=>useAuthStore().user
const person=(key:string)=>demoPeople.find(item=>item.id===key)?.name || key || '待指定'
const storage='adm-live-source-v04'
function makeLine(value:F,parent:F):F {return {id:id(),status:'PENDING_ASSIGN',ownerId:'',ownerName:'',lockOwnerId:'',businessType:'ISSUE',currency:parent.currency,amount:null,platform:'',shop:'',site:'',orderNo:'',ticketNo:'',pnr:'',matchStatus:'UNVERIFIED',matchEvidence:'',description:'',remark:'',analysis:{},appealDecision:'UNDECIDED',appealReason:'',recoveryRequired:false,recoveries:[],appeals:[],difference:{declaration:'UNDECLARED'},finance:{required:false,reason:'演示：本单不需财务处理',status:'PENDING'},workflow:{},collaborations:[],assignmentSegments:[],...copy(value)}}
function initial():F {
  const source=workspaceSeed()
  const cases=source.cases.map(item=>{
    const parent:F={id:item.id,admNo:item.admNo,supplierName:item.supplier,supplierType:'SUPPLIER',supplierCode:'DEMO-SUP',airline:'XX',currency:item.currency || 'CNY',originalAmount:item.amount,issuedDate:'2026-10-29',deadline:'2026-11-05T18:00',description:item.description,remark:item.remark,status:item.status==='CLOSED'?'CLOSED':'PROCESSING',version:1,partial:false,analysis:{},coordinatorId:'coordinator',coordinatorName:'林协调',createdAt:at(),updatedAt:at(),paused:false,voided:false,lines:[],attachments:[]}
    parent.lines=item.lines.map(line=>makeLine({id:line.id,orderNo:line.orderNo,ticketNo:line.ticketNo,pnr:line.pnr,platform:line.platform,shop:line.site,site:line.site,amount:line.amount,businessType:({出票:'ISSUE',退票:'REFUND',改签:'CHANGE'} as F)[line.business],status:({ACCEPT:'PENDING_ACCEPT',INVESTIGATE:'PROCESSING',APPEAL:'PROCESSING',REVIEW:'PENDING_REVIEW',DONE:'COMPLETED',MATCH:'PENDING_ASSIGN'} as F)[line.stage] || 'PROCESSING',ownerId:line.owner==='lead'?'handlerA':line.owner,ownerName:person(line.owner==='lead'?'handlerA':line.owner),matchStatus:'OURS',matchEvidence:'合成订单归属演示',description:line.description,analysis:{facts:'合成演示：已对照原件核实订单。',conclusion:line.conclusion,proposal:'按业务证据处理'},appealDecision:'NOT_REQUIRED',appealReason:'合成演示：本单无争议',recoveryRequired:line.recoveryRequired,finance:{required:line.financeRequired,reason:'演示核对依据',status:'PENDING'},workflow:{processDeadline:line.dueAt},diffType:line.diffType},parent))
    parent.attachments=item.files.map(file=>({id:file.id,name:file.name,category:file.category==='下发原件'?'ORIGINAL':'ANALYSIS',lineId:file.lineId,sharedLineIds:file.shared,mime:'text/plain',size:file.content.length,createdAt:at(),text:file.content}))
    return parent
  })
  return {cases,events:[],inbox:[],reports:[],operation:{version:1,notificationsEnabled:false,endpointIds:[],leadMinutes:60,repeatMinutes:120,escalationMinutes:240,snapshotsEnabled:false,snapshotAt:'18:00',rankingEnabled:false,minimumSamples:5,approvalNote:'本机演示，不发送',endpointOptions:[],endpointAvailable:false,externalDeliveryEnabled:false}}
}
let saved:F|undefined
try{const raw=localStorage.getItem(storage);if(raw){const value=JSON.parse(raw);if(Array.isArray(value.cases)&&Array.isArray(value.events))saved=value}}catch{/* Use independent seed; never overwrite v0.3. */}
export const liveState=reactive<F>(saved || initial())
export const transportStatus=reactive({last:'本机数据适配层就绪',error:''})
const plans=new Map<string,F>()
function need(condition:unknown,message:string):asserts condition{if(!condition)throw Error(message)}
function persist(){try{localStorage.setItem(storage,JSON.stringify(liveState));transportStatus.error=''}catch{transportStatus.error='本机缓存容量不足，请导出备份；当前数据仍保留在内存。'}}
export function exportLiveState(){return JSON.stringify({kind:'ADM_LIVE_SOURCE',version:'0.4',state:liveState},null,2)}
export function restoreLiveState(text:string){const value=JSON.parse(text.replace(/^\uFEFF/,''));need(value.kind==='ADM_LIVE_SOURCE'&&Array.isArray(value.state?.cases)&&Array.isArray(value.state?.events),'需要0.4原页面原型备份');for(const item of value.state.cases){need(item.id&&item.admNo&&Array.isArray(item.lines)&&Array.isArray(item.attachments),'主单结构不完整');cents(item.originalAmount);for(const line of item.lines)if(line.amount!=null&&line.amount!=='')cents(line.amount)}Object.assign(liveState,value.state);persist()}
function record(parent:F,action:string,body:F={},line?:F){parent.version++;parent.updatedAt=at();liveState.events.push({id:id(),caseId:parent.id,lineId:line?.id,action,label:`本机模拟：${action}`,actorId:actor().id,actorName:actor().displayName,createdAt:at(),at:at(),reason:body.reason || body.result || '本地模拟保存',afterStatus:line?.status || parent.status});persist()}
function workflowTasks():F[]{return liveState.cases.filter((item:F)=>!item.voided&&!item.historicalArchive).flatMap((item:F)=>item.lines.filter((line:F)=>line.status!=='COMPLETED'||line.finance?.required&&line.finance.status!=='CONFIRMED').map((line:F)=>({id:`${item.id}:${line.id}`,caseId:item.id,lineId:line.id,admNo:item.admNo,label:({PENDING_ASSIGN:'分配负责人',PENDING_ACCEPT:'接收任务',PROCESSING:'办理订单',PENDING_REVIEW:'独立审核',WAITING_FINANCE:'财务核对',COMPLETED:'回款跟进'} as F)[line.status],kind:({PENDING_ASSIGN:'ASSIGN',PENDING_ACCEPT:'ACCEPT',PROCESSING:'PROCESS',PENDING_REVIEW:'REVIEW',WAITING_FINANCE:'FINANCE',COMPLETED:'FINANCE'} as F)[line.status],ownerId:line.status==='PENDING_REVIEW'?'reviewer':line.status==='WAITING_FINANCE'?'finance':line.ownerId,ownerName:person(line.status==='PENDING_REVIEW'?'reviewer':line.status==='WAITING_FINANCE'?'finance':line.ownerId),status:line.status,dueAt:line.workflow?.processDeadline || item.deadline,overdue:false,paused:item.paused,version:item.version,url:`/adm/cases/${item.id}?lineId=${line.id}`})))}
function decorate(item:F):F {
  const parent=copy(item), admin=actor().isAdmin, who=actor().id, active=!item.historicalArchive&&!item.voided&&item.status!=='CLOSED'
  parent.allowedActions=active?[...(admin?['edit','upload','addLine','coordinator','pause','void','attachment_share']:[]),...(admin&&item.status==='DRAFT'?['publish']:[]),...(admin&&item.lines.length&&item.lines.every((line:F)=>line.status==='COMPLETED')?['close']:[]),...(item.paused&&admin?['resume']:[])]:admin&&item.status==='CLOSED'?['copy','reopen']:['copy']
  if(!parent.allowedActions.includes('copy'))parent.allowedActions.push('copy')
  parent.lines=parent.lines.map((line:F)=>{
    const own=line.ownerId===who, process=line.status==='PROCESSING', unlocked=!line.lockOwnerId||line.lockOwnerId===who
    const actions:string[]=[]
    if(active&&!item.paused){if(admin&&['PENDING_ASSIGN','PENDING_ACCEPT','PROCESSING'].includes(line.status))actions.push('assign','plan');if(own&&line.status==='PENDING_ACCEPT')actions.push('claim');if(own&&process&&unlocked)actions.push('edit','upload','recovery','appeal','difference','submit','plan','follow_up','transfer_request','collaboration_create','responsibility_propose','lock');if(line.lockOwnerId===who||admin)actions.push('unlock');if(own&&line.handover?.status==='PENDING')actions.push('transfer_cancel');if(line.handover?.toId===who&&line.handover.status==='PENDING')actions.push('transfer_accept','transfer_reject');if(who==='reviewer'&&line.status==='PENDING_REVIEW')actions.push('approve','return');if(who==='finance'&&(line.status==='WAITING_FINANCE'||line.finance?.required))actions.push('finance_confirm','upload')}
    if(item.status==='CLOSED'&&who==='finance'&&line.finance.required&&line.finance.status!=='CONFIRMED')actions.push('finance_confirm','upload')
    line.allowedActions=actions;line.uploadCategories=['VERIFICATION','RECOVERY','APPEAL','FINANCE','ANALYSIS']
    line.collaborations=(line.collaborations||[]).map((task:F)=>({...task,allowedActions:[...(task.ownerId===who&&task.status==='PENDING_ACCEPT'?['collaboration_accept']:[]),...(task.ownerId===who&&task.status==='PROCESSING'?['collaboration_submit']:[]),...(task.ownerId!==who&&(own||admin)&&task.status==='PENDING_REVIEW'?['collaboration_review']:[]),...(own||admin?['collaboration_cancel']:[])]}))
    if(line.responsibility)line.responsibility.allowedActions=who==='reviewer'&&line.responsibility.status==='PENDING_REVIEW'?['responsibility_review']:[]
    return line
  })
  parent.lineCount=parent.lines.length;parent.completedCount=parent.lines.filter((line:F)=>line.status==='COMPLETED').length
  return parent
}
function closure(parent:F):F {const total=parent.lines.reduce((sum:number,line:F)=>sum+(line.amount==null||line.amount===''?0:cents(line.amount)),0);const checks=[{code:'lines',label:'订单明细全部完成',passed:parent.lines.length>0&&parent.lines.every((line:F)=>line.status==='COMPLETED')},{code:'amount',label:'同币种金额分摊一致',passed:parent.lines.every((line:F)=>line.currency===parent.currency&&line.amount!=null&&line.amount!=='')&&total===cents(parent.originalAmount)},{code:'original',label:'具备下发原件',passed:parent.attachments.some((file:F)=>file.category==='ORIGINAL')},{code:'collaboration',label:'必需协办与交接已完成',passed:parent.lines.every((line:F)=>line.handover?.status!=='PENDING'&&line.collaborations.every((task:F)=>!task.required||task.status==='COMPLETED'))}];return {canClose:checks.every(item=>item.passed),checks,blockers:checks.filter(item=>!item.passed).map(item=>item.label),amounts:{currency:parent.currency,originalAmount:parent.originalAmount,allocatedAmount:cash(total),gap:cash(Math.abs(cents(parent.originalAmount)-total))}}}
function patchFields(target:F,body:F){for(const [key,value] of Object.entries(copy(body)))if(!['id','version','allowedActions','action','lines','attachments','idempotencyKey'].includes(key))target[key]=value}
function checkVersion(parent:F,body:F){if(body.version!=null&&body.version!==parent.version){const error=new Error('记录版本已变化，草稿保留，请刷新核对') as Error&{code:string};error.code='ADM_VERSION_CONFLICT';throw error}}
function applyAction(parent:F,line:F|undefined,body:F){
  const action=body.action, rights=line?decorate(parent).lines.find((value:F)=>value.id===line.id).allowedActions:decorate(parent).allowedActions
  if(!['collaboration_accept','collaboration_submit','collaboration_review','collaboration_cancel','responsibility_review'].includes(action))need(rights.includes(action),'当前模拟人员或状态不允许此操作，请切换对应岗位')
  if(line){
    if(action==='assign'){need(body.ownerId,'请选择承办人');if(line.ownerId&&line.ownerId!==body.ownerId){line.handover={status:'PENDING',fromId:line.ownerId,fromName:line.ownerName,toId:body.ownerId,toName:person(body.ownerId),reason:body.reason,summary:body.summary,requestedAt:at()}}else{line.ownerId=body.ownerId;line.ownerName=person(body.ownerId);line.status='PENDING_ACCEPT'}}
    else if(action==='claim'){line.status='PROCESSING';line.lockOwnerId=actor().id;line.assignmentSegments.push({id:id(),ownerName:actor().displayName,assignedAt:at(),acceptedAt:at(),round:1,reason:'本机模拟接单'})}
    else if(action==='lock')line.lockOwnerId=actor().id
    else if(action==='unlock')line.lockOwnerId=''
    else if(action==='submit'){need(line.matchStatus==='OURS','先核实订单归属');need(line.description&&line.analysis?.facts&&line.analysis?.conclusion,'先编辑订单，补齐问题描述、事实和结论');need(!line.workflow?.waitingFor,'等待事项未解除');need(line.handover?.status!=='PENDING','交接未确认');need(line.collaborations.every((task:F)=>!task.required||task.status==='COMPLETED'),'必需协办未完成');need(!line.recoveryRequired||line.recoveries.some((r:F)=>r.status==='COMPLETED'),'恢复编码未完成');need(line.appealDecision!=='UNDECIDED','请明确申诉决策');need(line.appealDecision!=='NOT_REQUIRED'||line.appealReason,'不申诉需说明原因');need(line.appealDecision!=='REQUIRED'||line.appeals.length&&line.appeals.every((r:F)=>['SUCCESS','PARTIAL_SUCCESS','FAILED','WITHDRAWN'].includes(r.status)),'申诉尚未终结');need(line.finance.required||line.finance.reason,'无需财务处理须说明依据');line.status='PENDING_REVIEW';line.lockOwnerId=''}
    else if(action==='approve'){need(body.reason?.trim(),'审核意见必填');line.review={approved:true,reason:body.reason,by:actor().displayName,at:at()};line.status=line.finance.required?'WAITING_FINANCE':'COMPLETED'}
    else if(action==='return'){need(body.reason?.trim(),'退回原因必填');line.status='PROCESSING';line.review={approved:false,reason:body.reason,at:at()}}
    else if(action==='finance_confirm'){need(body.reference?.trim()&&cents(body.amount)>0,'请填写凭证和有效金额');need(body.currency===line.currency,'币种不一致');need(body.evidence?.length,'请引用财务证据');line.finance={...line.finance,status:'CONFIRMED',reference:body.reference,amount:body.amount,currency:body.currency,reason:body.reason,evidence:body.evidence};line.status='COMPLETED'}
    else if(action==='recovery'){need(body.code,'请填写原编码');need(body.status!=='COMPLETED'||body.resultCode&&body.evidence?.length,'完成恢复须有恢复后编码和佐证');line.recoveries.push({...copy(body),id:id(),createdAt:at()})}
    else if(action==='appeal'){need(body.targetName?.trim()&&body.reason?.trim(),'填写申诉主体与说明');need(!['SUCCESS','PARTIAL_SUCCESS'].includes(body.status)||body.waivedAmount!==''&&body.waivedAmount!=null,'成功/部分成功须填减免金额');if(body.waivedAmount!=null&&body.waivedAmount!=='')need(cents(body.waivedAmount)<=cents(line.amount),'减免不能超过明细金额');line.appeals.push({...copy(body),id:id(),createdAt:at()})}
    else if(action==='difference'){need(body.reason?.trim(),'填写差异依据');line.difference={...copy(body),verified:false}}
    else if(action==='plan'){for(const key of ['reviewerId','financeOwnerId','processDeadline','appealDeadline','reviewDeadline','financeDeadline','recoveryDeadline'])if(key in body)line.workflow[key]=body[key]}
    else if(action==='follow_up'){if(body.waitingFor)need(body.nextFollowUpAt&&body.waitingReason,'等待须有原因与跟进时间');patchFields(line.workflow,body)}
    else if(action==='transfer_request'){need(body.ownerId!==actor().id&&body.ownerId&&body.summary,'请选择其他接收人并填交接摘要');line.handover={status:'PENDING',fromId:line.ownerId,fromName:line.ownerName,toId:body.ownerId,toName:person(body.ownerId),reason:body.reason,summary:body.summary,requestedAt:at()}}
    else if(action.startsWith('transfer_')){need(line.handover?.status==='PENDING','交接已处理');line.handover.responseReason=body.reason;line.handover.status=action==='transfer_accept'?'ACCEPTED':action==='transfer_reject'?'REJECTED':'CANCELLED';if(action==='transfer_accept'){line.ownerId=actor().id;line.ownerName=actor().displayName;line.lockOwnerId=''}}
    else if(action==='collaboration_create'){need(body.title&&body.description&&body.ownerId,'补齐协办目标、人员与描述');line.collaborations.push({...copy(body),id:id(),ownerName:person(body.ownerId),status:'PENDING_ACCEPT',reviews:[]})}
    else if(action.startsWith('collaboration_')){const task=line.collaborations.find((r:F)=>r.id===body.taskId);need(task,'协办不存在');const decorated=decorate(parent).lines.find((r:F)=>r.id===line.id).collaborations.find((r:F)=>r.id===task.id);need(decorated.allowedActions.includes(action),'当前人员不能办理该协办');if(action==='collaboration_accept')task.status='PROCESSING';if(action==='collaboration_submit'){need(body.result&&body.evidence?.length,'结果和证据必填');task.result=body.result;task.evidence=body.evidence;task.status='PENDING_REVIEW'}if(action==='collaboration_review'){task.reviews.push({approved:body.approved,reason:body.reason,at:at()});task.status=body.approved?'COMPLETED':'PROCESSING'}if(action==='collaboration_cancel')task.status='CANCELLED'}
    else if(action==='responsibility_propose'){need(body.reason&&body.evidence?.length,'责任提案须有原因和证据');line.responsibility={...copy(body),status:'PENDING_REVIEW',proposedByName:actor().displayName,proposedAt:at()}}
    else if(action==='responsibility_review'){need(actor().id==='reviewer','仅审核人可复核');line.responsibility={...line.responsibility,status:body.approved?'CONFIRMED':'REJECTED',reviewReason:body.reason}}
    else throw Error(`当前动作尚未适配本机演示：${action}`)
  }else{
    if(action==='publish'){need(parent.lines.length,'至少添加一条订单');parent.status='PROCESSING'}
    else if(action==='pause'){need(body.reason?.trim(),'挂起原因必填');parent.paused=true;parent.pauseReason=body.reason}
    else if(action==='resume')parent.paused=false
    else if(action==='void'){need(body.reason?.trim(),'作废原因必填');parent.voided=true}
    else if(action==='close'){need(closure(parent).canClose,closure(parent).blockers.join('；'));parent.status='CLOSED'}
    else if(action==='reopen'){need(body.reason?.trim(),'重开原因必填');parent.status='PROCESSING';parent.lines.forEach((r:F)=>{r.status='PROCESSING'})}
    else if(action==='coordinator'){parent.coordinatorId=body.coordinatorId;parent.coordinatorName=person(body.coordinatorId)}
    else if(action==='attachment_share'){need(body.acknowledgeFullFile,'须确认整份文件适合共享');const file=parent.attachments.find((r:F)=>r.id===body.attachmentId);need(file,'附件不存在');file.sharedLineIds=body.lineIds || []}
    else throw Error(`当前动作尚未适配本机演示：${action}`)
  }
  record(parent,action,body,line)
}
function config(){return {available:true,storageMode:'prototype-local',capabilities:{orders:false,finance:false,notifications:false},caseStatuses:['DRAFT','PROCESSING','PENDING_REVIEW','CLOSED'],lineStatuses:['PENDING_ASSIGN','PENDING_ACCEPT','PROCESSING','PENDING_REVIEW','WAITING_FINANCE','COMPLETED'],businessTypes:['ISSUE','REFUND','CHANGE','UNKNOWN'],attachmentCategories:['ORIGINAL','VERIFICATION','RECOVERY','APPEAL','FINANCE','ANALYSIS'],assignees:demoPeople.map(p=>({id:p.id,name:p.name})),people:{handle:demoPeople.filter(p=>p.role==='承办人').map(p=>({id:p.id,name:p.name})),review:[{id:'reviewer',name:'许审核'}],finance:[{id:'finance',name:'何财务'}],coordinate:[{id:'coordinator',name:'林协调'}]}}}
async function dispatch(method:string,url:string,body:F={},options:F={}):Promise<any>{
  if(url.startsWith('/v1/resource-governance/')){need(method==='GET','资源治理原型只允许本机查询，不提供真实写入');transportStatus.last=`本机 ${method} ${url}`;return governanceResponse(url,options.params || {})}
  need(url.startsWith('/v1/adm'),'原型禁止访问ADM以外接口')
  const path=url.slice('/v1/adm'.length), params=options.params || {}
  transportStatus.last=`本机 ${method} ${url}`
  if(path==='/config')return config()
  if(path==='/workflow/overview'){let items=workflowTasks();if(params.scope==='mine'&&!actor().isAdmin)items=items.filter(r=>r.ownerId===actor().id);if(params.kind)items=items.filter(r=>r.kind===params.kind);return {generatedAt:at(),businessDate:at().slice(0,10),scope:params.scope || 'mine',summary:{tasks:items.length,overdue:0,unassigned:items.filter(r=>!r.ownerId).length,missingDeadline:items.filter(r=>!r.dueAt).length,waiting:0},people:demoPeople.map(p=>({ownerId:p.id,ownerName:p.name,tasks:items.filter(r=>r.ownerId===p.id).length,overdue:0,missingDeadline:0})),items:items.slice((Number(params.page||1)-1)*20,Number(params.page||1)*20),pagination:{page:params.page||1,pageSize:20,total:items.length},limitations:['本机合成数据；通知、订单、财务均未连接生产。']}}
  if(path==='/operations/config'){if(method==='PUT'){need(actor().isAdmin,'仅协调人可改演示策略');need(!body.notificationsEnabled,'本机演示不能启用真实发送');Object.assign(liveState.operation,body,{version:liveState.operation.version+1});persist()}return copy(liveState.operation)}
  if(path==='/operations/preview')return {mode:'local-only',wouldSend:0,items:workflowTasks(),limitations:['仅本地预览，没有真实投递']}
  if(path==='/operations/inbox')return {items:liveState.inbox,unread:liveState.inbox.filter((r:F)=>!r.readAt).length}
  if(path.startsWith('/operations/inbox/')){const note=liveState.inbox.find((r:F)=>r.id===path.split('/')[3]);need(note,'消息不存在');note.readAt=at();persist();return note}
  if(path==='/operations/deliveries')return {items:[]}
  if(path==='/reports'&&method==='GET')return {items:liveState.reports.filter((r:F)=>!params.date||r.businessDate===params.date)}
  if(path==='/reports/capture'){const report={id:id(),version:1,businessDate:at().slice(0,10),generatedAt:at(),revision:liveState.reports.length+1,published:false,ruleVersion:'prototype-0.4',summary:{tasks:workflowTasks().length},people:[],quality:{source:'本机合成'},limitations:['不是真实日报或绩效']};liveState.reports.push(report);persist();return report}
  if(path.startsWith('/reports/')){const report=liveState.reports.find((r:F)=>r.id===path.split('/')[2]);need(report,'快照不存在');if(path.endsWith('/publish')){report.published=true;report.version++;persist()}return report}
  if(path==='/templates'){need(params.format==='center','旧Java/Python兼容模板在本版尚未模拟；请使用统一模板');return templateWorkbook()}
  if(path==='/imports/preview'){const file=(body as unknown as FormData).get('file') as File;need(file&&file.size<=2*1024*1024,'选择2MB以内的本机演示文件');const items=file.name.endsWith('.json')?JSON.parse(await file.text()):await readWorkbook(file);need(Array.isArray(items)&&items.length,'没有可导入主单');const errors:F[]=[];items.forEach((item:F,i:number)=>{if(!item.admNo||!item.supplierName||!item.currency||!/^\d+(\.\d{1,2})?$/.test(String(item.originalAmount)))errors.push({row:i+2,message:'ADM号、下发方、币种和两位小数金额必填'});if(liveState.cases.some((old:F)=>old.admNo===item.admNo&&old.supplierName===item.supplierName))errors.push({row:i+2,message:'本机已存在同供应商同ADM'})});const previewId=id();plans.set(previewId,{items:copy(items),historical:file.name.endsWith('.json'),version:liveState.cases.map((r:F)=>r.id).join(',')});return {rowCount:items.length,cases:items.map((r:F)=>({...r,lineCount:r.lines?.length||0})),errors,warnings:['本机预览；JSON作为历史只读档案，XLSX为本机统一模板；不会自动匹配真实订单。'],previewId:errors.length?'':previewId}}
  if(path.startsWith('/imports/')&&path.endsWith('/commit')){need(actor().isAdmin,'仅协调人可导入');const plan=plans.get(path.split('/')[2]);need(plan,'预览已失效，请重新预览');for(const value of plan.items){const parent=createCase(value);if(plan.historical){parent.historicalArchive=true;parent.history={oldId:value.id,originalStatus:value.status,fields:copy(value)};parent.status='HISTORICAL';parent.lines.forEach((r:F)=>{r.lockOwnerId='';r.ownerId=''})}}plans.delete(path.split('/')[2]);persist();return {created:plan.items.length,items:plan.items}}
  if(path==='/cases'){
    if(method==='POST'){need(actor().isAdmin,'仅协调人可新建');return decorate(createCase(body))}
    let items=liveState.cases.map(decorate);if(params.search)items=items.filter((r:F)=>JSON.stringify(r).toLowerCase().includes(String(params.search).toLowerCase()));if(params.status)items=items.filter((r:F)=>r.status===params.status);if(params.supplierCode)items=items.filter((r:F)=>r.supplierCode.includes(params.supplierCode));if(params.businessCategory)items=items.filter((r:F)=>r.businessCategory===params.businessCategory);if(params.activeOnly)items=items.filter((r:F)=>r.status!=='CLOSED'&&!r.historicalArchive);if(params.scope==='mine'&&!actor().isAdmin)items=items.filter((r:F)=>r.lines.some((line:F)=>line.ownerId===actor().id||actor().id==='reviewer'&&line.status==='PENDING_REVIEW'||actor().id==='finance'&&line.finance.required));const page=Number(params.page||1),pageSize=Number(params.pageSize||20);return {items:items.slice((page-1)*pageSize,page*pageSize),pagination:{page,pageSize,total:items.length},summary:{cases:items.length,lines:items.reduce((n:number,r:F)=>n+r.lines.length,0),open:items.filter((r:F)=>r.status!=='CLOSED').length,overdue:0}}
  }
  const parts=path.split('/').filter(Boolean),parent=liveState.cases.find((r:F)=>r.id===decodeURIComponent(parts[1]||''));need(parent,'本机主单不存在')
  if(parts[2]==='copy')return decorate(createCase(body))
  if(parts.length===2){if(method==='PATCH'){checkVersion(parent,body);need(decorate(parent).allowedActions.includes('edit'),'主单当前不可编辑');patchFields(parent,body);record(parent,'edit',body)}return decorate(parent)}
  if(parts[2]==='closure-check')return closure(parent)
  if(parts[2]==='timeline')return copy(liveState.events.filter((r:F)=>r.caseId===parent.id).slice().reverse())
  if(parts[2]==='actions'){checkVersion(parent,body);applyAction(parent,undefined,body);return decorate(parent)}
  if(parts[2]==='attachments'){
    if(parts.length>3){const file=parent.attachments.find((r:F)=>r.id===decodeURIComponent(parts[3]||''));need(file,'附件不存在');if(file.dataUrl){const raw=atob(file.dataUrl.split(',')[1]);return new Blob([Uint8Array.from(raw,c=>c.charCodeAt(0))],{type:file.mime})}if(parts[4]==='preview')return new Blob([JSON.stringify({type:'text',text:file.text,truncated:false})],{type:'application/json'});return new Blob([file.text],{type:'text/plain'})}
    if(method==='GET')return copy(parent.attachments)
    const form=body as unknown as FormData,file=form.get('file') as File;checkVersion(parent,{version:Number(form.get('version'))});need(file&&file.size<=2*1024*1024,'单文件最多2MB');need(parent.attachments.reduce((n:number,r:F)=>n+(r.size||0),0)+file.size<=3*1024*1024,'本机原型附件累计最多3MB，请先导出备份');const bytes=new Uint8Array(await file.arrayBuffer());let bin='';for(let i=0;i<bytes.length;i+=8192)bin+=String.fromCharCode(...bytes.subarray(i,i+8192));const attachment={id:id(),name:file.name,category:String(form.get('category')),lineId:String(form.get('lineId')||''),mime:file.type||'application/octet-stream',size:file.size,createdAt:at(),sharedLineIds:[],dataUrl:`data:${file.type||'application/octet-stream'};base64,${btoa(bin)}`};parent.attachments.push(attachment);record(parent,'upload',{});return attachment
  }
  if(parts[2]==='lines'){
    checkVersion(parent,body)
    if(parts[3]==='bulk-assign'){const results=body.lineIds.map((key:string)=>{const line=parent.lines.find((r:F)=>r.id===key);try{need(line,'订单不存在');applyAction(parent,line,{...body,action:'assign'});return {lineId:key,status:'SAVED'}}catch(error){return {lineId:key,status:'FAILED',message:(error as Error).message}}});return {items:results,successCount:results.filter((r:F)=>r.status==='SAVED').length}}
    if(parts.length===3){need(decorate(parent).allowedActions.includes('addLine'),'当前不能新增明细');parent.lines.push(makeLine(body,parent));record(parent,'addLine',body);return decorate(parent)}
    const line=parent.lines.find((r:F)=>r.id===decodeURIComponent(parts[3]||''));need(line,'订单明细不存在')
    if(parts[4]==='actions')applyAction(parent,line,body)
    else {need(decorate(parent).lines.find((r:F)=>r.id===line.id).allowedActions.includes('edit'),'当前人员或状态不可编辑明细');patchFields(line,body);record(parent,'editLine',body,line)}
    return decorate(parent)
  }
  throw Error(`未适配的演示请求：${method} ${path}`)
}
function createCase(body:F):F {need(body.admNo?.trim()&&body.supplierName?.trim(),'ADM号与下发方必填');cents(body.originalAmount);need(!liveState.cases.some((r:F)=>r.admNo===body.admNo.trim()&&r.supplierName===body.supplierName.trim()),'同下发方同ADM号已存在');const parent:F={id:id(),admNo:body.admNo.trim(),supplierName:body.supplierName.trim(),currency:body.currency,originalAmount:body.originalAmount,status:'DRAFT',version:1,partial:false,createdAt:at(),updatedAt:at(),coordinatorId:'coordinator',coordinatorName:'林协调',analysis:{},attachments:[],lines:[]};patchFields(parent,body);parent.lines=(body.lines||[]).map((r:F)=>makeLine(r,parent));liveState.cases.push(parent);record(parent,'create',body);return parent}
async function request<T=any>(method:string,url:string,body:F={},options:F={}):Promise<{data:T;headers:Record<string,string>}>{try{const value=await dispatch(method,url,body,options);if(value instanceof Blob)return {data:value as T,headers:{'content-type':value.type}};return {data:{success:true,data:copy(value)} as T,headers:{}}}catch(error){transportStatus.error=(error as Error).message;throw error}}
export const http={get:<T=any>(url:string,options:F={})=>request<T>('GET',url,{},options),post:<T=any>(url:string,body:F={})=>request<T>('POST',url,body),patch:<T=any>(url:string,body:F={})=>request<T>('PATCH',url,body),put:<T=any>(url:string,body:F={})=>request<T>('PUT',url,body)}
