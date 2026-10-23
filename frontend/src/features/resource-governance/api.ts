import { http, type ApiEnvelope } from '@/api/http'

export type GovernanceLayer = 'ota' | 'gds'
export type GovernanceDimension = 'platform' | 'site' | 'gds' | 'resourceChannel' | 'pcc' | 'apiGroup' | 'combination'

export interface GovernanceScope {
  startDate: string
  endDate: string
  dataSource: GovernanceLayer
  groupBy: GovernanceDimension
  platform: string
  site: string
  gds: string
  resourceChannel: string
  pcc: string
  apiGroup: string
  breachOnly?: boolean
  combination?: string
}

export interface GovernanceMetric {
  rowCount: number
  searchRequests: number
  searchSuccess: number
  searchFailure: number
  verifyRequests: number
  verifySuccess: number
  verifyFailure: number
  orderRequests: number
  orderSuccess: number
  orderFailure: number
  segmentCount: number | null
  segmentMissingRowCount: number | null
  queryToSegmentRatio: string | null
  ratioInfinite: boolean
  searchSuccessRate: string | null
  searchFailureRate: string | null
  verifySuccessRate: string | null
  verifyFailureRate: string | null
  orderSuccessRate: string | null
  orderFailureRate: string | null
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
  status:
    | 'no_records'
    | 'not_applicable'
    | 'segment_field_missing'
    | 'segment_data_missing'
    | 'segment_partial'
    | 'denominator_zero'
    | 'ready'
  breach: boolean
  breachReasons: string[]
  sourceUpdatedAt?: string | null
  gds?: string
  pcc?: string
  platform?: string
  site?: string
  targetSource?: string
  preciseScope?: boolean
}

export interface GovernanceChannelMetric extends GovernanceMetric {
  value: 'MP' | 'MPIS'
  name: string
  ratioApplicable: boolean
  queryShare: string | null
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
  ratioApplicable: boolean
  segmentColumnAvailable: boolean
  segmentDataAvailable: boolean
  breachOnly: boolean
  breachObjectCount: number
  filters: Record<GovernanceDimension, string>
  options: Record<GovernanceDimension, string[]>
  summary: GovernanceMetric
  trend: Array<{ date: string } & GovernanceMetric>
  apiGroups: Array<{ value: string; name: string } & GovernanceMetric>
  resourceChannels: GovernanceChannelMetric[]
  resourceStructure: {
    totalSearchRequests: number
    mpSearchRequests: number
    mpisSearchRequests: number
    mpisShare: string | null
  }
  dimension: {
    key: GovernanceDimension
    label: string
    rows: Array<{ value: string; name: string } & GovernanceMetric>
    limit?: number
    truncated?: boolean
    rankingScope?: string
  }
  notes: string[]
}

export async function fetchResourceGovernance(scope: GovernanceScope): Promise<GovernanceData> {
  const response = await http.get<ApiEnvelope<GovernanceData>>(`/v1/resource-governance/${scope.dataSource}/overview`, {
    params: scope,
  })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
export interface GdsRouteScope {
  startDate: string
  endDate: string
  platform?: string
  site?: string
  gds?: string
  pcc?: string
  resourceChannel?: string
  apiGroup?: string
  route?: string
  keyword?: string
}

export interface GdsRouteMetric {
  requestCount: number
  searchRequests: number
  searchSuccess: number
  searchFailure: number
  searchResultSuccess: number
  searchPriceCount: number
  searchTimeouts: number
  searchCacheCount: number
  searchSuccessRate: string | null
  searchResultSuccessRate: string | null
  searchTimeoutRate: string | null
  searchCacheRate: string | null
  avgSearchExecuteTime: string | null
  verifyRequests: number
  verifySuccess: number
  verifyFailure: number
  verifySuccessRate: string | null
  verifyTimeoutRate: string | null
  verifyPriceChangeRate: string | null
  avgVerifyExecuteTime: string | null
  orderRequests: number
  orderSuccess: number
  orderFailure: number
  orderSuccessRate: string | null
  orderTimeoutRate: string | null
  orderPriceChangeRate: string | null
  avgOrderExecuteTime: string | null
  mpSearchRequests: number
  mpisSearchRequests: number
  ndcSearchRequests: number
  mpShare: string | null
  mpisShare: string | null
  ndcShare: string | null
  directFlightCount: number
  connectingFlightCount: number
  sourceUpdatedAt: string | null
}

export interface GdsRouteMetricRow extends GdsRouteMetric {
  id: string
  route: string
  depCity: string
  arrCity: string
  depAirport: string
  arrAirport: string
  platform: string
  site: string
  gdsCode: string
  pccCode: string
}

export interface GdsRouteAnalysisData {
  source: string
  table: string
  available: boolean
  queryReady: boolean
  generatedAt: string
  period: { startDate: string; endDate: string }
  filters: Record<string, string>
  summary: GdsRouteMetric
  rows: GdsRouteMetricRow[]
  rowCount: number
  resultLimit: number
  truncated: boolean
  options: Record<'gds' | 'pcc' | 'platform' | 'site' | 'apiGroup', string[]>
  notes: string[]
}

export async function fetchGdsRouteAnalysis(scope: GdsRouteScope): Promise<GdsRouteAnalysisData> {
  const response = await http.get<ApiEnvelope<GdsRouteAnalysisData>>('/v1/resource-governance/gds/routes', {
    params: scope,
    timeout: 180_000,
  })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
