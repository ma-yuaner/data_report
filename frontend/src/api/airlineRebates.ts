import { ApiError, http, type ApiEnvelope } from './http'

export type RebateNumber = number | string | null
export type RebateConditionValue = string | number | string[] | number[]
export type MappingDecision = 'confirmed' | 'missing' | 'found' | 'reset'
interface MappingCheck { expected: string; present?: number; invalid?: number; passed: boolean }
export interface RebateDataMapping {
  status: 'exact' | 'trial' | 'unchecked' | 'failed' | 'missing' | 'unmapped' | 'pending_registration' | 'constant'
  kind: 'exact' | 'trial' | 'unmapped' | 'constant'
  fields: string[]
  filterFields: string[]
  checks: Record<string, MappingCheck>
  decision: { state?: MappingDecision; note?: string; by?: string; at?: string }
}
export interface RebateMappingReview {
  policy: RebatePolicy
  rules: RebateRule[]
  validation?: { rows: number; fields: Record<string, MappingCheck>; at: string; error?: string }
}
export interface RebateCondition {
  id: string
  fieldLabel: string
  operator: string
  value: RebateConditionValue
  mapping?: string
  dataMapping?: RebateDataMapping
  sourceText?: string | null
}
export interface RebateRule {
  id: string
  name: string
  sourcePage?: string
  conditions: RebateCondition[]
}
export interface RebatePolicy {
  id: string
  name: string
  airline?: string
  period?: string
  status: 'pending' | 'ready' | 'failed'
  errorMessage?: string
  confirmed?: boolean
  trialReady?: boolean
}
export interface RebateVersion {
  version: number
  reason: string
  savedAt?: string
  rules: RebateRule[]
}
export interface RebateTask {
  id: string
  name: string
  airline: string
  period: string
  owner: string
  currency: string
  policyName: string
  tier?: string | null
  refreshedAt?: string | null
  refreshMode?: 'scheduled' | 'manual' | null
  refreshStatus?: 'pending' | 'ready' | 'failed'
  estimatedReward?: RebateNumber
  pendingCount?: number | null
  editable?: boolean
  target: RebateNumber
  actual: RebateNumber
  completionRate: RebateNumber
  dataAsOf: string | null
}
export interface RebateRouteDay {
  id: string
  date: string
  records: number
  measuredAmount: RebateNumber
  estimatedReward: RebateNumber
}
export interface RebateRouteCategory extends Omit<RebateRouteDay, 'date'> { name: string }
export interface RebateProgress {
  runId?: string
  refreshedAt?: string | null
  refreshMode?: 'scheduled' | 'manual' | null
  target: RebateNumber
  actual: RebateNumber
  completionRate: RebateNumber
  estimatedReward: RebateNumber
  dataAsOf: string | null
  version: number | null
  status: 'pending' | 'ready' | 'failed'
  errorMessage?: string
  dataNote?: string
  otherOriginReward?: RebateNumber
  pendingCount?: number
  sourceRows?: number
  pendingReasons?: Record<string, number>
  tier?: string | null
  categories?: RebateRouteCategory[]
}
export interface RebateDetailRow {
  id: string
  orderNo: string
  route: string
  eligibleAmount: RebateNumber
  ticketNo?: string
  ticketFare?: RebateNumber
  currency?: string | null
  ratePercent?: RebateNumber
  estimatedReward?: RebateNumber
  orderEstimatedReward?: RebateNumber
  segmentDecisions?: { route: string; date: string; cabin: string; marketingAirline: string; result: string }[]
  result: string
}
export interface RebateTaskDraft { policyId: string; name: string; owner: string }

const root = '/v1/airline-rebates'
const policies = root + '/policies'
const tasks = root + '/tasks'
const taskPath = (id: string) => tasks + '/' + encodeURIComponent(id)
const routePath = (id: string, run: string, category: string) =>
  taskPath(id) + '/runs/' + encodeURIComponent(run) + '/routes/' + encodeURIComponent(category)
async function unwrap<T>(request: Promise<{data: ApiEnvelope<T>}>): Promise<T> {
  const { data } = await request
  if (!data || typeof data !== 'object' || typeof data.success !== 'boolean') {
    throw new ApiError('航司后返服务尚未接通。', 404)
  }
  if (!data.success) throw new ApiError(data.message || '操作未完成。')
  return data.data
}

const mappingPath = (id: string) => policies + '/' + encodeURIComponent(id) + '/mapping'

export const airlineRebates = {
  deletePolicy: (id: string) => unwrap(http.delete<ApiEnvelope<null>>(policies + '/' + encodeURIComponent(id))),
  deleteTask: (id: string) => unwrap(http.delete<ApiEnvelope<null>>(taskPath(id))),
  listPolicies: (signal: AbortSignal) => unwrap(http.get<ApiEnvelope<RebatePolicy[]>>(policies, { signal })),
  listTasks: (signal: AbortSignal) => unwrap(http.get<ApiEnvelope<RebateTask[]>>(tasks, { signal })),
  readMapping: (id: string, signal: AbortSignal) =>
    unwrap(http.get<ApiEnvelope<RebateMappingReview>>(mappingPath(id), { signal })),
  validateMapping: (id: string) =>
    unwrap(http.post<ApiEnvelope<RebateMappingReview>>(mappingPath(id) + '/validate')),
  reviewMapping: (id: string, group: string, rule: string, state: MappingDecision, note: string) =>
    unwrap(http.put<ApiEnvelope<RebateMappingReview>>(mappingPath(id), { group, rule, state, note })),
  confirmPolicy: (id: string) =>
    unwrap(http.post<ApiEnvelope<RebatePolicy>>(policies + '/' + encodeURIComponent(id) + '/confirm')),
  run: (id: string) => unwrap(http.post<ApiEnvelope<RebateProgress>>(taskPath(id) + '/runs')),
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return unwrap(http.post<ApiEnvelope<RebatePolicy>>(policies, form))
  },
  createTask: (draft: RebateTaskDraft) => unwrap(http.post<ApiEnvelope<RebateTask>>(tasks, draft)),
  versions: (id: string, signal: AbortSignal) =>
    unwrap(http.get<ApiEnvelope<RebateVersion[]>>(taskPath(id) + '/versions', { signal })),
  saveVersion: (id: string, baseVersion: number, reason: string, rules: RebateRule[]) =>
    unwrap(http.post<ApiEnvelope<RebateVersion>>(taskPath(id) + '/versions', { baseVersion, reason, rules })),
  progress: (id: string, signal: AbortSignal) =>
    unwrap(http.get<ApiEnvelope<RebateProgress>>(taskPath(id) + '/progress', { signal })),
  routeDays: (id: string, run: string, category: string, signal: AbortSignal) =>
    unwrap(http.get<ApiEnvelope<RebateRouteDay[]>>(routePath(id, run, category) + '/days', { signal })),
  exportRoute: (id: string, run: string, category: string, day?: string) =>
    http.get<Blob>(routePath(id, run, category) + '/export', { params: { day }, responseType: 'blob' }),
  details: (id: string, dailyId: string, category: string, page: number, signal: AbortSignal, q?: string) =>
    unwrap(http.get<ApiEnvelope<{ items: RebateDetailRow[]; total: number }>>(
      taskPath(id) + '/progress/' + encodeURIComponent(dailyId) + '/details',
      { params: { category, page, pageSize: 25, q }, signal },
    )),
}
