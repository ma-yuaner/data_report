import { seed, id, tasks, cents, cash, transition, type SimState, type Case } from './model'
import { prepareIntake, specificTypes } from './intake'

export const defaultRules = () => ({
  lead: 'lead',
  platformA: 'handlerA',
  platformB: 'handlerB',
  warningHours: 24,
  channel: '企业微信',
  types: specificTypes.map((name, index) => ({ name, code: `DEMO-${index + 1}` })),
  suppliers: [{ name: '合成供应商 · 非真实业务', currency: 'CNY', rate: '1' }],
  rates: [
    { currency: 'HKD', rate: '0.92' },
    { currency: 'USD', rate: '7.10' },
    { currency: 'JPY', rate: '0.047' },
    { currency: 'EUR', rate: '7.70' },
  ],
})
export function workspaceSeed(): SimState {
  const state = seed('normal')
  state.scenario = 'workspace'
  state.rules = defaultRules()
  const make = (source: string, no: string, stage?: string) => {
    const item = seed(source).cases[0]!
    const old = item.id
    item.id = `case-${no}`
    item.admNo = `DEMO-ADM-${no}`
    item.currency = 'CNY'
    item.sourceType = '供应商'
    item.airline = 'XX'
    item.issuedOn = '2026-10-28'
    item.replyDue = '2026-11-05'
    item.lines.forEach((line, index) => {
      const oldLine = line.id,
        newLine = `${item.id}-line-${index + 1}`
      const map = new Map(
        item.files.filter((file) => file.lineId === oldLine).map((file) => [file.id, `${item.id}-${file.id}`]),
      )
      item.files
        .filter((file) => file.lineId === oldLine)
        .forEach((file) => {
          file.lineId = newLine
          file.id = map.get(file.id)!
        })
      line.id = newLine
      line.orderNo = `SYN-${no}-${index + 1}`
      line.evidence = line.evidence.map((key) => map.get(key) || key)
      if (stage) line.stage = stage as typeof line.stage
    })
    item.files
      .filter((file) => !file.lineId)
      .forEach((file) => {
        file.id = `${item.id}-${file.id}`
      })
    if (old && item.closedSnapshots)
      item.closedSnapshots = [{ at: state.clock, amount: item.amount, lines: JSON.parse(JSON.stringify(item.lines)) }]
    return item
  }
  const ordinary = make('simple', '101')
  ordinary.description = '供应要求核实重复预定，完成处理后提交独立审核。'
  const appeal = make('simple', '102', 'APPEAL')
  appeal.lines[0]!.appealDecision = '申诉'
  appeal.lines[0]!.conclusion = '已核对事实，向平台申请撤销处罚。'
  const recovery = make('simple', '103', 'INVESTIGATE')
  Object.assign(recovery.lines[0]!, {
    recoveryRequired: true,
    recoveryCode: 'DEMO-R03',
    recoveryDue: '2026-10-30T18:00',
    dueAt: '2026-10-30T18:00',
  })
  const review = make('simple', '104', 'REVIEW')
  Object.assign(review.lines[0]!, {
    conclusion: '合成示例：已核对并完成差异登记，待审核。',
    diffType: '重复预定',
    appealReason: '核实成立，不申诉',
    differenceRecorded: true,
    differenceReason: 'DEMO-DIFF-104',
    financeReason: '无回款事项',
  })
  const finance = make('cashflow', '105')
  finance.lines[0]!.expectedRefund = finance.lines[0]!.amount
  const pre = make('simple', '106')
  pre.preliminary = true
  pre.description = '预罚核实：待补正式ADM和关联订单信息。'
  pre.lines[0]!.owner = 'lead'
  const multi = make('normal', '107')
  multi.lines.forEach((line) => {
    line.owner = 'lead'
    line.supervisor = 'lead'
  })
  state.cases = [ordinary, appeal, recovery, review, finance, pre, multi]
  state.notices = tasks(state).map((task) => ({
    id: id(),
    recipient: task.owner,
    caseId: task.caseId,
    lineId: task.lineId,
    text: `[本地通知] ${task.title}`,
    read: false,
  }))
  return state
}
export function recordWorkspace(
  state: SimState,
  actor: string,
  caseId: string,
  action: string,
  reason: string,
  lineId = '',
) {
  state.version++
  state.events.push({
    id: id(),
    at: state.clock,
    caseId,
    lineId,
    actor,
    action,
    reason,
    before: '修改前',
    after: '已保存',
    round: 1,
  })
}
export function canEditCase(item: Case, actor: string) {
  return (
    actor === 'coordinator' &&
    !item.historyOnly &&
    item.status === 'ACTIVE' &&
    !item.paused &&
    item.lines.every(
      (line) =>
        ['MATCH', 'ASSIGN', 'ACCEPT', 'INVESTIGATE'].includes(line.stage) &&
        !line.transfer &&
        (!line.lockedBy || line.lockedBy === actor),
    )
  )
}
// CSV supports quoted commas, quotes and multiline values. The same writer creates the template and exports.
export function readCsv(text: string): string[][] {
  const result: string[][] = []
  let row: string[] = [],
    cell = '',
    quote = false
  const input = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n')
  for (let i = 0; i < input.length; i++) {
    const c = input[i]
    if (c === '"') {
      if (quote && input[i + 1] === '"') {
        cell += '"'
        i++
      } else quote = !quote
    } else if (c === ',' && !quote) {
      row.push(cell)
      cell = ''
    } else if (c === '\n' && !quote) {
      row.push(cell)
      if (row.some(Boolean)) result.push(row)
      row = []
      cell = ''
    } else cell += c
  }
  if (quote) throw Error('CSV引号未闭合，请检查文件')
  row.push(cell)
  if (row.some(Boolean)) result.push(row)
  return result
}
export const writeCsv = (rows: unknown[][]) =>
  rows
    .map((row) =>
      row
        .map((value) => {
          const raw = String(value ?? '')
          const safe = /^[=+@\-\t\r]/.test(raw) ? `'${raw}` : raw
          return `"${safe.replace(/"/g, '""')}"`
        })
        .join(','),
    )
    .join('\r\n')
