// Module registration only; never import authenticated business views here.
import { systemMenus } from '../adm-review/system-navigation'
export const modules = systemMenus.map(menu => ({
  id: menu.id, name: menu.title,
  status: menu.id === 'governance' ? '0.2 需求与设计联动' : menu.id === 'adm' ? '0.4 原页面动态交互' : '原系统已有菜单 · 原型待接入',
  description: menu.id === 'governance' ? '复用原系统布局；六个原菜单、组件PRD、需求来源、字段与接口表设计索引。' : menu.id === 'adm' ? '直接复用正式ADM页面，弹窗抽屉真实联动，点击组件定位PRD。' : '保留正式系统的菜单名称和位置；此模块本轮未制作可操作原型。',
  artifact: menu.id === 'governance' ? '资源治理原页面评审_DEMO_0.2.html' : menu.id === 'adm' ? 'ADM产品验收台_DEMO_0.4.html' : '',
  source: menu.id === 'adm' ? 'frontend/prototypes/adm-review' : 'frontend/src/layouts/AppLayout.vue',
  document: menu.id === 'governance' ? 'docs/product/modules/resource-governance/README.md' : menu.id === 'adm' ? 'docs/product/modules/adm/README.md' : 'README.md',
  next: menu.id === 'governance' ? '从资源治理→GDS资源治理开始；新需求可以继续提供。' : menu.id === 'adm' ? '打开原型，先从ADM管理→我的工作台开始。' : '新增或调整前先核对原页面、权限及公共能力，避免独立重复开发。',
}))
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
