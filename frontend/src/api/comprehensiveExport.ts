import { http, type ApiEnvelope } from './http'
import type { BusinessKey, FilterScope } from './comprehensive'
import type { GdsRouteScope } from './resourceGovernance'

export type ComprehensiveExportStatus =
  | 'QUEUED' | 'RUNNING' | 'CANCEL_REQUESTED' | 'CANCELLED'
  | 'SUCCEEDED' | 'FAILED' | 'EXPIRED'

export interface ComprehensiveExportTask {
  id: string
  businessType: BusinessKey | 'gds_routes'
  taskLabel?: string
  businessLabel: string
  startDate: string
  endDate: string
  status: ComprehensiveExportStatus
  totalRows: number
  processedRows: number
  queuedAt: string
  startedAt: string | null
  finishedAt: string | null
  updatedAt: string
  message: string
  downloadName: string | null
  canCancel: boolean
  canDownload: boolean
  reused: boolean
}

export async function listComprehensiveExports(): Promise<ComprehensiveExportTask[]> {
  const response = await http.get<ApiEnvelope<ComprehensiveExportTask[]>>('/v1/exports')
  return response.data.data
}

export async function createComprehensiveExport(
  scope: FilterScope,
  businessType: BusinessKey,
): Promise<ComprehensiveExportTask> {
  const { preset: _preset, ...values } = scope
  const response = await http.post<ApiEnvelope<ComprehensiveExportTask>>(
    '/v1/exports',
    { ...values, businessType },
  )
  return response.data.data
}

export async function cancelComprehensiveExport(id: string): Promise<ComprehensiveExportTask> {
  const response = await http.post<ApiEnvelope<ComprehensiveExportTask>>(
    `/v1/exports/${encodeURIComponent(id)}/cancel`,
  )
  return response.data.data
}

export function comprehensiveExportDownloadUrl(id: string) {
  return `/api/v1/exports/${encodeURIComponent(id)}/download`
}

export async function createGdsRouteExport(scope: GdsRouteScope): Promise<ComprehensiveExportTask> {
  const response = await http.post<ApiEnvelope<ComprehensiveExportTask>>('/v1/exports', { ...scope, kind: 'gds_routes' })
  return response.data.data
}
