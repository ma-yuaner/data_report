import { ApiError, http, type ApiEnvelope } from './http'

export type RebateConditionValue = string | number | string[] | number[]
export interface RebateCondition {
  id: string
  fieldLabel: string
  operator: string
  value: RebateConditionValue
  mapping?: string
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
  target: number | null
  actual: number | null
  completionRate: number | null
  dataAsOf: string | null
}
export interface RebateDailyPoint {
  id: string
  date: string
  version: number
  actual: number | null
  completionRate: number | null
}
export interface RebateProgress {
  target: number | null
  actual: number | null
  completionRate: number | null
  estimatedReward: number | null
  dataAsOf: string | null
  version: number | null
  status: 'pending' | 'ready' | 'failed'
  errorMessage?: string
  daily: RebateDailyPoint[]
}
export interface RebateDetailRow {
  id: string
  orderNo: string
  route: string
  eligibleAmount: number | null
  result: string
}
export interface RebateTaskDraft { policyId: string; name: string; owner: string }

const root = '/v1/airline-rebates'
const policies = root + '/policies'
const tasks = root + '/tasks'
const taskPath = (id: string) => tasks + '/' + encodeURIComponent(id)
async function unwrap<T>(request: Promise<{data: ApiEnvelope<T>}>): Promise<T> {
  const { data } = await request
  if (!data || typeof data !== 'object' || typeof data.success !== 'boolean') {
    throw new ApiError('航司后返服务尚未接通。', 404)
  }
  if (!data.success) throw new ApiError(data.message || '操作未完成。')
  return data.data
}

export const airlineRebates = {
  listPolicies: (signal: AbortSignal) => unwrap(http.get<ApiEnvelope<RebatePolicy[]>>(policies, { signal })),
  listTasks: (signal: AbortSignal) => unwrap(http.get<ApiEnvelope<RebateTask[]>>(tasks, { signal })),
  readPolicy: (id: string, signal: AbortSignal) =>
    unwrap(http.get<ApiEnvelope<RebateRule[]>>(policies + '/' + encodeURIComponent(id), { signal })),
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
  details: (id: string, dailyId: string, page: number, signal: AbortSignal) =>
    unwrap(http.get<ApiEnvelope<{ items: RebateDetailRow[]; total: number }>>(
      taskPath(id) + '/progress/' + encodeURIComponent(dailyId) + '/details',
      { params: { page, pageSize: 25 }, signal },
    )),
}
