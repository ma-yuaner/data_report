import { http, type ApiEnvelope } from './http'

export interface KpiItem {
  key: string
  label: string
  value: string
  unit: string
  change: number | null
  tone: 'neutral' | 'pending' | 'risk'
}

export interface ProfitMetric {
  key: 'issue' | 'refund' | 'change' | 'ancillary'
  label: string
  countLabel: string
  count: number | null
  segmentLabel: string | null
  segmentCount: number | null
  profit: number | null
  timeField: string
  available: boolean
  error: string | null
}

export interface OverviewData {
  mode: 'mock' | 'live'
  source: string
  generatedAt: string
  cacheHit: boolean
  period: { startDate: string; endDate: string }
  status: { label: string; freshness: string; metricState: string }
  totalProfit: { value: number | null; available: boolean }
  metrics: ProfitMetric[]
  notes: string[]
}

export interface RiskProfitMetric {
  key: 'issue' | 'refund' | 'change'
  label: string
  table: string
  timeField: 'business_date' | 'stat_date'
  ticketCount: number | null
  estimatedProfit: number | null
  available: boolean
  error: string | null
}

export interface RiskProfitSummaryData {
  source: string
  generatedAt: string
  cacheHit: boolean
  available: boolean
  period: { startDate: string; endDate: string; monthLabel: string }
  metrics: RiskProfitMetric[]
  notes: string[]
  filters: RiskProfitFilters
}

export type RiskDimensionKey = 'platform' | 'site' | 'department' | 'airline' | 'supplier'
export interface RiskProfitFilters extends Record<RiskDimensionKey, string> {
  profitStatus: 'all' | 'loss' | 'profit' | 'zero'
}
export interface RiskFilterOptionsData {
  source: string
  field: RiskDimensionKey
  options: string[]
  truncated: boolean
  available: boolean
  errors: string[]
  cacheHit: boolean
}

export interface IssueProfitSummary {
  issueCount: number
  segmentCount: number
  profit: number
  averageProfit: number
  lossCount: number
  lossRate: number
  profitCount: number
  zeroProfitCount: number
}

export interface DimensionProfitItem {
  name: string
  count: number
  profit: number
}

export interface FieldCompletenessItem {
  field: string
  label: string
  usage: string
  nonNullCount: number
  totalCount: number
  rate: number
  state: 'ready' | 'partial' | 'missing'
}

export interface IssueProfitAnalysisData {
  mode: 'mock' | 'live'
  source: string
  available: boolean
  error: string | null
  generatedAt: string
  cacheHit: boolean
  period: { startDate: string; endDate: string }
  summary: IssueProfitSummary | null
  trend: { granularity: 'day' | 'month'; items: Array<{ period: string; count: number; profit: number }> }
  dimensions: Record<'platform' | 'airline' | 'supplier' | 'organization', DimensionProfitItem[]>
  completeness: FieldCompletenessItem[]
  coverageSummary: { averageRate: number; ready: number; partial: number; missing: number; total: number } | null
}

export type BusinessProfitType = 'refund' | 'change' | 'ancillary'

export interface BusinessProfitAnalysisData {
  mode: 'mock' | 'live'
  source: string
  available: boolean
  error: string | null
  generatedAt: string
  cacheHit: boolean
  business: {
    key: BusinessProfitType
    name: string
    countLabel: string
    segmentLabel: string | null
    timeField: string
    profitField: string
    conditionLabel: string
  }
  period: { startDate: string; endDate: string }
  summary: {
    count: number
    segmentCount: number | null
    profit: number
    averageProfit: number
    negativeCount: number
    negativeRate: number
  } | null
  trend: {
    granularity: 'day' | 'month'
    items: Array<{ period: string; count: number; segmentCount: number | null; profit: number; negativeCount: number }>
  }
}

export interface DataAssetItem {
  key: 'issue' | BusinessProfitType
  domain: string
  database: string
  table: string
  timeField: string
  columnCount: number | null
  metrics: string[]
  condition: string
  state: 'configured' | 'ready' | 'empty' | 'warning' | 'error'
  latestDataTime: string | null
  error: string | null
}

