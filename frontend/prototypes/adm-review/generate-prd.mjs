import { writeFile } from 'node:fs/promises'
import { fieldGroups, actionSpecs } from './product-spec.ts'

const names = { intake:'录入与主单信息', match:'订单与匹配', investigate:'处理意见与差异', recovery:'恢复编码', appeal:'申诉跟进', review:'独立审核', finance:'财务回款', assign:'分派、交接、协办与办理锁', attachments:'附件与证据', close:'结案、重开与整改', exchange:'导入导出与历史档案', settings:'规则配置', notifications:'通知与回执', report:'统计与日报' }
const intro = ['# ADM管理原型与PRD 0.3', '', '更新：2026-10-28。状态：前端可操作原型，供业务直接使用并反馈；不是正式服务端或部署完成。', '',
  '本轮按用户要求优先完整功能和连续操作，把分散场景归并为同一个工作区。默认打开台账，多种状态样例同时存在；不需要重置场景即可录入、分派、处理、申诉、审核、结案和回款。评审记录保留在辅助入口。', '',
  '左侧为可操作原型，右侧跟随页面/步骤显示功能、逐字段定义、按钮条件和跳转。窗口内同步显示当前动作的前置条件与完成结果。', '',
  '## 页面与完整办理路径', '',
  '| 页面 | 功能与去向 |', '| --- | --- |',
  '| 我的工作 / 团队督办 | 查看到人任务、期限、交接和协办；点开进入同一张单。组长保留本组督办。 |',
  '| ADM台账 | 搜索、按阶段/平台/下发日期筛选、勾选主单、批量分派/解锁、导出台账或差异交接CSV。 |',
  '| 录入与核实 | 主单与多票号子项、人工确认拆分、本地候选识别、单币种分摊、参考换算、查重、复制、新建预览。预罚可先无订单，转正式补齐。 |',
  '| 单据详情 | 同单切换订单处理、原件附件、结案整改和操作历史；基础信息审核前可编辑并留痕。 |',
  '| 恢复编码 / 申诉跟进 | 集中列表打开原单，记录恢复期限和佐证，或按对象/轮次登记申诉；不另建互不关联的演示。 |',
  '| 审核 / 回款 | 审核通过或退回原承办；审核后按需生成财务待办，支持部分及多次回款。业务结案后继续追踪。 |',
  '| 通知与回执 | 按本人显示、标已读、打开对应任务、登记外部收到回执、生成到期提醒；不对外发送。 |',
  '| 统计与日报 | 当前范围主单/明细、逾期、人员积压排序、原币汇总及可读日报下载；不作为正式绩效考核。 |',
  '| 导入导出 / 历史档案 | 统一CSV模板，先预览后确认，基础更新保留结果与备注；历史约定JSON只读试导、重复源ID跳过、可复制引用。 |',
  '| 规则设置 | 本机维护分派、类型代码、供应默认币种、参考汇率和预警参数。只影响后续新单和匹配，不追溯重派。 |', '',
  '主流程：录入预览→组长接收/转交→承办接收→同单填写处理意见→申诉或不申诉差异依据→独立审核→协调人整单结案。回款与结案后整改分别继续。审核退回原承办，转交未确认前原人继续负责，期限不重置。', '',
  '## 需求覆盖', '',
  '| 原始需求 | 本版前端对应功能 |', '| --- | --- |',
  '| R001/R005/R017 | 到人任务、组长再分派/督办、确认式交接、站内模拟通知与外部回执记录 |',
  '| R002/R004/R010/R016 | 主单多订单、多票号、出退改/平台/PNR、基础信息编辑、候选识别与人民币参考值 |',
  '| R003/R009 | 复制引用、重复提醒、审核前编辑、办理锁、批量解锁/分派与逐项结果 |',
  '| R006/R008 | 多对象多轮申诉、不申诉原因、差异依据、承担金额与独立审核 |',
  '| R007/R018 | 本机文件上传/预览/下载/授权，恢复编码、截止、完成时间与佐证 |',
  '| R011/R013 | 统一CSV导入导出、备注保留、外部代码映射、只读历史JSON试导 |',
  '| R012/R014 | 连续工作区、统计/日报/积压排序，辅助评审入口 |',
  '| R015/R019 | 独立回款、部分多次到账、预罚核实与转正式 |', '',
  '## 功能与字段说明', '']
