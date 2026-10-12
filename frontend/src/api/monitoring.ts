import { http, type ApiEnvelope } from './http'

export interface MonitorRun {
  id: number
  runNo: string
  jobType: string
  sourceCode?: string
  batchId?: string
  status: string
  rowsRead: number
  rowsWritten: number
  rulesChecked: number
  eventsCreated: number
  errorMessage?: string
  startedAt: string
  finishedAt?: string
  durationMs?: number
}

export interface MonitorRule {
  id: number
  ruleCode: string
  ruleName: string
  templateCode: string
  templateName?: string
  businessType: string
  sourceParentId?: number
  ownerUserName?: string
  severity: string
  status: string
  effectiveStartAt?: string
  effectiveEndAt?: string
  currentVersionNo: number
  lastRunAt?: string
  lastHitAt?: string
  hitCount?: number
  updatedAt: string
}

export interface MonitorCondition {
  id: number
  fieldCode: string
  operatorCode: string
  valueType: string
  valueJson: string
  conditionRole: string
}

export interface MonitorRuleDetail {
  rule: MonitorRule
  versions: Array<Record<string, unknown> & { id: number; versionNo: number; conditions: MonitorCondition[] }>
  logs: Array<Record<string, unknown>>
}

export interface MonitorEvent {
  id: number
  eventNo: string
  ruleId: number
  ruleCode: string
  templateCode: string
  businessType: string
  entityType: string
  entityKey: string
  severity: string
  eventTitle: string
  eventDetail?: string
  eventStatus: string
  hitCount: number
  occurredAt: string
  businessRefType?: string
  businessRefId?: number
}

export interface MonitorOverview {
  available: boolean
  source: string
  ruleSummary: { totalRules?: number; activeRules?: number; scheduledRules?: number; pausedRules?: number }
  eventSummary: { totalEvents?: number; openEvents?: number; acknowledgedEvents?: number }
  pendingNotifications: number
  recentRuns: MonitorRun[]
}

export interface PagedResult<T> { rows: T[]; total: number; page: number; pageSize: number }

export interface MonitorRuleInput {
  templateCode: 'ORDER_SEGMENT_THRESHOLD'
  ruleName: string
  severity: string
  effectiveStartAt?: string
  effectiveEndAt?: string
  ownerUserName?: string
  scheduleSeconds?: number
  changeReason?: string
  conditions: Array<{ fieldCode: string; operatorCode: string; value: string | number | string[]; conditionRole?: string }>
}

export interface MonitorDiagnosticCondition {
  fieldCode: string
  fieldName: string
  operatorCode: string
  expected: unknown
  actual: unknown
  passed: boolean
  conditionRole: string
  groupNo: number
}

export interface MonitorDiagnostic {
  rule: MonitorRule
  order: Record<string, unknown> | null
  event?: Record<string, unknown> | null
  matched: boolean
  conditions: MonitorDiagnosticCondition[]
  stages: Array<{ code: string; name: string; passed: boolean; message: string }>
  recentStats: Array<Record<string, unknown>>
}

export const monitoringApi = {
  overview: () => http.get<ApiEnvelope<MonitorOverview>>('/v1/monitoring/overview').then(response => response.data.data),
  createRule: (payload: MonitorRuleInput) => http.post<ApiEnvelope<{ id: number; ruleCode: string; status: string; versionNo: number }>>('/v1/monitoring/rules', payload).then(response => response.data.data),
  rules: (params: Record<string, unknown>) => http.get<ApiEnvelope<PagedResult<MonitorRule>>>('/v1/monitoring/rules', { params }).then(response => response.data.data),
  ruleDetail: (id: number) => http.get<ApiEnvelope<MonitorRuleDetail>>(`/v1/monitoring/rules/${id}`).then(response => response.data.data),
  diagnoseRule: (id: number, otaOrderNo: string) => http.get<ApiEnvelope<MonitorDiagnostic>>(`/v1/monitoring/rules/${id}/diagnose`, { params: { otaOrderNo } }).then(response => response.data.data),
  updateRuleStatus: (id: number, payload: { status: string; note?: string }) => http.patch<ApiEnvelope<{ id: number; status: string }>>(`/v1/monitoring/rules/${id}/status`, payload).then(response => response.data.data),
  events: (params: Record<string, unknown>) => http.get<ApiEnvelope<PagedResult<MonitorEvent>>>('/v1/monitoring/events', { params }).then(response => response.data.data),
  updateEventStatus: (id: number, payload: { status: string; note?: string }) => http.patch<ApiEnvelope<{ id: number; status: string }>>(`/v1/monitoring/events/${id}/status`, payload).then(response => response.data.data),
  runs: (params: Record<string, unknown> = {}) => http.get<ApiEnvelope<MonitorRun[]>>('/v1/monitoring/runs', { params }).then(response => response.data.data),
}
