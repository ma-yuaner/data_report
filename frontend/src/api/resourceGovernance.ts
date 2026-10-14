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
  queryToPnrRatio: string | null
  ratioInfinite: boolean
  searchSuccessRate: string | null
  verifySuccessRate: string | null
  orderSuccessRate: string | null
  searchCacheRate: string | null
  avgSearchExecuteTime: string | null
  excessQueryCount: number | null
  status: 'no_records' | 'pnr_field_missing' | 'pnr_data_missing' | 'denominator_zero' | 'ready'
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
  targetRatio: number
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
  const response = await http.get<ApiEnvelope<GovernanceData>>('/v1/resource-governance/overview', { params: scope })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
