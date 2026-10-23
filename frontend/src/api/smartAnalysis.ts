import { http, type ApiEnvelope } from './http'

export type SmartType = 'all' | 'down' | 'void'
export type SmartStage = 'all' | 'participation' | 'unparticipated' | 'success' | 'use' | 'unsuccessful' | 'unused' | 'refund'
export type SmartTrendDate = 'issue' | 'departure' | 'order'

export interface SmartFilters {
  startDate: string
  endDate: string
  firstDepStart: string
  firstDepEnd: string
  orderStart: string
  orderEnd: string
  airline: string
  platform: string
  site: string
  policy: string
  leader: string
  member: string
  supplier: string
  gds: string
  productType: string
  depAirport: string
  arrAirport: string
  route: string
  depCity: string
  arrCity: string
  depCountry: string
  arrCountry: string
  depZone: string
  arrZone: string
  depArea: string
  arrArea: string
  flightWay: string
  transferType: string
  orderSource: string
  routeCategory: string
  ageType: string
  ndc: string
  routeLength: string
  cityRoute: string
  countryRoute: string
  zoneRoute: string
  tcRoute: string
  profitBand: string
  otaOrderNo: string
}

export interface SmartMetricSet {
  participatedCount: number | null
  succeededCount: number | null
  usedCount: number | null
  profit: string | null
  participationRate: number | null
  successRate: number | null
  adoptionRate: number | null
  participationUseRate: number | null
  useRate: number | null
  averageProfit: string | null
}

export interface SmartMetrics {
  ticketCount: number | null
  totalProfit: string | null
  segmentCount: number | null
  refundCount: number | null
  perSegmentProfit: string | null
  smart: SmartMetricSet
  down: SmartMetricSet
  void: SmartMetricSet
}

export interface SmartOverviewData {
  source: string
  available: boolean
  hasData: boolean
  error: string
  period: { startDate: string; endDate: string }
  trend: { dateType: SmartTrendDate; dateLabel: string; cutoffSource: string; cutoffDate: string; dailyStartDate: string; monthlyStartDate: string }
  updatedAt: string
  metrics: SmartMetrics
  dailyTrend: { period: string; metrics: SmartMetrics }[]
  monthlyTrend: { period: string; metrics: SmartMetrics }[]
  notes: string[]
}

export interface SmartDimensionPath {
  key: keyof SmartFilters
  label: string
  value: string
  name: string
}

export interface SmartDimensionData {
  source: string
  available: boolean
  hasData: boolean
  error: string
  period: { startDate: string; endDate: string }
  dimensions: { key: keyof SmartFilters; label: string }[]
  page: number
  pageSize: number
  total: number
  totals: SmartMetrics
  rows: { key: string; path: SmartDimensionPath[]; metrics: SmartMetrics }[]
  updatedAt: string
}

export interface SmartPlacementCoverageTask {
  id: number
  taskNo: string
  opportunityName: string
  status: string
  priority: string
  platformName: string
  siteName: string | null
  airlineCode: string
  departureCode: string | null
  arrivalCode: string | null
  routeText: string | null
  productType: string | null
  orderSource: string | null
  analysisStartDate: string
  analysisEndDate: string
  currentAssigneeName: string | null
  monitoringStartedAt: string | null
  externalPolicyId: string | null
  matchedOrderCount: number
  updatedAt: string
}

export interface SmartPlacementCoverage {
  available: boolean
  error: string
  truncated: boolean
  period: { startDate: string; endDate: string }
  summary: {
    taskCount: number
    monitoringTaskCount: number
    workflowTaskCount: number
    matchedOrderCount: number
    statusCounts: Record<string, number>
  }
  rows: SmartPlacementCoverageTask[]
}

export interface SmartComprehensiveData {
  overview: SmartOverviewData
  dimensions: SmartDimensionData
  placement: SmartPlacementCoverage
}

export type SmartDetailValueType = 'text' | 'date' | 'datetime' | 'count' | 'money' | 'boolean'
export interface SmartDetailColumn {
  key: string
  title: string
  valueType: SmartDetailValueType
  category: string
  width: number
}
export interface SmartDetailData {
  source: string
  available: boolean
  hasData: boolean
  error: string
  period: { startDate: string; endDate: string }
  page: number
  pageSize: number
  total: number
  summary: { ticketCount: number | null; orderCount: number | null; profit: string | null }
  columns: SmartDetailColumn[]
  availableColumns: SmartDetailColumn[]
  rows: ({ recordKey: string } & Record<string, string | number | boolean | null>)[]
  updatedAt: string
}

export interface SmartTicketData {
  source: string
  available: boolean
  found: boolean
  error: string
  columns: SmartDetailColumn[]
  record: Record<string, string | number | boolean | null> | null
}

