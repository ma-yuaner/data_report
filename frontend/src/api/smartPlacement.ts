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
  journeyType: string | null
  segmentType: string | null
  includeCabins: string | null
  excludeCabins: string | null
  productType: string | null
  orderSource: string | null
  placementMethod: string
  estimatedMonthTicketCount: number | null
  estimatedMonthProfitCny: string | null
  priority: PlacementPriority
  status: PlacementTaskStatus
  currentAssigneeId: number | null
  currentAssigneeName: string | null
  expectedCompleteAt: string
  createdById: number
  createdByName: string
  createdAt: string
  updatedAt: string
}

export type PlacementTask = PlacementTaskRow & Record<string, string | number | boolean | null>
export interface PlacementReview extends Record<string, string | number | boolean | null> { id: number; reviewStage: string; reviewResult: string; reviewerName: string; createdAt: string }
export interface PlacementExecution extends Record<string, string | number | boolean | null> { id: number; executionResult: string; externalPolicyId: string | null; operatorName: string; createdAt: string }
export interface PlacementLog extends Record<string, string | number | boolean | null> { id: number; actionCode: string; fromStatus: string | null; toStatus: string | null; operatorName: string; operationNote: string | null; createdAt: string }
export interface PlacementEffectReview extends Record<string, string | number | boolean | null> {
  id: number
  reviewResult: string
  reviewConclusion: string
  nextAction: string | null
  reviewerName: string
  metricSnapshotJson: string
  createdAt: string
}

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
  effectReviews: PlacementEffectReview[]
}

export interface PlacementEffectSummary extends Record<string, string | number | null> {
  rawMatchCount: number
  attributedOrderCount: number
  ticketCount: number | null
  segmentCount: number | null
  estimatedProfitCny: string | null
  ticketedOrderCount: number
  smartParticipatedCount: number
  smartSucceededCount: number
  smartUsedCount: number
  handledCount: number
  staleCount: number
  waitingSyncCount: number
  smartParticipationRate: number | null
  smartSuccessRate: number | null
  attentionCompletionRate: number | null
}

export interface PlacementTaskMonitorRule extends Record<string, string | number | boolean | null> {
  id: number
  ruleCode: string
  ruleName: string
  status: string
  currentVersionNo: number
  effectiveStartAt: string | null
  effectiveEndAt: string | null
  lastRunAt: string | null
  lastHitAt: string | null
  hitCount: number
  openEventCount: number
}

export interface PlacementTaskMonitorCondition extends Record<string, string | number | null> {
  id: number
  ruleVersionId: number
  groupNo: number
  sortNo: number
  fieldCode: string
  operatorCode: string
  valueType: string
  valueJson: string
  conditionRole: 'INCLUDE' | 'EXCLUDE'
}

export interface PlacementTaskMonitoring {
  available: boolean
  rule: PlacementTaskMonitorRule | null
  conditions: PlacementTaskMonitorCondition[]
  effectSummary?: PlacementEffectSummary
}

