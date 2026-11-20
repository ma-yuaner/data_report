export const nodes = ['改期审核', '改期操作'] as const
export type NodeName = typeof nodes[number]
export interface ErpRecord {
  id: string
  created: string
  start: number | null
  end: number | null
  terminal: 'pending' | 'completed' | 'withdrawn' | 'rejected' | 'unknown'
  sourceStatus: string
  endSource: '' | 'latest_issue_time' | 'ACCEPT' | 'audit_operator_time'
  platform: string
  air: string
  owner: string
  kind: string
  linked: number
  businessAt?: number | null
  applicationAt?: number | null
  reportMinutes?: number | null
  platformName?: string
  supplier?: string
  intake?: string
  exchange?: string
  shift?: string
  applicationShift?: string
  completionShift?: string
  ruleDecision?: { source: 'platform' | 'fallback' | 'pending'; minutes: number | null; version: string; detail: string }
}
export interface SlaRule {
  id: string
  node: NodeName
  minutes: number
}
export interface ErpSnapshot {
  snapshot: number
  dates: [string, string]
  records: { audit: ErpRecord[]; operation: ErpRecord[] }
  rules: SlaRule[]
  coverage?: { missingDates: string[]; latestCoveredDate: string | null }
}
export type SlaState = '已撤回' | '操作驳回' | '数据异常' | '待配置' | '进行中超时' | '已完成超时' | '进行中正常' | '已达标'
export interface SlaRow extends ErpRecord {
  node: NodeName
  index: string
  state: SlaState
  elapsed: number | null
  due: number | null
  rule?: SlaRule
}

export const timeout = (row: SlaRow) => row.state === '已完成超时' || row.state === '进行中超时'
export const gap = (row: SlaRow) => row.state === '待配置' || row.state === '数据异常'
export const excluded = (row: SlaRow) => row.state === '已撤回' || row.state === '操作驳回'

export function evaluateErpNodes({ audit, operation }: ErpSnapshot['records'], rules: SlaRule[], asOf: number): SlaRow[] {
  const sources = [[nodes[0], 'audit', audit], [nodes[1], 'operation', operation]] as const
  return sources.flatMap(([node, source, records]) => {
    const defaultRule = rules.find(item => item.node === node)
    return records.map(record => {
      const decision = record.ruleDecision
      const rule = decision
        ? decision.minutes === null ? undefined : { id: decision.version, node, minutes: decision.minutes }
        : defaultRule
      const elapsed = record.start === null ? null : ((record.end ?? asOf) - record.start) / 60000
      let state: SlaState
      if (record.terminal === 'withdrawn') state = '已撤回'
      else if (record.terminal === 'rejected') state = '操作驳回'
      else if (record.terminal === 'unknown' || (record.terminal === 'completed' && record.end === null) ||
        elapsed === null || elapsed < 0) state = '数据异常'
      else if (!rule) state = '待配置'
      else if (elapsed > rule.minutes) state = record.end === null ? '进行中超时' : '已完成超时'
      else state = record.end === null ? '进行中正常' : '已达标'
      const due = rule && record.start !== null ? record.start + rule.minutes * 60000 : null
      return {
        ...record, node, index: source + ':' + record.id, state, due, rule,
        elapsed: state === '已撤回' || state === '操作驳回' ? null : elapsed,
      }
    })
  })
}

export function stats(rows: SlaRow[]) {
  const late = rows.filter(timeout).length
  const passed = rows.filter(row => row.state === '已达标').length
  const judged = passed + late
  return { judged, late, rate: judged ? (passed * 100 / judged).toFixed(1) + '%' : '—' }
}
