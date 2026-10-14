import { http, type ApiEnvelope } from './http'

export type GovernanceLayer = 'ota' | 'gds'
export type GovernanceDimension = 'platform' | 'site' | 'gds' | 'pcc' | 'apiGroup'

export interface GovernanceScope {
  startDate: string
  endDate: string
  dataSource: GovernanceLayer
  groupBy: GovernanceDimension
  platform: string
  site: string
  gds: string
  pcc: string
  apiGroup: string
}

export interface GovernanceMetric {
  rowCount: number
  searchRequests: number
  searchSuccess: number
  verifyRequests: number
  verifySuccess: number
  orderRequests: number
  orderSuccess: number
  pnrCount: number | null
  pnrMissingRowCount: number | null
  queryToPnrRatio: string | null
  ratioInfinite: boolean
  searchSuccessRate: string | null
  verifySuccessRate: string | null
  orderSuccessRate: string | null
  searchCacheRate: string | null
  verifyCacheRate: string | null
  orderCacheRate: string | null
  avgSearchExecuteTime: string | null
  avgVerifyExecuteTime: string | null
  avgOrderExecuteTime: string | null
  searchPriceChangeRate: string | null
  verifyPriceChangeRate: string | null
  orderPriceChangeRate: string | null
  excessQueryCount: number | null
  targetRatio: number | null
  successTargets: Partial<Record<'search' | 'verify' | 'order', string>>
  status: 'no_records' | 'not_applicable' | 'pnr_field_missing' | 'pnr_data_missing' | 'pnr_partial' | 'denominator_zero' | 'ready'
  sourceUpdatedAt?: string | null
}

export interface GovernanceData {
  source: string
  table: string
  available: boolean
  error: string
  generatedAt: string
  period: { startDate: string; endDate: string }
  dataSource: { key: GovernanceLayer; value: number; label: string }
  targetRatio: number | null
  gdsTargets: Record<string, number>
  otaSuccessTargets: Record<string, Partial<Record<'search' | 'verify' | 'order', string>>>
  pnrApplicable: boolean
  pnrColumnAvailable: boolean
  pnrDataAvailable: boolean
  filters: Record<GovernanceDimension, string>
  options: Record<GovernanceDimension, string[]>
  summary: GovernanceMetric
  trend: Array<{ date: string } & GovernanceMetric>
  dimension: { key: GovernanceDimension; label: string; rows: Array<{ value: string; name: string } & GovernanceMetric> }
  notes: string[]
}

export async function fetchResourceGovernance(scope: GovernanceScope): Promise<GovernanceData> {
  const response = await http.get<ApiEnvelope<GovernanceData>>(`/v1/resource-governance/${scope.dataSource}/overview`, { params: scope })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
