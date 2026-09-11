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

export async function getIssues() {
  const response = await http.get<ApiEnvelope<{ mode: string; items: IssueItem[]; total: number }>>('/v1/issues')
  return response.data.data
}

export async function getCoverage() {
  const response = await http.get<ApiEnvelope<{ mode: string; items: CoverageItem[]; total: number }>>('/v1/assets/coverage')
  return response.data.data
}
