/** Product simulation only. No HTTP, production data, real delivery or authoritative accounting. */
export const roles = [
  { id: 'lead', name: '组长 · 分派与督办（模拟）', purpose: '接收初派任务、再分配并查看本组进度' },
  { id: 'coordinator', name: '林协调 · 接收与调度', purpose: '接收、分派异常、调度和整单结案' },
  { id: 'handlerA', name: '陈承办 · 平台A', purpose: '只办理分给自己的订单与协办' },
  { id: 'handlerB', name: '周承办 · 平台B', purpose: '只办理分给自己的订单与协办' },
  { id: 'reviewer', name: '许审核 · 独立复核', purpose: '复核证据、结论和责任提案' },
  { id: 'finance', name: '何财务 · 财务确认', purpose: '核对凭证，不把申诉成功当到账' },
]
export const roleName = (id: string) => roles.find((item) => item.id === id)?.name || '未指定'
export type Stage =
  'MATCH' | 'ASSIGN' | 'ACCEPT' | 'INVESTIGATE' | 'APPEAL' | 'DIFFERENCE' | 'REVIEW' | 'FINANCE' | 'DONE'
export const stageNames: Record<Stage, string> = {
  MATCH: '待核实归属',
  ASSIGN: '待指定负责人',
  ACCEPT: '待接单',
  INVESTIGATE: '调查取证',
  APPEAL: '申诉与跟进',
  DIFFERENCE: '差异登记',
  REVIEW: '待独立审核',
  FINANCE: '待财务确认',
  DONE: '明细完成',
}
export const stageNode: Record<Stage, string> = {
  MATCH: 'match',
  ASSIGN: 'assign',
  ACCEPT: 'accept',
  INVESTIGATE: 'investigate',
  APPEAL: 'appeal',
  DIFFERENCE: 'difference',
  REVIEW: 'review',
  FINANCE: 'finance',
  DONE: 'close',
}
export interface Evidence {
  id: string
  name: string
  category: string
  lineId: string
  shared: string[]
  content: string
  redactedFrom?: string
  dataUrl?: string
  mime?: string
  size?: number
}
export interface Collaboration {
  id: string
  title: string
  owner: string
  required: boolean
  status: 'TODO' | 'ACTIVE' | 'REVIEW' | 'DONE'
  result: string
  evidence: string[]
}
export interface Appeal {
  id: string
  target: string
  status: string
  result: string
  evidence: string[]
  round: number
}
export interface Line {
  id: string
  orderNo: string
  ticketNo: string
  pnr: string
  platform: string
  site: string
  business: string
  amount: string
  stage: Stage
  owner: string
  supervisor?: string
  borneAmount?: string
  expectedRefund?: string
  payments?: { id: string; reference: string; amount: string; at: string; reason: string; evidence: string[] }[]
  recoveryDue?: string
  recoveryCompletedAt?: string
  lockedBy?: string
  dueAt: string
  matchReason: string
  description: string
  facts: string
  cause: string
  proposal: string
  conclusion: string
  remark: string
  diffType: string
  diffSecond: string
  attribution: string
  responsibilityStatus: string
  responsiblePerson: string
  responsibilityProposer: string
  appealDecision: string
  appealReason: string
  appeals: Appeal[]
  differenceRecorded: boolean
  differenceReason: string
  recoveryRequired: boolean
  recoveryCode: string
  recoveryResult: string
  financeRequired: boolean
  financeReason: string
  financeReference: string
  settledAmount: string
  evidence: string[]
  collaborations: Collaboration[]
  transfer?: { to: string; reason: string }
  waitingFor: string
  followUpAt: string
  round: number
}
export interface Case {
  id: string
  admNo: string
  supplier: string
  sourceType?: string
  currency?: string
  airline?: string
  issuedOn?: string
  replyDue?: string
  referenceCny?: string
  preliminary?: boolean
  historyOnly?: boolean
  historySource?: Record<string, unknown>
  amount: string
  description: string
  remark: string
  status: 'DRAFT' | 'ACTIVE' | 'CLOSED' | 'VOID'
  paused: boolean
  lines: Line[]
  files: Evidence[]
  remediation: { owner: string; status: string; result: string; evidence?: string[] }
  source: string
  closedSnapshots?: { at: string; amount: string; lines: Line[] }[]
}
export interface Event {
  id: string
  at: string
  caseId: string
  lineId: string
  actor: string
  action: string
  reason: string
  before: string
  after: string
  round: number
}
export interface SimState {
  schema: number
  version: number
  clock: string
  scenario: string
  cases: Case[]
  events: Event[]
  notices: { id: string; recipient: string; caseId: string; lineId: string; text: string; read: boolean }[]
  rules?: {
    lead: string
    platformA: string
    platformB: string
    warningHours: number
    channel: string
    types: { name: string; code: string }[]
    suppliers: { name: string; currency: string; rate: string }[]
    rates: { currency: string; rate: string }[]
  }
}
export interface Task {
  id: string
  caseId: string
  lineId: string
  kind: string
  title: string
  owner: string
  node: string
  dueAt: string
  why: string
  overdue: boolean
}
let serial = 0
export const id = () => `demo-${Date.now()}-${++serial}`
export function cents(value: unknown): number {
  const match = /^(0|[1-9]\d{0,8})(?:\.(\d{1,2}))?$/.exec(String(value))
  if (!match) throw new Error('金额须为非负数、最多两位小数且不超过999999999.99')
  return Number(match[1]) * 100 + Number((match[2] || '').padEnd(2, '0'))
}
export const cash = (value: number) => `${Math.floor(value / 100)}.${String(value % 100).padStart(2, '0')}`
export const lineSeed = (index: number): Line => ({
  id: `line-${index}`,
  orderNo: `SYN-202610-${index}`,
  ticketNo: `999-000000000${index}`,
  pnr: `DEMO0${index}`,
  platform: index === 2 ? '平台B' : '平台A',
  site: '华东站点',
  business: ['出票', '退票', '改签'][(index - 1) % 3]!,
  amount: ['600.00', '250.00', '150.00'][(index - 1) % 3]!,
  stage: 'INVESTIGATE',
  owner: index === 2 ? 'handlerB' : 'handlerA',
  supervisor: 'lead',
  dueAt: '2026-11-01T18:00',
  matchReason: '演练：订单号与票号一致',
  description: '供应下发差异，需要核对业务记录与证据',
  facts: '',
  cause: '',
  proposal: '',
  conclusion: '',
  remark: '',
  diffType: '票务差异',
  diffSecond: '规则理解',
  attribution: '待认定',
  responsibilityStatus: '未提案',
  responsiblePerson: '',
  responsibilityProposer: '',
  appealDecision: '不申诉',
  appealReason: '',
  appeals: [],
  differenceRecorded: false,
  differenceReason: '',
  recoveryRequired: false,
  recoveryCode: '',
  recoveryResult: '',
  financeRequired: false,
  financeReason: '',
  financeReference: '',
  settledAmount: '',
  evidence: [],
  collaborations: [],
  waitingFor: '',
  followUpAt: '',
  round: 1,
})
export function seed(scenario = 'simple'): SimState {
  const lines = [lineSeed(1), lineSeed(2), lineSeed(3)]
  const parent: Case = {
    id: 'case-demo-001',
    admNo: 'DEMO-ADM-001',
    supplier: '合成供应商 · 非真实业务',
    amount: '1000.00',
    description: '一张ADM包含两个平台、三个出退改订单；金额由业务逐项确认，不自动平均分摊。',
    remark: '所有人名与业务资料均为合成',
    status: 'ACTIVE',
    paused: false,
    lines,
    files: [],
    remediation: { owner: 'handlerB', status: '未开始', result: '' },
    source: '模拟供应下发',
  }
  lines.forEach((line) => {
    const proof: Evidence = {
      id: `proof-${line.id}`,
      name: `${line.orderNo}-演练证据.txt`,
      category: '调查证据',
      lineId: line.id,
      shared: [],
      content: `合成演练证据，非真实订单。\n订单 ${line.orderNo}\n业务 ${line.business}\n请核对事实、原因与处理建议。`,
    }
    parent.files.push(proof)
    line.evidence.push(proof.id)
  })
  parent.files.unshift({
    id: 'original-demo',
    name: '供应ADM原件-演练.txt',
    category: '下发原件',
    lineId: '',
    shared: [],
    content: '合成供应ADM原件，包含平台A、平台B三笔订单。仅协调人默认可读；需明确整份共享或上传脱敏副本。',
  })
  if (scenario === 'normal') {
    lines.forEach((line) => (line.stage = 'ACCEPT'))
    lines[0]!.appealDecision = '申诉'
    lines[0]!.financeRequired = true
  }
  if (scenario === 'simple') {
    parent.lines = [lines[0]!]
    parent.amount = lines[0]!.amount
    parent.description = '普通单：接收、填写处理意见、审核并结案。'
    parent.lines[0]!.stage = 'ACCEPT'
    parent.lines[0]!.diffType = '重复预定'
    parent.lines[0]!.diffSecond = ''
    parent.files = parent.files.filter((file) => !file.lineId || file.lineId === lines[0]!.id)
  }
  if (scenario === 'cashflow') {
    parent.lines = [lines[0]!]
    parent.amount = lines[0]!.amount
    parent.files = parent.files.filter((file) => !file.lineId || file.lineId === lines[0]!.id)
    parent.lines[0]!.stage = 'DONE'
    parent.lines[0]!.financeRequired = true
    parent.lines[0]!.conclusion = '合成演练：申诉成功，审核通过，等待退款到账。'
    parent.status = 'CLOSED'
    parent.closedSnapshots = [
      { at: '2026-10-28T14:00', amount: parent.amount, lines: JSON.parse(JSON.stringify(parent.lines)) },
    ]
  }
  if (scenario === 'exception') {
    lines[0]!.stage = 'MATCH'
    lines[0]!.owner = ''
    lines[0]!.orderNo = ''
    lines[0]!.matchReason = ''
    lines[1]!.stage = 'ASSIGN'
    lines[1]!.owner = ''
    parent.amount = '1100.00'
  }
  if (scenario === 'urgent') {
    lines[0]!.dueAt = '2026-10-26T12:00'
    lines[0]!.waitingFor = '供应商补充规则'
    lines[0]!.followUpAt = '2026-10-27T12:00'
    lines[1]!.transfer = { to: 'handlerA', reason: '演练：跨平台交接，原人负责直至接收' }
  }
  if (scenario === 'closed') {
    parent.status = 'CLOSED'
    lines.forEach((line) => {
      line.stage = 'DONE'
      line.facts = '演练历史事实'
      line.cause = '已核对'
      line.proposal = '已处理'
      line.conclusion = '本案例为结案后整改场景，非真实结案'
      line.appealReason = '演练无需申诉'
      line.differenceReason = '演练无需登记'
      line.financeReason = '演练无需财务'
    })
    parent.remediation.status = '待整改'
    parent.closedSnapshots = [
      { at: '2026-10-26T18:00', amount: parent.amount, lines: JSON.parse(JSON.stringify(lines)) },
    ]
  }
  const state: SimState = {
    schema: 2,
    version: 1,
    clock: '2026-10-28T15:00',
    scenario,
    cases: [parent],
    events: [],
    notices: [],
  }
  tasks(state).forEach((task) =>
    state.notices.push({
      id: id(),
      recipient: task.owner,
      caseId: task.caseId,
      lineId: task.lineId,
      text: `[企业微信模拟] ${task.title}`,
      read: false,
    }),
  )
  return state
}
export function visibleLines(item: Case, actor: string) {
  if (actor === 'coordinator') return item.lines
  return item.lines.filter(
    (line) =>
      line.owner === actor ||
      line.supervisor === actor ||
      line.transfer?.to === actor ||
      line.collaborations.some((task) => task.owner === actor) ||
      actor === 'reviewer' ||
      (actor === 'finance' && line.financeRequired),
  )
}
export const visibleFile = (item: Evidence, actor: string, lines: Line[]) =>
  actor === 'coordinator' || lines.some((line) => item.lineId === line.id || item.shared.includes(line.id))
