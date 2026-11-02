import { http, type ApiEnvelope } from './http'

export interface MissedFilters {
  startDate: string; endDate: string; otaOrderNo: string; platform: string; airline: string
  operator: string; group: string; depCity: string; arrCity: string; jobType: string
  businessType: string; minPrice: string; maxPrice: string; sortBy: string; direction: 'asc' | 'desc'
}
export interface MissedOrder extends Record<string, string | number | null> {
  id: number; otaCode: string; platformName: string; otaOrderNo: string; airline: string
  saleDiffPrice: string | null; depCity: string | null; arrCity: string | null
  cabin: string | null; hprCabin: string | null; policyOperator: string | null
  policyOperatorGroupName: string | null; remark: string | null; issueTicketTime: string | null
  jobTypeName: string | null; businessTypeName: string | null
}
export interface MissedList {
  available: boolean; source: string; filters: MissedFilters; scope: string; scopeEmpty: boolean
  summary: { recordCount: number; orderCount: number; operatorCount: number; routeCount: number; latestRowUpdatedAt: string | null }
  rows: MissedOrder[]; total: number; page: number; pageSize: number
}
export interface MissedDetail { row: MissedOrder; history: MissedOrder[]; historyTruncated: boolean; scope: string; matches?: { available: boolean; rows: { id: number; taskId: number; externalPolicyId: string; taskNo: string; opportunityName: string; attentionStatus: string; matchedAt: string }[]; message: string; truncated?: boolean } }
export type MissedOptions = Record<string, { truncated: boolean; rows: { value: string; label: string }[] }>

async function get<T>(path: string, params?: object) {
  const response = await http.get<ApiEnvelope<T>>(`/v1/smart-placement/missed-orders${path}`, { params })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export const fetchMissedOrders = (params: MissedFilters & { page: number; pageSize: number }) => get<MissedList>('', params)
export const fetchMissedOptions = (params: Partial<MissedFilters>) => get<MissedOptions>('/options', params)
export const fetchMissedDetail = (id: number) => get<MissedDetail>(`/${id}`)

export function defaultMissedFilters(): MissedFilters {
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  const first = new Date(`${today.slice(0, 7)}-01T00:00:00Z`)
  const start = new Date(first); start.setUTCDate(start.getUTCDate() - 7)
  const end = new Date(first); end.setUTCMonth(end.getUTCMonth() + 1); end.setUTCDate(0)
  return { startDate: start.toISOString().slice(0, 10), endDate: end.toISOString().slice(0, 10), otaOrderNo: '', platform: '', airline: '', operator: '', group: '', depCity: '', arrCity: '', jobType: '', businessType: '', minPrice: '', maxPrice: '', sortBy: 'issueTicketTime', direction: 'desc' }
}
