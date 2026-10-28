// Module registration only; never import authenticated business views here.
export const modules = [
  { id: 'adm', name: 'ADM 管理', status: '0.3 连续工作区', description: '完整台账与同单连续办理，含导入、分派、申诉、审核、分次回款和联动PRD。', artifact: 'ADM产品验收台_DEMO_0.3.html', source: 'frontend/prototypes/adm-review', document: 'docs/product/modules/adm/README.md', next: '直接进入台账操作；右侧查看字段用途、编辑条件和按钮去向，有问题再反馈。' },
  { id: 'finance', name: '财务核对', status: '待接入', description: '尚未迁入正式页面或制作本地原型。', artifact: '', source: '', document: '', next: '确定评审范围，读取已有需求与页面后接入。' },
  { id: 'hr', name: 'HR 报表', status: '待接入', description: '尚未迁入正式页面或制作本地原型。', artifact: '', source: '', document: '', next: '确定评审范围，读取已有需求与页面后接入。' },
  { id: 'analysis', name: '业务分析', status: '待接入', description: '尚未迁入正式页面或制作本地原型。', artifact: '', source: '', document: '', next: '确定评审范围，读取已有需求与页面后接入。' },
  { id: 'governance', name: '资源治理', status: '待接入', description: '尚未迁入正式页面或制作本地原型。', artifact: '', source: '', document: '', next: '确定评审范围，读取已有需求与页面后接入。' },
] as const
export const requirementPrompts = [
  { id: 'people', title: '1. 谁在使用', hint: '有哪些岗位？各自每天做什么？哪些内容只能本人或主管看到？' },
  { id: 'pain', title: '2. 现在最难处理的事情', hint: '现在怎么做、哪里耗时或容易出错、希望改善成什么样。' },
  { id: 'information', title: '3. 需要查看和填写的信息', hint: 'ADM、订单、金额、PNR、附件、分析说明等。说明字段用途，拿不准可以写待讨论。' },
  { id: 'flow', title: '4. 一张单怎样走完', hint: '从收到ADM开始，谁接收、谁处理、交给谁、什么时候算完成？可以用箭头写。' },
  { id: 'exceptions', title: '5. 特殊情况', hint: '分错人、找不到订单、多个平台、出退改混合、申诉失败、退回或重开怎么处理？' },
  { id: 'reminders', title: '6. 提醒和分析', hint: '什么时候提醒谁？每天看哪些指标？排名怎样算公平，哪些等待不应归责个人？' },
  { id: 'examples', title: '7. 样例和完成标准', hint: '提供脱敏样例、现有表格或截图，并描述怎样操作才算满足需求。' },
  { id: 'questions', title: '8. 优先级与待确认', hint: '必须有、后续再做、可以取消；尚未达成一致的意见请保留。' },
] as const
export type Draft = { author: string; notes: Record<string, string> }
export const emptyDraft = (): Draft => ({ author: '', notes: Object.fromEntries(requirementPrompts.map(item => [item.id, ''])) })
export function parseDraft(raw: string): Draft {
  const value: unknown = JSON.parse(raw)
  if (!value || typeof value !== 'object') throw new Error('草稿结构不兼容')
  const draft = value as Partial<Draft>
  if (typeof draft.author !== 'string' || draft.author.length > 100 || !draft.notes || typeof draft.notes !== 'object') throw new Error('草稿字段不兼容')
  const result = emptyDraft()
  result.author = draft.author
  for (const item of requirementPrompts) {
    const text = draft.notes[item.id]
    if (typeof text !== 'string' || text.length > 20000) throw new Error('草稿内容不兼容')
    result.notes[item.id] = text
  }
  return result
}
export function requirementText(draft: Draft) {
  return ['ADM管理需求收集（业务原始输入，待整理与确认）', `整理人：${draft.author || '未填写'}`, '',
    ...requirementPrompts.flatMap(item => [item.title, draft.notes[item.id]?.trim() || '待补充', '']),
    '备注：本文件不代表需求已批准或正式开发获批。'].join('\r\n')
}
