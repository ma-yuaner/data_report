import { http, type ApiEnvelope } from './http'

export interface RouteFollowup {
  reason: string
  status: string
  note: string
  nextReviewAt: string | null
}
export interface DiagnosticPolicy {
  taskId: number
  taskNo: string
  name: string
  externalPolicyId: string | null
  executionId: number | null
  siteName: string | null
  ownerName: string | null
  state: string
  observedFrom: string | null
  observedUntil: string
  observedDays: number | null
  lastOrderAt: string | null
  noOrderDays: number | null
  periodOrderCount: number | null
  assessmentOrderCount: number | null
  lastRunAt: string
  followupId: number
  followup: Partial<RouteFollowup>
  followupRecordedBy: string | null
  followupRecordedAt: string
  due: boolean
  conditions: Record<string, string | null>
  orderScopeComplete: boolean
}
export interface DiagnosticCell {
  platform: string
  state: string
  periodOrderCount: number | null
  assessmentOrderCount: number | null
  lastOrderAt: string | null
  mixedConditions: boolean
  policies: DiagnosticPolicy[]
}
export interface DiagnosticRoute {
  key: string
  airlineCode: string | null
  departureType: string | null
  departureCode: string | null
  arrivalType: string | null
  arrivalCode: string | null
  journeyType: string | null
  segmentType: string | null
  routeText: string | null
  diagnosis: string
  mixedConditions: boolean
  due: boolean
  hasInterruption: boolean
  cells: Record<string, DiagnosticCell>
}
export interface RouteDiagnosisResult {
  rows: DiagnosticRoute[]
  total: number
  page: number
  pageSize: number
  platforms: string[]
  summary: Record<string, number>
  days: number
  asOf: string
  windowStart: string
  health: Record<string, { status: string; finishedAt: string; startedAt: string; lastSuccessAt: string; code: string; message: string; healthy: boolean }>
  dataHealthy: boolean
  scopeNote: string
}

export async function fetchRouteDiagnosis(values: Record<string, string | number>) {
  const response = await http.get<ApiEnvelope<RouteDiagnosisResult>>('/v1/smart-placement/route-diagnosis', { params: values })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export async function saveRouteFollowup(taskId: number, values: RouteFollowup & { followupId: number }) {
  const response = await http.post<ApiEnvelope<RouteFollowup & { id: number; alreadySaved: boolean }>>(`/v1/smart-placement/tasks/${taskId}/route-followups`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
