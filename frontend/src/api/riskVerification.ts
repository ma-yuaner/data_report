import { http, type ApiEnvelope } from './http'

export type EvidenceRow = Record<string, string | number | null>
export interface EvidenceBlock {
  label: string
  status: 'not_requested' | 'ready' | 'empty' | 'failed' | 'truncated' | 'not_integrated'
  records: EvidenceRow[]
  complete: boolean
  error?: string
}
export interface RiskEvidence {
  erpOrderId: string
  order: EvidenceRow
  blocks: Record<string, EvidenceBlock>
  fetchedAt: string
  candidate: boolean
  notice: string
  aiInvoked: false
  complete: false
}
export interface RiskCandidates {
  items: EvidenceRow[]
  hasMore: boolean
  nextBefore: string | null
  notice: string
}
export async function riskCandidates(startDate: string, endDate: string, before?: string) {
  const { data } = await http.get<ApiEnvelope<RiskCandidates>>('/v1/risk-verification/candidates', { params: { startDate, endDate, before } })
  if (!data.success) throw new Error(data.message)
  return data.data
}
export async function riskEvidence(id: string, sections: string[], identifierType = 'auto') {
  const { data } = await http.get<ApiEnvelope<RiskEvidence>>(`/v1/risk-verification/orders/${encodeURIComponent(id)}/evidence`, { params: { sections: sections.join(','), identifierType } })
  if (!data.success) throw new Error(data.message)
  return data.data
}

export interface RiskCase {
  id: string
  version: number
  state: string
  evidence: RiskEvidence
  evidenceFingerprint: string
  reviews: unknown[]
  confirmation: unknown
  analyses: unknown[]
  createdAt: string
  activeOperation: unknown
}
export interface RiskCaseSummary {
  id: string
  version: number
  state: string
  erpOrderId: string
  profitReasonType: string
  createdAt: string
}
export interface RiskStatus {
  ai: { enabled: boolean; configured: boolean; verified: boolean; model: string; notice: string }
  sourceConfigured: boolean
  rules?: { id: string; label: string; formula: string; status: string }[]
}
export interface RiskKnowledge {
  id: string
  version: number
  status: string
  title: string
  content: string
  scope: string
  source: string
}
async function flowGet<T>(path: string): Promise<T> {
  const { data } = await http.get<ApiEnvelope<T>>(`/v1/risk-verification/${path}`)
  if (!data.success) throw new Error(data.message)
  return data.data
}
async function flowPost<T>(path: string, body: object): Promise<T> {
  const { data } = await http.post<ApiEnvelope<T>>(`/v1/risk-verification/${path}`, body)
  if (!data.success) throw new Error(data.message)
  return data.data
}
export const riskFlow = {
  status: () => flowGet<RiskStatus>('status'),
  list: () => flowGet<RiskCaseSummary[]>('cases'),
  get: (id: string) => flowGet<RiskCase>(`cases/${id}`),
  create: (orderId: string, sections: string[]) => flowPost<RiskCase>('cases', { orderId, sections }),
  preview: (id: string) => flowGet<unknown>(`cases/${id}/preview`),
  review: (item: RiskCase) => flowPost<RiskCase>(`cases/${item.id}/review`, { version: item.version }),
  confirm: (item: RiskCase, conclusion: string, reason: string) => flowPost<RiskCase>(`cases/${item.id}/confirm`, { version: item.version, conclusion, reason }),
  analyze: (item: RiskCase) => flowPost<RiskCase>(`cases/${item.id}/analyze`, { version: item.version }),
  recover: (item: RiskCase) => flowPost<RiskCase>(`cases/${item.id}/recover`, { version: item.version }),
  draft: (item: RiskCase, knowledge: { title: string; content: string; scope: string; source: string }) => flowPost<RiskKnowledge>(`cases/${item.id}/knowledge`, { version: item.version, ...knowledge }),
  knowledge: () => flowGet<RiskKnowledge[]>('knowledge'),
  publish: (item: RiskKnowledge) => flowPost<RiskKnowledge>(`knowledge/${item.id}/publish`, { version: item.version }),
}
