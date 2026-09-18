import { http, type ApiEnvelope } from './http'

export type RiskBusinessKey = 'issue' | 'change' | 'refund'
export interface RiskMetric {
  rowCount: number | null
  ticketCount: number | null
  estimatedProfit: string | null
  knownTicketCount: number | null
  knownProfit: string | null
  ticketMissingCount: number
  profitMissingCount: number
  status: 'unavailable' | 'no_records' | 'incomplete' | 'ready'
}
export interface RiskScope {
  startDate: string
  endDate: string
  businessType: 'all' | RiskBusinessKey
  profitStatus: 'all' | 'loss' | 'profit' | 'zero'
  dateBasis: 'overview' | 'reconcile'
}
export interface RiskMonthlyData {
  source: string
  available: boolean
  error: string
  generatedAt: string
  period: { startDate: string; endDate: string }
  filters: Omit<RiskScope, 'startDate' | 'endDate'>
  businesses: { key: RiskBusinessKey; label: string; table: string; timeField: string; metrics: RiskMetric }[]
  summary: RiskMetric
  months: { month: string; label: string; isPartial: boolean; metrics: Partial<Record<RiskBusinessKey, RiskMetric>>; summary: RiskMetric }[]
  notes: string[]
}
export async function getRiskMonthly(scope: RiskScope): Promise<RiskMonthlyData> {
  const response = await http.get<ApiEnvelope<RiskMonthlyData>>('/v1/analysis/risk-monthly', { params: scope })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
