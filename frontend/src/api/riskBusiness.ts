import { http, type ApiEnvelope } from './http'

export type RiskBusinessKey = 'issue' | 'refund' | 'change'
export type RiskGroupKey = 'platform' | 'site' | 'department' | 'airline' | 'supplier' | 'policy' | 'reason' | 'verifyResult'
export type ProfitStatus = 'all' | 'loss' | 'profit' | 'zero'

export interface RiskBusinessScope {
  startDate: string
  endDate: string
  platform: string
  site: string
  department: string
  airline: string
  supplier: string
  policy: string
  reason: string
  verifyResult: string
  profitStatus: ProfitStatus
  groupBy: RiskGroupKey
  page: number
  pageSize: number
}

export interface RiskBusinessMetric {
  rowCount: number
  ticketCount: number | null
  knownTicketCount: number | null
  ticketMissingCount: number
  estimatedProfit: string | null
  knownProfit: string | null
  profitMissingCount: number
  lossTicketCount: number | null
  lossEstimatedProfit: string | null
  averageLossPerTicket: string | null
  lossTicketShare: string | null
  profitTicketCount: number | null
  zeroTicketCount: number | null
  status: 'no_records' | 'incomplete' | 'ready'
}

export interface RiskDimensionRow extends RiskBusinessMetric {
  key: string
  name: string
  value: string | null
}

export interface RiskOrderRow {
  recordKey: string
  businessDate: string
  otaOrderNo: string
  relationOrderNo: string
  issueTicketNo: string
  serviceOrderNo: string
  passengerName: string | null
  platform: string | null
  site: string | null
  department: string | null
  airline: string | null
  route: string | null
  supplier: string | null
  policyOperator: string | null
  operator: string | null
  reason: string | null
  profitRemark: string | null
  verifyResult: string | null
  ticketCount: number | null
  estimatedProfit: string | null
  actualProfit: string | null
}

export interface RiskBusinessData {
  available: boolean
  error: string
  source: string
  generatedAt: string
  business: { key: RiskBusinessKey; label: string }
  period: { startDate: string; endDate: string; timeField: string }
  filters: Omit<RiskBusinessScope, 'startDate' | 'endDate' | 'groupBy' | 'page' | 'pageSize'>
  availableGroups: { key: RiskGroupKey; label: string }[]
  groupBy: RiskGroupKey
  reasonAvailable: boolean
  summary: RiskBusinessMetric
  trend: ({ period: string } & RiskBusinessMetric)[]
  dimensions: RiskDimensionRow[]
  orders: { page: number; pageSize: number; total: number; rows: RiskOrderRow[] }
  notes: string[]
}

export async function fetchRiskBusiness(business: RiskBusinessKey, scope: RiskBusinessScope): Promise<RiskBusinessData> {
  const response = await http.get<ApiEnvelope<RiskBusinessData>>(`/v1/analysis/risk-business/${business}`, { params: scope })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
