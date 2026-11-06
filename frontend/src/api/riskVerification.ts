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

export type VerificationStatus = 'problem' | 'supported' | 'insufficient' | 'reviewing' | 'unchecked' | 'failed' | 'rule_pending' | 'outdated'
export interface VerificationMetrics {
  total: number
  problem: number
  supported: number
  insufficient: number
  reviewing: number
  unchecked: number
  failed: number
  rule_pending: number
  outdated: number
}
export interface RiskCatalogFreshness {
  missingDays?: string[]
  preparation?: { readyDays: string[]; missingDays: string[]; mode: string; ruleVersion: string; reports: { day: string; orders: number; seconds: number; statuses: Record<string, number>; insufficientCauses: Record<string, number> }[] }
  reasonDictionaryVersion?: string
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
  sampling?: { sampled: number; disputed: number }
  dataFreshness: RiskCatalogFreshness
  period: { startDate: string; endDate: string }
  dateBasis: string
  metrics: VerificationMetrics
  categories: VerificationCategory[]
  notes: string[]
}
export interface AutoRiskJob { id: string | null; status: string; done: number; total: number; remaining: number; startDate?: string; endDate?: string; phase?: string; message?: string; reused?: number; refreshedRows?: number; sourceMode?: string; preparationReports?: { day: string; orders: number; seconds: number; statuses: Record<string, number>; insufficientCauses: Record<string, number> }[] }
export interface RiskMatchCondition { field: string; label: string; value: string; actual?: string | null; outcome?: string; missing?: string[] }
export interface RiskCandidateTrace { ruleId: string; outcome: string; reason?: string; weight?: number; updateTime?: string; configurationVersion?: number; conditions?: RiskMatchCondition[] }
export interface RiskConfigCandidate {
  id: string | number; rule_name: string; rule_type: string; version: number | null; ota_code: string | null; ota_site_code: string | null; airline: string | null;
  start_time: string | null; end_time: string | null; update_time: string | null; ext_json: string | null; rule_notes: string | null;
  weight: number | null; weightFields: string[]; priorityPosition?: number; priorityStatus: string; conditions: RiskMatchCondition[]; contentTruncated: boolean;
  segmentThresholds?: { values: Record<string, string> };
}

export interface AutoRiskResult {
  id: string; orderId: string; reasonCode: string; sourceUpdatedAt: string | null; ruleVersion: string; checkedAt: string
  status: VerificationStatus; summary: string; platform?: string; stopLoss?: string; missing?: string[]; evidenceHash?: string
  sourceMode?: string; loadedAt?: string; isCurrent?: boolean; catalogRunId?: string; reusedFrom?: string
  aggregate?: { orderCount: number; ticketCount: number; childTickets?: number; infantTickets?: number; totalProfit?: string; averageProfit?: string; averageProfitDisplay?: string; currency?: string; commissionIncluded: boolean; scope: { orderId: string; updatedAt?: string; ticketCount: number }[] }
  tickets: { id: string; profit: string | null; commission: string | null; adjustedProfit?: string; boundary?: string; status: VerificationStatus; explanation: string; segmentCount?: number | null; stopLoss?: string | null; configuration?: { status: string; weight?: number; sortBasis?: string; matchingFacts?: Record<string, string>; matchingFactProblems?: Record<string, string>; candidateTrace?: RiskCandidateTrace[]; issueWay?: string; issueWayLabel?: string; diagnostics?: { ruleId: string; stage: string; reason: string; fields: string[] }[]; ruleId?: string; configurationVersion?: number; asOf?: string; jsonPath?: string; baseAmount?: string; extraSegments?: number; extraPerSegment?: string; configurationHash?: string; configurationSnapshot?: Record<string, unknown>; basis?: string; historyProof?: string; source?: string; historyReferences?: string[] } }[]
  logReferences?: { id: string; at: string | null }[]
  samples?: { id: string; outcome: string; reason: string; at: string }[]
}
export const riskAutomatic = {
  start: (startDate: string, endDate: string, reason?: string) => flowPost<AutoRiskJob>('automatic/jobs', { startDate, endDate, reason, mode: 'refresh_verify' }),
  job: () => flowGet<AutoRiskJob | null>('automatic/job'),
  result: (orderId: string, issueDate?: string) => flowGet<AutoRiskResult | null>(`automatic/orders/${orderId}${issueDate ? `?issueDate=${encodeURIComponent(issueDate)}` : ''}`),
  sample: (orderId: string, resultId: string, outcome: string, reason: string, issueDate?: string) => flowPost<unknown>(`automatic/orders/${orderId}/sample`, { resultId, outcome, reason, issueDate }),
}
export interface RiskProblemType { id: string; name: string; created_by: string; created_at: string }
export interface RiskProblemTag { id: string; order_id: string; type_id: string; type_name: string; reason: string; created_by: string; created_at: string }
export const riskProblems = {
  types: () => flowGet<RiskProblemType[]>('problem-types'),
  createType: (name: string) => flowPost<RiskProblemType>('problem-types', { name }),
  tags: (orderId: string) => flowGet<RiskProblemTag[]>(`orders/${orderId}/problem-tags`),
  saveTags: (orderId: string, typeIds: string[], reason: string) => flowPost<RiskProblemTag[]>(`orders/${orderId}/problem-tags`, { typeIds, reason }),
  configs: (platform: string, group: string, ruleId = '', airline = '', page = 1, pageSize = 20) => flowGet<{ items: RiskConfigCandidate[]; total: number; page: number; pageSize: number; notice: string; useForCalculation: false }>(`rule-configs?${new URLSearchParams({ platform, group, ruleId, airline, page: String(page), pageSize: String(pageSize) })}`),
}
export interface VerificationOrder {
  issue_date?: string | null; ota_order_no?: string | null; ota_code?: string | null; order_no?: string | null; profit_reason_type: string | null; update_time?: string | null;
  total_profit?: string | null; segment_count?: number | null; airlines?: string[]; departments?: string[]; metricsReady?: boolean
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
  orders: (startDate: string, endDate: string, reason: string | undefined, status: VerificationStatus | 'all', page: number, pageSize: number, filters: { orderNo?: string; platform?: string; airline?: string; sort?: string } = {}) => http.get<ApiEnvelope<VerificationOrders>>('/v1/risk-verification/orders', { params: { startDate, endDate, reason, status, page, pageSize, ...filters } }).then(response => response.data.data),
}

// Exact 正常业务 codes verified against the published reason dictionary.
export const NORMAL_REASON_CODES: string[] = ['R001', 'RPA000']