export interface PlacementDimensionOption { value: string; label: string; code?: string; platformName?: string; platformCode?: string }
export interface PlacementDimensionOptions {
  source: string
  platforms: PlacementDimensionOption[]
  sites: PlacementDimensionOption[]
  airlines: PlacementDimensionOption[]
  products: PlacementDimensionOption[]
  truncated: Record<string, boolean>
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
  journeyType?: string
  segmentType?: string
  flightNos?: string
  includeCabins?: string
  excludeCabins?: string
  productType?: string
  orderSource?: string[]
  orderStartDate?: string
  orderEndDate?: string
  advanceSaleDays?: number
  travelStartDate?: string
  travelEndDate?: string
  placementMethod: string
  lossThresholdMin?: number
  lossThresholdMax?: number
  longTerm: boolean
  suggestedEffectiveStart?: string
  suggestedEffectiveEnd?: string
  historicalTicketCount?: number
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
  outcomeStatus: string | null
  dataFreshnessStatus: string | null
  outcomeSourceTable: string | null
  outcomeSourceUpdatedAt: string | null
  outcomeLastCheckedAt: string | null
  currentTicketNo: string | null
  currentPassengerName: string | null
  currentTicketTime: string | null
  currentTicketCount: number | null
  currentSegmentCount: number | null
  currentEstimatedProfitCny: string | null
  currentOrderStatus: string | null
  currentIssueStatus: string | null
  smartConfirm: string | null
  smartParticipated: number | null
  smartSucceeded: number | null
  smartUsed: number | null
  attributionType: 'PRIMARY' | 'SECONDARY' | null
  primaryMatchId: number | null
  matchedPolicyCount: number | null
  attributionNote: string | null
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
    primaryOrderCount: number
    ticketedOrderCount: number
    smartParticipatedCount: number
    smartSucceededCount: number
    smartUsedCount: number
    staleCount: number
    waitingSyncCount: number
    smartParticipationRate: number | null
    smartSuccessRate: number | null
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
export async function fetchPlacementDimensions() {
  const response = await http.get<ApiEnvelope<PlacementDimensionOptions>>('/v1/smart-placement/dimensions')
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export async function fetchPlacementTask(id: number) {
  const response = await http.get<ApiEnvelope<PlacementTaskDetail>>(`/v1/smart-placement/tasks/${id}`)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function fetchPlacementTaskMonitoring(id: number) {
  const response = await http.get<ApiEnvelope<PlacementTaskMonitoring>>(`/v1/smart-placement/tasks/${id}/monitoring`)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function createPlacementTask(values: PlacementTaskInput) {
  const response = await http.post<ApiEnvelope<{ id: number; taskNo: string; status: PlacementTaskStatus }>>('/v1/smart-placement/tasks', values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function updatePlacementTask(id: number, values: PlacementTaskInput) {
  const response = await http.patch<ApiEnvelope<{ id: number; taskNo: string; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function deletePlacementTask(id: number) {
  const response = await http.delete<ApiEnvelope<{ id: number; deleted: boolean }>>(`/v1/smart-placement/tasks/${id}`)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function withdrawPlacementTask(id: number) {
  const response = await http.post<ApiEnvelope<{ id: number; taskNo: string; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}/withdraw`)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function cancelPlacementTask(id: number, reason: string) {
  const response = await http.post<ApiEnvelope<{ id: number; taskNo: string; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}/cancel`, { reason })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function reviewPlacementTask(id: number, values: Record<string, unknown>) {
  const response = await http.post<ApiEnvelope<{ id: number; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}/reviews`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function batchReviewPlacementTasks(taskIds: number[], values: Record<string, unknown>) {
  const response = await http.post<ApiEnvelope<{ count: number; taskIds: number[]; status: PlacementTaskStatus }>>('/v1/smart-placement/tasks/reviews/batch', { ...values, taskIds })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function claimPlacementTask(id: number, values: { plannedCompleteAt: string; note?: string }) {
  const response = await http.post<ApiEnvelope<{ id: number; status: PlacementTaskStatus; assigneeName: string }>>(`/v1/smart-placement/tasks/${id}/claim`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function executePlacementTask(id: number, values: Record<string, unknown>) {
  const response = await http.post<ApiEnvelope<{ id: number; taskId: number; status: PlacementTaskStatus; monitorRule?: { ruleId: number; ruleCode: string; ruleVersionId: number; ruleVersionNo: number; ruleStatus: string; conditionCount: number } | null }>>(`/v1/smart-placement/tasks/${id}/executions`, values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function stopPlacementMonitoring(id: number, reason: string) {
  const response = await http.post<ApiEnvelope<{ id: number; status: PlacementTaskStatus }>>(`/v1/smart-placement/tasks/${id}/stop`, { reason })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function createPlacementEffectReview(id: number, values: { result: string; conclusion: string; nextAction?: string }) {
  const response = await http.post<ApiEnvelope<{ id: number; taskId: number; result: string; metricSnapshot: PlacementEffectSummary }>>(`/v1/smart-placement/tasks/${id}/effect-reviews`, values)
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
