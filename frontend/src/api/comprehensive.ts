import { http, type ApiEnvelope } from './http'

export type BusinessKey = 'issue' | 'refund' | 'change' | 'ancillary'
export type DimensionKey = 'platform' | 'site' | 'airline' | 'product' | 'policy'
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
  policy: string
}
export type ComprehensiveDetailValueType = 'text' | 'date' | 'datetime' | 'count' | 'money'
export interface ComprehensiveDetailColumn {
  key: string
  title: string
  valueType: ComprehensiveDetailValueType
  width: number
}
export type ComprehensiveDetailRow = { recordKey: string } & Record<string, string | number | null>
export interface ComprehensiveDetailData {
  available: boolean
  error: string
  source: string
  business: { key: BusinessKey; label: string }
  period: { startDate: string; endDate: string }
  columns: ComprehensiveDetailColumn[]
  page: number
  pageSize: number
  total: number
  rows: ComprehensiveDetailRow[]
}
export interface ComprehensiveDiagnosisData {
  source: string
  available: boolean
  error: string
  current: ComprehensiveData
  previous: Pick<ComprehensiveData, 'available' | 'error' | 'period' | 'coverage' | 'metrics' | 'totalProfit'>
  changes: {
    totalProfit: string | null
    metrics: Record<BusinessKey, { count: number | null; profit: string | null }>
  }
  notes: string[]
}
export async function fetchComprehensive(scope: FilterScope, groupBy: DimensionKey): Promise<ComprehensiveData> {
  const { preset: _preset, ...params } = scope
  const response = await http.get<ApiEnvelope<ComprehensiveData>>('/v1/analysis/comprehensive', { params: { ...params, groupBy } })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export async function fetchComprehensiveDiagnosis(scope: FilterScope, groupBy: DimensionKey): Promise<ComprehensiveDiagnosisData> {
  const { preset: _preset, ...params } = scope
  const response = await http.get<ApiEnvelope<ComprehensiveDiagnosisData>>('/v1/analysis/comprehensive/diagnosis', { params: { ...params, groupBy } })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export async function fetchComprehensiveDetails(scope: FilterScope, businessType: BusinessKey, page = 1, pageSize = 50): Promise<ComprehensiveDetailData> {
  const { preset: _preset, ...params } = scope
  const response = await http.get<ApiEnvelope<ComprehensiveDetailData>>('/v1/analysis/comprehensive/details', { params: { ...params, businessType, page, pageSize } })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
