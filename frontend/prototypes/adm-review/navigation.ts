/** Review navigation is an index of prototype pages/windows, not a production menu contract. */
export const navigationGroups = [
  { id: 'work', title: '我的工作', children: [
    { id: 'work', title: '本人待办' }, { id: 'notifications', title: '通知与回执' },
  ] },
  { id: 'adm', title: 'ADM管理', children: [
    { id: 'ledger', title: 'ADM台账' }, { id: 'intake', title: '录入与核实' },
    { id: 'case:detail', title: '订单处理' }, { id: 'case:attachments', title: '原件与附件' },
    { id: 'case:close', title: '结案与整改' }, { id: 'case:history', title: '操作历史' },
  ] },
  { id: 'team', title: '团队管理', children: [
    { id: 'dispatch', title: '分派与督办' }, { id: 'case:transfer', title: '任务交接' },
    { id: 'case:collab', title: '协办任务' },
  ] },
  { id: 'processing', title: '专项处理', children: [
    { id: 'recovery', title: '恢复编码' }, { id: 'appeals', title: '申诉跟进' },
    { id: 'case:difference', title: '差异登记' }, { id: 'reviewQueue', title: '独立审核' },
    { id: 'financeQueue', title: '回款跟进' },
  ] },
  { id: 'analysis', title: '统计分析', children: [{ id: 'report', title: '进度统计与日报' }] },
  { id: 'settings', title: 'ADM配置与资料', children: [
    { id: 'settings', title: 'ADM业务规则' }, { id: 'exchange', title: '导入导出' },
    { id: 'history', title: '历史档案' },
  ] },
]
export const navigationEntry = (key: string) => navigationGroups.flatMap(group => group.children.map(child => ({ ...child, group: group.id, parent: group.title }))).find(child => child.id === key)
export const integrationReuse = [
  { capability:'账号与权限', source:'系统管理 / 账号管理', approach:'复用现有账号、ADM菜单及功能权限；本原型人员切换仅模拟，不新增账号系统。', status:'已有公共入口，ADM新流程权限仍需正式接入。' },
  { capability:'通知发送与回执', source:'监控中心 / 通知管理', approach:'复用既有通知配置、日志与渠道能力；ADM事件/接收人需要适配，不另建通用通知后台。', status:'原型只生成本地通知，公共通知是否完整覆盖ADM待核对适配。' },
  { capability:'导出任务', source:'系统页头 / 导出任务', approach:'正式接入既有导出任务、队列和抽屉；原型CSV仅模拟内容与交接，不是另一套正式导出服务。', status:'全局能力已存在；原型未连真实队列。' },
  { capability:'分派、错误类型与差异代码', source:'ADM管理 / ADM业务规则（评审索引）', approach:'只保存ADM专属映射和分派条件；人员来自现有账号，字典来源先核对可复用项。', status:'业务配置有必要；最终正式入口和表结构待批准，不新增一级系统设置。' },
  { capability:'参考汇率与供应默认值', source:'ADM录入 / 本机演示参数', approach:'正式优先复用已确认的供应档案与汇率源；未找到契约前保留手工参考，不重复建设公共主数据。', status:'本机演示值，不声称已有实时接口。' },
]
export const caseDestinations: Record<string, { tab: string; doc?: string; hint: string }> = {
  'case:detail': { tab:'detail', hint:'选定订单后接收、填写处理意见并提交下一节点。' },
  'case:attachments': { tab:'attachments', doc:'attachments', hint:'查看本单原件和明细证据，按获权范围补充材料。' },
  'case:close': { tab:'close', doc:'close', hint:'协调人核对全部明细后结案；整改和回款继续独立跟踪。' },
  'case:history': { tab:'history', doc:'overview', hint:'查看这张单的操作人、变更、依据和时间。' },
  'case:transfer': { tab:'detail', doc:'transfer', hint:'当前承办点击“发起确认式转交”；接收人在同单接受或驳回。确认前原人负责。' },
  'case:collab': { tab:'detail', doc:'investigate', hint:'主承办调查中可“创建协办任务”；下方“协办任务”区显示接收、提交和独立复核。' },
  'case:difference': { tab:'detail', doc:'difference', hint:'不申诉时在“提交处理 / 审核”里填写差异依据；申诉失败进入差异阶段后点击“登记差异并提交审核”。' },
}
