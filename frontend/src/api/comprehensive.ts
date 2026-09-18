import { http, type ApiEnvelope } from './http'

export type BusinessKey = 'issue' | 'refund' | 'change' | 'ancillary'
export type DimensionKey = 'platform' | 'site' | 'airline' | 'product'
export interface Metric {
  count: number | null
  profit: string | null
  knownProfit: string | null
  profitMissingCount: number
  productMissingCount: number
}
export type Metrics = Record<BusinessKey, Metric>
export interface DimensionRow {
  key: string
  value: string
  name: string
  metrics: Metrics
  totalProfit: string | null
}
export interface ComprehensiveData {
  source: string
  available: boolean
  error: string
  period: { startDate: string; endDate: string }
  coverage: { missingDays: string[]; availableDays: string[]; updatedAt: string }
  metrics: Metrics
  totalProfit: string | null
  trend: { period: string; metrics: Metrics; totalProfit: string | null }[]
  comparison: DimensionRow[]
  options: Record<DimensionKey, { label: string; value: string }[]>
  notes: string[]
}
export interface FilterScope {
  preset: string
  startDate: string
  endDate: string
  platform: string
  site: string
  airline: string
  product: string
}
export async function fetchComprehensive(scope: FilterScope, groupBy: DimensionKey): Promise<ComprehensiveData> {
  const { preset: _preset, ...params } = scope
  const response = await http.get<ApiEnvelope<ComprehensiveData>>('/v1/analysis/comprehensive', { params: { ...params, groupBy } })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