export const importHeaders = [
  'ADM号',
  '供应商',
  '来源主体',
  '航司',
  '下发日期',
  '回复截止',
  '币种',
  '主单金额',
  'ADM内容',
  '错误类型',
  '备注',
  '订单号',
  '票号',
  '平台',
  '业务',
  '子项金额',
  'PNR',
]
export const templateCsv = () =>
  writeCsv([
    importHeaders,
    [
      'DEMO-NEW-201',
      '合成供应商',
      '供应商',
      'XX',
      '2026-10-28',
      '2026-11-05',
      'CNY',
      '600.00',
      '核实重复预定',
      '重复预定',
      '样例备注',
      'SYN-201',
      '',
      '平台A',
      '出票',
      '600.00',
      'DEMO01',
    ],
  ])
export function previewCsv(input: string, state: SimState, mode: string) {
  const rows = readCsv(input)
  const headers = rows.shift()
  if (!headers || importHeaders.some((key) => !headers.includes(key))) throw Error('表头不完整，请先下载统一CSV模板')
  if (!rows.length || rows.length > 200) throw Error('本地原型每次1–200行')
  const grouped = new Map<string, { data: Record<string, string>; rows: string[][]; numbers: number[] }>()
  const errors: string[] = []
  rows.forEach((row, index) => {
    const data = Object.fromEntries(headers.map((key, i) => [key, row[i] || '']))
    const key = `${data['供应商']}\u0000${data['ADM号']}`
    if (!grouped.has(key)) grouped.set(key, { data, rows: [], numbers: [] })
    const group = grouped.get(key)!
    if (importHeaders.slice(0, 11).some((field) => data[field] !== group.data[field]))
      errors.push(`第${index + 2}行：同一ADM主单信息不一致`)
    group.rows.push(['订单号', '平台', '业务', '子项金额', 'PNR', '票号'].map((field) => data[field] || ''))
    group.numbers.push(index + 2)
  })
  const cases: Case[] = []
  for (const group of grouped.values()) {
    try {
      const d = group.data
      const item = prepareIntake(
        {
          admNo: d['ADM号'],
          supplier: d['供应商'],
          sourceType: d['来源主体'],
          airline: d['航司'],
          issuedOn: d['下发日期'],
          replyDue: d['回复截止'],
          currency: d['币种'],
          amount: d['主单金额'],
          description: d['ADM内容'],
          diffType: d['错误类型'],
          remark: d['备注'],
          rows: group.rows.map((row) => row.join(',')).join('\n'),
          preliminary: false,
        },
        state.rules?.types.map((type) => type.name),
      )
      const existing = state.cases.find((value) => value.admNo === item.admNo && value.supplier === item.supplier)
      if (existing && (mode !== 'update' || !canEditCase(existing, 'coordinator')))
        throw Error(
          existing.historyOnly
            ? '历史只读档案不能覆盖'
            : mode === 'update'
              ? '已有单状态或编辑锁不允许更新'
              : '已有同供应商同ADM；选择更新模式或修改编号',
        )
      cases.push(item)
    } catch (error) {
      errors.push(`第${group.numbers.join('、')}行：${(error as Error).message}`)
    }
  }
  return { cases, errors, rows: rows.length }
}
export function applyCsv(state: SimState, actor: string, input: string, mode: string, overwrite: boolean) {
  if (actor !== 'coordinator') throw Error('仅协调人可导入')
  const plan = previewCsv(input, state, mode)
  if (plan.errors.length) throw Error(plan.errors.join('；'))
  const next: SimState = JSON.parse(JSON.stringify(state))
  for (const item of plan.cases) {
    const old = next.cases.find((value) => value.admNo === item.admNo && value.supplier === item.supplier)
    if (old) {
      // Existing workflow, attachments, analysis and IDs are retained; import is not a way to reset approvals.
      if (
        old.lines.length !== item.lines.length ||
        old.lines.some(
          (line, i) =>
            line.orderNo !== item.lines[i]?.orderNo ||
            line.platform !== item.lines[i]?.platform ||
            line.business !== item.lines[i]?.business,
        )
      )
        throw Error(`${item.admNo}：更新不允许替换订单结构，请在单据内核对`)
      old.description = item.description
      old.remark = overwrite ? item.remark : old.remark
      if (old.currency && old.currency !== item.currency) throw Error(`${item.admNo}：已有单不支持通过导入改变币种`)
      for (const key of ['airline', 'issuedOn', 'replyDue', 'sourceType', 'amount'] as const)
        (old as any)[key] = item[key]
      old.lines.forEach((line, i) => {
        const source = item.lines[i]!
        line.amount = source.amount
        line.ticketNo = source.ticketNo
        line.pnr = source.pnr
        line.diffType = source.diffType
      })
      recordWorkspace(next, actor, old.id, 'import', 'CSV更新基础信息；处理结果/附件/负责人保留')
    } else {
      item.lines.forEach((line) => {
        line.owner = next.rules?.lead || 'lead'
      })
      next.cases.push(item)
      recordWorkspace(next, actor, item.id, 'import', 'CSV新建')
      tasks(next)
        .filter((task) => task.caseId === item.id)
        .forEach((task) =>
          next.notices.push({
            id: id(),
            recipient: task.owner,
            caseId: task.caseId,
            lineId: task.lineId,
            text: `[本地通知] ${task.title}`,
            read: false,
          }),
        )
    }
  }
  return next
}
export function exportCases(
  cases: Case[],
  actor: string,
  scope: (item: Case) => Case['lines'],
  difference = false,
  types: { name: string; code: string }[] = [],
) {
  const rows: unknown[][] = [
    difference
      ? ['ADM号', '订单号', '平台', '类型', '外部代码', '已登记', '差异依据', '币种', '承担金额', '备注']
      : importHeaders,
  ]
  for (const item of cases)
    for (const line of scope(item))
      rows.push(
        difference
          ? [
              item.admNo,
              line.orderNo,
              line.platform,
              line.diffType,
              types.find((type) => type.name === line.diffType)?.code || '待映射',
              line.differenceRecorded ? '是' : '否',
              line.differenceReason,
              item.currency || 'CNY',
              line.borneAmount || '',
              line.remark,
            ]
          : [
              item.admNo,
              item.supplier,
              item.sourceType || '',
              item.airline || '',
              item.issuedOn || '',
              item.replyDue || '',
              item.currency || 'CNY',
              actor === 'coordinator' ? item.amount : '',
              item.description,
              line.diffType,
              actor === 'coordinator' ? item.remark : line.remark,
              line.orderNo,
              line.ticketNo,
              line.platform,
              line.business,
              line.amount,
              line.pnr,
            ],
      )
  return writeCsv(rows)
}
export function batchAction(
  source: SimState,
  actor: string,
  cases: string[],
  action: string,
  owner: string,
  reason: string,
) {
  if (actor !== 'coordinator') throw Error('仅协调人可批量处理')
  if (!reason.trim()) throw Error('请填写批量操作依据')
  let state: SimState = JSON.parse(JSON.stringify(source))
  const results: string[] = []
  for (const caseId of cases)
    for (const line of state.cases.find((item) => item.id === caseId)?.lines || []) {
      try {
        state = transition(state, actor, caseId, line.id, action, { owner, reason }, state.version)
        results.push(`${line.orderNo}：成功`)
      } catch (error) {
        results.push(`${line.orderNo}：${(error as Error).message}`)
      }
    }
  return { state, results }
}