const lines = [...intro]
for (const [key, fields] of Object.entries(fieldGroups)) {
  lines.push(`### ${names[key] || key}`, '', '| 字段 | 含义与用途 | 来源/默认 | 编辑条件 | 必填、校验与影响 |', '| --- | --- | --- | --- | --- |')
  for (const field of fields) lines.push(`| ${[field.name,field.meaning,field.source,field.edit,field.rule].map(value=>value.replaceAll('|','／')).join(' | ')} |`)
  lines.push('')
}
lines.push('## 按钮条件与页面流转', '', '| 操作 | 何时可用 | 点击后结果和去向 |', '| --- | --- | --- |')
for (const action of Object.values(actionSpecs)) lines.push(`| ${action.name} | ${action.when} | ${action.result} |`)
lines.push('', '导航和“切换下一处理人”只更换视图/模拟身份，不替用户提交、审核或结案。操作失败保留弹窗草稿，成功更新任务和留痕；有未保存内容关闭时提示。', '',
  '## 当前实现边界与待定规则', '',
  '- 所有状态、权限、通知和金额操作均为本机模拟，不调用正式订单、差异、财务、邮件、企微、GDS或生产数据库。',
  '- 票号/订单识别只从当前本地样例查候选，未命中或多匹配保留人工核对；参考汇率为本地手工值，不是实时接口。',
  '- 本机附件支持图片、PDF、文本预览及其他格式下载，不解析Excel业务内容、不执行ASD自动归档或旧附件迁移。关闭浏览器后的保存依赖本机缓存容量；缓存失败时页面提示导出备份。',
  '- CSV为本版可操作统一模板；外部差异/财务正式模板、旧38/44列、Java/Python真实历史格式映射尚需正式契约。本版历史试导使用原型约定JSON，不冒充全量迁移。',
  '- 节点期限、恢复两天的日历与起点、等待扣时、通知对象/渠道、正式字典/外部代码、财务核对人和附件保留期限仍待业务确认。当前可操作建议不代表这些口径已批准。',
  '- 不实现超时自动拒单、自动删除附件、真实绩效处罚或生产旧入口停用；这些动作需独立确认规则和正式开发。',
  '- 批量改状态仅提供合法的分派/解锁动作，不提供绕过证据、审核或结案条件的任意状态覆盖。', '',
  '## 实现与维护', '',
  '原型入口：frontend/prototypes/adm-review；字段和按钮定义：product-spec.ts；本PRD及离线HTML由generate-prd.mjs生成，避免逐字段说明两边手写漂移。', '',
  '构建：在frontend执行 npm run package:product-review。生成工作区“产品评审台_打开我.html”和“产品评审台/ADM产品验收台_DEMO_0.3.html”。', '')
const markdown=lines.join('\n')
await writeFile(new URL('../../../docs/product/modules/adm/prototype-prd-v03.md',import.meta.url),markdown,'utf8')
const escape=(value)=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')
const body=lines.map(line=>line.startsWith('### ')?`<h3>${escape(line.slice(4))}</h3>`:line.startsWith('## ')?`<h2>${escape(line.slice(3))}</h2>`:line.startsWith('# ')?`<h1>${escape(line.slice(2))}</h1>`:line.startsWith('| ---')?'':line.startsWith('| ')?`<div class="row">${line.split('|').slice(1,-1).map(cell=>`<span>${escape(cell.trim())}</span>`).join('')}</div>`:`<p>${escape(line)}</p>`).join('\n')
await writeFile(new URL('./PRD_0.3.html',import.meta.url),`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ADM原型PRD 0.3</title><style>body{font:15px/1.9 system-ui,'Microsoft YaHei';color:#182235;background:#f2f5f9;margin:0}main{max-width:1320px;background:white;padding:32px;margin:auto}h1{font-size:27px}h2{margin-top:36px}.row{display:flex;border-bottom:1px solid #dbe3ee;overflow-wrap:anywhere}.row span{flex:1;padding:10px;min-width:0}.row span:first-child{flex:0.65;font-weight:600}@media(max-width:700px){main{padding:16px}.row{display:block}.row span{display:block;padding:6px}}</style><main>${body}</main></html>`,'utf8')
console.log(`Generated ADM PRD 0.3: ${Object.values(fieldGroups).flat().length} field definitions, ${Object.keys(actionSpecs).length} action definitions.`)
