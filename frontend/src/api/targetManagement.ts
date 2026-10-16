import { http, type ApiEnvelope } from './http'

export type TargetScene = 'PLATFORM' | 'GDS' | 'POLICY'
export type TargetStatus = 'ACTIVE' | 'DRAFT' | 'PAUSED' | 'CLOSED' | 'VOID'

export interface TargetMetric {
  code: string
  name: string
  version: string
  unitCode: string
  dateBasis: string
  sourceSystem: string
  measureCode: string
  supportedScenes: string[]
  definition: string
  filterDescription?: string | null
}

export interface TargetOption { code: string; name: string }
export interface TargetUserOption { id: number; username: string; name: string }
export interface TargetOptions {
  available: boolean
  platforms: TargetOption[]
  gds: TargetOption[]
  users: TargetUserOption[]
  departments: TargetOption[]
  policyGroups: TargetOption[]
}

export interface TargetGdsMeasure {
  itemId: number
  target: number
  actual: number | null
  yesterday: number | null
  dataStatus: string
}

export interface TargetRow {
  id: string
  itemId: number
  itemIds: Record<string, number>
  planId: number
  scene: 'platform' | 'gds' | 'policy'
  period: string
  departmentCode: string
  department: string
  platformCode: string
  platform?: string | null
  gds?: string | null
  policyCode: string
  policy?: string | null
  ownerUserId?: number | null
  owner: string
  metric: string
  metricCode: string
  metricVersion: string
  target: number
  actual: number | null
  yesterday: number | null
  expectedRate: number | null
  completionRate: number | null
  progressGapRate: number | null
  remaining: number | null
  requiredDaily: number | null
  profit: number | null
  profitPerSegment: number | null
  status: TargetStatus
  dataStatus: string
  dataThroughDate?: string | null
  remark: string
  gdsBreakdown?: Record<string, TargetGdsMeasure>
}

export interface TargetListResult {
  available: boolean
  scene: TargetScene
  period: string
  rows: TargetRow[]
  summary: {
    target: number
    actual: number | null
    completionRate: number | null
    behind: number
    configuredCount: number
    progressReadyCount: number
  }
  dataThroughDate?: string | null
}

export interface SaveTargetInput {
  scene: TargetScene
  period: string
  departmentCode?: string
  departmentName: string
  platformCode?: string
  platformName?: string
  gdsCode?: string
  policyGroupCode?: string
  policyGroupName?: string
  ownerUserId: number
  ownerName: string
  metricCode: string
  metricVersion: string
  targetValue?: number
  itemId?: number
  itemIds?: Record<string, number>
  gdsTargets?: Array<{ gdsCode: string; targetValue: number }>
  status: 'ACTIVE' | 'DRAFT' | 'PAUSED'
  remark?: string
}

export async function fetchTargets(params: { scene: TargetScene; period: string; status?: string; keyword?: string }) {
  const response = await http.get<ApiEnvelope<TargetListResult>>('/v1/business-configuration/targets', { params })
  return response.data.data
}

export async function fetchTargetMetrics() {
  const response = await http.get<ApiEnvelope<{ available: boolean; rows: TargetMetric[] }>>('/v1/business-configuration/targets/metrics')
  return response.data.data.rows
}

export async function fetchTargetOptions() {
  const response = await http.get<ApiEnvelope<TargetOptions>>('/v1/business-configuration/targets/options')
  return response.data.data
}

export async function saveTarget(input: SaveTargetInput) {
  const response = await http.post<ApiEnvelope<{ planId: number; itemIds: number[] }>>('/v1/business-configuration/targets', input)
  return response.data.data
}