export function tasks(state: SimState): Task[] {
  const result: Task[] = []
  const add = (
    item: Case,
    line: Line | undefined,
    kind: string,
    title: string,
    owner: string,
    node: string,
    dueAt: string,
    why: string,
    extra = '',
  ) =>
    result.push({
      id: `${item.id}:${line?.id || 'main'}:${kind}:${extra}`,
      caseId: item.id,
      lineId: line?.id || '',
      kind,
      title,
      owner,
      node,
      dueAt,
      why,
      overdue: !!dueAt && dueAt < state.clock,
    })
  state.cases.forEach((item) => {
    if (item.historyOnly || item.status === 'VOID' || item.status === 'DRAFT' || item.paused) return
    item.lines
      .filter((line) => line.stage === 'DONE' && line.financeRequired && !line.financeReference)
      .forEach((line) =>
        add(
          item,
          line,
          '回款',
          `确认回款 · ${line.orderNo}`,
          'finance',
          'finance',
          '',
          '业务已审核，回款独立跟进；缺少财务期限不视为按时完成',
        ),
      )
    if (item.status === 'CLOSED') {
      if (['待整改', '整改中', '待复核'].includes(item.remediation.status))
        add(
          item,
          undefined,
          '整改',
          item.remediation.status === '待复核' ? '独立复核整改结果' : '完成结案后的预防整改',
          item.remediation.status === '待复核' ? 'reviewer' : item.remediation.owner,
          'remediation',
          '',
          '结案保留，整改不篡改已核准的业务事实',
        )
      return
    }
    item.lines.forEach((line) => {
      if (line.recoveryRequired && !line.recoveryResult)
        add(
          item,
          line,
          '恢复编码',
          `恢复编码 · ${line.orderNo}`,
          line.owner,
          'recovery',
          line.recoveryDue || '',
          '独立恢复节点，完成须编码、结果与佐证；期限由人工填写',
        )
      if (line.stage !== 'DONE')
        add(
          item,
          line,
          line.stage,
          `${stageNames[line.stage]} · ${line.orderNo || '待匹配订单'}`,
          ['MATCH', 'ASSIGN'].includes(line.stage)
            ? 'coordinator'
            : line.stage === 'REVIEW'
              ? 'reviewer'
              : line.stage === 'FINANCE'
                ? 'finance'
                : line.owner,
          stageNode[line.stage],
          line.dueAt,
          line.owner
            ? '根据模拟平台分派规则或协调人确认生成；规则正式启用需业务批准'
            : '无法唯一匹配或负责人缺失，交协调人处理，不随机派人',
        )
      if (line.transfer)
        add(
          item,
          line,
          '交接',
          '确认转交：接受或驳回',
          line.transfer.to,
          'transfer',
          line.dueAt,
          '确认前原承办人继续负责，期限不重置',
        )
      if (line.waitingFor)
        add(
          item,
          line,
          '跟进',
          `跟进：${line.waitingFor}`,
          line.owner,
          'investigate',
          line.followUpAt,
          '登记等待不表示工作完成；跟进期限需要明确填写',
        )
      line.collaborations
        .filter((task) => task.status !== 'DONE')
        .forEach((task) =>
          add(
            item,
            line,
            '协办',
            `${task.status === 'REVIEW' ? '复核协办结果' : '办理协办'}：${task.title}`,
            task.status === 'REVIEW' ? (line.owner !== task.owner ? line.owner : 'coordinator') : task.owner,
            'investigate',
            line.dueAt,
            task.required ? '必需协办，完成前阻断明细推进' : '协办有独立交付结果，不替换主承办',
            task.id,
          ),
        )
    })
    if (item.lines.every((line) => line.stage === 'DONE'))
      add(
        item,
        undefined,
        '结案',
        '核对整单并结案',
        'coordinator',
        'close',
        '',
        '子订单完成不等于主单已结案，需核对原件、分摊和证据',
      )
  })
  return result.sort((a, b) => Number(b.overdue) - Number(a.overdue) || a.id.localeCompare(b.id))
}
type Body = Record<string, any>
const need = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message)
}
const text = (value: unknown, label: string, max = 4000) => {
  need(typeof value === 'string' && value.trim() && value.length <= max, `${label}必填，最多${max}字`)
  return String(value).trim()
}
function proof(item: Case, line: Line, ids: unknown): string[] {
  need(Array.isArray(ids) && ids.length, '请选择当前明细可读的证据')
  const values = ids as string[]
  need(
    values.every((value) =>
      item.files.some((file) => file.id === value && (file.lineId === line.id || file.shared.includes(line.id))),
    ),
    '证据无效或未授权到该明细',
  )
  return [...new Set(values)]
}
export function blockers(item: Case) {
  const result: string[] = []
  if (item.status !== 'ACTIVE' || item.paused) result.push('主单必须处于未挂起的办理状态')
  if (!item.files.some((file) => file.category === '下发原件')) result.push('缺少下发原件')
  if (item.lines.some((line) => line.stage !== 'DONE')) result.push('仍有未完成的子订单')
  if (item.lines.some((line) => line.transfer)) result.push('仍有待确认交接')
  if (item.lines.some((line) => line.collaborations.some((task) => task.required && task.status !== 'DONE')))
    result.push('必需协办未完成')
  try {
    if (item.lines.reduce((sum, line) => sum + cents(line.amount), 0) !== cents(item.amount))
      result.push('原币分摊不平；需调整明细或原件依据，不能自动凑数')
  } catch {
    result.push('金额格式无效')
  }
  return result
}
export function transition(
  source: SimState,
  actor: string,
  caseId: string,
  lineId: string,
  action: string,
  body: Body = {},
  expected = source.version,
): SimState {
  need(source.version === expected, '版本已变化，请关闭弹窗、核对最新记录后重试；输入草稿仍保留')
  const state: SimState = JSON.parse(JSON.stringify(source))
  const item = state.cases.find((item) => item.id === caseId)
  need(item, '主单不存在')
  const parent = item!
  need(!parent.historyOnly, '历史档案只读；可复制引用新建，不回写旧档案')
  const line = parent.lines.find((line) => line.id === lineId)
  const coordinator = () => need(actor === 'coordinator', '仅协调人可操作')
  const handle = () =>
    need(line && line.owner === actor && ['handlerA', 'handlerB', 'lead'].includes(actor), '仅当前主承办可操作')
  const stage = (...values: Stage[]) => need(line && values.includes(line.stage), '当前节点不允许此操作')
  const before = parent.status === 'CLOSED' ? '已结案' : line ? stageNames[line.stage] : parent.status
  if (
    line?.lockedBy &&
    line.lockedBy !== actor &&
    ![
      'unlock',
      'review',
      'finance',
      'responsibility_review',
      'transfer_accept',
      'transfer_reject',
      'remediation_review',
    ].includes(action)
  )
    need(false, `此明细由${roleName(line.lockedBy)}锁定，请先协调解锁`)
  if (parent.preliminary)
    need(
      !['submit', 'appeal', 'appeal_next', 'difference', 'review', 'finance', 'close'].includes(action),
      '预罚单请先核实并由协调人转正式，随后继续办理',
    )
  const closedAttachment =
    action === 'attach' &&
    parent.status === 'CLOSED' &&
    actor === parent.remediation.owner &&
    parent.remediation.status === '整改中'
  const closedFinance =
    action === 'finance' && parent.status === 'CLOSED' && line?.stage === 'DONE' && line.financeRequired
  if (
    !closedAttachment &&
    !closedFinance &&
    !['reopen', 'remediate', 'remediation_accept', 'remediation_review'].includes(action)
  ) {
    need(parent.status !== 'CLOSED', '已结案核心事实只读；可完成整改或授权重开')
    need(parent.status !== 'VOID', '作废主单只读')
    need(!parent.paused || action === 'resume', '主单已挂起，恢复后办理')
  }
  if (action === 'lock' || action === 'unlock') {
    need(line && (line.owner === actor || actor === 'coordinator'), '仅当前承办或协调人可管理办理锁')
    need(
      line && ['MATCH', 'ASSIGN', 'ACCEPT', 'INVESTIGATE', 'APPEAL', 'DIFFERENCE'].includes(line.stage),
      '审核后不可修改办理锁',
    )
    if (action === 'lock') {
      need(!line!.lockedBy || line!.lockedBy === actor, '已有他人持锁')
      line!.lockedBy = actor
    } else {
      text(body.reason, '解锁依据')
      line!.lockedBy = ''
    }
  } else if (action === 'edit' || action === 'preliminary') {
    coordinator()
    need(
      parent.status === 'ACTIVE' &&
        parent.lines.every(
          (value) =>
            ['MATCH', 'ASSIGN', 'ACCEPT', 'INVESTIGATE'].includes(value.stage) &&
            !value.transfer &&
            (!value.lockedBy || value.lockedBy === actor),
        ),
      '审核后、交接中或他人持锁时不允许更改基础信息',
    )
    need(action !== 'preliminary' || parent.preliminary, '当前已是正式ADM')
    parent.admNo = text(body.admNo, 'ADM号', 200)
    parent.supplier = text(body.supplier, '供应商', 200)
    need(
      !state.cases.some(
        (value) => value.id !== parent.id && value.admNo === parent.admNo && value.supplier === parent.supplier,
      ),
      '同供应商同ADM号已存在',
    )
    parent.description = text(body.description, 'ADM内容', 8000)
    parent.remark = String(body.remark || '')
    parent.airline = text(body.airline, '航司代码', 40)
    need(['航司', '供应商', '平台'].includes(body.sourceType), '来源主体无效')
    parent.sourceType = body.sourceType
    need(
      /^\d{4}-\d\d-\d\d$/.test(body.issuedOn) &&
        /^\d{4}-\d\d-\d\d$/.test(body.replyDue) &&
        body.replyDue >= body.issuedOn,
      '请核对下发日期和回复截止',
    )
    parent.issuedOn = body.issuedOn
    parent.replyDue = body.replyDue
    const entries = body.lines as Line[]
    need(Array.isArray(entries) && entries.length === parent.lines.length, '请保留原有订单结构')
    entries.forEach((entry, index) => {
      const target = parent.lines[index]!
      text(entry.orderNo, '订单号', 200)
      cents(entry.amount)
      need(
        ['平台A', '平台B'].includes(entry.platform) && ['出票', '退票', '改签'].includes(entry.business),
        '平台或业务无效',
      )
      for (const key of ['orderNo', 'ticketNo', 'platform', 'business', 'amount', 'pnr', 'site'] as const)
        target[key] = String(entry[key] || '')
    })
    const tickets = entries.flatMap((entry) =>
      String(entry.ticketNo || '')
        .split(/[;；、\s]+/)
        .filter(Boolean),
    )
    need(new Set(tickets).size === tickets.length, '票号重复，请核对子项')
    need(cents(body.amount) === parent.lines.reduce((sum, value) => sum + cents(value.amount), 0), '主单与子项金额不平')
    parent.amount = body.amount
    text(body.reason, '修改依据')
    if (action === 'preliminary') {
      parent.preliminary = false
      parent.lines.forEach((value) => {
        value.stage = 'ACCEPT'
        value.owner = state.rules?.lead || 'lead'
      })
    }
  } else if (action === 'recovery') {
    handle()
    stage('INVESTIGATE')
    line!.recoveryRequired = true
    line!.recoveryCode = text(body.recoveryCode, '恢复编码', 100)
    line!.recoveryDue = String(body.recoveryDue || '')
    need(!line!.recoveryDue || /^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(line!.recoveryDue), '恢复截止格式无效')
    line!.recoveryResult = String(body.recoveryResult || '')
    if (body.recoveryResult) {
      proof(parent, line!, body.evidence)
      line!.recoveryCompletedAt = state.clock
    } else line!.recoveryCompletedAt = ''
  } else if (action === 'publish') {
    coordinator()
    need(parent.status === 'DRAFT', '仅草稿可发布')
    need(parent.lines.length, '至少一条子订单')
    parent.status = 'ACTIVE'
  } else if (action === 'match') {
    coordinator()
    stage('MATCH')
    line!.orderNo = text(body.orderNo, '订单号', 100)
    line!.matchReason = text(body.reason, '核实依据')
    line!.platform = body.platform === '平台B' ? '平台B' : '平台A'
    line!.owner = body.autoAssign
      ? line!.platform === '平台B'
        ? state.rules?.platformB || 'handlerB'
        : state.rules?.platformA || 'handlerA'
      : ''
    line!.stage = line!.owner ? 'ACCEPT' : 'ASSIGN'
  } else if (action === 'assign') {
    coordinator()
    stage('ASSIGN', 'ACCEPT', 'INVESTIGATE')
    need(['handlerA', 'handlerB', 'lead'].includes(body.owner), '请选择获授权承办人')
    need(!line!.transfer, '先完成或取消已有交接')
    line!.owner = body.owner
    line!.stage = 'ACCEPT'
    text(body.reason, '分配原因')
  } else if (action === 'claim') {
    handle()
    stage('ACCEPT')
    line!.stage = 'INVESTIGATE'
  } else if (action === 'record' || action === 'submit') {
    handle()
    stage('INVESTIGATE')
    for (const key of [
      'description',
      'facts',
      'cause',
      'proposal',
      'conclusion',
      'remark',
      'diffType',
      'diffSecond',
      'attribution',
      'appealReason',
      'financeReason',
      'recoveryCode',
      'recoveryResult',
      'waitingFor',
      'followUpAt',
      'pnr',
      'site',
      'expectedRefund',
      'recoveryDue',
    ])
      if (key in body) (line as any)[key] = String(body[key] || '').slice(0, 8000)
    for (const key of ['recoveryRequired', 'financeRequired']) if (key in body) (line as any)[key] = body[key] === true
    if (body.appealDecision) line!.appealDecision = body.appealDecision
    line!.evidence = proof(parent, line!, body.evidence || line!.evidence)
    if (line!.waitingFor) need(/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(line!.followUpAt), '等待时须明确下次跟进时间')
    if (action === 'submit') {
      need(!line!.transfer, '待交接确认，不得推进')
      need(
        line!.collaborations.every((task) => !task.required || task.status === 'DONE'),
        '必需协办尚未完成',
      )
      for (const key of ['description', 'conclusion', 'diffType', 'attribution']) text((line as any)[key], key)
      need(!line!.waitingFor, '尚有等待事项，请先完成跟进并清除等待，或保存草稿继续跟进')
      need(!line!.recoveryRequired || (line!.recoveryCode && line!.recoveryResult), '恢复编码必需时需编码与完成结果')
      need(line!.appealDecision === '申诉' || line!.appealReason, '不申诉必须说明依据')
      need(line!.financeRequired || line!.financeReason, '无需回款必须说明依据')
      if (line!.financeRequired) need(cents(line!.expectedRefund) > 0, '需要回款时请填写大于0的应收金额')
      if (line!.recoveryRequired && line!.recoveryResult) line!.recoveryCompletedAt = state.clock
      line!.waitingFor = ''
      line!.stage = line!.appealDecision === '申诉' ? 'APPEAL' : 'DIFFERENCE'
    }
  } else if (action === 'appeal') {
    handle()
    stage('APPEAL')
    const evidence = proof(parent, line!, body.evidence)
    need(['平台', '供应商', '航司', '供应商/航司'].includes(body.target), '请选择申诉对象')
    need(['处理中', '成功', '部分成功', '失败', '撤回'].includes(body.status), '申诉状态无效')
    if (['部分成功', '失败'].includes(body.status)) {
      need(cents(body.borneAmount) <= cents(line!.amount), '承担金额不能超过本明细金额')
      line!.borneAmount = body.borneAmount
    }
    if (typeof body.financeRequired === 'boolean') line!.financeRequired = body.financeRequired
    if (line!.financeRequired) {
      need(cents(body.expectedRefund) > 0, '请填写应收金额')
      line!.expectedRefund = body.expectedRefund
    }
    line!.appeals.push({
      id: id(),
      target: body.target,
      status: body.status,
      result: text(body.result, '申诉说明'),
      evidence,
      round: line!.appeals.filter((value) => value.target === body.target).length + 1,
    })
  } else if (action === 'appeal_next') {
    handle()
    stage('APPEAL')
    const latest = new Map(line!.appeals.map((value) => [value.target, value]))
    need(latest.size && [...latest.values()].every((value) => value.status !== '处理中'), '尚有未结束申诉或未记录申诉')
    line!.stage = [...latest.values()].every((value) => value.status === '成功') ? 'REVIEW' : 'DIFFERENCE'
  } else if (action === 'difference') {
    handle()
    stage('DIFFERENCE')
    line!.differenceReason = text(body.reason, '已登记凭据或无需登记依据')
    line!.differenceRecorded = body.recorded === true
    line!.evidence = proof(parent, line!, body.evidence)
    need(!line!.transfer, '待交接确认，不得提交审核')
    need(
      line!.collaborations.every((task) => !task.required || task.status === 'DONE'),
      '必需协办未完成',
    )
    line!.stage = 'REVIEW'
  } else if (action === 'review') {
    need(actor === 'reviewer', '仅独立审核人可操作，不允许主承办自审')
    stage('REVIEW')
    text(body.reason, '审核意见')
    proof(parent, line!, line!.evidence)
    need(
      !line!.transfer && line!.collaborations.every((task) => !task.required || task.status === 'DONE'),
      '待交接或必需协办未完成',
    )
    line!.stage = body.approved ? 'DONE' : 'INVESTIGATE'
    line!.lockedBy = ''
  } else if (action === 'finance') {
    need(actor === 'finance', '仅财务确认人可操作')
    stage('DONE')
    need(line!.financeRequired && !line!.financeReference, '当前没有待回款事项，不能重复确认')
    line!.financeReference = text(body.reference, '核对凭证号', 200)
    need(cents(body.amount) > 0, '到账金额须大于0；无支出不应创建回款任务')
    need(
      !(line!.payments || []).some((payment) => payment.reference === body.reference.trim()),
      '该明细已登记此凭证，不重复记账',
    )
    const total = (line!.payments || []).reduce((sum, value) => sum + cents(value.amount), 0) + cents(body.amount)
    const due = cents(line!.expectedRefund || line!.amount)
    need(total <= due, '累计到账不能超过应收，请核对金额')
    need(!body.confirmComplete || total === due, '仍有剩余应收，不能确认全部到账')
    const evidence = proof(parent, line!, body.evidence)
    const reason = text(body.reason, '财务核对依据')
    ;(line!.payments ||= []).push({
      id: id(),
      reference: body.reference.trim(),
      amount: body.amount,
      at: state.clock,
      reason,
      evidence,
    })
    line!.settledAmount = cash(total)
    line!.financeReference = total === due ? body.reference.trim() : ''
    line!.stage = 'DONE'
  } else if (action === 'transfer_request') {
    handle()
    stage('ACCEPT', 'INVESTIGATE', 'APPEAL', 'DIFFERENCE')
    need(!line!.transfer, '已有待确认交接')
    need(['handlerA', 'handlerB', 'lead'].includes(body.owner) && body.owner !== actor, '接收人必须为其他获授权承办人')
    line!.transfer = { to: body.owner, reason: text(body.reason, '交接原因及待办摘要') }
  } else if (action === 'transfer_accept' || action === 'transfer_reject') {
    need(line?.transfer?.to === actor, '仅待接收人可确认或驳回')
    text(body.reason, '交接处理意见')
    if (action === 'transfer_accept') line!.owner = actor
    line!.transfer = undefined
  } else if (action === 'transfer_cancel') {
    handle()
    need(line!.transfer, '无待确认交接')
    text(body.reason, '取消原因')
    line!.transfer = undefined
  } else if (action === 'collab_create') {
    handle()
    stage('INVESTIGATE')
    need(['handlerA', 'handlerB'].includes(body.owner), '请选择协办人')
    line!.collaborations.push({
      id: id(),
      title: text(body.title, '协办目标', 200),
      owner: body.owner,
      required: body.required === true,
      status: 'TODO',
      result: '',
      evidence: [],
    })
  } else if (action === 'collab_accept' || action === 'collab_submit' || action === 'collab_review') {
    const task = line?.collaborations.find((value) => value.id === body.taskId)
    need(task, '协办任务不存在')
    if (action === 'collab_review') {
      need(
        (actor === line!.owner || actor === 'coordinator') && actor !== task!.owner && task!.status === 'REVIEW',
        '仅非协办本人的主承办/协调人可独立复核',
      )
      text(body.reason, '复核意见')
      task!.status = body.approved ? 'DONE' : 'ACTIVE'
    } else {
      need(actor === task!.owner, '只能办理本人的协办')
      if (action === 'collab_accept') {
        need(task!.status === 'TODO', '已接收，请勿重复')
        task!.status = 'ACTIVE'
      } else {
        need(task!.status === 'ACTIVE', '先接收再提交')
        task!.result = text(body.result, '协办结果')
        task!.evidence = proof(parent, line!, body.evidence)
        task!.status = 'REVIEW'
      }
    }
  } else if (action === 'responsibility') {
    handle()
    stage('INVESTIGATE')
    line!.attribution = text(body.attribution, '责任类别', 100)
    line!.responsiblePerson = String(body.person || '')
    text(body.reason, '认定依据')
    proof(parent, line!, body.evidence)
    line!.responsibilityStatus = '待独立复核'
    line!.responsibilityProposer = actor
  } else if (action === 'responsibility_review') {
    need(actor === 'reviewer' && line?.responsibilityStatus === '待独立复核', '仅指定审核人可复核待定提案')
    text(body.reason, '责任复核依据')
    line!.responsibilityStatus = body.approved ? '已确认' : '退回补充'
  } else if (action === 'amount') {
    coordinator()
    need(line, '请选择明细')
    need(['MATCH', 'ASSIGN', 'ACCEPT', 'INVESTIGATE'].includes(line!.stage), '提交申诉后不直接改金额，需退回或重开')
    cents(body.amount)
    line!.amount = body.amount
    text(body.reason, '金额调整依据')
  } else if (action === 'attach') {
    need(
      line ? visibleLines(parent, actor).some((value) => value.id === line.id) : actor === 'coordinator',
      '无此材料范围',
    )
    need(
      actor === 'coordinator' ||
        line?.owner === actor ||
        line?.collaborations.some((value) => value.owner === actor && value.status === 'ACTIVE') ||
        actor === 'reviewer' ||
        actor === 'finance',
      '无当前材料上传权',
    )
    if (closedAttachment) need(line && body.category !== '下发原件', '结案后只能向获权明细补充整改证据，不更换主单原件')
    const file: Evidence = {
      id: id(),
      name: text(body.name, '演练附件名称', 200),
      category: body.category || '补充证据',
      lineId: lineId || '',
      shared: [],
      content: text(body.content, '演练文件内容', 10000),
    }
    if (body.dataUrl) {
      need(
        typeof body.dataUrl === 'string' &&
          /^data:(image\/(png|jpeg|gif|webp)|application\/pdf|text\/plain|application\/octet-stream);base64,/.test(
            body.dataUrl,
          ),
        '文件类型无效',
      )
      need(body.size > 0 && body.size <= 2 * 1024 * 1024, '单文件最多2MB')
      need(
        parent.files.reduce((total, value) => total + (value.size || 0), 0) + body.size <= 6 * 1024 * 1024,
        '本单本地文件合计最多6MB',
      )
      file.dataUrl = body.dataUrl
      file.mime = String(body.mime)
      file.size = body.size
    }
    parent.files.push(file)
    if (line) line.evidence.push(file.id)
  } else if (action === 'share') {
    coordinator()
    const file = parent.files.find((value) => value.id === body.fileId)
    need(file, '附件不存在')
    need(body.confirm === true, '须确认整份文件适合授权范围；脱敏需真实副本')
    need(
      Array.isArray(body.lineIds) &&
        body.lineIds.every((value: string) => parent.lines.some((line) => line.id === value)),
      '共享范围无效',
    )
    text(body.reason, '共享依据')
    file!.shared = [...new Set(body.lineIds)] as string[]
  } else if (action === 'close') {
    coordinator()
    need(!blockers(parent).length, blockers(parent).join('；'))
    text(body.reason, '结案核对依据')
    parent.status = 'CLOSED'
    parent.remediation.status = '待整改'
    ;(parent.closedSnapshots ||= []).push({
      at: state.clock,
      amount: parent.amount,
      lines: JSON.parse(JSON.stringify(parent.lines)),
    })
  } else if (action === 'reopen') {
    coordinator()
    need(parent.status === 'CLOSED', '仅结案单可重开')
    text(body.reason, '重开依据')
    parent.status = 'ACTIVE'
    parent.lines.forEach((value) => {
      value.stage = 'INVESTIGATE'
      value.round++
    })
    parent.remediation.status = '未开始'
  } else if (action === 'remediation_accept') {
    need(
      parent.status === 'CLOSED' && actor === parent.remediation.owner && parent.remediation.status === '待整改',
      '仅指定整改人可接收',
    )
    parent.remediation.status = '整改中'
  } else if (action === 'remediate') {
    need(
      parent.status === 'CLOSED' && actor === parent.remediation.owner && parent.remediation.status === '整改中',
      '仅指定整改人可提交结案后整改',
    )
    parent.remediation.result = text(body.result, '整改措施与验证结果')
    need(line, '请选择相关明细的证据')
    parent.remediation.evidence = proof(parent, line!, body.evidence)
    parent.remediation.status = '待复核'
  } else if (action === 'remediation_review') {
    need(
      parent.status === 'CLOSED' && actor === 'reviewer' && parent.remediation.status === '待复核',
      '仅独立复核人可复核整改',
    )
    text(body.reason, '整改复核依据')
    parent.remediation.status = body.approved ? '已整改' : '整改中'
  } else if (action === 'pause' || action === 'resume' || action === 'void') {
    coordinator()
    text(body.reason, '控制操作原因')
    if (action === 'void') parent.status = 'VOID'
    else parent.paused = action === 'pause'
  } else throw new Error('不支持的演练操作')
  state.version++
  state.events.push({
    id: id(),
    at: state.clock,
    caseId,
    lineId,
    actor,
    action,
    reason: String(body.reason || body.result || '模拟操作'),
    before,
    after: parent.status === 'CLOSED' ? '已结案' : line ? stageNames[line.stage] : parent.status,
    round: line?.round || 1,
  })
  const previous = new Set(tasks(source).map((task) => `${task.id}:${task.owner}`))
  tasks(state)
    .filter((task) => !previous.has(`${task.id}:${task.owner}`))
    .forEach((task) =>
      state.notices.push({
        id: id(),
        recipient: task.owner,
        caseId: task.caseId,
        lineId: task.lineId,
        text: `${parent.preliminary ? '[邮件核实＋群辅助模拟]' : `[${state.rules?.channel || '企业微信'}模拟]`} ${task.title}`,
        read: false,
      }),
    )
  tasks(state)
    .filter((task) => !previous.has(`${task.id}:${task.owner}`))
    .forEach((task) => {
      const target = parent.lines.find((value) => value.id === task.lineId)
      if (target?.supervisor && target.supervisor !== task.owner && ['handlerA', 'handlerB'].includes(task.owner))
        state.notices.push({
          id: id(),
          recipient: target.supervisor,
          caseId: task.caseId,
          lineId: task.lineId,
          text: `[组长督办模拟] ${roleName(task.owner)}：${task.title}`,
          read: false,
        })
    })
  return state
}

/** Keep the single-page non-appeal submission atomic: failed difference validation retains the draft and original state. */
export function submitProcessing(
  source: SimState,
  actor: string,
  caseId: string,
  lineId: string,
  body: Body,
  expected = source.version,
) {
  let next = transition(source, actor, caseId, lineId, 'submit', body, expected)
  if (body.appealDecision === '不申诉')
    next = transition(
      next,
      actor,
      caseId,
      lineId,
      'difference',
      {
        reason: body.differenceReason,
        recorded: body.differenceRecorded,
        evidence: body.evidence,
      },
      next.version,
    )
  return next
}
