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
  { id: 'settings', title: '系统设置', children: [
    { id: 'settings', title: '业务规则设置' }, { id: 'exchange', title: '导入导出' },
    { id: 'history', title: '历史档案' },
  ] },
]
export const navigationEntry = (key: string) => navigationGroups.flatMap(group => group.children.map(child => ({ ...child, group: group.id, parent: group.title }))).find(child => child.id === key)
export const caseDestinations: Record<string, { tab: string; doc?: string; hint: string }> = {
  'case:detail': { tab:'detail', hint:'选定订单后接收、填写处理意见并提交下一节点。' },
  'case:attachments': { tab:'attachments', doc:'attachments', hint:'查看本单原件和明细证据，按获权范围补充材料。' },
  'case:close': { tab:'close', doc:'close', hint:'协调人核对全部明细后结案；整改和回款继续独立跟踪。' },
  'case:history': { tab:'history', doc:'overview', hint:'查看这张单的操作人、变更、依据和时间。' },
  'case:transfer': { tab:'detail', doc:'transfer', hint:'当前承办点击“发起确认式转交”；接收人在同单接受或驳回。确认前原人负责。' },
  'case:collab': { tab:'detail', doc:'investigate', hint:'主承办调查中可“创建协办任务”；下方“协办任务”区显示接收、提交和独立复核。' },
  'case:difference': { tab:'detail', doc:'difference', hint:'不申诉时在“提交处理 / 审核”里填写差异依据；申诉失败进入差异阶段后点击“登记差异并提交审核”。' },
}
