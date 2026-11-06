import { http, type ApiEnvelope } from './http'
import { createAdmKey } from '@/features/adm/identifier'

// Same stable-per-draft, internal-HTTP-safe operation identifier as existing forms.
export const reviewKey = createAdmKey
export const conclusions: Record<string, string> = { no_issue: '核查无问题', unknown: '无法判断', problem: '有问题' }
export const dispositions: Record<string, string> = { pending: '待认定', included: '计入差错', excluded: '不计入差错' }
export const followStates: Record<string, string> = { todo: '待跟进', following: '跟进中', waiting: '等待反馈', done: '已完成' }
export interface ReviewPolicy { id: string; name: string; policyVersion: string; start: string; end: string; scope: string; basis: string }
export interface OrderReview { orderId: string; issueDate: string; resultId: string; systemStatus: string; version: number; conclusion: string; reason: string; caseId: string | null; actor: string; at: string; firstSeen?: boolean; special?: boolean; specialReason?: string; stale?: boolean; policy?: ReviewPolicy }
export interface ReviewContext { orderId: string; issueDate: string; resultId: string; systemStatus: string; version: number; stale: boolean; review: OrderReview | null; events?: FollowEvent[]; eventsTruncated?: boolean }
export interface FollowCase { stale?: boolean; id: string; version: number; title: string; conclusion: string; disposition: string; state: string; assignee: string; nextStep: string; nextAt: string | null; firstSeen: boolean; special: boolean; specialReason: string; problemType: string; cause: string; responsibility: string; createdAt: string; updatedAt: string }
export interface FollowEvent { actor: string; at: string; kind: string; note: string; before: Partial<FollowCase & OrderReview> | null; after: Partial<FollowCase & OrderReview> }
export interface FollowDetail extends FollowCase { orders: OrderReview[]; events: FollowEvent[]; eventsTruncated: boolean }
export interface FollowList { items: FollowCase[]; total: number; metrics: Record<string, number>; page: number; pageSize: number }
async function get<T>(path: string, params?: Record<string, unknown>) {
  const { data } = await http.get<ApiEnvelope<T>>(`/v1/risk-verification/followup/${path}`, { params })
  if (!data.success) throw new Error(data.message)
  return data.data
}
async function post<T>(path: string, body: Record<string, unknown>) {
  const { data } = await http.post<ApiEnvelope<T>>(`/v1/risk-verification/followup/${path}`, body)
  if (!data.success) throw new Error(data.message)
  return data.data
}
export const riskFollowup = {
  summaries: (orders: { orderId: string; issueDate: string }[]) => get<ReviewContext[]>('reviews', { orders: orders.map(o => `${o.orderId}:${o.issueDate}`).join(',') }),
  list: (params: Record<string, unknown> = {}) => get<FollowList>('cases', params),
  detail: (id: string) => get<FollowDetail>(`cases/${encodeURIComponent(id)}`),
  update: (id: string, body: Record<string, unknown>) => post<FollowCase>(`cases/${encodeURIComponent(id)}`, body),
  order: (id: string, issueDate: string) => get<ReviewContext>(`orders/${encodeURIComponent(id)}`, { issueDate }),
  review: (body: Record<string, unknown>) => post<{ count: number; caseId: string | null }>('reviews', body),
  policies: () => get<ReviewPolicy[]>('policies'),
  createPolicy: (body: Record<string, unknown>) => post<ReviewPolicy>('policies', body),
}

export function reviewStatus(context?: ReviewContext): string {
  if (!context) return '读取中'
  if (context.stale) return '待重新核实'
  if (!context.review) return '待人工核实'
  return ({ no_issue: '已核实 · 无问题', problem: '已核实 · 有问题', unknown: '待补证 · 无法判断' } as Record<string, string>)[context.review.conclusion] || '待人工核实'
}