export interface MetricDefinitionItem {
  name: string
  formula: string
  timeField: string
  stage: string
  status: 'current'
}

export interface AssetCatalogData {
  mode: 'mock' | 'live'
  source: string
  generatedAt: string
  cacheHit: boolean
  assets: DataAssetItem[]
  metrics: MetricDefinitionItem[]
  analyses: AnalysisAssetItem[]
  analysisTaskCount: number
}

export interface AnalysisAssetItem {
  domain: string
  taskCount: number
  maturity: string
  representative: string
  plan: string
}

export interface ProfitProblemBusiness {
  key: ProfitMetric['key']
  name: string
  negativeCount: number | null
  lossAmount: number | null
  lossShare: number
  available: boolean
  error: string | null
}

export interface ProfitProblemItem {
  businessKey: ProfitMetric['key']
  businessName: string
  eventId: string
  orderNo: string
  ticketNo: string
  platform: string
  supplier: string
  airline: string
  operator: string
  occurredAt: string
  profit: number
}

export interface ProfitProblemData {
  mode: 'mock' | 'live'
  source: string
  available: boolean
  generatedAt: string
  cacheHit: boolean
  period: { startDate: string; endDate: string }
  summary: {
    negativeCount: number
    lossAmount: number
    affectedBusinessCount: number
    availableBusinessCount: number
  } | null
  businesses: ProfitProblemBusiness[]
  items: ProfitProblemItem[]
  notes: string[]
}

export interface IssueItem {
  id: string
  category: string
  object: string
  title: string
  impact: string
  owner: string
  status: string
  level: string
}

export interface CoverageItem {
  domain: string
  state: 'ready' | 'building' | 'partial' | 'missing' | 'pending'
  label: string
  coverage: number
  canAnswer: string
}

export async function getOverview(params?: { startDate: string; endDate: string }) {
  const response = await http.get<ApiEnvelope<OverviewData>>('/v1/dashboard/overview', { params })
  return response.data.data
}

export async function getRiskProfitSummary(params: { startDate: string; endDate: string } & Partial<RiskProfitFilters>) {
  const response = await http.get<ApiEnvelope<RiskProfitSummaryData>>('/v1/dashboard/risk-profit-summary', { params })
  return response.data.data
}

export async function getRiskProfitFilterOptions(
  params: { startDate: string; endDate: string; field: RiskDimensionKey; search?: string } & Partial<RiskProfitFilters>,
) {
  const response = await http.get<ApiEnvelope<RiskFilterOptionsData>>('/v1/dashboard/risk-profit-filter-options', { params })
  return response.data.data
}

export async function getIssueProfitAnalysis(params: { startDate: string; endDate: string }) {
  const response = await http.get<ApiEnvelope<IssueProfitAnalysisData>>('/v1/analysis/issue-profit', { params })
  return response.data.data
}

export async function getBusinessProfitAnalysis(businessType: BusinessProfitType, params: { startDate: string; endDate: string }) {
  const response = await http.get<ApiEnvelope<BusinessProfitAnalysisData>>(`/v1/analysis/business-profit/${businessType}`, { params })
  return response.data.data
}

export async function getAssetCatalog() {
  const response = await http.get<ApiEnvelope<AssetCatalogData>>('/v1/assets/catalog')
  return response.data.data
}

export async function getProfitProblems(params: { startDate: string; endDate: string }) {
  const response = await http.get<ApiEnvelope<ProfitProblemData>>('/v1/problems/profit-loss', { params })
  return response.data.data
}

export async function getIssues() {
  const response = await http.get<ApiEnvelope<{ mode: string; items: IssueItem[]; total: number }>>('/v1/issues')
  return response.data.data
}

export async function getCoverage() {
  const response = await http.get<ApiEnvelope<{ mode: string; items: CoverageItem[]; total: number }>>('/v1/assets/coverage')
  return response.data.data
}
