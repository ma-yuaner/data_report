import { http, type ApiEnvelope } from './http'

export interface KpiItem {
  key: string
  label: string
  value: string
  unit: string
  change: number | null
  tone: 'neutral' | 'pending' | 'risk'
}

export interface OverviewData {
  mode: 'mock' | 'live'
  generatedAt: string
  status: { label: string; freshness: string; metricState: string }
  kpis: KpiItem[]
  trend: { dates: string[]; orders: number[]; tickets: number[] }
  lifecycle: Array<{ stage: string; value: number; state: string }>
  focus: Array<{ title: string; type: string; level: string; action: string }>
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

export async function getOverview() {
  const response = await http.get<ApiEnvelope<OverviewData>>('/v1/dashboard/overview')
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

