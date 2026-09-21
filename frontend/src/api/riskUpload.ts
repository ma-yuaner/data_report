import { http, type ApiEnvelope } from './http'

export type RiskUploadBusiness = 'issue' | 'refund' | 'change'
export type RiskUploadStatus = 'queued' | 'running' | 'success' | 'failed'

export interface RiskUploadDefinition {
  key: RiskUploadBusiness
  label: string
  targetTable: string
  defaultSheet: string
  writeMode: string
  requiresLoadDate: boolean
}

export interface RiskUploadJob {
  id: string
  businessType: RiskUploadBusiness
  targetTable: string
  originalName: string
  fileSize: number
  fileSha256: string
  sheetName: string
  loadDate: string | null
  status: RiskUploadStatus
  queuedAt: string
  startedAt: string | null
  finishedAt: string | null
  rowsRead: number | null
  rowsWritten: number | null
  message: string
  logs: string[]
}

export interface RiskUploadData {
  enabled: boolean
  tokenRequired: boolean
  historyAuthorized: boolean
  maxFileSizeMb: number
  definitions: RiskUploadDefinition[]
  jobs: RiskUploadJob[]
}

function tokenHeaders(token: string) {
  return token ? { 'X-Risk-Upload-Token': token } : undefined
}

export async function getRiskUploads(token = ''): Promise<RiskUploadData> {
  const response = await http.get<ApiEnvelope<RiskUploadData>>('/v1/risk-uploads', {
    headers: tokenHeaders(token),
  })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function createRiskUpload(
  definition: RiskUploadDefinition,
  file: File,
  sheetName: string,
  loadDate: string,
  token: string,
  onProgress: (percent: number) => void,
): Promise<RiskUploadJob> {
  const body = new FormData()
  body.append('businessType', definition.key)
  body.append('file', file)
  body.append('sheetName', sheetName)
  if (definition.requiresLoadDate) body.append('loadDate', loadDate)
  body.append('confirmOverwrite', 'true')
  const response = await http.post<ApiEnvelope<RiskUploadJob>>('/v1/risk-uploads', body, {
    headers: tokenHeaders(token),
    timeout: 10 * 60_000,
    onUploadProgress: event => {
      if (event.total) onProgress(Math.round(event.loaded * 100 / event.total))
    },
  })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