export interface SmartViewTemplate<T extends Record<string, unknown> = Record<string, unknown>> {
  id: number
  scope: 'dimension-analysis' | 'detail-fields'
  name: string
  value: T
  ownerUserId: number
  ownerName: string
  isOwner: boolean
  isPublic: boolean
  updatedAt: string
}

export const dimensionOptions = [
  ['airline', '航司'], ['platform', 'OTA平台'], ['site', 'OTA站点'], ['policy', '政策员'],
  ['leader', '组长'], ['member', '组员'], ['supplier', '出票供应商'], ['gds', 'GDS系统'],
  ['productType', '产品类型'], ['depAirport', '出发机场'], ['arrAirport', '到达机场'],
  ['route', '航线'], ['depCity', '出发城市'], ['arrCity', '到达城市'],
  ['depCountry', '出发国家'], ['arrCountry', '到达国家'], ['depZone', '出发大区'],
  ['arrZone', '到达大区'], ['depArea', '出发TC区'], ['arrArea', '到达TC区'],
  ['flightWay', '航程类型'], ['transferType', '航段类型'], ['orderSource', '订单来源'],
  ['routeCategory', '航线类别'], ['ageType', '乘客类型'], ['ndc', 'NDC标识'],
  ['routeLength', '长短航线'], ['cityRoute', '城市航线'], ['countryRoute', '国家航线'],
  ['zoneRoute', '大区航线'], ['tcRoute', 'TC区航线'],
  ['profitBand', '利润区间'],
].map(([value, label]) => ({ value, label }))

function cleanFilters(filters: SmartFilters) {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''))
}

export const smartAnalysisApi = {
  comprehensive: (filters: SmartFilters, params: { groupBy: string; smartType: SmartType; sortBy: string; direction: 'asc' | 'desc'; page: number; pageSize: number }) => http.get<ApiEnvelope<SmartComprehensiveData>>('/v1/smart-analysis/comprehensive', { params: { ...cleanFilters(filters), ...params } }).then(response => response.data.data),
  overview: (filters: SmartFilters, trendDate: SmartTrendDate) => http.get<ApiEnvelope<SmartOverviewData>>('/v1/smart-analysis/overview', { params: { ...cleanFilters(filters), trendDate } }).then(response => response.data.data),
  trends: (filters: SmartFilters, trendDate: SmartTrendDate) => http.get<ApiEnvelope<SmartOverviewData>>('/v1/smart-analysis/trends', { params: { ...cleanFilters(filters), trendDate } }).then(response => response.data.data),
  dimensions: (filters: SmartFilters, params: { groupBy: string[]; smartType: SmartType; sortBy: string; direction: 'asc' | 'desc'; page: number; pageSize: number }) => http.get<ApiEnvelope<SmartDimensionData>>('/v1/smart-analysis/dimensions', { params: { ...cleanFilters(filters), ...params, groupBy: params.groupBy.join(',') } }).then(response => response.data.data),
  details: (filters: SmartFilters, params: { smartType: SmartType; stage: SmartStage; fields: string[]; page: number; pageSize: number }) => http.get<ApiEnvelope<SmartDetailData>>('/v1/smart-analysis/details', { params: { ...cleanFilters(filters), ...params, fields: params.fields.join(',') } }).then(response => response.data.data),
  ticket: (issueId: string) => http.get<ApiEnvelope<SmartTicketData>>(`/v1/smart-analysis/tickets/${encodeURIComponent(issueId)}`).then(response => response.data.data),
  filterOptions: (filters: SmartFilters, field: string, search = '') => http.get<ApiEnvelope<{ available: boolean; error: string; field: string; options: { value: string; label: string }[]; truncated: boolean }>>('/v1/smart-analysis/filter-options', { params: { ...cleanFilters(filters), field, search } }).then(response => response.data.data),
  templates: <T extends Record<string, unknown>>(scope: 'dimension-analysis' | 'detail-fields') => http.get<ApiEnvelope<{ scope: string; rows: SmartViewTemplate<T>[] }>>('/v1/smart-analysis/templates', { params: { scope } }).then(response => response.data.data.rows),
  saveTemplate: <T extends Record<string, unknown>>(input: { id?: number; scope: 'dimension-analysis' | 'detail-fields'; name: string; value: T; isPublic: boolean }) => http.post<ApiEnvelope<SmartViewTemplate<T>>>('/v1/smart-analysis/templates', input).then(response => response.data.data),
  deleteTemplate: (id: number) => http.delete<ApiEnvelope<{ id: number }>>(`/v1/smart-analysis/templates/${id}`).then(response => response.data.data),
}
