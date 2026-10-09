import { http, type ApiEnvelope } from './http'

export type PlacementTaskStatus = 'DRAFT' | 'PENDING_DATA_REVIEW' | 'PENDING_POLICY_REVIEW' | 'CLAIMABLE' | 'IN_PROGRESS' | 'MONITORING' | 'FAILED' | 'REJECTED' | 'CLOSED' | 'ENDED'
export type PlacementPriority = 'HIGH' | 'MEDIUM' | 'LOW'

export interface PlacementTaskRow {
  id: number
  taskNo: string
  opportunityName: string
  opportunitySource: string
  platformName: string
  siteName: string | null
  airlineCode: string
  departureCode: string | null
  arrivalCode: string | null
  routeText: string | null
  includeCabins: string | null
  excludeCabins: string | null
  productType: string | null
  placementMethod: string
  estimatedMonthTicketCount: number | null
  estimatedMonthProfitCny: string | null
  priority: PlacementPriority
  status: PlacementTaskStatus
  currentAssigneeName: string | null
  expectedCompleteAt: string
  createdByName: string
  createdAt: string
  updatedAt: string
}

export type PlacementTask = PlacementTaskRow & Record<string, string | number | boolean | null>
export interface PlacementReview extends Record<string, string | number | boolean | null> { id: number; reviewStage: string; reviewResult: string; reviewerName: string; createdAt: string }
export interface PlacementExecution extends Record<string, string | number | boolean | null> { id: number; executionResult: string; externalPolicyId: string | null; operatorName: string; createdAt: string }
export interface PlacementLog extends Record<string, string | number | boolean | null> { id: number; actionCode: string; fromStatus: string | null; toStatus: string | null; operatorName: string; operationNote: string | null; createdAt: string }

export interface PlacementTaskList {
  available: boolean
  error: string
  summary: Record<PlacementTaskStatus, number>
  rows: PlacementTaskRow[]
  total: number
  page: number
  pageSize: number
}

export interface PlacementTaskDetail {
  task: PlacementTask
  reviews: PlacementReview[]
  executions: PlacementExecution[]
  logs: PlacementLog[]
}

export interface PlacementTaskInput {
  opportunityName: string
  opportunitySource: string
  analysisRuleCode?: string
  analysisStartDate: string
  analysisEndDate: string
  platformCode?: string
  platformName: string
  siteCode?: string
  siteName?: string
  airlineCode: string
  departureCode?: string
  arrivalCode?: string
  routeText?: string
  journeyType?: string
  flightNos?: string
  includeCabins?: string
  excludeCabins?: string
  productType?: string
  orderStartDate?: string
  orderEndDate?: string
  travelStartDate?: string
  travelEndDate?: string
  placementMethod: string
  adjustmentValue?: number
  adjustmentUnit?: string
  suggestedEffectiveStart?: string
  suggestedEffectiveEnd?: string
  historicalTicketCount?: number
  historicalSegmentCount?: number
  historicalProfitCny?: number
  estimatedMonthTicketCount?: number
  estimatedMonthProfitCny?: number
  analysisConclusion: string
  riskNote?: string
  priority: PlacementPriority
  expectedCompleteAt: string
  submit: boolean
}

export interface PlacementOrderRow extends Record<string, string | number | null> {
  id: number
  taskId: number
  externalPolicyId: string
  otaOrderNo: string
  ticketNo: string | null
  passengerName: string | null
  platformName: string | null
  siteName: string | null
  airlineCode: string | null
  routeText: string | null
  ticketCount: number | null
  segmentCount: number | null
  estimatedProfitCny: string | null
  matchedAt: string
  messageStatus: string
  attentionStatus: string
  attentionOwnerName: string | null
}

export interface PlacementOrderList {
  available: boolean
  error: string
  period: { startDate: string; endDate: string }
  summary: {
    orderCount: number
    ticketCount: number
    segmentCount: number
    estimatedProfit: string
    pendingCount: number
    activePolicyCount: number
  }
  rows: PlacementOrderRow[]
  total: number
  page: number
  pageSize: number
}

export async function fetchPlacementTasks(params: Record<string, string | number>) {
  const response = await http.get<ApiEnvelope<PlacementTaskList>>('/v1/smart-placement/tasks', { params })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export async function fetchPlacementTask(id: number) {
  const response = await http.get<ApiEnvelope<PlacementTaskDetail>>(`/v1/smart-placement/tasks/${id}`)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function createPlacementTask(values: PlacementTaskInput) {
  const response = await http.post<ApiEnvelope<{ id: number; taskNo: string; status: PlacementTaskStatus }>>('/v1/smart-placement/tasks', values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function reviewPlacementTask(id: number, values: Record<string, unknown>) {
  const response = await http.post<ApiEnvelope<{ id: number; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}/reviews`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function claimPlacementTask(id: number, values: { plannedCompleteAt: string; note?: string }) {
  const response = await http.post<ApiEnvelope<{ id: number; status: PlacementTaskStatus; assigneeName: string }>>(`/v1/smart-placement/tasks/${id}/claim`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function executePlacementTask(id: number, values: Record<string, unknown>) {
  const response = await http.post<ApiEnvelope<{ id: number; taskId: number; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}/executions`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function fetchPlacementOrders(params: Record<string, string | number>) {
  const response = await http.get<ApiEnvelope<PlacementOrderList>>('/v1/smart-placement/orders', { params })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function updatePlacementAttention(id: number, values: { status: string; resolutionCode?: string; resolutionNote?: string }) {
  const response = await http.patch<ApiEnvelope<{ id: number; status: string; ownerName: string }>>(`/v1/smart-placement/orders/${id}/attention`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
