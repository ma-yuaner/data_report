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

export type VerificationStatus = 'problem' | 'supported' | 'insufficient' | 'reviewing' | 'unchecked'
export interface VerificationMetrics {
  total: number
  problem: number
  supported: number
  insufficient: number
  reviewing: number
  unchecked: number
}
export interface RiskCatalogFreshness {
  source: 'sibebid'
  mode: 'etl_catalog'
  complete: boolean
  oldestSyncedAt: string
  newestSyncedAt: string
  days: { issue_date: string; etl_run_id: string; row_count: number; synced_at: string }[]
  latestAttempt: { status: string; started_at: string; finished_at: string | null; error_code: string | null } | null
}
export interface VerificationCategory extends VerificationMetrics {
  reasonCode: string
  reasonLabel: string
  ruleStatus: string
}
export interface VerificationOverview {
  dataFreshness: RiskCatalogFreshness
  period: { startDate: string; endDate: string }
  dateBasis: string
  metrics: VerificationMetrics
  categories: VerificationCategory[]
  notes: string[]
}
export interface VerificationOrder extends EvidenceRow {
  id: string
  verificationStatus: VerificationStatus
  caseId: string | null
}
export interface VerificationOrders {
  dataFreshness: RiskCatalogFreshness
  items: VerificationOrder[]
  total: number
  page: number
  pageSize: number
}
export const verificationOverview = {
  summary: (startDate: string, endDate: string) => http.get<ApiEnvelope<VerificationOverview>>('/v1/risk-verification/overview', { params: { startDate, endDate } }).then(response => response.data.data),
  orders: (startDate: string, endDate: string, reason: string | undefined, status: VerificationStatus | 'all', page: number, pageSize: number) => http.get<ApiEnvelope<VerificationOrders>>('/v1/risk-verification/orders', { params: { startDate, endDate, reason, status, page, pageSize } }).then(response => response.data.data),
}
