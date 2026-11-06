import { http, type ApiEnvelope } from './http'
import { type AutoRiskResult } from './riskVerification'
export interface ConfigObservationTicket {
  ticketId: string; ruleId: string | null; originalStopLoss: string | null; originalResult: string;
  beforeStopLoss: string | null; latestStopLoss: string | null; status: string; reason: string;
  valueChanged: boolean | null; differentFromOriginal: boolean | null; configurationChanged: boolean | null; sourceVersion: number | null;
  sourceUpdatedAt: string | null; observedAt: string; sourceStatus: number | string | null;
  sourceCurrentlyEffective: boolean | null; sourceStart: string | null; sourceEnd: string | null; effectiveTimeBasis: string; usedForOriginalCalculation: false;
}
export interface ConfigObservation { id: string; observedAt: string; recordedAt: string; observedBy: string; changed: boolean; hasUnavailable: boolean; hasUnknownComparison: boolean; tickets: ConfigObservationTicket[]; notice: string }
export interface ConfigEvidence { id: string; original: AutoRiskResult; originalHash: string; savedAt: string; savedBy: string; latest?: ConfigObservation | null; observations?: ConfigObservation[]; historyTruncated?: boolean; alreadySaved?: boolean }
async function call<T>(order: string, method: 'get' | 'post', body: Record<string, unknown>, suffix = '') {
  const path = `/v1/risk-verification/configuration-evidence/${encodeURIComponent(order)}${suffix}`
  const { data } = method === 'get' ? await http.get<ApiEnvelope<T>>(path, { params: body }) : await http.post<ApiEnvelope<T>>(path, body)
  if (!data.success) throw new Error(data.message)
  return data.data
}
export const riskConfigEvidence = {
  get: (order: string, issueDate: string) => call<ConfigEvidence | null>(order, 'get', { issueDate }),
  save: (order: string, issueDate: string, resultId: string) => call<ConfigEvidence>(order, 'post', { issueDate, resultId }),
  observe: (order: string, issueDate: string, requestId: string) => call<ConfigObservation>(order, 'post', { issueDate, requestId }, '/observe'),
}
