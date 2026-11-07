import { http, type ApiEnvelope } from './http'
import type { RiskMatchCondition } from './riskVerification'

export interface LatestConfigTicket {
  ticketId: string; originalStopLoss: string | null; latestStopLoss: string | null; status: string; reason: string
  configurationChanged?: boolean | null
  lastSuccessful?: LatestConfigTicket & { observedAt: string; sourceHash: string }
  configuration?: {
    ruleId?: string; configurationVersion?: number | null; conditions?: RiskMatchCondition[]
    jsonPath?: string; baseAmount?: string; extraSegments?: number; extraPerSegment?: string
    sourceUpdatedAt?: string | null; sourceStart?: string | null; sourceEnd?: string | null
  } | null
  changes?: { field: string; label?: string; before: unknown; after: unknown }[]
}
export interface LatestConfigRun {
  runId: string; runDay?: string; observedAt: string; completedAt: string | null; sourceHash: string; sourceChangedAfterSnapshot: boolean
}
export interface LatestConfigResponse {
  state: 'unrefreshed' | 'ready'; historyRunId: string | null
  expectedRunDay: string
  observation: { tickets: LatestConfigTicket[]; changed: boolean } | null
  publishedRun: LatestConfigRun | null
  latestAttempt: { runId: string | null; status: string; lastError: string | null; startedAt: string; completedAt: string | null } | null
}
export async function readLatestConfig(orderId: string, issueDate: string, resultId: string, historyRunId?: string) {
  const { data } = await http.get<ApiEnvelope<LatestConfigResponse>>(`/v1/risk-verification/configuration-evidence/${encodeURIComponent(orderId)}/latest`, {
    params: { issueDate, resultId, historyRunId },
  })
  if (!data.success) throw new Error(data.message)
  return data.data
}
export const latestConfigStatus = (status?: string) => ({
  matched: '匹配成功', ready: '匹配成功', no_match: '无适用配置', insufficient: '证据不足', unavailable: '无法取得', ambiguous: '候选不确定',
}[status || ''] || '尚未刷新')
