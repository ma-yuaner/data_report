import { http, type ApiEnvelope } from './http'
import type { ComprehensiveDetailData, DimensionKey, FilterScope } from './comprehensive'

export const profitGroups = { gain: '盈利', loss: '冲量', total: '整体' } as const
export type ProfitGroup = keyof typeof profitGroups
export type Drilldown = { date: string; group: ProfitGroup; snapshotVersion: string }
export interface ProfitMetric {
  segmentCount: number | null
  profit: string | null
  adsProjectedKnownProfit: string
  knownProfitProjectionDifference: string
  perSegmentProfit: string | null
  recordCount: number
  ticketCount: number
  unrecognizedTicketRecords: number
  segmentMissingCount: number
  profitMissingCount: number
}
export type ProfitTotals = Record<ProfitGroup | 'unclassified', ProfitMetric>
export interface ProfitVolumeData {
  snapshotVersion: string
  rows: (ProfitTotals & { date: string })[]
  summary: ProfitTotals
  adsReconciliation: 'matched' | 'different' | 'unavailable'
  adsDifferenceDays: string[]
}
type Unavailable = { available: false; error: string; missingDays?: string[] }

export async function fetchProfitVolume(scope: FilterScope, signal: AbortSignal) {
  const { preset: _preset, ...params } = scope
  const { data } = await http.get<ApiEnvelope<(ProfitVolumeData & { available: true }) | Unavailable>>(
    '/v1/analysis/issue-profit/profit-volume', { params, signal },
  )
  return data.data
}

export async function fetchProfitVolumeDetails(scope: FilterScope, drill: Drilldown, page: number, pageSize: number, signal?: AbortSignal) {
  const { preset: _preset, ...params } = scope
  const { data } = await http.get<ApiEnvelope<(ComprehensiveDetailData & { ticketCount: number; unrecognizedTicketRecords: number }) | Unavailable>>(
    '/v1/analysis/issue-profit/profit-volume/details',
    { params: { ...params, issueDate: drill.date, group: drill.group, snapshotVersion: drill.snapshotVersion, page, pageSize }, signal },
  )
  return data.data
}

export async function fetchProfitVolumeDimension(scope: FilterScope, drill: Drilldown, dimension: DimensionKey, signal: AbortSignal) {
  const { preset: _preset, ...params } = scope
  const { data } = await http.get<ApiEnvelope<{ available: true; total: ProfitMetric; rows: (ProfitMetric & { label: string; value: string })[] } | Unavailable>>(
    '/v1/analysis/issue-profit/profit-volume',
    { params: { ...params, issueDate: drill.date, group: drill.group, snapshotVersion: drill.snapshotVersion, dimension }, signal },
  )
  return data.data
}
